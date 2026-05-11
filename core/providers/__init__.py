"""
core.providers — factory for market-data providers.

Selection is controlled by the OPTIONDASH_PROVIDER environment variable.
Defaults to 'yfinance'. Valid options: 'yfinance', 'ibkr'.
"""

import os

from core.providers.yfinance_provider import YFinanceProvider


def get_provider():
    provider = os.getenv('OPTIONDASH_PROVIDER', 'yfinance').lower()
    if provider == 'yfinance':
        return YFinanceProvider()
    elif provider == 'ibkr':
        # Wrap IBKR in LegacyAdapter so the TUI sees the yfinance-shaped
        # interface uniformly across providers.
        from core.providers.ibkr_provider import IBKRProvider
        from core.providers.legacy_adapter import LegacyAdapter
        return LegacyAdapter(IBKRProvider())
    else:
        raise ValueError(f"Unknown provider: {provider}. "
                         f"Valid options: yfinance, ibkr")
