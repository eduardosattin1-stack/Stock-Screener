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
    """The scan, for the moat teeth and the duration bucket. FAILS LOUD (2026-07-27).

    This used to read two LOCAL paths and silently return {} when neither existed — which is exactly
    what happened on the operator box, where frontend/public/latest_global.json is not materialised.
    An empty scan does not raise: moat_features just sees no p_fcf/roic and stamps erosion="" /
    roic_below_hurdle=False, and every seat gets duration_bucket="unknown". So the moat terminal-erosion
    cap and the debt-cycle duration cap both went INERT on the 2026-07-27 book without a single error —
    the caps reported "nothing to cap" when the truth was "nothing to look at". GCS is now the fallback,
    and an empty result is a loud WARN rather than a shrug."""
    for p in (BK.parent / "frontend" / "public" / "latest_global.json", ROOT / "latest_global.json"):
        d = _load(p)
        if d:
            by = {x.get("symbol"): x for x in d.get("stocks", []) if x.get("symbol")}
            if by:
                return by
    try:
        if str(BK / "alpha_compounder") not in sys.path:
            sys.path.insert(0, str(BK / "alpha_compounder"))   # gcs_io lives in the subpackage
        import gcs_io
        d = gcs_io.gcs_read_json("scans/latest_global.json") or {}
        by = {x.get("symbol"): x for x in d.get("stocks", []) if x.get("symbol")}
        if by:
            print(f"scan: local mirror absent -> read {len(by)} names from GCS")
            return by
    except Exception as e:
        print(f"WARN scan: GCS fallback failed ({e})")
    print("WARN scan: NO scan data available (local mirror absent, GCS unreachable) — the moat-erosion "
          "teeth and the duration bucket CANNOT evaluate and will report nothing-to-cap. Do not read "
          "that as a clean book.")
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
        # base fair value: the TYPED number, never the prose. This is what the trim ceiling keys off,
        # and it is why the ceiling is trustworthy where a parsed target was not (2026-07-24).
        if isinstance(val.get("base_fv_px"), (int, float)) and not isinstance(p.get("base_fv_px"), (int, float)):
            p["base_fv_px"] = val["base_fv_px"]
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


# ── CYCLE FIT (2026-07-28) ────────────────────────────────────────────────────────────────────────
# Bruno's ask: name, per stock, WHICH phase a payoff actually needs — so "a phase-three trade being
# bought in phase one" is said out loud before it is bought, rather than discovered afterwards. The
# lesson it encodes is his own: a thematically-right asset with the wrong discount-rate exposure
# (gold and the SMR names through 2026) is not an entry, it is a wait.
#
# DETERMINISTIC, and deliberately so: derived from duration_bucket (itself computed from the scan's
# FCF), never from a probability an agent invented. The Director may override with phase_needed +
# a written reason, exactly like duration_bucket_override.
PHASE_ORDER = ["EXPANSION", "DISCIPLINE", "FORCING", "MONETIZATION"]
# What a payoff of this shape NEEDS to be paid: money arriving now is rewarded exactly when duration
# is being punished (DISCIPLINE); value that lives in a terminal year needs the cost of waiting to
# fall again (MONETIZATION). payback sits in between and is not phase-fussy.
_BUCKET_NEEDS = {"cash_now": "DISCIPLINE", "payback_2_3y": "ANY", "story": "MONETIZATION",
                 "unknown": "UNKNOWN"}
MIN_WEEKS_PER_STEP = 2      # the state machine's own hysteresis: 2 consecutive publishes per step


def stamp_cycle_fit(picks, cycle):
    """Per seat: which phase its payoff needs, how far that is from where we are, and whether its own
    stated horizon survives the wait. Stamps cycle_fit{} — advisory, never an eligibility gate."""
    cur = str((cycle or {}).get("debt_cycle_phase") or "UNKNOWN").upper()
    for p in picks:
        bucket = str(p.get("duration_bucket") or "unknown")
        needed = str(p.get("phase_needed") or "").upper() or _BUCKET_NEEDS.get(bucket, "UNKNOWN")
        src = "director_override" if p.get("phase_needed") else f"derived_from_{bucket}"
        fit = {"current_phase": cur, "phase_needed": needed, "source": src,
               "duration_bucket": bucket, "horizon_months": p.get("horizon_months")}
        if needed in ("ANY", "UNKNOWN") or cur not in PHASE_ORDER or needed not in PHASE_ORDER:
            fit["verdict"] = "phase_agnostic" if needed == "ANY" else "unknown"
            fit["read"] = ("This payoff does not depend much on where the borrowing cycle sits."
                           if needed == "ANY" else
                           "Not enough data to place this payoff in the cycle.")
        else:
            gap = PHASE_ORDER.index(needed) - PHASE_ORDER.index(cur)
            fit["phases_away"] = gap
            if gap == 0:
                fit["verdict"] = "aligned"
                fit["read"] = f"Paid in the phase we are actually in ({cur})."
            elif gap < 0:
                fit["verdict"] = "phase_passed"
                fit["read"] = (f"The phase that paid this ({needed}) is behind us; we are in {cur}. "
                               f"The thesis has to work on its own merits now, not on the cycle.")
            else:
                wks = gap * MIN_WEEKS_PER_STEP
                hz = p.get("horizon_months")
                survives = (isinstance(hz, (int, float)) and hz * 4.3 >= wks * 2)
                fit["verdict"] = "waiting_on_phase"
                fit["min_weeks_away"] = wks
                fit["horizon_survives_wait"] = bool(survives)
                fit["read"] = (
                    f"This is paid in {needed}, and we are in {cur} — {gap} phase step"
                    f"{'s' if gap > 1 else ''} away, which the cycle cannot cross in under ~{wks} "
                    f"weeks by its own rules and realistically takes far longer. "
                    + (f"Its {hz}-month horizon has room to wait." if survives and hz else
                       f"Its {hz}-month horizon may expire before the phase arrives." if hz else
                       "It states no horizon, so the wait is open-ended."))
        p["cycle_fit"] = fit
    waiting = [p["symbol"] for p in picks if (p.get("cycle_fit") or {}).get("verdict") == "waiting_on_phase"]
    if waiting:
        print(f"cycle-fit: {len(waiting)} seat(s) waiting on a phase that has not arrived: {waiting}")


def duration_cap_entries(apx, picks, cycle):
    """Phase-conditioned duration cap, returned in the SAME extra_caps schema the existing
    machinery already consumes ({names, max_units, axis}), so _pc.build_weights stays the
    single normalization path (secular_theme_caps / corr_breach_caps do the same).

    ADVISORY BY DECISION (Bruno, 2026-07-27): "the macro should give us trends/direction,
    not weigh on the picks." With _post_common.EQUAL_WEIGHT_BOOKS=True every book publishes
    1/n, so this cap — exactly like the secular-theme and correlation caps — bites
    size_units_effective and the audit trail ONLY. IT MOVES NO PUBLISHED WEIGHT. It is kept
    live-but-inert so _cycle_ledger.jsonl accumulates the realized duration mix and the
    question "would trimming story duration in DISCIPLINE have helped?" becomes answerable
    from evidence rather than from priors. Macro reaches the book through risk_stance, the
    STEP-3a entry-discount floor and the horizon stretch — never through sizing.
    Flipping EQUAL_WEIGHT_BOOKS off makes this cap LIVE, which is a sizing change: read the
    FORK-2 note in CLAUDE.md first.

    Mechanics when it is live: an AGGREGATE-EXPOSURE judgement, never an eligibility one —
    the LOWEST-conviction story seats are trimmed toward a 0.1-unit floor and emitted as
    single-name caps; demotion belongs to the skeptic/numeric gates. Proportional scaling is
    deliberately NOT used: it would cut the strongest story seat as hard as the weakest.

    cash_now_min and real_asset_floor are WARN/advisory — a cap cannot conjure names that
    are not seated. UNKNOWN phase carries the loosest caps (fail-open)."""
    cycle = cycle or {}
    phase = cycle.get("debt_cycle_phase") or "UNKNOWN"
    caps = cycle.get("duration_caps") or {}
    if not caps:
        from debt_cycle import PHASE_DURATION_CAPS
        caps = PHASE_DURATION_CAPS.get(phase, PHASE_DURATION_CAPS["UNKNOWN"])
    advisory = bool(getattr(_pc, "EQUAL_WEIGHT_BOOKS", False))
    apx["debt_cycle_phase_applied"] = phase
    apx["duration_caps_applied"] = caps
    # "advisory" = trims units + audit trail only; "live" = also moves published weight.
    apx["duration_cap_effect"] = "advisory" if advisory else "live"
    entries, binding, warnings = [], [], []
    # Basis = the effective units from the first build_weights pass (post moat/theme teeth).
    units = {p["symbol"]: float(p.get("size_units_effective") or 0) for p in picks}
    tot = sum(units.values())
    if not picks or tot <= 0:
        apx["cap_binding"] = binding
        return entries

    smax = caps.get("story_max")
    # ONLY measured-story names are capped. 'unknown' (no FCF data in the scan record)
    # is deliberately outside the cap — see debt_cycle.duration_bucket: collapsing
    # no-data into story let a thin scan pin the whole book to the 0.1u floor.
    story = [p for p in picks if p.get("duration_bucket") == "story"]
    n_unknown = sum(1 for p in picks if p.get("duration_bucket") == "unknown")
    if n_unknown:
        warnings.append(f"{n_unknown}/{len(picks)} seats have NO FCF data (duration_bucket=unknown) "
                        f"— excluded from the story cap (fail-open); check scan freshness")
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
                    entries.append({"names": [p["symbol"]], "max_units": round(u - cut, 3),
                                    "axis": "duration:story"})
                    p["cycle_capped"] = True
                    p["cycle_cap_note"] = (
                        f"{phase} duration cap: {cut:.2f}u trimmed (story <= {smax:.0%} of book)"
                        + (" — ADVISORY only, the book publishes equal weight so this seat's "
                           "published weight is unchanged" if advisory else ""))
                    p["cycle_cap_effect"] = "advisory" if advisory else "live"
                    need -= cut
            binding.append("duration_story")
            if need > 1e-9:
                warnings.append(f"story legs all at 0.1u floor and still {need:.2f}u over the "
                                f"{phase} story cap — floor respected, residual overage published")
            print(f"duration-cap [{'ADVISORY — no published weight moves' if advisory else 'LIVE'}]: "
                  f"{phase} story<= {smax:.0%} BOUND — units trimmed on "
                  f"{[p['symbol'] for p in story if p.get('cycle_capped')]}")

    cmin = caps.get("cash_now_min")
    if isinstance(cmin, (int, float)) and tot > 0:
        c_share = sum(units[p["symbol"]] for p in picks if p.get("duration_bucket") == "cash_now") / tot
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
    return entries


def process(apx, uni, scan_by, market=None):
    """Consume the apex skeptic + numeric gate, clamp conviction, stamp the moat teeth, enforce the
    secular-theme + Director combined caps (+ measured correlation caps when `market` is supplied),
    and build weights. Mutates + returns (apx, picks, extra). Pure when market=None — safe on an
    in-memory copy with no network (test_regime_post baseline unchanged)."""
    _pc.apply_skeptic_corrections(SKEP_DIR, RES_DIR,          # Tier-1 write-back: typed corrections
                                  quadrant=apx.get("regime_quadrant"))   # -> records, before verdicts
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
    # payback-speed label, derive the phase story-cap from the FIRST weight pass, then
    # re-run build_weights with those caps appended — one normalization path, no bespoke
    # re-normalization. Fail-open: missing snapshot => UNKNOWN => loosest caps.
    stamp_duration_buckets(picks, scan_by)
    _cycle = (_load(ROOT / "macro_regime.json", {}) or {}).get("debt_cycle") or {}
    stamp_cycle_fit(picks, _cycle)              # which phase each payoff NEEDS vs where we are
    _dur = duration_cap_entries(apx, picks, _cycle)
    if _dur:
        extra = extra + _dur
        weights = _pc.build_weights(apx, picks, extra_caps=extra, memo_units=memo,
                                    per_name_cap=_pc.moat_per_name_cap)
        apx["weights"] = weights
        apx["secular_theme_caps"] = extra
    if market:
        quotes, weekly_rets, asof = market
        apx["stress_test"] = _pc.stress_block(picks, weights, quotes, asof,
                                              bear_px=lambda p: p.get("bear_fv_px"),
                                              bear_label="valuation.bear_px")
        apx["exits"] = _pc.exits_block(picks, quotes, thesis_break=lambda p: p.get("thesis_break_px"),
                                       fair_value=lambda p: p.get("base_fv_px"))
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
