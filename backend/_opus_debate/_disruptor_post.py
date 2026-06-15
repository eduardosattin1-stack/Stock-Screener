#!/usr/bin/env python3
"""Deterministic post-processing for the DISRUPTOR apex (spec §5.2 — parameterized clone of
_value_post.py).

Validates / stamps backend/_opus_debate/disruptor/apex_basket_disruptor.json AFTER the Director and
BEFORE disruptor_csv / disruptor_publish. NEVER changes disruptor-apex membership (design principle
P1). Idempotent: re-running with --offline reuses the cached market data, so output is byte-identical.

What changed vs _value_post.py (the §5.2 table):
  - File constants parameterized to the disruptor/ subtree.
  - live_quotes / weekly_logrets / get_market / build_weights / stress_block / stamp_entry_plans /
    exits_block / stamp_stale_anchor: copied verbatim.
  - stamp_cro_only -> stamp_gate_caps: clamp size_units <= 0.5 for fcf_inflecting AND hype_flag names
    (the disruptor analogues of a CRO-only leg).
  - NEW enforce_theme_caps: <=3 names AND <=30% weight per theme from each pick's themes[]; on breach
    append {names, max_units: 30% of total units, axis:"theme:<id>"} to extra_caps + rebuild weights.
  - corr_block betas parameterized to ["SMH","QQQ"] (AI-capex/long-duration beta is this book's
    systematic risk) instead of XLY; emits theme_beta = {sym: {smh, qqq}}.
  - gate_sync DROPPED — the disruptor universe barely overlaps the regime/value books. Instead: if a
    disruptor EXCLUDE symbol also appears in the regime or value apex, print a loud warning.
  - MEMO_UNITS_20260609 one-off dropped (Director emits structured size_units from day 1 here).

Pipeline order:
    disruptor_input -> [Director writes apex_basket_disruptor.json] -> disruptor_post (THIS)
    -> disruptor_csv -> disruptor_publish

Usage:
    python _disruptor_post.py            # live: fetch quotes + 2y charts, stamp, cache
    python _disruptor_post.py --offline  # reuse cache (idempotency test)
"""
import json
import os
import sys
import math
import statistics
from datetime import datetime as _dt
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../backend/_opus_debate
BK = os.path.dirname(_HERE)                             # .../backend
sys.path.insert(0, BK)
os.chdir(BK)
if not os.environ.get("FMP_API_KEY"):                  # match _value_post.py / _funded_leverage fallback
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
from screener_v6 import fmp, get_chart                  # noqa: E402  FMP REST + OHLCV

ROOT = Path("_opus_debate")
DROOT = ROOT / "disruptor"
APEX_F = DROOT / "apex_basket_disruptor.json"
GIN_F = DROOT / "disruptor_grade_input.json"
RES_DIR = DROOT / "results"
CACHE_F = DROOT / "_disruptor_post_cache.json"
# cross-book overlap warning targets (DROP gate_sync — different universes, no demotion v1)
REGIME_F = ROOT / "apex_basket_opus_regime.json"
VALUE_F = ROOT / "apex_basket_value.json"

# theme caps (spec §4 hard constraints + §5.2 enforce_theme_caps backstop)
MAX_NAMES_PER_THEME = 3
MAX_WEIGHT_PER_THEME = 0.30


def load():
    apx = json.load(open(APEX_F, encoding="utf-8"))
    gin = {x["symbol"]: x for x in json.load(open(GIN_F, encoding="utf-8"))}
    return apx, gin


def live_quotes(symbols):
    """Batch quotes incl. yearHigh/yearLow (FMP stable batch-quote, comma symbols, chunked 50)."""
    out = {}
    for i in range(0, len(symbols), 50):
        rows = fmp("batch-quote", {"symbols": ",".join(symbols[i:i + 50])}) or []
        for q in rows:
            s = q.get("symbol")
            if s:
                out[s] = {"price": q.get("price"), "yearHigh": q.get("yearHigh"), "yearLow": q.get("yearLow")}
    return out


def weekly_logrets(chart):
    """Resample an ascending OHLCV chart to the last close of each ISO week; return {YYYY-WW: logret}."""
    byweek = {}
    for row in chart or []:
        d, c = row.get("date"), (row.get("adjClose") or row.get("close"))
        if not d or not isinstance(c, (int, float)) or c <= 0:
            continue
        try:
            y, w, _ = _dt.strptime(d[:10], "%Y-%m-%d").isocalendar()
        except Exception:
            continue
        byweek[f"{y}-{w:02d}"] = c                       # ascending chart -> last close in the week wins
    keys = sorted(byweek)
    return {keys[i]: math.log(byweek[keys[i]] / byweek[keys[i - 1]])
            for i in range(1, len(keys)) if byweek[keys[i - 1]] > 0}


def get_market(quote_syms, corr_syms, offline):
    """Fetch (or, --offline, reuse cached) live quotes + 2y weekly log-returns. Caches once for idempotency."""
    if offline and CACHE_F.exists():
        c = json.load(open(CACHE_F, encoding="utf-8"))
        return c.get("quotes", {}), c.get("weekly_rets", {}), c.get("asof", "")
    quotes = live_quotes(quote_syms)
    wr = {}
    for s in corr_syms:
        r = weekly_logrets(get_chart(s, days=760))
        if r:
            wr[s] = r
    asof = _dt.now().strftime("%Y-%m-%d")
    json.dump({"asof": asof, "quotes": quotes, "weekly_rets": wr}, open(CACHE_F, "w", encoding="utf-8"))
    return quotes, wr, asof


# ───────────────────────── §5.2 — gate caps (replaces stamp_cro_only) ─────────────────────────
def stamp_gate_caps(picks, gin):
    """Clamp size_units <= 0.5 for fcf_inflecting AND hype_flag names (the disruptor analogues of a
    CRO-only leg: an FCF that has not yet TTM-turned, or a price embedding a more aggressive S-curve
    than the evidence). Stamps the boolean flags on each pick so build_weights honors them."""
    for p in picks:
        g = gin.get(p["symbol"], {})
        # fcf_inflecting: prefer the Director's emitted flag, fall back to the grade-input gate field
        fcf_inflect = bool(p.get("fcf_inflecting", g.get("fcf_inflecting")))
        hype = bool(p.get("hype_flag"))
        p["fcf_inflecting"] = fcf_inflect
        p["hype_flag"] = hype
        p["gate_capped"] = bool(fcf_inflect or hype)


# ───────────────────────── stale-anchor (copied from _value_post) ─────────────────────────
def stamp_stale_anchor(picks, gin):
    for p in picks:
        g = gin.get(p["symbol"], {})
        fired = False
        rf = RES_DIR / f"{p['symbol']}.json"
        if rf.exists():
            try:
                cs = (json.load(open(rf, encoding="utf-8")).get("catalyst_status") or "").upper()
                fired = cs.startswith("FIRED")
            except Exception:
                fired = False
        p["stale_anchor"] = bool(g.get("freshness_stale") and (g.get("eps_peak_ratio") or 0) >= 1.8 and fired)


# ───────────────────────── weight vector (copied; gate caps replace cro_only) ─────────────────────────
def build_weights(apx, picks, extra_caps=None):
    units = {}
    for p in picks:
        u = p.get("size_units")
        if not isinstance(u, (int, float)) or not (0.1 <= u <= 1.5):
            u = 1.0                                            # Director emits structured size_units from day 1
        if p.get("fcf_inflecting"):
            u = min(u, 0.5)                                    # §5.2 gate cap
        if p.get("hype_flag"):
            u = min(u, 0.5)                                    # §5.2 gate cap
        if p.get("stale_anchor"):
            u = min(u, 0.5)
        units[p["symbol"]] = u
    for cap in list(apx.get("combined_caps") or []) + list(extra_caps or []):   # Director caps + corr/theme breaches
        names = [s for s in (cap.get("names") or []) if s in units]
        mx = cap.get("max_units")
        tot = sum(units[s] for s in names)
        if names and isinstance(mx, (int, float)) and tot > mx:
            scale = mx / tot
            for s in names:
                units[s] = round(units[s] * scale, 3)
    W = sum(units.values()) or 1.0
    weights = {s: round(u / W, 4) for s, u in units.items()}
    for p in picks:
        p["size_units_effective"] = units[p["symbol"]]
        p["weight_pct"] = round(weights[p["symbol"]] * 100, 2)
    return weights


# ───────────────────────── NEW §5.2 — theme caps (deterministic backstop) ─────────────────────────
def enforce_theme_caps(apx, picks):
    """From each pick's themes[], deterministically verify <=3 names AND <=30% weight per theme.
    On breach append {names, max_units: 30% of total units, axis:"theme:<id>"} to extra_caps and let
    build_weights rebuild — the deterministic backstop to the Director's theme-concentration promise.
    Returns the list of extra theme caps (may be empty)."""
    # current (provisional) effective units per pick
    units = {p["symbol"]: p.get("size_units_effective", p.get("size_units") or 1.0) for p in picks}
    total_units = sum(units.values()) or 1.0
    members_by_theme = {}
    for p in picks:
        for t in (p.get("themes") or []):
            members_by_theme.setdefault(t, []).append(p["symbol"])
    extra = []
    for t, names in members_by_theme.items():
        names = [s for s in names if s in units]
        if not names:
            continue
        theme_units = sum(units[s] for s in names)
        theme_w = theme_units / total_units
        cap_units = round(MAX_WEIGHT_PER_THEME * total_units, 3)
        breach_weight = theme_w > MAX_WEIGHT_PER_THEME + 1e-9
        breach_count = len(names) > MAX_NAMES_PER_THEME
        if breach_weight or breach_count:
            why = []
            if breach_count:
                why.append(f"{len(names)} names (>{MAX_NAMES_PER_THEME})")
            if breach_weight:
                why.append(f"{round(theme_w*100,1)}% weight (>{int(MAX_WEIGHT_PER_THEME*100)}%)")
            print(f"WARN theme cap: theme:{t} carries {names} — {', '.join(why)} -> combined units capped at {cap_units}")
            extra.append({"names": names, "max_units": cap_units, "axis": f"theme:{t}"})
    return extra


def derive_entry_posture(p, rec=None):
    """Deterministic fallback for entry TIMING when the Director didn't tag one (Director always wins).
    enter_now_carry can't be derived (needs the carry signal) -> scale_in (which also means 'enter now')."""
    cat = str((p.get("catalyst_status") or (rec or {}).get("catalyst_status") or "")).upper()
    if cat.startswith("PENDING_HARD") or cat.startswith("ARB"):
        return "on_confirmation"
    blob = (str(p.get("entry_plan") or "") + " "
            + " ".join(str(a) for a in (p.get("exposure_axes") or [])) + " "
            + str(p.get("lane") or "")).lower()
    if any(k in blob for k in ("knife", "demand-cycle", "cyclical", "de-gross", "degross")):
        return "wait_for_weakness"
    return "scale_in"


def stamp_entry_posture(picks):
    """Stamp entry_posture (WHEN to enter) when the Director didn't — his value always wins."""
    for p in picks:
        if not p.get("entry_posture"):
            p["entry_posture"] = derive_entry_posture(p)


def stamp_entry_plans(picks, quotes):
    """Display-only tranching guidance from distance to the 52w low (copied from _value_post)."""
    for p in picks:
        q = quotes.get(p["symbol"]) or {}
        px, lo = q.get("price"), q.get("yearLow")
        near = isinstance(px, (int, float)) and isinstance(lo, (int, float)) and lo > 0 and (px / lo - 1) < 0.05
        p["entry_plan"] = "3 tranches / 4 wks (knife: <5% above 52w low)" if near else "2 tranches / 2 wks"


def exits_block(picks, quotes):
    """Thesis-break exit levels, sanity-checked against live price (copied from _value_post)."""
    out = {}
    for p in picks:
        px = (quotes.get(p["symbol"]) or {}).get("price")
        tb = p.get("thesis_break_px")
        valid = isinstance(tb, (int, float)) and isinstance(px, (int, float)) and 0 < tb < px
        out[p["symbol"]] = {"thesis_break_px": tb if valid else None, "valid": bool(valid),
                            "review_trigger": "weekly refresh OR close < thesis_break_px"}
        if tb and not valid:
            print(f"WARN exits: {p['symbol']} thesis_break_px={tb} fails sanity vs px={px}")
    return out


# ───────────────────────── market-based stress (copied from _value_post) ─────────────────────────
def stress_block(picks, weights, quotes, asof):
    rows, w_lo, w_rec, w_bear, any_bear = [], 0.0, 0.0, 0.0, False
    for p in picks:
        s = p["symbol"]
        q = quotes.get(s) or {}
        px, lo, bear = q.get("price"), q.get("yearLow"), p.get("bear_fv_px")
        ok = isinstance(px, (int, float)) and isinstance(lo, (int, float)) and px > 0
        w = weights.get(s, 0)
        r_lo = (lo / px - 1) if ok else 0.0
        r_rec = (lo * 0.85 / px - 1) if ok else 0.0
        r_bear = (bear / px - 1) if (isinstance(px, (int, float)) and isinstance(bear, (int, float)) and px > 0) else None
        w_lo += w * r_lo
        w_rec += w * r_rec
        if r_bear is not None:
            w_bear += w * r_bear
            any_bear = True
        rows.append({"symbol": s, "price": px, "yr_low": lo,
                     "to_52w_low_pct": round(r_lo * 100, 1), "recession_pct": round(r_rec * 100, 1),
                     "cro_bear_pct": round(r_bear * 100, 1) if r_bear is not None else None})
    bear_invalid = (not any_bear) or (w_bear > 0)         # no bear FVs yet, or a "bear case" above spot
    published = w_rec if bear_invalid else min(w_rec, w_bear)
    return {"asof": asof, "basket_to_52w_lows_pct": round(w_lo * 100, 1),
            "recession_stress_pct": round(w_rec * 100, 1),
            "cro_bear_weighted_pct": round(w_bear * 100, 1) if any_bear else None,
            "bear_case_invalid": bool(bear_invalid),
            "published_downside_pct": round(published * 100, 1),
            "per_name": rows,
            "note": "Market-based stress: weighted basket return to the 52-week lows, and to 52w-lows -15% "
                    "(recession). cro_bear is the agents' own adverse SoP (bear_fv_px, theme-pause case); "
                    "when missing or implying upside it is flagged invalid and the published downside is the "
                    "market-based recession stress."}


# ───────────────────────── measured correlation (copied; benchmarks -> SMH/QQQ) ─────────────────────────
def _pearson(ra, rb):
    common = sorted(set(ra) & set(rb))
    if len(common) < 60:
        return None
    try:
        return statistics.correlation([ra[k] for k in common], [rb[k] for k in common])
    except Exception:
        return None


def _beta(rs, rm):
    if not rs or not rm:
        return None
    common = sorted(set(rs) & set(rm))
    if len(common) < 60:
        return None
    try:
        vm = statistics.variance([rm[k] for k in common])
        return statistics.covariance([rs[k] for k in common], [rm[k] for k in common]) / vm if vm > 0 else None
    except Exception:
        return None


def corr_block(syms, weekly_rets, weights, thresh=0.6, hard=0.7):
    pairs, flagged = [], []
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            c = _pearson(weekly_rets.get(a) or {}, weekly_rets.get(b) or {})
            if c is None:
                continue
            pairs.append({"a": a, "b": b, "corr": round(c, 2)})
            if c >= thresh:
                cw = weights.get(a, 0) + weights.get(b, 0)
                flagged.append({"a": a, "b": b, "corr": round(c, 2),
                                "combined_weight_pct": round(cw * 100, 1),
                                "breach": bool(c >= hard and cw > 0.16)})
    # AI-capex/long-duration beta is this book's systematic risk, not consumer (XLY): SMH + QQQ.
    smh = weekly_rets.get("SMH")
    qqq = weekly_rets.get("QQQ")
    theme_beta = {}
    for s in syms:
        bs = _beta(weekly_rets.get(s), smh)
        bq = _beta(weekly_rets.get(s), qqq)
        if bs is not None or bq is not None:
            theme_beta[s] = {"smh": round(bs, 2) if bs is not None else None,
                             "qqq": round(bq, 2) if bq is not None else None}
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    return {"window": "2y weekly log returns", "avg_pairwise": avg, "n_pairs": len(pairs),
            "max_pair": max(pairs, key=lambda p: p["corr"]) if pairs else None,
            "flagged_pairs": flagged, "theme_beta": theme_beta,
            "correlation_breach": any(f.get("breach") for f in flagged),
            "fx_note": "betas vs SMH (semis) + QQQ (long-duration tech) — the AI-capex/rate-duration systematic axes."}


# ───────────────────────── cross-book overlap warning (gate_sync DROPPED, §5.2) ─────────────────────────
def cross_book_overlap_warn(picks, gin):
    """gate_sync is DROPPED for the disruptor book — the universe barely overlaps the regime/value
    books, so cross-book demotion across different universes is out of scope v1. Instead: if a
    disruptor EXCLUDE symbol ALSO appears in the regime or value apex, print a loud operator warning."""
    excluded = {p["symbol"] for p in picks if (gin.get(p["symbol"], {}) or {}).get("forensic_gate") == "EXCLUDE"}
    # an EXCLUDE name should not be in the disruptor apex either, but check the broader grade-input set too
    excluded |= {x["symbol"] for x in gin.values() if (x or {}).get("forensic_gate") == "EXCLUDE"}
    if not excluded:
        return
    for other_f, label in ((REGIME_F, "REGIME"), (VALUE_F, "VALUE")):
        if not other_f.exists():
            continue
        try:
            oapx = json.load(open(other_f, encoding="utf-8"))
        except Exception:
            continue
        osyms = {p.get("symbol") for p in oapx.get("apex_basket", []) if isinstance(p, dict)}
        overlap = sorted(excluded & osyms)
        if overlap:
            print(f"!!! CROSS-BOOK WARNING: disruptor-EXCLUDE name(s) {overlap} ALSO sit in the {label} apex "
                  f"(different universes — no auto-demotion v1; operator should review).")


def main():
    offline = "--offline" in sys.argv
    apx, gin = load()
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    syms = [p["symbol"] for p in picks]
    quotes, weekly_rets, asof = get_market(syms, syms + ["SMH", "QQQ"], offline)
    stamp_gate_caps(picks, gin)                            # §5.2 (replaces stamp_cro_only)
    stamp_stale_anchor(picks, gin)
    w_prov = build_weights(apx, picks)                     # provisional (no corr/theme caps)
    corr = corr_block(syms, weekly_rets, w_prov)           # provisional, for breach detection
    breach_caps = [{"names": [f["a"], f["b"]], "max_units": 1.5, "axis": "correlation"}
                   for f in corr.get("flagged_pairs", []) if f.get("breach")]
    for bc in breach_caps:
        print(f"WARN correlation breach: {bc['names']} -> combined units capped at 1.5")
    # rebuild with corr breach caps, then layer theme caps measured against THOSE provisional weights
    build_weights(apx, picks, extra_caps=breach_caps)
    theme_caps = enforce_theme_caps(apx, picks)            # NEW §5.2 deterministic theme backstop
    weights = build_weights(apx, picks, extra_caps=breach_caps + theme_caps)   # final (honors all caps)
    corr = corr_block(syms, weekly_rets, weights)          # recompute combined-weight w/ final weights
    _flagged = {s for f in corr.get("flagged_pairs", []) for s in (f["a"], f["b"])}
    for p in picks:
        p["corr_flag"] = p["symbol"] in _flagged
    stamp_entry_plans(picks, quotes)
    stamp_entry_posture(picks)                            # entry TIMING (Director-tag fallback)
    # theme_exposure (final weights by theme; a 2-theme name counts toward both)
    theme_exposure = {}
    for p in picks:
        for t in (p.get("themes") or []):
            theme_exposure[t] = round(theme_exposure.get(t, 0.0) + weights.get(p["symbol"], 0) * 100, 2)
    apx["weights"] = weights
    apx["stress_test"] = stress_block(picks, weights, quotes, asof)
    apx["correlation"] = corr
    apx["exits"] = exits_block(picks, quotes)
    apx["theme_exposure"] = theme_exposure
    # theme_caps are a DERIVED backstop recomputed every run — surfaced under their own key, NEVER
    # folded into the Director's `combined_caps` (that would compound on a re-run and break --offline
    # idempotency; the spec §5.2 appends them to extra_caps in-memory, not to the persisted basket).
    apx["theme_caps"] = theme_caps
    json.dump(apx, open(APEX_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    cross_book_overlap_warn(picks, gin)                    # gate_sync DROPPED -> loud warning only
    st = apx["stress_test"]
    max_theme = max(theme_exposure.items(), key=lambda kv: kv[1]) if theme_exposure else (None, 0)
    print(f"disruptor_post: stamped {APEX_F} | weights sum={round(sum(weights.values()), 4)} "
          f"| stress 52w-low={st['basket_to_52w_lows_pct']}% recession={st['recession_stress_pct']}% "
          f"| corr avg={corr.get('avg_pairwise')} pairs={corr.get('n_pairs')} "
          f"breaches={sum(1 for f in corr.get('flagged_pairs', []) if f.get('breach'))} "
          f"| top theme {max_theme[0]}={max_theme[1]}% (cap {int(MAX_WEIGHT_PER_THEME*100)}%) "
          f"| gate_capped={[p['symbol'] for p in picks if p.get('gate_capped')]} "
          f"stale={[p['symbol'] for p in picks if p.get('stale_anchor')]}")


if __name__ == "__main__":
    main()
