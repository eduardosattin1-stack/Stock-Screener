#!/usr/bin/env python3
"""Deterministic post-processing for the FUTURE RESOURCES apex (FUTURE_RESOURCES_SPEC.md §5 —
parameterized clone of _disruptor_post.py, which is itself the §5.2 clone of _value_post.py).

Validates / stamps backend/_opus_debate/future_resources/apex_basket_fr.json AFTER the Director and
BEFORE fr_csv / fr_publish. NEVER changes apex membership (design principle P1; the sole sanctioned
membership change is the shared skeptic consumption — REFUTED demotes to runner_ups). Idempotent:
re-running with --offline reuses the cached market data, so output is byte-identical.

What changed vs _disruptor_post.py:
  - File constants parameterized to the future_resources/ subtree; skeptic shards _skeptic_fr.
  - stamp_gate_caps -> FR gate caps: HEADWIND-chain names (regime_state.json) clamp to <= 0.5 unless
    the Director wrote a non-empty headwind_justification (the spec §5 rule, deterministically
    backstopped); growth_capex_fcf_negative names clamp to <= 0.75; the torque x leverage blow-up
    quadrant (fcf_torque_10pct >= 40 AND net_funded_debt_ebitda >= 2.5) clamps to <= 0.75 with a
    printed warning. hype_flag kept from the disruptor (price embedding a steeper story than the
    evidence); fcf_inflecting dropped (not an FR gate — Lane A requires cash TODAY).
  - enforce_theme_caps -> enforce_chain_caps over each pick's chains[] (<=3 names, <=30% weight).
  - corr_block benchmarks -> ["XME", "URA"] (physical-resources beta is this book's systematic risk,
    not AI-capex); emits chain_beta = {sym: {xme, ura}}.
  - cross_book_overlap_warn kept verbatim (regime/value apexes; warning only, no demotion).

Pipeline order:
    fr_input -> [Director writes apex_basket_fr.json] -> fr_post (THIS) -> fr_csv -> fr_publish

Usage:
    python _fr_post.py            # live: fetch quotes + 2y charts, stamp, cache
    python _fr_post.py --offline  # reuse cache (idempotency test)
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
if not os.environ.get("FMP_API_KEY"):                  # match _disruptor_post.py / _funded_leverage fallback
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
from screener_v6 import fmp, get_chart                  # noqa: E402  FMP REST + OHLCV
sys.path.insert(0, _HERE)                              # so the sibling _wheel module resolves
from _wheel import stamp_wheel                          # noqa: E402  CSP->CC wheel suggestion

ROOT = Path("_opus_debate")
FROOT = ROOT / "future_resources"
APEX_F = FROOT / "apex_basket_fr.json"
GIN_F = FROOT / "fr_grade_input.json"
RES_DIR = FROOT / "results"
CACHE_F = FROOT / "_fr_post_cache.json"
REGIME_STATE_F = FROOT / "regime_state.json"
# cross-book overlap warning targets (no gate_sync — different universes, warning only)
REGIME_F = ROOT / "apex_basket_opus_regime.json"
VALUE_F = ROOT / "apex_basket_value.json"

# chain caps (spec §5 hard constraints; deterministic backstop to the Director's promise)
MAX_NAMES_PER_CHAIN = 3
MAX_WEIGHT_PER_CHAIN = 0.30
# torque x leverage blow-up quadrant (spec §3/§5): high commodity torque on a levered balance sheet
TORQUE_QUADRANT_TORQUE = 40.0     # fcf_torque_10pct >= this (a 10% commodity move swings EBITDA >= 40%)
TORQUE_QUADRANT_LEVERAGE = 2.5    # net_funded_debt_ebitda >= this


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


# ───────────────────────── FR gate caps (replaces the disruptor's stamp_gate_caps) ─────────────────────────
def stamp_gate_caps(picks, gin):
    """FR sizing gates, spec §5 — Director's judgement wins where the spec lets it, the backstop is
    deterministic where it doesn't:
      - HEADWIND chain (regime_state.json): size_units <= 0.5 UNLESS the pick carries a non-empty
        headwind_justification (the spec's 'or written justification' escape — justified keeps its
        size but is stamped headwind_flag for the card).
      - growth_capex_fcf_negative (OCF-positive / FCF-negative build-cycle producer): <= 0.75.
      - torque x leverage blow-up quadrant: <= 0.75 with a printed warning.
      - hype_flag (Director-emitted): <= 0.5 (kept from the disruptor)."""
    regime = {}
    if REGIME_STATE_F.exists():
        try:
            regime = json.load(open(REGIME_STATE_F, encoding="utf-8"))
        except Exception:
            regime = {}
    if not regime:
        # fail LOUD, not open: without the regime read the HEADWIND backstop is disabled for the run
        print("WARN regime cap: regime_state.json missing/unreadable — the HEADWIND size backstop is "
              "DISABLED this run (refresh FUTURE_RESOURCES_REGIME.md per its protocol)")
    for p in picks:
        g = gin.get(p["symbol"], {})
        chains = p.get("chains") or g.get("chains") or []
        # PRIMARY-chain scope — the same contract the Director operates under (FR_DIRECTOR_PROMPT
        # gates on the PRIMARY chain; fr_grade_input's chain_regime is primary-only). An any-chain
        # cap would silently halve a 2-chain pick the Director sized correctly (and was told to
        # leave headwind_justification empty for). Secondary-chain headwinds are surfaced as a
        # non-capping flag for the card.
        prim = p.get("chain") or (chains[0] if chains else None)
        headwind = (regime.get(prim) or {}).get("state") == "HEADWIND"
        any_headwind = any((regime.get(c) or {}).get("state") == "HEADWIND" for c in chains)
        justified = bool(str(p.get("headwind_justification") or "").strip())
        p["headwind_flag"] = bool(any_headwind)
        p["headwind_capped"] = bool(headwind and not justified)
        if headwind and not justified:
            print(f"WARN regime cap: {p['symbol']} primary chain {prim} is HEADWIND with no written "
                  f"justification -> size_units clamped to 0.5")
        p["growth_capex_fcf_negative"] = bool(p.get("growth_capex_fcf_negative",
                                                    g.get("growth_capex_fcf_negative")))
        tq = g.get("fcf_torque_10pct")
        nd = g.get("net_funded_debt_ebitda")
        quadrant = (isinstance(tq, (int, float)) and tq >= TORQUE_QUADRANT_TORQUE
                    and isinstance(nd, (int, float)) and nd >= TORQUE_QUADRANT_LEVERAGE)
        if quadrant:
            print(f"WARN torque-quadrant: {p['symbol']} torque={tq}% x leverage={nd}x -> size_units clamped to 0.75")
        p["torque_quadrant"] = bool(quadrant)
        p["hype_flag"] = bool(p.get("hype_flag"))
        p["gate_capped"] = bool(p["headwind_capped"] or p["growth_capex_fcf_negative"]
                                or quadrant or p["hype_flag"])


# ───────────────────────── stale-anchor (copied from _disruptor_post) ─────────────────────────
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


# ───────────────────────── weight vector (copied; FR gate caps wired in) ─────────────────────────
def build_weights(apx, picks, extra_caps=None):
    units = {}
    for p in picks:
        u = p.get("size_units")
        if not isinstance(u, (int, float)) or not (0.1 <= u <= 1.5):
            u = 1.0
        if p.get("skeptic_missing") or p.get("skeptic_stale_refuted"):
            u = min(u, 0.5)                                    # skeptic-coverage teeth: un-vetted seat
        if p.get("correction_severity") == "material":
            u = min(u, 0.75)                                   # bounded haircut on a material correction
        if p.get("headwind_capped"):
            u = min(u, 0.5)                                    # HEADWIND chain, no justification
        if p.get("hype_flag"):
            u = min(u, 0.5)
        if p.get("growth_capex_fcf_negative"):
            u = min(u, 0.75)                                   # build-cycle producer (spec §1.2)
        if p.get("torque_quadrant"):
            u = min(u, 0.75)                                   # torque x leverage blow-up quadrant
        if p.get("stale_anchor"):
            u = min(u, 0.5)
        units[p["symbol"]] = u
    for cap in list(apx.get("combined_caps") or []) + list(extra_caps or []):   # Director caps + corr/chain breaches
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


# ───────────────────────── chain caps (deterministic backstop, clone of enforce_theme_caps) ─────────────────────────
def _pick_chains(p, gin):
    """A pick's chains, with the grade-input fallback — the Director dropping the field is exactly
    the misbehavior the deterministic backstop exists to catch, so the backstop must see it."""
    return p.get("chains") or ((gin.get(p.get("symbol"), {}) or {}).get("chains")) or []


def _chain_breaches(picks, gin, tol=1e-9):
    """Detect chains breaching <=MAX_NAMES / <=MAX_WEIGHT on the CURRENT effective units.
    Returns ({chain: {names, share, n}}, units, total). Detection only — no prints, no caps."""
    units = {p["symbol"]: p.get("size_units_effective", p.get("size_units") or 1.0) for p in picks}
    total = sum(units.values()) or 1.0
    members_by_chain = {}
    for p in picks:
        for c in _pick_chains(p, gin):
            members_by_chain.setdefault(c, []).append(p["symbol"])
    out = {}
    for c, names in members_by_chain.items():
        names = [s for s in names if s in units]
        if not names:
            continue
        cu = sum(units[s] for s in names)
        if cu / total > MAX_WEIGHT_PER_CHAIN + tol or len(names) > MAX_NAMES_PER_CHAIN:
            out[c] = {"names": names, "share": cu / total, "n": len(names)}
    return out, units, total


def enforce_chain_caps(apx, picks, gin):
    """Deterministic backstop to the Director's chain-concentration promise (<=3 names AND <=30%
    weight per chain; a 2-chain name counts toward BOTH). Solves all breaching chains JOINTLY:
    with k breaching chains, every capped chain lands at exactly MAX_W post-normalization when
        cap_i = MAX_W * outside_units / (1 - k*MAX_W)
    where outside_units = units of picks in NO breaching chain (exact for disjoint chains; the
    caller re-checks once for the overlapping case). Independently-solved caps under-tighten —
    each treats the other breaching chain as 'outside' — leaving both above 30% after rebuild.
    Genuinely infeasible geometry (k*MAX_W >= 1, or zero outside units) is WARNED, never capped:
    a cap of 0 would zero-collapse every weight in the book."""
    breaching, units, total = _chain_breaches(picks, gin)
    if not breaching:
        return []
    k = len(breaching)
    in_breach = {s for b in breaching.values() for s in b["names"]}
    outside_units = sum(u for s, u in units.items() if s not in in_breach)
    denom = 1 - k * MAX_WEIGHT_PER_CHAIN
    if denom <= 1e-9 or outside_units <= 1e-9:
        print(f"WARN chain cap: {k} chain(s) breach {sorted(breaching)} but the geometry makes "
              f"<={int(MAX_WEIGHT_PER_CHAIN*100)}%-per-chain INFEASIBLE (k*cap >= 100%, or no "
              f"outside names) — NOT capped (a zero cap would collapse the book); operator review")
        return []
    extra = []
    for c, b in sorted(breaching.items()):
        cap_units = round(MAX_WEIGHT_PER_CHAIN * outside_units / denom, 3)
        why = []
        if b["n"] > MAX_NAMES_PER_CHAIN:
            why.append(f"{b['n']} names (>{MAX_NAMES_PER_CHAIN})")
        if b["share"] > MAX_WEIGHT_PER_CHAIN + 1e-9:
            why.append(f"{round(b['share']*100,1)}% weight (>{int(MAX_WEIGHT_PER_CHAIN*100)}%)")
        print(f"WARN chain cap: chain:{c} carries {b['names']} — {', '.join(why)} -> combined units "
              f"capped at {cap_units} (joint solve, k={k})")
        extra.append({"names": b["names"], "max_units": cap_units, "axis": f"chain:{c}"})
    return extra


def derive_entry_posture(p, rec=None):
    """Deterministic fallback for entry TIMING when the Director didn't tag one (Director always wins)."""
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


# ───────────────────────── market-based stress (copied from _disruptor_post) ─────────────────────────
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
    bear_invalid = (not any_bear) or (w_bear > 0)
    published = w_rec if bear_invalid else min(w_rec, w_bear)
    return {"asof": asof, "basket_to_52w_lows_pct": round(w_lo * 100, 1),
            "recession_stress_pct": round(w_rec * 100, 1),
            "cro_bear_weighted_pct": round(w_bear * 100, 1) if any_bear else None,
            "bear_case_invalid": bool(bear_invalid),
            "published_downside_pct": round(published * 100, 1),
            "per_name": rows,
            "note": "Market-based stress: weighted basket return to the 52-week lows, and to 52w-lows -15% "
                    "(recession). cro_bear is the agents' own adverse SoP (bear_fv_px, commodity-downcycle "
                    "case); when missing or implying upside it is flagged invalid and the published downside "
                    "is the market-based recession stress."}


# ───────────────────────── measured correlation (copied; benchmarks -> XME/URA) ─────────────────────────
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
    # physical-resources beta is this book's systematic risk (not AI-capex): XME (metals & mining)
    # + URA (uranium) — the "global growth + China demand" shared axis in measurable form.
    xme = weekly_rets.get("XME")
    ura = weekly_rets.get("URA")
    chain_beta = {}
    for s in syms:
        bx = _beta(weekly_rets.get(s), xme)
        bu = _beta(weekly_rets.get(s), ura)
        if bx is not None or bu is not None:
            chain_beta[s] = {"xme": round(bx, 2) if bx is not None else None,
                             "ura": round(bu, 2) if bu is not None else None}
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    return {"window": "2y weekly log returns", "avg_pairwise": avg, "n_pairs": len(pairs),
            "max_pair": max(pairs, key=lambda p: p["corr"]) if pairs else None,
            "flagged_pairs": flagged, "chain_beta": chain_beta,
            "correlation_breach": any(f.get("breach") for f in flagged),
            "fx_note": "betas vs XME (metals & mining) + URA (uranium) — the physical-resources "
                       "systematic axes (global growth + China demand)."}


# ───────────────────────── cross-book overlap warning (copied from _disruptor_post) ─────────────────────────
def cross_book_overlap_warn(picks, gin):
    """No gate_sync for the FR book — the universe barely overlaps the regime/value books. If an
    FR EXCLUDE symbol ALSO appears in the regime or value apex, print a loud operator warning."""
    excluded = {p["symbol"] for p in picks if (gin.get(p["symbol"], {}) or {}).get("forensic_gate") == "EXCLUDE"}
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
            print(f"!!! CROSS-BOOK WARNING: FR-EXCLUDE name(s) {overlap} ALSO sit in the {label} apex "
                  f"(different universes — no auto-demotion; operator should review).")


def main():
    offline = "--offline" in sys.argv
    # consume_skeptic judges shard freshness against the APEX FILE's mtime (shards must postdate the
    # Director's write). The post itself rewrites the apex — without preserving the mtime, a RE-RUN
    # of the post (the routine's own guard says "re-run once" after a failed push) would see every
    # shard as stale and silently half-size the whole book as MISSING. Preserve the Director's write
    # time as the epoch of record across post rewrites.
    apex_mtime_before = APEX_F.stat().st_mtime if APEX_F.exists() else None
    apx, gin = load()
    # UNIFIED SKEPTIC consumption: the FR book ships WITH its kill-tier from day 1 (the disruptor
    # got its skeptic late, 2026-07-01, precisely because the highest-vol book lacked one) — REFUTED
    # demotes to runner_ups; MISSING/stale-REFUTED seats are stamped + half-sized; a material
    # correction takes the bounded haircut (all via the shared _post_common machinery).
    try:
        import _post_common as _pc
        apx = _pc.consume_skeptic(apx, APEX_F, Path(__file__).resolve().parent / "_skeptic_fr")
    except Exception as _e:
        print(f"WARN: fr skeptic consumption failed ({_e}) — proceeding un-vetted (stamps will say MISSING)")
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    syms = [p["symbol"] for p in picks]
    quotes, weekly_rets, asof = get_market(syms, syms + ["XME", "URA"], offline)
    stamp_gate_caps(picks, gin)
    stamp_stale_anchor(picks, gin)
    w_prov = build_weights(apx, picks)                     # provisional (no corr/chain caps)
    corr = corr_block(syms, weekly_rets, w_prov)           # provisional, for breach detection
    breach_caps = [{"names": [f["a"], f["b"]], "max_units": 1.5, "axis": "correlation"}
                   for f in corr.get("flagged_pairs", []) if f.get("breach")]
    for bc in breach_caps:
        print(f"WARN correlation breach: {bc['names']} -> combined units capped at 1.5")
    build_weights(apx, picks, extra_caps=breach_caps)
    # Deterministic chain backstop — joint closed-form solve, never a convergence loop: all chains
    # breaching on the provisional weights are capped TOGETHER (independently-solved caps each treat
    # the other breaching chain as "outside" and under-tighten — both land above 30% after rebuild).
    # The solve is exact for disjoint chains; ONE bounded re-check handles overlap (a 2-chain name
    # shifts another cap's outside-units) and may only TIGHTEN an already-capped axis. A chain that
    # breaches ONLY as a consequence of other chains' caps is geometry, not concentration — WARN,
    # never cap (with few chains <=30%-per-chain is infeasible; iterating would spiral caps to zero).
    chain_caps = enforce_chain_caps(apx, picks, gin)
    if chain_caps:
        build_weights(apx, picks, extra_caps=breach_caps + chain_caps)
        by_axis = {c["axis"]: c for c in chain_caps}
        for c in enforce_chain_caps(apx, picks, gin):
            if c["axis"] in by_axis and c["max_units"] < by_axis[c["axis"]]["max_units"]:
                by_axis[c["axis"]] = c                     # overlap re-check: tighten capped axes only
            elif c["axis"] not in by_axis:
                print(f"WARN chain cap: {c['axis']} exceeds the cap only AFTER other chains were "
                      f"capped (few-chain geometry makes <=30%-per-chain infeasible) — operator "
                      f"review; NOT capped to avoid a spiral to zero")
        chain_caps = sorted(by_axis.values(), key=lambda c: c["axis"])
    weights = build_weights(apx, picks, extra_caps=breach_caps + chain_caps)   # final (honors all caps)
    # residual audit on the FINAL weights — a share still above the cap means overlapping or
    # infeasible geometry survived the bounded passes; loud, distinct from the cap WARNs above.
    # Tolerance 0.2pp: caps and per-name units round to 3 decimals (~0.05pp share noise); the
    # failure this audit exists for (an under-tightened joint breach) sits whole points above.
    residual = {c: b for c, b in _chain_breaches(picks, gin)[0].items()
                if b["share"] > MAX_WEIGHT_PER_CHAIN + 2e-3}
    for c, b in sorted(residual.items()):
        print(f"WARN chain cap RESIDUAL: chain:{c} still at {round(b['share']*100, 1)}% "
              f"({b['n']} names) on FINAL weights — overlapping/infeasible geometry; operator review")
    corr = corr_block(syms, weekly_rets, weights)          # recompute combined-weight w/ final weights
    _flagged = {s for f in corr.get("flagged_pairs", []) for s in (f["a"], f["b"])}
    for p in picks:
        p["corr_flag"] = p["symbol"] in _flagged
    stamp_entry_plans(picks, quotes)
    stamp_entry_posture(picks)
    stamp_wheel(picks, "fr", quotes)
    for p in picks:
        p.setdefault("conviction", p.get("fr_score"))      # ledger/decision-history conviction key
    # chain_exposure (final weights by chain; a 2-chain name counts toward both) — same chain
    # resolution as the cap enforcement (grade-input fallback), so the published exposure can never
    # disagree with what the backstop capped.
    chain_exposure = {}
    for p in picks:
        for c in _pick_chains(p, gin):
            chain_exposure[c] = round(chain_exposure.get(c, 0.0) + weights.get(p["symbol"], 0) * 100, 2)
    apx["weights"] = weights
    apx["stress_test"] = stress_block(picks, weights, quotes, asof)
    apx["correlation"] = corr
    apx["exits"] = exits_block(picks, quotes)
    apx["chain_exposure"] = chain_exposure
    # chain_caps are a DERIVED backstop recomputed every run — surfaced under their own key, NEVER
    # folded into the Director's combined_caps (that would compound on a re-run and break --offline
    # idempotency).
    apx["chain_caps"] = chain_caps
    json.dump(apx, open(APEX_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if apex_mtime_before is not None:
        os.utime(APEX_F, (apex_mtime_before, apex_mtime_before))   # keep the Director's write time
    cross_book_overlap_warn(picks, gin)
    st = apx["stress_test"]
    max_chain = max(chain_exposure.items(), key=lambda kv: kv[1]) if chain_exposure else (None, 0)
    print(f"fr_post: stamped {APEX_F} | weights sum={round(sum(weights.values()), 4)} "
          f"| stress 52w-low={st['basket_to_52w_lows_pct']}% recession={st['recession_stress_pct']}% "
          f"| corr avg={corr.get('avg_pairwise')} pairs={corr.get('n_pairs')} "
          f"breaches={sum(1 for f in corr.get('flagged_pairs', []) if f.get('breach'))} "
          f"| top chain {max_chain[0]}={max_chain[1]}% (cap {int(MAX_WEIGHT_PER_CHAIN*100)}%) "
          f"| gate_capped={[p['symbol'] for p in picks if p.get('gate_capped')]} "
          f"stale={[p['symbol'] for p in picks if p.get('stale_anchor')]}")


if __name__ == "__main__":
    main()
