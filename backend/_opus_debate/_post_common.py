#!/usr/bin/env python3
"""Shared post-processing primitives for BOTH the value apex (_value_post.py) and the regime/apex
book (_regime_post.py): the skeptic kill-tier, the weight builder (with the moat-erosion + combined
caps), and the deterministic secular-theme concentration cap. Factored out so the two books run ONE
implementation - a skeptic that demotes and a cap loop that sizes, identical across surfaces.

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
    providers, cache path, bear-px getter, benchmark symbol) - this module stays free of import side
    effects (no FMP/screener_v6 import; the caller injects its fetchers).
"""
import json
import re
import math
import statistics
from datetime import datetime as _dt
from pathlib import Path


# STEP-3a entry-discount floor, mirrored from the Director prompt (weekly_opus_refresh STEP 3a,
# 2026-07-24): the bar a NEW seat's computed expected return must clear, scaled by the quadrant.
# Used here only by the numbers-scope repricing branch below - keep the two in sync.
_ENTRY_FLOOR_PCT = {"GOLDILOCKS": 20.0, "REFLATION": 20.0, "STAGFLATION": 25.0, "RISK_OFF": 30.0}

# FOUR-QUESTION CRO GRADE (2026-10-06, Bruno). The regime-lane CRO answers Q1 THESIS (thesis_state),
# Q2 VALUATION (the typed block), Q3 ENTRY (entry_mode + level/event) and Q4 FIT (context only); the
# A/B/C letter is DERIVED by derive_grade() below from thesis_state x entry_mode + the entry floor
# above. Records without the typed fields keep their agent letter (fail-open, legacy path).
THESIS_STATES = ("INTACT", "IMPAIRED", "BROKEN")
ENTRY_MODES = ("NOW", "AT_LEVEL", "ON_EVENT", "NONE")
WASHOUT_TYPES = ("MECHANICAL", "FACTOR", "NONE")
GRADE_SCHEMA = "v2-4q"


def entry_floor_pct(q):
    """The STEP-3a entry floor (%) for a quadrant. UNKNOWN / missing -> 20, the loosest bar (fail-open)."""
    return _ENTRY_FLOOR_PCT.get(str(q or "").upper(), 20.0)


def current_quadrant(root):
    """The live quadrant from <root>/macro_regime.json, or None on any failure (entry_floor_pct(None)
    then gives the loosest 20% bar - a missing snapshot must never tighten the book)."""
    try:
        m = json.load(open(Path(root) / "macro_regime.json", encoding="utf-8"))
        q = m.get("quadrant") or m.get("regime_quadrant")
        return str(q).strip().upper() if q else None
    except Exception:
        return None


def _record_live_px(records_dir, sym):
    """Live price from the debate record (valuation block preferred) - the pipeline's own number,
    never the skeptic's, so a fabricated quote can't game the repricing branch."""
    try:
        rec = json.load(open(Path(records_dir) / f"{sym}.json", encoding="utf-8"))
        px = (rec.get("valuation") or {}).get("live_price") or rec.get("live_price")
        return float(px) if isinstance(px, (int, float)) and px > 0 else None
    except Exception:
        return None


def _persist_revision(records_dir, sym, fv, er_pct):
    """Write the skeptic's re-derived fair value INTO the debate record (additive key) so the next
    cycle's carry/skeptic/Director anchor on the corrected number instead of the refuted one -
    the WKL.AS failure mode: the EUR 82 re-derivation lived only in kill_fact prose and the record
    still said EUR 92 the following week."""
    try:
        fp = Path(records_dir) / f"{sym}.json"
        rec = json.load(open(fp, encoding="utf-8"))
        rec["skeptic_revision"] = {"fv_px": float(fv), "er_pct": round(er_pct, 1),
                                   "kill_scope": "numbers", "at": _dt.now().strftime("%Y-%m-%d")}
        fp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"WARN skeptic: could not persist revised FV for {sym} ({e})")


# Valuation levels the skeptic may correct via corrections_typed. Deliberately ONLY the typed
# levels the agents own - inputs (net debt, shares, EBITDA anchors) live in prose, so a correction
# to an input must be carried through to the level by the skeptic ("state the LEVEL, the pipeline
# computes every ratio"). live_price is the pipeline's and is never correctable.
_CORRECTABLE_FIELDS = ("bear_px", "base_fv_px", "bull_px", "downside_floor_px")


def _crossed(pre, post, threshold):
    """True when a value moved across a threshold in either direction (verdict-relevant flip)."""
    if not isinstance(pre, (int, float)) or not isinstance(post, (int, float)):
        return False
    return (pre >= threshold) != (post >= threshold)


def apply_skeptic_corrections(shards_dir, records_dir, quadrant=None, revise_cap=8):
    """Tier-1 write-back (2026-08-05, Bruno: 'the skeptic note is useless if nothing feeds back -
    what I need is a reliable debate whose conclusion reads trustworthy numbers'). Apply each
    shard's typed corrections to the record's valuation block (originals preserved as <field>_orig,
    audit trail in skeptic_corrections_applied), then re-run the SAME deterministic machinery as
    `numeric-gate --enforce` over the corrected levels: computed{} (rr/ER/floor-distance) is
    recomputed and diverging prose R:R is rewritten with _orig kept. The Director, the gates and
    the stock page then all read ONE internally consistent set of numbers - the skeptic note
    becomes an audit line instead of a contradiction (the GPOR case: bear_px 130 -> 120, so the
    published rr 1.23 was arithmetically dead on the record's own bear math).

    Returns (applied_syms, revise_needed): revise_needed is the Tier-2 trigger list - material
    CONFIRMED_WITH_CORRECTIONS shards whose corrected arithmetic flips a verdict-relevant
    threshold (rr across 1.0, ER across the quadrant entry floor). REFUTED names are NEVER on it:
    a kill is a judgement, not an arithmetic slip (2026-07-27 repair taxonomy) - their records
    still get the level corrections, but the prose/grade is not revised.

    Idempotent: an already-applied correction (valuation[field] == to) is skipped; a prior-week
    stale shard never rewrites a fresh record; legacy records without a typed valuation block are
    left alone (low-confidence prose-mining must never masquerade as typed)."""
    shards_dir, records_dir = Path(shards_dir), Path(records_dir)
    applied, revise = [], []
    if not shards_dir.is_dir() or not records_dir.is_dir():
        return applied, revise
    try:
        import _numeric_gate as _ng
    except Exception:
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            import _numeric_gate as _ng
        except Exception:
            _ng = None
    floor = _ENTRY_FLOOR_PCT.get(str(quadrant or "").upper(), 20.0)
    for sf in sorted(shards_dir.glob("*.json")):
        try:
            sh = json.load(open(sf, encoding="utf-8"))
        except Exception:
            continue
        sym, cts = sh.get("symbol"), sh.get("corrections_typed")
        if not sym or not isinstance(cts, list) or not cts:
            continue
        rf = records_dir / f"{sym}.json"
        if not rf.exists():
            continue
        if sf.stat().st_mtime < rf.stat().st_mtime - 86400:
            continue   # prior-week shard vs a fresh record: never apply stale corrections
        try:
            rec = json.load(open(rf, encoding="utf-8"))
        except Exception:
            continue
        val = rec.get("valuation")
        if not isinstance(val, dict):
            continue   # legacy record: no typed block to correct
        audit = rec.get("skeptic_corrections_applied") or []
        pre = dict(rec.get("computed") or {})
        changed = False
        for c in cts:
            if not isinstance(c, dict):
                continue
            fld, to = c.get("field"), c.get("to")
            if fld not in _CORRECTABLE_FIELDS or not isinstance(to, (int, float)) or to <= 0:
                continue
            cur = val.get(fld)
            if cur == to:
                continue   # idempotent re-run
            if f"{fld}_orig" not in val and cur is not None:
                val[f"{fld}_orig"] = cur   # never clobber the true original on re-apply
            val[fld] = float(to)
            audit.append({"field": fld, "from": cur, "to": float(to),
                          "basis": str(c.get("basis") or "")[:300],
                          "at": _dt.now().strftime("%Y-%m-%d")})
            changed = True
        if not changed:
            continue
        rec["skeptic_corrections_applied"] = audit
        if _ng is not None:
            try:
                res = _ng.check_record(rec)
                # NEVER UPGRADE (2026-10-06): this recompute has no live quotes and no scan, so it
                # cannot see G1A (price), G1B (currency) or GQ (coverage). Re-stamping its result
                # silently laundered real REJECT/EXCLUDE stamps to PASS (APP, FICO, BLDR, LYFT,
                # ZEAL.CO on 2026-10-05) - and value-input now shows the stamp to the Director.
                # Keep the prior gate when it rested on one of those codes; append the new reasons.
                _prior_gate = str(rec.get("numeric_gate") or "")
                _prior_rs = [str(r) for r in (rec.get("numeric_gate_reasons") or [])]
                _ext = [r for r in _prior_rs if r.startswith(("G1A_PRICE_MISMATCH", "G1B_", "GQ_"))]
                _rank = {"PASS": 0, "WARN": 1, "EXCLUDE_ELIGIBILITY": 2, "REJECT": 3}
                if _ext and _rank.get(_prior_gate, 0) > _rank.get(res["gate"], 0):
                    res = {**res, "gate": _prior_gate,
                           "reasons": _ext + [r for r in res["reasons"] if r not in _ext]}
                rec["numeric_gate"] = res["gate"]
                rec["numeric_gate_reasons"] = list(res["reasons"])
                rec["computed"] = {k: v for k, v in res["computed"].items()
                                   if k in _ng.COMPUTED_STAMP_KEYS and v is not None}
                if any(r.startswith("PROSE_RR_KILLED") for r in res["reasons"]) and not rec.get("carried"):
                    if "risk_reward_prose_orig" not in rec:
                        rec["risk_reward_prose_orig"] = rec.get("risk_reward")
                    rec["risk_reward"] = _ng._rr_display(rec.get("valuation") or {},
                                                         res["computed"], res["reasons"])
            except Exception as e:
                print(f"WARN skeptic-apply: recompute failed for {sym} ({e}) - levels applied, "
                      f"computed{{}} left as-was")
        # FOUR-QUESTION GRADE (2026-10-06): a corrected base_fv_px / bear_px can move the derived
        # letter (the ER crosses the entry floor, or an add level now sits at/below the exit), so
        # re-derive on the corrected record. Legacy records (no thesis_state/entry_mode) are left
        # untouched by derive_grade; any failure leaves the letter as-was (fail-open).
        try:   # the value book passes no quadrant: read the live one next to the records (None -> 20%)
            derive_grade(rec, quadrant=quadrant or current_quadrant(records_dir.parent))
        except Exception as e:
            print(f"WARN skeptic-apply: grade re-derive failed for {sym} ({e}) - letter left as-was")
        rf.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        applied.append(sym)
        post = rec.get("computed") or {}
        flips = (_crossed(pre.get("rr_ratio"), post.get("rr_ratio"), 1.0)
                 or _crossed(pre.get("expected_return_pct"), post.get("expected_return_pct"), floor))
        if (str(sh.get("verdict") or "").upper() == "CONFIRMED_WITH_CORRECTIONS"
                and sh.get("correction_severity") == "material" and flips):
            revise.append(sym)
        print(f"skeptic-apply: {sym} - {len([a for a in audit if a.get('at') == _dt.now().strftime('%Y-%m-%d')])} "
              f"correction(s) applied | rr {pre.get('rr_ratio')} -> {post.get('rr_ratio')} | "
              f"ER {pre.get('expected_return_pct')} -> {post.get('expected_return_pct')}"
              + (" | REVISE (verdict-relevant flip)" if sym in revise else ""))
    if len(revise) > revise_cap:
        print(f"skeptic-apply: revise list capped at {revise_cap} (dropped: {revise[revise_cap:]})")
        revise = revise[:revise_cap]
    return applied, revise


def consume_skeptic(apx, apex_file: Path, skep_dir: Path, conviction_field: str = "value_conviction_cap",
                    records_dir: Path = None):
    """Merge skep_dir/<SYM>.json shards -> sidecar <skep_dir>_results.json and apply the verdicts.
    REFUTED demotes the apex member to the front of runner_ups; CONFIRMED_WITH_CORRECTIONS stamps the
    correction + conviction cap. Idempotent: re-running re-applies the same verdicts to the same members.
    records_dir: where the debate records live (default <apex dir>/results_regime) - used by the
    numbers-scope repricing branch for the live price + revised-FV write-back."""
    skep_dir = Path(skep_dir)
    apex_file = Path(apex_file)
    records_dir = Path(records_dir) if records_dir else (apex_file.parent / "results_regime")
    if not skep_dir.is_dir():
        return apx
    # ANCHOR (2026-07-24): freshness is measured against the DIRECTOR's write, not the file's mtime.
    # The post layer rewrites this same file, so using mtime meant every re-run pushed the anchor
    # forward and re-aged its own inputs - run the post layer twice and same-day shards flipped to
    # "stale". post_anchor_ts is stamped once, on the first post-processing after a Director write
    # (a fresh Director file has no stamp, so a genuinely new run re-anchors correctly).
    apex_mtime = apex_file.stat().st_mtime if apex_file.exists() else 0
    if isinstance(apx.get("post_anchor_ts"), (int, float)):
        apex_mtime = apx["post_anchor_ts"]
    else:
        apx["post_anchor_ts"] = apex_mtime
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
                if d.get("symbol"):                      # remember stale verdicts - a stale REFUTED
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
    # COVERAGE - fail LOUD, not open (the 06-30 apex + EEFT/HRMY value book shipped with zero fresh
    # shards and this function returned silently). Every apex member without a FRESH shard is stamped
    # skeptic_verdict=MISSING (+ skeptic_missing=True -> half-sized by moat_per_name_cap); a STALE
    # REFUTED on a still-held member is stamped skeptic_stale_refuted (half-size + re-run flag), never
    # silently ignored. Publish stays possible (partial runs are the ops norm) - visible and priced.
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
    # re-reads the apex JSON it previously stamped - so a name flagged by an early run stayed
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
        # moat_per_name_cap - a haircut, never a hard ceiling (the proven numeric-cap bug class).
        if v.get("correction_severity"):
            p["correction_severity"] = v["correction_severity"]
        if v.get("kill_scope"):
            p["skeptic_kill_scope"] = v["kill_scope"]
        if v.get("carried_from_book"):
            p["skeptic_carried_from"] = v["carried_from_book"]
        if isinstance(v.get(conviction_field), (int, float)):   # legacy shards only (pre-X1)
            p[conviction_field] = v[conviction_field]
        if (v.get("verdict") or "").upper() == "REFUTED":
            # REPRICING BRANCH (2026-08-03, the WKL.AS case). kill_scope "numbers" + a typed
            # revised_fv_px means the skeptic RE-DERIVED the fair value rather than falsifying the
            # thesis - the record's SoP was wrong by an amount, not wrong in kind. Before this
            # branch, a name repriced EUR 92 -> EUR 82 (still cheap, just less cheap) was demoted
            # byte-identically to one whose thesis was false, and the EUR 82 evaporated into
            # kill_fact prose. Now: re-grade the seat on the skeptic's own number against the
            # STEP-3a entry floor. Clears it -> the seat SURVIVES at the material 0.75u haircut
            # (moat_per_name_cap). Fails it -> demoted as before, but for the stated numeric
            # reason. Either way the revised FV persists (pick + record) as next cycle's anchor.
            # thesis/moat/catalyst kills, and a numbers kill WITHOUT the typed number, demote
            # exactly as before - fail-safe, never fail-open.
            rev = v.get("revised_fv_px")
            live = (_record_live_px(records_dir, p["symbol"])
                    if v.get("kill_scope") == "numbers" and isinstance(rev, (int, float)) and rev > 0
                    else None)
            if live:
                rev_er = (float(rev) / live - 1.0) * 100.0
                floor = _ENTRY_FLOOR_PCT.get(str(apx.get("regime_quadrant") or "").upper(), 20.0)
                p["skeptic_revised_fv"] = float(rev)
                p["skeptic_revised_er_pct"] = round(rev_er, 1)
                _persist_revision(records_dir, p["symbol"], rev, rev_er)
                if rev_er >= floor:
                    p["skeptic_repriced"] = True
                    p["correction_severity"] = "material"   # bounded 0.75u haircut, never a ceiling
                    keep.append(p)
                    print(f"WARN skeptic: {p['symbol']} REFUTED/numbers -> REPRICED, seat kept | "
                          f"revised fv {rev} vs live {live} = ER {rev_er:+.1f}% clears the "
                          f"{floor:.0f}% floor | material haircut applies | "
                          f"kill_fact: {str(v.get('kill_fact', ''))[:120]}")
                    continue
                p["skeptic_refuted"] = True
                demoted.append(p)
                print(f"WARN skeptic: {p['symbol']} REFUTED/numbers -> DEMOTED | revised fv {rev} "
                      f"vs live {live} = ER {rev_er:+.1f}% under the {floor:.0f}% floor | "
                      f"kill_fact: {str(v.get('kill_fact', ''))[:120]}")
                continue
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
        # MEMO-CONSISTENCY GUARD (2026-08-25, the NTES incident). A demotion here moves the OBJECT
        # but cannot rewrite the Director's PROSE: on 2026-08-24 NTES was demoted while the memo
        # still read "NTES: KEEP ... Kept at a half unit" and its runner-up thesis still said "that
        # is why the seat stays a half unit" - the published artifact contradicted its own book.
        # The real fix is ordering (the kill-tier now runs BEFORE the value Director), so reaching
        # this branch means a kill landed late and the memo is stale by construction. Stamp the
        # contradiction into the artifact rather than letting a reader trust the prose.
        _names = ", ".join(sorted(dsyms))
        _note = ("[POST-LAYER CORRECTION - " + _dt.now().strftime("%Y-%m-%d") + "] The skeptic "
                 "kill-tier demoted the following name(s) to runner-ups AFTER this memo was "
                 "written: " + _names + ". Any sentence below that describes one of them as "
                 "seated, sized, or kept is superseded - the apex_basket field above is the book. "
                 "Reason(s): "
                 + " | ".join(f"{d.get('symbol')}: {str((merged.get(d.get('symbol')) or {}).get('kill_fact', ''))[:200]}"
                              for d in demoted) + "\n\n")
        for _mk in ("value_memo", "director_memo", "fr_memo", "mining_memo", "fdt_memo"):
            if isinstance(apx.get(_mk), str) and apx[_mk]:
                apx[_mk] = _note + apx[_mk]
                break
        apx["skeptic_demoted_post_memo"] = sorted(dsyms)
        for _d in demoted:                       # strip seat language from the demoted entry itself
            _d["demoted_by_skeptic"] = True
            _d["seat_status"] = "NOT SEATED - refuted by the skeptic after the Director wrote"
        print(f"WARN memo-consistency: stamped a post-layer correction into the memo for {_names} "
              f"(the Director's prose predates this kill)")
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
    PUBLISHED weight_pct is 1/n - see the note above."""
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
    # Skeptic-coverage teeth apply to EVERY seat, lanes included - an un-vetted seat is half-sized.
    if p.get("skeptic_missing") or p.get("skeptic_stale_refuted"):
        return min(u, 0.5)
    # Unified-skeptic MATERIAL correction (a load-bearing number/date/anchor moved): a BOUNDED
    # 3/4 haircut - consequences without the numeric-cap-as-ceiling bug class (X1/VB-P5).
    if p.get("correction_severity") == "material":
        u = min(u, 0.75)
    # LANE CONTRACT: an equity special-sit seat is EVENT-driven - the Director's STEP-3b exempted it
    # from the compounder moat/erosion teeth, and the publish layer already floor-sizes it harder
    # (1.5% risk-to-floor). Applying the moat half-cap here would contradict that contract.
    if p.get("lane") == "equity_special_sit":
        return u
    # 2026-07-21 #4: the value post stamps washout_moat_exception (deep drawdown + NARROW/WIDE moat
    # + non-eroding trend) - it relaxes ONLY the moat CAP half-size to 0.75; cro_only/stale_anchor
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
    real weight - banded steps make small re-grades weight-invisible; only a band CROSSING (a
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


# TRIM RULE (2026-07-24, Bruno). Both books had a FLOOR (thesis break) and no CEILING: a name could
# grind from deeply discounted to fully valued and nothing ever fired, because the only exit test was
# "is the thesis broken?" - it isn't, so it is held. Observed live: EEFT rode its cushion from ~44%
# down to ~9% and was still KEEP. Trimming at a fraction of base fair value banks the win the
# discount-closing thesis actually predicted, without needing the thesis to break first.
TRIM_AT_FRAC = 0.85          # price >= 85% of base fair value -> TRIM (the discount has mostly closed)


def exits_block(picks, quotes, thesis_break, fair_value=None):
    """Exit plan per seat: a FLOOR (thesis break) and, when a fair value is supplied, a CEILING
    (trim level). Both sanity-checked against the live price. thesis_break(p) / fair_value(p) are
    CALLER-SUPPLIED getters so each book maps its own fields."""
    out = {}
    for p in picks:
        sym = p["symbol"]
        px = (quotes.get(sym) or {}).get("price")
        tb = thesis_break(p)
        valid = isinstance(tb, (int, float)) and isinstance(px, (int, float)) and 0 < tb < px
        fv = fair_value(p) if fair_value else None
        # fair value must be a positive number in the SAME ballpark as the quote - this is the guard
        # that catches unit/currency slips (a 21 "target" on a $291 stock, an 8 on a 7,310 yen name).
        fv_ok = (isinstance(fv, (int, float)) and fv > 0 and isinstance(px, (int, float)) and px > 0
                 and 0.2 < px / fv < 5)
        trim = round(fv * TRIM_AT_FRAC, 4) if fv_ok else None
        action = "HOLD"
        if valid and px <= tb:
            action = "EXIT_REVIEW"                     # floor breached - the thesis is on the clock
        elif trim is not None and px >= trim:
            action = "TRIM"                            # ceiling reached - bank part of the re-rate
        out[sym] = {"thesis_break_px": tb if valid else None, "valid": bool(valid),
                    "fair_value_px": fv if fv_ok else None, "trim_at_px": trim,
                    "pct_of_fair_value": round(px / fv, 3) if fv_ok else None,
                    "action": action,
                    "review_trigger": "weekly refresh OR close < thesis_break_px OR close >= trim_at_px"}
        p["trim_at_px"] = trim
        p["exit_action"] = action
        if tb and not valid:
            print(f"WARN exits: {sym} thesis_break_px={tb} fails sanity vs px={px}")
        if fv is not None and not fv_ok:
            print(f"WARN exits: {sym} fair_value={fv} implausible vs px={px} - no trim level set")
    n_trim = sum(1 for v in out.values() if v["action"] == "TRIM")
    n_exit = sum(1 for v in out.values() if v["action"] == "EXIT_REVIEW")
    if n_trim or n_exit:
        print(f"exits: {n_trim} at/above the trim level, {n_exit} below the thesis break "
              f"-> {[s for s, v in out.items() if v['action'] != 'HOLD']}")
    return out


# ── FOUR-QUESTION GRADE DERIVATION (2026-10-06, Bruno) ───────────────────────────────────────────
# The regime CRO no longer owns the letter: it answers thesis_state (Q1) and entry_mode + level/event
# (Q3), and the letter follows by rule. Approved mapping:
#   A = INTACT + NOW                   B price = INTACT + AT_LEVEL
#   B proof = IMPAIRED + ON_EVENT      B event = INTACT + ON_EVENT
#   C = BROKEN (any entry) or entry NONE
# Coercions (each stamps grade_flags): IMPAIRED + NOW / AT_LEVEL -> ON_EVENT on thesis_test.resolves_on
# (B proof), or C when there is no test; an add level at/below the exit -> base_fv/(1+floor) when that
# is above the exit, else C; a NOW whose discount is below the quadrant entry floor -> B price at
# base_fv/(1+floor), or C when that price is at/below the exit. WASH-OUT (the price the committee
# waited for arrived): a second price-wait is coerced (INTACT -> NOW), and a NOW that fails the floor
# at the wash-out is C - never another level. A C that is the CRO's own answer (BROKEN, entry NONE,
# IMPAIRED with no test) caps conviction at 2 so a pass can never clear the Director's conviction >= 3
# bar. macro_fit and the debt-cycle phase are NEVER read here
# REVIEW FIXES (2026-10-06, Bruno's P1-P7):
#  P1 only LEVEL_REACHED forbids a second price-wait. A 10% FALL with the price still above the level
#     named last time (or with no named level) may keep AT_LEVEL at or below that level, and a proof /
#     event wait may keep ON_EVENT - no SECOND_PRICE_WAIT coercion, no WASHOUT_BELOW_FLOOR there.
#  P2 an AT_LEVEL level must itself clear the floor (else base_fv/(1+floor) when that is above the
#     exit - LEVEL_FAILS_FLOOR - or C NO_BUYABLE_PRICE) and sit below the live price (at or above it the
#     wait is met: NOW, and the floor check decides - LEVEL_AT_OR_ABOVE_PRICE).
#  P3 a C that comes only from price or the quadrant floor (NO_BUYABLE_PRICE, WASHOUT_BELOW_FLOOR /
#     PASS_BELOW_FLOOR) keeps the letter C as "not a buy" but NEVER touches conviction - the macro
#     quadrant can never push a held seat out of the book (CLAUDE.md: macro never moves conviction).
#  P7 the effective entry_level_px is stored as the parsed number ("HK$35.8" -> 35.8).
# (CLAUDE.md FORK 2/B): the quadrant floor is the one sanctioned macro bar, and an UNKNOWN quadrant,
# a missing price or a missing fair value never tightens anything.
_GRADE_SKIP_LANES = ("equity_special_sit", "special_sit")     # B13 event lane - its own rubric
_GRADE_SKIP_SOURCES = ("opus_catalyst", "ledger_recheck")      # B13 + forensic re-checks keep their letter
# flags that mean the code changed what the CRO answered (the rest are warnings that change nothing)
_GRADE_COERCIONS = ("BROKEN_WITH_ENTRY", "SECOND_PRICE_WAIT_COERCED", "IMPAIRED_ENTRY_COERCED",
                    "IMPAIRED_ENTRY_NO_TEST", "LEVEL_REPLACED", "NO_BUYABLE_PRICE", "WASHOUT_BELOW_FLOOR",
                    "FLOOR_REDERIVED", "LEVEL_FAILS_FLOOR", "LEVEL_AT_OR_ABOVE_PRICE", "WASHOUT_LEVEL_CAPPED")


def _pos_num(x):
    v = _num(x)
    return v if v is not None and v > 0 else None


def _grade_exit_px(rec):
    """The record's exit level: the highest typed price at which the thesis is on the clock
    (valuation.bear_px, valuation.downside_floor_px, a record-level thesis_break_px). None if none."""
    val = rec.get("valuation") if isinstance(rec.get("valuation"), dict) else {}
    lv = [v for v in (_pos_num(val.get("bear_px")), _pos_num(val.get("downside_floor_px")),
                      _pos_num(rec.get("thesis_break_px"))) if v]
    return max(lv) if lv else None


def _grade_er(rec, base, live_px=None):
    """(expected return % of base_fv_px over the live price, the price used). Price order: the
    caller's live quote, the record's top-level live_price (restamped by every carry), the debate's
    own valuation.live_price; else the numeric gate's computed.expected_return_pct. (None, None) when
    nothing is usable - fail-open: a missing price never re-derives a letter. A price more than 5x
    away from the fair value is a unit slip (GBp vs GBP) and is skipped."""
    val = rec.get("valuation") if isinstance(rec.get("valuation"), dict) else {}
    if base:
        for px in (live_px, rec.get("live_price"), val.get("live_price")):
            px = _pos_num(px)
            if px and 0.2 < px / base < 5:
                return round((base / px - 1.0) * 100.0, 2), px
    comp = rec.get("computed") if isinstance(rec.get("computed"), dict) else {}
    er = comp.get("expected_return_pct")
    if isinstance(er, (int, float)) and not isinstance(er, bool):
        return float(er), None
    return None, None


def _thesis_test_ok(tt):
    return isinstance(tt, dict) and all(tt.get(k) not in (None, "")
                                        for k in ("metric", "pass_level", "fail_level", "resolves_on"))


def derive_grade(rec, quadrant=None, live_px=None, washout=None, today=None):
    """Derive the A/B/C letter of a regime debate record from its typed four-question fields, IN PLACE.

    quadrant  - macro_regime.json quadrant (None/UNKNOWN -> the loosest 20% floor);
    live_px   - optional live quote (else the record's live_price / valuation.live_price / computed ER);
    washout   - this run's prep-bundle washout block when the record IS the wash-out debate.

    Legacy path: a record without a valid thesis_state + entry_mode (or a B13 / ledger-recheck record)
    is returned untouched ({"verdict_source": "agent_legacy"}) - it keeps its agent letter.
    Otherwise stamps verdict (final), verdict_structural (before the price re-derive), verdict_agent_orig
    (the CRO's own letter, set once), verdict_source "derived", wait_kind (price|proof|event, B only),
    grade_flags, grade_rederived (+ entry_level_px_derived), grade_schema, entry_floor_pct; coerced
    effective entry_mode / entry_level_px / entry_event with the CRO's originals in *_agent_orig and
    grade_basis (so a re-run recomputes from the same inputs - idempotent - while a Revise / delta
    rewrite of the fields is taken as the new input). A wash-out resolution is persisted into
    washout_resolution (stamped_by grade-derive). A C that is the CRO's own answer (BROKEN, entry NONE,
    IMPAIRED with no test) caps conviction at 2 (conviction_agent_orig kept); a C from price or the
    quadrant floor leaves conviction alone (P3). Never reads macro_fit or the debt cycle."""
    if not isinstance(rec, dict):
        return {"verdict_source": "agent_legacy"}
    lane = str(rec.get("lane") or "").strip().lower()
    src = str(rec.get("source") or "").strip().lower()
    if lane in _GRADE_SKIP_LANES or src.startswith(_GRADE_SKIP_SOURCES):
        return {"verdict_source": "agent_legacy", "skipped": lane or src}
    # INPUTS = the CRO's own answers. When an earlier pass coerced them and nothing has touched the
    # record since, read the originals back from grade_basis; otherwise the record's values ARE the input.
    cur = [rec.get("thesis_state"), rec.get("entry_mode"), rec.get("entry_level_px"), rec.get("entry_event")]
    basis = rec.get("grade_basis") if isinstance(rec.get("grade_basis"), dict) else None
    if basis and isinstance(basis.get("in"), list) and len(basis["in"]) == 4 and cur == basis.get("out"):
        ts_in, em_in, lvl_in, ev_in = basis["in"]
    else:
        ts_in, em_in, lvl_in, ev_in = cur
    ts = str(ts_in or "").strip().upper()
    em = str(em_in or "").strip().upper()
    if ts not in THESIS_STATES or em not in ENTRY_MODES:
        return {"verdict_source": "agent_legacy"}
    today = today or _dt.now().strftime("%Y-%m-%d")
    floor = entry_floor_pct(quadrant)
    quad = str(quadrant or "").strip().upper() or "UNKNOWN"
    val = rec.get("valuation") if isinstance(rec.get("valuation"), dict) else {}
    base = _pos_num(val.get("base_fv_px"))
    exit_px = _grade_exit_px(rec)
    floor_px = round(base / (1.0 + floor / 100.0), 4) if base else None
    tt = rec.get("thesis_test") if isinstance(rec.get("thesis_test"), dict) else None
    tt_event = str((tt or {}).get("resolves_on") or "").strip()
    tt_metric = str((tt or {}).get("metric") or "").strip()
    rec.setdefault("verdict_agent_orig", rec.get("verdict"))
    flags = []
    wr = rec.get("washout_resolution") if isinstance(rec.get("washout_resolution"), dict) else None
    wo_now = isinstance(washout, dict) and bool(washout)              # this IS the wash-out debate
    wo_ctx = wo_now or bool(wr and wr.get("stamped_by") == "grade-derive")
    if wr and not wo_ctx:
        flags.append("WASHOUT_RESOLUTION_WITHOUT_TRIGGER")            # agent-written, no trigger: ignored
    # P1: which trigger. LEVEL_REACHED (the price reached the level the committee named) forbids a second
    # price-wait. A 10% FALL whose price is still above the level named last time (or with no named
    # level: an older B, a proof or an event wait) does not - the wait may be kept at or below that level.
    # Read from this run's bundle, else from the resolution an earlier pass persisted (later re-derives).
    _wsrc = (washout if wo_now else wr) if wo_ctx else {}
    wo_level, wo_px = (_pos_num(_wsrc.get("level")), _pos_num(_wsrc.get("price"))) if wo_ctx else (None, None)
    wo_fall = wo_ctx and (_wsrc.get("level_source") == "fall_10pct" or _wsrc.get("trigger_kind") == "FELL_10PCT")
    if wo_fall and wo_level is not None and wo_px is not None and wo_px <= wo_level:
        wo_fall = False                                               # the fall reached the level: it IS the level
    wo_reached = wo_ctx and not wo_fall

    # (ii) structural letter, with the approved coercions
    em_eff, lvl, ev = em, _pos_num(lvl_in), str(ev_in or "").strip()
    if ts == "BROKEN":
        if em != "NONE":
            flags.append("BROKEN_WITH_ENTRY")
        em_eff = "NONE"
    if wo_reached and em_eff == "AT_LEVEL":
        flags.append("SECOND_PRICE_WAIT_COERCED")                     # resolve the wait, never extend it
        if ts == "INTACT":
            em_eff = "NOW"
    if ts == "IMPAIRED" and em_eff in ("NOW", "AT_LEVEL"):
        if tt_event or tt_metric:                                     # an impaired thesis waits for its proof
            flags.append("IMPAIRED_ENTRY_COERCED")
            em_eff = "ON_EVENT"
            ev = tt_event or f"the thesis test ({tt_metric})"
        else:
            flags.append("IMPAIRED_ENTRY_NO_TEST")
            em_eff = "NONE"
    if em_eff == "ON_EVENT" and not ev:
        if tt_event:
            ev = tt_event
            flags.append("EVENT_FROM_THESIS_TEST")
        else:
            flags.append("ENTRY_EVENT_MISSING")
    if ts == "IMPAIRED" and not _thesis_test_ok(tt):
        flags.append("THESIS_TEST_MISSING")                           # (iii) warn only - never tightens
    wkind, lvl_pre = None, None
    if em_eff == "NONE":
        letter = "C"
    elif em_eff == "NOW":
        letter = "A"
    elif em_eff == "ON_EVENT":
        letter, wkind = "B", ("proof" if ts == "IMPAIRED" else "event")
    else:                                                             # INTACT + AT_LEVEL
        letter, wkind = "B", "price"
        if lvl is None and floor_px is not None:
            lvl = floor_px
            flags.append("LEVEL_MISSING_DERIVED")
        elif lvl is None:
            flags.append("LEVEL_MISSING")
        if wo_fall and wo_level is not None and lvl is not None and lvl > wo_level:
            lvl = wo_level                                            # P1: keep the wait at or below last time's level
            flags.append("WASHOUT_LEVEL_CAPPED")
        if lvl is not None and exit_px is not None and lvl <= exit_px:   # (iv) add at/below the exit
            flags.append("ADD_AT_OR_BELOW_EXIT")
            if floor_px is not None and floor_px > exit_px:
                lvl = floor_px
                flags.append("LEVEL_REPLACED")
            elif floor_px is not None:                                # no buyable price between break and bar
                letter, wkind, em_eff, lvl = "C", None, "NONE", None
                flags.append("NO_BUYABLE_PRICE")
            # no base_fv_px: nothing to replace it with - the CRO's level stays, flagged (fail-open)
        # P2: the level must itself clear the entry floor (base_fv_px / level - 1 >= floor). A level the
        # floor rejects is replaced by base_fv/(1+floor) when that is above the exit, else no buyable price.
        # 1e-4 relative slack so a level rounded to the cent is not flagged. No fair value: unchecked.
        lvl_pre = lvl
        if letter == "B" and lvl is not None and floor_px is not None and lvl > floor_px * (1.0 + 1e-4):
            if exit_px is None or floor_px > exit_px:
                lvl = floor_px
                flags.append("LEVEL_FAILS_FLOOR")
            else:
                letter, wkind, em_eff, lvl = "C", None, "NONE", None
                flags.append("NO_BUYABLE_PRICE")
        if letter == "B" and "LEVEL_MISSING_DERIVED" not in flags \
                and str(rec.get("washout_type") or "").strip().upper() not in ("MECHANICAL", "FACTOR"):
            flags.append("AT_LEVEL_WITHOUT_SELLER")
    structural = letter
    if str(rec.get("verdict_agent_orig") or "").strip().upper()[:1] not in ("", structural):
        flags.append("AGENT_LETTER_MISMATCH")

    # (vi) price re-derive - only a structural A, only with a usable price (fail-open otherwise)
    er, px_used = _grade_er(rec, base, live_px)
    rederived, wo_pass, met = None, False, None
    # P2: a price-wait must sit strictly below today's price. A level at or above it is flagged (the
    # CRO's level, or the code's replacement); when the effective level is at or above the price the
    # wait is already met - it is a NOW, and the floor check below decides (buy now, or a code-derived
    # price-wait / no buyable price). Fail-open: no usable price (or no fair value) -> no check.
    if letter == "B" and wkind == "price" and px_used is not None:
        if any(v is not None and v >= px_used for v in (lvl, lvl_pre)):
            flags.append("LEVEL_AT_OR_ABOVE_PRICE")
        if lvl is not None and lvl >= px_used:
            met, letter, wkind, em_eff = lvl, "A", None, "NOW"
    prior_pass = bool(wr and wr.get("stamped_by") == "grade-derive" and wr.get("outcome") == "PASS_BELOW_FLOOR")
    # P3: the wash-out pass the rubric prescribes (level reached, thesis INTACT, the price still fails
    # the floor -> the CRO answers NONE) is a PRICE answer - exactly what a NOW derives below - so it is
    # the same PASS_BELOW_FLOOR, with conviction untouched (later re-derives keep it via prior_pass)
    if letter == "C" and ts == "INTACT" and em == "NONE" and wo_reached \
            and ((wo_now and er is not None and er < floor) or (not wo_now and prior_pass)):
        wo_pass = True
        flags.append("WASHOUT_BELOW_FLOOR")
    if letter == "A" and er is not None and er < floor:
        if wo_reached and (wo_now or prior_pass):
            letter, em_eff, wo_pass = "C", "NONE", True
            flags.append("WASHOUT_BELOW_FLOOR")
            why = (f"the wash-out arrived, but the expected return of {er:.1f}% is still below the "
                   f"{floor:.0f}% entry bar - a pass, not another price to wait for")
        elif floor_px is not None and exit_px is not None and floor_px <= exit_px:
            letter, em_eff = "C", "NONE"
            flags.append("NO_BUYABLE_PRICE")
            why = (f"the expected return of {er:.1f}% is below the {floor:.0f}% entry bar, and the price "
                   f"that would clear it sits at or below the exit level")
        else:
            letter, wkind, em_eff, lvl = "B", "price", "AT_LEVEL", floor_px
            flags.append("FLOOR_REDERIVED")
            if floor_px is None:
                flags.append("LEVEL_UNDERIVABLE")
            why = (f"the expected return of {er:.1f}% is below the {floor:.0f}% entry bar"
                   + (f" - wait for a better price, near {_px(floor_px)}" if floor_px is not None else ""))
        if met is not None:
            why = f"the price is at or below the level the committee named ({_px(met)}), but {why}"
        rederived = {"from": "A", "to": letter, "why": why, "er_pct": round(er, 1), "floor_pct": floor,
                     "quadrant": quad, "live_px": px_used, "base_fv_px": base}

    # (v) wash-out resolution, persisted so later re-derives keep the coercion
    if wo_now:
        outcome = ("PASS_BELOW_FLOOR" if wo_pass else {"A": "BUY", "C": "PASS"}.get(letter)
                   or {"proof": "WAIT_FOR_PROOF", "event": "WAIT_FOR_EVENT"}.get(wkind, "WAIT_FOR_PRICE"))
        wr2 = dict(wr or {})
        wr2.update({"stamped_by": "grade-derive", "outcome": outcome,
                    "trigger_kind": "LEVEL_REACHED" if wo_reached else "FELL_10PCT",
                    "level": washout.get("level"), "level_source": washout.get("level_source"),
                    "price": washout.get("price"), "debate_price": washout.get("debate_price"),
                    "resolved_date": wr2.get("resolved_date") or today})
        rec["washout_resolution"] = wr2

    # conviction (P3): only a C that is the CRO's OWN answer caps it at 2 (BROKEN, an entry NONE the CRO
    # wrote, IMPAIRED with no test - the CRO's number is kept). A C from price or the quadrant floor
    # (NO_BUYABLE_PRICE, WASHOUT_BELOW_FLOOR / PASS_BELOW_FLOOR) keeps the letter as "not a buy" and
    # leaves conviction alone, so the macro quadrant can never push a held seat under the Director's
    # conviction >= 3 bar. A cap is lifted again whenever it no longer applies.
    conv = _num(rec.get("conviction"))
    cap_ok = letter == "C" and not wo_pass and (ts == "BROKEN" or em == "NONE"
                                                or "IMPAIRED_ENTRY_NO_TEST" in flags)
    if cap_ok:
        if conv is not None and conv > 2:
            rec.setdefault("conviction_agent_orig", rec.get("conviction"))
            rec["conviction"] = 2
            rec["grade_conviction_capped"] = True
    elif rec.get("grade_conviction_capped"):
        orig = rec.pop("conviction_agent_orig", None)
        rec.pop("grade_conviction_capped", None)
        if conv == 2 and orig is not None:                            # untouched since the cap: restore
            rec["conviction"] = orig

    # (vii) stamps - effective fields + the CRO's originals (grade_basis keeps re-runs idempotent)
    if em_eff == "AT_LEVEL":
        # P7: store the parsed number ("HK$35.8" -> 35.8) so the tracker and the wash-out check read the
        # same level the letter was graded on; a numeric input that is unchanged stays byte-identical
        out_lvl = (lvl_in if (isinstance(lvl_in, (int, float)) and not isinstance(lvl_in, bool)
                              and lvl is not None and lvl == lvl_in) else lvl)
    elif em == "AT_LEVEL" or em_eff != em:
        out_lvl = None
    else:
        out_lvl = lvl_in
    out_ev = ev if em_eff == "ON_EVENT" else ev_in
    out = [ts, em_eff, out_lvl, out_ev]
    inp = [ts_in, em_in, lvl_in, ev_in]
    rec["thesis_state"], rec["entry_mode"], rec["entry_level_px"], rec["entry_event"] = out
    if out != inp:
        rec["grade_basis"] = {"in": inp, "out": out}
    else:
        rec.pop("grade_basis", None)
    if em_eff != em:
        rec["entry_mode_agent_orig"] = em_in
    else:
        rec.pop("entry_mode_agent_orig", None)
    if out_lvl != lvl_in:
        rec["entry_level_px_agent_orig"] = lvl_in
    else:
        rec.pop("entry_level_px_agent_orig", None)
    if rederived:
        rec["grade_rederived"] = rederived
    else:
        rec.pop("grade_rederived", None)
    if rederived and letter == "B":
        rec["entry_level_px_derived"] = lvl
    else:
        rec.pop("entry_level_px_derived", None)
    rec["verdict_structural"] = structural
    rec["verdict"] = letter
    rec["verdict_source"] = "derived"
    if wkind:
        rec["wait_kind"] = wkind
    else:
        rec.pop("wait_kind", None)
    if flags:
        rec["grade_flags"] = flags
    else:
        rec.pop("grade_flags", None)
    rec["grade_schema"] = GRADE_SCHEMA
    rec["entry_floor_pct"] = floor
    return {"verdict_source": "derived", "verdict": letter, "verdict_structural": structural,
            "verdict_agent_orig": rec.get("verdict_agent_orig"), "wait_kind": wkind,
            "rederived": bool(rederived), "coerced": any(f in _GRADE_COERCIONS for f in flags),
            "washout_outcome": (rec.get("washout_resolution") or {}).get("outcome") if wo_now else None,
            "flags": flags, "er_pct": er, "floor_pct": floor}


def structural_letter(rec, quadrant=None):
    """The price-free derived letter of a record (before the entry-floor re-derive), or None for a
    legacy record. Pure - works on a copy. The continuity gate compares THIS, so a letter that moved
    only because the price crossed the entry floor is never read as a flip."""
    if not isinstance(rec, dict):
        return None
    try:
        res = derive_grade(json.loads(json.dumps(rec, default=str)), quadrant=quadrant)
    except Exception:
        return None
    return res.get("verdict_structural") if res.get("verdict_source") == "derived" else None


# ── ENTRY DISCIPLINE (2026-09-08) ─────────────────────────────────────────────────────────────────
# Bruno's read of the 2026-09-07 value book: three seats carried a debate grade B - the CRO's "wait
# for the wash-out", with NAMED entry levels (NOK 100-105, $285 / $270, $66-70) - yet the Director
# tagged enter_now_carry / scale_in on two of them, and the memo said "no name graded 'pass for
# now' is seated" (literally true: that is grade C; grade B IS seated, on the rotation rule). The
# book is a paper track: KEEP means "already held, do not sell" - never "buy at today's price".
# This layer makes that distinction deterministic, with the SAME override contract as
# duration_bucket: the Director may disagree with the CRO's timing only by writing a DATED reason.
# Display + audit trail only: no seat, size, weight or NAV moves here.
VERDICT_PLAIN = {"A": "buy now", "B": "wait for a better entry", "C": "pass for now"}
# FOUR-QUESTION GRADE (2026-10-06): a derived B says WHAT it waits for. A legacy B (no wait_kind on
# the record) keeps the generic "wait for a better entry" above.
VERDICT_PLAIN_BY_WAIT = {"price": "wait for a better price", "proof": "wait for proof",
                         "event": "wait for the event"}


def grade_plain(v, wait_kind=None):
    """House-voice caption for a debate letter: A "buy now"; B by wait_kind ("wait for a better
    price" / "wait for proof" / "wait for the event", legacy B "wait for a better entry"); C "pass for now"."""
    v = str(v or "").strip().upper()[:1]
    if v == "B" and wait_kind in VERDICT_PLAIN_BY_WAIT:
        return VERDICT_PLAIN_BY_WAIT[wait_kind]
    return VERDICT_PLAIN.get(v, "")


POSTURE_PLAIN = {"enter_now_carry": "enter now, carry", "scale_in": "scale in",
                 "wait_for_weakness": "wait for weakness", "on_confirmation": "on confirmation"}
_ENTER_NOW = ("enter_now_carry", "scale_in")
# The CRO's own verdict paragraph (record.moderator_conclusion). Opener = the first clause is a wait;
# the phrases are the specific ways this pipeline's CROs say "not at this price" (every one seen on
# the 2026-09-07 tape). Deliberately narrow: "paid to wait" / "while we wait" must NOT fire. The
# typed cro_add_px / cro_add_event the Director now emits are the primary path; this is the
# fail-safe for an omitted level, so leaving the field blank cannot dodge the rule.
_WAIT_OPENER = re.compile(r"^\s*wait\b", re.I)
_WAIT_PHRASES = re.compile(r"wait for the wash-?out|wait for a better (?:entry|price)|wait for proof"
                           r"|wait for the event|hold the file open"
                           r"|don'?t buy the flush|do not buy|not a buy|first-actionable-buy|entry trigger", re.I)
_DATED = re.compile(r"\b(?:20\d\d-\d\d-\d\d"
                    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+20\d\d"
                    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+20\d\d)\b", re.I)
ENTRY_MEMO_MARK = "\n\nENTRY DISCIPLINE (deterministic"


def _num(x):
    """Coerce a typed-or-prose level ("NOK 105", "$285", 285) to a float; None when there is none."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        m = re.search(r"-?\d+(?:\.\d+)?", x.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _px(x, cur=""):
    if x is None:
        return "?"
    s = f"{x:,.0f}" if abs(x) >= 1000 else (f"{x:,.2f}".rstrip("0").rstrip("."))
    return (s + " " + cur).strip()


def _posture_plain(v):
    key = str(v or "").split(":")[0].strip()
    detail = str(v or "").split(":", 1)[1].strip() if ":" in str(v or "") else ""
    base = POSTURE_PLAIN.get(key, key or "blank")
    return f"{base}: {detail}" if detail else base


def _wait_quote(concl, limit=260):
    """The CRO's own wait sentence(s), VERBATIM, for the memo when the Director typed no add level.
    Picks the wait phrase whose next 400 chars carry a number (the level / date sentence), latest
    wins on ties; returns from that sentence's start to the first sentence end past `limit` chars.
    A quote, never a parsed number - the typed cro_add_px stays the only machine-readable level."""
    if not concl:
        return ""
    hits = list(_WAIT_PHRASES.finditer(concl)) + list(_WAIT_OPENER.finditer(concl))
    if not hits:
        return ""
    def _score(m):                      # a priced level (NOK 105 / $285 / 880p) beats a bare percentage
        win = concl[m.start():m.start() + 400]
        return (2 if re.search(r"(?:[A-Z]{3}|[$€£])\s?\d|\d+\s?p\b", win) else 1 if re.search(r"\d", win) else 0,
                m.start())
    best = max(hits, key=_score)
    ends = [x.end() for x in re.finditer(r"[.!?]\s", concl[:best.start()])]
    start = ends[-1] if ends else 0
    seg = concl[start:start + limit * 2]
    cut = re.search(r"[.!?]\s", seg[limit:])
    seg = seg[:limit + cut.end() - 1] if cut else seg
    return re.sub(r"\s+", " ", seg).strip()


def reconcile_entry_posture(apx, picks, ctx_of, memo_key, today=None):
    """Reconcile every seat's entry_posture to its own debate grade. ctx_of(sym) -> dict with any of
    verdict / conclusion / currency / live_px / entry_px / entry_date (all optional, best-effort), plus
    (2026-10-06, four-question grade) thesis_state / entry_mode / wait_kind / entry_level_px / entry_event /
    thesis_test / washout_type / macro_fit / peer_position / grade_rederived from the record and
    base_fv_px / er_pct / floor_pct / quadrant from the post layer. A typed entry_mode switches the seat to
    the typed path; an A seat whose live discount is under the floor or whose price is past the trim
    line (exit_action TRIM) is re-graded to a price-wait here (cro_verdict_record keeps the A).
    Per seat stamps cro_verdict(+_plain), cro_says_wait, cro_add_px, cro_add_event, entry_posture_source
    (director | cro-reconciled | cro-derived | director-override | derived) and, when the post layer
    reverts an unjustified enter-now tag, entry_posture_director_orig. Appends (replacing any prior
    copy - idempotent on re-run) the ENTRY DISCIPLINE block to apx[memo_key] and apx['entry_discipline'].
    Never touches membership, size_units, weights or NAV."""
    today = today or _dt.now().strftime("%Y-%m-%d")
    waits, reconciled, overrides, consistent, blank, lines, other = [], [], [], [], [], [], []
    rederived = []
    for p in picks:
        sym = p.get("symbol")
        c = ctx_of(sym) or {}
        v = str(c.get("verdict") or p.get("cro_verdict_record") or p.get("cro_verdict") or "").strip().upper()[:1]
        # FOUR-QUESTION GRADE (2026-10-06): a record carrying a typed entry_mode is graded by its typed
        # fields (wait_kind, entry_level_px, entry_event); older records keep the prose path below.
        typed = str(c.get("entry_mode") or "").strip().upper() in ENTRY_MODES
        wait_kind = (c.get("wait_kind") or None) if typed else None
        # the Director's own transcription, kept aside once a record / derived value wins (re-runs read it back)
        dir_px = _num(p["cro_add_px_director"] if "cro_add_px_director" in p else p.get("cro_add_px"))
        dir_ev = str((p["cro_add_event_director"] if "cro_add_event_director" in p
                      else p.get("cro_add_event")) or "").strip()
        # A-SEAT CHECK: a debate A is "buy now" only while the discount at the LIVE price still clears
        # the quadrant entry floor and the price is under the trim line. Otherwise this seat can never
        # say buy here - it waits for a better price (fail-open: no price / no exit stamp = no check).
        v_eff, blocked = v, None
        if v == "A":
            er, fl = _num(c.get("er_pct")), _num(c.get("floor_pct"))
            below = er is not None and fl is not None and er < fl
            trim = str(p.get("exit_action") or "").strip().upper() == "TRIM"
            if below or trim:
                v_eff, wait_kind = "B", "price"
                base, tp = _pos_num(c.get("base_fv_px")), _pos_num(p.get("trim_at_px"))
                lv = ([base / (1.0 + fl / 100.0)] if base and fl is not None else []) + ([tp * 0.999] if tp else [])
                _q = str(c.get("quadrant") or "UNKNOWN").strip().upper()          # plain words in the memo
                _q = {"RISK_OFF": "risk-off", "UNKNOWN": "default"}.get(_q, _q.lower())
                parts = ([f"the discount ({er:.1f}%) is below the {_q} entry bar "
                          f"({fl:.0f}%)"] if below else []) + (["the price is above the trim line"] if trim else [])
                blocked = {"from": "A", "to": "B", "er_pct": round(er, 1) if er is not None else None,
                           "floor_pct": fl, "quadrant": c.get("quadrant") or "UNKNOWN", "trim_line_hit": trim,
                           "add_px": round(min(lv), 4) if lv else None,
                           "why": "graded A by the debate, but " + " and ".join(parts) + " - not a buy here"}
        p["cro_verdict"] = v_eff or None
        if blocked:
            p["cro_verdict_record"] = v
            p["grade_rederived"] = blocked
            rederived.append(sym)
        else:
            p.pop("cro_verdict_record", None)
            if isinstance(c.get("grade_rederived"), dict):          # re-derived on the record by grade-derive
                p["grade_rederived"] = c["grade_rederived"]
                rederived.append(sym)
            else:
                p.pop("grade_rederived", None)
        p["cro_verdict_plain"] = grade_plain(v_eff, wait_kind)
        # add level / event: the record's typed fields win, the Director's transcription is the fallback,
        # a blocked A takes the derived level (the price that clears the floor and the trim line)
        rec_px = _num(c.get("entry_level_px")) if typed else None
        rec_ev = str(c.get("entry_event") or "").strip() if typed else ""
        if blocked:
            add_px, add_ev, add_src = blocked["add_px"], "", "derived"
        else:
            add_px = rec_px if rec_px is not None else dir_px
            add_ev = rec_ev or dir_ev
            add_src = ("record" if (rec_px is not None or rec_ev)
                       else "director" if (dir_px is not None or dir_ev) else "")
        if add_src in ("record", "derived"):
            p.setdefault("cro_add_px_director", dir_px)
            p.setdefault("cro_add_event_director", dir_ev)
        p["cro_add_px"] = add_px
        p["cro_add_event"] = add_ev
        if add_src:
            p["cro_add_source"] = add_src
        else:
            p.pop("cro_add_source", None)
        for _k in ("thesis_state", "entry_mode", "thesis_test", "washout_type", "macro_fit", "peer_position"):
            if c.get(_k) is not None:                                  # for the publish whitelist
                p[_k] = c[_k]
        if wait_kind:
            p["wait_kind"] = wait_kind
        else:
            p.pop("wait_kind", None)
        concl = str(c.get("conclusion") or "")
        said_wait = bool(_WAIT_OPENER.search(concl) or _WAIT_PHRASES.search(concl))
        if blocked or typed:
            wait_graded = v_eff in ("B", "C")                           # the derived letter IS the wait
        else:
            wait_graded = (v == "B" and (said_wait or add_px is not None or bool(add_ev))) or v == "C"
        p["cro_says_wait"] = wait_graded
        p["cro_wait_quote"] = _wait_quote(concl) if wait_graded else ""
        cur = str(p.get("entry_posture") or "")
        key = cur.split(":")[0].strip()
        reason = str(p.get("entry_posture_override_reason") or "").strip()
        src = str(p.get("entry_posture_source") or "")
        if blocked or (typed and wait_kind == "price"):
            cro_posture = "wait_for_weakness"
        elif typed and wait_kind in ("proof", "event"):
            cro_posture = f"on_confirmation: {add_ev}" if add_ev else "on_confirmation"
        else:
            cro_posture = f"on_confirmation: {add_ev}" if add_ev else "wait_for_weakness"
        if wait_graded:
            waits.append(sym)
            # a floor / trim-line re-derived A can never say buy - no override, dated or not
            if key in _ENTER_NOW and _DATED.search(reason) and sym not in rederived:
                src = "director-override"
                overrides.append(sym)
            elif key in _ENTER_NOW:
                p["entry_posture_director_orig"] = cur
                p["entry_posture"] = cro_posture
                src = "cro-reconciled"
                reconciled.append(sym)
            elif not key:
                p["entry_posture"] = cro_posture
                src = "cro-derived"
                blank.append(sym)
            elif src in ("cro-reconciled", "cro-derived"):        # re-run: already reconciled last pass
                (reconciled if src == "cro-reconciled" else blank).append(sym)
            elif src == "director-override":
                overrides.append(sym)
            else:
                src = "director"
                consistent.append(sym)
        else:
            src = "director" if key else "derived"
            other.append(f"{sym} ({p['cro_verdict_plain'] or 'no grade'})")
        p["entry_posture_source"] = src
        if not wait_graded:
            continue
        # ── memo line (plain language; the numbers come from the tracking file + the record) ──
        ccy = str(c.get("currency") or "")
        e_px, l_px = _num(c.get("entry_px")), _num(c.get("live_px"))
        held = ""
        if e_px and c.get("entry_date"):
            held = f"held since {c['entry_date']} at {_px(e_px, ccy)}"
            if l_px:
                held += f" (now {_px(l_px, ccy)}, {((l_px / e_px) - 1) * 100:+.1f}%)"
        elif c.get("pending_since"):
            held = f"pending since {c['pending_since']} - not bought yet, waits on its gate"
        elif str(p.get("decision") or "").upper() == "ADD":
            held = "new this week"
        if blocked:
            says = f"{blocked['why']}; it waits for a better price"
        else:
            says = f"the debate says {grade_plain(v_eff, wait_kind) or 'wait'}"
            if isinstance(c.get("grade_rederived"), dict) and c["grade_rederived"].get("why"):
                says += f" (graded A by the debate, but {c['grade_rederived']['why']})"
        if add_px is not None and add_ev:
            says += f" - adds near {_px(add_px, ccy)} or on the {add_ev}"
        elif add_px is not None:
            says += f" - adds near {_px(add_px, ccy)}"
        elif add_ev:
            says += f" - adds on the {add_ev}"
        elif p.get("cro_wait_quote"):
            says += f' - in its words: "{p["cro_wait_quote"]}"'
        else:
            says += " but the Director recorded no add level (read the record's conclusion for the trigger)"
        orig_plain = _posture_plain(p.get("entry_posture_director_orig"))
        new_plain = _posture_plain(p.get("entry_posture"))
        if src == "cro-reconciled":
            what = f'Director tagged "{orig_plain}" with no dated reason -> reconciled to "{new_plain}".'
        elif src == "director-override":
            what = f'Director overrides the wait with a dated reason ("{reason[:140]}") - posture "{new_plain}" stands.'
        elif src == "cro-derived":
            what = f'Director left the posture blank -> set to "{new_plain}" from the debate.'
        else:
            what = f'Posture "{new_plain}" (Director, consistent with the debate).'
        lines.append(f"  - {sym}: " + "; ".join(x for x in (held, says) if x) + ". " + what)
    n = len(picks)
    head = (f"ENTRY DISCIPLINE (deterministic, stamped {today}). A kept seat is a paper position already "
            f"held: \"keep\" means do not sell, never buy at today's price. {len(waits)} of {n} seat(s) are "
            f"wait-graded by their own debate (\"wait for a better price\", \"wait for proof\", \"wait for the "
            f"event\", \"wait for a better entry\" or \"pass for now\"); for those the "
            f"entry posture is the reviewer's, not the Director's, unless a dated reason is on record."
            + (f" Graded A by the debate but not a buy here (below the entry bar or above the trim line): "
               f"{', '.join(rederived)}." if rederived else "")
            + (f" Reconciled by the post layer: {', '.join(reconciled)}." if reconciled else "")
            + (f" Set from the debate (Director left blank): {', '.join(blank)}." if blank else "")
            + (f" Director overrides on record: {', '.join(overrides)}." if overrides else ""))
    tail = f"\n  Not wait-graded (posture as the Director tagged it): {', '.join(other)}." if other else ""
    block = "\n\n" + head + ("\n" + "\n".join(lines) if lines else "") + tail
    assert block.startswith(ENTRY_MEMO_MARK), "memo marker drifted"
    memo = apx.get(memo_key)
    if isinstance(memo, str):
        i = memo.find(ENTRY_MEMO_MARK)
        if i >= 0:
            memo = memo[:i]
        apx[memo_key] = memo.rstrip() + block
    summary = {"stamped": today, "wait_graded": waits, "reconciled": reconciled, "set_from_debate": blank,
               "director_overrides": overrides, "consistent": consistent, "rederived": rederived}
    apx["entry_discipline"] = summary
    return summary


def seat_means_bought(apx, held_syms, memo_key="director_memo"):
    """BASKET MEANS BOUGHT (2026-10-13, Bruno). Every position the paper books ever recorded (125 of 126
    across regime + value) was filled at the first close after the Director added it; the one
    wait-gated new seat (KARE.AT, 2026-10-12, buy at EUR 411) was the inconsistency. Rule: a NEW seat
    is bought at the next close, so a NEW name whose own debate says wait for a better price / proof /
    the event (reconciled posture wait_for_weakness or on_confirmation, or a B/C grade with no
    enter-now override) is NOT a basket member - it goes to the FRONT of runner_ups with its trigger
    stamped, and joins the basket only when a later run grades it buy. Held seats are untouched (keep
    != buy here; the hold/add-at label already covers them). Returns the moved symbols."""
    keep, moved = [], []
    for p in apx.get("apex_basket", []) or []:
        sym = p.get("symbol")
        if not sym or sym in held_syms:
            keep.append(p)
            continue
        post = str(p.get("entry_posture") or "")
        key = post.split(":")[0].strip()
        v = str(p.get("cro_verdict") or "").strip().upper()[:1]
        src = str(p.get("entry_posture_source") or "")
        waits = key in ("wait_for_weakness", "on_confirmation") or (v in ("B", "C") and key not in _ENTER_NOW)
        if waits and src != "director-override":
            lvl = _pos_num(p.get("cro_add_px"))
            ev = str(p.get("cro_add_event") or "").strip() or (post.split(":", 1)[1].strip() if ":" in post else "")
            trig = (f"buys near {lvl:g}" if lvl is not None else (f"buys after {ev[:120]}" if ev else "buys on a better price"))
            p["seat_deferred"] = True
            p["seat_deferred_reason"] = (f"new seat whose debate says wait ({p.get('cro_verdict_plain') or key or v}): "
                                         f"a basket seat is bought at the next close, so it waits on the runner-up list - {trig}")
            p["runner_up_trigger"] = trig
            moved.append(p)
            print(f"seat-means-bought: {sym} graded wait by its own debate -> runner-up ({trig})")
        else:
            keep.append(p)
    if moved:
        ms = {m["symbol"] for m in moved}
        apx["apex_basket"] = keep
        apx["runner_ups"] = moved + [r for r in (apx.get("runner_ups") or [])
                                     if (r.get("symbol") if isinstance(r, dict) else r) not in ms]
        note = ("SEAT RULE (deterministic, " + _dt.now().strftime("%Y-%m-%d") + "): a basket seat is bought at the next "
                "close. New names whose own debate says wait were moved to the runner-up list with their trigger: "
                + ", ".join(f"{m['symbol']} ({m['runner_up_trigger']})" for m in moved) + ".")
        if isinstance(apx.get(memo_key), str):
            apx[memo_key] = note + "\n\n" + apx[memo_key]
    return [m["symbol"] for m in moved]


def entry_gate(p, held, today=None):
    """The entry order a NEW seat rests on (2026-10-06), read off the reconciled pick: None for a seat
    already held (keep != buy, nothing to gate), else {letter, mode NOW|AT_LEVEL|ON_EVENT|NONE, level,
    event, decided}. The effective posture wins (a dated Director override stands); a C seat without
    one rests on NONE. Display + the paper tracker's input only - no weight moves here."""
    if held:
        return None
    v = str(p.get("cro_verdict") or "").strip().upper()[:1]
    post = str(p.get("entry_posture") or "")
    key = post.split(":")[0].strip()
    lvl = _pos_num(p.get("cro_add_px"))
    ev = str(p.get("cro_add_event") or "").strip() or (post.split(":", 1)[1].strip() if ":" in post else "")
    if key in _ENTER_NOW:
        mode = "NOW"
    elif v == "C":
        mode = "NONE"
    elif key == "wait_for_weakness":
        mode = "AT_LEVEL"
    elif key == "on_confirmation":
        mode = "ON_EVENT"
    elif v == "A":
        mode = "NOW"
    else:
        mode = "AT_LEVEL" if lvl is not None else ("ON_EVENT" if ev else "NONE")
    return {"letter": v or None, "mode": mode, "level": lvl if mode == "AT_LEVEL" else None,
            "event": ev if mode == "ON_EVENT" else "", "decided": today or _dt.now().strftime("%Y-%m-%d")}
