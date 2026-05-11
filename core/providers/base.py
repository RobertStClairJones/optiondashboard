"""
core.providers.base
-------------------
Protocol describing the market-data provider interface. Implementations
(e.g. YFinanceProvider, IBKRProvider) should expose these methods.

Note: this Protocol is structural — Python does not enforce conformance at
runtime. The current YFinanceProvider keeps the legacy signatures from
core/market_data.py (tuple return on get_options_chain, price_source, etc.)
for zero-behavior-change in Phase 1. The Protocol will be reconciled when
IBKR support lands in Phase 2.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    def get_spot_price(self, ticker: str) -> float: ...
    def get_available_expiries(self, ticker: str) -> list[str]: ...
    def get_options_chain(self, ticker: str, expiry: str) -> pd.DataFrame: ...
    def get_option_premium(self, ticker: str, expiry: str,
                           strike: float, opt_type: str) -> float: ...
    def build_option(self, ticker: str, expiry: str,
                     strike: float, opt_type: str,
                     direction: str, contracts: int,
                     price_override: float | None) -> object: ...
