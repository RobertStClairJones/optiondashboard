"""
tui.py
------
Bloomberg-style terminal dashboard for option payoff analysis.
Run with: python tui.py

Imports from:
  core/engine.py      – Option, StockPosition, Strategy
  core/market_data.py – get_spot_price, get_available_expiries, get_options_chain
  utils/export_pdf.py – export_pdf
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Textual ─────────────────────────────────────────────────────────────────
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Button, DataTable, Footer, Header, Input,
    Label, Rule, Select, Static, TabbedContent, TabPane,
)
from textual import on, work
from rich.text import Text as RichText

# ── Project files (imported directly, never rewritten) ───────────────────────
from core import Option, StockPosition, Strategy
from utils.export_pdf import export_pdf

# ── Paths ────────────────────────────────────────────────────────────────────
SAVED_CHARTS_DIR = Path(__file__).parent / "data" / "saved_charts"
SAVED_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
SAVED_PDFS_DIR = Path(__file__).parent / "data" / "saved_pdfs"
SAVED_PDFS_DIR.mkdir(parents=True, exist_ok=True)

# ── Presets (mirrored from dashboard.py) ─────────────────────────────────────
PRESETS: dict[str, list[dict] | None] = {
    "— none —": None,
    "Long Call": [
        dict(type="call", pos="long",  K=100.0, prem=3.5, qty=1, expiry="2025-06-20"),
    ],
    "Short Put": [
        dict(type="put",  pos="short", K=95.0,  prem=2.8, qty=1, expiry="2025-06-20"),
    ],
    "Bull Call Spread": [
        dict(type="call", pos="long",  K=100.0, prem=3.5, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="short", K=110.0, prem=1.0, qty=1, expiry="2025-06-20"),
    ],
    "Bear Call Spread": [
        dict(type="call", pos="short", K=100.0, prem=3.5, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="long",  K=110.0, prem=1.0, qty=1, expiry="2025-06-20"),
    ],
    "Bull Put Spread": [
        dict(type="put",  pos="long",  K=90.0,  prem=1.5, qty=1, expiry="2025-06-20"),
        dict(type="put",  pos="short", K=100.0, prem=3.5, qty=1, expiry="2025-06-20"),
    ],
    "Long Straddle": [
        dict(type="call", pos="long", K=100.0, prem=3.5, qty=1, expiry="2025-06-20"),
        dict(type="put",  pos="long", K=100.0, prem=3.2, qty=1, expiry="2025-06-20"),
    ],
    "Long Strangle": [
        dict(type="put",  pos="long", K=95.0,  prem=2.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="long", K=105.0, prem=2.1, qty=1, expiry="2025-06-20"),
    ],
    "Long Call Butterfly": [
        dict(type="call", pos="long",  K=90.0,  prem=9.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="short", K=100.0, prem=4.5, qty=2, expiry="2025-06-20"),
        dict(type="call", pos="long",  K=110.0, prem=1.5, qty=1, expiry="2025-06-20"),
    ],
    "Iron Condor": [
        dict(type="put",  pos="long",  K=85.0,  prem=1.0, qty=1, expiry="2025-06-20"),
        dict(type="put",  pos="short", K=90.0,  prem=2.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="short", K=110.0, prem=2.0, qty=1, expiry="2025-06-20"),
        dict(type="call", pos="long",  K=115.0, prem=1.0, qty=1, expiry="2025-06-20"),
    ],
    "Covered Call": [
        dict(type="stock", pos="long",  K=100.0, prem=0.0, qty=1, expiry="2025-06-20"),
        dict(type="call",  pos="short", K=110.0, prem=2.5, qty=1, expiry="2025-06-20"),
    ],
    "Protective Put": [
        dict(type="stock", pos="long", K=100.0, prem=0.0, qty=1, expiry="2025-06-20"),
        dict(type="put",   pos="long", K=95.0,  prem=2.0, qty=1, expiry="2025-06-20"),
    ],
}

# ── Monetary formatter ────────────────────────────────────────────────────────

def _fmt_money(v: float, inf_str: str = "Unlimited") -> str:
    """Format a P&L value as $X,XXX.XX; handle ±inf gracefully."""
    if v == float("inf"):   return inf_str
    if v == float("-inf"):  return f"-{inf_str}"
    return f"${v:,.2f}"


# ── Analytical max-profit / max-loss ──────────────────────────────────────────

def _analytical_max_profit_loss(legs: list[dict]) -> tuple[float | None, float | None]:
    """
    Return (max_profit, max_loss) analytically for recognised strategy types.
    Values are per-share (matching core.py payoff_at_expiry convention).
    float('inf') / float('-inf') = unlimited.
    Returns (None, None) to signal caller should keep the numeric-scan result.
    """
    opts   = [L for L in legs if L.get("type") in ("call", "put")]
    stocks = [L for L in legs if L.get("type") in ("stock", "stock (underlying)")]

    def _nc() -> float:
        """Net credit of all legs (+ve = receive premium, -ve = pay)."""
        t = 0.0
        for L in legs:
            p, q = float(L.get("prem", 0.0)), int(L.get("qty", 1))
            t += p * q if L.get("pos") == "short" else -p * q
        return t

    # ── Single option ────────────────────────────────────────────────────────
    if len(legs) == 1 and len(opts) == 1:
        L = opts[0]
        K, p, q, pos, ot = (float(L["K"]), float(L.get("prem", 0.0)),
                             int(L.get("qty", 1)), L["pos"], L["type"])
        if   ot == "call" and pos == "long":  return float("inf"),       -p * q
        elif ot == "call" and pos == "short": return  p * q,              float("-inf")
        elif ot == "put"  and pos == "long":  return (K - p) * q,        -p * q
        elif ot == "put"  and pos == "short": return  p * q,             -(K - p) * q

    # ── 2-leg, options only ──────────────────────────────────────────────────
    if len(legs) == 2 and len(opts) == 2 and not stocks:
        c_legs = sorted([L for L in opts if L["type"] == "call"], key=lambda L: float(L["K"]))
        p_legs = sorted([L for L in opts if L["type"] == "put"],  key=lambda L: float(L["K"]))

        if len(c_legs) == 2:                               # both calls
            lo, hi = c_legs;  q = int(lo.get("qty", 1))
            if lo["pos"] == "long"  and hi["pos"] == "short":   # bull call spread
                nd = float(lo["prem"]) - float(hi["prem"])
                return (float(hi["K"]) - float(lo["K"]) - nd) * q, -nd * q
            if lo["pos"] == "short" and hi["pos"] == "long":    # bear call spread
                nc_v = float(lo["prem"]) - float(hi["prem"])
                return nc_v * q, -(float(hi["K"]) - float(lo["K"]) - nc_v) * q

        if len(p_legs) == 2:                               # both puts
            lo, hi = p_legs;  q = int(lo.get("qty", 1))
            if hi["pos"] == "long"  and lo["pos"] == "short":   # bear put spread
                nd = float(hi["prem"]) - float(lo["prem"])
                return (float(hi["K"]) - float(lo["K"]) - nd) * q, -nd * q
            if hi["pos"] == "short" and lo["pos"] == "long":    # bull put spread
                nc_v = float(hi["prem"]) - float(lo["prem"])
                return nc_v * q, -(float(hi["K"]) - float(lo["K"]) - nc_v) * q

        if len(c_legs) == 1 and len(p_legs) == 1:         # call + put
            c, p = c_legs[0], p_legs[0];  q = int(c.get("qty", 1))
            if c["pos"] == "long"  and p["pos"] == "long":   # long straddle/strangle
                return float("inf"), -(float(c["prem"]) + float(p["prem"])) * q
            if c["pos"] == "short" and p["pos"] == "short":  # short straddle/strangle
                return (float(c["prem"]) + float(p["prem"])) * q, float("-inf")

    # ── 3-leg butterfly ──────────────────────────────────────────────────────
    if len(legs) == 3 and len(opts) == 3 and not stocks:
        lo, mid, hi = sorted(opts, key=lambda L: float(L["K"]))
        q = int(lo.get("qty", 1))
        if (lo["pos"] == "long" and mid["pos"] == "short"
                and int(mid.get("qty", 1)) == 2 and hi["pos"] == "long"):
            nd = _nc()   # nd is negative (net debit)
            return (float(mid["K"]) - float(lo["K"]) + nd) * q, nd * q

    # ── 4-leg iron condor ────────────────────────────────────────────────────
    if len(legs) == 4 and len(opts) == 4 and not stocks:
        c_s = sorted([L for L in opts if L["type"] == "call"], key=lambda L: float(L["K"]))
        p_s = sorted([L for L in opts if L["type"] == "put"],  key=lambda L: float(L["K"]))
        if len(c_s) == 2 and len(p_s) == 2:
            p_lo, p_hi = p_s;  c_lo, c_hi = c_s
            if (p_lo["pos"] == "long"  and p_hi["pos"] == "short" and
                c_lo["pos"] == "short" and c_hi["pos"] == "long"):
                nc_v   = _nc()
                put_w  = float(p_hi["K"]) - float(p_lo["K"])
                call_w = float(c_hi["K"]) - float(c_lo["K"])
                return nc_v, -(max(put_w, call_w) - nc_v)

    # ── Covered call ─────────────────────────────────────────────────────────
    if len(legs) == 2 and len(opts) == 1 and len(stocks) == 1:
        c_l = [L for L in opts if L["type"] == "call" and L["pos"] == "short"]
        if c_l and stocks[0]["pos"] == "long":
            c, s = c_l[0], stocks[0]
            q = int(c.get("qty", 1))
            return ((float(c["K"]) - float(s["K"]) + float(c.get("prem", 0))) * q,
                    -(float(s["K"]) - float(c.get("prem", 0))) * q)

    # ── Protective put ───────────────────────────────────────────────────────
    if len(legs) == 2 and len(opts) == 1 and len(stocks) == 1:
        p_l = [L for L in opts if L["type"] == "put" and L["pos"] == "long"]
        if p_l and stocks[0]["pos"] == "long":
            p, s = p_l[0], stocks[0]
            q = int(p.get("qty", 1))
            return (float("inf"),
                    -(float(s["K"]) - float(p["K"]) + float(p.get("prem", 0))) * q)

    return None, None   # unrecognised — caller keeps numeric-scan result


def _is_multi_directional(legs: list[dict]) -> bool:
    """
    Return True if the strategy can profit from the underlying moving in either
    direction (straddle, strangle, butterfly, condor, iron condor).
    """
    opts = [L for L in legs if L.get("type") in ("call", "put")]
    long_calls = [L for L in opts if L["type"] == "call" and L["pos"] == "long"]
    long_puts  = [L for L in opts if L["type"] == "put"  and L["pos"] == "long"]
    # Long straddle / strangle: long call + long put
    if long_calls and long_puts:
        return True
    # Butterfly (3 options): long–short–long
    if len(opts) == 3:
        s = sorted(opts, key=lambda L: float(L["K"]))
        if s[0]["pos"] == "long" and s[1]["pos"] == "short" and s[2]["pos"] == "long":
            return True
    # Condor / iron condor (4 options)
    if len(opts) == 4:
        return True
    return False


# ── Bloomberg colour palette ──────────────────────────────────────────────────
C_AMBER  = "#FF8C00"
C_GREEN  = "#00FF41"
C_RED    = "#FF3333"
C_CYAN   = "#00E5FF"
C_YELLOW = "#FFE000"
C_DIM    = "#664400"


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions – call into existing project modules
# ═══════════════════════════════════════════════════════════════════════════════

def _build_strategy(name: str, legs: list[dict]) -> Strategy:
    """Construct a Strategy from legs list. Calls core.Option / StockPosition / Strategy."""
    s = Strategy(name)
    for L in legs:
        leg_type = L["type"]
        pos      = L["pos"]
        K        = float(L["K"])
        prem     = float(L.get("prem", 0.0))
        qty      = int(L["qty"])
        exp      = datetime.strptime(L["expiry"], "%Y-%m-%d").date()
        ticker   = L.get("ticker", "")
        if leg_type in ("stock", "stock (underlying)"):
            lbl = f"{'Long' if pos=='long' else 'Short'}{' '+ticker if ticker else ''} Stock @ {K:.2f}"
            s.add_leg(StockPosition(K, pos, qty, label=lbl))
        else:
            ps = "L" if pos == "long" else "S"
            ts = "C" if leg_type == "call" else "P"
            qs = f"x{qty} " if qty > 1 else ""
            tk = f"{ticker} " if ticker else ""
            s.add_leg(Option(leg_type, pos, K, prem, exp, qty,
                             label=f"{ps} {qs}{tk}{ts} K={K:.0f}"))
    return s


def _render_chart(strategy: Strategy, width: int, height: int,
                  hover_x: float | None = None) -> RichText:
    """
    Render ASCII payoff diagram.
    Calls strategy._auto_spot_range() and strategy.payoff_at_expiry() from core.py.
    Uses plotext for rendering; falls back to a plain-text note on error.
    Optional hover_x draws a cyan vertical crosshair at that spot price.
    """
    try:
        import plotext as plt

        chart_w = max(width - 4, 20)
        chart_h = max(height - 2, 8)

        plt.clf()
        plt.plotsize(chart_w, chart_h)
        plt.canvas_color("black")
        plt.axes_color("black")
        plt.ticks_color("orange")

        spot_range = strategy._auto_spot_range(n=min(chart_w * 3, 600))
        total_pnl  = strategy.payoff_at_expiry(spot_range)
        spots      = spot_range.tolist()
        pnls       = total_pnl.tolist()

        above = [v if v >= 0 else float("nan") for v in pnls]
        below = [v if v <  0 else float("nan") for v in pnls]

        # Draw order matters in plotext: last plot wins per pixel.
        # Orange baseline first, then green profit on top, red loss on top last.
        plt.plot(spots, pnls,  color="orange", label="P&L")
        if any(v == v for v in above):   # nan != nan
            plt.plot(spots, above, color="green", label="Profit")
        if any(v == v for v in below):
            plt.plot(spots, below, color="red",   label="Loss")

        plt.hline(0, color=239)
        for be in strategy.breakeven_points(spot_range):
            plt.vline(be, color="yellow")

        if hover_x is not None:
            plt.vline(hover_x, color="cyan")

        plt.xlabel("Spot Price at Expiry")
        plt.ylabel("P/L")
        plt.title(f" {strategy.name} ")

        return RichText.from_ansi(plt.build())

    except Exception as exc:
        return RichText(f" [chart error: {exc}]", style=C_AMBER)


def _load_saved_charts() -> list[dict]:
    charts = []
    for fp in sorted(SAVED_CHARTS_DIR.glob("*.json"), reverse=True):
        try:
            with open(fp) as f:
                data = json.load(f)
            data["_path"] = str(fp)
            charts.append(data)
        except Exception:
            pass
    return charts


def _save_chart_file(strategy: Strategy, legs: list[dict],
                     summary: dict, ticker: str) -> str:
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe  = "".join(c if c.isalnum() or c in "-_" else "_" for c in strategy.name)
    fname = f"{ts}_{safe}.json"
    arr   = strategy._auto_spot_range()
    data  = {
        "ticker": ticker,
        "strategy_name": strategy.name,
        "date_saved": datetime.now().isoformat(),
        "summary": summary,
        "legs": legs,
        "spot_range": [float(arr[0]), float(arr[-1]), len(arr)],
    }
    with open(SAVED_CHARTS_DIR / fname, "w") as f:
        json.dump(data, f, default=str)
    return fname


# ═══════════════════════════════════════════════════════════════════════════════
# Custom widgets
# ═══════════════════════════════════════════════════════════════════════════════

class MetricsBar(Horizontal):
    """Four metric cells: Net Premium · Max Profit · Max Loss · Breakevens."""

    DEFAULT_CSS = "MetricsBar { height: 5; }"

    def compose(self) -> ComposeResult:
        yield Static("", id="m-net",    classes="metric-box")
        yield Static("", id="m-profit", classes="metric-box")
        yield Static("", id="m-loss",   classes="metric-box")
        yield Static("", id="m-be",     classes="metric-box")

    def update_metrics(self, summary: dict) -> None:
        net   = summary.get("net_premium", 0.0)
        max_p = summary.get("max_profit",  0.0)
        max_l = summary.get("max_loss",    0.0)
        be    = summary.get("breakeven_points", [])

        def _cell(title: str, value: str, val_style: str) -> RichText:
            t = RichText()
            t.append(f" {title}\n", style=f"{C_DIM} bold")
            t.append(f" {value}",   style=f"{val_style} bold")
            return t

        self.query_one("#m-net").update(
            _cell("NET PREMIUM",
                  f"{'CR' if net >= 0 else 'DR'} ${abs(net):,.2f}",
                  C_GREEN if net >= 0 else C_RED))
        self.query_one("#m-profit").update(
            _cell("MAX PROFIT", _fmt_money(max_p),
                  C_GREEN if max_p > 0 else C_AMBER))
        self.query_one("#m-loss").update(
            _cell("MAX LOSS",   _fmt_money(max_l),
                  C_RED   if max_l < 0 else C_AMBER))
        self.query_one("#m-be").update(
            _cell("BREAKEVEN(S)",
                  "  ".join(f"${b:,.2f}" for b in be) if be else "—",
                  C_YELLOW))

    def reset(self) -> None:
        """Blank all metric cells to dashes (no active strategy)."""
        def _cell(title: str) -> RichText:
            t = RichText()
            t.append(f" {title}\n", style=f"{C_DIM} bold")
            t.append(" —",          style=f"{C_DIM} bold")
            return t
        for wid, title in (("#m-net",    "NET PREMIUM"),
                           ("#m-profit", "MAX PROFIT"),
                           ("#m-loss",   "MAX LOSS"),
                           ("#m-be",     "BREAKEVEN(S)")):
            try: self.query_one(wid).update(_cell(title))
            except Exception: pass


class ChartWidget(Static):
    """ASCII payoff diagram, rendered via plotext.

    Supports a mouse-hover crosshair: stores the most recent strategy and
    redraws with a vertical cyan line at the hovered spot price. Also
    updates a paired tooltip widget (set via `tooltip_id`) showing
    Spot / P/L / % Move values.
    """

    DEFAULT_CSS = "ChartWidget { height: 1fr; background: #000000; }"

    # Plotext leaves roughly these many cells for axis labels — approximate.
    _PAD_LEFT  = 7
    _PAD_RIGHT = 2
    _PAD_TOP   = 2
    _PAD_BOT   = 3

    def __init__(self, *args, tooltip_id: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._strategy: Strategy | None = None
        self._spot_min: float = 0.0
        self._spot_max: float = 0.0
        self._current_spot: float | None = None
        self._tooltip_id = tooltip_id
        self._last_hover_x: float | None = None

    def on_mount(self) -> None:
        self.update(RichText(" No strategy — add legs on the left.", style=C_AMBER))
        self._reset_tooltip()

    def _reset_tooltip(self) -> None:
        """Persistent placeholder (dashes) in the info bar when no hover is active."""
        if not self._tooltip_id:
            return
        tt = RichText()
        tt.append("  Hover over chart   ", style=f"{C_DIM} bold")
        tt.append("Spot: ", style=C_DIM);   tt.append("—",     style=C_CYAN)
        tt.append("   P/L: ", style=C_DIM); tt.append("—",     style=C_AMBER)
        tt.append("   Move: ", style=C_DIM);tt.append("—",     style=C_AMBER)
        try:
            self.app.query_one(self._tooltip_id, Static).update(tt)
        except Exception:
            pass

    def refresh_chart(self, strategy: Strategy,
                      current_spot: float | None = None) -> None:
        self._strategy = strategy
        arr = strategy._auto_spot_range()
        self._spot_min = float(arr[0])
        self._spot_max = float(arr[-1])
        self._current_spot = current_spot
        self._last_hover_x = None
        w = max(self.size.width  or 80, 20)
        h = max(self.size.height or 24,  8)
        self.update(_render_chart(strategy, w, h))
        self._reset_tooltip()

    def _mouse_x_to_spot(self, mx: int) -> float | None:
        w = max(self.size.width or 80, 20)
        chart_w = max(w - self._PAD_LEFT - self._PAD_RIGHT, 1)
        x_in = mx - self._PAD_LEFT
        if x_in < 0 or x_in > chart_w:
            return None
        if self._spot_max <= self._spot_min:
            return None
        frac = x_in / chart_w
        return self._spot_min + frac * (self._spot_max - self._spot_min)

    def on_mouse_move(self, event) -> None:
        if self._strategy is None:
            return
        spot = self._mouse_x_to_spot(event.x)
        if spot is None:
            return
        # Skip redraw if the mapped spot didn't change meaningfully.
        if (self._last_hover_x is not None
                and abs(spot - self._last_hover_x) < (self._spot_max - self._spot_min) / 400):
            return
        self._last_hover_x = spot
        try:
            pnl = float(self._strategy.realized_payoff(spot))
        except Exception:
            return

        tt = RichText()
        tt.append("  Hover  ", style=f"{C_DIM} bold")
        tt.append(f"Spot: ", style=C_DIM)
        tt.append(f"${spot:,.2f}", style=C_CYAN)
        tt.append("   P/L: ", style=C_DIM)
        tt.append(f"${pnl:,.2f}", style=C_GREEN if pnl >= 0 else C_RED)
        if self._current_spot and self._current_spot > 0:
            pct = ((spot - self._current_spot) / self._current_spot) * 100
            sign = "+" if pct >= 0 else ""
            tt.append("   Move: ", style=C_DIM)
            tt.append(f"{sign}{pct:.2f}%", style=C_AMBER)
        if self._tooltip_id:
            try:
                self.app.query_one(self._tooltip_id, Static).update(tt)
            except Exception:
                pass

        # Redraw chart with crosshair at hovered spot.
        w = max(self.size.width  or 80, 20)
        h = max(self.size.height or 24,  8)
        self.update(_render_chart(self._strategy, w, h, hover_x=spot))

    def on_leave(self, event=None) -> None:
        """Clear crosshair and reset tooltip to placeholder state."""
        if self._strategy is None:
            return
        self._last_hover_x = None
        self._reset_tooltip()
        w = max(self.size.width  or 80, 20)
        h = max(self.size.height or 24,  8)
        self.update(_render_chart(self._strategy, w, h))


# ── Panel Widget subclasses (each has its own compose so context managers work)

class DashboardTab(Horizontal):
    """Left builder + right chart panel."""

    DEFAULT_CSS = "DashboardTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="left-panel"):
            yield Button("⟲ RESET ALL", id="btn-reset-all", classes="reset-btn")
            yield Label("STRATEGY", classes="section-label")
            yield Input(placeholder="Strategy name…",
                        value="Custom Strategy", id="inp-name")
            yield Input(placeholder="Ticker (AAPL, SPY…)", id="inp-ticker")

            yield Label("PRESETS", classes="section-label")
            yield Select([(k, k) for k in PRESETS],
                         value="— none —", id="sel-preset")
            yield Button("Load Preset", id="btn-load-preset")

            yield Label("ADD LEG", classes="section-label")
            yield Select([("call","call"),("put","put"),("stock","stock")],
                         value="call", id="sel-type")
            yield Select([("long","long"),("short","short")],
                         value="long", id="sel-pos")
            yield Input(placeholder="Strike / Entry", value="100.00", id="inp-strike")
            yield Static("", id="move-required", classes="move-required-info")
            yield Input(placeholder="Premium",        value="3.50",   id="inp-prem")
            yield Input(placeholder="Quantity",       value="1",      id="inp-qty")
            yield Input(placeholder="Expiry YYYY-MM-DD",
                        value=(date.today() + timedelta(days=90)).strftime("%Y-%m-%d"),
                        id="inp-expiry")
            yield Button("+ Add Leg", id="btn-add", variant="primary")

            yield Label("LEGS", classes="section-label")
            yield DataTable(id="legs-table", cursor_type="row")
            with Horizontal(id="dash-legs-actions"):
                yield Button("Clear All",   id="clear-btn")
                yield Button("Remove Row",  id="btn-remove")

            with Vertical(id="target-section"):
                yield Label("TARGET PRICE (optional)", classes="section-label")
                yield Input(placeholder="0.00", value="", id="inp-target")
                yield Static("", id="target-pnl-info")

        with Vertical(id="right-panel"):
            yield MetricsBar(id="metrics-bar")
            yield Static("", id="target-info",  classes="target-info")
            yield Static("", id="status-msg")
            yield Static("", id="chart-hover-info", classes="hover-info")
            yield ChartWidget(id="chart-widget", tooltip_id="#chart-hover-info")
            with Horizontal(id="action-row"):
                yield Button("Save Chart", id="save-btn")
                yield Button("Export PDF", id="pdf-btn")
                yield Static("", id="action-status")


class LiveDataTab(Horizontal):
    """Live market data fetcher."""

    DEFAULT_CSS = "LiveDataTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="live-form"):
            yield Button("⟲ RESET ALL", id="live-reset-all", classes="reset-btn")
            yield Label("STRATEGY NAME", classes="section-label")
            yield Input(placeholder="Strategy name…",
                        value="Custom Strategy", id="live-inp-name")

            yield Label("LIVE MARKET DATA", classes="section-label")
            yield Input(placeholder="Ticker (AAPL, SPY…)", id="live-ticker")
            yield Button("Fetch Expiries", id="btn-fetch", variant="primary")
            yield Static("", id="live-spot-label")

            yield Label("TARGET PRICE", classes="section-label")
            yield Input(placeholder="Target Price (e.g. 155.00)", id="live-target")
            yield Label("BUDGET", classes="section-label")
            yield Input(placeholder="Max Budget (e.g. 500.00)", id="live-budget")

            yield Label("EXPIRY", classes="section-label")
            yield Select([], id="sel-expiry", allow_blank=True)
            yield Button("Load Chain", id="btn-chain")
            yield Rule()

            yield Label("ADD TO STRATEGY", classes="section-label")
            yield Label("OPTION TYPE", classes="section-label")
            yield Select([("call","call"),("put","put")],
                         value="call", id="live-opt-type")
            yield Label("DIRECTION", classes="section-label")
            yield Select([("long","long"),("short","short")],
                         value="long", id="live-opt-pos")
            yield Select([("mid","mid"),("bid","bid"),("ask","ask"),("lastPrice","lastPrice")],
                         value="mid", id="live-price-src")
            yield Input(placeholder="Quantity", value="1", id="live-qty")
            yield Static("", id="live-strike-label")
            yield Select([], id="sel-strike", allow_blank=True)
            yield Button("Add Live Leg", id="btn-live-add", variant="primary")
            yield Static("", id="live-status")

            yield Rule()
            yield Label("STRATEGY LEGS", classes="section-label")
            yield DataTable(id="live-legs-table", cursor_type="row")
            with Horizontal(id="live-legs-actions"):
                yield Button("Clear All", id="live-clear-btn", classes="danger-btn")
                yield Button("Remove Leg", id="live-remove-btn")

        with Vertical(id="live-right-panel"):
            # ── Option chain (upper section) ─────────────────────────────
            with Vertical(id="chain-panel"):
                yield Label("OPTION CHAIN", classes="section-label")
                yield DataTable(id="chain-table", cursor_type="row")

            # ── Payoff diagram + metrics (lower section) ─────────────────
            yield MetricsBar(id="live-metrics-bar")
            yield Static("", id="live-target-info", classes="target-info")
            yield Static("", id="live-cost-info",   classes="cost-info")
            yield Static("", id="live-chart-hover-info", classes="hover-info")
            yield ChartWidget(id="live-chart-widget", tooltip_id="#live-chart-hover-info")
            with Horizontal(id="live-action-row"):
                yield Button("Save", id="live-save-btn")
                yield Button("Export PDF", id="live-pdf-btn")
                yield Static("", id="live-action-status")


class SavedTab(Horizontal):
    """Saved charts browser."""

    DEFAULT_CSS = "SavedTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="saved-list"):
            yield Label("SAVED CHARTS", classes="section-label")
            yield DataTable(id="saved-table", cursor_type="row")
            yield Button("Delete Selected", id="btn-del-saved")
            yield Button("Download PDF", id="btn-saved-pdf")
            yield Label("(or press [P] on selected row)", classes="section-label")

        with Vertical(id="saved-detail"):
            yield Static("← Select a saved chart to view details",
                         id="saved-detail-text")
            yield Static("", id="saved-chart-hover-info", classes="hover-info")
            yield ChartWidget(id="saved-chart-widget",
                              tooltip_id="#saved-chart-hover-info")
            yield Static("", id="saved-pdf-status")


class BacktestingTab(Vertical):
    """Placeholder for future backtesting features."""

    DEFAULT_CSS = "BacktestingTab { height: 1fr; background: #000000; align: center middle; }"

    def compose(self) -> ComposeResult:
        yield Static(
            RichText.from_markup(
                "[#00E5FF bold]BACKTESTING[/]\n\n"
                "[#FF8C00]Coming Soon[/]\n\n"
                "[#664400]Historical payoff simulation, scenario analysis,\n"
                "and strategy performance over custom date ranges.[/]"
            ),
            id="backtesting-placeholder",
        )


_HELP_TEXT = """\
[bold #00E5FF]╔══════════════════════════════════════════════════════════════════════╗[/]
[bold #00E5FF]║              OPTIONS TERMINAL  ·  USER GUIDE                        ║[/]
[bold #00E5FF]╚══════════════════════════════════════════════════════════════════════╝[/]

[bold #FF8C00]QUICK START[/]
  1. Go to the [bold #00E5FF]DASHBOARD[/] tab.
  2. Pick a [bold]Preset[/] (e.g. "Iron Condor") and press [bold]Load Preset[/].
  3. The payoff chart and metrics update instantly.
  4. Press [bold #FFE000]Ctrl+S[/] to save, or [bold #FFE000]Ctrl+P[/] to export a PDF to ~/Downloads/.

[bold #FF8C00]NAVIGATION[/]
  Mouse click or [bold]Tab[/] / [bold]Shift+Tab[/] to move between widgets.
  [bold]Enter[/] activates buttons and opens Select dropdowns.
  [bold]Arrow keys[/] navigate DataTable rows and Select options.
  [bold]Esc[/] closes a Select dropdown without changing the value.

[bold #FF8C00]KEYBOARD SHORTCUTS[/]
  [bold #FFE000]?[/]        Open this Help tab
  [bold #FFE000]Q[/]        Quit the terminal
  [bold #FFE000]Ctrl+S[/]   Save current strategy to saved_charts/
  [bold #FFE000]Ctrl+P[/]   Export PDF report to ~/Downloads/
  [bold #FFE000]Ctrl+R[/]   Refresh / redraw the payoff chart
  [bold #FFE000]F5[/]       Refresh / redraw the payoff chart
  [bold #FFE000]Tab[/]      Move focus to next widget
  [bold #FFE000]Shift+Tab[/] Move focus to previous widget

[bold #FF8C00]DASHBOARD TAB[/]  (manual strategy builder)
  ┌─ LEFT PANEL ──────────────────────────────────────────────────────────┐
  │  [bold]Strategy name[/]  — label shown in charts and saved files.               │
  │  [bold]Ticker[/]         — used in PDF exports (cosmetic, not required).        │
  │  [bold]Presets[/]        — load a ready-made strategy in one click.             │
  │                                                                       │
  │  ADD LEG fields:                                                      │
  │    [bold]Type[/]    call / put / stock  (stock = equity position)              │
  │    [bold]Pos[/]     long (buy) or short (sell/write)                           │
  │    [bold]Strike[/]  option strike price or stock entry price                   │
  │    [bold]Premium[/] option cost per share (ignored for stock legs)             │
  │    [bold]Qty[/]     number of contracts / shares                               │
  │    [bold]Expiry[/]  YYYY-MM-DD format                                          │
  │    Press [bold #00FF41]+ Add Leg[/] to append the leg.                                   │
  │                                                                       │
  │  LEGS table — select a row then press [bold]Remove Row[/] to delete it.       │
  │  [bold]Clear All[/] removes every leg instantly.                               │
  │                                                                       │
  │  [bold]Target Price[/] — draws a vertical marker on the chart and shows       │
  │    the expected P&L at that spot price.                               │
  └───────────────────────────────────────────────────────────────────────┘
  ┌─ RIGHT PANEL ─────────────────────────────────────────────────────────┐
  │  [bold #00E5FF]Metrics bar[/]  NET PREMIUM · MAX PROFIT · MAX LOSS · BREAKEVEN(S)   │
  │    [#00FF41]Green[/] = credit/profit  [#FF3333]Red[/] = debit/loss  [#FFE000]Yellow[/] = breakeven        │
  │                                                                       │
  │  [bold #00E5FF]Payoff chart[/]  ASCII diagram rendered by plotext.                   │
  │    [#00FF41]Green fill[/]  = profit zone  [#FF3333]Red fill[/]  = loss zone                │
  │    [#FFE000]Yellow line[/] = breakeven(s)                                       │
  │                                                                       │
  │  [bold]Save Chart[/]  — serialises strategy to saved_charts/ (JSON).          │
  │  [bold]Export PDF[/]  — generates a PDF report via ReportLab and saves        │
  │    to ~/Downloads/ and saved_pdfs/                                    │
  └───────────────────────────────────────────────────────────────────────┘

[bold #FF8C00]LIVE DATA TAB[/]  (fetch real option chains from Yahoo Finance)
  1. Type a ticker (e.g. [bold]AAPL[/]) and press [bold #00FF41]Fetch Expiries[/].
     The live spot price is shown in green when fetched.
  2. Select an [bold]Expiry[/] date from the dropdown.
  3. Press [bold]Load Chain[/] — the option chain fills the right panel.
  4. Choose [bold]Option type[/] (call/put), [bold]Position[/], [bold]Price source[/] (mid/bid/ask).
  5. Pick a [bold]Strike[/] from the dropdown.
  6. Press [bold #00FF41]Add Live Leg[/] — the leg is added to your strategy.
  Switch back to [bold]DASHBOARD[/] to see the updated chart.

[bold #FF8C00]SAVED TAB[/]
  Lists all previously saved strategies (newest first).
  Click a row to view details (legs, metrics) in the right panel.
  [bold]Delete Selected[/] removes the file permanently.

[bold #FF8C00]AVAILABLE PRESETS[/]
  [#FF8C00]Long Call[/]           Buy a call — unlimited upside, limited loss.
  [#FF8C00]Short Put[/]           Sell a put — collect premium, bullish/neutral.
  [#FF8C00]Bull Call Spread[/]    Buy low-K call, sell high-K call. Capped profit/loss.
  [#FF8C00]Bear Call Spread[/]    Sell low-K call, buy high-K call. Net credit, bearish.
  [#FF8C00]Bull Put Spread[/]     Net credit spread. Profit if underlying stays above.
  [#FF8C00]Long Straddle[/]       Buy ATM call + put. Profit from big moves either way.
  [#FF8C00]Long Strangle[/]       Buy OTM call + OTM put. Cheaper straddle, wider BEs.
  [#FF8C00]Long Call Butterfly[/] 3-leg. Profit when underlying pins near middle strike.
  [#FF8C00]Iron Condor[/]         4-leg. Net credit; profit inside a price range.
  [#FF8C00]Covered Call[/]        Long stock + short call. Income; caps upside.
  [#FF8C00]Protective Put[/]      Long stock + long put. Insurance against downside.

[bold #FF8C00]METRICS GLOSSARY[/]
  [bold]Net Premium[/]   CR = net credit received. DR = net debit paid.
  [bold]Max Profit[/]    Best-case P&L across the full spot range.
  [bold]Max Loss[/]      Worst-case P&L — how much you can lose.
  [bold]Breakeven(s)[/]  Spot price(s) where total P&L = 0.
  All values are [bold]per share[/] — multiply by 100 for one standard contract.

[bold #FF8C00]TIPS[/]
  • Press [bold #FFE000]Ctrl+R[/] after resizing the window to redraw the chart at the new size.
  • The [bold]Target Price[/] input adds a cyan marker on the chart so you can
    instantly see your expected P&L at your price target.
  • PDF export uses ReportLab (installed automatically with pip install reportlab).
    If not installed, a LaTeX .tex file is exported instead.
  • Live data requires an internet connection and uses Yahoo Finance (yfinance).

[dim]─────────────────────────────────────────────────────────────────────────[/]
[dim]OPTIONS TERMINAL  ·  python tui.py  ·  press Q to quit[/]
"""


class HelpTab(VerticalScroll):
    """Scrollable user guide panel."""

    DEFAULT_CSS = "HelpTab { height: 1fr; background: #000000; padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Static(_HELP_TEXT, markup=True, id="help-content")


# ═══════════════════════════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════════════════════════

class OptionsTUI(App[None]):
    """Bloomberg-style options strategy terminal."""

    CSS_PATH  = "tui.tcss"
    TITLE     = "OPTIONS TERMINAL"
    SUB_TITLE = "payoff analysis · bloomberg style"

    BINDINGS = [
        Binding("q",      "quit",                "Quit"),
        Binding("ctrl+s", "action_save",         "Save"),
        Binding("ctrl+p", "action_pdf",          "PDF"),
        Binding("ctrl+r", "action_refresh_chart","Refresh"),
        Binding("ctrl+n", "new_window",          "New Window"),
        Binding("f5",     "action_refresh_chart","Refresh",   show=False),
        Binding("question_mark", "show_help",    "Help"),
    ]

    def __init__(self, ticker: str = "", session_name: str = "") -> None:
        super().__init__()
        self._cli_ticker       = ticker.strip().upper()
        self._cli_session_name = session_name.strip()
        self.target_price: float | None = None
        self.budget:       float | None = None

    # ── reactive state ──────────────────────────────────────────────────────
    legs: reactive[list[dict]] = reactive(list, always_update=True)

    # live-data state (managed imperatively)
    _live_spot: float | None = None
    _live_expiries: list[str] = []
    _live_calls  = None
    _live_puts   = None
    _live_expiry: str = ""
    _saved_cache: list[dict] = []

    # ── compose ─────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("LIVE DATA", id="tab-live"):
                yield LiveDataTab()
            with TabPane("MANUAL ENTRY", id="tab-dashboard"):
                yield DashboardTab()
            with TabPane("SAVED", id="tab-saved"):
                yield SavedTab()
            with TabPane("BACKTESTING", id="tab-backtesting"):
                yield BacktestingTab()
            with TabPane("? HELP", id="tab-help"):
                yield HelpTab()
        yield Footer()

    # ── on_mount ─────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        legs_tbl: DataTable = self.query_one("#legs-table")
        legs_tbl.add_columns("#", "Type", "Pos", "Strike", "Prem", "Qty", "Expiry")

        live_legs_tbl: DataTable = self.query_one("#live-legs-table")
        live_legs_tbl.add_columns("#", "Type", "Pos", "Strike", "Prem", "Qty", "Expiry")

        chain_tbl: DataTable = self.query_one("#chain-table")
        chain_tbl.add_columns("Strike", "Bid", "Mid", "Ask", "IV", "OI", "Vol")

        saved_tbl: DataTable = self.query_one("#saved-table")
        saved_tbl.add_columns("Strategy", "Ticker", "Date Saved")
        self._refresh_saved_table()

        # Target price section is hidden until a multi-directional strategy is loaded
        self.query_one("#target-section").display = False

        # Apply CLI arguments
        if self._cli_session_name:
            self.title = self._cli_session_name
        if self._cli_ticker:
            self.query_one("#inp-ticker", Input).value = self._cli_ticker
            self.query_one("#live-ticker", Input).value = self._cli_ticker

    # ── Legs helpers ─────────────────────────────────────────────────────────
    def _refresh_legs_table(self) -> None:
        for tbl_id in ("#legs-table", "#live-legs-table"):
            tbl: DataTable = self.query_one(tbl_id)
            tbl.clear()
            for i, L in enumerate(self.legs, 1):
                tbl.add_row(str(i), L["type"], L["pos"],
                            f"{float(L['K']):.2f}",
                            f"{float(L.get('prem',0)):.2f}",
                            str(L["qty"]), L["expiry"])

    def _rebuild_and_render(self) -> None:
        if not self.legs:
            for cw in self.query(ChartWidget):
                cw.update(RichText(" No legs — add at least one leg.", style=C_AMBER))
            for wid in ("#target-info", "#live-target-info"):
                try: self.query_one(wid, Static).update(RichText(""))
                except Exception: pass
            return
        name     = self.query_one("#inp-name", Input).value.strip() or "Strategy"
        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)
        if self._live_spot:
            summary["current_spot"] = self._live_spot

        # Override with analytical max-profit / max-loss where possible
        ana_p, ana_l = _analytical_max_profit_loss(self.legs)
        if ana_p is not None:
            summary["max_profit"] = ana_p
        if ana_l is not None:
            summary["max_loss"] = ana_l

        # Update Dashboard tab widgets
        self.query_one("#metrics-bar",     MetricsBar).update_metrics(summary)
        self.query_one("#chart-widget",    ChartWidget).refresh_chart(strategy, self._live_spot)

        # Update Live Data tab widgets (always in sync)
        self.query_one("#live-metrics-bar",  MetricsBar).update_metrics(summary)
        self.query_one("#live-chart-widget", ChartWidget).refresh_chart(strategy, self._live_spot)
        self._update_cost_info(summary)
        self._update_target_info(strategy)

        # Show/hide target-price section and update inline P&L display
        multi = _is_multi_directional(self.legs)
        try:
            self.query_one("#target-section").display = multi
        except Exception:
            pass
        self._update_move_required()
        if multi:
            self._update_target_pnl_info(strategy)

    def _update_cost_info(self, summary: dict) -> None:
        """Show net cost per contract (and budget) in the Live Data panel."""
        net    = summary.get("net_premium", 0.0)
        cost_c = net * 100  # per standard 100-share contract
        direction = "DR" if cost_c < 0 else "CR"
        t = RichText()
        if self.budget is not None:
            t.append(f"  Budget: ${self.budget:,.2f}  |  ", style=C_AMBER)
        t.append(f"Net Cost/contract: {direction} ${abs(cost_c):,.2f}", style=C_AMBER)
        self.query_one("#live-cost-info", Static).update(t)

    def _update_target_info(self, strategy: Strategy) -> None:
        """Compute and display Profit @ Target and Move Required."""
        if self.target_price is None:
            for wid in ("#target-info", "#live-target-info"):
                try: self.query_one(wid, Static).update(RichText(""))
                except Exception: pass
            return
        pnl  = strategy.realized_payoff(self.target_price)
        spot = self._live_spot or 0.0
        t = RichText()
        t.append(f"  Profit @ Target Price (${self.target_price:,.2f}): ", style=C_DIM)
        t.append(_fmt_money(pnl), style=C_GREEN if pnl >= 0 else C_RED)
        if spot > 0:
            pct  = ((self.target_price - spot) / spot) * 100
            sign = "+" if pct >= 0 else ""
            t.append("   Move Required: ", style=C_DIM)
            t.append(f"{sign}{pct:.2f}%", style=C_CYAN)
        for wid in ("#target-info", "#live-target-info"):
            try: self.query_one(wid, Static).update(t)
            except Exception: pass

    def _update_move_required(self) -> None:
        """Show distance from current spot to the strike entered in the Dashboard."""
        try:
            wid = self.query_one("#move-required", Static)
        except Exception:
            return
        try:
            strike_str = self.query_one("#inp-strike", Input).value.strip()
            if not strike_str:
                wid.update("")
                return
            strike = float(strike_str)
            spot   = self._live_spot
            if spot is None or spot <= 0:
                wid.update("")
                return
            dist      = strike - spot
            pct       = (dist / spot) * 100
            sign      = "+" if dist >= 0 else ""
            direction = "UP" if dist >= 0 else "DOWN"
            t = RichText()
            t.append(
                f"  Move required: {sign}${dist:,.2f} ({sign}{pct:.2f}% {direction})",
                style=C_CYAN if dist >= 0 else C_RED,
            )
            wid.update(t)
        except (ValueError, Exception):
            try:
                wid.update("")
            except Exception:
                pass

    def _update_target_pnl_info(self, strategy: Strategy) -> None:
        """For multi-directional strategies, show P&L at the target price below the input."""
        try:
            info = self.query_one("#target-pnl-info", Static)
        except Exception:
            return
        target_str = self.query_one("#inp-target", Input).value.strip()
        if not target_str:
            info.update("")
            return
        try:
            target = float(target_str)
        except ValueError:
            info.update("")
            return
        pnl  = strategy.realized_payoff(target)
        sign = "+" if pnl >= 0 else ""
        pnl_str   = f"{sign}{_fmt_money(pnl)}"
        pnl_style = C_GREEN if pnl >= 0 else C_RED
        t = RichText()
        t.append(f"  If UP to ${target:,.2f}: P&L = ", style=C_DIM)
        t.append(pnl_str, style=pnl_style)
        t.append("\n")
        t.append(f"  If DOWN to ${target:,.2f}: P&L = ", style=C_DIM)
        t.append(pnl_str, style=pnl_style)
        info.update(t)

    # ── Dashboard button handlers ─────────────────────────────────────────────
    @on(Button.Pressed, "#btn-load-preset")
    def handle_load_preset(self) -> None:
        key = self.query_one("#sel-preset", Select).value
        if key == Select.BLANK or key not in PRESETS or PRESETS[key] is None:
            self._set_status("Select a preset first.")
            return
        self.legs = [dict(L) for L in PRESETS[key]]
        self.query_one("#inp-name", Input).value = str(key)
        self._refresh_legs_table()
        self._rebuild_and_render()
        self._set_status(f"Loaded preset: {key}")

    @on(Button.Pressed, "#btn-add")
    def handle_add_leg(self) -> None:
        try:
            leg_type = str(self.query_one("#sel-type",  Select).value)
            pos      = str(self.query_one("#sel-pos",   Select).value)
            strike   = float(self.query_one("#inp-strike", Input).value)
            prem     = float(self.query_one("#inp-prem",   Input).value) \
                       if leg_type != "stock" else 0.0
            qty      = int(self.query_one("#inp-qty",   Input).value)
            expiry   = self.query_one("#inp-expiry",    Input).value.strip()
            datetime.strptime(expiry, "%Y-%m-%d")   # validate
        except ValueError as exc:
            self._set_status(f"Invalid input: {exc}")
            return
        self.legs = self.legs + [
            dict(type=leg_type, pos=pos, K=strike, prem=prem, qty=qty, expiry=expiry)
        ]
        self._refresh_legs_table()
        self._rebuild_and_render()
        self._set_status(f"Added {pos} {leg_type} K={strike:.2f}")

    @on(Button.Pressed, "#btn-reset-all")
    @on(Button.Pressed, "#live-reset-all")
    def handle_reset_all(self) -> None:
        self._reset_all()

    def _reset_all(self) -> None:
        """Wipe every input, select, chain, and piece of state back to defaults."""
        self.legs = []
        self._refresh_legs_table()

        # Dashboard inputs
        defaults_inputs = {
            "#inp-name":   "Custom Strategy",
            "#inp-ticker": "",
            "#inp-strike": "100.00",
            "#inp-prem":   "3.50",
            "#inp-qty":    "1",
            "#inp-expiry": (date.today() + timedelta(days=90)).strftime("%Y-%m-%d"),
            "#inp-target": "",
            # Live inputs
            "#live-inp-name": "Custom Strategy",
            "#live-ticker":   "",
            "#live-target":   "",
            "#live-budget":   "",
            "#live-qty":      "1",
        }
        for sel, val in defaults_inputs.items():
            try: self.query_one(sel, Input).value = val
            except Exception: pass

        # Selects with fixed option sets
        fixed_selects = {
            "#sel-preset":     "— none —",
            "#sel-type":       "call",
            "#sel-pos":        "long",
            "#live-opt-type":  "call",
            "#live-opt-pos":   "long",
            "#live-price-src": "mid",
        }
        for sel, val in fixed_selects.items():
            try: self.query_one(sel, Select).value = val
            except Exception: pass

        # Dynamic selects — clear options entirely
        for sel_id in ("#sel-expiry", "#sel-strike"):
            try: self.query_one(sel_id, Select).set_options([])
            except Exception: pass

        # Clear chain table
        try: self.query_one("#chain-table", DataTable).clear()
        except Exception: pass

        # Reset state
        self.target_price   = None
        self.budget         = None
        self._live_spot     = None
        self._live_expiries = []
        self._live_calls    = None
        self._live_puts     = None
        self._live_expiry   = ""

        # Clear status / info widgets
        for wid in ("#live-spot-label", "#live-strike-label", "#live-status",
                    "#live-cost-info",  "#target-info", "#live-target-info",
                    "#move-required",   "#target-pnl-info",
                    "#action-status",   "#live-action-status",
                    "#status-msg", "#chart-hover-info", "#live-chart-hover-info",
                    "#saved-chart-hover-info"):
            try: self.query_one(wid, Static).update(RichText(""))
            except Exception: pass

        # Reset metric bars back to dashes
        for mb_id in ("#metrics-bar", "#live-metrics-bar"):
            try: self.query_one(mb_id, MetricsBar).reset()
            except Exception: pass

        # Reset charts and hide the target-price section
        for cw in self.query(ChartWidget):
            cw._strategy = None
            cw.update(RichText(" No legs — add at least one leg.", style=C_AMBER))
            cw._reset_tooltip()
        try: self.query_one("#target-section").display = False
        except Exception: pass

        self._set_status("Reset complete — clean slate.")

    @on(Button.Pressed, "#clear-btn")
    def handle_clear(self) -> None:
        self.legs = []
        self._refresh_legs_table()
        self.query_one(ChartWidget).update(
            RichText(" No legs — add at least one leg.", style=C_AMBER))
        self._set_status("All legs cleared.")

    @on(Button.Pressed, "#btn-remove")
    def handle_remove(self) -> None:
        tbl: DataTable = self.query_one("#legs-table")
        row = tbl.cursor_row
        if 0 <= row < len(self.legs):
            removed = self.legs[row]
            self.legs = [L for i, L in enumerate(self.legs) if i != row]
            self._refresh_legs_table()
            self._rebuild_and_render()
            self._set_status(f"Removed leg {row+1}: {removed['type']} K={removed['K']}")
        else:
            self._set_status("Select a row in the legs table first.")

    @on(Button.Pressed, "#save-btn")
    def action_save(self) -> None:
        if not self.legs:
            self._set_action_status("No legs to save.", C_RED)
            return
        name     = self.query_one("#inp-name", Input).value.strip() or "Strategy"
        ticker   = self.query_one("#inp-ticker", Input).value.strip().upper()
        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)
        fname    = _save_chart_file(strategy, self.legs, summary, ticker)
        self._refresh_saved_table()
        self._set_action_status(f"Saved: {fname}", C_GREEN)

    @on(Button.Pressed, "#pdf-btn")
    def action_pdf(self) -> None:
        if not self.legs:
            self._set_action_status("No legs to export.", C_RED)
            return
        self._set_action_status("Generating PDF…", C_YELLOW)
        self._do_export_pdf()

    @work(thread=True)
    def _do_export_pdf(self) -> None:
        name     = self.query_one("#inp-name",   Input).value.strip() or "Strategy"
        ticker   = self.query_one("#inp-ticker", Input).value.strip().upper() or name
        target_s = self.query_one("#inp-target", Input).value.strip()
        target   = float(target_s) if target_s else self.target_price

        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)

        # Apply analytical override so PDF matches TUI metrics bar
        ana_p, ana_l = _analytical_max_profit_loss(self.legs)
        if ana_p is not None:
            summary["max_profit"] = ana_p
        if ana_l is not None:
            summary["max_loss"] = ana_l

        # Compute target analysis for PDF
        profit_at_target = None
        pct_move         = None
        if target is not None:
            try:
                profit_at_target = strategy.realized_payoff(target)
                spot = summary.get("current_spot")
                if spot and spot > 0:
                    pct_move = ((target - spot) / spot) * 100
            except Exception:
                pass

        # export_pdf imported from utils/export_pdf.py
        pdf_bytes, tex_src, fname_base = export_pdf(
            fig                = None,
            ticker             = ticker,
            strategy_name      = name,
            legs               = self.legs,
            summary            = summary,
            strategy           = strategy,
            spot_range         = spot_arr,
            target_price       = target,
            profit_at_target   = profit_at_target,
            pct_move_to_target = pct_move,
        )

        out_bytes = pdf_bytes if pdf_bytes is not None else tex_src.encode()
        out_ext   = ".pdf" if pdf_bytes is not None else ".tex"
        out_fname = f"{fname_base}{out_ext}"
        dl_path   = Path.home() / "Downloads" / out_fname
        dl_path.write_bytes(out_bytes)
        (SAVED_PDFS_DIR / out_fname).write_bytes(out_bytes)

        label = "PDF" if pdf_bytes else ".tex"
        self.app.call_from_thread(
            self._set_action_status,
            f"{label} → ~/Downloads/{out_fname}", C_GREEN,
        )

    @on(Button.Pressed, "#live-save-btn")
    def handle_live_save(self) -> None:
        if not self.legs:
            self._set_live_action_status("No legs to save.", C_RED)
            return
        name     = self.query_one("#live-inp-name", Input).value.strip() or "Strategy"
        ticker   = self.query_one("#live-ticker",   Input).value.strip().upper()
        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)
        if self._live_spot:
            summary["current_spot"] = self._live_spot
        fname = _save_chart_file(strategy, self.legs, summary, ticker)
        self._refresh_saved_table()
        self._set_live_action_status(f"Saved: {fname}", C_GREEN)

    @on(Button.Pressed, "#live-clear-btn")
    def handle_live_clear(self) -> None:
        self.legs = []
        self._refresh_legs_table()
        for cw in self.query(ChartWidget):
            cw.update(RichText(" No legs — add at least one leg.", style=C_AMBER))
        self.query_one("#live-cost-info", Static).update(RichText(""))
        self._set_live_status("All legs cleared.")

    @on(Button.Pressed, "#live-remove-btn")
    def handle_live_remove(self) -> None:
        tbl: DataTable = self.query_one("#live-legs-table")
        row = tbl.cursor_row
        if 0 <= row < len(self.legs):
            removed = self.legs[row]
            self.legs = [L for i, L in enumerate(self.legs) if i != row]
            self._refresh_legs_table()
            self._rebuild_and_render()
            self._set_live_status(
                f"Removed leg {row+1}: {removed['type']} K={removed['K']}")
        else:
            self._set_live_status("Select a row in the legs table first.")

    @on(Button.Pressed, "#live-pdf-btn")
    def handle_live_pdf(self) -> None:
        if not self.legs:
            self._set_live_action_status("No legs to export.", C_RED)
            return
        self._set_live_action_status("Generating PDF…", C_YELLOW)
        self._do_export_live_pdf()

    @work(thread=True)
    def _do_export_live_pdf(self) -> None:
        name   = self.query_one("#live-inp-name", Input).value.strip() or "Strategy"
        ticker = self.query_one("#live-ticker",   Input).value.strip().upper() or name
        target = self.target_price

        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)
        if self._live_spot:
            summary["current_spot"] = self._live_spot

        # Apply analytical override so PDF matches TUI metrics bar
        ana_p, ana_l = _analytical_max_profit_loss(self.legs)
        if ana_p is not None:
            summary["max_profit"] = ana_p
        if ana_l is not None:
            summary["max_loss"] = ana_l

        # Compute target analysis for PDF
        profit_at_target = None
        pct_move         = None
        if target is not None:
            try:
                profit_at_target = strategy.realized_payoff(target)
                spot = summary.get("current_spot")
                if spot and spot > 0:
                    pct_move = ((target - spot) / spot) * 100
            except Exception:
                pass

        pdf_bytes, tex_src, fname_base = export_pdf(
            fig                = None,
            ticker             = ticker,
            strategy_name      = name,
            legs               = self.legs,
            summary            = summary,
            strategy           = strategy,
            spot_range         = spot_arr,
            target_price       = target,
            profit_at_target   = profit_at_target,
            pct_move_to_target = pct_move,
        )

        out_bytes = pdf_bytes if pdf_bytes is not None else tex_src.encode()
        out_ext   = ".pdf" if pdf_bytes is not None else ".tex"
        out_fname = f"{fname_base}{out_ext}"
        dl_path   = Path.home() / "Downloads" / out_fname
        dl_path.write_bytes(out_bytes)
        (SAVED_PDFS_DIR / out_fname).write_bytes(out_bytes)

        label = "PDF" if pdf_bytes else ".tex"
        self.app.call_from_thread(
            self._set_live_action_status,
            f"{label} → ~/Downloads/{out_fname}", C_GREEN,
        )

    # ── Live data handlers ─────────────────────────────────────────────────
    @on(Button.Pressed, "#btn-fetch")
    def handle_fetch(self) -> None:
        ticker = self.query_one("#live-ticker", Input).value.strip().upper()
        if not ticker:
            self._set_live_status("Enter a ticker first.")
            return
        self._set_live_status(f"Fetching {ticker}…")
        self._fetch_expiries(ticker)

    @work(thread=True)
    def _fetch_expiries(self, ticker: str) -> None:
        try:
            from core.market_data import get_spot_price, get_available_expiries
            spot     = get_spot_price(ticker)
            expiries = get_available_expiries(ticker)
            self._live_spot     = spot
            self._live_expiries = expiries

            def _update() -> None:
                self.query_one("#live-spot-label", Static).update(
                    RichText(f" {ticker} spot: {spot:.2f}", style=C_GREEN))
                sel: Select = self.query_one("#sel-expiry")
                sel.set_options([(e, e) for e in expiries])
                sel.refresh()
                if expiries:
                    sel.value = expiries[0]
                    self._live_expiry = expiries[0]
                    self._set_live_status(f"Fetched {len(expiries)} expiries.")
                else:
                    self._set_live_status(f"No expiries found for {ticker}.")
                self._update_move_required()
            self.app.call_from_thread(_update)
        except Exception as exc:
            self.app.call_from_thread(self._set_live_status, f"Error: {exc}")

    @on(Button.Pressed, "#btn-chain")
    def handle_chain(self) -> None:
        sel = self.query_one("#sel-expiry", Select)
        if sel.value == Select.BLANK:
            self._set_live_status("Fetch expiries first.")
            return
        ticker = self.query_one("#live-ticker", Input).value.strip().upper()
        expiry = str(sel.value)
        self._live_expiry = expiry
        self._set_live_status(f"Loading {ticker} {expiry}…")
        self._fetch_chain(ticker, expiry)

    @work(thread=True)
    def _fetch_chain(self, ticker: str, expiry: str) -> None:
        try:
            from core.market_data import get_options_chain
            calls, puts = get_options_chain(ticker, expiry)
            self._live_calls = calls
            self._live_puts  = puts

            def _update() -> None:
                opt_type = str(self.query_one("#live-opt-type", Select).value)
                df = calls if opt_type == "call" else puts
                self._populate_chain_table(df)
                strikes = sorted(df["strike"].tolist())
                sel: Select = self.query_one("#sel-strike")
                sel.set_options([(f"{s:.2f}", s) for s in strikes])
                if strikes:
                    sel.value = strikes[len(strikes) // 2]
                self.query_one("#live-strike-label", Static).update(
                    RichText(f" {len(strikes)} strikes loaded.", style=C_AMBER))
                self._set_live_status("Chain loaded — pick a strike and add leg.")
            self.app.call_from_thread(_update)
        except Exception as exc:
            self.app.call_from_thread(self._set_live_status, f"Error: {exc}")

    def _populate_chain_table(self, df) -> None:
        tbl: DataTable = self.query_one("#chain-table")
        tbl.clear()
        cols = [c for c in ["strike","bid","mid","ask","impliedVolatility","openInterest","volume"]
                if c in df.columns]

        def _int(v) -> str:
            """Convert to int string; return '—' for NaN/None/non-numeric."""
            try:
                f = float(v)
                return str(int(f)) if f == f else "—"   # f != f  ⟹  NaN
            except (TypeError, ValueError):
                return "—"

        for _, row in df[cols].iterrows():
            tbl.add_row(
                f"{row['strike']:.2f}",
                f"{row.get('bid',0):.2f}",
                f"{row.get('mid',0):.2f}",
                f"{row.get('ask',0):.2f}",
                f"{row.get('impliedVolatility',0):.1%}" if "impliedVolatility" in row else "—",
                _int(row.get("openInterest", 0)),
                _int(row.get("volume", 0)),
            )

    @on(Input.Changed, "#live-target")
    def handle_live_target_changed(self, event: Input.Changed) -> None:
        try:
            self.target_price = float(event.value) if event.value.strip() else None
        except ValueError:
            self.target_price = None

    @on(Input.Changed, "#live-budget")
    def handle_live_budget_changed(self, event: Input.Changed) -> None:
        try:
            self.budget = float(event.value) if event.value.strip() else None
        except ValueError:
            self.budget = None

    @on(Input.Changed, "#inp-strike")
    def handle_strike_changed(self, _event: Input.Changed) -> None:
        self._update_move_required()

    @on(Input.Changed, "#inp-target")
    def handle_target_changed(self, event: Input.Changed) -> None:
        try:
            self.target_price = float(event.value) if event.value.strip() else None
        except ValueError:
            self.target_price = None
        if self.legs and _is_multi_directional(self.legs):
            try:
                name     = self.query_one("#inp-name", Input).value.strip() or "Strategy"
                strategy = _build_strategy(name, self.legs)
                self._update_target_pnl_info(strategy)
                self._update_target_info(strategy)
            except Exception:
                pass

    @on(Select.Changed, "#live-opt-type")
    def handle_chain_type(self, event: Select.Changed) -> None:
        if self._live_calls is None:
            return
        df = self._live_calls if event.value == "call" else self._live_puts
        if df is not None:
            self._populate_chain_table(df)
            strikes = sorted(df["strike"].tolist())
            sel: Select = self.query_one("#sel-strike")
            sel.set_options([(f"{s:.2f}", s) for s in strikes])

    @on(Button.Pressed, "#btn-live-add")
    def handle_live_add(self) -> None:
        ticker   = self.query_one("#live-ticker",   Input).value.strip().upper()
        opt_type = str(self.query_one("#live-opt-type",  Select).value)
        pos      = str(self.query_one("#live-opt-pos",   Select).value)
        src      = str(self.query_one("#live-price-src", Select).value)
        strike_v = self.query_one("#sel-strike", Select).value

        if strike_v == Select.BLANK or self._live_calls is None:
            self._set_live_status("Load a chain first.")
            return
        try:
            qty    = int(self.query_one("#live-qty", Input).value)
            strike = float(strike_v)
        except ValueError:
            self._set_live_status("Invalid quantity.")
            return

        df   = self._live_calls if opt_type == "call" else self._live_puts
        row  = df[df["strike"] == strike]
        prem = float(row[src].iloc[0]) if not row.empty else 0.0

        self.legs = self.legs + [
            dict(type=opt_type, pos=pos, K=strike, prem=prem, qty=qty,
                 expiry=self._live_expiry, ticker=ticker)
        ]
        self.query_one("#inp-ticker", Input).value = ticker
        # Sync live name to Dashboard so _rebuild_and_render uses it
        live_name = self.query_one("#live-inp-name", Input).value.strip()
        if live_name:
            self.query_one("#inp-name", Input).value = live_name
        self._refresh_legs_table()
        self._rebuild_and_render()
        self._set_live_status(f"Added {pos} {opt_type} K={strike:.2f} prem={prem:.2f} ({src})")

    # ── Saved charts ───────────────────────────────────────────────────────
    def _refresh_saved_table(self) -> None:
        self._saved_cache = _load_saved_charts()
        tbl: DataTable = self.query_one("#saved-table")
        tbl.clear()
        for c in self._saved_cache:
            dt = datetime.fromisoformat(c["date_saved"]).strftime("%d %b %Y %H:%M")
            tbl.add_row(c.get("strategy_name","?"), c.get("ticker") or "—", dt)

    @on(DataTable.RowSelected, "#saved-table")
    def handle_saved_row(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if idx >= len(self._saved_cache):
            return
        c = self._saved_cache[idx]
        s = c.get("summary", {})
        net = s.get("net_premium", 0)
        be  = s.get("breakeven_points", [])

        t = RichText()
        t.append(f"  {c.get('strategy_name','?')}", style=f"{C_CYAN} bold")
        t.append(f"  ·  {c.get('ticker') or '—'}\n\n", style=C_AMBER)
        t.append("  Saved:       ", style=C_DIM)
        t.append(f"{datetime.fromisoformat(c['date_saved']).strftime('%d %b %Y %H:%M')}\n", style=C_AMBER)
        def _sfmt(v) -> str:
            try:    return _fmt_money(float(v))
            except: return str(v)

        t.append("  Net Premium: ", style=C_DIM)
        t.append(f"{'CR' if net>=0 else 'DR'} ${abs(net):,.2f}\n",
                 style=C_GREEN if net >= 0 else C_RED)
        t.append("  Max Profit:  ", style=C_DIM)
        t.append(f"{_sfmt(s.get('max_profit', 0))}\n", style=C_GREEN)
        t.append("  Max Loss:    ", style=C_DIM)
        t.append(f"{_sfmt(s.get('max_loss', 0))}\n",   style=C_RED)
        t.append("  Breakevens:  ", style=C_DIM)
        t.append(f"{',  '.join(f'${b:,.2f}' for b in be) if be else '—'}\n", style=C_YELLOW)
        t.append("\n  Legs:\n", style=C_CYAN)
        for L in c.get("legs", []):
            t.append(
                f"    {L['pos']:5s} {L['type']:5s}  K={L['K']:.2f}"
                f"  prem={L.get('prem',0):.2f}  qty={L['qty']}  {L['expiry']}\n",
                style=C_AMBER)
        self.query_one("#saved-detail-text", Static).update(t)

        # Render the payoff chart for this saved strategy (with hover tooltip)
        legs = c.get("legs", [])
        if legs:
            try:
                strategy = _build_strategy(c.get("strategy_name", "Strategy"), legs)
                saved_spot = c.get("summary", {}).get("current_spot")
                self.query_one("#saved-chart-widget", ChartWidget).refresh_chart(
                    strategy, saved_spot)
            except Exception as exc:
                self.query_one("#saved-chart-widget", ChartWidget).update(
                    RichText(f" [chart error: {exc}]", style=C_RED))
        else:
            self.query_one("#saved-chart-widget", ChartWidget).update(
                RichText(" No legs in this saved strategy.", style=C_AMBER))

    @on(Button.Pressed, "#btn-saved-pdf")
    def handle_saved_pdf_button(self) -> None:
        tbl: DataTable = self.query_one("#saved-table")
        idx = tbl.cursor_row
        if not (0 <= idx < len(self._saved_cache)):
            self.query_one("#saved-pdf-status", Static).update(
                RichText(" Select a row first.", style=C_RED))
            return
        self.query_one("#saved-pdf-status", Static).update(
            RichText(" Generating PDF…", style=C_YELLOW))
        self._do_export_saved_pdf(idx)

    @on(Button.Pressed, "#btn-del-saved")
    def handle_delete_saved(self) -> None:
        tbl: DataTable = self.query_one("#saved-table")
        idx = tbl.cursor_row
        if 0 <= idx < len(self._saved_cache):
            entry    = self._saved_cache[idx]
            json_path = Path(entry["_path"])
            if json_path.exists():
                json_path.unlink()

            # Also delete any matching PDFs/tex in the project folder.
            # Filename pattern from utils.export_pdf: {TICKER}_{safe_name}_{date}.{pdf|tex}
            ticker    = (entry.get("ticker") or "STRATEGY").upper()
            safe_name = (entry.get("strategy_name") or "Strategy").replace(" ", "_").replace("/", "-")
            pattern   = f"{ticker}_{safe_name}_*"
            pdfs_removed = 0
            for ext in ("pdf", "tex"):
                for fp in SAVED_PDFS_DIR.glob(f"{pattern}.{ext}"):
                    try:
                        fp.unlink()
                        pdfs_removed += 1
                    except Exception:
                        pass

            self._refresh_saved_table()
            msg = " Deleted."
            if pdfs_removed:
                msg += f"  (also removed {pdfs_removed} PDF{'s' if pdfs_removed != 1 else ''} from saved_pdfs/)"
            self.query_one("#saved-detail-text", Static).update(
                RichText(msg, style=C_RED))
            # Clear the chart and hover info so the detail pane isn't stale.
            try:
                self.query_one("#saved-chart-widget", ChartWidget).update(
                    RichText(" Deleted.", style=C_RED))
                self.query_one("#saved-chart-hover-info", Static).update(RichText(""))
                self.query_one("#saved-pdf-status", Static).update(RichText(""))
            except Exception:
                pass

    def on_key(self, event) -> None:
        """Export PDF when P is pressed on the SAVED tab."""
        if event.key != "p":
            return
        try:
            active = self.query_one("#tabs", TabbedContent).active
        except Exception:
            return
        if active != "tab-saved":
            return
        tbl: DataTable = self.query_one("#saved-table")
        idx = tbl.cursor_row
        if not (0 <= idx < len(self._saved_cache)):
            self.query_one("#saved-pdf-status", Static).update(
                RichText(" Select a row first.", style=C_RED))
            return
        self.query_one("#saved-pdf-status", Static).update(
            RichText(" Generating PDF…", style=C_YELLOW))
        self._do_export_saved_pdf(idx)

    @work(thread=True)
    def _do_export_saved_pdf(self, idx: int) -> None:
        c    = self._saved_cache[idx]
        legs = c.get("legs", [])
        if not legs:
            self.app.call_from_thread(
                self.query_one("#saved-pdf-status", Static).update,
                RichText(" No legs in saved strategy.", style=C_RED),
            )
            return
        name   = c.get("strategy_name", "Strategy")
        ticker = c.get("ticker") or name

        strategy = _build_strategy(name, legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)

        ana_p, ana_l = _analytical_max_profit_loss(legs)
        if ana_p is not None:
            summary["max_profit"] = ana_p
        if ana_l is not None:
            summary["max_loss"] = ana_l

        pdf_bytes, tex_src, fname_base = export_pdf(
            fig                = None,
            ticker             = ticker,
            strategy_name      = name,
            legs               = legs,
            summary            = summary,
            strategy           = strategy,
            spot_range         = spot_arr,
            target_price       = None,
            profit_at_target   = None,
            pct_move_to_target = None,
        )

        out_bytes = pdf_bytes if pdf_bytes is not None else tex_src.encode()
        out_ext   = ".pdf"    if pdf_bytes is not None else ".tex"
        out_fname = f"{fname_base}{out_ext}"
        dl_path   = Path.home() / "Downloads" / out_fname
        dl_path.write_bytes(out_bytes)
        (SAVED_PDFS_DIR / out_fname).write_bytes(out_bytes)

        full_path = str(dl_path)
        label     = "PDF" if pdf_bytes else ".tex"
        self.app.call_from_thread(
            self.query_one("#saved-pdf-status", Static).update,
            RichText(f"  {label} → {full_path}", style=C_GREEN),
        )

    # ── Keybinding actions ──────────────────────────────────────────────────
    def action_refresh_chart(self) -> None:
        self._rebuild_and_render()

    def action_show_help(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-help"

    def action_new_window(self) -> None:
        self.spawn_new_window()

    def spawn_new_window(self) -> None:
        """Launch a fresh TUI instance in a new terminal window via launch.py."""
        launch_py = Path(__file__).parent / "launch.py"
        subprocess.Popen(
            [sys.executable, str(launch_py)],
            start_new_session=True,
        )

    # ── Status helpers ──────────────────────────────────────────────────────
    def _set_status(self, msg: str) -> None:
        self.query_one("#status-msg", Static).update(
            RichText(f" {msg}", style=C_AMBER) if msg else RichText(""))

    def _set_action_status(self, msg: str, style: str = C_AMBER) -> None:
        self.query_one("#action-status", Static).update(
            RichText(f"  {msg}", style=style))

    def _set_live_status(self, msg: str) -> None:
        self.query_one("#live-status", Static).update(
            RichText(f" {msg}", style=C_AMBER))

    def _set_live_action_status(self, msg: str, style: str = C_AMBER) -> None:
        self.query_one("#live-action-status", Static).update(
            RichText(f"  {msg}", style=style))


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OPTIONS TERMINAL — payoff analysis")
    parser.add_argument("--session-name", default="",
                        help="Set the window/app title (e.g. 'AAPL Iron Condor')")
    parser.add_argument("--ticker", default="",
                        help="Pre-populate the ticker input on startup")
    args = parser.parse_args()
    OptionsTUI(ticker=args.ticker, session_name=args.session_name).run()
