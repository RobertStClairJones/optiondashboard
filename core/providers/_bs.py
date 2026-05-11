"""
core.providers._bs
------------------
Shared Black-Scholes helpers used by both YFinanceProvider and
IBKRProvider so the two providers emit greeks on the same scale.

Convention: vega is per 1% IV change; theta is per calendar day.
These match IBKR's own modelGreeks output (so BS fallback values
slot cleanly alongside IBKR-native values in mixed rows).
"""

from __future__ import annotations

import math


RISK_FREE_RATE = 0.04


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _is_nan(x) -> bool:
    if x is None:
        return True
    try:
        return math.isnan(x)
    except (TypeError, ValueError):
        return False


def bs_greeks(spot, strike, t_years, iv, right) -> dict:
    """Return Black-Scholes greeks as {delta, gamma, theta, vega}.

    Returns all-NaN if any input is degenerate (negative/zero/NaN).
    ``right`` accepts "C"/"call"/"Call" for calls (case-insensitive),
    anything else is treated as put.
    """
    nan = float("nan")
    if (_is_nan(spot) or _is_nan(strike) or _is_nan(iv)
            or spot <= 0 or strike <= 0 or iv <= 0 or t_years <= 0):
        return {"delta": nan, "gamma": nan, "theta": nan, "vega": nan}
    sigma_sqrt_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (RISK_FREE_RATE + 0.5 * iv * iv) * t_years) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    pdf_d1 = _norm_pdf(d1)
    discount = math.exp(-RISK_FREE_RATE * t_years)
    gamma = pdf_d1 / (spot * sigma_sqrt_t)
    vega = (spot * pdf_d1 * math.sqrt(t_years)) / 100.0
    if str(right).upper().startswith("C"):
        delta = _norm_cdf(d1)
        theta_year = (-spot * pdf_d1 * iv / (2.0 * math.sqrt(t_years))
                      - RISK_FREE_RATE * strike * discount * _norm_cdf(d2))
    else:
        delta = _norm_cdf(d1) - 1.0
        theta_year = (-spot * pdf_d1 * iv / (2.0 * math.sqrt(t_years))
                      + RISK_FREE_RATE * strike * discount * _norm_cdf(-d2))
    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta_year / 365.0,
        "vega": vega,
    }
