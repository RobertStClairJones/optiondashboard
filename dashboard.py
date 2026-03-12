"""
dashboard.py
------------
Streamlit interactive dashboard for option payoff visualisation.

Run with:
    streamlit run option_payoff/dashboard.py
or from the project root:
    streamlit run dashboard.py
"""

from __future__ import annotations

import sys
import os

# Allow running as `streamlit run option_payoff/dashboard.py` from any directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
from datetime import date, datetime, timedelta

import numpy as np
import streamlit as st

from option_payoff.core import Option, StockPosition, Strategy
from option_payoff.visualization import plot_payoff, plot_multi_strategies

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Option Payoff Visualiser",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Option Payoff Visualiser")
st.caption("Build custom option strategies, visualise payoff diagrams, and compute realised P&L.")

# ---------------------------------------------------------------------------
# Sidebar — mode selector
# ---------------------------------------------------------------------------

st.sidebar.header("Mode")
mode = st.sidebar.radio(
    "Data source",
    ["Manual entry", "Live market data (yfinance)"],
    index=0,
)

# ---------------------------------------------------------------------------
# Helper: session state for legs
# ---------------------------------------------------------------------------

if "legs" not in st.session_state:
    st.session_state.legs: list[dict] = []

if "strategy_name" not in st.session_state:
    st.session_state.strategy_name = "Custom Strategy"


def _add_leg(leg_dict: dict):
    st.session_state.legs.append(leg_dict)


def _clear_legs():
    st.session_state.legs = []


# ---------------------------------------------------------------------------
# Presets loader
# ---------------------------------------------------------------------------

PRESETS = {
    "— none —": None,
    "Long Call": [
        dict(type="call", pos="long",  K=100, prem=3.5, qty=1, expiry="2025-06-20"),
    ],
    "Bull Call Spread": [
        dict(type="call", pos="long",  K=100, prem=3.5, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="short", K=110, prem=1.0, qty=1, expiry="2025-06-20"),
    ],
    "Bear Call Spread": [
        dict(type="call", pos="short", K=100, prem=3.5, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="long",  K=110, prem=1.0, qty=1, expiry="2025-06-20"),
    ],
    "Long Straddle": [
        dict(type="call", pos="long", K=100, prem=3.5, qty=1, expiry="2025-06-20"),
        dict(type="put",  pos="long", K=100, prem=3.2, qty=1, expiry="2025-06-20"),
    ],
    "Long Strangle": [
        dict(type="put",  pos="long", K=95,  prem=2.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="long", K=105, prem=2.1, qty=1, expiry="2025-06-20"),
    ],
    "Long Call Butterfly": [
        dict(type="call", pos="long",  K=90,  prem=9.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="short", K=100, prem=4.5, qty=2, expiry="2025-06-20"),
        dict(type="call", pos="long",  K=110, prem=1.5, qty=1, expiry="2025-06-20"),
    ],
    "Iron Condor": [
        dict(type="put",  pos="long",  K=85,  prem=1.0, qty=1, expiry="2025-06-20"),
        dict(type="put",  pos="short", K=90,  prem=2.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="short", K=110, prem=2.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="long",  K=115, prem=1.0, qty=1, expiry="2025-06-20"),
    ],
    "Covered Call": [
        dict(type="stock", pos="long", K=100, prem=0,   qty=1, expiry="2025-06-20"),
        dict(type="call",  pos="short", K=110, prem=2.5, qty=1, expiry="2025-06-20"),
    ],
}


# ---------------------------------------------------------------------------
# Preset selector (sidebar)
# ---------------------------------------------------------------------------

st.sidebar.header("Quick Presets")
preset_choice = st.sidebar.selectbox("Load preset", list(PRESETS.keys()))

if st.sidebar.button("Load preset"):
    preset = PRESETS[preset_choice]
    if preset is not None:
        st.session_state.legs = [dict(l) for l in preset]
        st.session_state.strategy_name = preset_choice
        st.rerun()


# ---------------------------------------------------------------------------
# SECTION 1: Add legs
# ---------------------------------------------------------------------------

st.header("1 · Build Your Strategy")

# Strategy name
st.session_state.strategy_name = st.text_input(
    "Strategy name", value=st.session_state.strategy_name
)

# ── Manual entry ─────────────────────────────────────────────────────────────
if mode == "Manual entry":
    with st.expander("➕ Add a new leg", expanded=True):
        c1, c2, c3, c4, c5, c6 = st.columns([1.5, 1.5, 1.2, 1.2, 1.2, 1.5])

        opt_type = c1.selectbox("Type", ["call", "put", "stock (underlying)"], key="new_type")
        position = c2.selectbox("Position", ["long", "short"], key="new_pos")
        strike   = c3.number_input("Strike / Entry price", min_value=0.01,
                                   value=100.0, step=0.5, key="new_K")
        premium  = c4.number_input("Premium", min_value=0.0,
                                   value=3.50, step=0.05, key="new_prem",
                                   disabled=(opt_type == "stock (underlying)"))
        quantity = c5.number_input("Quantity", min_value=1, value=1,
                                   step=1, key="new_qty")
        expiry   = c6.date_input("Expiry", value=date.today() + timedelta(days=90),
                                 key="new_expiry")

        if st.button("Add leg"):
            _add_leg(dict(
                type=opt_type,
                pos=position,
                K=float(strike),
                prem=float(premium),
                qty=int(quantity),
                expiry=expiry.strftime("%Y-%m-%d"),
            ))
            st.rerun()

# ── Live market data ──────────────────────────────────────────────────────────
else:
    try:
        from option_payoff.market_data import (
            get_spot_price,
            get_available_expiries,
            get_options_chain,
        )
        market_ok = True
    except ImportError:
        st.error("yfinance is not installed. Run: pip install yfinance")
        market_ok = False

    if market_ok:
        with st.expander("🔍 Fetch from market", expanded=True):
            col_t, col_e = st.columns([2, 2])
            ticker_input = col_t.text_input("Ticker symbol", value="AAPL",
                                            placeholder="AAPL, SPY, TSLA…").upper()

            # Fetch expiries
            if st.button("Fetch expiry dates"):
                with st.spinner("Fetching…"):
                    try:
                        st.session_state["expiries"] = get_available_expiries(ticker_input)
                        st.session_state["spot"] = get_spot_price(ticker_input)
                        st.session_state["ticker"] = ticker_input
                    except Exception as exc:
                        st.error(str(exc))

            expiries = st.session_state.get("expiries", [])
            spot = st.session_state.get("spot")
            fetched_ticker = st.session_state.get("ticker", "")

            if spot:
                st.info(f"**{fetched_ticker}** spot price: **{spot:.2f}**")

            if expiries:
                chosen_expiry = col_e.selectbox("Expiry date", expiries)

                # Load chain
                if st.button("Load option chain"):
                    with st.spinner("Fetching chain…"):
                        try:
                            calls, puts = get_options_chain(fetched_ticker, chosen_expiry)
                            st.session_state["calls"] = calls
                            st.session_state["puts"] = puts
                            st.session_state["chosen_expiry"] = chosen_expiry
                        except Exception as exc:
                            st.error(str(exc))

                calls_df = st.session_state.get("calls")
                puts_df  = st.session_state.get("puts")

                if calls_df is not None:
                    cA, cB, cC, cD = st.columns([1.5, 1.5, 1.5, 1.5])
                    leg_type = cA.selectbox("Option type", ["call", "put"], key="mkt_type")
                    leg_pos  = cB.selectbox("Position", ["long", "short"], key="mkt_pos")
                    leg_qty  = cC.number_input("Quantity", 1, 100, 1, key="mkt_qty")
                    price_src = cD.selectbox("Price source", ["mid", "bid", "ask", "lastPrice"],
                                             key="mkt_psrc")

                    df_show = calls_df if leg_type == "call" else puts_df
                    chain_cols = ["strike", "bid", "mid", "ask",
                                  "impliedVolatility", "openInterest", "volume"]
                    chain_cols = [c for c in chain_cols if c in df_show.columns]

                    st.dataframe(
                        df_show[chain_cols].style.format({
                            "strike": "{:.2f}", "bid": "{:.2f}",
                            "mid": "{:.2f}", "ask": "{:.2f}",
                            "impliedVolatility": "{:.1%}",
                        }),
                        use_container_width=True,
                        height=220,
                    )

                    available_strikes = sorted(df_show["strike"].tolist())
                    chosen_strike = st.selectbox("Choose strike", available_strikes,
                                                  key="mkt_strike")

                    if st.button("Add this option leg"):
                        prem = float(df_show[df_show["strike"] == chosen_strike][price_src].iloc[0])
                        _add_leg(dict(
                            type=leg_type,
                            pos=leg_pos,
                            K=float(chosen_strike),
                            prem=prem,
                            qty=int(leg_qty),
                            expiry=st.session_state["chosen_expiry"],
                            ticker=fetched_ticker,
                        ))
                        st.rerun()


# ---------------------------------------------------------------------------
# SECTION 2: Current legs table
# ---------------------------------------------------------------------------

st.header("2 · Legs Summary")

if not st.session_state.legs:
    st.info("No legs added yet. Use the panel above or load a preset.")
else:
    col_leg, col_del = st.columns([5, 1])
    with col_leg:
        import pandas as pd
        rows = []
        for i, L in enumerate(st.session_state.legs):
            rows.append({
                "#":        i + 1,
                "Type":     L["type"],
                "Position": L["pos"],
                "Strike":   L["K"],
                "Premium":  L.get("prem", "—"),
                "Qty":      L["qty"],
                "Expiry":   L["expiry"],
                "Ticker":   L.get("ticker", "—"),
            })
        st.dataframe(pd.DataFrame(rows).set_index("#"), use_container_width=True)

    with col_del:
        st.write("")
        st.write("")
        if st.button("🗑 Clear all legs"):
            _clear_legs()
            st.rerun()

        remove_idx = st.number_input("Remove leg #", min_value=1,
                                     max_value=max(len(st.session_state.legs), 1),
                                     step=1, value=1)
        if st.button("Remove"):
            idx = int(remove_idx) - 1
            if 0 <= idx < len(st.session_state.legs):
                st.session_state.legs.pop(idx)
                st.rerun()


# ---------------------------------------------------------------------------
# SECTION 3: Plot settings
# ---------------------------------------------------------------------------

st.header("3 · Chart Settings")

cs1, cs2, cs3, cs4 = st.columns(4)
spot_lo   = cs1.number_input("Spot range — min",  value=50.0,  step=1.0)
spot_hi   = cs2.number_input("Spot range — max",  value=150.0, step=1.0)
n_points  = cs3.number_input("Resolution (pts)",  value=500,   step=50,
                              min_value=100, max_value=2000)
show_legs = cs4.checkbox("Show individual legs", value=True)

use_realized = st.checkbox("Mark realized spot at maturity")
realized_spot: float | None = None
if use_realized:
    realized_spot = st.number_input(
        "Actual spot price at expiry",
        value=100.0, step=0.5,
        help="Enter the observed underlying price on the expiry date to see your realized P&L."
    )

spot_range = np.linspace(float(spot_lo), float(spot_hi), int(n_points))


# ---------------------------------------------------------------------------
# SECTION 4: Build strategy & render
# ---------------------------------------------------------------------------

st.header("4 · Payoff Diagram")

if not st.session_state.legs:
    st.warning("Add at least one leg above.")
else:
    # Build Strategy from leg dicts
    strategy = Strategy(st.session_state.strategy_name)
    for L in st.session_state.legs:
        leg_type = L["type"]
        pos  = L["pos"]
        K    = float(L["K"])
        prem = float(L.get("prem", 0.0))
        qty  = int(L["qty"])
        exp  = datetime.strptime(L["expiry"], "%Y-%m-%d").date()
        ticker = L.get("ticker", "")

        if leg_type == "stock (underlying)" or leg_type == "stock":
            lbl = f"{'Long' if pos == 'long' else 'Short'} {ticker+' ' if ticker else ''}Stock @ {K:.2f}"
            strategy.add_leg(StockPosition(K, pos, qty, label=lbl))
        else:
            pos_s = "L" if pos == "long" else "S"
            typ_s = "C" if leg_type == "call" else "P"
            qty_s = f"x{qty} " if qty > 1 else ""
            tick_s = f"{ticker} " if ticker else ""
            label = f"{pos_s} {qty_s}{tick_s}{typ_s} K={K:.0f}"
            strategy.add_leg(
                Option(leg_type, pos, K, prem, exp, qty, label=label)
            )

    # ── Summary metrics ──
    summary = strategy.summary(spot_range)
    net = summary["net_premium"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Premium",
              f"{'Credit' if net >= 0 else 'Debit'} {abs(net):.2f}",
              delta=None)
    m2.metric("Max Profit",  f"{summary['max_profit']:.2f}")
    m3.metric("Max Loss",    f"{summary['max_loss']:.2f}")
    be = summary["breakeven_points"]
    m4.metric("Breakeven(s)", ", ".join(f"{b:.2f}" for b in be) if be else "None")

    if use_realized and realized_spot is not None:
        rpnl = strategy.realized_payoff(float(realized_spot))
        sign = "+" if rpnl >= 0 else ""
        color = "green" if rpnl >= 0 else "red"
        st.markdown(
            f"**Realised P&L at spot {realized_spot:.2f}:** "
            f"<span style='color:{color}; font-size:1.3em; font-weight:bold'>"
            f"{sign}{rpnl:.4f}</span>",
            unsafe_allow_html=True,
        )

    # ── Payoff chart ──
    fig, _ = plot_payoff(
        strategy,
        spot_range,
        show_legs=show_legs,
        realized_spot=float(realized_spot) if use_realized and realized_spot is not None else None,
        figsize=(12, 5.5),
    )
    st.pyplot(fig)

    # ── Payoff table (optional) ──
    with st.expander("Raw payoff table"):
        import pandas as pd
        step = max(1, len(spot_range) // 50)
        tbl_spots = spot_range[::step]
        tbl_pnl   = strategy.payoff_at_expiry(tbl_spots)
        df_tbl = pd.DataFrame({
            "Spot": tbl_spots.round(2),
            "Total P&L": tbl_pnl.round(4),
        })
        for i, leg in enumerate(strategy.legs):
            df_tbl[f"Leg {i+1}: {leg.label}"] = leg.payoff_at_expiry(tbl_spots).round(4)
        st.dataframe(df_tbl, use_container_width=True)


# ---------------------------------------------------------------------------
# SECTION 5: Compare strategies
# ---------------------------------------------------------------------------

with st.expander("📊 Compare multiple presets"):
    st.write("Select presets to overlay on a single chart.")
    preset_keys = [k for k in PRESETS if k != "— none —"]
    chosen_presets = st.multiselect("Presets to compare", preset_keys,
                                    default=["Bull Call Spread", "Bear Call Spread"])

    if chosen_presets and st.button("Compare"):
        strats = []
        for pk in chosen_presets:
            legs_dicts = PRESETS[pk]
            s = Strategy(pk)
            for L in legs_dicts:
                exp = datetime.strptime(L["expiry"], "%Y-%m-%d").date()
                if L["type"] == "stock":
                    s.add_leg(StockPosition(L["K"], L["pos"], L["qty"]))
                else:
                    s.add_leg(Option(L["type"], L["pos"], L["K"], L["prem"], exp, L["qty"]))
            strats.append(s)

        fig2, _ = plot_multi_strategies(strats, spot_range)
        st.pyplot(fig2)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "Built with [option_payoff](.) framework · "
    "Prices shown are per-share (×100 for one standard contract) · "
    "For educational purposes only — not financial advice."
)
