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


def main():
    test_numbers_repricing()
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
