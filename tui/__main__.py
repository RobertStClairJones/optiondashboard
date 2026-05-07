"""
__main__.py
-----------
Entry point for ``python -m tui``.
"""
from __future__ import annotations

import argparse

from tui.app import OptionsTUI


def main() -> None:
    parser = argparse.ArgumentParser(description="OPTIONS TERMINAL — payoff analysis")
    parser.add_argument("--session-name", default="",
                        help="Set the window/app title (e.g. 'AAPL Iron Condor')")
    parser.add_argument("--ticker", default="",
                        help="Pre-populate the ticker input on startup")
    args = parser.parse_args()
    OptionsTUI(ticker=args.ticker, session_name=args.session_name).run()


if __name__ == "__main__":
    main()
