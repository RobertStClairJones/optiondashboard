# core package — re-export everything so existing imports stay unchanged
from core.engine import Option, StockPosition, Strategy
from core.market_data import (
    get_spot_price,
    get_available_expiries,
    get_options_chain,
    get_option_premium,
    build_option,
    display_chain,
)

__all__ = [
    "Option",
    "StockPosition",
    "Strategy",
    "get_spot_price",
    "get_available_expiries",
    "get_options_chain",
    "get_option_premium",
    "build_option",
    "display_chain",
]
