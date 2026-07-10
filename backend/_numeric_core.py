#!/usr/bin/env python3
"""_numeric_core.py — shared deterministic valuation-arithmetic primitives (2026-07-10 extraction).

Pure functions extracted from `_post_board.py` (the Catalyst Watch / Loeb board post-processor),
which built the only proven, battle-tested R:R / SoP-integrity / thin-floor machinery in the repo.
`_post_board.py` had it; the weekly Speculair debate pipeline (apex/value/B13 books) did not — the
2026-07 forensics (HNR1.DE's asserted "2:1 reward-to-risk" contradicting its own sop_bear; KBR's
"live_price: null"; AAUC's "price_currency: null" on a dual-listing) all trace to that gap. This
module is the shared home so both consumers use ONE arithmetic implementation.

Extraction discipline: every function here is a byte-for-byte behavioral copy of its
`_post_board.py` original (verified via `python backend/_post_board.py <board> --report` producing
identical output before/after `_post_board.py` was pointed at these wrappers). `fetch_live_quotes`
is parameterized on `fmp_key`/`fmp_base` (the original hardcoded a fallback demo key as a module
constant in `_post_board.py`; that constant stays THERE — this module never hardcodes a key) so
other callers (weekly_opus_refresh.py, the future numeric-gate) can supply their own key-loading.

New (not extracted, added 2026-07-10): `implied_currency()` — an exchange-suffix -> currency map,
needed by the numeric gate's dual-listing check (the AAUC incident: a CAD/USD mismatch on a .TO
name). `compute_ratios()` (stamping the typed `valuation` block once it exists) is deliberately
deferred to when the numeric-gate ships alongside real fixtures to test it against.
"""
from __future__ import annotations
import requests

# ── R:R lane methods ─────────────────────────────────────────────────────────────────────────────
RATIO_METHODS = ("sop", "recovery", "capital_return")


def _vf(row, key):
    v = row.get(key)
    try:
        import pandas as pd
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
    except ImportError:
        if v is None:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def rr_ratio_lane(method, live, f):
    """Deterministic lane-aware R:R vs the fresh `live` price. f = dossier fields (dict).
    Returns: float (clean ratio), dict (binary barbell), ('TINY', rr) (rr but <5% downside),
    ('FLAG', reason) (edge L, stays on board), ('DROP', reason) (tier->NONE), or None (un-computable)."""
    if method in RATIO_METHODS:
        tgt, flr = _vf(f, "fair_value_target"), _vf(f, "downside_floor")
        if tgt is None or flr is None: return None
        up, dn = tgt - live, live - flr
        if up <= 0: return ("FLAG", "NO_UPSIDE")        # target<=live: catalyst already played out
        if dn <= 0: return ("FLAG", "FLOOR_GE_LIVE")    # floor>=live: no/inverted downside
        return up / dn                                  # thin-floor handled in the overlay (needs dn)
    if method == "spread":
        dp, un = _vf(f, "deal_price"), _vf(f, "undisturbed_price")
        if dp is None or un is None: return None
        up, dn = dp - live, live - un
        if up <= 0: return ("DROP", "TRADING_THROUGH_TERMS")   # negative spread
        if dn <= 0: return ("FLAG", "NO_BREAK_DOWNSIDE")
        return up / dn
    if method == "binary_prob":                                # barbell, NOT a single ratio
        p, tw, dl = _vf(f, "win_prob"), _vf(f, "target_on_win"), _vf(f, "downside_on_loss")
        if p is None or tw is None or dl is None: return None
        ev = p * (tw - live) + (1 - p) * (dl - live)
        payoff = (tw - live) / max(live - dl, 1e-9)
        return {"ev_pct": ev / live, "win_prob": p, "payoff": payoff,
                "up_leg": tw - live, "down_leg": live - dl}
    return None


def grade_from_measure(method, res):
    """edge_grade from the computed measure (calibratable starting thresholds)."""
    if method == "binary_prob" and isinstance(res, dict):
        if res["ev_pct"] >= 0.15 and res["payoff"] >= 2: return "H"
        return "M" if res["ev_pct"] > 0 else "L"
    if isinstance(res, (int, float)):
        if res >= 2.5: return "H"
        if res >= 1.5: return "M"
        return "L"
    return "?"


# ── SoP build integrity ──────────────────────────────────────────────────────────────────────────
MULT_BAND = {"EBITDA": (4, 25), "sales": (0.5, 12)}   # plausible EV/x bands; outliers flagged


def _n(x):
    try:
        v = float(x)
        return None if v != v else v   # drop NaN
    except (TypeError, ValueError):
        return None


def sop_integrity(v, live, tol=0.05):
    """Deterministic backstop (sop lanes only). Recompute the build from the components and run the
    integrity checks that catch this run's failures MECHANICALLY: units chaos, per-row arithmetic,
    out-of-band multiples, advocacy/premium stacked on the build, and absurd per-share values.
    Returns (built_per_share|None, flags[list], quarantine_bool). R:R is ALWAYS driven off `built`;
    a quarantined name shows NO number (its inputs are broken)."""
    flags = []
    comps = v.get("sop_components") or []
    so = _n(v.get("shares_out"))
    if not comps or not so:
        return (None, flags, False)
    nd = _n(v.get("net_debt")) or 0.0
    adj = _n(v.get("adjustments")) or 0.0
    tgt = _n(v.get("fair_value_target"))
    # per-row arithmetic + multiple bands  (ev == metric x multiple, or metric x ownership for stakes)
    for c in comps:
        m = c.get("driver_metric"); mv = _n(c.get("metric_value")); ev = _n(c.get("ev_contribution"))
        mult = _n(c.get("multiple")); own = _n(c.get("ownership"))
        seg = str(c.get("segment", ""))[:18]
        if mv is not None and ev is not None:
            factor = own if (m == "stake_mv" and own is not None) else (mult if mult is not None else 1.0)
            expect = mv * factor
            if abs(expect) > 1e-9 and abs(expect - ev) / abs(expect) > 0.01:
                flags.append("ROW_EV_MISMATCH:" + seg)
        if m in MULT_BAND and mult is not None and not (MULT_BAND[m][0] <= mult <= MULT_BAND[m][1]):
            flags.append("MULTIPLE_OUT_OF_BAND:%s(%gx)" % (seg, mult))
    try:
        built = (sum(_n(c.get("ev_contribution")) or 0.0 for c in comps) - nd - adj) / so
    except ZeroDivisionError:
        return (None, flags, True)
    # units: declared+sane is clean; declared-insane or implausible build -> quarantine
    u = v.get("units") or {}
    units_ok = u.get("shares") == "millions" and u.get("money") == "usd_millions"
    if not units_ok:
        flags.append("UNITS_UNDECLARED")
    # implausible per-share build = the unit-chaos signature (INIO -$2M/sh, B/BN built ~0 vs a real target)
    absurd = (built < 0 or (live and abs(built) > 50 * live)
              or (tgt and abs(tgt) > 1 and abs(built) < 0.1 * abs(tgt)))
    quarantine = any(f.startswith("ROW_EV_MISMATCH") for f in flags) or absurd
    if absurd:
        flags.append("ABSURD_BUILD")
    # reconcile asserted target to the build (MAT's $24-vs-$30 advocacy gap)
    if tgt and built and abs(built - tgt) / abs(built) > tol:
        flags.append("SOP_TARGET_MISMATCH")
    return (built, flags, quarantine)


# ── Thin/tiny-floor thresholds (was inline 0.15/0.05 literals in _post_board.py's process()) ─────
# A ratio resting on too little downside is not a confident H — the MAT-class trap: a chart-low
# floor manufactures a thin denominator and inflates the ratio. THIS is the exact defect class the
# HNR1.DE "2:1 reward-to-risk" (a ~6.4%-away "floor") fell into in the weekly Speculair debate.
THIN_FLOOR_PCT = 0.15   # downside-to-floor below this fraction of live price -> THIN_FLOOR
TINY_FLOOR_PCT = 0.05   # below this fraction -> TINY_FLOOR (the tighter, more severe flag)


# ── Live quotes ───────────────────────────────────────────────────────────────────────────────────
DEFAULT_FMP_BASE = "https://financialmodelingprep.com/stable"


def fetch_live_quotes(symbols, batch=80, fmp_key=None, fmp_base=DEFAULT_FMP_BASE):
    """Fresh FMP REST batch quotes -> {SYMBOL: price}. {} on failure (caller flags stale).
    Caller supplies fmp_key (this module never hardcodes one)."""
    out = {}
    if not fmp_key:
        return out
    syms = sorted({str(x).upper() for x in symbols if x and isinstance(x, str)})
    for i in range(0, len(syms), batch):
        try:
            r = requests.get(f"{fmp_base}/batch-quote",
                             params={"symbols": ",".join(syms[i:i + batch]), "apikey": fmp_key}, timeout=25)
            for q in (r.json() or []):
                if q.get("symbol") and q.get("price") is not None:
                    out[str(q["symbol"]).upper()] = float(q["price"])
        except Exception:
            continue
    return out


# ── Currency implied by exchange suffix (new 2026-07-10 — the numeric gate's dual-listing check) ──
# The AAUC incident: a .TO (CAD) name's regime record had price_currency:null and the agent
# fabricated a price "near the C$44 offer" — nothing checked the currency implied by the symbol
# against what the agent stated. Not exhaustive; extend as new dual-listed names show up.
EXCHANGE_CURRENCY = {
    ".DE": "EUR", ".PA": "EUR", ".MI": "EUR", ".AS": "EUR", ".MC": "EUR", ".HE": "EUR",
    ".BR": "EUR", ".LS": "EUR", ".VI": "EUR", ".IR": "EUR",
    ".L": "GBp",          # LSE quotes in pence, not pounds — a frequent x100 trap
    ".SW": "CHF",
    ".T": "JPY",
    ".HK": "HKD",
    ".TO": "CAD", ".V": "CAD",
    ".CO": "DKK", ".OL": "NOK", ".ST": "SEK",
    ".AX": "AUD",
    ".SI": "SGD",
    ".KS": "KRW",
    ".SA": "BRL",
    ".MX": "MXN",
    ".NS": "INR", ".BO": "INR",
}


def implied_currency(symbol: str) -> str:
    """Currency implied by an exchange-suffixed ticker (e.g. 'AAUC.TO' -> 'CAD'). Defaults to USD
    for bare US tickers or any suffix not in the map (never raises)."""
    if not symbol:
        return "USD"
    s = str(symbol).upper()
    for suffix, ccy in EXCHANGE_CURRENCY.items():
        if s.endswith(suffix):
            return ccy
    return "USD"
