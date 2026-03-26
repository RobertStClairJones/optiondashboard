"""
tui.py
------
Bloomberg-style terminal dashboard for option payoff analysis.
Replaces: streamlit run dashboard.py
Run with: python tui.py

Imports and calls functions directly from:
  core.py             – Option, StockPosition, Strategy
  market_data.py      – get_spot_price, get_available_expiries, get_options_chain
  utils/export_pdf.py – export_pdf
"""
from __future__ import annotations

import json
import os
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
SAVED_CHARTS_DIR = Path(__file__).parent / "saved_charts"
SAVED_CHARTS_DIR.mkdir(exist_ok=True)
SAVED_PDFS_DIR = Path(__file__).parent / "saved_pdfs"
SAVED_PDFS_DIR.mkdir(exist_ok=True)

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


def _render_chart(strategy: Strategy, width: int, height: int) -> RichText:
    """
    Render ASCII payoff diagram.
    Calls strategy._auto_spot_range() and strategy.payoff_at_expiry() from core.py.
    Uses plotext for rendering; falls back to a plain-text note on error.
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

        if any(v == v for v in above):   # nan != nan
            plt.plot(spots, above, color="green", label="Profit")
        if any(v == v for v in below):
            plt.plot(spots, below, color="red",   label="Loss")
        plt.plot(spots, pnls, color="orange", label="Total P&L")

        plt.hline(0, color=239)
        for be in strategy.breakeven_points(spot_range):
            plt.vline(be, color="yellow")

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
                  f"{'CR' if net >= 0 else 'DR'} {abs(net):.2f}",
                  C_GREEN if net >= 0 else C_RED))
        self.query_one("#m-profit").update(
            _cell("MAX PROFIT", f"{max_p:.2f}", C_GREEN if max_p > 0 else C_AMBER))
        self.query_one("#m-loss").update(
            _cell("MAX LOSS",   f"{max_l:.2f}", C_RED   if max_l < 0 else C_AMBER))
        self.query_one("#m-be").update(
            _cell("BREAKEVEN(S)",
                  "  ".join(f"{b:.2f}" for b in be) if be else "—",
                  C_YELLOW))


class ChartWidget(Static):
    """ASCII payoff diagram, rendered via plotext."""

    DEFAULT_CSS = "ChartWidget { height: 1fr; background: #000000; }"

    def on_mount(self) -> None:
        self.update(RichText(" No strategy — add legs on the left.", style=C_AMBER))

    def refresh_chart(self, strategy: Strategy) -> None:
        w = max(self.size.width  or 80, 20)
        h = max(self.size.height or 24,  8)
        self.update(_render_chart(strategy, w, h))


# ── Panel Widget subclasses (each has its own compose so context managers work)

class DashboardTab(Horizontal):
    """Left builder + right chart panel."""

    DEFAULT_CSS = "DashboardTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="left-panel"):
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
            yield Input(placeholder="Premium",        value="3.50",   id="inp-prem")
            yield Input(placeholder="Quantity",       value="1",      id="inp-qty")
            yield Input(placeholder="Expiry YYYY-MM-DD",
                        value=(date.today() + timedelta(days=90)).strftime("%Y-%m-%d"),
                        id="inp-expiry")
            yield Button("+ Add Leg", id="btn-add", variant="primary")

            yield Label("LEGS", classes="section-label")
            yield DataTable(id="legs-table", cursor_type="row")
            with Horizontal():
                yield Button("Clear All",   id="clear-btn")
                yield Button("Remove Row",  id="btn-remove")

            yield Label("TARGET PRICE (optional)", classes="section-label")
            yield Input(placeholder="0.00", value="", id="inp-target")

        with Vertical(id="right-panel"):
            yield MetricsBar(id="metrics-bar")
            yield Static("", id="status-msg")
            yield ChartWidget(id="chart-widget")
            with Horizontal(id="action-row"):
                yield Button("Save Chart", id="save-btn")
                yield Button("Export PDF", id="pdf-btn")
                yield Static("", id="action-status")


class LiveDataTab(Horizontal):
    """Live market data fetcher."""

    DEFAULT_CSS = "LiveDataTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="live-form"):
            yield Label("LIVE MARKET DATA", classes="section-label")
            yield Input(placeholder="Ticker (AAPL, SPY…)", id="live-ticker")
            yield Button("Fetch Expiries", id="btn-fetch", variant="primary")
            yield Static("", id="live-spot-label")

            yield Label("EXPIRY", classes="section-label")
            yield Select([], id="sel-expiry", allow_blank=True)
            yield Button("Load Chain", id="btn-chain")
            yield Rule()

            yield Label("ADD TO STRATEGY", classes="section-label")
            yield Select([("call","call"),("put","put")],
                         value="call", id="live-opt-type")
            yield Select([("long","long"),("short","short")],
                         value="long", id="live-opt-pos")
            yield Select([("mid","mid"),("bid","bid"),("ask","ask"),("lastPrice","lastPrice")],
                         value="mid", id="live-price-src")
            yield Input(placeholder="Quantity", value="1", id="live-qty")
            yield Static("", id="live-strike-label")
            yield Select([], id="sel-strike", allow_blank=True)
            yield Button("Add Live Leg", id="btn-live-add", variant="primary")
            yield Static("", id="live-status")

        with Vertical(id="chain-panel"):
            yield Label("OPTION CHAIN", classes="section-label")
            yield DataTable(id="chain-table", cursor_type="row")


class SavedTab(Horizontal):
    """Saved charts browser."""

    DEFAULT_CSS = "SavedTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="saved-list"):
            yield Label("SAVED CHARTS", classes="section-label")
            yield DataTable(id="saved-table", cursor_type="row")
            yield Button("Delete Selected", id="btn-del-saved")

        with VerticalScroll(id="saved-detail"):
            yield Static("← Select a saved chart to view details",
                         id="saved-detail-text")


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
        Binding("f5",     "action_refresh_chart","Refresh",   show=False),
        Binding("question_mark", "show_help",    "Help"),
    ]

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
            with TabPane("DASHBOARD", id="tab-dashboard"):
                yield DashboardTab()
            with TabPane("LIVE DATA", id="tab-live"):
                yield LiveDataTab()
            with TabPane("SAVED", id="tab-saved"):
                yield SavedTab()
            with TabPane("? HELP", id="tab-help"):
                yield HelpTab()
        yield Footer()

    # ── on_mount ─────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        legs_tbl: DataTable = self.query_one("#legs-table")
        legs_tbl.add_columns("#", "Type", "Pos", "Strike", "Prem", "Qty", "Expiry")

        chain_tbl: DataTable = self.query_one("#chain-table")
        chain_tbl.add_columns("Strike", "Bid", "Mid", "Ask", "IV", "OI", "Vol")

        saved_tbl: DataTable = self.query_one("#saved-table")
        saved_tbl.add_columns("Strategy", "Ticker", "Date Saved")
        self._refresh_saved_table()

    # ── Legs helpers ─────────────────────────────────────────────────────────
    def _refresh_legs_table(self) -> None:
        tbl: DataTable = self.query_one("#legs-table")
        tbl.clear()
        for i, L in enumerate(self.legs, 1):
            tbl.add_row(str(i), L["type"], L["pos"],
                        f"{float(L['K']):.2f}",
                        f"{float(L.get('prem',0)):.2f}",
                        str(L["qty"]), L["expiry"])

    def _rebuild_and_render(self) -> None:
        if not self.legs:
            self.query_one(ChartWidget).update(
                RichText(" No legs — add at least one leg.", style=C_AMBER))
            return
        name     = self.query_one("#inp-name", Input).value.strip() or "Strategy"
        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)
        if self._live_spot:
            summary["current_spot"] = self._live_spot
        self.query_one(MetricsBar).update_metrics(summary)
        self.query_one(ChartWidget).refresh_chart(strategy)

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
        target   = float(target_s) if target_s else None

        strategy = _build_strategy(name, self.legs)
        spot_arr = strategy._auto_spot_range()
        summary  = strategy.summary(spot_arr)

        # export_pdf imported from utils/export_pdf.py
        pdf_bytes, tex_src, fname_base = export_pdf(
            fig           = None,
            ticker        = ticker,
            strategy_name = name,
            legs          = self.legs,
            summary       = summary,
            strategy      = strategy,
            spot_range    = spot_arr,
            target_price  = target,
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
            from market_data import get_spot_price, get_available_expiries
            spot     = get_spot_price(ticker)
            expiries = get_available_expiries(ticker)
            self._live_spot     = spot
            self._live_expiries = expiries

            def _update() -> None:
                self.query_one("#live-spot-label", Static).update(
                    RichText(f" {ticker} spot: {spot:.2f}", style=C_GREEN))
                sel: Select = self.query_one("#sel-expiry")
                sel.set_options([(e, e) for e in expiries])
                if expiries:
                    sel.value = expiries[0]
                    self._live_expiry = expiries[0]
                self._set_live_status(f"Fetched {len(expiries)} expiries.")
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
            from market_data import get_options_chain
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
        for _, row in df[cols].iterrows():
            tbl.add_row(
                f"{row['strike']:.2f}",
                f"{row.get('bid',0):.2f}",
                f"{row.get('mid',0):.2f}",
                f"{row.get('ask',0):.2f}",
                f"{row.get('impliedVolatility',0):.1%}" if "impliedVolatility" in row else "—",
                str(int(row.get("openInterest", 0))),
                str(int(row.get("volume", 0))),
            )

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
        t.append("  Net Premium: ", style=C_DIM)
        t.append(f"{'CR' if net>=0 else 'DR'} {abs(net):.2f}\n",
                 style=C_GREEN if net >= 0 else C_RED)
        t.append("  Max Profit:  ", style=C_DIM)
        t.append(f"{s.get('max_profit',0):.2f}\n",  style=C_GREEN)
        t.append("  Max Loss:    ", style=C_DIM)
        t.append(f"{s.get('max_loss',0):.2f}\n",    style=C_RED)
        t.append("  Breakevens:  ", style=C_DIM)
        t.append(f"{',  '.join(f'{b:.2f}' for b in be) if be else '—'}\n", style=C_YELLOW)
        t.append("\n  Legs:\n", style=C_CYAN)
        for L in c.get("legs", []):
            t.append(
                f"    {L['pos']:5s} {L['type']:5s}  K={L['K']:.2f}"
                f"  prem={L.get('prem',0):.2f}  qty={L['qty']}  {L['expiry']}\n",
                style=C_AMBER)
        self.query_one("#saved-detail-text", Static).update(t)

    @on(Button.Pressed, "#btn-del-saved")
    def handle_delete_saved(self) -> None:
        tbl: DataTable = self.query_one("#saved-table")
        idx = tbl.cursor_row
        if 0 <= idx < len(self._saved_cache):
            path = Path(self._saved_cache[idx]["_path"])
            if path.exists():
                path.unlink()
            self._refresh_saved_table()
            self.query_one("#saved-detail-text", Static).update(
                RichText(" Deleted.", style=C_RED))

    # ── Keybinding actions ──────────────────────────────────────────────────
    def action_refresh_chart(self) -> None:
        self._rebuild_and_render()

    def action_show_help(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-help"

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


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    OptionsTUI().run()
