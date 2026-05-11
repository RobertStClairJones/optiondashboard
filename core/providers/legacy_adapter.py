"""
core.providers.legacy_adapter
-----------------------------
LegacyAdapter — wraps an IBKRProvider and exposes the legacy
yfinance-shaped interface that the TUI was originally built against:

  * get_options_chain → tuple (calls_df, puts_df) with lowercase columns
    (strike, bid, ask, mid, lastPrice, impliedVolatility, openInterest,
     volume, delta, gamma, theta, vega)
  * get_option_premium accepts (and ignores) price_source — IBKR returns mid
  * build_option accepts (position, quantity, price_source) and maps onto
    IBKR's (direction, contracts, price_override) signature

Connection-layer access (_ib, _ensure_connected, inner) is forwarded so
the Phase 3 status workers don't care whether they hold an adapter or
the raw provider.
"""

from __future__ import annotations

import pandas as pd

from core.engine import Option
from core.providers.ibkr_provider import IBKRProvider


# IBKR -> yfinance column names. Mid stays as mid; we add a lastPrice copy
# of mid because IBKR doesn't expose lastPrice as a distinct field.
_RENAME = {
    "Strike": "strike",
    "Bid":    "bid",
    "Ask":    "ask",
    "Mid":    "mid",
    "IV":     "impliedVolatility",
    "OI":     "openInterest",
    "Volume": "volume",
    "Delta":  "delta",
    "Gamma":  "gamma",
    "Theta":  "theta",
    "Vega":   "vega",
}


class LegacyAdapter:
    """Provider-shaped façade with legacy column names + tuple-of-DFs output."""

    def __init__(self, inner: IBKRProvider):
        self._inner = inner

    # ------------------------------------------------------------------
    # Connection layer pass-through (used by Phase 3 status workers).
    # ------------------------------------------------------------------

    @property
    def inner(self) -> IBKRProvider:
        return self._inner

    @property
    def _ib(self):
        return self._inner._ib

    def _ensure_connected(self):
        return self._inner._ensure_connected()

    # ------------------------------------------------------------------
    # Public market-data API (legacy yfinance shape).
    # ------------------------------------------------------------------

    def get_spot_price(self, ticker: str) -> float:
        return self._inner.get_spot_price(ticker)

    def get_available_expiries(self, ticker: str) -> list[str]:
        return self._inner.get_available_expiries(ticker)

    def get_options_chain(self, ticker: str, expiry: str):
        """Split IBKR's single unified DataFrame into (calls, puts) and
        rename to legacy yfinance column names."""
        df = self._inner.get_options_chain(ticker, expiry)
        calls = df[df["Type"] == "C"].drop(columns=["Type"]).copy()
        puts  = df[df["Type"] == "P"].drop(columns=["Type"]).copy()
        for sub in (calls, puts):
            sub.rename(columns=_RENAME, inplace=True)
            # yfinance ships a lastPrice column; IBKR doesn't expose it cleanly,
            # so mirror mid into lastPrice for downstream compatibility.
            sub["lastPrice"] = sub["mid"]
        return calls.reset_index(drop=True), puts.reset_index(drop=True)

    def get_option_premium(self, ticker: str, expiry: str,
                           strike: float, option_type: str,
                           price_source: str = "mid") -> float:
        """price_source is accepted for API compatibility but ignored —
        IBKR always returns the mid of the snapshot."""
        return self._inner.get_option_premium(ticker, expiry, strike, option_type)

    def build_option(self, ticker: str, expiry: str, strike: float,
                     option_type: str, position: str, quantity: int = 1,
                     price_source: str = "mid") -> Option:
        """Maps yfinance-style kwargs onto IBKRProvider.build_option. Lets
        the inner provider re-fetch premium (price_override=None) so the
        leg's premium reflects current market mid."""
        return self._inner.build_option(
            ticker, expiry, strike, option_type,
            direction=position, contracts=quantity,
            price_override=None,
        )
