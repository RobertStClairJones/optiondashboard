"""
app.py
------
``OptionsTUI`` application shell — top-level event handlers, keybindings,
and helper functions that bridge the UI to ``core`` and ``utils``.

Imports from sibling modules:
  tui.widgets   – MetricsBar, ChartWidget, ToastContainer, ConfirmModal
  tui.tabs      – LiveDataTab, SavedTab, BacktestingTab, HelpTab
  tui.analytics – _fmt_money, _analytical_max_profit_loss
  tui.constants – colour palette
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

# ── Textual ─────────────────────────────────────────────────────────────────
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Button, DataTable, Footer, Header, Input,
    Select, Static, TabbedContent, TabPane,
)
from textual import on, work
from rich.text import Text as RichText

# ── Project files (imported directly, never rewritten) ───────────────────────
from core import Option, StockPosition, Strategy
from utils.export_pdf import export_pdf

# ── Sibling modules ──────────────────────────────────────────────────────────
from tui.analytics import _fmt_money, _analytical_max_profit_loss
from tui.constants import (
    C_AMBER, C_GREEN, C_RED, C_CYAN, C_YELLOW, C_DIM,
    C_BB_LABEL, C_BB_WHITE, C_BB_GREEN, C_BB_RED, C_BB_GOLD,
)
from tui.tabs import LiveDataTab, SavedTab, BacktestingTab, HelpTab
from tui.widgets import (
    ChartWidget, ConfirmModal, MetricsBar, ToastContainer,
)

# ── Paths ────────────────────────────────────────────────────────────────────
# tui/app.py → parent = tui/, parent.parent = project root
_PROJECT_ROOT    = Path(__file__).resolve().parent.parent
SAVED_CHARTS_DIR = _PROJECT_ROOT / "data" / "saved_charts"
SAVED_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
SAVED_PDFS_DIR   = _PROJECT_ROOT / "data" / "saved_pdfs"
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
# Main Application
# ═══════════════════════════════════════════════════════════════════════════════

class OptionsTUI(App[None]):
    """Bloomberg-style options strategy terminal."""

    # Resolved relative to this module (tui/app.py) → tui/styles.tcss
    CSS_PATH  = "styles.tcss"
    TITLE     = "OPTIONS TERMINAL"

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

    # toggle-button state (replaces former Select widgets)
    _opt_type: str = "call"   # "call" | "put"
    _opt_pos:  str = "long"   # "long" | "short"

    # ── compose ─────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("STRATEGY BUILDER", id="tab-live"):
                yield LiveDataTab()
            with TabPane("MY STRATEGIES", id="tab-saved"):
                yield SavedTab()
            with TabPane("BACKTESTING", id="tab-backtesting"):
                yield BacktestingTab()
            with TabPane("? HELP", id="tab-help"):
                yield HelpTab()
        yield ToastContainer(id="toast-container")
        yield Footer()

    # ── on_mount ─────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        live_legs_tbl: DataTable = self.query_one("#live-legs-table")
        live_legs_tbl.add_columns("#", "Type", "Pos", "Strike", "Prem", "Qty", "Expiry")

        chain_tbl: DataTable = self.query_one("#chain-table")
        chain_tbl.add_columns("Strike", "Bid", "Mid", "Ask", "IV", "OI", "Vol", "Δ")
        # Header tooltips — shown by Textual on hover.
        try:
            chain_tbl.show_header = True
        except Exception:
            pass

        saved_tbl: DataTable = self.query_one("#saved-table")
        saved_tbl.add_columns("Strategy", "Ticker", "Date Saved")
        self._refresh_saved_table()

        # Tooltips on widgets that map to chain columns (best-effort hover hints).
        try:
            self.query_one("#chain-legend", Static).tooltip = (
                "IV: Implied Volatility — market's expectation of future price movement\n"
                "OI: Open Interest — total number of outstanding contracts\n"
                "Vol: Volume — number of contracts traded today\n"
                "Δ:  Delta — rate of change of option price vs spot price "
                "(0..1 calls, -1..0 puts)"
            )
        except Exception:
            pass

        # Apply CLI arguments
        if self._cli_session_name:
            self.title = self._cli_session_name
        if self._cli_ticker:
            self.query_one("#live-ticker", Input).value = self._cli_ticker

    # ── Legs helpers ─────────────────────────────────────────────────────────
    def _refresh_legs_table(self) -> None:
        try:
            tbl: DataTable = self.query_one("#live-legs-table", DataTable)
        except Exception:
            return
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
            for wid in ("#live-target-info",):
                try: self.query_one(wid, Static).update(RichText(""))
                except Exception: pass
            return
        name     = self.query_one("#live-inp-name", Input).value.strip() or "Strategy"
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

        # Update Strategy Builder widgets
        self.query_one("#live-metrics-bar",  MetricsBar).update_metrics(summary)
        self.query_one("#live-chart-widget", ChartWidget).refresh_chart(strategy, self._live_spot)
        self._update_cost_info(summary)
        self._update_target_info(strategy)

    def _update_cost_info(self, summary: dict) -> None:
        """Show net cost (and budget) in the Strategy Builder panel.

        Bloomberg palette: grey labels, white budget value, green/red net cost
        depending on credit/debit. ``net_premium`` is already per-contract.
        """
        net = summary.get("net_premium", 0.0)
        direction = "DR" if net < 0 else "CR"
        cost_color = C_BB_RED if net < 0 else C_BB_GREEN
        label_style = f"{C_BB_LABEL} bold"
        t = RichText()
        if self.budget is not None:
            t.append("  Budget: ", style=label_style)
            t.append(f"${self.budget:,.2f}", style=f"{C_BB_WHITE} bold")
            t.append("  |  ", style=label_style)
        t.append("Net Cost: ", style=label_style)
        t.append(f"{direction} ${abs(net):,.2f}", style=f"{cost_color} bold")
        self.query_one("#live-cost-info", Static).update(t)

    def _update_target_info(self, strategy: Strategy) -> None:
        """Compute and display Profit @ Target and Move Required.

        Bloomberg palette: grey labels, the target P&L always rendered in
        gold so it stands out as the key metric, % move green/red on sign.
        """
        try:
            wid = self.query_one("#live-target-info", Static)
        except Exception:
            return
        if self.target_price is None:
            wid.update(RichText(""))
            return
        pnl  = strategy.realized_payoff(self.target_price)
        spot = self._live_spot or 0.0
        label_style = f"{C_BB_LABEL} bold"
        t = RichText()
        t.append(f"  Profit @ Target Price (${self.target_price:,.2f}): ",
                 style=label_style)
        t.append(_fmt_money(pnl), style=f"{C_BB_GOLD} bold")
        if spot > 0:
            pct  = ((self.target_price - spot) / spot) * 100
            sign = "+" if pct >= 0 else ""
            move_color = C_BB_GREEN if pct >= 0 else C_BB_RED
            t.append("   Move Required: ", style=label_style)
            t.append(f"{sign}{pct:.2f}%", style=f"{move_color} bold")
        wid.update(t)

    # ── Reset confirmation ───────────────────────────────────────────────────
    @on(Button.Pressed, "#live-reset-all")
    def handle_reset_all(self) -> None:
        def _on_close(confirmed: bool | None) -> None:
            if confirmed:
                self._reset_all()
        self.push_screen(
            ConfirmModal("Are you sure you want to reset everything?"),
            _on_close,
        )

    def _reset_all(self) -> None:
        """Wipe every input, select, chain, and piece of state back to defaults."""
        self.legs = []
        self._refresh_legs_table()

        defaults_inputs = {
            "#live-inp-name": "Custom Strategy",
            "#live-ticker":   "",
            "#live-target":   "",
            "#live-budget":   "",
            "#live-qty":      "1",
        }
        for sel, val in defaults_inputs.items():
            try: self.query_one(sel, Input).value = val
            except Exception: pass

        # Price-type Select
        try: self.query_one("#live-price-src", Select).value = "mid"
        except Exception: pass

        # Dynamic selects — clear options entirely
        for sel_id in ("#sel-expiry", "#sel-strike"):
            try: self.query_one(sel_id, Select).set_options([])
            except Exception: pass

        # Reset toggle button state
        self._opt_type = "call"
        self._opt_pos  = "long"
        self._sync_toggle_buttons()

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
                    "#live-cost-info",  "#live-target-info",
                    "#live-action-status",
                    "#live-chart-hover-info", "#saved-chart-hover-info"):
            try: self.query_one(wid, Static).update(RichText(""))
            except Exception: pass

        # Reset metric bar
        try: self.query_one("#live-metrics-bar", MetricsBar).reset()
        except Exception: pass

        # Reset charts
        for cw in self.query(ChartWidget):
            cw._strategy = None
            cw.update(RichText(" No legs — add at least one leg.", style=C_AMBER))
            cw._reset_tooltip()

        self._set_live_status("Reset complete — clean slate.")

    # ── Toggle buttons (CALL/PUT, LONG/SHORT) ────────────────────────────────
    # Use "-selected" rather than "-active": Textual already toggles "-active"
    # for the brief mouse-press state on Button, so any custom "-active" we set
    # gets clobbered on the next interaction.
    def _sync_toggle_buttons(self) -> None:
        pairs = (
            ("#tgl-opt-call", self._opt_type == "call"),
            ("#tgl-opt-put",  self._opt_type == "put"),
            ("#tgl-pos-long", self._opt_pos  == "long"),
            ("#tgl-pos-short",self._opt_pos  == "short"),
        )
        for sel, active in pairs:
            try:
                btn = self.query_one(sel, Button)
                if active:
                    btn.add_class("-selected")
                else:
                    btn.remove_class("-selected")
            except Exception:
                pass

    @on(Button.Pressed, "#tgl-opt-call")
    def _toggle_opt_call(self) -> None:
        self._opt_type = "call"
        self._sync_toggle_buttons()
        self._on_opt_type_changed()

    @on(Button.Pressed, "#tgl-opt-put")
    def _toggle_opt_put(self) -> None:
        self._opt_type = "put"
        self._sync_toggle_buttons()
        self._on_opt_type_changed()

    @on(Button.Pressed, "#tgl-pos-long")
    def _toggle_pos_long(self) -> None:
        self._opt_pos = "long"
        self._sync_toggle_buttons()

    @on(Button.Pressed, "#tgl-pos-short")
    def _toggle_pos_short(self) -> None:
        self._opt_pos = "short"
        self._sync_toggle_buttons()

    def _on_opt_type_changed(self) -> None:
        """Re-render chain table when CALL/PUT toggle flips."""
        if self._live_calls is None:
            return
        df = self._live_calls if self._opt_type == "call" else self._live_puts
        if df is not None:
            self._populate_chain_table(df)
            strikes = sorted(df["strike"].tolist())
            sel: Select = self.query_one("#sel-strike")
            sel.set_options([(f"{s:.2f}", s) for s in strikes])

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
        self._show_toast("Strategy saved!")

    # Backwards-compat alias for Ctrl+S binding
    def action_save(self) -> None:
        self.handle_live_save()

    def action_pdf(self) -> None:
        self.handle_live_pdf()

    @on(Button.Pressed, "#live-clear-btn")
    def handle_live_clear(self) -> None:
        self.legs = []
        self._refresh_legs_table()
        for cw in self.query(ChartWidget):
            cw.update(RichText(" No legs — add at least one leg.", style=C_AMBER))
        try:
            self.query_one("#live-cost-info", Static).update(RichText(""))
        except Exception:
            pass
        try:
            self.query_one("#live-metrics-bar", MetricsBar).reset()
        except Exception:
            pass
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
                # NOTE (refactor-spotted bug): _update_move_required() is not
                # defined on this class. Preserved as-is per refactor brief.
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
                df = calls if self._opt_type == "call" else puts
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

        def _int(v) -> str:
            """Convert to int string; return '—' for NaN/None/non-numeric."""
            try:
                f = float(v)
                return str(int(f)) if f == f else "—"
            except (TypeError, ValueError):
                return "—"

        def _delta(v) -> str:
            try:
                f = float(v)
                if f != f:
                    return "—"
                return f"{f:+.2f}"
            except (TypeError, ValueError):
                return "—"

        # Identify ATM strike (closest to current spot) so we can highlight it.
        atm_strike: float | None = None
        if self._live_spot and self._live_spot > 0:
            try:
                strikes = df["strike"].tolist()
                atm_strike = min(strikes, key=lambda s: abs(float(s) - self._live_spot))
            except Exception:
                atm_strike = None

        delta_col = "delta" if "delta" in df.columns else None

        for _, row in df.iterrows():
            strike = float(row["strike"])
            cells = [
                f"{strike:.2f}",
                f"{row.get('bid', 0):.2f}",
                f"{row.get('mid', 0):.2f}",
                f"{row.get('ask', 0):.2f}",
                (f"{row['impliedVolatility']:.1%}"
                 if "impliedVolatility" in row and row["impliedVolatility"] == row["impliedVolatility"]
                 else "—"),
                _int(row.get("openInterest", 0)),
                _int(row.get("volume", 0)),
                _delta(row[delta_col]) if delta_col else "—",
            ]

            is_atm = atm_strike is not None and abs(strike - float(atm_strike)) < 1e-9
            if is_atm:
                styled = [RichText(c, style=f"{C_YELLOW} bold") for c in cells]
                tbl.add_row(*styled, key=f"strike-{strike:.4f}")
            else:
                tbl.add_row(*cells, key=f"strike-{strike:.4f}")

    @on(Input.Changed, "#live-target")
    def handle_live_target_changed(self, event: Input.Changed) -> None:
        try:
            self.target_price = float(event.value) if event.value.strip() else None
        except ValueError:
            self.target_price = None
        if self.legs:
            try:
                name = self.query_one("#live-inp-name", Input).value.strip() or "Strategy"
                strategy = _build_strategy(name, self.legs)
                self._update_target_info(strategy)
            except Exception:
                pass

    @on(Input.Changed, "#live-budget")
    def handle_live_budget_changed(self, event: Input.Changed) -> None:
        try:
            self.budget = float(event.value) if event.value.strip() else None
        except ValueError:
            self.budget = None

    @on(DataTable.RowSelected, "#chain-table")
    def handle_chain_row_selected(self, event: DataTable.RowSelected) -> None:
        """Click a row to auto-fill the Strike select with that row's strike."""
        if self._live_calls is None:
            return
        df = self._live_calls if self._opt_type == "call" else self._live_puts
        if df is None:
            return
        idx = event.cursor_row
        strikes_in_order = df["strike"].tolist()
        if not (0 <= idx < len(strikes_in_order)):
            return
        chosen = float(strikes_in_order[idx])
        try:
            sel: Select = self.query_one("#sel-strike", Select)
            sel.value = chosen
            self._set_live_status(f"Strike set to {chosen:.2f} (from chain).")
        except Exception:
            pass

    @on(Button.Pressed, "#btn-live-add")
    def handle_live_add(self) -> None:
        ticker   = self.query_one("#live-ticker",   Input).value.strip().upper()
        opt_type = self._opt_type
        pos      = self._opt_pos
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
        # tui/app.py → parent.parent = project root, where launch.py lives
        launch_py = Path(__file__).resolve().parent.parent / "launch.py"
        subprocess.Popen(
            [sys.executable, str(launch_py)],
            start_new_session=True,
        )

    # ── Status helpers ──────────────────────────────────────────────────────
    def _set_live_status(self, msg: str) -> None:
        try:
            self.query_one("#live-status", Static).update(
                RichText(f" {msg}", style=C_AMBER))
        except Exception:
            pass

    def _set_live_action_status(self, msg: str, style: str = C_AMBER) -> None:
        try:
            self.query_one("#live-action-status", Static).update(
                RichText(f"  {msg}", style=style))
        except Exception:
            pass

    def _show_toast(self, msg: str, style: str = C_GREEN, duration: float = 2.5) -> None:
        try:
            self.query_one("#toast-container", ToastContainer).show(msg, style, duration)
        except Exception:
            pass
