"""
widgets.py
----------
Custom Textual widgets used across the Options Terminal.

Public widgets
--------------
* ``MetricsBar``      – four-cell stat bar (Net / Max P / Max L / Breakeven).
* ``ChartWidget``     – ASCII payoff diagram via plotext, with a mouse-hover
                        crosshair + tooltip.
* ``ToastContainer``  – bottom-right notification overlay.
* ``ConfirmModal``    – generic Yes/No modal dialog.

Module-level helper
-------------------
* ``_render_chart``   – core plotext rendering function consumed by
                        ``ChartWidget``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from textual import on
from rich.text import Text as RichText

from core import Option, Strategy
from tui.analytics import _fmt_money
from tui.constants import (
    C_AMBER, C_GREEN,
    C_BB_LABEL, C_BB_WHITE, C_BB_GREEN, C_BB_RED,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Chart rendering helper
# ═══════════════════════════════════════════════════════════════════════════════

def _render_chart(strategy: Strategy, width: int, height: int,
                  hover_x: float | None = None,
                  current_spot: float | None = None) -> RichText:
    """
    Render ASCII payoff diagram.
    Uses plotext for rendering; falls back to a plain-text note on error.
    Optional hover_x draws a cyan vertical crosshair at that spot price.
    Marks each leg, the current spot, and labels each breakeven price.
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

        # Higher-density sample = visually smoother polyline.
        spot_range = strategy._auto_spot_range(n=min(chart_w * 6, 1200))
        total_pnl  = strategy.payoff_at_expiry(spot_range)
        spots      = spot_range.tolist()
        pnls       = total_pnl.tolist()

        above = [v if v >= 0 else float("nan") for v in pnls]
        below = [v if v <  0 else float("nan") for v in pnls]

        # Per-leg payoff curves (thin amber dashes underneath the total).
        if len(strategy.legs) > 1:
            for leg in strategy.legs:
                try:
                    leg_pnl = leg.payoff_at_expiry(spot_range).tolist()
                    plt.plot(spots, leg_pnl, color="orange+",
                             marker="braille", label=getattr(leg, "label", "leg"))
                except Exception:
                    pass

        # Total P&L: the prominent line. Braille marker = highest density.
        plt.plot(spots, pnls, color="orange", marker="braille", label="P&L")
        if any(v == v for v in above):
            plt.plot(spots, above, color="green", marker="braille", label="Profit")
        if any(v == v for v in below):
            plt.plot(spots, below, color="red", marker="braille", label="Loss")

        plt.hline(0, color=239)
        for be in strategy.breakeven_points(spot_range):
            plt.vline(be, color="yellow")
            try:
                plt.text(f"BE ${be:.2f}", x=be, y=0,
                         color="yellow", background="black", alignment="center")
            except Exception:
                pass

        # Current spot — distinct cyan/white marker line.
        if current_spot is not None and current_spot > 0:
            plt.vline(current_spot, color="cyan")
            try:
                plt.text(f"Spot ${current_spot:.2f}",
                         x=current_spot, y=max(pnls),
                         color="cyan", background="black", alignment="center")
            except Exception:
                pass

        if hover_x is not None:
            plt.vline(hover_x, color="cyan+")

        plt.xlabel("Spot Price at Expiry")
        plt.ylabel("P/L")
        plt.title(f" {strategy.name} ")

        return RichText.from_ansi(plt.build())

    except Exception as exc:
        return RichText(f" [chart error: {exc}]", style=C_AMBER)


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

        def _cell(title: str, value: str, val_color: str) -> RichText:
            t = RichText()
            t.append(f" {title}\n", style=f"{C_BB_LABEL} bold")
            t.append(f" {value}",   style=f"{val_color} bold")
            return t

        # NET PREMIUM — DR prefix + amount share the same red/green per sign.
        net_color = C_BB_GREEN if net >= 0 else C_BB_RED
        net_str   = f"{'CR' if net >= 0 else 'DR'} ${abs(net):,.2f}"
        self.query_one("#m-net").update(_cell("NET PREMIUM", net_str, net_color))

        # MAX PROFIT is always green (covers "Unlimited" too).
        self.query_one("#m-profit").update(
            _cell("MAX PROFIT", _fmt_money(max_p), C_BB_GREEN))

        # MAX LOSS is always red.
        self.query_one("#m-loss").update(
            _cell("MAX LOSS", _fmt_money(max_l), C_BB_RED))

        # BREAKEVEN(S) is a neutral price → white.
        be_str = "  ".join(f"${b:,.2f}" for b in be) if be else "—"
        self.query_one("#m-be").update(
            _cell("BREAKEVEN(S)", be_str, C_BB_WHITE))

    def reset(self) -> None:
        """Blank all metric cells to dashes (no active strategy)."""
        def _cell(title: str) -> RichText:
            t = RichText()
            t.append(f" {title}\n", style=f"{C_BB_LABEL} bold")
            t.append(" —",          style=f"{C_BB_LABEL} bold")
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
        label_style = f"{C_BB_LABEL} bold"
        tt = RichText()
        tt.append("  Hover over chart   ", style=label_style)
        tt.append("Spot: ", style=label_style);   tt.append("—", style=label_style)
        tt.append("   P/L: ", style=label_style); tt.append("—", style=label_style)
        tt.append("   Move: ", style=label_style);tt.append("—", style=label_style)
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
        self.update(_render_chart(strategy, w, h, current_spot=current_spot))
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
        label_style = f"{C_BB_LABEL} bold"
        pnl_color   = C_BB_GREEN if pnl >= 0 else C_BB_RED
        tt.append("  Hover  ",       style=label_style)
        tt.append("Spot: ",          style=label_style)
        tt.append(f"${spot:,.2f}",   style=f"{C_BB_WHITE} bold")
        tt.append("   P/L: ",        style=label_style)
        tt.append(f"${pnl:,.2f}",    style=f"{pnl_color} bold")
        if self._current_spot and self._current_spot > 0:
            pct = ((spot - self._current_spot) / self._current_spot) * 100
            sign = "+" if pct >= 0 else ""
            move_color = C_BB_GREEN if pct >= 0 else C_BB_RED
            tt.append("   Move: ",   style=label_style)
            tt.append(f"{sign}{pct:.2f}%", style=f"{move_color} bold")
        if self._tooltip_id:
            try:
                self.app.query_one(self._tooltip_id, Static).update(tt)
            except Exception:
                pass

        # Redraw chart with crosshair at hovered spot.
        w = max(self.size.width  or 80, 20)
        h = max(self.size.height or 24,  8)
        self.update(_render_chart(self._strategy, w, h,
                                  hover_x=spot, current_spot=self._current_spot))

    def on_leave(self, event=None) -> None:
        """Clear crosshair and reset tooltip to placeholder state."""
        if self._strategy is None:
            return
        self._last_hover_x = None
        self._reset_tooltip()
        w = max(self.size.width  or 80, 20)
        h = max(self.size.height or 24,  8)
        self.update(_render_chart(self._strategy, w, h,
                                  current_spot=self._current_spot))


class ToastContainer(Static):
    """Bottom-right toast notification overlay. Shows a message for ~2.5s."""

    DEFAULT_CSS = ""

    def on_mount(self) -> None:
        self.display = False

    def show(self, msg: str, style: str = C_GREEN, duration: float = 2.5) -> None:
        t = RichText()
        t.append(f"  ✓  {msg}  ", style=f"{style} bold")
        self.update(t)
        self.display = True
        self.set_timer(duration, self._hide)

    def _hide(self) -> None:
        self.display = False
        self.update("")


class ConfirmModal(ModalScreen[bool]):
    """Generic Yes/No confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > #confirm-box {
        width: 56;
        height: 9;
        background: #0d0500;
        border: solid #FF4500;
        padding: 1 2;
    }
    ConfirmModal #confirm-msg {
        height: 3;
        content-align: center middle;
        color: #FF8C00;
        text-style: bold;
    }
    ConfirmModal #confirm-actions {
        height: 3;
        align: center middle;
    }
    ConfirmModal Button {
        margin: 0 2;
        min-width: 12;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self._message, id="confirm-msg")
            with Horizontal(id="confirm-actions"):
                yield Button("Confirm", id="confirm-yes", variant="primary")
                yield Button("Cancel", id="confirm-no")

    @on(Button.Pressed, "#confirm-yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def _no(self) -> None:
        self.dismiss(False)
