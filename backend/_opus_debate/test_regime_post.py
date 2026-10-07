#!/usr/bin/env python3
"""Non-mutating smoke test for _regime_post: runs the consume_skeptic + moat-stamp + theme-cap +
weight build on an in-memory copy of the regime apex and asserts it produces a valid capped book.
Does NOT write apex_basket_opus_regime.json. Usage: python backend/_opus_debate/test_regime_post.py
"""
import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BK = HERE.parent
sys.path.insert(0, str(BK))
sys.path.insert(0, str(HERE))

import _regime_post as R  # noqa: E402
import _post_common as _pc  # noqa: E402


def test_numbers_repricing():
    """Regression (2026-08-03, the WKL.AS case): a skeptic REFUTED with kill_scope='numbers' and a
    typed revised_fv_px is a REPRICING — re-graded against the entry floor, not auto-demoted.
    Four cases: clears floor (kept + material haircut), fails floor (demoted, numeric reason),
    thesis kill (demoted, unchanged), numbers kill without the typed number (demoted, fail-safe)."""
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "results_regime").mkdir()
        (root / "shards").mkdir()

        def _mk(sym, live, verdict, scope=None, rev=None):
            (root / "results_regime" / f"{sym}.json").write_text(
                json.dumps({"symbol": sym, "valuation": {"live_price": live}}), encoding="utf-8")
            sh = {"symbol": sym, "verdict": verdict, "kill_fact": f"{sym} kill", "corrections": "",
                  "correction_severity": "material", "kill_scope": scope, "evidence": []}
            if rev is not None:
                sh["revised_fv_px"] = rev
            (root / "shards" / f"{sym}.json").write_text(json.dumps(sh), encoding="utf-8")

        # KEEPME: 70 -> revised 92 = +31% ER, clears the 20% GOLDILOCKS floor
        _mk("KEEPME", 70.0, "REFUTED", "numbers", 92.0)
        # DROPNUM: 70 -> revised 78 = +11% ER, under the floor -> demoted with the numeric reason
        _mk("DROPNUM", 70.0, "REFUTED", "numbers", 78.0)
        # DROPTHESIS: thesis kill -> demoted regardless of any number
        _mk("DROPTHESIS", 70.0, "REFUTED", "thesis", 200.0)
        # DROPNOFV: numbers kill WITHOUT the typed number -> fail-safe demote
        _mk("DROPNOFV", 70.0, "REFUTED", "numbers", None)

        apx = {"regime_quadrant": "GOLDILOCKS",
               "apex_basket": [{"symbol": s, "size_units": 1.0}
                               for s in ("KEEPME", "DROPNUM", "DROPTHESIS", "DROPNOFV")],
               "runner_ups": []}
        apex_f = root / "apex.json"
        apex_f.write_text(json.dumps(apx), encoding="utf-8")

        out = _pc.consume_skeptic(apx, apex_f, root / "shards", records_dir=root / "results_regime")
        kept = [p["symbol"] for p in out["apex_basket"]]
        demoted = [p["symbol"] for p in out["runner_ups"]]
        assert kept == ["KEEPME"], f"only the floor-clearing repricing survives, got {kept}"
        assert sorted(demoted) == ["DROPNOFV", "DROPNUM", "DROPTHESIS"], f"got {demoted}"

        keep = out["apex_basket"][0]
        assert keep.get("skeptic_repriced") is True
        assert keep.get("skeptic_revised_fv") == 92.0
        assert keep.get("correction_severity") == "material", "kept seat must carry the 0.75u haircut"
        assert _pc.moat_per_name_cap(keep, 1.0) == 0.75, "material severity -> 0.75u"

        dnum = next(p for p in out["runner_ups"] if p["symbol"] == "DROPNUM")
        assert dnum.get("skeptic_revised_fv") == 78.0, "demoted repricing still carries the number"

        # the revised FV persisted into the record = next cycle's anchor
        rec = json.loads((root / "results_regime" / "KEEPME.json").read_text(encoding="utf-8"))
        assert rec.get("skeptic_revision", {}).get("fv_px") == 92.0, "revision must persist to the record"
        rec2 = json.loads((root / "results_regime" / "DROPTHESIS.json").read_text(encoding="utf-8"))
        assert "skeptic_revision" not in rec2, "thesis kills must not write a revision"
    print("OK: numbers-scope repricing branch (keep/demote/thesis/no-fv all correct).")


def test_apply_skeptic_corrections():
    """Regression (2026-08-05, the GPOR case): typed skeptic corrections are APPLIED to the record's
    valuation block (originals kept, audit trail stamped) and the ratios recomputed — instead of
    living as a prose note that contradicts the published numbers. Cases: apply + recompute,
    idempotent re-run, stale shard skipped, Tier-2 revise triggered only for material CWC whose
    rr crosses 1.0 (REFUTED never revises), junk fields ignored."""
    import json
    import os
    import sys
    import tempfile
    import types
    import time

    # hermetic recompute: inject a fake _numeric_gate so the test pins the contract, not the formula
    fake = types.ModuleType("_numeric_gate")
    fake.COMPUTED_STAMP_KEYS = ("rr_ratio", "expected_return_pct")

    def _fake_check(rec):
        v = rec.get("valuation") or {}
        live, base, bear = v.get("live_price"), v.get("base_fv_px"), v.get("bear_px")
        up, down = base - live, live - bear
        return {"gate": "WARN", "reasons": [],
                "computed": {"rr_ratio": round(up / down, 2) if down > 0 else None,
                             "expected_return_pct": round(up / live * 100, 1)}}
    fake.check_record = _fake_check
    fake._rr_display = lambda v, c, r: "rr-display"
    real = sys.modules.get("_numeric_gate")
    sys.modules["_numeric_gate"] = fake
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "recs").mkdir()
            (root / "shards").mkdir()

            def _rec(sym, bear):
                (root / "recs" / f"{sym}.json").write_text(json.dumps({
                    "symbol": sym,
                    "valuation": {"live_price": 100.0, "bear_px": bear, "base_fv_px": 140.0,
                                  "bull_px": 160.0},
                    "computed": {"rr_ratio": round(40.0 / (100.0 - bear), 2),
                                 "expected_return_pct": 40.0}}), encoding="utf-8")

            def _shard(sym, verdict, sev, cts):
                (root / "shards" / f"{sym}.json").write_text(json.dumps({
                    "symbol": sym, "verdict": verdict, "correction_severity": sev,
                    "kill_scope": "numbers", "corrections_typed": cts}), encoding="utf-8")

            # FLIP: bear 95 -> 55 moves rr 8.0 -> 0.89, across 1.0; material CWC -> revise
            _rec("FLIP", 95.0)
            _shard("FLIP", "CONFIRMED_WITH_CORRECTIONS", "material",
                   [{"field": "bear_px", "from": 95.0, "to": 55.0, "basis": "sop_bear primary derivation"}])
            # SAME correction on a REFUTED name -> applied but NEVER on the revise list
            _rec("REFD", 95.0)
            _shard("REFD", "REFUTED", "material",
                   [{"field": "bear_px", "from": 95.0, "to": 55.0, "basis": "x"}])
            # NOFLIP: bear 95 -> 90 keeps rr above 1.0 -> applied, no revise
            _rec("NOFLIP", 95.0)
            _shard("NOFLIP", "CONFIRMED_WITH_CORRECTIONS", "material",
                   [{"field": "bear_px", "from": 95.0, "to": 90.0, "basis": "x"}])
            # JUNK: unknown field + non-positive value -> nothing applied
            _rec("JUNK", 95.0)
            _shard("JUNK", "CONFIRMED_WITH_CORRECTIONS", "material",
                   [{"field": "live_price", "from": 100.0, "to": 90.0, "basis": "not correctable"},
                    {"field": "bear_px", "from": 95.0, "to": -5.0, "basis": "junk"}])
            # STALE: valid correction but the shard is a week older than the record -> skipped
            _rec("STALE", 95.0)
            _shard("STALE", "CONFIRMED_WITH_CORRECTIONS", "material",
                   [{"field": "bear_px", "from": 95.0, "to": 55.0, "basis": "x"}])
            old = time.time() - 7 * 86400
            os.utime(root / "shards" / "STALE.json", (old, old))

            applied, revise = _pc.apply_skeptic_corrections(root / "shards", root / "recs",
                                                            quadrant="GOLDILOCKS")
            assert sorted(applied) == ["FLIP", "NOFLIP", "REFD"], f"got {applied}"
            assert revise == ["FLIP"], f"only the material-CWC rr-flip revises, got {revise}"

            rec = json.loads((root / "recs" / "FLIP.json").read_text(encoding="utf-8"))
            assert rec["valuation"]["bear_px"] == 55.0
            assert rec["valuation"]["bear_px_orig"] == 95.0, "original must be preserved"
            assert rec["computed"]["rr_ratio"] == 0.89, "ratios must be recomputed on corrected levels"
            assert rec["skeptic_corrections_applied"][0]["to"] == 55.0

            junk = json.loads((root / "recs" / "JUNK.json").read_text(encoding="utf-8"))
            assert junk["valuation"].get("live_price") == 100.0 and "skeptic_corrections_applied" not in junk
            stale = json.loads((root / "recs" / "STALE.json").read_text(encoding="utf-8"))
            assert stale["valuation"]["bear_px"] == 95.0, "stale shard must not rewrite a fresh record"

            # idempotency: second run applies nothing new
            applied2, revise2 = _pc.apply_skeptic_corrections(root / "shards", root / "recs",
                                                              quadrant="GOLDILOCKS")
            assert applied2 == [] and revise2 == [], f"re-run must be a no-op, got {applied2}/{revise2}"
            rec2 = json.loads((root / "recs" / "FLIP.json").read_text(encoding="utf-8"))
            assert len(rec2["skeptic_corrections_applied"]) == 1, "audit must not double-append"
            assert rec2["valuation"]["bear_px_orig"] == 95.0, "orig must never be clobbered"
    finally:
        if real is not None:
            sys.modules["_numeric_gate"] = real
        else:
            sys.modules.pop("_numeric_gate", None)
    print("OK: typed-corrections write-back (apply/recompute/idempotent/stale/junk/revise-trigger).")


def test_entry_posture_reconciliation():
    """Regression (2026-09-08, Bruno's review of the 09-07 value book): a seat whose own debate grade
    is B (legacy plain "wait for a better entry" since 2026-10-06 - was "wait for the wash-out") or C
    ("pass for now") may not carry an enter-now posture unless
    the Director wrote a DATED override reason. Cases: (a) enter_now_carry on a wait seat, no reason
    -> reconciled to wait_for_weakness, original kept; (b) same with a dated reason -> stands, source
    director-override; (c) typed cro_add_event -> on_confirmation:<event>; (d) grade A -> untouched;
    (e) grade B whose conclusion names no wait and no typed level -> stands (source director);
    (f) blank posture on a wait seat -> set from the debate; (g) re-run is idempotent (one memo block)."""
    ctx = {
        "W1": {"verdict": "B", "conclusion": "Wait for the wash-out. Good company, wrong day.",
               "currency": "NOK", "live_px": 118.0, "entry_px": 111.2, "entry_date": "2026-08-31"},
        "W2": {"verdict": "B", "conclusion": "Hold the file open, not the position."},
        "W3": {"verdict": "B", "conclusion": "A wait, not a buy, until the print."},
        "A1": {"verdict": "A", "conclusion": "Buy it here, at conviction four."},
        "B1": {"verdict": "B", "conclusion": "A good business at a cheap price with the catalyst behind it."},
        "W4": {"verdict": "C", "conclusion": "Pass for now."},
    }
    picks = [
        {"symbol": "W1", "entry_posture": "enter_now_carry"},
        {"symbol": "W2", "entry_posture": "scale_in",
         "entry_posture_override_reason": "Dividend declared 2026-09-01 pays the wait; entering now."},
        {"symbol": "W3", "entry_posture": "enter_now_carry", "cro_add_px": "$285", "cro_add_event": "November print"},
        {"symbol": "A1", "entry_posture": "enter_now_carry"},
        {"symbol": "B1", "entry_posture": "enter_now_carry"},
        {"symbol": "W4"},
    ]
    apx = {"apex_basket": picks, "director_memo": "ROTATION\nKEPT - W1, W2."}
    ed = _pc.reconcile_entry_posture(apx, picks, lambda s: ctx.get(s), "director_memo", today="2026-09-08")
    by = {p["symbol"]: p for p in picks}
    assert by["W1"]["entry_posture"] == "wait_for_weakness" and by["W1"]["entry_posture_director_orig"] == "enter_now_carry"
    # 2026-10-06 (Bruno's four-question decision): a LEGACY B (no wait_kind on the record) now reads
    # "wait for a better entry" - the pin moved with the house-voice change, the behavior did not
    assert by["W1"]["entry_posture_source"] == "cro-reconciled" and by["W1"]["cro_verdict_plain"] == "wait for a better entry"
    assert by["W2"]["entry_posture"] == "scale_in" and by["W2"]["entry_posture_source"] == "director-override"
    assert by["W3"]["entry_posture"] == "on_confirmation: November print" and by["W3"]["cro_add_px"] == 285.0
    assert by["A1"]["entry_posture"] == "enter_now_carry" and by["A1"]["entry_posture_source"] == "director"
    assert by["B1"]["entry_posture"] == "enter_now_carry" and by["B1"]["entry_posture_source"] == "director" and not by["B1"]["cro_says_wait"]
    assert by["W4"]["entry_posture"] == "wait_for_weakness" and by["W4"]["entry_posture_source"] == "cro-derived"
    assert set(ed["wait_graded"]) == {"W1", "W2", "W3", "W4"} and ed["reconciled"] == ["W1", "W3"]
    memo = apx["director_memo"]
    assert memo.count("ENTRY DISCIPLINE (deterministic") == 1 and "held since 2026-08-31 at 111.2 NOK (now 118 NOK, +6.1%)" in memo
    assert "4 of 6 seat(s) are wait-graded" in memo and "Not wait-graded" in memo and "B1 (wait for a better entry)" in memo
    assert 'in its words: "Hold the file open, not the position."' in memo   # verbatim CRO quote, no typed level
    assert by["W3"]["cro_wait_quote"] and "adds near 285 or on the November print" in memo   # typed level wins over the quote
    # (g) idempotent: a second pass over the stamped book changes nothing and does not duplicate the block
    import copy as _copy
    before = _copy.deepcopy(picks)
    _pc.reconcile_entry_posture(apx, picks, lambda s: ctx.get(s), "director_memo", today="2026-09-08")
    assert picks == before and apx["director_memo"].count("ENTRY DISCIPLINE (deterministic") == 1
    assert apx["entry_discipline"]["reconciled"] == ["W1", "W3"]
    print("OK: entry-posture reconciliation (7 cases)")


def _rec4q(ts, em, live=100.0, base=130.0, bear=80.0, floor_px=None, lvl=None, ev="", tt=None,
           verdict="A", conv=4, wtype="NONE"):
    """A synthetic regime record carrying the four-question fields (2026-10-06)."""
    return {"symbol": "X", "verdict": verdict, "conviction": conv, "live_price": live,
            "thesis_state": ts, "entry_mode": em, "entry_level_px": lvl, "entry_event": ev,
            "thesis_test": tt, "washout_type": wtype,
            "valuation": {"live_price": live, "bear_px": bear, "base_fv_px": base,
                          "bull_px": base * 1.3 if base else None,
                          "downside_floor_px": floor_px}}


_TT = {"metric": "Q3 gross margin", "pass_level": ">= 41%", "fail_level": "< 38%", "resolves_on": "2026-10-29 Q3 print"}


def test_derive_grade():
    """Four-question grade derivation (2026-10-06, Bruno's approved mapping): A = INTACT+NOW, B price =
    INTACT+AT_LEVEL, B proof = IMPAIRED+ON_EVENT, B event = INTACT+ON_EVENT, C = BROKEN or NONE; the
    coercions, the entry-floor re-derive, the wash-out resolution, the C conviction cap, fail-open on a
    missing price / UNKNOWN quadrant, legacy records untouched, idempotency."""
    import copy as _c
    D = _pc.derive_grade
    # (a) INTACT+NOW, ER 30% >= 20% GOLDILOCKS floor -> A; verdict_agent_orig kept; idempotent
    r = _rec4q("INTACT", "NOW", verdict="A")
    res = D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "A" and r["verdict_structural"] == "A" and r["verdict_source"] == "derived"
    assert r["verdict_agent_orig"] == "A" and r["grade_schema"] == "v2-4q" and "wait_kind" not in r
    snap = _c.deepcopy(r)
    D(r, quadrant="GOLDILOCKS")
    assert r == snap, "derive_grade must be idempotent"
    # (b) INTACT+NOW with ER 10% < 20% -> B price at base/(1+floor); structural stays A
    r = _rec4q("INTACT", "NOW", live=100.0, base=110.0, bear=70.0, verdict="A")
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "B" and r["wait_kind"] == "price" and r["verdict_structural"] == "A"
    assert r["entry_mode"] == "AT_LEVEL" and r["entry_mode_agent_orig"] == "NOW"
    assert abs(r["entry_level_px"] - round(110.0 / 1.2, 4)) < 1e-9 and r["entry_level_px_derived"] == r["entry_level_px"]
    assert r["grade_rederived"]["from"] == "A" and r["grade_rederived"]["floor_pct"] == 20.0
    assert "FLOOR_REDERIVED" in r["grade_flags"] and r["verdict_agent_orig"] == "A"
    snap = _c.deepcopy(r)
    D(r, quadrant="GOLDILOCKS")
    assert r == snap, "a re-derived record must be stable on re-run (grade_basis)"
    r["live_price"] = 85.0                                  # the price fell: ER 29% clears -> A again
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "A" and r["entry_mode"] == "NOW" and "grade_rederived" not in r and "grade_basis" not in r
    # (c) quadrant scaling + fail-open: ER 22% is an A under GOLDILOCKS / UNKNOWN / None, a B under RISK_OFF
    for q, want in (("GOLDILOCKS", "A"), ("UNKNOWN", "A"), (None, "A"), ("STAGFLATION", "B"), ("RISK_OFF", "B")):
        r = _rec4q("INTACT", "NOW", live=100.0, base=122.0, bear=70.0)
        D(r, quadrant=q)
        assert r["verdict"] == want, f"{q}: got {r['verdict']}"
    r = _rec4q("INTACT", "NOW", live=None, base=110.0)       # no price anywhere -> no re-derive
    r["valuation"]["live_price"] = None
    D(r, quadrant="RISK_OFF")
    assert r["verdict"] == "A" and "grade_rederived" not in r, "a missing price must never tighten"
    # (d) IMPAIRED+ON_EVENT -> B proof (event from the test when blank); INTACT+ON_EVENT -> B event
    r = _rec4q("IMPAIRED", "ON_EVENT", tt=dict(_TT), verdict="B", conv=3)
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "B" and r["wait_kind"] == "proof" and r["entry_event"] == _TT["resolves_on"]
    assert _pc.grade_plain("B", "proof") == "wait for proof"
    r = _rec4q("INTACT", "ON_EVENT", ev="the FDA decision", verdict="B")
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "B" and r["wait_kind"] == "event"
    # (e) IMPAIRED + NOW / AT_LEVEL: coerced to ON_EVENT on the test (B proof), or C with no test
    r = _rec4q("IMPAIRED", "NOW", tt=dict(_TT), verdict="A")
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "B" and r["wait_kind"] == "proof" and r["entry_mode"] == "ON_EVENT"
    assert "IMPAIRED_ENTRY_COERCED" in r["grade_flags"] and r["entry_mode_agent_orig"] == "NOW"
    r = _rec4q("IMPAIRED", "AT_LEVEL", lvl=90.0, tt=None, verdict="B", conv=4)
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "C" and "IMPAIRED_ENTRY_NO_TEST" in r["grade_flags"]
    # (f) BROKEN + AT_LEVEL -> C, conviction capped at 2 (the CRO's number kept)
    r = _rec4q("BROKEN", "AT_LEVEL", lvl=90.0, verdict="B", conv=4)
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "C" and r["entry_mode"] == "NONE" and "BROKEN_WITH_ENTRY" in r["grade_flags"]
    assert r["conviction"] == 2 and r["conviction_agent_orig"] == 4
    # (g) add level at/below the exit: replaced by base/(1+floor) when that is above the exit, else C
    # (2026-10-06 review P2: live 120 so the replacement 108.33 sits below the price - at live 100 it
    # would be a met wait, see test_level_rule3)
    r = _rec4q("INTACT", "AT_LEVEL", lvl=75.0, bear=80.0, base=130.0, live=120.0, verdict="B", wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "B" and "ADD_AT_OR_BELOW_EXIT" in r["grade_flags"] and "LEVEL_REPLACED" in r["grade_flags"]
    assert abs(r["entry_level_px"] - round(130.0 / 1.2, 4)) < 1e-9 and r["entry_level_px_agent_orig"] == 75.0
    r = _rec4q("INTACT", "AT_LEVEL", lvl=75.0, bear=100.0, base=110.0, live=120.0, verdict="B", conv=3)
    D(r, quadrant="GOLDILOCKS")                         # 110/1.2 = 91.7 <= exit 100 -> no buyable price
    # P3: a C from the floor keeps the CRO's conviction (was capped at 2 before the review fix)
    assert r["verdict"] == "C" and "NO_BUYABLE_PRICE" in r["grade_flags"] and r["conviction"] == 3
    assert "grade_conviction_capped" not in r and "conviction_agent_orig" not in r
    r = _rec4q("INTACT", "AT_LEVEL", lvl=75.0, bear=80.0, base=None, verdict="B")
    D(r, quadrant="GOLDILOCKS")                         # no fair value: nothing to replace it with (fail-open)
    assert r["verdict"] == "B" and r["entry_level_px"] == 75.0 and "ADD_AT_OR_BELOW_EXIT" in r["grade_flags"]
    # (h) WASH-OUT: INTACT + a second AT_LEVEL -> NOW (A) when the floor clears; -> C when it does not
    wo = {"level": 92.0, "level_source": "entry_level_px", "price": 91.0, "debate_price": 104.0}
    r = _rec4q("INTACT", "AT_LEVEL", lvl=85.0, live=91.0, base=125.0, verdict="B", wtype="MECHANICAL")
    res = D(r, quadrant="GOLDILOCKS", washout=wo)
    assert r["verdict"] == "A" and r["entry_mode"] == "NOW" and "SECOND_PRICE_WAIT_COERCED" in r["grade_flags"]
    assert res["washout_outcome"] == "BUY" and r["washout_resolution"]["stamped_by"] == "grade-derive"
    r = _rec4q("INTACT", "NOW", live=91.0, base=100.0, verdict="A", conv=4)
    # a FELL_10PCT bundle whose price (91) is already at/below the named level (92) IS the level reached
    # (P1); the floor-failing NOW is a pass, and that floor C leaves conviction alone (P3)
    res = D(r, quadrant="GOLDILOCKS", washout=dict(wo, level_source="fall_10pct"))
    assert r["verdict"] == "C" and res["washout_outcome"] == "PASS_BELOW_FLOOR" and r["conviction"] == 4
    assert r["washout_resolution"]["trigger_kind"] == "LEVEL_REACHED" and "grade_conviction_capped" not in r
    snap = _c.deepcopy(r)
    D(r, quadrant="GOLDILOCKS")                         # a later re-derive (no bundle) keeps the pass
    assert r["verdict"] == "C" and r == snap
    r = _rec4q("IMPAIRED", "ON_EVENT", tt=dict(_TT), verdict="B")
    D(r, quadrant="GOLDILOCKS", washout=wo)
    assert r["verdict"] == "B" and r["washout_resolution"]["outcome"] == "WAIT_FOR_PROOF"
    # (i) a Revise rewrite after a coercion is the new input (not reverted to the old basis)
    r = _rec4q("INTACT", "NOW", live=100.0, base=110.0, bear=70.0)
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "B"
    r["entry_mode"], r["entry_level_px"], r["thesis_state"] = "NONE", None, "INTACT"   # Revise: no entry
    D(r, quadrant="GOLDILOCKS")
    assert r["verdict"] == "C" and r["entry_mode"] == "NONE"
    # (j) legacy records (no typed fields) and B13 / ledger re-checks are untouched
    for leg in ({"symbol": "L", "verdict": "B", "conviction": 3, "live_price": 10.0},
                dict(_rec4q("INTACT", "NOW"), source="ledger_recheck"),
                dict(_rec4q("INTACT", "NOW"), lane="equity_special_sit")):
        before = _c.deepcopy(leg)
        assert D(leg, quadrant="RISK_OFF")["verdict_source"] == "agent_legacy" and leg == before
    assert _pc.structural_letter(_rec4q("INTACT", "NOW", live=100.0, base=105.0)) == "A"   # price-free
    print("OK: four-question grade derivation (mapping, coercions, floor, wash-out, cap, fail-open, idempotent)")


def test_entry_posture_typed():
    """Typed path of reconcile_entry_posture (2026-10-06): the record's typed fields win; an A seat under
    the floor or past the trim line can never say buy; wait_kind drives the wording + posture;
    entry_gate only for NEW seats; fail-open with no price / no exit stamp."""
    ctx = {
        # record A, but the live ER (12%) is under the 20% bar -> wait for a better price at base/1.2
        "RA": {"verdict": "A", "thesis_state": "INTACT", "entry_mode": "NOW", "base_fv_px": 112.0,
               "er_pct": 12.0, "floor_pct": 20.0, "quadrant": "GOLDILOCKS", "conclusion": "Buy now."},
        # legacy A whose price sits past the trim line (value book)
        "TR": {"verdict": "A", "base_fv_px": 100.0, "er_pct": 25.0, "floor_pct": 20.0, "conclusion": "Buy it."},
        # typed proof-wait: the record's event wins over the Director's transcription
        "PF": {"verdict": "B", "thesis_state": "IMPAIRED", "entry_mode": "ON_EVENT", "wait_kind": "proof",
               "entry_event": "2026-10-29 Q3 print", "thesis_test": dict(_TT), "conclusion": "Wait for proof."},
        # typed price-wait: the record's level wins
        "PX": {"verdict": "B", "thesis_state": "INTACT", "entry_mode": "AT_LEVEL", "wait_kind": "price",
               "entry_level_px": 41.5, "washout_type": "FACTOR", "conclusion": "Wait for a better price."},
        "BR": {"verdict": "C", "thesis_state": "BROKEN", "entry_mode": "NONE", "conclusion": "Pass for now."},
        # A with NO price and no exit stamp -> fail-open, stays a buy
        "NP": {"verdict": "A", "thesis_state": "INTACT", "entry_mode": "NOW", "floor_pct": 20.0,
               "conclusion": "Buy now."},
    }
    picks = [
        {"symbol": "RA", "entry_posture": "enter_now_carry", "decision": "ADD"},
        {"symbol": "TR", "entry_posture": "enter_now_carry", "exit_action": "TRIM", "trim_at_px": 85.0,
         "decision": "KEEP"},
        {"symbol": "PF", "entry_posture": "scale_in", "cro_add_event": "some prose event", "decision": "ADD"},
        {"symbol": "PX", "entry_posture": "", "cro_add_px": 39.0, "decision": "KEEP"},
        {"symbol": "BR", "entry_posture": "enter_now_carry", "decision": "KEEP"},
        {"symbol": "NP", "entry_posture": "enter_now_carry", "decision": "ADD"},
    ]
    apx = {"apex_basket": picks, "director_memo": "ROTATION"}
    ed = _pc.reconcile_entry_posture(apx, picks, lambda s: ctx.get(s), "director_memo", today="2026-10-06")
    by = {p["symbol"]: p for p in picks}
    ra = by["RA"]
    assert ra["cro_verdict"] == "B" and ra["cro_verdict_record"] == "A" and ra["wait_kind"] == "price"
    assert ra["cro_verdict_plain"] == "wait for a better price" and ra["entry_posture"] == "wait_for_weakness"
    assert abs(ra["cro_add_px"] - round(112.0 / 1.2, 4)) < 1e-9 and ra["cro_add_source"] == "derived"
    assert ra["grade_rederived"]["er_pct"] == 12.0 and "not a buy here" in ra["grade_rederived"]["why"]
    tr = by["TR"]
    assert tr["cro_verdict"] == "B" and tr["grade_rederived"]["trim_line_hit"] is True
    # the add level is the LOWER of base/(1+floor) = 83.33 and trim x 0.999 = 84.92
    assert tr["entry_posture"] == "wait_for_weakness" and abs(tr["cro_add_px"] - round(100.0 / 1.2, 4)) < 1e-9
    pf = by["PF"]
    assert pf["cro_verdict_plain"] == "wait for proof" and pf["entry_posture"] == "on_confirmation: 2026-10-29 Q3 print"
    assert pf["cro_add_source"] == "record" and pf["cro_add_event_director"] == "some prose event"
    px = by["PX"]
    assert px["cro_add_px"] == 41.5 and px["cro_add_source"] == "record" and px["entry_posture"] == "wait_for_weakness"
    assert px["cro_verdict_plain"] == "wait for a better price" and px["washout_type"] == "FACTOR"
    assert by["BR"]["cro_verdict_plain"] == "pass for now" and by["BR"]["entry_posture"] == "wait_for_weakness"
    np_ = by["NP"]
    assert np_["cro_verdict"] == "A" and np_["entry_posture"] == "enter_now_carry" and not np_["cro_says_wait"]
    assert sorted(ed["rederived"]) == ["RA", "TR"]
    memo = apx["director_memo"]
    assert "graded A by the debate, but the discount (12.0%) is below the goldilocks entry bar (20%)" in memo
    assert "the price is above the trim line" in memo
    # entry_gate: a NEW seat rests on its gate; a held seat has none
    g = _pc.entry_gate(ra, held=False, today="2026-10-06")
    assert g == {"letter": "B", "mode": "AT_LEVEL", "level": ra["cro_add_px"], "event": "", "decided": "2026-10-06"}
    assert _pc.entry_gate(by["PF"], held=False)["mode"] == "ON_EVENT" and _pc.entry_gate(tr, held=True) is None
    assert _pc.entry_gate(np_, held=False)["mode"] == "NOW" and _pc.entry_gate(by["BR"], held=False)["mode"] == "NONE"
    # idempotent re-run
    import copy as _c
    before = _c.deepcopy(picks)
    _pc.reconcile_entry_posture(apx, picks, lambda s: ctx.get(s), "director_memo", today="2026-10-06")
    assert picks == before and apx["director_memo"].count("ENTRY DISCIPLINE (deterministic") == 1
    print("OK: entry-posture typed path (floor/trim A-seat check, proof/price waits, gate, fail-open)")


# ── CRO four-question REVIEW FIXES (2026-10-06, findings 8-20, policies P1-P7) ───────────────────────
# Each case below is a reviewer reproduction (scratchpad cro_review/sim1-4, h5/h5b/h6/h8/h9/h10)
# turned into a permanent regression. weekly_opus_refresh is imported lazily (its import chdirs into
# backend/ - restored) and every path global it writes through is pointed at a temp tree.
def _wor():
    import os
    cwd = os.getcwd()
    try:
        import weekly_opus_refresh as W  # noqa: E402
    finally:
        os.chdir(cwd)
    return W


class _WorTree:
    """Temp ROOT for weekly_opus_refresh verbs (results_regime / inputs / _archive_prev / ledgers /
    macro_regime.json); every module path global is restored on exit, the tree is deleted."""
    _KEYS = ("ROOT", "RES", "INP", "_WASHOUT_LEDGER", "COHORT_LEDGER")

    def __init__(self, quadrant="GOLDILOCKS"):
        self.quadrant = quadrant

    def __enter__(self):
        import json
        import tempfile
        self.W = _wor()
        self.saved = {k: getattr(self.W, k) for k in self._KEYS}
        self.td = Path(tempfile.mkdtemp(prefix="test_regime_post_"))
        for d in ("results_regime", "inputs", "_archive_prev/results_regime", "_skeptic_regime"):
            (self.td / d).mkdir(parents=True, exist_ok=True)
        if self.quadrant:
            (self.td / "macro_regime.json").write_text(json.dumps({"quadrant": self.quadrant}), encoding="utf-8")
        W = self.W
        W.ROOT, W.RES, W.INP = self.td, self.td / "results_regime", self.td / "inputs"
        W._WASHOUT_LEDGER, W.COHORT_LEDGER = self.td / "_washout_ledger.jsonl", self.td / "_cohort_ledger.jsonl"
        return W, self.td

    def __exit__(self, *exc):
        import shutil
        for k, v in self.saved.items():
            setattr(self.W, k, v)
        shutil.rmtree(self.td, ignore_errors=True)
        return False


def _put(td, sub, sym, rec):
    import json
    (td / sub / f"{sym}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def _get(td, sub, sym):
    import json
    return json.loads((td / sub / f"{sym}.json").read_text(encoding="utf-8"))


def _ledger_rows(path):
    import json
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def test_washout_fall_vs_level():
    """Findings 8 + 10 (P1). sim1 S1: a price-wait B at 125 that fell 10.4% to 125.5 fired FELL_10PCT and
    was then forced to C (conviction 2) 0.4% above the committee's own level - the fall now never fires
    on a named level, and a FELL_10PCT resolution may keep its price-wait at or below the prior level
    (no SECOND_PRICE_WAIT, no WASHOUT_BELOW_FLOOR). sim1 S2: an event wait that fell 12% may keep
    waiting for its event. Only LEVEL_REACHED forbids a second price-wait."""
    import copy as _c
    W = _wor()
    D = _pc.derive_grade
    # (a) the trigger
    w1 = _rec4q("INTACT", "AT_LEVEL", live=140.0, base=150.0, bear=100.0, lvl=125.0, verdict="B", wtype="FACTOR")
    D(w1, quadrant="GOLDILOCKS")
    assert w1["verdict"] == "B" and w1["entry_level_px"] == 125.0
    assert W._washout_check(w1, {"price": 125.5}) is None, "a 10% fall above the named level is not a wash-out"
    wo = W._washout_check(w1, {"price": 124.0})
    assert wo and wo["level_source"] == "entry_level_px" and wo["level"] == 125.0
    leg = {"symbol": "L", "verdict": "B", "conviction": 3, "live_price": 100.0, "valuation": {"live_price": 100.0}}
    assert W._washout_check(leg, {"price": 88.0})["level_source"] == "fall_10pct", "an older B with no level"
    assert W._washout_check(leg, {"price": 89.0}, legacy_level=85.0) is None, "a cro_add_px waits for its own price"
    assert W._washout_check(leg, {"price": 84.0}, legacy_level=85.0)["level_source"] == "cro_add_px"
    ev1 = _rec4q("INTACT", "ON_EVENT", live=50.0, base=80.0, bear=30.0, ev="FDA PDUFA decision 2026-11-20", verdict="B")
    D(ev1, quadrant="GOLDILOCKS")
    wo2 = W._washout_check(ev1, {"price": 44.0})
    assert wo2 and wo2["level_source"] == "fall_10pct" and wo2["level"] is None, "an event wait still re-checks on a fall"
    # (b) a FELL_10PCT bundle with the price still above the prior level (an older prep's bundle)
    wof = {"level": 125.0, "level_source": "fall_10pct", "price": 125.5, "debate_price": 140.0, "fall_pct": -10.4}
    keep = _rec4q("INTACT", "AT_LEVEL", live=125.5, base=150.0, bear=100.0, lvl=125.0, verdict="B", wtype="FACTOR")
    res = D(keep, quadrant="GOLDILOCKS", washout=wof)
    fl = set(keep.get("grade_flags") or [])
    assert keep["verdict"] == "B" and keep["entry_level_px"] == 125.0 and res["washout_outcome"] == "WAIT_FOR_PRICE"
    assert not fl & {"SECOND_PRICE_WAIT_COERCED", "WASHOUT_BELOW_FLOOR"} and keep["conviction"] == 4, fl
    assert keep["washout_resolution"]["trigger_kind"] == "FELL_10PCT"
    snap = _c.deepcopy(keep)
    D(keep, quadrant="GOLDILOCKS")                       # a later re-derive (no bundle) keeps the wait
    assert keep == snap
    now = _rec4q("INTACT", "NOW", live=125.5, base=150.0, bear=100.0, verdict="A")
    res = D(now, quadrant="GOLDILOCKS", washout=wof)     # ER 19.5% < 20%: a price-wait, never a forced pass
    assert now["verdict"] == "B" and "FLOOR_REDERIVED" in now["grade_flags"] and now["conviction"] == 4
    assert "WASHOUT_BELOW_FLOOR" not in now["grade_flags"] and res["washout_outcome"] == "WAIT_FOR_PRICE"
    up = _rec4q("INTACT", "AT_LEVEL", live=125.5, base=150.0, bear=100.0, lvl=125.4, verdict="B", wtype="FACTOR")
    D(up, quadrant="GOLDILOCKS", washout=wof)            # a HIGHER level than last time is capped at it
    assert up["verdict"] == "B" and up["entry_level_px"] == 125.0 and "WASHOUT_LEVEL_CAPPED" in up["grade_flags"]
    # (c) the event wait keeps waiting for its event (never forced to buy ahead of it)
    e2 = _rec4q("INTACT", "ON_EVENT", live=44.0, base=80.0, bear=30.0, ev="FDA PDUFA decision 2026-11-20", verdict="B")
    res = D(e2, quadrant="GOLDILOCKS", washout=wo2)
    assert e2["verdict"] == "B" and e2["wait_kind"] == "event" and res["washout_outcome"] == "WAIT_FOR_EVENT"
    # (d) LEVEL_REACHED still forbids a second price-wait
    lv = _rec4q("INTACT", "AT_LEVEL", live=124.0, base=150.0, bear=100.0, lvl=120.0, verdict="B", wtype="FACTOR")
    res = D(lv, quadrant="GOLDILOCKS", washout=wo)
    assert lv["verdict"] == "A" and "SECOND_PRICE_WAIT_COERCED" in lv["grade_flags"] and res["washout_outcome"] == "BUY"
    # (e) the prompts say the same thing
    import live_debate_engine as E  # noqa: E402
    rub = E.REGIME_CRO_RUBRIC
    assert "FELL 10% (level_source fall_10pct)" in rub and "WAIT_FOR_EVENT | PASS" in rub
    assert "never forced to buy ahead of the event" in rub and "answer AT_LEVEL at a level that obeys rules (3) and (4)" in rub and "Never write NONE for a price reason" in rub
    tpl = W._WORKFLOW_TEMPLATE
    assert "After a 10% fall (no level was named) you may name a price-wait level" in tpl
    assert "BUY|WAIT_FOR_PRICE|WAIT_FOR_PROOF|WAIT_FOR_EVENT|PASS" in tpl
    print("OK: wash-out fall vs level (P1: trigger, kept waits, capped level, event wait, prompts)")


def test_revise_washout_constraint():
    """Finding 13 (prompt): Revise must not write AT_LEVEL on a record whose wash-out reached its level
    (the published grade would contradict the rewritten prose); only the P1 fall allowance remains."""
    tpl = _wor()._WORKFLOW_TEMPLATE
    i = tpl.index("HARD CONSTRAINTS: (1) The skeptic corrections")
    rev = tpl[i:i + 4000]
    assert "AT_LEVEL is NOT allowed" in rev and "washout_resolution stamped_by grade-derive" in rev
    assert "only after a 10% fall (FELL_10PCT) may it be AT_LEVEL, at or below washout.level" in rev
    print("OK: Revise wash-out constraint (no second price-wait after the level was reached)")


def test_level_rule3():
    """Findings 11 + 17 (P2). sim2 S4 / h9: a CRO level at/above the live price, or one whose own
    discount fails the floor, used to stay a silent B - and fired a LEVEL_REACHED wash-out at an UNMOVED
    price that the wash-out rule then turned into a pass. h1: the code's own replacement level could sit
    above the price ("wait for ~108 while it trades at 100")."""
    import copy as _c
    W = _wor()
    D = _pc.derive_grade
    fp = round(110.0 / 1.2, 4)
    r = _rec4q("INTACT", "AT_LEVEL", live=100.0, base=110.0, bear=80.0, lvl=105.0, verdict="B", wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # above the price AND failing the floor
    assert r["verdict"] == "B" and abs(r["entry_level_px"] - fp) < 1e-9 and r["entry_level_px_agent_orig"] == 105.0
    assert {"LEVEL_FAILS_FLOOR", "LEVEL_AT_OR_ABOVE_PRICE"} <= set(r["grade_flags"]), r["grade_flags"]
    assert W._washout_check(r, {"price": 100.0}) is None, "no wash-out at an unmoved price"
    snap = _c.deepcopy(r)
    D(r, quadrant="GOLDILOCKS")
    assert r == snap, "idempotent"
    r = _rec4q("INTACT", "AT_LEVEL", live=100.0, base=110.0, bear=80.0, lvl=95.0, verdict="B", wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # 110/95 - 1 = 15.8% < 20%: a sub-floor buy level
    assert abs(r["entry_level_px"] - fp) < 1e-9 and "LEVEL_FAILS_FLOOR" in r["grade_flags"]
    assert "LEVEL_AT_OR_ABOVE_PRICE" not in r["grade_flags"]
    r = _rec4q("INTACT", "AT_LEVEL", live=112.0, base=115.0, bear=80.0, floor_px=75.0, lvl=108.0, verdict="B",
               wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # h9: 115/108 - 1 = 6.5%
    assert r["verdict"] == "B" and abs(r["entry_level_px"] - round(115.0 / 1.2, 4)) < 1e-9
    r = _rec4q("INTACT", "AT_LEVEL", live=100.0, base=150.0, bear=80.0, lvl=105.0, verdict="B", wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # level above the price that clears the floor: wait met
    assert r["verdict"] == "A" and r["entry_mode"] == "NOW" and r["entry_level_px"] is None
    assert "LEVEL_AT_OR_ABOVE_PRICE" in r["grade_flags"] and r["entry_mode_agent_orig"] == "AT_LEVEL"
    assert r["verdict_structural"] == "B"
    r = _rec4q("INTACT", "AT_LEVEL", live=100.0, base=130.0, bear=80.0, lvl=75.0, verdict="B", wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # h1: the code's replacement 108.33 sits above the price
    assert r["verdict"] == "A" and {"LEVEL_REPLACED", "LEVEL_AT_OR_ABOVE_PRICE"} <= set(r["grade_flags"])
    r = _rec4q("INTACT", "AT_LEVEL", live=100.0, base=110.0, bear=93.0, lvl=97.0, verdict="B", conv=4, wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # fails the floor and base/1.2 = 91.7 <= exit 93
    assert r["verdict"] == "C" and "NO_BUYABLE_PRICE" in r["grade_flags"] and r["conviction"] == 4
    r = _rec4q("INTACT", "AT_LEVEL", live=100.0, base=None, bear=80.0, lvl=105.0, verdict="B", wtype="FACTOR")
    D(r, quadrant="GOLDILOCKS")                          # no fair value: nothing to check against (fail-open)
    assert r["verdict"] == "B" and r["entry_level_px"] == 105.0
    print("OK: AT_LEVEL rule (3) enforced (floor, below the price, met wait, fail-open)")


def test_conviction_cap_own_answer_only():
    """Findings 14 + 15 (P3, CLAUDE.md: macro never moves conviction). h8 / sim2 S5: the same held
    INTACT+NOW seat (ER 15%, bear 90) was B conv 4 under GOLDILOCKS but C conv 2 under RISK_OFF - a
    quadrant change alone pushed it under the Director's conviction >= 3 bar. Now only a C that is the
    CRO's own answer caps conviction."""
    import copy as _c
    D = _pc.derive_grade
    base = _rec4q("INTACT", "NOW", live=100.0, base=115.0, bear=90.0, floor_px=70.0, verdict="A", conv=4)
    for q, want in (("GOLDILOCKS", "B"), ("RISK_OFF", "C")):
        r = _c.deepcopy(base)
        D(r, quadrant=q)
        assert r["verdict"] == want and r["conviction"] == 4, (q, r["verdict"], r["conviction"])
        assert "conviction_agent_orig" not in r and "grade_conviction_capped" not in r
    assert "NO_BUYABLE_PRICE" in r["grade_flags"]
    # the real grade-derive verb, quadrant from macro_regime.json (h8)
    for q, want in (("GOLDILOCKS", "B"), ("STAGFLATION", "B"), ("RISK_OFF", "C"), (None, "B")):
        with _WorTree(q) as (W, td):
            _put(td, "results_regime", "H", dict(_c.deepcopy(base), update_mode="carry", carried=True))
            W.grade_derive()
            o = _get(td, "results_regime", "H")
            assert o["verdict"] == want and o["conviction"] == 4, (q, o["verdict"], o["conviction"])
    # a wash-out that reached its level and still fails the floor: C, conviction untouched
    wo = {"level": 92.0, "level_source": "entry_level_px", "price": 91.0, "debate_price": 104.0}
    r = _rec4q("INTACT", "NOW", live=91.0, base=100.0, verdict="A", conv=4)
    D(r, quadrant="GOLDILOCKS", washout=wo)
    assert r["verdict"] == "C" and "WASHOUT_BELOW_FLOOR" in r["grade_flags"] and r["conviction"] == 4
    # the rubric's own wording for that case (INTACT + NONE, "pass for now") is the same price pass
    r = _rec4q("INTACT", "NONE", live=91.0, base=100.0, verdict="C", conv=4)
    res = D(r, quadrant="GOLDILOCKS", washout=wo)
    assert res["washout_outcome"] == "PASS_BELOW_FLOOR" and r["conviction"] == 4
    snap = _c.deepcopy(r)
    D(r, quadrant="GOLDILOCKS")                          # a later re-derive (no bundle) keeps it
    assert r == snap
    r = _rec4q("INTACT", "NONE", live=91.0, base=130.0, verdict="C", conv=4)
    res = D(r, quadrant="GOLDILOCKS", washout=wo)        # the price CLEARS the floor: the CRO's own pass
    assert res["washout_outcome"] == "PASS" and r["conviction"] == 2
    # the CRO's own C still caps: BROKEN, an entry NONE it wrote, IMPAIRED with no test
    for rr in (_rec4q("BROKEN", "NOW", conv=4), _rec4q("INTACT", "NONE", conv=4),
               _rec4q("IMPAIRED", "NOW", tt=None, conv=4)):
        D(rr, quadrant="GOLDILOCKS")
        assert rr["verdict"] == "C" and rr["conviction"] == 2 and rr["conviction_agent_orig"] == 4
    # a record the old code capped for a floor C gets its conviction back on the next derive
    old = _c.deepcopy(base)
    D(old, quadrant="RISK_OFF")
    old.update({"conviction": 2, "conviction_agent_orig": 4, "grade_conviction_capped": True})
    D(old, quadrant="RISK_OFF")
    assert old["verdict"] == "C" and old["conviction"] == 4 and "grade_conviction_capped" not in old
    print("OK: conviction cap only on the CRO's own C (floor / quadrant C leaves conviction alone)")


def test_prior_record_and_continuity():
    """Findings 9 + 16 (P4). sim4 / sim2 S3: prior_record showed the CODE-derived letter, level and
    capped conviction, so a CRO obeying step 1c inherited a price-derived grade as its own answer;
    h5 / h5b: continuity-gate then flagged that obedient CRO as an UNJUSTIFIED_FLIP (A/2 -> C/2, and
    the nonsense C/2 -> C/2)."""
    import copy as _c
    W = _wor()
    D = _pc.derive_grade

    def _full(**kw):
        r = _rec4q(kw.pop("ts", "INTACT"), kw.pop("em", "NOW"), **kw)
        r.update({"source": "opus_regime_mod", "update_mode": "full", "debated_at": "2026-10-04",
                  "whats_changed_since_prior": "", "moderator_conclusion": "Buy now. The thesis holds."})
        return r
    # (a) RISK_OFF: the CRO said INTACT+NOW conv 4, the code published C (no buyable price)
    pr = _full(live=85.0, base=100.0, bear=80.0, verdict="A", conv=4)
    D(pr, quadrant="RISK_OFF")
    assert pr["verdict"] == "C" and pr["verdict_structural"] == "A"
    pc = W._prior_compact_of(pr)
    assert (pc["verdict"], pc["conviction"], pc["thesis_state"], pc["entry_mode"]) == ("A", 4, "INTACT", "NOW")
    cd = pc["code_derived_from_price"]
    assert cd and cd["verdict"] == "C" and "NO_BUYABLE_PRICE" in cd["flags"] and cd["why"]
    # (b) GOLDILOCKS floor-derived B: the committee answered NOW, the code made it a price-wait at 83.33
    fl = _full(live=88.0, base=100.0, bear=70.0, verdict="A", conv=4)
    D(fl, quadrant="GOLDILOCKS")
    pc2 = W._prior_compact_of(fl)
    assert pc2["entry_mode"] == "NOW" and pc2["entry_level_px"] is None and pc2["verdict"] == "A"
    assert pc2["code_derived_from_price"]["entry_mode"] == "AT_LEVEL" and pc2["code_derived_from_price"]["entry_level_px"]
    # (c) an older record shows its stored values, nothing code-derived
    leg = {"symbol": "L", "verdict": "B", "conviction": 3, "live_price": 10.0}
    pcl = W._prior_compact_of(leg)
    assert pcl["verdict"] == "B" and pcl["conviction"] == 3 and pcl["code_derived_from_price"] is None
    # continuity-gate on a temp tree
    with _WorTree("RISK_OFF") as (W, td):
        # (i) the obedient CRO inherits the committee answer -> not a flip
        _put(td, "_archive_prev/results_regime", "XIN", pr)
        _put(td, "results_regime", "XIN", _full(live=85.0, base=100.0, bear=80.0, verdict=pc["verdict"],
                                                conv=pc["conviction"]))
        # (ii) h5: a prior the OLD code capped (C/2, CRO 4) and a CRO that inherits the published C/2
        p5 = _c.deepcopy(pr)
        p5.update({"conviction": 2, "conviction_agent_orig": 4, "grade_conviction_capped": True})
        _put(td, "_archive_prev/results_regime", "X5", p5)
        _put(td, "results_regime", "X5", _full(em="NONE", live=85.0, base=100.0, bear=80.0, verdict="C", conv=2))
        # (iii) h5b: BROKEN_WITH_ENTRY prior (C, capped 2, CRO 4) and a rubric-compliant BROKEN+NONE C/2
        pb = _full(ts="BROKEN", live=100.0, base=130.0, bear=70.0, verdict="C", conv=4)
        D(pb, quadrant="GOLDILOCKS")
        assert pb["conviction"] == 2 and pb["conviction_agent_orig"] == 4
        _put(td, "_archive_prev/results_regime", "Y", pb)
        _put(td, "results_regime", "Y", _full(ts="BROKEN", em="NONE", live=100.0, base=130.0, bear=70.0,
                                              verdict="C", conv=2))
        # (iv) control: a real A/4 -> C/1 re-roll with no dated fact is still flagged
        pa = _full(live=70.0, base=100.0, bear=50.0, verdict="A", conv=4)
        D(pa, quadrant="RISK_OFF")
        assert pa["verdict"] == "A"
        _put(td, "_archive_prev/results_regime", "Z", pa)
        _put(td, "results_regime", "Z", _full(em="NONE", live=70.0, base=100.0, bear=50.0, verdict="C", conv=1))
        W.continuity_gate()
        for s in ("XIN", "Y"):
            assert not _get(td, "results_regime", s).get("continuity_flag"), (s, _get(td, "results_regime", s).get("continuity_flag"))
        # X5: the committee's own answer last week was A/4 (the published C/2 was code-derived from price);
        # writing C/2 with no dated fact is a re-roll of its own answer - flagged (confirm pass, 2026-10-06)
        for s in ("X5", "Z"):
            assert str(_get(td, "results_regime", s).get("continuity_flag") or "").startswith("UNJUSTIFIED_FLIP"), s
    tpl = W._WORKFLOW_TEMPLATE
    assert "never inherit a letter, level or conviction cap the code derived from price" in tpl
    assert "prior_record.code_derived_from_price" in tpl
    print("OK: prior_record carries the committee answer; continuity compares the committee answers on both sides")


def test_washout_ledger_upsert():
    """Findings 12 + 18 (P5). sim3 / h6: lane-stamp ledgered the wash-out once in Gates (BUY/A); a
    material skeptic correction later made the final record a pass, and the ledger kept scoring a BUY
    the book never made. Now an upsert keyed on (date, symbol), refreshed by every grade-derive pass and
    by lane-stamp, keeping cohort-mark's fills. Plus: cohort-mark fills spy0 for rows it did not see on
    their own day (it is not run on the prep day, so xs_* never filled)."""
    import datetime as _dtm
    import json
    import os
    import time
    run = "2026-10-11"
    wo = {"level": 90.0, "level_source": "entry_level_px", "price": 89.0, "debate_price": 100.0, "fall_pct": -11.0,
          "prior_letter": "B", "prior_thesis_state": "INTACT", "prior_entry_mode": "AT_LEVEL", "washout_type": "FACTOR"}
    rec = {"symbol": "XWO", "source": "opus_regime_mod", "update_mode": "full", "verdict": "A", "conviction": 4,
           "thesis_state": "INTACT", "entry_mode": "NOW", "entry_level_px": None, "entry_event": "",
           "washout_type": "NONE", "live_price": 89.0,
           "washout_resolution": {"trigger": "LEVEL_REACHED", "prior_level_px": 90, "resolved_to": "BUY", "note": "x"},
           "valuation": {"live_price": 89.0, "price_currency": "USD", "quote_listing": "XWO", "bear_px": 70.0,
                         "base_fv_px": 115.0, "bull_px": 140.0, "downside_floor_px": None,
                         "valuation_method": "multiple", "horizon_months": 12, "as_of": run}}
    with _WorTree("GOLDILOCKS") as (W, td):
        _put(td, "inputs", "XWO", {"symbol": "XWO", "methodologies": [], "washout": wo, "debate_run": run,
                                   "transcript_date": ""})
        _put(td, "results_regime", "XWO", rec)
        led = W._WASHOUT_LEDGER
        W.grade_derive()                                 # Gates
        W.lane_stamp()
        rows = _ledger_rows(led)
        assert len(rows) == 1 and (rows[0]["resolution"], rows[0]["new_letter"]) == ("BUY", "A"), rows
        rows[0].update({"spy0": 400.0, "r_4w": 1.5})     # a cohort-mark fill must survive the upsert
        led.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
        _put(td, "_skeptic_regime", "XWO", {
            "symbol": "XWO", "verdict": "CONFIRMED_WITH_CORRECTIONS", "correction_severity": "material",
            "kill_scope": "numbers",
            "corrections_typed": [{"field": "base_fv_px", "from": 115.0, "to": 100.0, "basis": "2026-10-09 10-Q"}]})
        _later = time.time() + 5
        os.utime(td / "_skeptic_regime" / "XWO.json", (_later, _later))
        _pc.apply_skeptic_corrections(td / "_skeptic_regime", td / "results_regime", quadrant="GOLDILOCKS")
        W.grade_derive()                                 # the post-Revise grade-rederive pass
        final = _get(td, "results_regime", "XWO")
        assert final["verdict"] == "C" and final["washout_resolution"]["outcome"] == "PASS_BELOW_FLOOR"
        rows = _ledger_rows(led)
        assert len(rows) == 1 and (rows[0]["resolution"], rows[0]["new_letter"], rows[0]["new_entry_mode"]) == \
            ("PASS_BELOW_FLOOR", "C", "NONE"), rows
        assert rows[0]["spy0"] == 400.0 and rows[0]["r_4w"] == 1.5 and rows[0]["coerced"] is True
        W.lane_stamp()                                   # a resume re-run: still one row, still the final one
        rows = _ledger_rows(led)
        assert len(rows) == 1 and rows[0]["resolution"] == "PASS_BELOW_FLOOR"
        W.grade_derive(dry_run=True)                     # dry run writes nothing
        assert _ledger_rows(led) == rows
    # spy0 for a row cohort-mark did not see on its own day: SPY's close on or before the row date
    assert W._close_on_or_before([("2026-10-09", 500.0), ("2026-10-12", 505.0)], "2026-10-11") == 500.0
    assert W._close_on_or_before([("2026-10-12", 505.0)], "2026-10-11") is None
    today = _dtm.date.today()
    d0 = (today - _dtm.timedelta(days=30)).isoformat()
    with _WorTree("GOLDILOCKS") as (W, td):
        W._WASHOUT_LEDGER.write_text(json.dumps({"symbol": "XWO", "date": d0, "price": 100.0,
                                                 "resolution": "BUY"}) + "\n", encoding="utf-8")
        nc, saved = W._numeric_core, (W._numeric_core.fetch_live_quotes, W._spy_eod_closes, W.E.get_key)
        try:
            nc.fetch_live_quotes = lambda syms, **k: {"SPY": 440.0, "XWO": 110.0}
            W._spy_eod_closes = lambda frm: [(d0, 400.0)]
            W.E.get_key = lambda k: None
            W.cohort_mark()
        finally:
            nc.fetch_live_quotes, W._spy_eod_closes, W.E.get_key = saved
        row = _ledger_rows(W._WASHOUT_LEDGER)[0]
        assert row["spy0"] == 400.0 and row["r_4w"] == 10.0 and row["xs_4w"] == 0.0, row
    print("OK: wash-out ledger is an upsert from the final record (+ spy0 backfill for xs_*)")


def test_washout_check_code_level_and_string_level():
    """Findings 19 + 20 (P6, P7). h10: a level the CODE derived from the floor (FLOOR_REDERIVED) fired a
    full Opus wash-out once the price came back to it - grade-derive re-letters that one by itself.
    A string level ("HK$35.8") graded B on 35.8 but could never fire its own wash-out."""
    W = _wor()
    D = _pc.derive_grade
    wo = {"level": 95.0, "level_source": "entry_level_px", "price": 88.0, "debate_price": 100.0, "fall_pct": -12.0}
    r = _rec4q("INTACT", "AT_LEVEL", live=88.0, base=115.0, bear=70.0, floor_px=65.0, lvl=85.0, verdict="B",
               wtype="MECHANICAL")
    D(r, quadrant="GOLDILOCKS", washout=wo)
    assert r["verdict"] == "A"                           # the second price-wait was coerced to a buy
    r.update({"update_mode": "carry", "carried": True, "live_price": 100.0})
    D(r, quadrant="GOLDILOCKS")                          # rallied: the floor re-derive names a code level
    assert r["entry_mode"] == "AT_LEVEL" and r.get("entry_level_px_derived") is not None
    assert W._washout_check(r, {"price": 95.0}) is None, "a code-derived level never fires a wash-out"
    s = _rec4q("INTACT", "AT_LEVEL", live=40.0, base=50.0, bear=30.0, lvl="HK$35.8", verdict="B", wtype="FACTOR")
    D(s, quadrant="GOLDILOCKS")
    assert s["verdict"] == "B" and s["entry_level_px"] == 35.8 and s["entry_level_px_agent_orig"] == "HK$35.8"
    import copy as _c
    snap = _c.deepcopy(s)
    D(s, quadrant="GOLDILOCKS")
    assert s == snap, "idempotent"
    w = W._washout_check(s, {"price": 35.5})
    assert w and w["level_source"] == "entry_level_px" and w["level"] == 35.8
    raw = {"symbol": "S", "verdict": "B", "entry_mode": "AT_LEVEL", "entry_level_px": "HK$35.8",
           "valuation": {"live_price": 37.0}}            # stored by the old code as the raw string
    w = W._washout_check(raw, {"price": 35.5})
    assert w and w["level_source"] == "entry_level_px" and w["level"] == 35.8
    print("OK: wash-out check ignores code-derived levels and parses string levels")


def test_scorecard_snapshot_no_lookahead():
    """Finding 5 (P9). cro_review/sim_lookahead.py: a DELTA record keeps last_full_debate copied from
    its anchor (08-24) while its valuation and four-question fields are dated 10-12. attach_snapshots
    matched on last_full_debate, so the 10-12 values landed on the 08-24 write (implied upside from a
    live price inside the forward window), and the archive refilled them every run (30 rows). Now:
    match on debated_at, else valuation.as_of, else last_full_debate; never fill an earlier write; skip a
    delta/refresh whose own history entry carries the fields; scrub what the archive already holds."""
    import json
    import tempfile
    import cro_scorecard as CS
    hist_e = lambda d, txt, **kw: {"date": d, "timestamp": d + "T11:00:00+00:00", "source": "opus_regime_mod",
                                   "verdict": "B", "conviction": 3, "bull_thesis": txt, "bear_thesis": "b",
                                   "moderator_conclusion": "m", **kw}
    val = lambda as_of, live, base: {"live_price": live, "base_fv_px": base, "bear_px": live * 0.8,
                                     "price_currency": "EUR", "as_of": as_of}
    saved_here = CS.HERE
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        CS.HERE = td                                     # relative_to() tags resolve under the temp tree
        try:
            (td / "hist").mkdir()
            snap = td / "snap"
            snap.mkdir()
            new_val = val("2026-10-12", 14.10, 19.0)
            (td / "hist" / "DUE.json").write_text(json.dumps([
                hist_e("2026-08-24", "anchor"), hist_e("2026-10-05", "carry week"),
                hist_e("2026-10-12", "delta", valuation=new_val, thesis_state="IMPAIRED", entry_mode="ON_EVENT",
                       grade_schema="4q-2026-10")]), encoding="utf-8")
            (td / "hist" / "FUL.json").write_text(json.dumps([hist_e("2026-10-05", "full")]), encoding="utf-8")
            (td / "hist" / "NOAS.json").write_text(json.dumps([hist_e("2026-08-24", "anchor"),
                                                               hist_e("2026-10-12", "delta2")]), encoding="utf-8")
            (td / "hist" / "LEG.json").write_text(json.dumps([hist_e("2026-07-01", "legacy")]), encoding="utf-8")
            (td / "hist" / "REF.json").write_text(json.dumps([hist_e("2026-09-22", "full"),
                                                              hist_e("2026-10-05", "refresh")]), encoding="utf-8")
            (td / "hist" / "LATE.json").write_text(json.dumps([hist_e("2026-09-22", "full")]), encoding="utf-8")
            recs = {
                # the sim: delta, lfd copied from the anchor, typed values dated today
                "DUE": {"symbol": "DUE", "update_mode": "delta", "last_full_debate": "2026-08-24",
                        "debated_at": "2026-10-12", "valuation": new_val, "thesis_state": "IMPAIRED",
                        "entry_mode": "ON_EVENT", "grade_schema": "4q-2026-10"},
                # a delta without debated_at: valuation.as_of dates it; its history entry carries nothing
                "NOAS": {"symbol": "NOAS", "update_mode": "delta", "last_full_debate": "2026-08-24",
                         "valuation": val("2026-10-12", 50.0, 70.0), "thesis_state": "INTACT", "entry_mode": "NOW"},
                "FUL": {"symbol": "FUL", "update_mode": "full", "last_full_debate": "2026-10-05",
                        "debated_at": "2026-10-05", "valuation": val("2026-10-05", 20.0, 26.0)},
                # both dates missing: the old last_full_debate match is the only one left
                "LEG": {"symbol": "LEG", "last_full_debate": "2026-07-01", "thesis_state": "INTACT"},
                # a refresh keeps the original valuation (as_of 09-22): it belongs to the 09-22 write
                "REF": {"symbol": "REF", "update_mode": "refresh", "debated_at": "2026-09-22", "as_of": "2026-10-05",
                        "last_full_debate": "2026-09-22", "valuation": val("2026-09-22", 30.0, 40.0)},
                # debated_at 09-22 but a valuation restated 10-05: never put the later price on 09-22
                "LATE": {"symbol": "LATE", "update_mode": "full", "debated_at": "2026-09-22",
                         "valuation": val("2026-10-05", 9.0, 12.0), "thesis_state": "INTACT"},
            }
            for s, d in recs.items():
                (snap / f"{s}.json").write_text(json.dumps(d), encoding="utf-8")
            rows, _, _ = CS.load_distinct_writes(td / "hist")
            CS.attach_snapshots(rows, snap_dirs=(snap,))
            by = {(r["symbol"], r["date"]): r for r in rows}
            old = by[("DUE", "2026-08-24")]
            for fld in ("valuation", "thesis_state", "entry_mode", "grade_schema"):
                assert not old.get(fld), ("look-ahead onto the 08-24 write", fld, old.get(fld))
            assert by[("DUE", "2026-10-12")]["typed_src"] == "history"
            assert not by[("NOAS", "2026-08-24")].get("valuation") and not by[("NOAS", "2026-08-24")].get("thesis_state")
            assert by[("NOAS", "2026-10-12")]["valuation"]["as_of"] == "2026-10-12"
            assert by[("NOAS", "2026-10-12")]["thesis_state"] == "INTACT"
            assert by[("FUL", "2026-10-05")]["valuation"]["base_fv_px"] == 26.0
            assert by[("LEG", "2026-07-01")]["thesis_state"] == "INTACT"
            assert by[("REF", "2026-09-22")]["valuation"]["as_of"] == "2026-09-22"
            assert not by[("REF", "2026-10-05")].get("valuation")
            assert not by[("LATE", "2026-09-22")].get("valuation"), "a valuation 13 days newer is never filled"
            assert by[("LATE", "2026-09-22")]["thesis_state"] == "INTACT"
            # the archive self-heal: what the old matcher already saved is dropped on the next collect
            arch = td / "arch.jsonl"
            bad = {"symbol": "DUE", "date": "2026-08-24", "verdict": "B", "typed_src": "snapshot:results_regime",
                   "valuation": {"base_fv_px": 23.89, "live_price": 16.72, "as_of": "2026-10-05"},
                   "cro_add_px": 15.0, "level_src": "snapshot:results_regime"}
            keep_hist = {"symbol": "KH", "date": "2026-08-24", "verdict": "B", "typed_src": "history",
                         "valuation": {"base_fv_px": 10.0, "live_price": 8.0, "as_of": "2026-10-05"}}
            keep_near = {"symbol": "KN", "date": "2026-10-02", "verdict": "B", "typed_src": "snapshot:results_regime",
                         "valuation": {"base_fv_px": 10.0, "live_price": 8.0, "as_of": "2026-10-05"},
                         "cro_add_px": 7.5, "level_src": "apex:apex_basket_opus_regime.json"}
            arch.write_text("\n".join(json.dumps(x) for x in (bad, keep_hist, keep_near)) + "\n", encoding="utf-8")
            rows, _, _ = CS.load_distinct_writes(td / "hist")
            rows, _, _ = CS.merge_archive(rows, arch, "2026-10-12")
            assert CS.scrub_lookahead(rows) == 1
            CS.attach_snapshots(rows, snap_dirs=(snap,))
            by = {(r["symbol"], r["date"]): r for r in rows}
            d824 = by[("DUE", "2026-08-24")]
            assert not d824.get("valuation") and not d824.get("cro_add_px") and not d824.get("typed_src"), d824
            assert by[("KH", "2026-08-24")]["valuation"]["base_fv_px"] == 10.0, "history values are never scrubbed"
            assert by[("KN", "2026-10-02")]["valuation"]["base_fv_px"] == 10.0 and by[("KN", "2026-10-02")]["cro_add_px"] == 7.5
            assert CS.scrub_lookahead(rows) == 0, "idempotent"
        finally:
            CS.HERE = saved_here
    print("OK: scorecard snapshots match the date their values were produced (no look-ahead; archive self-heals)")


def _publish_funcs(*names, **stubs):
    """Exec ONLY the named top-level functions of publish_to_frontend.py (never the module: importing it
    runs a real publish) in a namespace holding the real plain_language plus the given stubs."""
    import ast
    import re
    import plain_language
    src = (HERE / "publish_to_frontend.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names}
    missing = [n for n in names if n not in found]
    assert not missing, f"publish_to_frontend.py has no {missing}"
    ns = {"plain_language": plain_language, "re": re, **stubs}
    exec(compile(ast.Module(body=[found[n] for n in names], type_ignores=[]), "publish_to_frontend.py", "exec"), ns)
    return ns, src


def test_publish_plain_event_strings():
    """Finding 6 (P10). The UI prints cro_add_event (seat chip + tooltip), pending_gate.event (pending
    tooltip) and the stock-page strip builds its sentence from thesis_test.metric / resolves_on - all raw,
    so 'Q3 print confirms the PENDING_HARD catalyst; thesis_test passes' reached the screen as is. Publish
    now plainifies those display copies (after both tracker runs; the raw record is never touched)."""
    import copy as _c
    raw_ev = "Q3 print confirms the PENDING_HARD catalyst; thesis_test passes"
    plain_ev = "Q3 print confirms the firmly dated catalyst; thesis test passes"
    tt = {"metric": "SOFT_EXTENDED order book vs entry_level_px", "pass_level": 105, "fail_level": "orders -5% (BROKEN)",
          "resolves_on": "2026-11-05 Q3 print (PENDING_HARD)"}
    ns, src = _publish_funcs("_plain_test", "_plain_display_events", "_hist_entry",
                             risk_badge=lambda *a, **k: None, skeptic_shard=lambda s: {})
    rec = {"symbol": "X", "verdict": "B", "conviction": 3, "bull_thesis": "b", "thesis_state": "IMPAIRED",
           "thesis_test": tt, "entry_mode": "ON_EVENT", "entry_event": raw_ev}
    keep = _c.deepcopy(rec)
    # (1) the seat chip / tooltip strings, after both tracker runs
    eg = {"letter": "B", "mode": "ON_EVENT", "level": None, "event": raw_ev}
    pg = {"kind": "event", "event": raw_ev, "since": "2026-10-12", "source": "entry_gate"}
    es = [{"symbol": "X", "cro_add_event": raw_ev, "entry_gate": eg, "pending_gate": pg},
          {"symbol": "Y", "cro_add_event": "", "entry_gate": None, "pending_gate": {"kind": "next_close"}}]
    ns["_plain_display_events"](es)
    assert es[0]["cro_add_event"] == plain_ev, es[0]["cro_add_event"]
    assert es[0]["entry_gate"]["event"] == plain_ev and es[0]["pending_gate"]["event"] == plain_ev
    assert eg["event"] == raw_ev and pg["event"] == raw_ev, "the gate dicts are copied, never edited in place"
    assert es[0]["pending_gate"]["kind"] == "event" and es[0]["pending_gate"]["since"] == "2026-10-12"
    assert es[1] == {"symbol": "Y", "cro_add_event": "", "entry_gate": None, "pending_gate": {"kind": "next_close"}}
    # (2) the dated history entry the stock-page strip reads
    e = ns["_hist_entry"](rec, "", "2026-10-12", "t")
    assert e["thesis_test"]["metric"] == "soft and undated order book vs entry level", e["thesis_test"]
    assert e["thesis_test"]["fail_level"] == "orders -5% (broken)" and e["thesis_test"]["pass_level"] == 105
    assert e["thesis_test"]["resolves_on"] == "2026-11-05 Q3 print (firmly dated)"
    assert "PENDING_HARD" not in str(e) and "thesis_test passes" not in str(e)
    assert rec == keep, "the raw record is never touched"
    # (3) the per-methodology overlay (debated-but-not-seated names)
    ov = _publish_funcs("_plain_test", "_opus_overlay", risk_badge=lambda *a, **k: None,
                        skeptic_shard=lambda s: {}, dossier_for=lambda s: "", RES=Path("."),
                        load=lambda p, *a: _c.deepcopy(rec),
                        _GRADE_REC_FIELDS=("verdict", "thesis_state", "thesis_test", "entry_mode",
                                           "entry_event"))[0]["_opus_overlay"]("X")
    assert ov["thesis_test"]["metric"] == "soft and undated order book vs entry level" and ov["entry_event"] == plain_ev
    assert ns["_plain_test"](None) is None and ns["_plain_test"]("x") == "x"
    # (4) wiring: the seat pass runs after the weighted tracker run and before the payload is assembled;
    # the seat entries carry the plain thesis_test copy
    i_w = src.index('local_name="speculair_apex_tracking_weighted.json"')
    i_p = src.index("    _plain_display_events(entries)")
    i_a = src.index('baskets["apex_basket"] = entries')
    assert i_w < i_p < i_a, (i_w, i_p, i_a)
    assert src.count('"thesis_test": _plain_test(rec.get("thesis_test"))') == 2   # seat entry + overlay
    print("OK: publish shows the event and thesis-test strings in plain words")


def main():
    test_numbers_repricing()
    test_apply_skeptic_corrections()
    test_entry_posture_reconciliation()
    test_derive_grade()
    test_entry_posture_typed()
    test_washout_fall_vs_level()
    test_revise_washout_constraint()
    test_level_rule3()
    test_conviction_cap_own_answer_only()
    test_prior_record_and_continuity()
    test_washout_ledger_upsert()
    test_washout_check_code_level_and_string_level()
    test_scorecard_snapshot_no_lookahead()
    test_publish_plain_event_strings()
    apx = R._load(R.REGIME_F)
    if not apx or not apx.get("apex_basket"):
        print("SKIP: no apex_basket_opus_regime.json to test against")
        return
    uni = {x["symbol"]: x for x in (R._load(R.ROOT / "_radar_universe.json", []) or [])}
    scan_by = R._scan_by_sym()

    apx, picks, extra = R.process(copy.deepcopy(apx), uni, scan_by)  # the SAME path main() runs
    weights = apx["weights"]

    print(f"apex ({len(picks)}):")
    for p in picks:
        print(f"  {p['symbol']:8} moat={str(p.get('moat') or '-'):6} erosion={(p.get('moat_erosion') or '-'):4} "
              f"sev={p.get('erosion_severity', '-'):16} theme={str(p.get('secular_theme') or '-'):26} "
              f"units->{p.get('size_units')}->{p.get('size_units_effective')} wt={p.get('weight_pct')}%")
    print("secular-theme caps:", extra)
    s = round(sum(weights.values()), 4)
    # build_weights rounds EACH weight to 4dp, so the sum lands within ~1e-4 of 1.0 rather
    # than exactly on it whenever the units don't divide cleanly (this fixture: 1.1/7.2 ->
    # 0.1528 x3 + 0.75/7.2 -> 0.1042 x2 + 0.8/7.2 -> 0.1111 x3 = 1.0001; a bare
    # [1.4,1.1,0.8] basket drifts the same way). The 1e-6 assert was stricter than the
    # shared sizing path's actual guarantee and failed on this fixture regardless of the
    # cycle layer — verified red at 03f3a71, pre-debt-cycle. Asserted at the real
    # guarantee; tighten only by making build_weights renormalize exactly (which would
    # move published weights in BOTH the apex and value books).
    assert abs(s - 1.0) < 1e-3, f"weights must sum to ~1.0 (4dp rounding), got {s}"
    assert all(isinstance(p.get("weight_pct"), (int, float)) for p in picks), "every pick needs weight_pct"
    print(f"OK: weights sum={s}, every pick weighted, no crash.")


if __name__ == "__main__":
    main()
