"""
core.py
-------
Core data structures: Option, StockPosition, Strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Union

import numpy as np


# ---------------------------------------------------------------------------
# Leg types
# ---------------------------------------------------------------------------

@dataclass
class Option:
    """
    A single vanilla option position.

    Parameters
    ----------
    option_type : 'call' or 'put'
    position    : 'long' or 'short'
    strike      : strike price (K)
    premium     : option price paid/received per unit
    expiry      : expiration date
    quantity    : number of contracts (default 1)
    label       : display name (auto-generated if empty)
    """

    option_type: Literal["call", "put"]
    position: Literal["long", "short"]
    strike: float
    premium: float
    expiry: date
    quantity: int = 1
    label: str = ""

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("quantity must be a positive integer.")
        if self.premium < 0:
            raise ValueError("premium cannot be negative.")
        if self.strike <= 0:
            raise ValueError("strike must be positive.")
        if not self.label:
            pos = "Long" if self.position == "long" else "Short"
            qty = f" x{self.quantity}" if self.quantity > 1 else ""
            opt = "Call" if self.option_type == "call" else "Put"
            self.label = f"{pos}{qty} {opt} K={self.strike:.2f}"

    # ------------------------------------------------------------------
    # All cash-flow / P&L results are reported per-contract: each US equity
    # option contract represents 100 shares, so we apply a fixed ×100
    # multiplier here. Quantity is the number of contracts.
    _SHARES_PER_CONTRACT = 100

    def payoff_at_expiry(self, spot_prices: np.ndarray) -> np.ndarray:
        """P&L at expiry for each element of *spot_prices* (per-contract dollars)."""
        spot = np.asarray(spot_prices, dtype=float)
        if self.option_type == "call":
            intrinsic = np.maximum(spot - self.strike, 0.0)
        else:
            intrinsic = np.maximum(self.strike - spot, 0.0)

        if self.position == "long":
            per_share = intrinsic - self.premium
        else:
            per_share = self.premium - intrinsic
        return per_share * self.quantity * self._SHARES_PER_CONTRACT

    def realized_payoff(self, actual_spot: float) -> float:
        """P&L for a single known spot price at maturity (per-contract dollars)."""
        return float(self.payoff_at_expiry(np.array([actual_spot]))[0])

    def days_to_expiry(self, reference_date: date | None = None) -> int:
        ref = reference_date or date.today()
        return (self.expiry - ref).days

    def cost(self) -> float:
        """
        Net cash flow of this leg in dollars (per-contract, ×100 shares).
        Negative = debit (long), positive = credit (short).
        """
        sign = -1 if self.position == "long" else 1
        return sign * self.premium * self.quantity * self._SHARES_PER_CONTRACT


@dataclass
class StockPosition:
    """
    A long or short position in the underlying stock / future.

    Parameters
    ----------
    entry_price : price at which the stock was bought/shorted
    position    : 'long' or 'short'
    quantity    : number of shares (default 1)
    label       : display name (auto-generated if empty)
    """

    entry_price: float
    position: Literal["long", "short"]
    quantity: int = 1
    label: str = ""

    def __post_init__(self):
        if not self.label:
            pos = "Long" if self.position == "long" else "Short"
            qty = f" x{self.quantity}" if self.quantity > 1 else ""
            self.label = f"{pos}{qty} Stock @ {self.entry_price:.2f}"

    def payoff_at_expiry(self, spot_prices: np.ndarray) -> np.ndarray:
        spot = np.asarray(spot_prices, dtype=float)
        if self.position == "long":
            return (spot - self.entry_price) * self.quantity
        else:
            return (self.entry_price - spot) * self.quantity

    def realized_payoff(self, actual_spot: float) -> float:
        return float(self.payoff_at_expiry(np.array([actual_spot]))[0])

    def cost(self) -> float:
        sign = -1 if self.position == "long" else 1
        return sign * self.entry_price * self.quantity


# Convenience union type for type hints
Leg = Union[Option, StockPosition]


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class Strategy:
    """
    A collection of option / stock legs forming a trading strategy.

    Usage
    -----
    >>> s = Strategy("My Spread")
    >>> s.add_leg(Option("call", "long",  100, 3.0, date(2025,6,20)))
    >>> s.add_leg(Option("call", "short", 110, 1.0, date(2025,6,20)))
    >>> s.print_summary()
    """

    def __init__(self, name: str, legs: list[Leg] | None = None):
        self.name = name
        self.legs: list[Leg] = list(legs) if legs else []

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def add_leg(self, leg: Leg) -> Strategy:
        """Append a leg and return *self* for chaining."""
        self.legs.append(leg)
        return self

    # ------------------------------------------------------------------
    # Financial metrics
    # ------------------------------------------------------------------

    def net_premium(self) -> float:
        """
        Aggregate cash flow of the strategy.
        Positive = net credit received, negative = net debit paid.
        """
        return sum(leg.cost() for leg in self.legs)

    def payoff_at_expiry(self, spot_prices: np.ndarray) -> np.ndarray:
        """Total P&L across all legs for each spot price."""
        spot = np.asarray(spot_prices, dtype=float)
        total = np.zeros_like(spot)
        for leg in self.legs:
            total += leg.payoff_at_expiry(spot)
        return total

    def realized_payoff(self, actual_spot: float) -> float:
        """
        Compute the total realised P&L when you know the final spot price.

        Parameters
        ----------
        actual_spot : observed underlying price at option expiry

        Returns
        -------
        float : net profit (positive) or loss (negative) per unit
        """
        return float(self.payoff_at_expiry(np.array([actual_spot]))[0])

    def breakeven_points(self, spot_prices: np.ndarray) -> list[float]:
        """
        Approximate breakeven prices via linear interpolation at sign changes.
        """
        payoffs = self.payoff_at_expiry(spot_prices)
        breakevens: list[float] = []
        for i in range(len(payoffs) - 1):
            if payoffs[i] * payoffs[i + 1] < 0:
                be = spot_prices[i] - payoffs[i] * (
                    spot_prices[i + 1] - spot_prices[i]
                ) / (payoffs[i + 1] - payoffs[i])
                breakevens.append(round(float(be), 4))
        return breakevens

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self, spot_prices: np.ndarray | None = None) -> dict:
        """Return a dict with key risk metrics over *spot_prices*."""
        if spot_prices is None:
            spot_prices = self._auto_spot_range()
        payoffs = self.payoff_at_expiry(spot_prices)

        return {
            "strategy": self.name,
            "n_legs": len(self.legs),
            "net_premium": round(self.net_premium(), 4),
            "max_profit": float(np.max(payoffs)),
            "max_loss": float(np.min(payoffs)),
            "breakeven_points": self.breakeven_points(spot_prices),
        }

    def print_summary(self, spot_prices: np.ndarray | None = None) -> None:
        """Pretty-print strategy metrics."""
        if spot_prices is None:
            spot_prices = self._auto_spot_range()
        s = self.summary(spot_prices)
        net = s["net_premium"]
        net_str = f"{'Credit' if net >= 0 else 'Debit'} {abs(net):.4f}"
        be_str = (
            ", ".join(f"{b:.4f}" for b in s["breakeven_points"])
            if s["breakeven_points"]
            else "None"
        )

        print(f"\n{'='*52}")
        print(f"  Strategy   : {s['strategy']}")
        print(f"  Legs       : {s['n_legs']}")
        print(f"  Net        : {net_str}")
        print(f"  Max Profit : {s['max_profit']:.4f}")
        print(f"  Max Loss   : {s['max_loss']:.4f}")
        print(f"  Breakevens : {be_str}")
        print(f"{'='*52}")
        for leg in self.legs:
            pos = "L" if getattr(leg, "position", "long") == "long" else "S"
            print(f"    [{pos}]  {leg.label}")
        print()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auto_spot_range(self, padding: float = 0.30, n: int = 600) -> np.ndarray:
        """Infer a sensible price axis from the legs' strikes / entry prices."""
        ref_prices: list[float] = []
        for leg in self.legs:
            if isinstance(leg, Option):
                ref_prices.append(leg.strike)
            elif isinstance(leg, StockPosition):
                ref_prices.append(leg.entry_price)

        if not ref_prices:
            raise ValueError("Strategy has no legs — cannot determine spot range.")

        lo, hi = min(ref_prices), max(ref_prices)
        mid = (lo + hi) / 2
        spread = max(hi - lo, mid * 0.15)
        lo_plot = max(lo - spread * (1 + padding), 0.01)
        hi_plot = hi + spread * (1 + padding)
        return np.linspace(lo_plot, hi_plot, n)

    def __repr__(self) -> str:
        return f"Strategy('{self.name}', legs={len(self.legs)})"
