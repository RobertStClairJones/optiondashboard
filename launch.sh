#!/usr/bin/env bash
# launch.sh — open a new Terminal.app window running tui.py
# Alternative to OptionsTerminal.app — no Platypus dependency required.
#
# Usage:
#   bash launch.sh            # blank TUI
#   bash launch.sh AAPL       # pre-populate ticker

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TICKER="${1:-}"

# ── Detect Python ────────────────────────────────────────────────────────────
if [[ -f "$SCRIPT_DIR/venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
elif [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON="$(command -v python3 2>/dev/null || command -v python)"
fi

# ── Build the command to run inside the new window ───────────────────────────
if [[ -n "$TICKER" ]]; then
    TUI_CMD="cd \"$SCRIPT_DIR\" && \"$PYTHON\" tui.py --ticker \"$TICKER\" --session-name \"OPTIONS TERMINAL\""
else
    TUI_CMD="cd \"$SCRIPT_DIR\" && \"$PYTHON\" tui.py --session-name \"OPTIONS TERMINAL\""
fi

# ── AppleScript: open Terminal.app with the OptionsTerminal profile if installed
osascript <<APPLESCRIPT
tell application "Terminal"
    -- Try to use the OptionsTerminal profile; fall back silently if not installed
    try
        set newTab to do script "$TUI_CMD" with default settings
        set current settings of newTab to settings set "OptionsTerminal"
    on error
        do script "$TUI_CMD"
    end try
    activate
end tell
APPLESCRIPT
