# Options Terminal

A Bloomberg-style terminal for options strategy analysis. Fetch live chains, build multi-leg strategies, visualise payoff diagrams, and export PDF reports — all from the command line.

## Quick start

```bash
pip install -r requirements.txt
python tui.py
```

## Launching

| Command | What it does |
|---------|-------------|
| `python tui.py` | Run directly in current terminal |
| `python tui.py --ticker AAPL` | Pre-populate ticker on launch |
| `bash launch.sh [TICKER]` | Open a new Terminal.app window (macOS, amber theme) |
| `python launch.py [TICKER]` | Open a new window on any OS |

**First time on macOS** — install the terminal profile for the amber theme:
1. Double-click `OptionsTerminal.terminal` in Finder
2. Click OK to install
3. `launch.sh` will use it automatically from then on

## Project structure

```
tui.py                      ← entry point
tui.tcss                    ← stylesheet
launch.py                   ← multi-OS window spawner
launch.sh                   ← macOS launcher
OptionsTerminal.terminal    ← Terminal.app profile
core/
  engine.py                 ← options math
  market_data.py            ← live data (yfinance)
utils/
  export_pdf.py             ← PDF export (ReportLab)
data/
  saved_charts/             ← saved JSON strategies (auto-created)
  saved_pdfs/               ← exported PDFs (auto-created)
requirements.txt
```

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+N` | Open a new TUI window |
| `Tab` | Navigate between tabs |
| `Q` / `Ctrl+C` | Quit |
