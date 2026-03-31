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
python tui.py
```
Or use the macOS launcher for a dedicated window:
```
bash launch.sh [TICKER]
```

## File structure
```
tui.py                      ← entry point, all UI and event logic
tui.tcss                    ← Textual stylesheet
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
- All UI logic stays in tui.py
- Options math stays in core/engine.py
- Market data fetching stays in core/market_data.py
- PDF export stays in utils/export_pdf.py
- Never hardcode API keys — use .env

## Notes for Claude Code
- Do not break existing functionality when making changes
- The core/ package re-exports everything via __init__.py — from core import Option always works
- data/ directories are auto-created by tui.py on startup — never hardcode those paths
- Textual 8.x quirk: Select widget border/color must target SelectCurrent child, not Select itself
- Textual 8.x quirk: Tabs Underline widget must be hidden via CSS (display: none)
