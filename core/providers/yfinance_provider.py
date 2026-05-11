"""
core.providers.yfinance_provider
--------------------------------
YFinanceProvider — wraps the live market-data logic that previously lived
in core/market_data.py. Behavior is intentionally identical to the legacy
module functions (same signatures, same return shapes) so the shim in
core/market_data.py stays a drop-in re-export.
"""

from __future__ import annotations

from datetime import datetime, date

import pandas as pd

from core.engine import Option
# Re-export RISK_FREE_RATE so external code that did
# `from core.providers.yfinance_provider import RISK_FREE_RATE` still works.
from core.providers._bs import RISK_FREE_RATE, bs_greeks  # noqa: F401


def _ticker(symbol: str):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required for market data. Install with: pip install yfinance"
        ) from exc
    return yf.Ticker(symbol.upper())


def _add_mid(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'mid' column = (bid + ask) / 2, fallback to lastPrice."""
    df = df.copy()
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    mask = df["mid"] <= 0
    df.loc[mask, "mid"] = df.loc[mask, "lastPrice"]
    return df


class YFinanceProvider:
    """yfinance-backed implementation of MarketDataProvider."""

    def get_spot_price(self, ticker: str) -> float:
        t = _ticker(ticker)
        try:
            price = t.fast_info.last_price
            if price is None or price != price:
                raise ValueError
            return float(price)
        except Exception:
            hist = t.history(period="1d")
            if hist.empty:
                raise ValueError(f"Could not fetch spot price for {ticker!r}.")
            return float(hist["Close"].iloc[-1])

    def get_available_expiries(self, ticker: str) -> list[str]:
        t = _ticker(ticker)
        expiries = t.options
        if not expiries:
            raise ValueError(f"No options found for {ticker!r}. Check the ticker symbol.")
        return list(expiries)

    def get_options_chain(
        self,
        ticker: str,
        expiry: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        t = _ticker(ticker)
        chain = t.option_chain(expiry)
        cols = ["strike", "bid", "ask", "lastPrice",
                "impliedVolatility", "openInterest", "volume", "inTheMoney"]

        calls = _add_mid(chain.calls[[c for c in cols if c in chain.calls.columns]])
        puts  = _add_mid(chain.puts [[c for c in cols if c in chain.puts.columns]])

        # Best-effort Black-Scholes greeks. Same {delta, gamma, theta, vega}
        # schema and unit conventions as IBKRProvider so the TUI can render
        # either provider's output without re-formatting.
        try:
            spot = self.get_spot_price(ticker)
            exp_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
            t_years = max((exp_dt - date.today()).days / 365.0, 1.0 / 365.0)

            def _greeks_for(df: pd.DataFrame, opt_type: str) -> pd.DataFrame:
                def _row(r):
                    g = bs_greeks(spot, float(r["strike"]), t_years,
                                  float(r["impliedVolatility"]), opt_type)
                    return pd.Series(
                        [g["delta"], g["gamma"], g["theta"], g["vega"]],
                        index=["delta", "gamma", "theta", "vega"])
                return df.apply(_row, axis=1)

            if "impliedVolatility" in calls.columns:
                calls[["delta", "gamma", "theta", "vega"]] = _greeks_for(calls, "call")
            if "impliedVolatility" in puts.columns:
                puts[["delta", "gamma", "theta", "vega"]] = _greeks_for(puts, "put")
        except Exception:
            pass

        return calls, puts

    def get_option_premium(
        self,
        ticker: str,
        expiry: str,
        strike: float,
        option_type: str,
        price_source: str = "mid",
    ) -> float:
        calls, puts = self.get_options_chain(ticker, expiry)
        df = calls if option_type.lower() == "call" else puts

        exact = df[df["strike"] == strike]
        if not exact.empty:
            return float(exact[price_source].iloc[0])

        closest_row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
        actual_k = float(closest_row["strike"].values[0])
        print(f"  [market_data] Strike {strike} not found for {ticker} {expiry}. "
              f"Using closest available: {actual_k}")
        return float(closest_row[price_source].values[0])

    def build_option(
        self,
        ticker: str,
        expiry: str,
        strike: float,
        option_type: str,
        position: str,
        quantity: int = 1,
        price_source: str = "mid",
    ) -> Option:
        premium = self.get_option_premium(ticker, expiry, strike, option_type, price_source)
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()

        pos_short = "L" if position.lower() == "long" else "S"
        typ_short = "C" if option_type.lower() == "call" else "P"
        label = f"{pos_short} {ticker} {typ_short} K={strike:.0f} ({expiry})"

        return Option(
            option_type=option_type.lower(),
            position=position.lower(),
            strike=float(strike),
            premium=premium,
            expiry=expiry_date,
            quantity=quantity,
            label=label,
        )

    def display_chain(
        self,
        ticker: str,
        expiry: str,
        option_type: str = "call",
        atm_range: int = 10,
    ) -> pd.DataFrame:
        spot = self.get_spot_price(ticker)
        calls, puts = self.get_options_chain(ticker, expiry)
        df = calls if option_type.lower() == "call" else puts

        df = df.sort_values("strike").reset_index(drop=True)
        atm_idx = int((df["strike"] - spot).abs().idxmin())
        lo = max(atm_idx - atm_range, 0)
        hi = min(atm_idx + atm_range + 1, len(df))
        sub = df.iloc[lo:hi].copy()

        atm_strike = df.loc[atm_idx, "strike"]
        sub["ATM"] = sub["strike"].apply(lambda k: "<-- ATM" if k == atm_strike else "")

        display_cols = ["strike", "bid", "mid", "ask", "impliedVolatility",
                        "openInterest", "volume", "ATM"]
        display_cols = [c for c in display_cols if c in sub.columns]

        print(f"\n  {ticker}  {option_type.upper()}  —  Expiry: {expiry}  |  Spot: {spot:.2f}")
        print(sub[display_cols].to_string(index=False))
        return sub[display_cols]
