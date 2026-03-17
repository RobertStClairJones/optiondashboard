"""
dashboard.py
------------
Streamlit interactive dashboard for option payoff visualisation.

Run with:
    streamlit run dashboard.py
"""

from __future__ import annotations

import sys
import os
import json
from pathlib import Path


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import warnings
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from core import Option, StockPosition, Strategy
from visualization import plot_payoff_plotly, plot_multi_strategies
from utils.export_pdf import export_pdf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Options Dashboard",
    page_icon=None,
    layout="wide",
)

# ---------------------------------------------------------------------------
# Saved charts directory
# ---------------------------------------------------------------------------

SAVED_CHARTS_DIR = Path(__file__).parent / "saved_charts"
SAVED_CHARTS_DIR.mkdir(exist_ok=True)

SAVED_PDFS_DIR = Path(__file__).parent / "saved_pdfs"
SAVED_PDFS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Sentiment options
# ---------------------------------------------------------------------------

SENTIMENT_OPTIONS = [
    "Very Bearish",
    "Bearish",
    "Neutral",
    "Directional",
    "Bullish",
    "Very Bullish",
]

# Maps each sentiment to the 1-2 most fitting presets (must match keys in PRESETS)
SENTIMENT_PRESETS: dict[str, list[str]] = {
    "Very Bearish":  ["Bear Call Spread"],
    "Bearish":       ["Bear Call Spread"],
    "Neutral":       ["Iron Condor", "Long Call Butterfly"],
    "Directional":   ["Long Straddle", "Long Strangle"],
    "Bullish":       ["Bull Call Spread", "Long Call"],
    "Very Bullish":  ["Long Call", "Bull Call Spread"],
}

# ---------------------------------------------------------------------------
# Custom CSS — dark navy trading-platform aesthetic
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* ---- Base ---- */
[data-testid="stAppViewContainer"] {
    background-color: #0d1b2a;
}
[data-testid="stHeader"] {
    background-color: #0d1b2a;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background-color: #0a1520 !important;
    border-right: 1px solid #1e3a5f;
}
[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}

/* ---- Section headers ---- */
.section-header {
    font-size: 13px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin: 28px 0 10px 0;
}

/* ---- Sentiment button row ---- */
.sentiment-row {
    display: flex;
    gap: 10px;
    margin: 8px 0 20px 0;
    flex-wrap: wrap;
}
.sent-btn {
    background: #1a2744;
    border: 2px solid #2a3f6a;
    border-radius: 50px;
    padding: 8px 18px;
    color: #94a3b8;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.18s ease;
    white-space: nowrap;
    text-align: center;
}
.sent-btn:hover {
    border-color: #3b82f6;
    color: #bfdbfe;
}
.sent-btn.active {
    background: #1d4ed8;
    border-color: #60a5fa;
    color: #ffffff;
    box-shadow: 0 0 14px rgba(59,130,246,0.35);
}

/* ---- Metric cards ---- */
[data-testid="metric-container"] {
    background: #1a2744 !important;
    border: 1px solid #2a3f6a !important;
    border-radius: 12px !important;
    padding: 16px !important;
}
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 12px !important; }
[data-testid="stMetricValue"] { color: #e2e8f0 !important; }

/* ---- Inputs ---- */
input, textarea, select {
    background-color: #1a2744 !important;
    border: 1px solid #2a3f6a !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}
label { color: #94a3b8 !important; font-size: 13px !important; }

/* ---- Dataframe ---- */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #2a3f6a;
}

/* ---- Expanders ---- */
details {
    background: #1a2744 !important;
    border: 1px solid #2a3f6a !important;
    border-radius: 10px !important;
    padding: 4px 0;
}
summary {
    color: #e2e8f0 !important;
    font-weight: 600 !important;
}

/* ---- Divider ---- */
hr { border-color: #1e3a5f !important; margin: 20px 0 !important; }

/* ---- Info / Warning boxes ---- */
[data-testid="stInfo"]    { background: #1a2744; border-left: 3px solid #3b82f6; border-radius: 8px; }
[data-testid="stWarning"] { background: #1a2744; border-left: 3px solid #f59e0b; border-radius: 8px; }
[data-testid="stSuccess"] { background: #1a2744; border-left: 3px solid #22c55e; border-radius: 8px; }
[data-testid="stError"]   { background: #1a2744; border-left: 3px solid #ef4444; border-radius: 8px; }

/* ---- Tab strip ---- */
[data-testid="stTabs"] button {
    color: #64748b !important;
    font-weight: 600 !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #3b82f6 !important;
    border-bottom: 2px solid #3b82f6 !important;
}

/* ---- General text ---- */
p, span, div { color: #e2e8f0; }
h1, h2, h3 { color: #f1f5f9 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

for _k, _v in {
    "legs": [],
    "strategy_name": "Custom Strategy",
    "sentiment": "Bullish",
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_leg(leg_dict: dict):
    st.session_state.legs.append(leg_dict)


def _clear_legs():
    st.session_state.legs = []


@st.cache_data(ttl=3600)
def _get_company_name(ticker: str) -> str:
    """Return the long company name for a ticker via yfinance, or empty string."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return info.get("longName") or info.get("shortName") or ""
    except Exception:
        return ""


def _compute_auto_range(legs: list[dict], padding: float = 0.30) -> tuple[float, float]:
    ref_prices = [L["K"] for L in legs]
    if not ref_prices:
        return 50.0, 150.0
    lo, hi = min(ref_prices), max(ref_prices)
    mid = (lo + hi) / 2
    spread = max(hi - lo, mid * 0.15)
    lo_plot = max(lo - spread * (1 + padding), 0.01)
    hi_plot = hi + spread * (1 + padding)
    return round(lo_plot, 2), round(hi_plot, 2)


def save_chart(strategy: Strategy, fig, spot_range: np.ndarray, summary: dict, ticker: str = "") -> str:
    """Serialise a chart to JSON and write to saved_charts/. Returns filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in strategy.name)
    filename = f"{timestamp}_{safe_name}.json"
    filepath = SAVED_CHARTS_DIR / filename

    data = {
        "ticker": ticker,
        "strategy_name": strategy.name,
        "date_saved": datetime.now().isoformat(),
        "summary": summary,
        "legs": st.session_state.legs,
        "spot_range": [float(spot_range[0]), float(spot_range[-1]), len(spot_range)],
        "figure_json": fig.to_json(),
    }

    with open(filepath, "w") as f:
        json.dump(data, f, default=str)

    return filename


def load_saved_charts() -> list[dict]:
    """Return saved chart metadata sorted newest-first."""
    charts = []
    for filepath in sorted(SAVED_CHARTS_DIR.glob("*.json"), reverse=True):
        try:
            with open(filepath) as f:
                data = json.load(f)
            data["_filepath"] = str(filepath)
            data["_filename"] = filepath.name
            charts.append(data)
        except Exception:
            continue
    return charts


# ---------------------------------------------------------------------------
# Presets
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
        dict(type="stock", pos="long",  K=100, prem=0,   qty=1, expiry="2025-06-20"),
        dict(type="call",  pos="short", K=110, prem=2.5, qty=1, expiry="2025-06-20"),
    ],
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Settings")

    mode = st.radio(
        "Data source",
        ["Manual entry", "Live market data"],
        index=0,
    )

    st.divider()

    st.markdown("### Quick Presets")
    preset_choice = st.selectbox("Preset", list(PRESETS.keys()), label_visibility="collapsed")
    if st.button("Load preset", use_container_width=True):
        preset = PRESETS[preset_choice]
        if preset is not None:
            st.session_state.legs = [dict(l) for l in preset]
            st.session_state.strategy_name = preset_choice
            st.rerun()

# ---------------------------------------------------------------------------
# Page tabs
# ---------------------------------------------------------------------------

tab_dashboard, tab_saved = st.tabs(["Dashboard", "Saved Charts"])

# ===========================================================================
# TAB: SAVED CHARTS
# ===========================================================================

with tab_saved:
    st.markdown("## Saved Charts")
    st.caption("All previously saved payoff visualisations.")

    charts = load_saved_charts()

    if not charts:
        st.info("No saved charts yet. Go to the Dashboard, build a strategy, and click **Save Chart**.")
    else:
        for chart_data in charts:
            saved_dt = datetime.fromisoformat(chart_data["date_saved"])
            ticker_str = chart_data.get("ticker") or "—"
            strat_name = chart_data.get("strategy_name", "Unknown")
            summary = chart_data.get("summary", {})

            with st.expander(
                f"**{strat_name}** · {ticker_str} · {saved_dt.strftime('%d %b %Y, %H:%M')}",
                expanded=False,
            ):
                c1, c2, c3, c4 = st.columns(4)
                net = summary.get("net_premium", 0)
                be = summary.get("breakeven_points", [])
                c1.metric("Max Profit", f"{summary.get('max_profit', 0):.2f}")
                c2.metric("Max Loss",   f"{summary.get('max_loss', 0):.2f}")
                c3.metric("Net Premium", f"{'Cr' if net >= 0 else 'Dr'} {abs(net):.2f}")
                c4.metric("Breakeven(s)", ", ".join(f"{b:.2f}" for b in be) if be else "—")

                try:
                    import plotly.io as pio
                    fig_saved = pio.from_json(chart_data["figure_json"])
                    st.plotly_chart(fig_saved, use_container_width=True)
                except Exception as e:
                    st.error(f"Could not render chart: {e}")

                if st.button("Delete", key=f"del_{chart_data['_filename']}"):
                    os.remove(chart_data["_filepath"])
                    st.rerun()

# ===========================================================================
# TAB: DASHBOARD
# ===========================================================================

with tab_dashboard:

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------

    st.markdown("## Options Dashboard")

    # -----------------------------------------------------------------------
    # Sentiment selector
    # -----------------------------------------------------------------------

    st.markdown('<div class="section-header">Market Sentiment</div>', unsafe_allow_html=True)

    sent_cols = st.columns(len(SENTIMENT_OPTIONS))
    for i, label in enumerate(SENTIMENT_OPTIONS):
        with sent_cols[i]:
            is_active = st.session_state.sentiment == label
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"sent_{label}", use_container_width=True, type=btn_type):
                st.session_state.sentiment = label
                st.rerun()

    # Sentiment — strategy suggestions
    _suggestions = [s for s in SENTIMENT_PRESETS.get(st.session_state.sentiment, [])
                    if s in PRESETS]
    if _suggestions:
        st.markdown(
            f'<div style="background:#1a2744;border:1px solid #2a3f6a;border-radius:8px;'
            f'padding:10px 14px;margin:8px 0 4px 0;font-size:13px;color:#94a3b8;">'
            f'<b style="color:#e2e8f0">{st.session_state.sentiment}</b> — '
            f'suggested strategies: '
            + " · ".join(f'<span style="color:#3b82f6">{s}</span>' for s in _suggestions)
            + '</div>',
            unsafe_allow_html=True,
        )
        _sug_cols = st.columns(len(_suggestions))
        for _i, _s in enumerate(_suggestions):
            with _sug_cols[_i]:
                if st.button(f"Load {_s}", key=f"load_sug_{_s}", use_container_width=True):
                    st.session_state.legs = [dict(l) for l in PRESETS[_s]]
                    st.session_state.strategy_name = _s
                    st.rerun()

    # -----------------------------------------------------------------------
    # Target price & budget
    # -----------------------------------------------------------------------

    tp_col, bud_col, _ = st.columns([1, 1, 2])
    target_price = tp_col.number_input(
        "Target Price",
        min_value=0.0, value=0.0, step=1.0, format="%.2f",
        help=(
            "Where you expect the underlying to be at expiry. "
            "Set above 0 to see a target marker on the payoff chart "
            "and the expected P&L at that price."
        ),
    )
    budget = bud_col.number_input(
        "Max Budget ($)",
        min_value=0.0, value=0.0, step=10.0, format="%.0f",
        help=(
            "Maximum you are willing to pay in net premium (debit strategies). "
            "A warning appears if the strategy cost exceeds this amount."
        ),
    )

    st.divider()

    # -----------------------------------------------------------------------
    # Build strategy
    # -----------------------------------------------------------------------

    st.markdown('<div class="section-header">Build Strategy</div>', unsafe_allow_html=True)

    name_col, _ = st.columns([2, 2])
    st.session_state.strategy_name = name_col.text_input(
        "Strategy name",
        value=st.session_state.strategy_name,
        label_visibility="collapsed",
        placeholder="Strategy name…",
    )

    # -- Manual entry ---------------------------------------------------------
    if mode == "Manual entry":
        with st.expander("➕ Add a new leg", expanded=not bool(st.session_state.legs)):
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

            if st.button("Add leg", type="primary"):
                _add_leg(dict(
                    type=opt_type,
                    pos=position,
                    K=float(strike),
                    prem=float(premium),
                    qty=int(quantity),
                    expiry=expiry.strftime("%Y-%m-%d"),
                ))
                st.rerun()

    # -- Live market data -----------------------------------------------------
    else:
        try:
            from market_data import get_spot_price, get_available_expiries, get_options_chain
            market_ok = True
        except ImportError:
            st.error("yfinance is not installed. Run: pip install yfinance")
            market_ok = False

        if market_ok:
            with st.expander("🌐 Fetch from market", expanded=True):
                col_t, col_e = st.columns([2, 2])
                ticker_input = col_t.text_input(
                    "Ticker symbol", value="AAPL", placeholder="AAPL, SPY, TSLA…"
                ).upper()

                if st.button("Fetch expiry dates", type="primary"):
                    with st.spinner("Fetching…"):
                        try:
                            st.session_state["expiries"] = get_available_expiries(ticker_input)
                            st.session_state["spot"]     = get_spot_price(ticker_input)
                            st.session_state["ticker"]   = ticker_input
                        except Exception as exc:
                            st.error(str(exc))

                expiries        = st.session_state.get("expiries", [])
                spot            = st.session_state.get("spot")
                fetched_ticker  = st.session_state.get("ticker", "")

                if spot:
                    st.info(f"**{fetched_ticker}** spot price: **{spot:.2f}**")

                if expiries:
                    chosen_expiry = col_e.selectbox("Expiry date", expiries, label_visibility="collapsed")

                    if st.button("Load option chain"):
                        with st.spinner("Fetching chain…"):
                            try:
                                calls, puts = get_options_chain(fetched_ticker, chosen_expiry)
                                st.session_state["calls"]          = calls
                                st.session_state["puts"]           = puts
                                st.session_state["chosen_expiry"]  = chosen_expiry
                            except Exception as exc:
                                st.error(str(exc))

                    calls_df = st.session_state.get("calls")
                    puts_df  = st.session_state.get("puts")

                    if calls_df is not None:
                        cA, cB, cC, cD = st.columns([1.5, 1.5, 1.5, 1.5])
                        leg_type  = cA.selectbox("Option type", ["call", "put"], key="mkt_type")
                        leg_pos   = cB.selectbox("Position", ["long", "short"], key="mkt_pos")
                        leg_qty   = cC.number_input("Quantity", 1, 100, 1, key="mkt_qty")
                        price_src = cD.selectbox("Price source", ["mid", "bid", "ask", "lastPrice"],
                                                 key="mkt_psrc")

                        df_show    = calls_df if leg_type == "call" else puts_df
                        chain_cols = ["strike", "bid", "mid", "ask",
                                      "impliedVolatility", "openInterest", "volume"]
                        chain_cols = [c for c in chain_cols if c in df_show.columns]

                        st.dataframe(
                            df_show[chain_cols].style.format({
                                "strike": "{:.2f}", "bid": "{:.2f}",
                                "mid": "{:.2f}",    "ask": "{:.2f}",
                                "impliedVolatility": "{:.1%}",
                            }),
                            use_container_width=True,
                            height=220,
                        )

                        available_strikes = sorted(df_show["strike"].tolist())
                        chosen_strike = st.selectbox("Choose strike", available_strikes, key="mkt_strike")

                        if st.button("Add this option leg", type="primary"):
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

    # -----------------------------------------------------------------------
    # Legs summary
    # -----------------------------------------------------------------------

    if st.session_state.legs:
        st.markdown('<div class="section-header">Legs Summary</div>', unsafe_allow_html=True)

        col_leg, col_del = st.columns([5, 1])
        with col_leg:
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
            if st.button("Clear all", use_container_width=True):
                _clear_legs()
                st.rerun()

            remove_idx = st.number_input(
                "Remove leg #",
                min_value=1,
                max_value=max(len(st.session_state.legs), 1),
                step=1,
                value=1,
            )
            if st.button("Remove", use_container_width=True):
                idx = int(remove_idx) - 1
                if 0 <= idx < len(st.session_state.legs):
                    st.session_state.legs.pop(idx)
                    st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # Chart settings (collapsible, collapsed by default)
    # -----------------------------------------------------------------------

    _realized_spot_input: float | None = None

    with st.expander("Chart Settings", expanded=False):
        csa, csb = st.columns(2)
        auto_range = csa.checkbox(
            "Auto spot range", value=True,
            help="Automatically sets chart x-axis from the legs' strikes. Uncheck to set manually.",
        )
        n_points = csb.number_input(
            "Resolution (pts)", value=300, step=50, min_value=100, max_value=2000,
            help="Number of price points along the x-axis. 300 is fine for most strategies.",
        )
        csc, csd = st.columns(2)
        show_legs    = csc.checkbox("Show individual legs", value=True)
        use_realized = csd.checkbox("Mark realized spot at maturity")

        if not auto_range:
            default_lo, default_hi = _compute_auto_range(st.session_state.legs)
            lo_col, hi_col = st.columns(2)
            spot_lo = lo_col.number_input("Spot range — min", value=default_lo, step=1.0)
            spot_hi = hi_col.number_input("Spot range — max", value=default_hi, step=1.0)

        if use_realized:
            _realized_spot_input = st.number_input(
                "Actual spot price at expiry", value=100.0, step=0.5,
                help="Enter the observed underlying price on the expiry date to see your realized P&L.",
            )

    if auto_range:
        spot_lo, spot_hi = _compute_auto_range(st.session_state.legs)

    realized_spot: float | None = _realized_spot_input

    spot_range = np.linspace(float(spot_lo), float(spot_hi), int(n_points))

    # -----------------------------------------------------------------------
    # Payoff diagram
    # -----------------------------------------------------------------------

    st.markdown('<div class="section-header">Payoff Diagram</div>', unsafe_allow_html=True)

    if not st.session_state.legs:
        st.info("Add at least one leg above to see the payoff diagram.")
    else:
        strategy = Strategy(st.session_state.strategy_name)
        fetched_ticker_for_save = ""

        for L in st.session_state.legs:
            leg_type = L["type"]
            pos    = L["pos"]
            K      = float(L["K"])
            prem   = float(L.get("prem", 0.0))
            qty    = int(L["qty"])
            exp    = datetime.strptime(L["expiry"], "%Y-%m-%d").date()
            ticker = L.get("ticker", "")
            if ticker:
                fetched_ticker_for_save = ticker

            if leg_type in ("stock (underlying)", "stock"):
                lbl = f"{'Long' if pos == 'long' else 'Short'} {ticker+' ' if ticker else ''}Stock @ {K:.2f}"
                strategy.add_leg(StockPosition(K, pos, qty, label=lbl))
            else:
                pos_s  = "L" if pos == "long" else "S"
                typ_s  = "C" if leg_type == "call" else "P"
                qty_s  = f"x{qty} " if qty > 1 else ""
                tick_s = f"{ticker} " if ticker else ""
                label  = f"{pos_s} {qty_s}{tick_s}{typ_s} K={K:.0f}"
                strategy.add_leg(Option(leg_type, pos, K, prem, exp, qty, label=label))

        # -- Summary metrics --
        summary = strategy.summary(spot_range)
        net = summary["net_premium"]
        be  = summary["breakeven_points"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Net Premium", f"{'Credit' if net >= 0 else 'Debit'} {abs(net):.2f}")
        m2.metric("Max Profit",  f"{summary['max_profit']:.2f}")
        m3.metric("Max Loss",    f"{summary['max_loss']:.2f}")
        m4.metric("Breakeven(s)", ", ".join(f"{b:.2f}" for b in be) if be else "None")

        # -- Budget check --
        if budget > 0:
            net_cost = abs(net) if net < 0 else 0.0
            if net_cost == 0.0:
                st.success(
                    f"This is a net credit strategy (+{abs(net):.2f} received) — no budget consumed."
                )
            elif net_cost <= budget:
                remaining = budget - net_cost
                st.success(
                    f"Within budget — net debit {net_cost:.2f} vs budget {budget:.0f} "
                    f"({remaining:.2f} remaining)."
                )
            else:
                overage = net_cost - budget
                st.warning(
                    f"Over budget — net debit {net_cost:.2f} exceeds budget {budget:.0f} "
                    f"by {overage:.2f}."
                )

        # -- Target price P&L --
        _tp = float(target_price) if target_price > 0 else None
        if _tp is not None:
            tpnl  = strategy.realized_payoff(_tp)
            sign  = "+" if tpnl >= 0 else ""
            color = "#22c55e" if tpnl >= 0 else "#ef4444"
            st.markdown(
                f"**P&L at target {_tp:.2f}:** "
                f"<span style='color:{color}; font-size:1.3em; font-weight:bold'>"
                f"{sign}{tpnl:.4f}</span>",
                unsafe_allow_html=True,
            )

        if use_realized and realized_spot is not None:
            rpnl  = strategy.realized_payoff(float(realized_spot))
            sign  = "+" if rpnl >= 0 else ""
            color = "#22c55e" if rpnl >= 0 else "#ef4444"
            st.markdown(
                f"**Realised P&L at spot {realized_spot:.2f}:** "
                f"<span style='color:{color}; font-size:1.3em; font-weight:bold'>"
                f"{sign}{rpnl:.4f}</span>",
                unsafe_allow_html=True,
            )

        # -- Interactive Plotly chart --
        fig = plot_payoff_plotly(
            strategy,
            spot_range,
            show_legs=show_legs,
            realized_spot=float(realized_spot) if use_realized and realized_spot is not None else None,
            target_price=_tp,
        )
        st.plotly_chart(fig, use_container_width=True)

        # -- Action buttons (Save + Export PDF) --
        save_col, export_col, _ = st.columns([1, 1, 2])
        with save_col:
            if st.button("Save Chart", type="primary", use_container_width=True):
                fname = save_chart(strategy, fig, spot_range, summary, fetched_ticker_for_save)
                st.success(f"Saved! ({fname})")

        with export_col:
            if st.button("Export PDF", use_container_width=True):
                with st.spinner("Generating report…"):
                    _ticker_for_export = fetched_ticker_for_save or strategy.name
                    _company = _get_company_name(_ticker_for_export) \
                        if _ticker_for_export else ""
                    _pdf_bytes, _tex_src, _fname_base = export_pdf(
                        fig           = fig,
                        ticker        = _ticker_for_export,
                        strategy_name = strategy.name,
                        legs          = st.session_state.legs,
                        summary       = summary,
                        strategy      = strategy,
                        spot_range    = spot_range,
                        company_name  = _company,
                    )
                _out_bytes = _pdf_bytes if _pdf_bytes is not None else _tex_src.encode("utf-8")
                _out_ext   = ".pdf" if _pdf_bytes is not None else ".tex"
                _out_fname = f"{_fname_base}{_out_ext}"
                # Write to ~/Downloads (Dock) and to saved_pdfs/
                _downloads_path = Path.home() / "Downloads" / _out_fname
                _downloads_path.write_bytes(_out_bytes)
                (SAVED_PDFS_DIR / _out_fname).write_bytes(_out_bytes)
                if _pdf_bytes is not None:
                    st.success(f"PDF saved to Downloads — {_out_fname}")
                else:
                    st.info(
                        f".tex saved to Downloads (reportlab not installed). "
                        f"Compile with: `pdflatex {_out_fname}`"
                    )

        # -- Raw payoff table --
        with st.expander("Raw payoff table"):
            step = max(1, len(spot_range) // 50)
            tbl_spots = spot_range[::step]
            tbl_pnl   = strategy.payoff_at_expiry(tbl_spots)
            df_tbl = pd.DataFrame({
                "Spot":     tbl_spots.round(2),
                "Total P&L": tbl_pnl.round(4),
            })
            for i, leg in enumerate(strategy.legs):
                df_tbl[f"Leg {i+1}: {leg.label}"] = leg.payoff_at_expiry(tbl_spots).round(4)
            st.dataframe(df_tbl, use_container_width=True)

    # -----------------------------------------------------------------------
    # Compare strategies
    # -----------------------------------------------------------------------

    with st.expander("Compare multiple presets"):
        st.write("Select presets to overlay on a single chart.")
        preset_keys = [k for k in PRESETS if k != "— none —"]
        chosen_presets = st.multiselect(
            "Presets to compare",
            preset_keys,
            default=["Bull Call Spread", "Bear Call Spread"],
        )

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

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------

    st.divider()
    st.caption(
        "Built with the option_payoff framework · "
        "Prices shown are per-share (x100 for one standard contract) · "
        "For educational purposes only — not financial advice."
    )
