"""
market_data.py
--------------
Thin shim that preserves the legacy module-level API by delegating to the
default provider (YFinanceProvider). New code should prefer
``core.providers.get_provider()``.
"""

from core.providers.yfinance_provider import YFinanceProvider as _p

_provider = _p()

get_spot_price = _provider.get_spot_price
get_available_expiries = _provider.get_available_expiries
get_options_chain = _provider.get_options_chain
get_option_premium = _provider.get_option_premium
build_option = _provider.build_option
display_chain = _provider.display_chain
