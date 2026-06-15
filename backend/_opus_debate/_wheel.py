#!/usr/bin/env python3
"""Wheel-strategy (cash-secured put -> covered call) suggestion per Speculair pick.

Sell a CSP at the "happy to own" level (downside-to-break) to get PAID to wait out a slow
re-rate; once assigned, sell a CC at the fair-value target. The CSP premium + annualized yield
are priced LIVE off the options chain (ThetaData via massive_options) when reachable, with a
qualitative fallback (strikes + tenor, "verify on broker") otherwise. NEVER an order — a paper
suggestion only.

The Director emits wheel:{suits, csp_strike, cc_strike, tenor_days, rationale}; this layer fills
missing strikes deterministically, HARD-GATES entry_posture==on_confirmation (event risk: do not
sell puts into a dated/binary catalyst), and prices the CSP live. Director values always win.
"""
import os
import re
import sys
from datetime import datetime, date

_HERE = os.path.dirname(os.path.abspath(__file__))
BK = os.path.dirname(_HERE)                              # .../backend
if BK not in sys.path:
    sys.path.insert(0, BK)
if not os.environ.get("FMP_API_KEY"):
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"

DEFAULT_TENOR = 40   # ~30-45 DTE: monthly-ish, good theta for a wheel


def _num(x):
    try:
        v = float(x)
        return v if (v == v and abs(v) != float("inf")) else None
    except (TypeError, ValueError):
        return None


def _parse_money(s):
    """First/base number out of fair-value prose like '~$215' or '$78-88 (base ~$82)'."""
    if s is None:
        return None
    t = str(s)
    m = re.search(r"base[^$0-9]{0,14}\$?\s*([0-9]+(?:\.[0-9]+)?)", t, re.I)
    if m:
        return float(m.group(1))
    vals = [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)", t)]
    if not vals:
        return None
    if len(vals) >= 2 and vals[1] <= vals[0] * 3:
        return round((vals[0] + vals[1]) / 2, 2)
    return vals[0]


def derive_strikes(pick, book, quote=None):
    """Fill CSP ('happy to own' / downside-to-break) + CC (fair value) strikes from existing fields.
    Director-supplied csp_strike/cc_strike (already merged into `pick`) win."""
    px = _num((quote or {}).get("price")) or _num(pick.get("price")) \
        or _num(pick.get("entry_price")) or _num(pick.get("current_price"))
    # CC strike = the fair-value target (cap the upside there once assigned)
    cc = _num(pick.get("cc_strike")) or _num(pick.get("target_px"))
    if cc is None:
        mos = _num(pick.get("sop_mos_pct"))     # stored as a percent (e.g. 50.6) in the value/disruptor books
        if px and mos is not None:
            frac = mos / 100.0 if abs(mos) > 1.5 else mos
            cc = round(px * (1 + frac), 2)
    if cc is None:
        cc = _parse_money(pick.get("sop_fair_value"))
    # CSP strike = the downside-to-break / where you'd be happy to own it
    csp = _num(pick.get("csp_strike")) or _num(pick.get("thesis_break_px")) or _num(pick.get("bear_fv_px"))
    if csp is None and px:
        lo = _num(pick.get("yr_low")) or _num((pick.get("stress") or {}).get("yr_low"))
        csp = round(min(px * 0.90, lo) if lo else px * 0.90, 2)   # regime has no thesis_break -> ~10% below
    return csp, cc, px


def price_csp_live(symbol, csp_strike, tenor_days=DEFAULT_TENOR):
    """Real CSP premium + annualized yield from the live chain. None if unreachable/non-optionable
    (EU names, illiquid, or no ThetaData creds in the run env -> caller uses the qualitative fallback)."""
    if not csp_strike or csp_strike <= 0:
        return None
    try:
        import massive_options as MO
        contracts = MO.get_options_snapshot(symbol)
    except Exception:
        return None
    if not contracts:
        return None
    puts = [c for c in contracts
            if (c.get("details") or {}).get("contract_type") == "put"
            and (c.get("details") or {}).get("strike_price")]
    if not puts:
        return None
    today = date.today()

    def _dte(c):
        e = str((c.get("details") or {}).get("expiration_date") or "")
        digits = e[:10] if "-" in e else e[:8]
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return (datetime.strptime(digits, fmt).date() - today).days
            except ValueError:
                continue
        return None

    cand = [(c, _dte(c)) for c in puts]
    cand = [(c, d) for c, d in cand if d is not None and d >= 7]
    if not cand:
        return None
    best_dte = min({d for _, d in cand}, key=lambda d: abs(d - tenor_days))
    exp_puts = [c for c, d in cand if d == best_dte]
    chosen = min(exp_puts, key=lambda c: abs(float(c["details"]["strike_price"]) - csp_strike))
    det = chosen["details"]
    q = chosen.get("last_quote") or {}
    strike = float(det["strike_price"])
    mid = q.get("midpoint") or (((q.get("bid") or 0) + (q.get("ask") or 0)) / 2) or None
    if not mid or mid <= 0:
        return None
    ann = round((mid / strike) * (365.0 / max(best_dte, 1)) * 100, 1)
    return {"csp_strike": round(strike, 2), "expiry": str(det.get("expiration_date")), "dte": best_dte,
            "csp_premium": round(mid, 2), "bid": q.get("bid"), "ask": q.get("ask"),
            "delta": (chosen.get("greeks") or {}).get("delta"), "iv": chosen.get("implied_volatility"),
            "csp_yield_annualized": ann}


def stamp_wheel(picks, book, quotes=None):
    """Attach a wheel suggestion per pick. Director's own wheel fields win; this fills the gaps,
    hard-gates on_confirmation (event risk), and prices the CSP live (else qualitative)."""
    quotes = quotes or {}
    for p in picks:
        w = dict(p.get("wheel") or {})
        if str(p.get("entry_posture") or "") == "on_confirmation" or w.get("suits") is False:
            p["wheel"] = {"suits": False}                # never wheel into a dated/binary event
            continue
        csp, cc, _px = derive_strikes({**p, **w}, book, quotes.get(p["symbol"]) or {})
        if not csp or not cc or csp <= 0 or cc <= 0:
            p["wheel"] = {"suits": False}
            continue
        tenor = int(_num(w.get("tenor_days")) or DEFAULT_TENOR)
        wheel = {"suits": True, "csp_strike": round(csp, 2), "cc_strike": round(cc, 2),
                 "tenor_days": tenor, "source": "qualitative",
                 "rationale": w.get("rationale") or "Get paid to wait: sell the put at your downside-to-break, then cover-call the re-rate at fair value.",
                 "csp_premium": None, "csp_yield_annualized": None,
                 "expiry": None, "dte": None, "delta": None, "iv": None}
        live = price_csp_live(p["symbol"], csp, tenor)
        if live:
            wheel.update(live)
            wheel["source"] = "live"
            wheel["cc_strike"] = round(cc, 2)            # CC stays the fair-value target
        p["wheel"] = wheel
