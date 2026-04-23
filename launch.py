#!/usr/bin/env python3
"""
launch.py
---------
Spawns a new terminal window running tui.py as an independent process.

Usage:
    python launch.py                                    # blank TUI
    python launch.py AAPL                              # pre-populate ticker
    python launch.py AAPL --session-name "AAPL Iron Condor"
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE   = Path(__file__).parent
TUI    = HERE / "tui.py"
PYTHON = sys.executable


def _build_tui_args(ticker: str = "", session_name: str = "") -> list[str]:
    """Return the argv list for tui.py with optional flags."""
    cmd: list[str] = [PYTHON, str(TUI)]
    if ticker:
        cmd += ["--ticker", ticker]
    if session_name:
        cmd += ["--session-name", session_name]
    return cmd


def spawn_window(ticker: str = "", session_name: str = "") -> None:
    """Open a new terminal window running tui.py."""
    system = platform.system()
    if system == "Darwin":
        _spawn_macos(ticker, session_name)
    elif system == "Linux":
        _spawn_linux(ticker, session_name)
    elif system == "Windows":
        _spawn_windows(ticker, session_name)
    else:
        print(f"Unsupported OS: {system}. Run manually: python tui.py", file=sys.stderr)


# ── macOS ─────────────────────────────────────────────────────────────────────

def _spawn_macos(ticker: str, session_name: str) -> None:
    tui_args = _build_tui_args(ticker, session_name)
    # Shell-escape each argument for use inside an AppleScript string
    shell_cmd = " ".join(
        f'"{a}"' if " " in a else a for a in tui_args
    )
    cd_and_run = f'cd "{HERE}" && {shell_cmd}'

    # Prefer iTerm2 if it is running; fall back to Terminal.app
    iterm_running = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to (name of processes) contains "iTerm2"'],
        capture_output=True, text=True,
    )
    if "true" in iterm_running.stdout.lower():
        script = f'''\
tell application "iTerm2"
    activate
    set newWindow to (create window with default profile)
    tell current session of newWindow
        write text "{cd_and_run.replace('"', '\\"')}"
    end tell
end tell'''
    else:
        script = f'''\
tell application "Terminal"
    do script "{cd_and_run.replace('"', '\\"')}"
    activate
end tell'''

    subprocess.Popen(["osascript", "-e", script])


# ── Linux ─────────────────────────────────────────────────────────────────────

def _spawn_linux(ticker: str, session_name: str) -> None:
    tui_args = _build_tui_args(ticker, session_name)
    # Build a bash -c '...; exec bash' invocation so the window stays open
    inner = " ".join(f'"{a}"' if " " in a else a for a in tui_args)
    bash_cmd = f'cd "{HERE}" && {inner}'

    for term in ("gnome-terminal", "xterm", "konsole"):
        if not shutil.which(term):
            continue
        if term == "gnome-terminal":
            subprocess.Popen([term, "--", "bash", "-c", f"{bash_cmd}; exec bash"])
        elif term == "konsole":
            subprocess.Popen([term, "-e", "bash", "-c", f"{bash_cmd}; exec bash"])
        else:  # xterm
            subprocess.Popen([term, "-e", "bash", "-c", f"{bash_cmd}; exec bash"])
        return

    print(
        "No supported terminal found (gnome-terminal, xterm, konsole). "
        "Run tui.py manually.",
        file=sys.stderr,
    )


# ── Windows ───────────────────────────────────────────────────────────────────

def _spawn_windows(ticker: str, session_name: str) -> None:
    tui_args = _build_tui_args(ticker, session_name)
    inner = " ".join(f'"{a}"' if " " in a else a for a in tui_args)
    cd_and_run = f'cd /d "{HERE}" && {inner}'

    if shutil.which("wt"):  # Windows Terminal
        subprocess.Popen(["wt", "cmd", "/k", cd_and_run])
    else:
        subprocess.Popen(f'start cmd /k "{cd_and_run}"', shell=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch a new OPTIONS TERMINAL (tui.py) window."
    )
    parser.add_argument(
        "ticker", nargs="?", default="",
        help="Ticker symbol to pre-populate in the new window (e.g. AAPL)",
    )
    parser.add_argument(
        "--session-name", default="",
        help="Session name shown in the window title",
    )
    args = parser.parse_args()
    spawn_window(ticker=args.ticker, session_name=args.session_name)


if __name__ == "__main__":
    main()
