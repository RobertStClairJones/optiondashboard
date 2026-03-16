# optiondashboard

## What this project does
A Streamlit-based options trading dashboard that allows users to:
- Look up live or manual option chain data for any ticker
- Select expiry dates and build multi-leg option strategies
- Visualise payoff diagrams for different strategies
- Analyse risk/reward metrics (return on risk, probability, max profit/loss)

## How to run
streamlit run dashboard.py

## File structure
- dashboard.py — main UI and app entry point
- core.py — core calculations and business logic
- market_data.py — fetches live market data (option chains, spot prices)
- strategies.py — options strategy definitions and logic
- visualization.py — payoff chart generation
- demo.py — demo/testing version
- requirements.txt — Python dependencies
- .streamlit/config.toml — Streamlit configuration
- saved_charts/ — locally saved payoff visualisations (JSON)

## Python version
3.12.6 (managed via pyenv)

## Key libraries
- Streamlit — UI framework
- yfinance — market data source
- pandas, numpy — data handling
- plotly or matplotlib — charting (check visualization.py)

## Coding conventions
- Keep UI logic in dashboard.py
- Keep calculations in core.py
- Keep all data fetching in market_data.py
- Keep strategy logic in strategies.py
- Keep chart generation in visualization.py

## Notes for Claude Code
- Never hardcode API keys — use .env file
- Do not break existing functionality when making UI changes
- Always test that `streamlit run dashboard.py` still works after changes
