"""
export_pdf.py
-------------
Generates a professional PDF report for an options strategy using ReportLab
(pure-Python, no system dependencies).

Falls back to downloading a .tex file only if ReportLab is not installed.

Public API
----------
export_pdf(fig, ticker, strategy_name, legs, summary)
    -> (pdf_bytes | None, tex_source: str, filename_base: str)
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Add parent dir so visualization/core are importable when called from utils/
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "Built with the option_payoff framework. "
    "Prices shown are per-share (\u00d7100 for one standard contract). "
    "For educational purposes only \u2014 not financial advice."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usd(val: float) -> str:
    """Format a value as USD with 2 decimal places (e.g. $1,234.56)."""
    if val < 0:
        return f"-${abs(val):,.2f}"
    return f"${val:,.2f}"


def _fmt_metric(val: float, inf_str: str = "Unlimited") -> str:
    if val in (float("inf"), float("-inf")):
        return inf_str
    return _usd(val)


def _chart_png_matplotlib(strategy, spot_range, tmpdir: str) -> str | None:
    """Render a clean print-ready payoff chart via matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        import numpy as np
        from core import Option

        if spot_range is None:
            spot_range = strategy._auto_spot_range()

        total_pnl = strategy.payoff_at_expiry(spot_range)

        # ── Colours (print-friendly white background) ──
        C_PROFIT  = "#d1fae5"   # light green fill
        C_LOSS    = "#fee2e2"   # light red fill
        C_LINE    = "#0f172a"   # near-black payoff line
        C_ZERO    = "#94a3b8"   # zero reference
        C_STRIKE  = "#cbd5e1"   # strike dotted
        C_BE      = "#b45309"   # breakeven amber
        C_AXIS    = "#334155"
        C_GRID    = "#f1f5f9"
        PALETTE   = ["#2563eb","#7c3aed","#ea580c","#059669","#db2777"]

        fig, ax = plt.subplots(figsize=(12, 5.2))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        # Profit / loss fill zones
        ax.fill_between(spot_range, total_pnl, 0,
                        where=(total_pnl >= 0), color=C_PROFIT, alpha=0.8)
        ax.fill_between(spot_range, total_pnl, 0,
                        where=(total_pnl < 0),  color=C_LOSS,   alpha=0.8)

        # Individual leg curves
        if len(strategy.legs) > 1:
            for i, leg in enumerate(strategy.legs):
                ax.plot(spot_range, leg.payoff_at_expiry(spot_range),
                        color=PALETTE[i % len(PALETTE)],
                        linewidth=1.2, linestyle="--", alpha=0.7,
                        label=leg.label)

        # Total P&L
        ax.plot(spot_range, total_pnl, color=C_LINE, linewidth=2.2,
                label="Total P&L", zorder=5)

        # Zero line
        ax.axhline(0, color=C_ZERO, linewidth=1.0, linestyle="--", zorder=3)

        # Strike lines
        seen: set = set()
        for leg in strategy.legs:
            if isinstance(leg, Option) and leg.strike not in seen:
                seen.add(leg.strike)
                ax.axvline(leg.strike, color=C_STRIKE, linewidth=0.8,
                           linestyle=":", zorder=2)
                ax.text(leg.strike, ax.get_ylim()[0],
                        f"K={leg.strike:.0f}", fontsize=7.5,
                        color="#64748b", ha="center", va="bottom")

        # Breakevens
        for be in strategy.breakeven_points(spot_range):
            ax.axvline(be, color=C_BE, linewidth=1.3, linestyle="--", zorder=4)
            y_top = float(np.max(total_pnl))
            y_rng = y_top - float(np.min(total_pnl)) or 1.0
            ax.annotate(f"BE ${be:.2f}",
                        xy=(be, y_top + y_rng * 0.04),
                        ha="center", fontsize=8, color=C_BE,
                        fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                  ec=C_BE, lw=0.8))

        # Formatting
        ax.set_xlabel("Underlying Spot Price at Expiry", fontsize=10,
                      color=C_AXIS, labelpad=8)
        ax.set_ylabel("Profit / Loss (USD)", fontsize=10,
                      color=C_AXIS, labelpad=8)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda v, _: f"${v:,.0f}"))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda v, _: f"${v:,.0f}"))
        ax.tick_params(colors=C_AXIS, labelsize=8.5)
        for spine in ax.spines.values():
            spine.set_edgecolor("#e2e8f0")
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color=C_GRID, linewidth=0.7)
        ax.xaxis.grid(False)

        if len(strategy.legs) > 1:
            ax.legend(fontsize=8, framealpha=0.9, edgecolor="#e2e8f0",
                      loc="upper left")

        fig.tight_layout(pad=1.4)

        path = os.path.join(tmpdir, "chart.png")
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ReportLab PDF builder
# ---------------------------------------------------------------------------

def _build_reportlab_pdf(
    ticker: str,
    company_name: str,
    strategy_name: str,
    report_date: date,
    legs: list[dict],
    summary: dict,
    chart_png: str | None,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table,
        TableStyle,
    )

    W, H = A4  # 595 x 842 pt
    margin = 2.5 * cm
    content_w = W - 2 * margin

    # ---- Styles ----
    def _style(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=10, leading=14,
                        textColor=colors.HexColor("#1a1a2e"))
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    S = {
        "report_lbl":  _style("rl",  fontName="Helvetica", fontSize=8,
                               textColor=colors.HexColor("#94a3b8"),
                               spaceAfter=3),
        "strat":       _style("strat", fontName="Helvetica-Bold", fontSize=15,
                               textColor=colors.HexColor("#0f172a"), spaceAfter=4),
        "date":        _style("date",  fontSize=9,
                               textColor=colors.HexColor("#64748b")),
        "ticker_badge":_style("tb",  fontName="Helvetica-Bold", fontSize=26,
                               alignment=1, textColor=colors.white,
                               leading=30, spaceAfter=3),
        "company_name":_style("cn",  fontName="Helvetica", fontSize=8,
                               alignment=1, textColor=colors.HexColor("#94a3b8"),
                               leading=11),
        "section":     _style("section", fontName="Helvetica-Bold", fontSize=12,
                               spaceBefore=14, spaceAfter=5,
                               textColor=colors.HexColor("#0f172a")),
        "body":        _style("body"),
        "metric_lbl":  _style("ml",  fontName="Helvetica-Bold", fontSize=10),
        "metric_val":  _style("mv",  fontSize=10,
                               textColor=colors.HexColor("#1d4ed8")),
        "disclaimer":  _style("disc", fontName="Helvetica-Oblique", fontSize=8,
                               alignment=1, textColor=colors.HexColor("#94a3b8")),
    }

    # ---- Story ----
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )
    story = []

    # ---- Header: left = report info, right = ticker badge ----
    _NAVY = colors.HexColor("#0f172a")
    left_cell = [
        Paragraph("OPTIONS STRATEGY REPORT", S["report_lbl"]),
        Paragraph(strategy_name, S["strat"]),
        Paragraph(report_date.strftime("%B %d, %Y"), S["date"]),
    ]
    ticker_label = ticker.upper() if ticker else "N/A"
    right_cell = [Paragraph(ticker_label, S["ticker_badge"])]
    if company_name:
        right_cell.append(Paragraph(company_name, S["company_name"]))

    badge_w  = 4.2 * cm
    left_w   = content_w - badge_w - 0.4 * cm
    hdr_tbl  = Table(
        [[left_cell, right_cell]],
        colWidths=[left_w, badge_w],
    )
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (1, 0), (1,  0),  _NAVY),
        ("ROUNDEDCORNERS",(1, 0), (1,  0),  [8, 8, 8, 8]),
        ("TOPPADDING",    (1, 0), (1,  0),  16),
        ("BOTTOMPADDING", (1, 0), (1,  0),  16),
        ("LEFTPADDING",   (1, 0), (1,  0),  6),
        ("RIGHTPADDING",  (1, 0), (1,  0),  6),
        ("TOPPADDING",    (0, 0), (0,  0),  4),
        ("BOTTOMPADDING", (0, 0), (0,  0),  4),
        ("LEFTPADDING",   (0, 0), (0,  0),  0),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor("#cbd5e1")))
    story.append(Spacer(1, 14))

    # Strategy legs table
    story.append(Paragraph("Strategy Legs", S["section"]))
    hdr = [["Type", "Strike", "Expiry", "Position", "Premium"]]
    rows = []
    for L in legs:
        rows.append([
            str(L.get("type", "")).capitalize(),
            _usd(float(L.get("K", 0))),
            str(L.get("expiry", "")),
            str(L.get("pos", "")).capitalize(),
            _usd(float(L.get("prem", 0.0))),
        ])
    col_w = [2.8*cm, 2.4*cm, 3.2*cm, 2.6*cm, 2.6*cm]
    tbl = Table(hdr + rows, colWidths=col_w, hAlign="LEFT")
    row_bg = [colors.HexColor("#f8fafc"), colors.white]
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1,  0),  colors.HexColor("#1e293b")),
        ("TEXTCOLOR",     (0, 0), (-1,  0),  colors.white),
        ("FONTNAME",      (0, 0), (-1,  0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1),  9),
        ("FONTNAME",      (0, 1), (-1, -1),  "Helvetica"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),  row_bg),
        ("ALIGN",         (1, 0), (1, -1),   "RIGHT"),
        ("ALIGN",         (4, 0), (4, -1),   "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1),  5),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  5),
        ("LEFTPADDING",   (0, 0), (-1, -1),  7),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  7),
        ("LINEBELOW",     (0, 0), (-1,  0),  1,   colors.HexColor("#1e293b")),
        ("LINEBELOW",     (0,-1), (-1, -1),  0.5, colors.HexColor("#e2e8f0")),
        ("GRID",          (0, 0), (-1, -1),  0.3, colors.HexColor("#e2e8f0")),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # Payoff diagram
    story.append(Paragraph("Payoff Diagram", S["section"]))
    if chart_png:
        img_h = content_w * (5.2 / 12)   # matches figsize=(12, 5.2) aspect ratio
        story.append(Image(chart_png, width=content_w, height=img_h))
    else:
        story.append(Paragraph("(Chart could not be rendered.)", S["body"]))
    story.append(Spacer(1, 14))

    # Key metrics — two-column layout via a 4-col table
    story.append(Paragraph("Key Metrics", S["section"]))

    net    = summary.get("net_premium", 0.0)
    max_p  = summary.get("max_profit", float("inf"))
    max_l  = summary.get("max_loss",   float("-inf"))
    be     = summary.get("breakeven_points", [])
    spot   = summary.get("current_spot", None)

    net_str  = f"{'Credit' if net >= 0 else 'Debit'} {_usd(abs(net))}"
    be_str   = ", ".join(_usd(b) for b in be) if be else "None"
    spot_str = _usd(float(spot)) if spot is not None else "N/A"

    def _lbl(t): return Paragraph(t, S["metric_lbl"])
    def _val(t): return Paragraph(t, S["metric_val"])

    mx_data = [
        [_lbl("Max Profit"),    _val(_fmt_metric(max_p)),
         _lbl("Net Premium"),   _val(net_str)],
        [_lbl("Max Loss"),      _val(_fmt_metric(max_l)),
         _lbl("Current Spot"),  _val(spot_str)],
        [_lbl("Breakeven Spot Price(s)"), _val(be_str), "", ""],
    ]
    half = content_w / 2
    mx_tbl = Table(mx_data,
                   colWidths=[2.8*cm, half - 2.8*cm, 2.8*cm, half - 2.8*cm],
                   hAlign="LEFT")
    mx_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.4, colors.HexColor("#f1f5f9")),
        ("SPAN",          (1, 2), (3,  2)),
    ]))
    story.append(mx_tbl)
    story.append(Spacer(1, 16))

    # Footer disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(_DISCLAIMER, S["disclaimer"]))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# LaTeX fallback (used only when reportlab is not installed)
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    for old, new in [
        ("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
        ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
        ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ]:
        text = text.replace(old, new)
    return text


def _build_latex(ticker, strategy_name, report_date, legs, summary,
                 chart_png_rel):
    def _leg_row(L):
        prem_str = f"{float(L.get('prem', 0)):.4f}"
        return (
            f"  {_esc(str(L.get('type','')))} & {_esc(str(L.get('K','')))} & "
            f"{_esc(str(L.get('expiry','')))} & {_esc(str(L.get('pos','')))} & "
            f"{_esc(prem_str)} \\\\"
        )
    leg_rows = "\n".join(_leg_row(L) for L in legs)
    net   = summary.get("net_premium", 0.0)
    max_p = summary.get("max_profit", float("inf"))
    max_l = summary.get("max_loss",   float("-inf"))
    be    = summary.get("breakeven_points", [])
    spot  = summary.get("current_spot", None)

    diagram = (
        rf"\includegraphics[width=\linewidth]{{{chart_png_rel}}}"
        if chart_png_rel else r"\textit{(Chart unavailable)}"
    )
    return rf"""\documentclass{{article}}
\usepackage[margin=2.5cm]{{geometry}}
\usepackage{{booktabs,graphicx,fancyhdr,lastpage,lmodern}}
\usepackage[T1]{{fontenc}}
\pagestyle{{fancy}}\fancyhf{{}}
\fancyfoot[C]{{\small\textit{{Page \thepage\ of \pageref{{LastPage}}}}}}
\begin{{document}}
\begin{{flushright}}
  {{\large\textbf{{{_esc(ticker or "N/A")}}}}}\\[2pt]
  {{\normalsize {_esc(strategy_name)}}}\\[2pt]
  {{\small {report_date.strftime("%B %d, %Y")}}}
\end{{flushright}}
\noindent\rule{{\linewidth}}{{0.5pt}}\vspace{{6pt}}
\section*{{Strategy Legs}}
\begin{{tabular}}{{@{{}}lrllr@{{}}}}
  \toprule
  \textbf{{Type}}&\textbf{{Strike}}&\textbf{{Expiry}}&\textbf{{Position}}&\textbf{{Premium}}\\
  \midrule
{leg_rows}
  \bottomrule
\end{{tabular}}
\vspace{{14pt}}
\section*{{Payoff Diagram}}
\begin{{center}}{diagram}\end{{center}}
\vspace{{10pt}}
\section*{{Key Metrics}}
\begin{{minipage}}[t]{{0.48\linewidth}}
  \textbf{{Max Profit:}} {_fmt_metric(max_p)}\\[4pt]
  \textbf{{Max Loss:}} {_fmt_metric(max_l)}\\[4pt]
  \textbf{{Breakeven(s):}} {", ".join(f"{b:.2f}" for b in be) if be else "None"}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.48\linewidth}}
  \textbf{{Net Premium:}} {"Credit" if net >= 0 else "Debit"} {abs(net):.4f}\\[4pt]
  \textbf{{Current Spot:}} {f"{float(spot):.2f}" if spot is not None else "N/A"}
\end{{minipage}}
\vspace{{14pt}}
\noindent\rule{{\linewidth}}{{0.5pt}}\vspace{{4pt}}
\begin{{center}}\small\textit{{For educational purposes only --- not financial advice.}}\end{{center}}
\end{{document}}""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_pdf(
    fig,
    ticker: str,
    strategy_name: str,
    legs: list[dict],
    summary: dict,
    strategy=None,
    spot_range=None,
    company_name: str = "",
) -> tuple[bytes | None, str, str]:
    today = date.today()
    safe_name   = strategy_name.replace(" ", "_").replace("/", "-")
    safe_ticker = (ticker or "STRATEGY").upper()
    filename_base = f"{safe_ticker}_{safe_name}_{today.strftime('%Y-%m-%d')}"

    with tempfile.TemporaryDirectory() as tmpdir:
        chart_png = _chart_png_matplotlib(strategy, spot_range, tmpdir) \
            if strategy is not None else None

        try:
            pdf_bytes = _build_reportlab_pdf(
                ticker        = ticker,
                company_name  = company_name,
                strategy_name = strategy_name,
                report_date   = today,
                legs          = legs,
                summary       = summary,
                chart_png     = chart_png,
            )
            return pdf_bytes, "", filename_base
        except ImportError:
            pass

        # Fallback: LaTeX source for local compilation
        tex = _build_latex(
            ticker        = ticker,
            strategy_name = strategy_name,
            report_date   = today,
            legs          = legs,
            summary       = summary,
            chart_png_rel = "chart.png" if chart_png else None,
        )
        return None, tex, filename_base
