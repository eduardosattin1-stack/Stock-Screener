#!/usr/bin/env python3
"""Deterministic post-processing for the VALUE apex (audit fixes 1-5,7, 2026-06-09).

Validates / stamps backend/_opus_debate/apex_basket_value.json AFTER the Director and
BEFORE value_csv / value_publish. NEVER changes value-apex membership (design principle P1;
the sole exception is gate_sync, which may demote a globally-EXCLUDEd name on the REGIME side).
Idempotent: re-running with --offline reuses the cached market data, so output is byte-identical.

Pipeline order:
    value_input -> [Director writes apex_basket_value.json] -> value_post (THIS) -> value_csv -> value_publish

Usage:
    python _value_post.py            # live: fetch quotes + 2y charts, stamp, cache
    python _value_post.py --offline  # reuse cache (idempotency test)
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
if not os.environ.get("FMP_API_KEY"):                  # match fmp_facts.py / _funded_leverage fallback
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
from screener_v6 import fmp, get_chart                  # noqa: E402  FMP REST + OHLCV

ROOT = Path("_opus_debate")
APEX_F = ROOT / "apex_basket_value.json"
GIN_F = ROOT / "value_grade_input.json"
RES_DIR = ROOT / "results_regime"
REGIME_F = ROOT / "apex_basket_opus_regime.json"
CACHE_F = ROOT / "_value_post_cache.json"

# One-off migration: until the Director emits structured `size_units`, reproduce the 2026-06-09
# memo sizing (SAX.DE half on advertising-cycle; ANF/BKNG 3/4 on the discretionary cap).
# DELETE this map after the first post-fix Director run writes real size_units.
MEMO_UNITS_20260609 = {"SAX.DE": 0.5, "ANF": 0.75, "BKNG": 0.75}


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


# ───────────────────────── Fix 2 — CRO-only legs ─────────────────────────
def stamp_cro_only(picks, gin):
    for p in picks:
        g = gin.get(p["symbol"], {})
        ms = g.get("mos_spread") or {}
        n_pos = sum(1 for v in ms.values() if isinstance(v, (int, float)) and v > 0)
        scan = g.get("scan_headline_mos_pct")
        p["mos_agreement_n"] = n_pos
        p["cro_only"] = bool(n_pos <= 2 and (not isinstance(scan, (int, float)) or scan < 10))


# ───────────────────────── Fix 3 — stale-anchor (deterministic half) ─────────────────────────
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


# ───────────────────────── Fix 5 — weight vector ─────────────────────────
def build_weights(apx, picks, extra_caps=None):
    units = {}
    for p in picks:
        u = p.get("size_units")
        if not isinstance(u, (int, float)) or not (0.1 <= u <= 1.5):
            u = MEMO_UNITS_20260609.get(p["symbol"], 1.0)     # one-off fallback until Director emits sizing
        if p.get("cro_only"):
            u = min(u, 0.5)                                    # fix 2
        if p.get("stale_anchor"):
            u = min(u, 0.5)                                    # fix 3
        units[p["symbol"]] = u
    for cap in list(apx.get("combined_caps") or []) + list(extra_caps or []):   # Director caps + corr breaches
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


def stamp_entry_plans(picks, quotes):
    """Fix 5c — display-only tranching guidance from distance to the 52w low."""
    for p in picks:
        q = quotes.get(p["symbol"]) or {}
        px, lo = q.get("price"), q.get("yearLow")
        near = isinstance(px, (int, float)) and isinstance(lo, (int, float)) and lo > 0 and (px / lo - 1) < 0.05
        p["entry_plan"] = "3 tranches / 4 wks (knife: <5% above 52w low)" if near else "2 tranches / 2 wks"


def exits_block(picks, quotes):
    """Fix 5d — thesis-break exit levels, sanity-checked against live price."""
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


# ───────────────────────── Fix 1 — market-based stress ─────────────────────────
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
                    "(recession). cro_bear is the agents' own adverse SoP (bear_fv_px); when missing or "
                    "implying upside it is flagged invalid and the published downside is the market-based "
                    "recession stress."}


# ───────────────────────── Fix 4 — measured correlation ─────────────────────────
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
    mkt = weekly_rets.get("XLY")
    betas = {}
    for s in syms:
        b = _beta(weekly_rets.get(s), mkt)
        if b is not None:
            betas[s] = round(b, 2)
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    return {"window": "2y weekly log returns", "avg_pairwise": avg, "n_pairs": len(pairs),
            "max_pair": max(pairs, key=lambda p: p["corr"]) if pairs else None,
            "flagged_pairs": flagged, "consumer_beta_xly": betas,
            "correlation_breach": any(f.get("breach") for f in flagged),
            "fx_note": "EU names in local ccy; correlations unadjusted for FX."}


# ───────────────────────── Fix 7 — cross-surface forensic gate sync ─────────────────────────
def gate_sync(gin):
    """EXCLUDE is a global forensic veto -> strip from the REGIME apex too (the ONE P1 exception).
    CAP may sit in the regime apex but must carry a visible forensic_cap flag. Idempotent."""
    if not REGIME_F.exists():
        return
    try:
        rapx = json.load(open(REGIME_F, encoding="utf-8"))
    except Exception:
        return
    keep, demoted = [], []
    for p in rapx.get("apex_basket", []):
        g = (gin.get(p.get("symbol"), {}) or {}).get("forensic_gate", "")
        if g == "EXCLUDE":
            p["gate_demotion"] = "EXCLUDE: interrogator credibility <=2 (global forensic veto)"
            demoted.append(p)
        else:
            p["forensic_cap"] = (g == "CAP")
            keep.append(p)
    rapx["apex_basket"] = keep
    if demoted:
        dsyms = {d.get("symbol") for d in demoted}
        prior = [r for r in (rapx.get("runner_ups") or [])
                 if (r.get("symbol") if isinstance(r, dict) else r) not in dsyms]
        rapx["runner_ups"] = demoted + prior
    json.dump(rapx, open(REGIME_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if demoted:
        print(f"gate_sync: demoted {[p.get('symbol') for p in demoted]} from regime apex (EXCLUDE)")
    caps = [p.get("symbol") for p in keep if p.get("forensic_cap")]
    if caps:
        print(f"gate_sync: regime apex CAP-flagged (allowed, visible): {caps}")


def main():
    offline = "--offline" in sys.argv
    apx, gin = load()
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    syms = [p["symbol"] for p in picks]
    quotes, weekly_rets, asof = get_market(syms, syms + ["XLY"], offline)
    stamp_cro_only(picks, gin)                              # fix 2
    stamp_stale_anchor(picks, gin)                          # fix 3
    w_prov = build_weights(apx, picks)                      # provisional (no corr caps)
    corr = corr_block(syms, weekly_rets, w_prov)            # fix 4 (provisional, for breach detection)
    breach_caps = [{"names": [f["a"], f["b"]], "max_units": 1.5, "axis": "correlation"}
                   for f in corr.get("flagged_pairs", []) if f.get("breach")]
    for bc in breach_caps:
        print(f"WARN correlation breach: {bc['names']} -> combined units capped at 1.5")
    weights = build_weights(apx, picks, extra_caps=breach_caps)   # fix 5 (final, honors breaches)
    corr = corr_block(syms, weekly_rets, weights)                 # recompute combined-weight w/ final weights
    _flagged = {s for f in corr.get("flagged_pairs", []) for s in (f["a"], f["b"])}
    for p in picks:
        p["corr_flag"] = p["symbol"] in _flagged                # fix 4: member of any >=0.6 pair
    stamp_entry_plans(picks, quotes)                             # fix 5c
    apx["weights"] = weights
    apx["stress_test"] = stress_block(picks, weights, quotes, asof)   # fix 1
    apx["correlation"] = corr                                         # fix 4
    apx["exits"] = exits_block(picks, quotes)                         # fix 5d
    json.dump(apx, open(APEX_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    gate_sync(gin)                                                   # fix 7 (regime side; separate file)
    st = apx["stress_test"]
    print(f"value_post: stamped {APEX_F} | weights sum={round(sum(weights.values()), 4)} "
          f"| stress 52w-low={st['basket_to_52w_lows_pct']}% recession={st['recession_stress_pct']}% "
          f"| corr avg={corr.get('avg_pairwise')} pairs={corr.get('n_pairs')} "
          f"breaches={sum(1 for f in corr.get('flagged_pairs', []) if f.get('breach'))} "
          f"| cro_only={[p['symbol'] for p in picks if p.get('cro_only')]} "
          f"stale={[p['symbol'] for p in picks if p.get('stale_anchor')]}")


if __name__ == "__main__":
    main()
