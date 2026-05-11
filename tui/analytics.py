"""
analytics.py
------------
Pure-math helpers for the Options Terminal TUI:

* ``_fmt_money``                 – format a P&L value as $X,XXX.XX (handles ±inf).
* ``_analytical_max_profit_loss`` – closed-form max-profit / max-loss for
  recognised strategy shapes (verticals, straddle/strangle, butterfly,
  iron condor, covered call, protective put).
* ``_is_multi_directional``      – helper flag for strategies that profit
  on either-direction moves.

No textual / yfinance / matplotlib imports — this module is dependency-free.
"""

from __future__ import annotations


# ── Monetary formatter ────────────────────────────────────────────────────────

def _fmt_money(v: float, inf_str: str = "Unlimited") -> str:
    """Format a P&L value as $X,XXX.XX; handle ±inf gracefully."""
    if v == float("inf"):   return inf_str
    if v == float("-inf"):  return f"-{inf_str}"
    return f"${v:,.2f}"


# ── Analytical max-profit / max-loss ──────────────────────────────────────────

_SHARES_PER_CONTRACT = 100   # mirrors core.engine.Option._SHARES_PER_CONTRACT


def _analytical_max_profit_loss(legs: list[dict]) -> tuple[float | None, float | None]:
    """
    Return (max_profit, max_loss) analytically for recognised strategy types.
    Values are in **dollars per-contract** — option-leg results are multiplied
    by 100 (one US equity option contract = 100 shares). Stock legs use their
    raw share quantity. float('inf') / float('-inf') = unlimited.
    Returns (None, None) to signal caller should keep the numeric-scan result.
    """
    M = _SHARES_PER_CONTRACT  # apply to every option-leg result below
    opts   = [L for L in legs if L.get("type") in ("call", "put")]
    stocks = [L for L in legs if L.get("type") in ("stock", "stock (underlying)")]

    def _nc() -> float:
        """Net credit of all option legs in dollars (per-contract, ×100)."""
        t = 0.0
        for L in legs:
            if L.get("type") not in ("call", "put"):
                continue
            p, q = float(L.get("prem", 0.0)), int(L.get("qty", 1))
            t += (p * q if L.get("pos") == "short" else -p * q) * M
        return t

    # ── Single option ────────────────────────────────────────────────────────
    if len(legs) == 1 and len(opts) == 1:
        L = opts[0]
        K, p, q, pos, ot = (float(L["K"]), float(L.get("prem", 0.0)),
                             int(L.get("qty", 1)), L["pos"], L["type"])
        if   ot == "call" and pos == "long":  return float("inf"),       -p * q * M
        elif ot == "call" and pos == "short": return  p * q * M,          float("-inf")
        elif ot == "put"  and pos == "long":  return (K - p) * q * M,    -p * q * M
        elif ot == "put"  and pos == "short": return  p * q * M,        -(K - p) * q * M

    # ── 2-leg, options only ──────────────────────────────────────────────────
    if len(legs) == 2 and len(opts) == 2 and not stocks:
        c_legs = sorted([L for L in opts if L["type"] == "call"], key=lambda L: float(L["K"]))
        p_legs = sorted([L for L in opts if L["type"] == "put"],  key=lambda L: float(L["K"]))

        if len(c_legs) == 2:                               # both calls
            lo, hi = c_legs;  q = int(lo.get("qty", 1))
            if lo["pos"] == "long"  and hi["pos"] == "short":   # bull call spread
                nd = float(lo["prem"]) - float(hi["prem"])
                return (float(hi["K"]) - float(lo["K"]) - nd) * q * M, -nd * q * M
            if lo["pos"] == "short" and hi["pos"] == "long":    # bear call spread
                nc_v = float(lo["prem"]) - float(hi["prem"])
                return nc_v * q * M, -(float(hi["K"]) - float(lo["K"]) - nc_v) * q * M

        if len(p_legs) == 2:                               # both puts
            lo, hi = p_legs;  q = int(lo.get("qty", 1))
            if hi["pos"] == "long"  and lo["pos"] == "short":   # bear put spread
                nd = float(hi["prem"]) - float(lo["prem"])
                return (float(hi["K"]) - float(lo["K"]) - nd) * q * M, -nd * q * M
            if hi["pos"] == "short" and lo["pos"] == "long":    # bull put spread
                nc_v = float(hi["prem"]) - float(lo["prem"])
                return nc_v * q * M, -(float(hi["K"]) - float(lo["K"]) - nc_v) * q * M

        if len(c_legs) == 1 and len(p_legs) == 1:         # call + put
            c, p = c_legs[0], p_legs[0];  q = int(c.get("qty", 1))
            if c["pos"] == "long"  and p["pos"] == "long":   # long straddle/strangle
                return float("inf"), -(float(c["prem"]) + float(p["prem"])) * q * M
            if c["pos"] == "short" and p["pos"] == "short":  # short straddle/strangle
                return (float(c["prem"]) + float(p["prem"])) * q * M, float("-inf")

    # ── 3-leg butterfly ──────────────────────────────────────────────────────
    if len(legs) == 3 and len(opts) == 3 and not stocks:
        lo, mid, hi = sorted(opts, key=lambda L: float(L["K"]))
        q = int(lo.get("qty", 1))
        if (lo["pos"] == "long" and mid["pos"] == "short"
                and int(mid.get("qty", 1)) == 2 and hi["pos"] == "long"):
            nd = _nc()   # already in dollars (×100)
            return (float(mid["K"]) - float(lo["K"])) * q * M + nd, nd

    # ── 4-leg iron condor ────────────────────────────────────────────────────
    if len(legs) == 4 and len(opts) == 4 and not stocks:
        c_s = sorted([L for L in opts if L["type"] == "call"], key=lambda L: float(L["K"]))
        p_s = sorted([L for L in opts if L["type"] == "put"],  key=lambda L: float(L["K"]))
        if len(c_s) == 2 and len(p_s) == 2:
            p_lo, p_hi = p_s;  c_lo, c_hi = c_s
            if (p_lo["pos"] == "long"  and p_hi["pos"] == "short" and
                c_lo["pos"] == "short" and c_hi["pos"] == "long"):
                nc_v   = _nc()   # dollars (×100)
                put_w  = float(p_hi["K"]) - float(p_lo["K"])
                call_w = float(c_hi["K"]) - float(c_lo["K"])
                return nc_v, -(max(put_w, call_w) * M - nc_v)

    # ── Covered call ─────────────────────────────────────────────────────────
    # Stock leg uses share quantity (not contract quantity), but it pairs with
    # one option contract worth 100 shares — so we scale the option premium and
    # its strike-vs-entry differential by ×100 to match.
    if len(legs) == 2 and len(opts) == 1 and len(stocks) == 1:
        c_l = [L for L in opts if L["type"] == "call" and L["pos"] == "short"]
        if c_l and stocks[0]["pos"] == "long":
            c, s = c_l[0], stocks[0]
            q = int(c.get("qty", 1))
            return ((float(c["K"]) - float(s["K"]) + float(c.get("prem", 0))) * q * M,
                    -(float(s["K"]) - float(c.get("prem", 0))) * q * M)

    # ── Protective put ───────────────────────────────────────────────────────
    if len(legs) == 2 and len(opts) == 1 and len(stocks) == 1:
        p_l = [L for L in opts if L["type"] == "put" and L["pos"] == "long"]
        if p_l and stocks[0]["pos"] == "long":
            p, s = p_l[0], stocks[0]
            q = int(p.get("qty", 1))
            return (float("inf"),
                    -(float(s["K"]) - float(p["K"]) + float(p.get("prem", 0))) * q * M)

    return None, None   # unrecognised — caller keeps numeric-scan result


def compute_net_greeks(legs: list[dict], spot: float | None) -> tuple[float, float]:
    """Return (net_delta, net_theta) summed across all legs.

    Per-leg contribution:
      * Option legs: sign × BS_greek × qty × _SHARES_PER_CONTRACT
        (sign = +1 long, -1 short; net_delta is share-equivalent, net_theta
         is daily $ decay)
      * Stock legs: sign × qty contributes to delta only (qty is shares,
        no ×100); theta = 0
      * Legs missing IV (e.g. preset-loaded with no live chain data) are
        skipped — their contribution stays 0.

    Returns (NaN, NaN) if spot is missing/invalid OR no leg could contribute
    (so the UI knows to render "—" rather than a spurious 0.00).
    """
    if spot is None or not (spot > 0):
        return float("nan"), float("nan")

    from datetime import datetime, date
    from core.providers._bs import bs_greeks

    today = date.today()
    net_delta = 0.0
    net_theta = 0.0
    contributed = False

    for L in legs:
        leg_type = (L.get("type") or "").lower()
        pos = (L.get("pos") or "long").lower()
        sign = 1 if pos == "long" else -1
        qty = int(L.get("qty", 1))

        if leg_type in ("stock", "stock (underlying)"):
            # Stock delta = ±1 per share; theta = 0. qty is already shares
            # so we do NOT apply the ×100 contract multiplier here.
            net_delta += sign * qty
            contributed = True
            continue

        if leg_type not in ("call", "put"):
            continue

        # IV is required for BS — captured on add for live legs, missing for
        # preset/saved legs. Skip silently when absent.
        iv_raw = L.get("iv")
        try:
            iv = float(iv_raw) if iv_raw is not None else float("nan")
        except (TypeError, ValueError):
            iv = float("nan")
        if iv != iv or iv <= 0:
            continue

        try:
            exp_date = datetime.strptime(L["expiry"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        t_years = max((exp_date - today).days / 365.0, 1.0 / 365.0)

        strike = float(L.get("K", 0.0))
        g = bs_greeks(spot, strike, t_years, iv, leg_type)
        if g["delta"] == g["delta"]:
            net_delta += sign * g["delta"] * qty * _SHARES_PER_CONTRACT
            contributed = True
        if g["theta"] == g["theta"]:
            net_theta += sign * g["theta"] * qty * _SHARES_PER_CONTRACT
            contributed = True

    if not contributed:
        return float("nan"), float("nan")
    return net_delta, net_theta


def _is_multi_directional(legs: list[dict]) -> bool:
    """
    Return True if the strategy can profit from the underlying moving in either
    direction (straddle, strangle, butterfly, condor, iron condor).
    """
    opts = [L for L in legs if L.get("type") in ("call", "put")]
    long_calls = [L for L in opts if L["type"] == "call" and L["pos"] == "long"]
    long_puts  = [L for L in opts if L["type"] == "put"  and L["pos"] == "long"]
    # Long straddle / strangle: long call + long put
    if long_calls and long_puts:
        return True
    # Butterfly (3 options): long–short–long
    if len(opts) == 3:
        s = sorted(opts, key=lambda L: float(L["K"]))
        if s[0]["pos"] == "long" and s[1]["pos"] == "short" and s[2]["pos"] == "long":
            return True
    # Condor / iron condor (4 options)
    if len(opts) == 4:
        return True
    return False
