"""
tabs.py
-------
Top-level TabPane content widgets for the Options Terminal:

* ``LiveDataTab``    – Strategy Builder (live chain + multi-leg builder).
* ``SavedTab``       – Saved-charts browser.
* ``BacktestingTab`` – Placeholder for future feature.
* ``HelpTab``        – Scrollable user guide.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Collapsible, DataTable, Input, Label, Select, Static,
)
from rich.text import Text as RichText

from tui.widgets import MetricsBar, ChartWidget


class LiveDataTab(Horizontal):
    """Strategy Builder — live market data + multi-leg builder."""

    DEFAULT_CSS = "LiveDataTab { height: 1fr; }"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="live-form"):
            yield Button("⟲ RESET ALL", id="live-reset-all", classes="reset-btn")

            with Collapsible(title="DATA SOURCE", collapsed=False, id="sec-data"):
                yield Label("Ticker")
                yield Input(placeholder="Ticker (AAPL, SPY…)", id="live-ticker")
                yield Button("Fetch Expiries", id="btn-fetch", variant="primary")
                yield Static("", id="live-spot-label")
                yield Label("Expiry")
                yield Select([], id="sel-expiry", allow_blank=True)
                yield Button("Load Chain", id="btn-chain")

            with Collapsible(title="STRATEGY SETUP", collapsed=False, id="sec-setup"):
                yield Label("Strategy Name")
                yield Input(placeholder="Strategy name…",
                            value="Custom Strategy", id="live-inp-name")
                yield Label("Target Price")
                yield Input(placeholder="Target Price (e.g. 155.00)", id="live-target")
                yield Label("Budget")
                yield Input(placeholder="Max Budget (e.g. 500.00)", id="live-budget")
                yield Label("Price Type")
                yield Select([("Bid", "bid"), ("Mid", "mid"), ("Ask", "ask")],
                             value="mid", id="live-price-src", allow_blank=False)
                yield Label("Option Type")
                with Horizontal(classes="toggle-row"):
                    yield Button("CALL", id="tgl-opt-call",
                                 classes="toggle-btn -selected")
                    yield Button("PUT",  id="tgl-opt-put",  classes="toggle-btn")
                yield Label("Direction")
                with Horizontal(classes="toggle-row"):
                    yield Button("LONG",  id="tgl-pos-long",
                                 classes="toggle-btn -selected")
                    yield Button("SHORT", id="tgl-pos-short", classes="toggle-btn")
                yield Label("Contracts")
                yield Input(placeholder="Quantity", value="1", id="live-qty")
                yield Label("Strike")
                yield Static("", id="live-strike-label")
                yield Select([], id="sel-strike", allow_blank=True)

            with Collapsible(title="LEGS", collapsed=False, id="sec-legs"):
                yield Button("Add Live Leg", id="btn-live-add", variant="primary")
                yield Static("", id="live-status")
                yield DataTable(id="live-legs-table", cursor_type="row")
                with Horizontal(id="live-legs-actions"):
                    yield Button("Clear All",  id="live-clear-btn",
                                 classes="danger-btn")
                    yield Button("Remove Leg", id="live-remove-btn")

        with Vertical(id="live-right-panel"):
            # ── Option chain (upper section) ─────────────────────────────
            with Vertical(id="chain-panel"):
                yield Label("OPTION CHAIN", classes="section-label")
                yield Static(
                    "  IV=Implied Volatility · OI=Open Interest · "
                    "Vol=Volume Today · Δ=Delta",
                    id="chain-legend",
                    classes="chain-legend",
                )
                yield DataTable(id="chain-table", cursor_type="row")

            # ── Payoff diagram + metrics (lower section) ─────────────────
            yield MetricsBar(id="live-metrics-bar")
            yield Static("", id="live-target-info", classes="target-info")
            yield Static("", id="live-cost-info",   classes="cost-info")
            yield Static("", id="live-chart-hover-info", classes="hover-info")
            yield ChartWidget(id="live-chart-widget",
                              tooltip_id="#live-chart-hover-info")
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
  1. Go to the [bold #00E5FF]STRATEGY BUILDER[/] tab.
  2. Enter a ticker, press [bold]Fetch Expiries[/], pick an expiry, then [bold]Load Chain[/].
  3. Click an option-chain row to set the Strike, choose CALL/PUT and LONG/SHORT,
     then press [bold #00FF41]Add Live Leg[/]. The payoff chart updates instantly.
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

[bold #FF8C00]STRATEGY BUILDER TAB[/]  (live option chains from Yahoo Finance)
  ┌─ LEFT PANEL — collapsible sections ────────────────────────────────────┐
  │  [bold]DATA SOURCE[/]      Ticker · Fetch Expiries · Expiry · Load Chain         │
  │  [bold]STRATEGY SETUP[/]   Strategy Name · Target Price · Budget · Price Type    │
  │                     Option Type [CALL/PUT] · Direction [LONG/SHORT]    │
  │                     Contracts · Strike                                 │
  │  [bold]LEGS[/]             Add Live Leg · legs table · Clear All / Remove Leg    │
  └───────────────────────────────────────────────────────────────────────┘
  ┌─ RIGHT PANEL ─────────────────────────────────────────────────────────┐
  │  [bold #00E5FF]Option Chain[/]  Strike · Bid · Mid · Ask · IV · OI · Vol · Δ          │
  │    The ATM strike row is highlighted in [bold #FFE000]amber[/].                          │
  │    Click any row to auto-fill the [bold]Strike[/] field in Strategy Setup.    │
  │                                                                       │
  │  [bold #00E5FF]Metrics bar[/]  NET PREMIUM · MAX PROFIT · MAX LOSS · BREAKEVEN(S)   │
  │  [bold #00E5FF]Payoff chart[/]  Profit (green) / Loss (red) zones, breakeven labels │
  │    and a cyan vertical marker at the current spot price.              │
  │                                                                       │
  │  [bold]Save[/]        — serialises strategy to saved_charts/ (JSON).          │
  │  [bold]Export PDF[/]  — generates a PDF report via ReportLab and saves        │
  │                  to ~/Downloads/ and saved_pdfs/                      │
  └───────────────────────────────────────────────────────────────────────┘

[bold #FF8C00]MY STRATEGIES TAB[/]
  Lists all previously saved strategies (newest first).
  Click a row to view details (legs, metrics) in the right panel.
  [bold]Delete Selected[/] removes the file permanently.

[bold #FF8C00]METRICS GLOSSARY[/]
  [bold]Net Premium[/]   CR = net credit received. DR = net debit paid.
  [bold]Max Profit[/]    Best-case P&L across the full spot range.
  [bold]Max Loss[/]      Worst-case P&L — how much you can lose.
  [bold]Breakeven(s)[/]  Spot price(s) where total P&L = 0.
  All values are [bold]per contract[/] — one US equity option contract = 100 shares,
  so the dashboard already multiplies premium × quantity × 100 for you.

[bold #FF8C00]TIPS[/]
  • Press [bold #FFE000]Ctrl+R[/] after resizing the window to redraw the chart at the new size.
  • The [bold]Target Price[/] input adds a cyan marker on the chart so you can
    instantly see your expected P&L at your price target.
  • PDF export uses ReportLab (installed automatically with pip install reportlab).
    If not installed, a LaTeX .tex file is exported instead.
  • Live data requires an internet connection and uses Yahoo Finance (yfinance).

[dim]─────────────────────────────────────────────────────────────────────────[/]
[dim]OPTIONS TERMINAL  ·  python -m tui  ·  press Q to quit[/]
"""


class HelpTab(VerticalScroll):
    """Scrollable user guide panel."""

    DEFAULT_CSS = "HelpTab { height: 1fr; background: #000000; padding: 1 2; }"

    def compose(self) -> ComposeResult:
        yield Static(_HELP_TEXT, markup=True, id="help-content")
