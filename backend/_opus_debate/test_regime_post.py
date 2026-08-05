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


def main():
    test_numbers_repricing()
    test_apply_skeptic_corrections()
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
