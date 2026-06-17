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


def main():
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
    assert abs(s - 1.0) < 1e-6, f"weights must sum to 1.0, got {s}"
    assert all(isinstance(p.get("weight_pct"), (int, float)) for p in picks), "every pick needs weight_pct"
    print(f"OK: weights sum={s}, every pick weighted, no crash.")


if __name__ == "__main__":
    main()
