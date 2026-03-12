"""
strategies.py
-------------
Pre-built factory functions for common option strategies.
Each function returns a ready-to-use Strategy object.

Strategies included
-------------------
Single-leg
  long_call, short_call, long_put, short_put

Spreads (two legs)
  bull_call_spread, bear_call_spread
  bull_put_spread,  bear_put_spread

Volatility plays (two legs)
  long_straddle, short_straddle, long_strangle, short_strangle

Three / four legs
  long_call_butterfly, long_put_butterfly
  iron_condor, iron_butterfly

With underlying
  covered_call, protective_put
"""

from datetime import date

from core import Option, StockPosition, Strategy


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _opt(
    option_type: str,
    position: str,
    strike: float,
    premium: float,
    expiry: date,
    quantity: int,
    ticker: str = "",
) -> Option:
    pos_abbr = "L" if position == "long" else "S"
    typ = "C" if option_type == "call" else "P"
    ticker_str = f"{ticker} " if ticker else ""
    label = f"{pos_abbr} {ticker_str}{typ} K={strike:.2f}"
    if quantity > 1:
        label = f"{pos_abbr}x{quantity} {ticker_str}{typ} K={strike:.2f}"
    return Option(option_type, position, strike, premium, expiry, quantity, label=label)


# ---------------------------------------------------------------------------
# Single-leg
# ---------------------------------------------------------------------------

def long_call(
    strike: float,
    premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """Buy a call option."""
    return Strategy("Long Call", [_opt("call", "long", strike, premium, expiry, quantity, ticker)])


def short_call(
    strike: float,
    premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """Sell a naked call option."""
    return Strategy("Short Call", [_opt("call", "short", strike, premium, expiry, quantity, ticker)])


def long_put(
    strike: float,
    premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """Buy a put option."""
    return Strategy("Long Put", [_opt("put", "long", strike, premium, expiry, quantity, ticker)])


def short_put(
    strike: float,
    premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """Sell a cash-secured put."""
    return Strategy("Short Put", [_opt("put", "short", strike, premium, expiry, quantity, ticker)])


# ---------------------------------------------------------------------------
# Call spreads
# ---------------------------------------------------------------------------

def bull_call_spread(
    low_strike: float,
    low_premium: float,
    high_strike: float,
    high_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Buy low-strike call, sell high-strike call.
    Bullish view with capped profit and capped loss.
    Max profit = (high_K - low_K - net_debit) * qty
    Max loss   = net_debit * qty
    """
    return Strategy(
        "Bull Call Spread",
        [
            _opt("call", "long",  low_strike,  low_premium,  expiry, quantity, ticker),
            _opt("call", "short", high_strike, high_premium, expiry, quantity, ticker),
        ],
    )


def bear_call_spread(
    low_strike: float,
    low_premium: float,
    high_strike: float,
    high_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Sell low-strike call, buy high-strike call.
    Bearish / neutral view. Net credit received.
    Max profit = net_credit * qty
    Max loss   = (high_K - low_K - net_credit) * qty
    """
    return Strategy(
        "Bear Call Spread",
        [
            _opt("call", "short", low_strike,  low_premium,  expiry, quantity, ticker),
            _opt("call", "long",  high_strike, high_premium, expiry, quantity, ticker),
        ],
    )


# ---------------------------------------------------------------------------
# Put spreads
# ---------------------------------------------------------------------------

def bull_put_spread(
    low_strike: float,
    low_premium: float,
    high_strike: float,
    high_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Buy low-strike put, sell high-strike put.
    Bullish/neutral view. Net credit received.
    Max profit = net_credit * qty
    Max loss   = (high_K - low_K - net_credit) * qty
    """
    return Strategy(
        "Bull Put Spread",
        [
            _opt("put", "long",  low_strike,  low_premium,  expiry, quantity, ticker),
            _opt("put", "short", high_strike, high_premium, expiry, quantity, ticker),
        ],
    )


def bear_put_spread(
    low_strike: float,
    low_premium: float,
    high_strike: float,
    high_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Buy high-strike put, sell low-strike put.
    Bearish view. Net debit paid.
    Max profit = (high_K - low_K - net_debit) * qty
    Max loss   = net_debit * qty
    """
    return Strategy(
        "Bear Put Spread",
        [
            _opt("put", "long",  high_strike, high_premium, expiry, quantity, ticker),
            _opt("put", "short", low_strike,  low_premium,  expiry, quantity, ticker),
        ],
    )


# ---------------------------------------------------------------------------
# Volatility strategies
# ---------------------------------------------------------------------------

def long_straddle(
    strike: float,
    call_premium: float,
    put_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Buy ATM call + ATM put at the same strike.
    Profits from large moves in either direction.
    """
    return Strategy(
        "Long Straddle",
        [
            _opt("call", "long", strike, call_premium, expiry, quantity, ticker),
            _opt("put",  "long", strike, put_premium,  expiry, quantity, ticker),
        ],
    )


def short_straddle(
    strike: float,
    call_premium: float,
    put_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Sell ATM call + ATM put at the same strike.
    Profits from low volatility / little price movement.
    """
    return Strategy(
        "Short Straddle",
        [
            _opt("call", "short", strike, call_premium, expiry, quantity, ticker),
            _opt("put",  "short", strike, put_premium,  expiry, quantity, ticker),
        ],
    )


def long_strangle(
    put_strike: float,
    put_premium: float,
    call_strike: float,
    call_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Buy OTM put (lower strike) + OTM call (higher strike).
    Cheaper than straddle; needs a bigger move to profit.
    """
    return Strategy(
        "Long Strangle",
        [
            _opt("put",  "long", put_strike,  put_premium,  expiry, quantity, ticker),
            _opt("call", "long", call_strike, call_premium, expiry, quantity, ticker),
        ],
    )


def short_strangle(
    put_strike: float,
    put_premium: float,
    call_strike: float,
    call_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Sell OTM put + OTM call.
    Profits from low volatility within a wide range.
    """
    return Strategy(
        "Short Strangle",
        [
            _opt("put",  "short", put_strike,  put_premium,  expiry, quantity, ticker),
            _opt("call", "short", call_strike, call_premium, expiry, quantity, ticker),
        ],
    )


# ---------------------------------------------------------------------------
# Butterfly & condor
# ---------------------------------------------------------------------------

def long_call_butterfly(
    low_strike: float,
    low_premium: float,
    mid_strike: float,
    mid_premium: float,
    high_strike: float,
    high_premium: float,
    expiry: date,
    ticker: str = "",
) -> Strategy:
    """
    Buy 1 low-K call, sell 2 mid-K calls, buy 1 high-K call.
    Low cost, profits when underlying pins near mid_strike.
    """
    return Strategy(
        "Long Call Butterfly",
        [
            _opt("call", "long",  low_strike,  low_premium,  expiry, 1, ticker),
            _opt("call", "short", mid_strike,  mid_premium,  expiry, 2, ticker),
            _opt("call", "long",  high_strike, high_premium, expiry, 1, ticker),
        ],
    )


def long_put_butterfly(
    low_strike: float,
    low_premium: float,
    mid_strike: float,
    mid_premium: float,
    high_strike: float,
    high_premium: float,
    expiry: date,
    ticker: str = "",
) -> Strategy:
    """Buy 1 low-K put, sell 2 mid-K puts, buy 1 high-K put."""
    return Strategy(
        "Long Put Butterfly",
        [
            _opt("put", "long",  low_strike,  low_premium,  expiry, 1, ticker),
            _opt("put", "short", mid_strike,  mid_premium,  expiry, 2, ticker),
            _opt("put", "long",  high_strike, high_premium, expiry, 1, ticker),
        ],
    )


def iron_condor(
    low_put_strike: float,   low_put_premium: float,
    high_put_strike: float,  high_put_premium: float,
    low_call_strike: float,  low_call_premium: float,
    high_call_strike: float, high_call_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Bull put spread + Bear call spread combined.
    Long low put / Short high put / Short low call / Long high call.
    Net credit; profits when underlying stays within the two short strikes.

    Strike order: low_put_K < high_put_K < low_call_K < high_call_K
    """
    return Strategy(
        "Iron Condor",
        [
            _opt("put",  "long",  low_put_strike,   low_put_premium,   expiry, quantity, ticker),
            _opt("put",  "short", high_put_strike,  high_put_premium,  expiry, quantity, ticker),
            _opt("call", "short", low_call_strike,  low_call_premium,  expiry, quantity, ticker),
            _opt("call", "long",  high_call_strike, high_call_premium, expiry, quantity, ticker),
        ],
    )


def iron_butterfly(
    put_wing_strike: float,  put_wing_premium: float,
    atm_strike: float,       atm_call_premium: float, atm_put_premium: float,
    call_wing_strike: float, call_wing_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Buy OTM put wing + sell ATM put + sell ATM call + buy OTM call wing.
    Highest profit when underlying expires exactly at ATM strike.
    """
    return Strategy(
        "Iron Butterfly",
        [
            _opt("put",  "long",  put_wing_strike,  put_wing_premium,  expiry, quantity, ticker),
            _opt("put",  "short", atm_strike,       atm_put_premium,   expiry, quantity, ticker),
            _opt("call", "short", atm_strike,       atm_call_premium,  expiry, quantity, ticker),
            _opt("call", "long",  call_wing_strike, call_wing_premium, expiry, quantity, ticker),
        ],
    )


# ---------------------------------------------------------------------------
# Strategies that include the underlying stock
# ---------------------------------------------------------------------------

def covered_call(
    stock_entry: float,
    call_strike: float,
    call_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Long stock + Short OTM call.
    Generates income; caps upside at call_strike.
    """
    stock_label = f"Long{' x'+str(quantity) if quantity > 1 else ''} {''+ticker+' ' if ticker else ''}Stock @ {stock_entry:.2f}"
    return Strategy(
        "Covered Call",
        [
            StockPosition(stock_entry, "long",  quantity, label=stock_label),
            _opt("call", "short", call_strike, call_premium, expiry, quantity, ticker),
        ],
    )


def protective_put(
    stock_entry: float,
    put_strike: float,
    put_premium: float,
    expiry: date,
    quantity: int = 1,
    ticker: str = "",
) -> Strategy:
    """
    Long stock + Long OTM put.
    Insurance: limits downside; unlimited upside.
    """
    stock_label = f"Long{' x'+str(quantity) if quantity > 1 else ''} {''+ticker+' ' if ticker else ''}Stock @ {stock_entry:.2f}"
    return Strategy(
        "Protective Put",
        [
            StockPosition(stock_entry, "long", quantity, label=stock_label),
            _opt("put", "long", put_strike, put_premium, expiry, quantity, ticker),
        ],
    )
