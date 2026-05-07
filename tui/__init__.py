"""
tui package
-----------
Bloomberg-style options strategy terminal.

External callers can keep using ``from tui import OptionsTUI`` unchanged.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Ensure the project root is on sys.path so sibling packages (`core`, `utils`)
# resolve regardless of how the user invokes us (`python -m tui`, REPL,
# `python -c "from tui import OptionsTUI"`, etc.).
_PROJECT_ROOT = str(_Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from tui.app import OptionsTUI

__all__ = ["OptionsTUI"]
