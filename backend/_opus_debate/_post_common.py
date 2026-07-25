#!/usr/bin/env python3
"""Shared post-processing primitives for BOTH the value apex (_value_post.py) and the regime/apex
book (_regime_post.py): the skeptic kill-tier, the weight builder (with the moat-erosion + combined
caps), and the deterministic secular-theme concentration cap. Factored out so the two books run ONE
implementation — a skeptic that demotes and a cap loop that sizes, identical across surfaces.

Design notes carried over from _value_post.py:
  - consume_skeptic is fork (b): a REFUTED apex member is physically DEMOTED to the front of
    runner_ups ("a skeptic that cannot demote is decoration"). Staleness guard ignores shards older
    than the apex file (a stale verdict must never demote a fresh basket).
  - build_weights enforces Director `combined_caps` + any `extra_caps` (correlation breaches, secular
    themes) by scaling the named cluster's units down to max_units; per_name_cap applies the half-size
    teeth (cro_only / stale_anchor / moat_erosion).
  - 2026-07-11: the SHARED MARKET BLOCKS moved here from _value_post.py so the regime book gets the
    same guards (value-book parity): get_market (live quotes + 2y weekly log-returns w/ on-disk cache
    + --offline reuse), stress_block (weighted downside to 52w lows / recession / caller-supplied bear
    px), corr_block (pairwise 2y weekly Pearson + beta vs a caller-supplied benchmark), exits_block
    (thesis-break sanity). All are pure functions parameterized on the book specifics (quotes/charts
    providers, cache path, bear-px getter, benchmark symbol) — this module stays free of import side
    effects (no FMP/screener_v6 import; the caller injects its fetchers).
"""
import json
import math
import statistics
from datetime import datetime as _dt
from pathlib import Path


def consume_skeptic(apx, apex_file: Path, skep_dir: Path, conviction_field: str = "value_conviction_cap"):
    """Merge skep_dir/<SYM>.json shards -> sidecar <skep_dir>_results.json and apply the verdicts.
    REFUTED demotes the apex member to the front of runner_ups; CONFIRMED_WITH_CORRECTIONS stamps the
    correction + conviction cap. Idempotent: re-running re-applies the same verdicts to the same members."""
    skep_dir = Path(skep_dir)
    apex_file = Path(apex_file)
    if not skep_dir.is_dir():
        return apx
    apex_mtime = apex_file.stat().st_mtime if apex_file.exists() else 0
    # Freshness window (2026-07-10, two-tier restructure): the skeptic phase now runs BEFORE the
    # Director inside the same weekly workflow, so a same-run shard is legitimately a few minutes-to-
    # hours OLDER than the apex file. The old strict `< apex_mtime - 1` guard would discard every
    # pre-Director shard as stale. A 24h window cleanly separates same-run shards (minutes/hours old)
    # from genuinely stale prior-week shards (~7 days old on the weekly cadence).
    SKEPTIC_FRESH_WINDOW_S = 24 * 3600
    merged, stale, stale_verdicts = {}, [], {}
    for f in sorted(skep_dir.glob("*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
            if f.stat().st_mtime < apex_mtime - SKEPTIC_FRESH_WINDOW_S:
                stale.append(f.stem)
                if d.get("symbol"):                      # remember stale verdicts — a stale REFUTED
                    stale_verdicts[d["symbol"]] = d       # on a still-held name must not vanish (HRMY)
                continue
            if d.get("symbol"):
                merged[d["symbol"]] = d
        except Exception as e:
            print(f"WARN skeptic: shard {f.name} unreadable ({e})")
    if stale:
        print(f"skeptic: ignored {len(stale)} stale shard(s) older than the apex: {sorted(stale)}")
    if merged:
        (skep_dir.parent / (skep_dir.name + "_results.json")).write_text(
            json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    # COVERAGE — fail LOUD, not open (the 06-30 apex + EEFT/HRMY value book shipped with zero fresh
    # shards and this function returned silently). Every apex member without a FRESH shard is stamped
    # skeptic_verdict=MISSING (+ skeptic_missing=True -> half-sized by moat_per_name_cap); a STALE
    # REFUTED on a still-held member is stamped skeptic_stale_refuted (half-size + re-run flag), never
    # silently ignored. Publish stays possible (partial runs are the ops norm) — visible and priced.
    missing, stale_ref = [], []
    for p in apx.get("apex_basket", []):
        sym = p.get("symbol")
        if not sym or sym in merged:
            continue
        sv = stale_verdicts.get(sym)
        if sv and (sv.get("verdict") or "").upper() == "REFUTED":
            p["skeptic_verdict"] = "MISSING"
            p["skeptic_stale_refuted"] = True
            p["skeptic_kill_fact"] = f"STALE shard: {str(sv.get('kill_fact', ''))[:160]}"
            stale_ref.append(sym)
        else:
            p["skeptic_verdict"] = "MISSING"
            p["skeptic_missing"] = True
            missing.append(sym)
    # STICKY-FLAG FIX (2026-07-24): the loop above only ever SETS skeptic_missing, and the post layer
    # re-reads the apex JSON it previously stamped — so a name flagged by an early run stayed
    # half-sized forever, even after the skeptic ran and CONFIRMED it. Observed live: all 9 apex seats
    # carried skeptic_missing=True from the first regime-post, collapsing the Director's 0.4-1.1
    # sizing spread to a flat 0.5. Clear the flag for every name that now HAS a fresh verdict.
    for p in apx.get("apex_basket", []):
        if p.get("symbol") in merged:
            p.pop("skeptic_missing", None)
            p.pop("skeptic_stale_refuted", None)
    if missing:
        print(f"WARN skeptic-coverage: {len(missing)} apex member(s) have NO fresh skeptic shard -> "
              f"stamped MISSING + half-sized: {missing} (fix: run the skeptic workflow)")
    if stale_ref:
        print(f"WARN skeptic-coverage: STALE REFUTED shard(s) on still-held member(s) -> half-sized, "
              f"re-run the skeptic: {stale_ref}")
    if not merged:
        return apx
    keep, demoted = [], []
    for p in apx.get("apex_basket", []):
        v = merged.get(p.get("symbol"))
        if not v:
            keep.append(p)
            continue
        p["skeptic_verdict"] = v.get("verdict", "")
        if v.get("kill_fact"):
            p["skeptic_kill_fact"] = v["kill_fact"]
        if v.get("corrections"):
            p["skeptic_corrections"] = v["corrections"]
        # Unified skeptic (X1): CATEGORICAL severity replaces the numeric cap. A "material"
        # correction (a load-bearing number/date/anchor moved) takes a bounded sizing haircut in
        # moat_per_name_cap — a haircut, never a hard ceiling (the proven numeric-cap bug class).
        if v.get("correction_severity"):
            p["correction_severity"] = v["correction_severity"]
        if v.get("kill_scope"):
            p["skeptic_kill_scope"] = v["kill_scope"]
        if v.get("carried_from_book"):
            p["skeptic_carried_from"] = v["carried_from_book"]
        if isinstance(v.get(conviction_field), (int, float)):   # legacy shards only (pre-X1)
            p[conviction_field] = v[conviction_field]
        if (v.get("verdict") or "").upper() == "REFUTED":
            p["skeptic_refuted"] = True
            demoted.append(p)
            print(f"WARN skeptic: {p['symbol']} REFUTED -> DEMOTED to runner_ups | kill_fact: {str(v.get('kill_fact', ''))[:160]}")
        else:
            keep.append(p)
    if demoted:
        dsyms = {d.get("symbol") for d in demoted}
        apx["apex_basket"] = keep
        apx["runner_ups"] = demoted + [r for r in (apx.get("runner_ups") or [])
                                       if (r.get("symbol") if isinstance(r, dict) else r) not in dsyms]
    for r in apx.get("runner_ups", []):
        if isinstance(r, dict) and r.get("symbol") in merged and "skeptic_verdict" not in r:
            r["skeptic_verdict"] = merged[r["symbol"]].get("verdict", "")
    n_conf = sum(1 for v in merged.values() if (v.get("verdict") or "").upper().startswith("CONFIRMED"))
    print(f"skeptic: {len(merged)} verdicts | confirmed={n_conf} refuted={len(demoted)} (demoted: {[d['symbol'] for d in demoted]})")
    return apx


# EQUAL WEIGHT (2026-07-24, Bruno's call). Every book publishes equal weight. Evidence: across 2151
# dated debate records the Director's conviction had NO monotone relation to forward return (buckets
# 1-5: +1.36/+1.48/+1.94/+1.22/+1.69%) and its TOP grade was its WORST bucket (verdict-A -1.92%, 38%
# win); the live equal-weight apex chain also leads the conviction-weighted one (111.9 vs 107.8).
# Weighting by a signal with no demonstrated edge just adds variance. The size_units the Director and
# the caps produce are STILL computed and stored (size_units_effective) so the teeth stay auditable
# and this is one flag to flip back the day conviction earns its keep.
EQUAL_WEIGHT_BOOKS = True


def build_weights(apx, picks, extra_caps=None, memo_units=None, per_name_cap=None):
    """Normalize size_units -> weight_pct, honoring per-name half-caps + combined/extra caps.
    per_name_cap(p, u) -> u' applies the teeth (cro_only / stale_anchor / moat_erosion). extra_caps and
    apx['combined_caps'] share the schema {names:[...], max_units: float, axis: str}.
    With EQUAL_WEIGHT_BOOKS the caps still run (size_units_effective is stamped as before) but the
    PUBLISHED weight_pct is 1/n — see the note above."""
    memo_units = memo_units or {}
    units = {}
    for p in picks:
        u = p.get("size_units")
        if not isinstance(u, (int, float)) or not (0.1 <= u <= 1.5):
            u = memo_units.get(p["symbol"], 1.0)
        if per_name_cap is not None:
            u = per_name_cap(p, u)
        units[p["symbol"]] = u
    for cap in list(apx.get("combined_caps") or []) + list(extra_caps or []):
        names = [s for s in (cap.get("names") or []) if s in units]
        mx = cap.get("max_units")
        tot = sum(units[s] for s in names)
        if names and isinstance(mx, (int, float)) and tot > mx:
            scale = mx / tot
            for s in names:
                units[s] = round(units[s] * scale, 3)
    if EQUAL_WEIGHT_BOOKS and units:
        eq = 1.0 / len(units)
        weights = {s: round(eq, 4) for s in units}
    else:
        W = sum(units.values()) or 1.0
        weights = {s: round(u / W, 4) for s, u in units.items()}
    for p in picks:
        p["size_units_effective"] = units[p["symbol"]]   # still stamped: the teeth stay auditable
        p["weight_pct"] = round(weights[p["symbol"]] * 100, 2)
        p["weight_basis"] = "equal" if EQUAL_WEIGHT_BOOKS else "size_units"
    return weights


def secular_theme_caps(picks, max_units=1.5):
    """Deterministic safety-net for the "don't put all eggs in one secular tail" rule. For each
    secular_theme carrying >=2 NON-DURABLE names, emit a combined_caps entry scaling that cluster to
    max_units. A WIDE moat that is NOT eroding is EXEMPT (durable half-relief taken to its limit: the
    anchor that merely carries the narrative is not the tail risk and is not cut). Returns extra_caps
    consumable by build_weights. The Director may ALSO emit its own combined_caps; both are honored."""
    by_theme = {}
    for p in picks:
        if p.get("lane") == "equity_special_sit":
            continue   # lane contract: event-driven seats resolve on their own catalyst, not a secular tail
        th = (p.get("secular_theme") or "").strip().lower()
        if not th or th in ("none", "n/a"):
            continue
        by_theme.setdefault(th, []).append(p)
    caps = []
    for th, members in sorted(by_theme.items()):
        non_durable = [m["symbol"] for m in members
                       if not (str(m.get("moat", "")).upper() == "WIDE" and m.get("moat_erosion") != "CAP")]
        if len(non_durable) >= 2:
            caps.append({"names": non_durable, "max_units": max_units, "axis": f"secular-theme:{th}"})
            print(f"secular-theme cap: {th} carries {len(non_durable)} non-durable legs {non_durable} -> combined units <= {max_units}")
    return caps


def moat_per_name_cap(p, u, extra_flags=()):
    """Half-size teeth: cro_only / stale_anchor (existing) + moat_erosion=='CAP' + skeptic-coverage
    (MISSING / stale-REFUTED). extra_flags lets a caller add book-specific boolean keys to the OR."""
    # Skeptic-coverage teeth apply to EVERY seat, lanes included — an un-vetted seat is half-sized.
    if p.get("skeptic_missing") or p.get("skeptic_stale_refuted"):
        return min(u, 0.5)
    # Unified-skeptic MATERIAL correction (a load-bearing number/date/anchor moved): a BOUNDED
    # 3/4 haircut — consequences without the numeric-cap-as-ceiling bug class (X1/VB-P5).
    if p.get("correction_severity") == "material":
        u = min(u, 0.75)
    # LANE CONTRACT: an equity special-sit seat is EVENT-driven — the Director's STEP-3b exempted it
    # from the compounder moat/erosion teeth, and the publish layer already floor-sizes it harder
    # (1.5% risk-to-floor). Applying the moat half-cap here would contradict that contract.
    if p.get("lane") == "equity_special_sit":
        return u
    # 2026-07-21 #4: the value post stamps washout_moat_exception (deep drawdown + NARROW/WIDE moat
    # + non-eroding trend) — it relaxes ONLY the moat CAP half-size to 0.75; cro_only/stale_anchor
    # and extra_flags still force 0.5. Books that never stamp the flag (regime) are unchanged.
    _moat_cap = p.get("moat_erosion") == "CAP" and not p.get("washout_moat_exception")
    if p.get("cro_only") or p.get("stale_anchor") or _moat_cap \
            or any(p.get(k) for k in extra_flags):
        return min(u, 0.5)
    if p.get("moat_erosion") == "CAP" and p.get("washout_moat_exception"):
        return min(u, 0.75)
    return u


def banded_units(conv):
    """Director conviction (0-100) -> coarse size-unit BANDS (2026-07-11, Weeks 3-4 anchoring).
    Replaces the continuous conviction/100 knob, where 3 points of weekly conviction wiggle moved
    real weight — banded steps make small re-grades weight-invisible; only a band CROSSING (a
    genuine re-rating) resizes the seat. Shared by _regime_post (memo units) and
    publish_to_frontend._apex_weights (fallback) so the two sizing paths can never diverge."""
    try:
        c = float(conv or 0)
    except (TypeError, ValueError):
        c = 0.0
    if c >= 90:
        return 1.4
    if c >= 70:
        return 1.1
    if c >= 50:
        return 0.8
    return 0.5


# ═════════════════════ SHARED MARKET BLOCKS (moved verbatim from _value_post.py, 2026-07-11) ═════════════════════
# Book-agnostic machinery: the caller injects its fetchers (quotes_fn/chart_fn), cache file, bear-px
# getter, thesis-break getter and beta benchmark. No network / FMP import at module scope.

def live_quotes(fmp_fn, symbols):
    """Batch quotes incl. yearHigh/yearLow (FMP stable batch-quote, comma symbols, chunked 50).
    fmp_fn(endpoint, params) -> list is the caller's FMP REST fetcher (e.g. screener_v6.fmp)."""
    out = {}
    for i in range(0, len(symbols), 50):
        rows = fmp_fn("batch-quote", {"symbols": ",".join(symbols[i:i + 50])}) or []
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


def get_market(quote_syms, corr_syms, offline, cache_path, quotes_fn, chart_fn):
    """Fetch (or, --offline, reuse cached) live quotes + 2y weekly log-returns. Caches once for idempotency.
    quotes_fn(symbols) -> {sym: {price, yearHigh, yearLow}}; chart_fn(sym) -> ascending OHLCV rows
    (the caller pins the window, e.g. lambda s: get_chart(s, days=760)); cache_path = the book's cache file."""
    cache_path = Path(cache_path)
    if offline and cache_path.exists():
        c = json.load(open(cache_path, encoding="utf-8"))
        return c.get("quotes", {}), c.get("weekly_rets", {}), c.get("asof", "")
    quotes = quotes_fn(quote_syms)
    wr = {}
    for s in corr_syms:
        r = weekly_logrets(chart_fn(s))
        if r:
            wr[s] = r
    asof = _dt.now().strftime("%Y-%m-%d")
    json.dump({"asof": asof, "quotes": quotes, "weekly_rets": wr}, open(cache_path, "w", encoding="utf-8"))
    return quotes, wr, asof


def stress_block(picks, weights, quotes, asof, bear_px, bear_label="bear_fv_px"):
    """Market-based stress: weighted basket return to the 52w lows, recession = 52w-low -15%, plus the
    agents' own adverse leg from the CALLER-SUPPLIED bear_px(p) getter (value: p['bear_fv_px']; regime:
    rec['valuation']['bear_px']). bear_case_invalid flags a missing/above-spot bear case; the published
    downside then falls back to the market-based recession stress. bear_label only names the getter in
    the note text."""
    rows, w_lo, w_rec, w_bear, any_bear = [], 0.0, 0.0, 0.0, False
    for p in picks:
        s = p["symbol"]
        q = quotes.get(s) or {}
        px, lo, bear = q.get("price"), q.get("yearLow"), bear_px(p)
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
                    f"(recession). cro_bear is the agents' own adverse SoP ({bear_label}); when missing or "
                    "implying upside it is flagged invalid and the published downside is the market-based "
                    "recession stress."}


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


def corr_block(syms, weekly_rets, weights, beta_symbol, beta_key=None, thresh=0.6, hard=0.7):
    """Pairwise 2y weekly-log-return Pearson: flag pairs >= thresh; breach = corr >= hard AND combined
    weight > 16% (consumed by corr_breach_caps -> extra_caps). Betas vs the CALLER-SUPPLIED benchmark
    (value: XLY under key 'consumer_beta_xly'; regime: SPY). beta_key defaults to beta_<symbol>."""
    beta_key = beta_key or f"beta_{beta_symbol.lower()}"
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
    mkt = weekly_rets.get(beta_symbol)
    betas = {}
    for s in syms:
        b = _beta(weekly_rets.get(s), mkt)
        if b is not None:
            betas[s] = round(b, 2)
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    return {"window": "2y weekly log returns", "avg_pairwise": avg, "n_pairs": len(pairs),
            "max_pair": max(pairs, key=lambda p: p["corr"]) if pairs else None,
            "flagged_pairs": flagged, beta_key: betas,
            "correlation_breach": any(f.get("breach") for f in flagged),
            "fx_note": "EU names in local ccy; correlations unadjusted for FX."}


def corr_breach_caps(corr, max_units=1.5):
    """Turn corr_block breaches (corr >= hard AND combined weight > 16%) into extra_caps entries for
    build_weights, printing the WARN per breach (moved from _value_post.main so both books share it)."""
    caps = [{"names": [f["a"], f["b"]], "max_units": max_units, "axis": "correlation"}
            for f in corr.get("flagged_pairs", []) if f.get("breach")]
    for bc in caps:
        print(f"WARN correlation breach: {bc['names']} -> combined units capped at {max_units}")
    return caps


def exits_block(picks, quotes, thesis_break):
    """Thesis-break exit levels, sanity-checked against live price (0 < tb < px). thesis_break(p) is the
    CALLER-SUPPLIED getter (value: p['thesis_break_px']; regime books map their own field)."""
    out = {}
    for p in picks:
        px = (quotes.get(p["symbol"]) or {}).get("price")
        tb = thesis_break(p)
        valid = isinstance(tb, (int, float)) and isinstance(px, (int, float)) and 0 < tb < px
        out[p["symbol"]] = {"thesis_break_px": tb if valid else None, "valid": bool(valid),
                            "review_trigger": "weekly refresh OR close < thesis_break_px"}
        if tb and not valid:
            print(f"WARN exits: {p['symbol']} thesis_break_px={tb} fails sanity vs px={px}")
    return out
