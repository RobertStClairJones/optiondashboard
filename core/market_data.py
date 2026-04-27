"""
market_data.py
--------------
Live market data helpers using yfinance.

Functions
---------
get_spot_price(ticker)
    Fetch the current underlying price.

get_available_expiries(ticker)
    List all available option expiry dates.

get_options_chain(ticker, expiry)
    Return (calls_df, puts_df) with bid/ask/mid and greeks.

get_option_premium(ticker, expiry, strike, option_type, price_source)
    Convenience: fetch a single option's price.

build_option(ticker, expiry, strike, option_type, position, quantity, price_source)
    Create an Option object from live market data.

display_chain(ticker, expiry, option_type, atm_range)
    Pretty-print the option chain around the ATM strike.
"""

from __future__ import annotations

import math
from datetime import datetime, date

import pandas as pd

from core import Option


# Black-Scholes delta (no dividends, configurable risk-free rate).
_RISK_FREE_RATE = 0.04


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(spot: float, strike: float, t_years: float,
              iv: float, opt_type: str) -> float:
    """Return Black-Scholes delta. NaN-safe; returns float('nan') if inputs degenerate."""
    if (spot is None or strike is None or iv is None
            or spot <= 0 or strike <= 0 or iv <= 0 or t_years <= 0
            or iv != iv or spot != spot or strike != strike):
        return float("nan")
    sigma_sqrt_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (_RISK_FREE_RATE + 0.5 * iv * iv) * t_years) / sigma_sqrt_t
    if opt_type == "call":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    # Replace zeros/NaN with lastPrice
    mask = df["mid"] <= 0
    df.loc[mask, "mid"] = df.loc[mask, "lastPrice"]
    return df


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_spot_price(ticker: str) -> float:
    """
    Return the latest traded price of *ticker*.

    Parameters
    ----------
    ticker : e.g. 'AAPL', 'SPY', 'TSLA'

    Returns
    -------
    float
    """
    t = _ticker(ticker)
    try:
        price = t.fast_info.last_price
        if price is None or price != price:   # NaN check
            raise ValueError
        return float(price)
    except Exception:
        hist = t.history(period="1d")
        if hist.empty:
            raise ValueError(f"Could not fetch spot price for {ticker!r}.")
        return float(hist["Close"].iloc[-1])


def get_available_expiries(ticker: str) -> list[str]:
    """
    Return the list of option expiry date strings for *ticker*.
    Format: 'YYYY-MM-DD'.

    Parameters
    ----------
    ticker : e.g. 'AAPL'
    """
    t = _ticker(ticker)
    expiries = t.options
    if not expiries:
        raise ValueError(f"No options found for {ticker!r}. Check the ticker symbol.")
    return list(expiries)


def get_options_chain(
    ticker: str,
    expiry: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch the full options chain for *ticker* on *expiry*.

    Parameters
    ----------
    ticker : e.g. 'AAPL'
    expiry : 'YYYY-MM-DD' (must be in get_available_expiries)

    Returns
    -------
    (calls_df, puts_df) — both DataFrames have columns:
        strike, bid, ask, mid, lastPrice, impliedVolatility,
        openInterest, volume, inTheMoney
    """
    t = _ticker(ticker)
    chain = t.option_chain(expiry)
    cols = ["strike", "bid", "ask", "lastPrice",
            "impliedVolatility", "openInterest", "volume", "inTheMoney"]

    calls = _add_mid(chain.calls[[c for c in cols if c in chain.calls.columns]])
    puts  = _add_mid(chain.puts [[c for c in cols if c in chain.puts.columns]])

    # Best-effort Black-Scholes delta column. Shown as "Δ" in the TUI chain.
    try:
        spot = get_spot_price(ticker)
        exp_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
        t_years = max((exp_dt - date.today()).days / 365.0, 1.0 / 365.0)
        if "impliedVolatility" in calls.columns:
            calls["delta"] = calls.apply(
                lambda r: _bs_delta(spot, float(r["strike"]), t_years,
                                    float(r["impliedVolatility"]), "call"),
                axis=1,
            )
        if "impliedVolatility" in puts.columns:
            puts["delta"] = puts.apply(
                lambda r: _bs_delta(spot, float(r["strike"]), t_years,
                                    float(r["impliedVolatility"]), "put"),
                axis=1,
            )
    except Exception:
        pass

    return calls, puts


def get_option_premium(
    ticker: str,
    expiry: str,
    strike: float,
    option_type: str,
    price_source: str = "mid",
) -> float:
    """
    Return the market price for a specific option.

    Parameters
    ----------
    ticker       : underlying symbol
    expiry       : 'YYYY-MM-DD'
    strike       : desired strike price
    option_type  : 'call' or 'put'
    price_source : 'mid' (default), 'bid', 'ask', or 'lastPrice'

    Returns
    -------
    float — premium per share (not per contract)
    """
    calls, puts = get_options_chain(ticker, expiry)
    df = calls if option_type.lower() == "call" else puts

    # Exact match first
    exact = df[df["strike"] == strike]
    if not exact.empty:
        return float(exact[price_source].iloc[0])

    # Closest strike fallback
    closest_row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
    actual_k = float(closest_row["strike"].values[0])
    print(f"  [market_data] Strike {strike} not found for {ticker} {expiry}. "
          f"Using closest available: {actual_k}")
    return float(closest_row[price_source].values[0])


def build_option(
    ticker: str,
    expiry: str,
    strike: float,
    option_type: str,
    position: str,
    quantity: int = 1,
    price_source: str = "mid",
) -> Option:
    """
    Create an ``Option`` object populated with live market data.

    Parameters
    ----------
    ticker       : e.g. 'AAPL'
    expiry       : 'YYYY-MM-DD' — must be a valid expiry date
    strike       : strike price (nearest available is used if exact not found)
    option_type  : 'call' or 'put'
    position     : 'long' or 'short'
    quantity     : number of contracts (default 1)
    price_source : 'mid' | 'bid' | 'ask' | 'lastPrice'

    Returns
    -------
    Option
    """
    premium = get_option_premium(ticker, expiry, strike, option_type, price_source)
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
    ticker: str,
    expiry: str,
    option_type: str = "call",
    atm_range: int = 10,
) -> pd.DataFrame:
    """
    Pretty-print and return the options chain for the ATM neighbourhood.

    Parameters
    ----------
    ticker      : underlying symbol
    expiry      : 'YYYY-MM-DD'
    option_type : 'call' or 'put'
    atm_range   : number of strikes above/below ATM to show

    Returns
    -------
    pd.DataFrame (filtered slice)
    """
    spot = get_spot_price(ticker)
    calls, puts = get_options_chain(ticker, expiry)
    df = calls if option_type.lower() == "call" else puts

    # Sort and locate ATM
    df = df.sort_values("strike").reset_index(drop=True)
    atm_idx = int((df["strike"] - spot).abs().idxmin())
    lo = max(atm_idx - atm_range, 0)
    hi = min(atm_idx + atm_range + 1, len(df))
    sub = df.iloc[lo:hi].copy()

    # Highlight ATM row
    atm_strike = df.loc[atm_idx, "strike"]
    sub["ATM"] = sub["strike"].apply(lambda k: "<-- ATM" if k == atm_strike else "")

    display_cols = ["strike", "bid", "mid", "ask", "impliedVolatility",
                    "openInterest", "volume", "ATM"]
    display_cols = [c for c in display_cols if c in sub.columns]

    print(f"\n  {ticker}  {option_type.upper()}  —  Expiry: {expiry}  |  Spot: {spot:.2f}")
    print(sub[display_cols].to_string(index=False))
    return sub[display_cols]
