# OPTIONS TERMINAL — Launch Guide

## Quick start (no dependencies)

```bash
python tui.py
```

---

## Option A — `launch.sh` (recommended, no extra tools)

Opens a new Terminal.app window with the correct profile applied.

```bash
bash launch.sh           # blank TUI
bash launch.sh AAPL      # pre-populate ticker field
```

**First time only — install the Terminal profile:**

1. Double-click `OptionsTerminal.terminal` in Finder.
2. Terminal.app will ask to install the profile — click **OK**.
3. After that, `launch.sh` will automatically apply it (220×55 window, amber-on-black).

---

## Option B — `OptionsTerminal.app` (Platypus bundle)

A native macOS `.app` double-clickable launcher.

### Prerequisites

```bash
brew install --cask platypus
# Open Platypus.app → Preferences → Install Command Line Tool
```

### Build

```bash
bash build_app.sh
```

This creates `OptionsTerminal.app` in the project root.

**Install the Terminal profile first** (same as Option A above), then double-click `OptionsTerminal.app`.

> **Note:** Platypus "Text Window" mode renders script stdout in a Cocoa panel.
> For the richest TUI experience (colour, keyboard handling) use `launch.sh` or
> `python tui.py` in a full Terminal.app window.

---

## Option C — `launch.py` (multi-window, cross-platform)

Spawn independent TUI sessions from the command line or via `Ctrl+N` inside the TUI:

```bash
python launch.py           # new blank window
python launch.py TSLA      # pre-populate ticker
```

---

## Fonts

For the best visual experience install **MesloLGS NR** (used by the Terminal profile):

```
https://github.com/romkatv/powerlevel10k#meslo-nerd-font-patched-for-powerlevel10k
```

The profile falls back to `Menlo` if MesloLGS is not installed.
