"""
option_payoff
=============
A framework for computing and visualising option strategy payoffs.

Quick start
-----------
>>> from option_payoff import Strategy, Option, long_call, bull_call_spread, plot_payoff
>>> from datetime import date
>>> s = bull_call_spread(100, 3.5, 110, 1.0, date(2025, 6, 20))
>>> s.print_summary()
>>> plot_payoff(s)
"""

from .core import Option, StockPosition, Strategy

from .strategies import (
    long_call,
    short_call,
    long_put,
    short_put,
    bull_call_spread,
    bear_call_spread,
    bull_put_spread,
    bear_put_spread,
    long_straddle,
    short_straddle,
    long_strangle,
    short_strangle,
    long_call_butterfly,
    long_put_butterfly,
    iron_condor,
    iron_butterfly,
    covered_call,
    protective_put,
)

from .visualization import plot_payoff, plot_multi_strategies, plot_payoff_grid

# Market data is optional (requires yfinance + internet)
try:
    from .market_data import (
        get_spot_price,
        get_available_expiries,
        get_options_chain,
        get_option_premium,
        build_option,
        display_chain,
    )
    _MARKET_DATA_AVAILABLE = True
except ImportError:
    _MARKET_DATA_AVAILABLE = False

__all__ = [
    # Core
    "Option", "StockPosition", "Strategy",
    # Strategy factories
    "long_call", "short_call", "long_put", "short_put",
    "bull_call_spread", "bear_call_spread",
    "bull_put_spread", "bear_put_spread",
    "long_straddle", "short_straddle",
    "long_strangle", "short_strangle",
    "long_call_butterfly", "long_put_butterfly",
    "iron_condor", "iron_butterfly",
    "covered_call", "protective_put",
    # Visualisation
    "plot_payoff", "plot_multi_strategies", "plot_payoff_grid",
    # Market data (optional)
    "get_spot_price", "get_available_expiries",
    "get_options_chain", "get_option_premium",
    "build_option", "display_chain",
]
