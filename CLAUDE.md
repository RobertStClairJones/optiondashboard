# optiondashboard

## What this project does
A Bloomberg-style terminal (TUI) for options trading analysis:
- Fetch live option chains for any ticker via yfinance
- Build multi-leg strategies manually or from live data
- Visualise payoff diagrams (ASCII in TUI, matplotlib in PDF)
- Analyse risk/reward metrics (max profit/loss, breakeven, target price)
- Export professional single-page PDF reports

## How to run
```
python -m tui
```
Or use the macOS launcher for a dedicated window:
```
bash launch.sh [TICKER]
```

## File structure
```
tui/                        ← UI package
  __init__.py               ← re-exports OptionsTUI; ensures project root on sys.path
  __main__.py               ← entry point for `python -m tui` (argparse + .run())
  app.py                    ← OptionsTUI app shell, keybindings, top-level handlers,
                              presets, save/load helpers, _build_strategy
  widgets.py                ← MetricsBar, ChartWidget, ToastContainer, ConfirmModal,
                              and the _render_chart plotext helper
  tabs.py                   ← LiveDataTab, SavedTab, BacktestingTab, HelpTab
  analytics.py              ← _fmt_money, _analytical_max_profit_loss,
                              _is_multi_directional (pure-math, no UI deps)
  constants.py              ← shared C_AMBER / C_BB_* colour palette
  styles.tcss               ← Textual stylesheet (resolved via CSS_PATH on app.py)
launch.py                   ← spawns new TUI window per OS (also Ctrl+N shortcut)
launch.sh                   ← macOS Terminal.app launcher with amber profile
OptionsTerminal.terminal    ← Terminal.app profile (amber theme, 220×55)
core/
  __init__.py               ← re-exports Option, StockPosition, Strategy + market fns
  engine.py                 ← options math (Option, StockPosition, Strategy)
  market_data.py            ← live data fetching via yfinance
utils/
  __init__.py
  export_pdf.py             ← ReportLab single-page PDF generation
data/
  saved_charts/             ← JSON payoff charts (auto-created, gitignored)
  saved_pdfs/               ← exported PDFs (auto-created, gitignored)
requirements.txt
```

## Module responsibilities
- **tui.app** owns the `OptionsTUI` class and is the only place that wires
  Textual events to project logic. Path constants (`SAVED_CHARTS_DIR`,
  `SAVED_PDFS_DIR`) live here, computed relative to the project root via
  `Path(__file__).resolve().parent.parent`.
- **tui.widgets** holds reusable widgets and the plotext-based chart renderer.
  No knowledge of strategies-on-disk or PDF export.
- **tui.tabs** holds the four `TabPane` content widgets. Pure layout — no
  event handlers; those live on `OptionsTUI` in `tui.app`.
- **tui.analytics** is dependency-free pure math (no Textual / yfinance /
  matplotlib). Safe to import from anywhere.
- **tui.constants** holds the shared colour palette used by `RichText` style
  strings across `widgets.py`, `tabs.py`, and `app.py`.

## Python version
3.12.6 (managed via pyenv)

## Key libraries
- textual 8.x — TUI framework
- yfinance — market data
- numpy — payoff calculations
- reportlab — PDF export
- plotext — ASCII charts in TUI
- matplotlib — chart rendering in PDF

## Coding conventions
- UI logic lives in the `tui/` package; respect the module split (app vs widgets
  vs tabs vs analytics vs constants) when adding code
- Options math stays in core/engine.py
- Market data fetching stays in core/market_data.py
- PDF export stays in utils/export_pdf.py
- Pure-math helpers used by both UI and exports go in tui/analytics.py
  (kept dependency-free — no textual / yfinance / matplotlib imports)
- Never hardcode API keys — use .env

## Notes for Claude Code
- Do not break existing functionality when making changes
- The core/ package re-exports everything via __init__.py — from core import Option always works
- The tui/ package re-exports `OptionsTUI` via __init__.py — `from tui import OptionsTUI` works
- data/ directories are auto-created by tui/app.py on import — never hardcode those paths
- Path constants in tui/app.py use `Path(__file__).resolve().parent.parent` to
  reach the project root; do not collapse to `parent` — that points at the
  package directory
- Textual 8.x quirk: Select widget border/color must target SelectCurrent child, not Select itself
- Textual 8.x quirk: Tabs Underline widget must be hidden via CSS (display: none)
- `CSS_PATH = "styles.tcss"` on OptionsTUI resolves relative to tui/app.py — i.e.
  to tui/styles.tcss
