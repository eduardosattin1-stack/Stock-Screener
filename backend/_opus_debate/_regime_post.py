#!/usr/bin/env python3
"""Deterministic post-processing for the REGIME / APEX book (apex_basket_opus_regime.json).

The mirror of _value_post.py for the catalyst/apex book. 2026-07-11 (pipeline-v3 Weeks 3-4) brings
the apex book to VALUE-BOOK GUARD PARITY — the forensics found the flagship published book was the
least numerically validated of the three. This now:
  1. consumes the APEX skeptic (_skeptic_regime/<SYM>.json) — REFUTED demotes to runner_ups;
  2. NUMERIC-GATE DEMOTE: an apex member whose debate record is stamped numeric_gate REJECT /
     EXCLUDE_ELIGIBILITY is demoted to runner_ups (a gate that cannot demote is decoration);
  3. CONVICTION CLAMP: |director_conviction - prior ledger conviction| > 10 without a dated fact in
     delta_justification -> conviction_eff = prior ± 10 (flags + clamps, never rewrites the prose);
  4. stamps the deterministic moat terminal-erosion teeth (moat_erosion=='CAP' -> 0.5 size cap);
  5. enforces the secular-theme concentration cap + Director combined_caps + measured-correlation
     breach caps;
  6. sizing memo = Director size_units when present, else BANDED conviction map (shared
     _post_common.banded_units — coarse steps, so conviction wiggle is weight-invisible);
  7. MARKET LAYER (value parity, network w/ _regime_post_cache.json + --offline): measured 2y weekly
     Pearson correlation matrix (beta vs SPY — the apex is a broad book, not the value book's
     consumer tilt), market stress (52w-low / recession / the record's typed valuation.bear_px), and
     thesis-break exits (Director thesis_break_px, fallback = valuation.bear_px). Fail-SOFT: a
     network blip skips the market layer with a WARN, never wedges the weekly publish;
  8. stamps size_units_effective + weight_pct + numeric_post_applied (publish gate requires it).

Pipeline order:
    Director -> apex_basket_opus_regime.json -> [skeptic shards, same-run pre-Director] ->
    _regime_post (THIS) -> publish_to_frontend.py

Usage: python backend/_opus_debate/_regime_post.py [--offline]
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../backend/_opus_debate
BK = _HERE.parent                                 # .../backend
ROOT = _HERE
sys.path.insert(0, str(BK))                       # backend on path for _moat / screener_v6 / _ledger
sys.path.insert(0, str(_HERE))                    # _opus_debate on path for _post_common
from _moat import moat_features                    # noqa: E402
import _post_common as _pc                          # noqa: E402
from _ledger import load_decision_history           # noqa: E402

REGIME_F = ROOT / "apex_basket_opus_regime.json"
SKEP_DIR = ROOT / "_skeptic_regime"
RES_DIR = ROOT / "results_regime"
CACHE_F = ROOT / "_regime_post_cache.json"

CONV_CLAMP_PTS = 10                                # |Δ conviction| beyond this needs a dated fact
_DATED_RE = re.compile(
    r"\b20\d\d-\d\d(-\d\d)?\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*20\d\d\b"
    r"|\b(Q[1-4])\s*(FY)?\s*20\d\d\b", re.IGNORECASE)
# Debt-cycle phase citations are NOT a per-name dated fact (spec §6.3: macro touches
# weights via the duration cap, never conviction). A delta_justification whose only
# dated content lives in a phase/cycle sentence is treated as unjustified.
_PHASE_JUST_RE = re.compile(
    r"\b(debt[- ]?cycle|monetiz|monetis|discipline\s+phase|forcing\s+phase|cycle\s+phase|"
    r"DISCIPLINE|FORCING|MONETIZATION|EXPANSION\s+phase)\b", re.IGNORECASE)


def _dated_fact_outside_phase(just: str) -> bool:
    """True when the justification carries a dated fact in a sentence that is NOT a
    debt-cycle-phase citation. 'MONETIZATION began 2026-08-01' alone must not unlock
    a conviction move; 'guide cut 2026-07-30; also MONETIZATION' still passes."""
    sents = re.split(r"(?<=[.;])\s+", just or "")
    keep = " ".join(s for s in sents if not _PHASE_JUST_RE.search(s))
    return bool(_DATED_RE.search(keep))


def _load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _scan_by_sym():
    for p in (BK.parent / "frontend" / "public" / "latest_global.json", ROOT / "latest_global.json"):
        d = _load(p)
        if d:
            return {x.get("symbol"): x for x in d.get("stocks", []) if x.get("symbol")}
    return {}


def stamp_moat(picks, uni, scan_by):
    """Compute + stamp the deterministic moat signals and the agent moat read onto each pick. Computes
    moat_features locally (from _radar_universe + scan + results_regime) so the regime book does NOT
    depend on value-input having run first — decoupling the weekly ordering."""
    for p in picks:
        sym = p.get("symbol")
        if not sym:
            continue
        r = _load(RES_DIR / f"{sym}.json", {}) or {"sector": p.get("sector", "")}
        mf = moat_features(uni.get(sym, {}), scan_by.get(sym, {}), r)
        p["moat_erosion"] = mf["moat_erosion"]
        p["erosion_severity"] = mf["erosion_severity"]
        p["moat_score"] = mf["moat_score"]
        p["roic_below_hurdle"] = mf["roic_below_hurdle"]
        if not p.get("moat"):
            p["moat"] = r.get("moat", "")
        if not p.get("secular_theme"):
            p["secular_theme"] = r.get("secular_theme", "")


def numeric_demote(apx):
    """Weeks-3/4 teeth for the numeric gate: an apex member whose results_regime record is stamped
    numeric_gate REJECT / EXCLUDE_ELIGIBILITY is DEMOTED to the front of runner_ups (mirrors the
    skeptic demote). Inert until `numeric-gate --enforce` runs (records without the stamp pass)."""
    keep, demoted = [], []
    for p in apx.get("apex_basket", []):
        sym = p.get("symbol")
        rec = _load(RES_DIR / f"{sym}.json", {}) or {}
        ng = rec.get("numeric_gate")
        if ng in ("REJECT", "EXCLUDE_ELIGIBILITY"):
            p["numeric_gate"] = ng
            p["numeric_gate_reasons"] = rec.get("numeric_gate_reasons", [])
            p["numeric_demoted"] = True
            demoted.append(p)
            print(f"WARN numeric-gate: {sym} {ng} -> DEMOTED to runner_ups | {rec.get('numeric_gate_reasons')}")
        else:
            if ng:                                            # PASS/WARN ride along for visibility
                p["numeric_gate"] = ng
            if isinstance(rec.get("computed"), dict):
                p["computed"] = rec["computed"]               # computed rr/ER onto the pick (ledger reads it)
            keep.append(p)
    if demoted:
        dsyms = {d.get("symbol") for d in demoted}
        apx["apex_basket"] = keep
        apx["runner_ups"] = demoted + [r for r in (apx.get("runner_ups") or [])
                                       if (r.get("symbol") if isinstance(r, dict) else r) not in dsyms]
    return apx


def conviction_clamp(picks):
    """Weeks-3/4 Director anchoring, the deterministic backstop: a director_conviction moving more
    than CONV_CLAMP_PTS vs the prior ledger conviction WITHOUT a dated fact in delta_justification is
    clamped to prior ± CONV_CLAMP_PTS (conviction_eff; the Director's raw number is preserved under
    director_conviction_orig). Flags-and-clamps only — prose untouched."""
    hist = (load_decision_history() or {}).get("regime", {})
    today = date.today().isoformat()
    clamped = []
    for p in picks:
        sym = p.get("symbol")
        try:
            conv = float(p.get("director_conviction"))
        except (TypeError, ValueError):
            continue
        prior_evs = [e for e in hist.get(sym, []) if e.get("date") != today
                     and isinstance(e.get("conviction"), (int, float))]
        if not prior_evs:
            continue
        prior = float(prior_evs[-1]["conviction"])
        delta = conv - prior
        p.setdefault("conviction_prior", prior)
        p.setdefault("conviction_delta", round(delta, 1))
        if abs(delta) <= CONV_CLAMP_PTS:
            continue
        just = str(p.get("delta_justification") or "")
        if _PHASE_JUST_RE.search(just):
            p["phase_cited_in_delta"] = True                  # visibility even when it also passes
        if _dated_fact_outside_phase(just):
            continue                                          # big move, dated NON-phase fact -> legitimate
        eff = prior + (CONV_CLAMP_PTS if delta > 0 else -CONV_CLAMP_PTS)
        p["director_conviction_orig"] = conv
        p["director_conviction"] = eff
        p["conviction_clamped"] = True
        p["conviction_clamp_note"] = (f"|Δ|={abs(delta):.0f}>{CONV_CLAMP_PTS} vs prior {prior:.0f} with no "
                                      f"dated fact in delta_justification -> clamped to {eff:.0f}")
        clamped.append(f"{sym} ({prior:.0f}->{conv:.0f} clamped {eff:.0f})")
    if clamped:
        print(f"WARN conviction-clamp: {clamped}")
    return picks


def stamp_valuation(picks):
    """Pull the typed valuation numbers off each pick's debate record onto the pick, so the market
    layer's getters (bear px, thesis break) and the ledger see them without re-reading records."""
    for p in picks:
        rec = _load(RES_DIR / f"{p.get('symbol')}.json", {}) or {}
        val = rec.get("valuation") or {}
        if isinstance(val.get("bear_px"), (int, float)) and not isinstance(p.get("bear_fv_px"), (int, float)):
            p["bear_fv_px"] = val["bear_px"]
        if not isinstance(p.get("thesis_break_px"), (int, float)):
            tb = val.get("bear_px")
            if isinstance(tb, (int, float)):
                p["thesis_break_px"] = tb
                p["thesis_break_source"] = "bear_px_fallback"


def stamp_duration_buckets(picks, scan_by):
    """Deterministic payback-speed label per pick (debt_cycle.duration_bucket) from scan
    FCF fundamentals. The Director may override only WITH a written justification —
    duration_bucket is the first macro-adjacent field with numeric authority (it feeds
    the phase duration cap), so the default must never be vibes."""
    from debt_cycle import duration_bucket
    for p in picks:
        p.update(duration_bucket(
            scan_by.get(p.get("symbol"), {}) or {},
            override=p.get("duration_bucket_override"),
            override_reason=str(p.get("duration_bucket_override_reason") or ""),
        ))


def enforce_duration_caps(apx, picks, cycle):
    """FORK 2/B — phase-conditioned duration cap, the same kind of object as the
    secular-theme and correlation caps: an AGGREGATE-EXPOSURE judgement, never an
    eligibility one. When the story-bucket share exceeds the phase cap, the
    LOWEST-conviction story seats are trimmed toward a 0.1-unit floor (trimming is a
    weight action; demotion belongs to the skeptic/numeric gates). cash_now_min and
    real_asset_floor are WARN/advisory — a cap cannot conjure names that aren't seated.
    UNKNOWN phase carries the loosest caps (fail-open). Records cap_binding so a
    binding cap is visible, not inferred."""
    cycle = cycle or {}
    phase = cycle.get("debt_cycle_phase") or "UNKNOWN"
    caps = cycle.get("duration_caps") or {}
    if not caps:
        from debt_cycle import PHASE_DURATION_CAPS
        caps = PHASE_DURATION_CAPS.get(phase, PHASE_DURATION_CAPS["UNKNOWN"])
    apx["debt_cycle_phase_applied"] = phase
    apx["duration_caps_applied"] = caps
    binding, warnings = [], []
    units = {p["symbol"]: float(p.get("size_units_effective") or 0) for p in picks}
    tot = sum(units.values())
    if not picks or tot <= 0:
        apx["cap_binding"] = binding
        return apx

    smax = caps.get("story_max")
    story = [p for p in picks if p.get("duration_bucket") == "story"]
    if isinstance(smax, (int, float)) and story and smax < 1.0:
        s_units = sum(units[p["symbol"]] for p in story)
        # story share after trim: Us' / (tot - Us + Us') <= smax  =>  Us' <= smax*(tot-Us)/(1-smax)
        target = smax * (tot - s_units) / (1.0 - smax)
        if s_units > target + 1e-9:
            need = s_units - target
            for p in sorted(story, key=lambda x: float(x.get("director_conviction") or 0)):
                if need <= 1e-9:
                    break
                u = units[p["symbol"]]
                cut = min(need, max(0.0, u - 0.1))          # trim toward floor, never to zero
                if cut > 1e-9:
                    units[p["symbol"]] = round(u - cut, 3)
                    p["cycle_capped"] = True
                    p["cycle_cap_note"] = (f"trimmed {cut:.2f}u by {phase} duration cap "
                                           f"(story <= {smax:.0%} of book)")
                    need -= cut
            binding.append("duration_story")
            if need > 1e-9:
                warnings.append(f"story legs all at 0.1u floor and still {need:.2f}u over the "
                                f"{phase} story cap — floor respected, residual overage published")
            W = sum(units.values()) or 1.0
            for p in picks:
                p["size_units_effective"] = units[p["symbol"]]
                p["weight_pct"] = round(units[p["symbol"]] / W * 100, 2)
            apx["weights"] = {s: round(u / W, 4) for s, u in units.items()}
            print(f"duration-cap: {phase} story<= {smax:.0%} BOUND — trimmed "
                  f"{[p['symbol'] for p in story if p.get('cycle_capped')]}")

    cmin = caps.get("cash_now_min")
    if isinstance(cmin, (int, float)):
        W = sum(units.values()) or 1.0
        c_share = sum(units[p["symbol"]] for p in picks if p.get("duration_bucket") == "cash_now") / W
        if c_share < cmin - 1e-9:
            warnings.append(f"cash_now share {c_share:.0%} < {phase} floor {cmin:.0%} — "
                            f"WARN only (a cap cannot conjure names); Director must own it in the memo")
    if "real_asset_floor" in caps:
        warnings.append(f"{phase} real_asset_floor {caps['real_asset_floor']:.0%} is ADVISORY "
                        f"(no deterministic real-asset classification yet)")
    for w in warnings:
        print(f"WARN duration-cap: {w}")
    apx["cap_binding"] = binding
    apx["duration_cap_warnings"] = warnings
    return apx


def process(apx, uni, scan_by, market=None):
    """Consume the apex skeptic + numeric gate, clamp conviction, stamp the moat teeth, enforce the
    secular-theme + Director combined caps (+ measured correlation caps when `market` is supplied),
    and build weights. Mutates + returns (apx, picks, extra). Pure when market=None — safe on an
    in-memory copy with no network (test_regime_post baseline unchanged)."""
    apx = _pc.consume_skeptic(apx, REGIME_F, SKEP_DIR)        # REFUTED -> demote BEFORE weights
    apx = numeric_demote(apx)                                 # numeric-gate teeth (inert pre-enforce)
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    stamp_moat(picks, uni, scan_by)
    stamp_moat([r for r in apx.get("runner_ups", []) if isinstance(r, dict)], uni, scan_by)  # visibility only
    stamp_valuation(picks)
    conviction_clamp(picks)
    extra = _pc.secular_theme_caps(picks)                    # don't put all eggs in one secular tail
    # Base unit = Director size_units when present, else the shared BANDED conviction map — coarse
    # steps shared with publish_to_frontend._apex_weights so the two sizing paths can never diverge.
    memo = {p["symbol"]: _pc.banded_units(p.get("director_conviction") or p.get("conviction"))
            for p in picks}
    if market:                                                # measured-correlation caps (value parity)
        quotes, weekly_rets, asof = market
        prov = _pc.build_weights(apx, picks, extra_caps=extra, memo_units=memo,
                                 per_name_cap=_pc.moat_per_name_cap)
        corr = _pc.corr_block([p["symbol"] for p in picks], weekly_rets, prov, beta_symbol="SPY")
        extra = extra + _pc.corr_breach_caps(corr, max_units=1.5)
        apx["correlation"] = corr
    weights = _pc.build_weights(apx, picks, extra_caps=extra, memo_units=memo, per_name_cap=_pc.moat_per_name_cap)
    apx["weights"] = weights
    apx["secular_theme_caps"] = extra
    # ── Dalio debt-cycle duration layer (2026-07-27, FORK 2/B): stamp the deterministic
    # payback-speed label, then enforce the phase story-cap AFTER build_weights (it
    # re-normalizes in place). Fail-open: missing snapshot => UNKNOWN => loosest caps.
    stamp_duration_buckets(picks, scan_by)
    _cycle = (_load(ROOT / "macro_regime.json", {}) or {}).get("debt_cycle") or {}
    apx = enforce_duration_caps(apx, picks, _cycle)
    if market:
        quotes, weekly_rets, asof = market
        apx["stress_test"] = _pc.stress_block(picks, weights, quotes, asof,
                                              bear_px=lambda p: p.get("bear_fv_px"),
                                              bear_label="valuation.bear_px")
        apx["exits"] = _pc.exits_block(picks, quotes, thesis_break=lambda p: p.get("thesis_break_px"))
    apx["moat_post_applied"] = True
    apx["numeric_post_applied"] = True
    return apx, picks, extra


def _get_market(picks, offline):
    """Value-parity market layer inputs: live quotes + 2y weekly log-returns for the picks + SPY,
    cached at _regime_post_cache.json (--offline reuses). Fail-SOFT: any failure returns None with a
    WARN — a network blip must never wedge the weekly publish; the market blocks are simply skipped
    (and the correlation stress falls back to the Director's asserted version for that week)."""
    try:
        # screener_v6 freezes FMP_KEY from the env AT IMPORT — load the real key (frontend/.env.local
        # via the engine's loader) BEFORE the import; fall back to the demo key like _value_post does.
        import os as _os
        if not _os.environ.get("FMP_API_KEY"):
            try:
                import live_debate_engine as _E
                _E.load_api_keys()
            except Exception:
                pass
        if not _os.environ.get("FMP_API_KEY"):
            _os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"   # match _value_post fallback
        from screener_v6 import fmp, get_chart               # deferred: heavy import, network-capable

        def quotes_fn(symbols):
            return _pc.live_quotes(fmp, symbols)

        syms = [p["symbol"] for p in picks if p.get("symbol")]
        market = _pc.get_market(syms, syms + ["SPY"], offline, CACHE_F,
                                quotes_fn=quotes_fn, chart_fn=lambda s: get_chart(s, days=760))
        quotes = market[0] if market else {}
        if not quotes:                                    # e.g. missing FMP key (401s) — same as no network
            print("WARN _regime_post: market layer returned NO quotes (missing FMP key / network?) — "
                  "stress/correlation/exits skipped this run (weights/caps/clamps still applied)")
            return None
        return market
    except Exception as e:
        print(f"WARN _regime_post: market layer unavailable ({e}) — stress/correlation/exits skipped "
              f"this run (weights/caps/clamps still applied)")
        return None


def main():
    offline = "--offline" in sys.argv
    apx = _load(REGIME_F)
    if not apx or not apx.get("apex_basket"):
        print(f"_regime_post: {REGIME_F} missing or empty — nothing to do.")
        return
    uni = {x["symbol"]: x for x in (_load(ROOT / "_radar_universe.json", []) or [])}
    scan_by = _scan_by_sym()
    market = _get_market([p for p in apx.get("apex_basket", []) if p.get("symbol")], offline)
    apx, picks, extra = process(apx, uni, scan_by, market=market)
    json.dump(apx, open(REGIME_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    capped = [p["symbol"] for p in picks if p.get("moat_erosion") == "CAP"]
    refute = [p["symbol"] for p in picks
              if p.get("erosion_severity") == "value-destroying"
              or (p.get("moat_erosion") == "CAP" and p.get("roic_below_hurdle"))]
    clamped = [p["symbol"] for p in picks if p.get("conviction_clamped")]
    ngd = [r.get("symbol") for r in apx.get("runner_ups", []) if isinstance(r, dict) and r.get("numeric_demoted")]
    st = apx.get("stress_test") or {}
    print(f"_regime_post: {len(picks)} apex | moat-capped={capped} | skeptic-REFUTE-candidates={refute} "
          f"| secular-theme caps={[c['axis'] for c in extra]} | conviction-clamped={clamped or 'none'} "
          f"| numeric-demoted={ngd or 'none'} | market-layer={'ON' if market else 'SKIPPED'}"
          + (f" | stress 52w-low={st.get('basket_to_52w_lows_pct')}% recession={st.get('recession_stress_pct')}% "
             f"published-downside={st.get('published_downside_pct')}%" if st else ""))


if __name__ == "__main__":
    main()
