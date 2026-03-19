"""
visualization.py
----------------
Payoff chart functions for single and multiple strategies.
"""

from __future__ import annotations

from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import plotly.graph_objects as go

from core import Option, Strategy

# Colour palette (colourblind-friendly enough, dark background friendly)
_PALETTE = [
    "#3498db", "#9b59b6", "#f39c12", "#1abc9c",
    "#e67e22", "#e91e63", "#00bcd4", "#8bc34a",
]

_PROFIT_COLOR = "#2ecc71"
_LOSS_COLOR   = "#e74c3c"
_TOTAL_COLOR  = "#2c3e50"
_BE_COLOR     = "#e67e22"
_REALIZED_COLOR = "#8e44ad"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_style(preferred: str = "seaborn-v0_8-whitegrid") -> None:
    try:
        plt.style.use(preferred)
    except OSError:
        try:
            plt.style.use("seaborn-whitegrid")
        except OSError:
            plt.style.use("default")


def _shade_zones(ax, x, y) -> None:
    ax.fill_between(x, y, 0, where=(y >= 0), color=_PROFIT_COLOR, alpha=0.12)
    ax.fill_between(x, y, 0, where=(y <  0), color=_LOSS_COLOR,   alpha=0.12)


def _add_strike_lines(ax, strategy: Strategy, y_min: float, y_range: float) -> None:
    seen: set[float] = set()
    for leg in strategy.legs:
        if isinstance(leg, Option) and leg.strike not in seen:
            seen.add(leg.strike)
            ax.axvline(leg.strike, color="#95a5a6", lw=0.8, ls=":", alpha=0.65)
            ax.text(
                leg.strike,
                y_min - 0.08 * y_range,
                f"K={leg.strike:.0f}",
                ha="center", va="top",
                fontsize=7.5, color="#7f8c8d",
            )


def _add_breakevens(ax, breakevens: list[float], y_range: float) -> None:
    for be in breakevens:
        ax.axvline(be, color=_BE_COLOR, lw=1.2, ls="--", alpha=0.85)
        ax.plot(be, 0, "o", color=_BE_COLOR, ms=6, zorder=7)
        ax.text(
            be,
            0.05 * y_range,
            f"BE\n{be:.2f}",
            ha="center", va="bottom",
            fontsize=8, color=_BE_COLOR, fontweight="bold",
        )


def _annotate_extremes(ax, x, y, n_pts: int) -> None:
    max_i, min_i = int(np.argmax(y)), int(np.argmin(y))
    edge = {0, n_pts - 1}

    if max_i not in edge:
        ax.annotate(
            f"Max: {y[max_i]:.2f}",
            xy=(x[max_i], y[max_i]),
            xytext=(0, 14), textcoords="offset points",
            ha="center", fontsize=8.5, color="#27ae60", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#27ae60", lw=0.9),
        )

    if min_i not in edge:
        ax.annotate(
            f"Min: {y[min_i]:.2f}",
            xy=(x[min_i], y[min_i]),
            xytext=(0, -18), textcoords="offset points",
            ha="center", fontsize=8.5, color="#c0392b", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#c0392b", lw=0.9),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_payoff(
    strategy: Strategy,
    spot_range: Optional[np.ndarray] = None,
    *,
    show_legs: bool = True,
    realized_spot: Optional[float] = None,
    figsize: tuple[float, float] = (11, 6),
    title: Optional[str] = None,
    ax: Optional[plt.Axes] = None,
) -> tuple[plt.Figure, plt.Axes]:
    """
    Plot the payoff diagram for a *strategy*.

    Parameters
    ----------
    strategy      : Strategy object to visualise
    spot_range    : numpy array of underlying prices (auto if None)
    show_legs     : overlay individual leg payoffs as dashed lines
    realized_spot : if given, mark the actual spot at maturity and print P&L
    figsize       : figure size (ignored when *ax* is provided)
    title         : custom title (defaults to strategy name)
    ax            : existing Axes to draw into (creates new figure if None)

    Returns
    -------
    (fig, ax)
    """
    if spot_range is None:
        spot_range = strategy._auto_spot_range()
    total_pnl = strategy.payoff_at_expiry(spot_range)

    _try_style()

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.get_figure()

    y_min, y_max = float(np.min(total_pnl)), float(np.max(total_pnl))
    y_pad = max(abs(y_max - y_min) * 0.18, 0.5)

    # -- Profit / loss zones --
    _shade_zones(ax, spot_range, total_pnl)

    # -- Individual legs --
    if show_legs and len(strategy.legs) > 1:
        for i, leg in enumerate(strategy.legs):
            color = _PALETTE[i % len(_PALETTE)]
            ax.plot(
                spot_range,
                leg.payoff_at_expiry(spot_range),
                "--", lw=1.2, color=color, alpha=0.65, label=leg.label,
            )

    # -- Total P&L --
    ax.plot(spot_range, total_pnl, "-", lw=2.8, color=_TOTAL_COLOR,
            label="Total P&L", zorder=5)

    # -- Zero line --
    ax.axhline(0, color="#7f8c8d", lw=0.75, ls="--")

    # -- Strike markers --
    _add_strike_lines(ax, strategy, y_min, y_max - y_min or 1.0)

    # -- Breakeven markers --
    _add_breakevens(ax, strategy.breakeven_points(spot_range), y_max - y_min or 1.0)

    # -- Extreme profit / loss annotations --
    _annotate_extremes(ax, spot_range, total_pnl, len(spot_range))

    # -- Realized spot marker --
    if realized_spot is not None:
        pnl_at_realized = strategy.realized_payoff(realized_spot)
        ax.axvline(realized_spot, color=_REALIZED_COLOR, lw=1.8, ls="-.", alpha=0.9)
        ax.plot(realized_spot, pnl_at_realized, "*",
                color=_REALIZED_COLOR, ms=13, zorder=8, label=f"Realized S={realized_spot:.2f}")
        label_y = pnl_at_realized + (y_max - y_min) * 0.06
        sign = "+" if pnl_at_realized >= 0 else ""
        ax.annotate(
            f"Realised P&L\n{sign}{pnl_at_realized:.2f}",
            xy=(realized_spot, pnl_at_realized),
            xytext=(12, 0), textcoords="offset points",
            fontsize=9, color=_REALIZED_COLOR, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=_REALIZED_COLOR, lw=1.0),
        )

    # -- Axes labels & title --
    net = strategy.net_premium()
    net_str = f"Net {'Credit' if net >= 0 else 'Debit'}: {abs(net):.2f}"
    ax.set_title(
        f"{title or strategy.name}   ·   {net_str}",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax.set_xlabel("Underlying Price at Expiry", fontsize=11)
    ax.set_ylabel("Profit / Loss", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax.set_ylim(y_min - y_pad, y_max + y_pad)
    ax.legend(fontsize=8.5, loc="upper left", framealpha=0.88)
    ax.grid(True, alpha=0.25)

    plt.tight_layout()
    return fig, ax


def plot_multi_strategies(
    strategies: list[Strategy],
    spot_range: Optional[np.ndarray] = None,
    *,
    figsize: tuple[float, float] = (12, 7),
    realized_spot: Optional[float] = None,
) -> tuple[plt.Figure, plt.Axes]:
    """
    Overlay multiple strategy payoffs on a single chart for easy comparison.

    Parameters
    ----------
    strategies    : list of Strategy objects
    spot_range    : shared price axis (auto if None)
    realized_spot : mark actual spot at maturity (drawn for all strategies)
    """
    if spot_range is None:
        all_x: list[float] = []
        for s in strategies:
            sr = s._auto_spot_range()
            all_x += [float(sr[0]), float(sr[-1])]
        spot_range = np.linspace(min(all_x), max(all_x), 600)

    _try_style()
    fig, ax = plt.subplots(figsize=figsize)
    ax.axhline(0, color="#7f8c8d", lw=0.75, ls="--")

    for i, strat in enumerate(strategies):
        color = _PALETTE[i % len(_PALETTE)]
        pnl = strat.payoff_at_expiry(spot_range)
        ax.plot(spot_range, pnl, lw=2.2, color=color, label=strat.name)
        for be in strat.breakeven_points(spot_range):
            ax.axvline(be, color=color, lw=0.8, ls=":", alpha=0.5)

    if realized_spot is not None:
        ax.axvline(realized_spot, color=_REALIZED_COLOR, lw=1.8, ls="-.", alpha=0.9,
                   label=f"Realized S={realized_spot:.2f}")

    ax.set_xlabel("Underlying Price at Expiry", fontsize=11)
    ax.set_ylabel("Profit / Loss", fontsize=11)
    ax.set_title("Strategy Comparison", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left", framealpha=0.88)
    ax.grid(True, alpha=0.25)

    plt.tight_layout()
    return fig, ax


def plot_payoff_plotly(
    strategy: Strategy,
    spot_range: Optional[np.ndarray] = None,
    *,
    show_legs: bool = True,
    realized_spot: Optional[float] = None,
    target_price: Optional[float] = None,
    current_spot: Optional[float] = None,
    title: Optional[str] = None,
) -> go.Figure:
    """
    Interactive Plotly payoff diagram with hover tooltips.

    Hovering over the chart displays the underlying price and total P&L
    at that point, plus each individual leg's P&L when show_legs is True.
    """
    if spot_range is None:
        spot_range = strategy._auto_spot_range()

    total_pnl = strategy.payoff_at_expiry(spot_range)
    breakevens = strategy.breakeven_points(spot_range)

    y_min = float(np.min(total_pnl))
    y_max = float(np.max(total_pnl))
    y_range = y_max - y_min or 1.0

    fig = go.Figure()

    # --- Profit fill zone (above zero) ---
    fig.add_trace(go.Scatter(
        x=spot_range,
        y=np.clip(total_pnl, 0, None),
        fill="tozeroy",
        fillcolor="rgba(34,197,94,0.20)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # --- Loss fill zone (below zero) ---
    fig.add_trace(go.Scatter(
        x=spot_range,
        y=np.clip(total_pnl, None, 0),
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.20)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # --- Individual legs (dashed) ---
    if show_legs and len(strategy.legs) > 1:
        for i, leg in enumerate(strategy.legs):
            color = _PALETTE[i % len(_PALETTE)]
            leg_pnl = leg.payoff_at_expiry(spot_range)
            fig.add_trace(go.Scatter(
                x=spot_range,
                y=leg_pnl,
                mode="lines",
                line=dict(color=color, width=1.5, dash="dash"),
                opacity=0.70,
                name=leg.label,
                hoverinfo="skip",
            ))

    # --- Total P&L line ---
    if current_spot is not None and current_spot > 0:
        _move_pct = ((spot_range - current_spot) / current_spot) * 100
        _hover_tpl = (
            "Spot Price: <b>$%{x:.2f}</b><br>"
            "P&L: <b>$%{y:.2f}</b><br>"
            "Move Required: <b>%{customdata:+.2f}%</b>"
            "<extra></extra>"
        )
    else:
        _move_pct = None
        _hover_tpl = (
            "Spot Price: <b>$%{x:.2f}</b><br>"
            "P&L: <b>$%{y:.2f}</b>"
            "<extra></extra>"
        )
    fig.add_trace(go.Scatter(
        x=spot_range,
        y=total_pnl,
        mode="lines",
        line=dict(color="#e2e8f0", width=2.5),
        name="Total P&L",
        customdata=_move_pct,
        hovertemplate=_hover_tpl,
    ))

    # --- Zero line ---
    fig.add_hline(y=0, line=dict(color="#95a5a6", width=1.2, dash="dash"))

    # --- Strike vertical lines ---
    seen: set[float] = set()
    for leg in strategy.legs:
        if isinstance(leg, Option) and leg.strike not in seen:
            seen.add(leg.strike)
            fig.add_vline(
                x=leg.strike,
                line=dict(color="#bdc3c7", width=1, dash="dot"),
                annotation_text=f"K={leg.strike:.0f}",
                annotation_position="bottom right",
                annotation=dict(font=dict(size=13, color="#7f8c8d")),
            )

    # --- Breakeven markers ---
    for idx, be in enumerate(breakevens):
        fig.add_vline(
            x=be,
            line=dict(color="#e67e22", width=1.5, dash="dash"),
        )
        # Alternate label heights to prevent overlap when multiple breakevens are close
        label_y = y_max + y_range * (0.10 + 0.16 * (idx % 2))
        fig.add_annotation(
            x=be,
            y=0,
            ax=be,
            ay=label_y,
            axref="x",
            ayref="y",
            text=f"<b>BE {be:.2f}</b>",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.5,
            arrowcolor="#e67e22",
            font=dict(size=12, color="#f59e0b"),
            bgcolor="rgba(13,27,42,0.85)",
            bordercolor="#f59e0b",
            borderwidth=1,
        )

    # --- Realized spot marker ---
    if realized_spot is not None:
        pnl_realized = strategy.realized_payoff(realized_spot)
        sign = "+" if pnl_realized >= 0 else ""
        fig.add_vline(
            x=realized_spot,
            line=dict(color="#8e44ad", width=2, dash="dashdot"),
        )
        fig.add_trace(go.Scatter(
            x=[realized_spot],
            y=[pnl_realized],
            mode="markers+text",
            marker=dict(symbol="star", size=14, color="#8e44ad"),
            text=[f"{sign}{pnl_realized:.2f}"],
            textposition="top center",
            textfont=dict(color="#8e44ad", size=11),
            name=f"Realized S={realized_spot:.2f}",
            hoverinfo="skip",
        ))

    # --- Target price marker ---
    if target_price is not None and float(spot_range[0]) <= target_price <= float(spot_range[-1]):
        pnl_at_target = strategy.realized_payoff(target_price)
        sign = "+" if pnl_at_target >= 0 else ""
        fig.add_vline(
            x=target_price,
            line=dict(color="#22d3ee", width=2, dash="dash"),
        )
        fig.add_annotation(
            x=target_price,
            y=y_max + y_range * 0.06,
            text=f"<b>Target {target_price:.2f}</b>",
            showarrow=False,
            font=dict(size=12, color="#22d3ee"),
            bgcolor="rgba(13,27,42,0.85)",
            bordercolor="#22d3ee",
            borderwidth=1,
        )
        fig.add_trace(go.Scatter(
            x=[target_price],
            y=[pnl_at_target],
            mode="markers+text",
            marker=dict(symbol="diamond", size=12, color="#22d3ee"),
            text=[f"{sign}{pnl_at_target:.2f}"],
            textposition="top center",
            textfont=dict(color="#22d3ee", size=11),
            name=f"Target {target_price:.2f}",
            hoverinfo="skip",
        ))

    # --- Title & layout ---
    net = strategy.net_premium()
    net_str = f"Net {'Credit' if net >= 0 else 'Debit'}: {abs(net):.2f}"
    plot_title = f"{title or strategy.name}   ·   {net_str}"

    fig.update_layout(
        title=dict(
            text=plot_title,
            font=dict(size=18, family="sans-serif", color="#e2e8f0"),
            x=0.5,
            xanchor="center",
        ),
        xaxis=dict(
            title="Underlying Price at Expiry",
            title_font=dict(size=14, color="#94a3b8"),
            tickfont=dict(size=12, color="#94a3b8"),
            tickformat=".2f",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            zeroline=False,
            linecolor="rgba(255,255,255,0.1)",
        ),
        yaxis=dict(
            title="Profit / Loss",
            title_font=dict(size=14, color="#94a3b8"),
            tickfont=dict(size=12, color="#94a3b8"),
            tickformat=".2f",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            zeroline=False,
            linecolor="rgba(255,255,255,0.1)",
        ),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="#1e3a5f",
            bordercolor="#3b82f6",
            font=dict(size=13, color="#e2e8f0"),
        ),
        legend=dict(
            orientation="v",
            x=0.01,
            y=0.99,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(13,27,42,0.85)",
            bordercolor="rgba(59,130,246,0.3)",
            borderwidth=1,
            font=dict(size=12, color="#e2e8f0"),
        ),
        plot_bgcolor="#1a2744",
        paper_bgcolor="#1a2744",
        margin=dict(l=80, r=40, t=80, b=70),
        height=520,
        font=dict(size=13, color="#e2e8f0"),
    )

    return fig


def plot_payoff_grid(
    strategies: list[Strategy],
    cols: int = 2,
    spot_range: Optional[np.ndarray] = None,
    figsize: Optional[tuple[float, float]] = None,
) -> tuple[plt.Figure, list[plt.Axes]]:
    """
    Draw each strategy in its own subplot arranged in a grid.

    Parameters
    ----------
    strategies : list of Strategy objects
    cols       : number of columns in the grid
    spot_range : shared x-axis (auto per strategy if None)
    figsize    : override automatic figure size
    """
    n = len(strategies)
    rows = (n + cols - 1) // cols
    if figsize is None:
        figsize = (cols * 6, rows * 4.5)

    _try_style()
    fig, axes = plt.subplots(rows, cols, figsize=figsize, squeeze=False)
    axes_flat = [axes[r][c] for r in range(rows) for c in range(cols)]

    for i, (strat, ax) in enumerate(zip(strategies, axes_flat)):
        sr = spot_range if spot_range is not None else strat._auto_spot_range()
        plot_payoff(strat, sr, ax=ax, show_legs=False)

    # Hide unused subplots
    for ax in axes_flat[n:]:
        ax.set_visible(False)

    plt.tight_layout()
    return fig, axes_flat[:n]
