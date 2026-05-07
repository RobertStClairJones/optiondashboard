"""
constants.py
------------
Shared colour palette for the Options Terminal TUI.

These hex values are referenced by RichText style strings across widgets,
tabs, and the app shell. They mirror the palette used in tui/styles.tcss.
"""

# Bloomberg colour palette (general)
C_AMBER  = "#FF8C00"
C_GREEN  = "#00FF41"
C_RED    = "#FF3333"
C_CYAN   = "#00E5FF"
C_YELLOW = "#FFE000"
C_DIM    = "#664400"

# Bloomberg-style stat-bar palette (used by MetricsBar + chart hover)
C_BB_LABEL = "#AAAAAA"   # dim light grey labels
C_BB_WHITE = "#FFFFFF"   # neutral values (spot, breakeven, budget)
C_BB_GREEN = "#39FF14"   # positive values + "Unlimited"
C_BB_RED   = "#FF3333"   # negative values
C_BB_GOLD  = "#FFD700"   # profit @ target price (always stands out)
