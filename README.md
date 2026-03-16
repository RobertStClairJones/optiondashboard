# optiondashboard

A Streamlit-based options trading dashboard for building, visualising, and analysing multi-leg option strategies.

## Features

- Look up live or manual option chain data for any ticker
- Select expiry dates and build multi-leg option strategies
- Visualise payoff diagrams with interactive Plotly charts
- Analyse risk/reward metrics (max profit, max loss, breakeven points)
- Save and browse payoff visualisations locally
- Dark trading-platform aesthetic

## How to run

### Option 1 — Makefile
```bash
make run
```

### Option 2 — Shell script
```bash
./run.sh
```

### Option 3 — Direct
```bash
streamlit run dashboard.py
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Or using make
make install
```

## Python version

3.12.6 (managed via pyenv)

## File structure

| File | Purpose |
|------|---------|
| `dashboard.py` | Main UI and app entry point |
| `core.py` | Core calculations and data structures |
| `market_data.py` | Live market data via yfinance |
| `strategies.py` | Pre-built strategy factory functions |
| `visualization.py` | Payoff chart generation (matplotlib + plotly) |
| `saved_charts/` | Locally saved payoff visualisations (JSON) |
| `.streamlit/config.toml` | Streamlit theme configuration |
