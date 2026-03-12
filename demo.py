"""
demo.py
-------
Quick examples showing the framework's capabilities.
Run with:  python option_payoff/demo.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
import numpy as np

from option_payoff import (
    Strategy, Option, StockPosition,
    long_call, bull_call_spread, long_straddle,
    iron_condor, covered_call,
    plot_payoff, plot_multi_strategies, plot_payoff_grid,
)

EXPIRY = date(2025, 6, 20)

# ---------------------------------------------------------------------------
# 1. Single long call
# ---------------------------------------------------------------------------
lc = long_call(strike=100, premium=3.5, expiry=EXPIRY, quantity=2)
lc.print_summary()

fig, ax = plot_payoff(lc)
fig.savefig("/tmp/long_call.png", dpi=120)
print("Saved: /tmp/long_call.png")

# ---------------------------------------------------------------------------
# 2. Bull call spread
# ---------------------------------------------------------------------------
bcs = bull_call_spread(100, 3.5, 110, 1.0, EXPIRY)
bcs.print_summary()

# Mark the realised spot (e.g. underlying closed at 107)
fig2, _ = plot_payoff(bcs, realized_spot=107.0)
fig2.savefig("/tmp/bull_call_spread.png", dpi=120)
print("Saved: /tmp/bull_call_spread.png")

# Compute realised P&L
pnl = bcs.realized_payoff(107.0)
print(f"Realised P&L at spot=107: {pnl:+.2f}")

# ---------------------------------------------------------------------------
# 3. Iron condor
# ---------------------------------------------------------------------------
ic = iron_condor(
    low_put_strike=85,  low_put_premium=1.0,
    high_put_strike=90, high_put_premium=2.0,
    low_call_strike=110, low_call_premium=2.0,
    high_call_strike=115, high_call_premium=1.0,
    expiry=EXPIRY,
)
ic.print_summary()

fig3, _ = plot_payoff(ic)
fig3.savefig("/tmp/iron_condor.png", dpi=120)
print("Saved: /tmp/iron_condor.png")

# ---------------------------------------------------------------------------
# 4. Covered call (stock + short call)
# ---------------------------------------------------------------------------
cc = covered_call(stock_entry=100, call_strike=110, call_premium=2.5, expiry=EXPIRY)
cc.print_summary()

# ---------------------------------------------------------------------------
# 5. Comparison grid
# ---------------------------------------------------------------------------
strategies = [
    bull_call_spread(100, 3.5, 110, 1.0, EXPIRY),
    long_straddle(100, 3.5, 3.2, EXPIRY),
    ic,
    cc,
]

fig4, _ = plot_payoff_grid(strategies, cols=2)
fig4.savefig("/tmp/strategy_grid.png", dpi=120)
print("Saved: /tmp/strategy_grid.png")

# ---------------------------------------------------------------------------
# 6. Manual strategy construction
# ---------------------------------------------------------------------------
custom = Strategy("Custom Ratio Spread")
custom.add_leg(Option("call", "long",  100, 3.0, EXPIRY, quantity=1, label="Buy 1 ATM Call"))
custom.add_leg(Option("call", "short", 110, 1.2, EXPIRY, quantity=2, label="Sell 2 OTM Calls"))
custom.print_summary()

# ---------------------------------------------------------------------------
# 7. Live market data (requires yfinance + internet)
# ---------------------------------------------------------------------------
def demo_market_data(ticker="AAPL"):
    try:
        from option_payoff import (
            get_spot_price, get_available_expiries,
            display_chain, build_option,
        )
    except ImportError:
        print("yfinance not available — skipping live data demo.")
        return

    spot = get_spot_price(ticker)
    print(f"\n{ticker} spot: {spot:.2f}")

    expiries = get_available_expiries(ticker)
    print(f"Available expiries (first 5): {expiries[:5]}")

    # Show near-ATM calls for the first expiry
    display_chain(ticker, expiries[0], option_type="call", atm_range=5)

    # Build a bull call spread from market data
    calls_expiry = expiries[1]   # second available expiry
    s = Strategy(f"{ticker} Bull Call Spread ({calls_expiry})")
    s.add_leg(build_option(ticker, calls_expiry, round(spot / 5) * 5,      "call", "long"))
    s.add_leg(build_option(ticker, calls_expiry, round(spot / 5) * 5 + 10, "call", "short"))
    s.print_summary()
    fig5, _ = plot_payoff(s, realized_spot=spot)
    fig5.savefig(f"/tmp/{ticker}_bcs.png", dpi=120)
    print(f"Saved /tmp/{ticker}_bcs.png")


if __name__ == "__main__":
    demo_market_data()
    print("\nAll demos complete.")
