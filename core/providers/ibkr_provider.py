"""
core.providers.ibkr_provider
----------------------------
IBKRProvider — Interactive Brokers implementation of MarketDataProvider.

Connection is lazy and cached for the process lifetime. Connection params
come from env vars:
    IBKR_HOST              (default 127.0.0.1)
    IBKR_PORT              (default 4002)
    IBKR_CLIENT_ID         (default 2 — 1 is reserved for ad-hoc test scripts)
    IBKR_TIMEOUT           (default 10)
    IBKR_MARKET_DATA_TYPE  (default 3 — delayed-fallback; 1=live, 2=frozen,
                            3=delayed, 4=delayed-frozen)

Threading model
~~~~~~~~~~~~~~~
ib_insync requires a running asyncio event loop to service the socket
between requests (heartbeats, async message dispatch). When called from
a Textual @work(thread=True) worker, the worker thread has no running
loop — ib.connect() spins up a transient loop, the connect handshake
completes, and as soon as connect() returns the loop stops running.
Gateway then sees no heartbeats and disconnects the client within
seconds. That was the "connects then immediately disconnects" symptom.

Fix: one dedicated daemon thread (_loop_thread) owns a persistent
asyncio loop (loop.run_forever()). Every ib_insync call is scheduled
onto that loop via asyncio.run_coroutine_threadsafe. The IB() instance
itself is constructed inside a coroutine on the loop thread, so all
internal asyncio primitives bind to the correct loop from birth.

Output schema for get_options_chain (single DataFrame, not tuple — adapter
reshapes to legacy shape for the TUI):
    Strike, Type, Bid, Ask, Mid, IV, OI, Volume, Delta, Gamma, Theta, Vega
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
import threading
import traceback
from datetime import datetime, date
from typing import Optional

import pandas as pd

try:
    from ib_insync import IB, Stock, Option as IBOption
except ImportError as exc:
    raise ImportError(
        "ib_insync is required for the IBKR provider. "
        "Install with: pip install ib_insync"
    ) from exc

from core.engine import Option


log = logging.getLogger(__name__)


RISK_FREE_RATE = 0.04

_OPTIONS_CHAIN_COLUMNS = [
    "Strike", "Type", "Bid", "Ask", "Mid", "IV",
    "OI", "Volume", "Delta", "Gamma", "Theta", "Vega",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _is_bad(x) -> bool:
    """True if x is None or NaN."""
    if x is None:
        return True
    try:
        return math.isnan(x)
    except (TypeError, ValueError):
        return False


def _safe_mid(bid, ask, last) -> float:
    """Mid = (bid+ask)/2 when both positive, else fall back to last, else NaN."""
    if not _is_bad(bid) and not _is_bad(ask) and bid > 0 and ask > 0:
        return (float(bid) + float(ask)) / 2.0
    if not _is_bad(last) and last > 0:
        return float(last)
    return float("nan")


def _bs_greeks(spot, strike, t_years, iv, right) -> dict:
    """Black-Scholes greeks matching IBKR's unit conventions: vega per 1%
    IV change, theta per calendar day."""
    nan = float("nan")
    if (_is_bad(spot) or _is_bad(strike) or _is_bad(iv)
            or spot <= 0 or strike <= 0 or iv <= 0 or t_years <= 0):
        return {"delta": nan, "gamma": nan, "theta": nan, "vega": nan}
    sigma_sqrt_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (RISK_FREE_RATE + 0.5 * iv * iv) * t_years) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    pdf_d1 = _norm_pdf(d1)
    discount = math.exp(-RISK_FREE_RATE * t_years)
    gamma = pdf_d1 / (spot * sigma_sqrt_t)
    vega = (spot * pdf_d1 * math.sqrt(t_years)) / 100.0
    if str(right).upper().startswith("C"):
        delta = _norm_cdf(d1)
        theta_year = (-spot * pdf_d1 * iv / (2.0 * math.sqrt(t_years))
                      - RISK_FREE_RATE * strike * discount * _norm_cdf(d2))
    else:
        delta = _norm_cdf(d1) - 1.0
        theta_year = (-spot * pdf_d1 * iv / (2.0 * math.sqrt(t_years))
                      + RISK_FREE_RATE * strike * discount * _norm_cdf(-d2))
    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta_year / 365.0,
        "vega": vega,
    }


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class IBKRProvider:
    """Interactive Brokers market-data provider via ib_insync.

    Owns a dedicated daemon thread running a persistent asyncio loop;
    every ib_insync call is marshalled onto that loop so the connection
    stays alive between requests.
    """

    def __init__(self):
        self._ib: Optional[IB] = None
        self._host = os.getenv("IBKR_HOST", "127.0.0.1")
        self._port = int(os.getenv("IBKR_PORT", "4002"))
        self._client_id = int(os.getenv("IBKR_CLIENT_ID", "2"))
        self._timeout = int(os.getenv("IBKR_TIMEOUT", "10"))
        self._market_data_type = int(os.getenv("IBKR_MARKET_DATA_TYPE", "3"))

        # Dedicated asyncio loop, owned by a daemon thread. Lazy-started
        # on first call so importing this module doesn't spawn threads.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_lock = threading.Lock()

    # -- Loop / scheduling --------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Lazily start the dedicated loop thread. Idempotent."""
        with self._loop_lock:
            if (self._loop is not None and self._loop_thread is not None
                    and self._loop_thread.is_alive()):
                return self._loop
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def _runner() -> None:
                asyncio.set_event_loop(loop)
                ready.set()
                try:
                    loop.run_forever()
                finally:
                    loop.close()

            t = threading.Thread(target=_runner, daemon=True,
                                 name="ibkr-asyncio-loop")
            t.start()
            if not ready.wait(timeout=5):
                raise RuntimeError("IBKR asyncio loop failed to start within 5s")
            self._loop = loop
            self._loop_thread = t
            return loop

    def _run_coro(self, coro, *, timeout: Optional[float] = None):
        """Schedule *coro* on the dedicated loop and block for its result.

        timeout: per-call wait limit in seconds. ``None`` = use a generous
        default sized for connect/handshake + buffer. Snapshot-heavy calls
        (chain fetches) should pass a larger explicit timeout.
        """
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        wait = timeout if timeout is not None else (self._timeout + 30)
        return fut.result(timeout=wait)

    def _expiry_to_ib(self, expiry: str) -> str:
        return expiry.replace("-", "")

    # -- Connection (all async; sync wrappers schedule onto the loop) -------

    async def _ensure_connected_async(self) -> IB:
        """Runs on the loop thread. Returns a connected IB instance,
        creating + connecting one if necessary."""
        if self._ib is not None and self._ib.isConnected():
            return self._ib
        # Tear down any half-dead instance before re-creating.
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:
                pass
            self._ib = None
        ib = IB()  # constructed on the loop thread → primitives bind to this loop
        await ib.connectAsync(
            self._host, self._port,
            clientId=self._client_id, timeout=self._timeout,
        )
        try:
            ib.reqMarketDataType(self._market_data_type)
        except Exception as exc:
            log.warning("reqMarketDataType(%s) failed: %s",
                        self._market_data_type, exc)
        self._ib = ib
        return ib

    def _ensure_connected(self) -> IB:
        """Sync entry point used by app.py + the in-class sync methods.
        Schedules the async connect on the loop and normalizes exception
        types to the same ConnectionError surface as before."""
        try:
            return self._run_coro(self._ensure_connected_async())
        except ConnectionRefusedError as exc:
            self._diagnostic(exc)
            raise ConnectionError(
                f"IB Gateway not running on {self._host}:{self._port}"
            ) from exc
        except (TimeoutError, asyncio.TimeoutError) as exc:
            self._diagnostic(exc)
            raise ConnectionError(
                "IB Gateway connection timed out — check Trusted IPs setting"
            ) from exc
        except Exception as exc:
            self._diagnostic(exc)
            msg = str(exc) or type(exc).__name__
            if "timeout" in msg.lower():
                raise ConnectionError(
                    "IB Gateway connection timed out — check Trusted IPs setting"
                ) from exc
            raise ConnectionError(
                f"Failed to connect to IB Gateway at {self._host}:{self._port}: {msg}"
            ) from exc

    def _diagnostic(self, exc: BaseException) -> None:
        """Surface the exact failure to logging + stderr so it survives
        Textual's stderr capture (visible after the TUI exits)."""
        log.exception("ibkr _ensure_connected failed")
        print(f"[ibkr] _ensure_connected failed: {exc!r}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    # -- Market data --------------------------------------------------------

    def get_spot_price(self, ticker: str) -> float:
        return self._run_coro(self._get_spot_price_async(ticker), timeout=60)

    async def _get_spot_price_async(self, ticker: str) -> float:
        ib = await self._ensure_connected_async()
        stock = Stock(ticker.upper(), "SMART", "USD")
        await ib.qualifyContractsAsync(stock)
        snaps = await ib.reqTickersAsync(stock)
        if not snaps:
            raise ValueError(f"delayed/no data for {ticker}")
        snap = snaps[0]
        mid = _safe_mid(snap.bid, snap.ask, snap.last)
        if _is_bad(mid):
            close = getattr(snap, "close", None)
            if not _is_bad(close) and close > 0:
                log.warning("Using delayed close price for %s", ticker)
                return float(close)
            raise ValueError(f"delayed/no data for {ticker}")
        return float(mid)

    def get_available_expiries(self, ticker: str) -> list[str]:
        return self._run_coro(self._get_available_expiries_async(ticker),
                              timeout=60)

    async def _get_available_expiries_async(self, ticker: str) -> list[str]:
        ib = await self._ensure_connected_async()
        stock = Stock(ticker.upper(), "SMART", "USD")
        await ib.qualifyContractsAsync(stock)
        chains = await ib.reqSecDefOptParamsAsync(
            stock.symbol, "", stock.secType, stock.conId)
        if not chains:
            raise ValueError(f"No options found for {ticker!r}")
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        expiries = sorted(chain.expirations)
        return [f"{e[:4]}-{e[4:6]}-{e[6:8]}" for e in expiries]

    def get_options_chain(self, ticker: str, expiry: str) -> pd.DataFrame:
        # Chain fetches can be slow — wide chains require a snapshot per
        # contract. Give them up to 5 minutes.
        return self._run_coro(self._get_options_chain_async(ticker, expiry),
                              timeout=300)

    async def _get_options_chain_async(self, ticker: str, expiry: str) -> pd.DataFrame:
        ib = await self._ensure_connected_async()
        symbol = ticker.upper()
        stock = Stock(symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(stock)
        chains = await ib.reqSecDefOptParamsAsync(
            stock.symbol, "", stock.secType, stock.conId)
        if not chains:
            log.warning("No option chain for %s", ticker)
            return pd.DataFrame(columns=_OPTIONS_CHAIN_COLUMNS)
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        expiry_ib = self._expiry_to_ib(expiry)
        if expiry_ib not in chain.expirations:
            raise ValueError(f"Expiry {expiry} not available for {ticker}")

        # Inline spot fetch (reuse same connection / loop).
        try:
            spot_snaps = await ib.reqTickersAsync(stock)
            spot = _safe_mid(spot_snaps[0].bid, spot_snaps[0].ask,
                             spot_snaps[0].last) if spot_snaps else float("nan")
        except Exception:
            spot = float("nan")

        try:
            exp_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
            t_years = max((exp_dt - date.today()).days / 365.0, 1.0 / 365.0)
        except Exception:
            t_years = 1.0 / 365.0

        contracts = [
            IBOption(symbol, expiry_ib, float(strike), right, "SMART")
            for strike in sorted(chain.strikes)
            for right in ("C", "P")
        ]
        qualified = await ib.qualifyContractsAsync(*contracts)
        valid = [c for c in qualified if getattr(c, "conId", 0)]
        if not valid:
            log.warning("No qualified option contracts for %s %s", ticker, expiry)
            return pd.DataFrame(columns=_OPTIONS_CHAIN_COLUMNS)

        tickers = await ib.reqTickersAsync(*valid)
        rows = []
        all_nan_quotes = True

        for tk in tickers:
            c = tk.contract
            bid, ask, last = tk.bid, tk.ask, tk.last
            mid = _safe_mid(bid, ask, last)

            iv = None
            delta = gamma = theta = vega = None
            mg = getattr(tk, "modelGreeks", None)
            if mg is not None:
                iv = getattr(mg, "impliedVol", None)
                delta = getattr(mg, "delta", None)
                gamma = getattr(mg, "gamma", None)
                theta = getattr(mg, "theta", None)
                vega = getattr(mg, "vega", None)

            if any(_is_bad(g) for g in (delta, gamma, theta, vega)):
                if not _is_bad(iv) and not _is_bad(spot):
                    bs = _bs_greeks(spot, c.strike, t_years, iv, c.right)
                    if _is_bad(delta): delta = bs["delta"]
                    if _is_bad(gamma): gamma = bs["gamma"]
                    if _is_bad(theta): theta = bs["theta"]
                    if _is_bad(vega):  vega  = bs["vega"]

            if not _is_bad(bid) or not _is_bad(ask):
                all_nan_quotes = False

            oi = tk.callOpenInterest if c.right == "C" else tk.putOpenInterest

            rows.append({
                "Strike": float(c.strike),
                "Type": c.right,
                "Bid": float(bid) if not _is_bad(bid) else float("nan"),
                "Ask": float(ask) if not _is_bad(ask) else float("nan"),
                "Mid": float(mid) if not _is_bad(mid) else float("nan"),
                "IV": float(iv) if not _is_bad(iv) else float("nan"),
                "OI": float(oi) if not _is_bad(oi) else float("nan"),
                "Volume": float(tk.volume) if not _is_bad(tk.volume) else float("nan"),
                "Delta": float(delta) if not _is_bad(delta) else float("nan"),
                "Gamma": float(gamma) if not _is_bad(gamma) else float("nan"),
                "Theta": float(theta) if not _is_bad(theta) else float("nan"),
                "Vega":  float(vega)  if not _is_bad(vega)  else float("nan"),
            })

        df = pd.DataFrame(rows, columns=_OPTIONS_CHAIN_COLUMNS)
        df[["Bid", "Ask"]] = df[["Bid", "Ask"]].replace(-1, float("nan"))

        if all_nan_quotes and len(df) > 0:
            log.warning("delayed data for %s %s — all bid/ask are NaN", ticker, expiry)

        return df.sort_values(["Strike", "Type"]).reset_index(drop=True)

    def get_option_premium(self, ticker: str, expiry: str,
                           strike: float, opt_type: str) -> float:
        return self._run_coro(
            self._get_option_premium_async(ticker, expiry, strike, opt_type),
            timeout=60)

    async def _get_option_premium_async(self, ticker: str, expiry: str,
                                        strike: float, opt_type: str) -> float:
        ib = await self._ensure_connected_async()
        right = "C" if str(opt_type).lower().startswith("c") else "P"
        contract = IBOption(ticker.upper(), self._expiry_to_ib(expiry),
                            float(strike), right, "SMART")
        await ib.qualifyContractsAsync(contract)
        snaps = await ib.reqTickersAsync(contract)
        if not snaps:
            log.warning("No market data for %s %s %s %s", ticker, expiry, strike, opt_type)
            return float("nan")
        tk = snaps[0]
        mid = _safe_mid(tk.bid, tk.ask, tk.last)
        if _is_bad(mid):
            log.warning("No market data for %s %s %s %s", ticker, expiry, strike, opt_type)
            return float("nan")
        return float(mid)

    def build_option(self, ticker: str, expiry: str,
                     strike: float, opt_type: str,
                     direction: str, contracts: int,
                     price_override: float | None) -> Option:
        if price_override is not None:
            premium = float(price_override)
        else:
            premium = self.get_option_premium(ticker, expiry, strike, opt_type)
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        position = direction.lower()
        typ_short = "C" if str(opt_type).lower().startswith("c") else "P"
        pos_short = "L" if position == "long" else "S"
        label = f"{pos_short} {ticker.upper()} {typ_short} K={float(strike):.0f} ({expiry})"
        return Option(
            option_type="call" if typ_short == "C" else "put",
            position=position,
            strike=float(strike),
            premium=premium,
            expiry=expiry_date,
            quantity=int(contracts),
            label=label,
        )
