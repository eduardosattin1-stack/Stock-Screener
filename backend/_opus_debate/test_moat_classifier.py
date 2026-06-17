#!/usr/bin/env python3
"""Ground-truth acceptance test for the deterministic moat / terminal-erosion gate (Piece 1).

Runs _moat_features over the 12 audited names and asserts the classification matches the manual
analysis. The deterministic gate is intentionally conservative (cap, never exclude) and reliably
separates the value-destroyers (GLOB) and clear eroders (CMCSA) from the durable franchises
(ADBE/NTES/MMS). IT/EEFT/LYFT/PLX are caught by the agent moat tag + apex skeptic, NOT asserted here.

Usage: python backend/_opus_debate/test_moat_classifier.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # backend/_opus_debate
BK = os.path.dirname(HERE)                           # backend
sys.path.insert(0, BK)
os.chdir(BK)
# moat_features is pure computation over already-loaded JSON — no FMP fetch, so no API key needed.

from _moat import moat_features as _moat_features  # noqa: E402

ROOT = os.path.join(BK, "_opus_debate")


def _load():
    uni = {x["symbol"]: x for x in json.load(open(os.path.join(ROOT, "_radar_universe.json"), encoding="utf-8"))}
    scan = None
    for p in (os.path.join(BK, "..", "frontend", "public", "latest_global.json"),
              os.path.join(ROOT, "latest_global.json")):
        if os.path.exists(p):
            scan = json.load(open(p, encoding="utf-8"))
            break
    sc_by = {s.get("symbol"): s for s in (scan or {}).get("stocks", [])}
    return uni, sc_by


def _result(sym, uni):
    rp = os.path.join(ROOT, "results_regime", sym + ".json")
    if os.path.exists(rp):
        try:
            return json.load(open(rp, encoding="utf-8"))
        except Exception:
            pass
    return {"sector": uni.get(sym, {}).get("sector", "")}


TARGETS = ["ADBE", "IT", "GLOB", "CMCSA", "EEFT", "PLX.PA", "LYFT", "NTES", "FSLR", "SCR.PA", "MMS", "THC"]


def main():
    uni, sc_by = _load()
    rows = {}
    print(f"{'sym':8} {'score':>5} {'erosion':>7} {'severity':>16} {'roic<h':>6} {'ret':>8} {'nm':>8} {'gm':>9} {'rev':>8} {'decel':>5}")
    for sym in TARGETS:
        mf = _moat_features(uni.get(sym, {}), sc_by.get(sym, {}), _result(sym, uni))
        rows[sym] = mf
        print(f"{sym:8} {mf['moat_score']:>5} {(mf['moat_erosion'] or '-'):>7} {mf['erosion_severity']:>16} "
              f"{str(mf['roic_below_hurdle']):>6} {mf['returns_trend']:>8} {mf['net_margin_trend']:>8} "
              f"{mf['gross_margin_trend']:>9} {mf['revenue_trend']:>8} {str(mf['revenue_decelerating']):>5}")

    # The apex/value skeptic treats a name as a default-REFUTE candidate when the moat is value-
    # destroying OR (capped AND earning below its cost-of-capital hurdle). This is robust to thin
    # data: GLOB/PLX/SCR are foreign mid-caps absent from the scan universe, so their per-year margin
    # series are unknown and the trend-based "value-destroying" label cannot confirm — but roic_below
    # + CAP still routes them to the skeptic. Full hard-exclusion is the skeptic's call, not the gate's.
    def is_refute_candidate(m):
        return m["erosion_severity"] == "value-destroying" or (m["moat_erosion"] == "CAP" and m["roic_below_hurdle"])

    failures = []

    def expect(sym, cond, msg):
        if sym not in rows:
            return
        if not cond(rows[sym]):
            failures.append(f"{sym}: {msg} (got {rows[sym]})")

    # GLOB must at least be capped + a skeptic REFUTE candidate (value-destroying when series exist).
    expect("GLOB", lambda m: m["moat_erosion"] == "CAP" and is_refute_candidate(m),
           "expected CAP + skeptic REFUTE candidate (sub-hurdle ROIC)")
    # CMCSA / IT / THC: clear eroders -> CAP (cushioned, NOT value-destroying).
    for cap in ("CMCSA", "IT", "THC"):
        expect(cap, lambda m: m["moat_erosion"] == "CAP", "expected CAP (eroding moat)")
    # Durable franchises: rising returns / non-eroding margins must NOT trip the gate.
    for clean in ("ADBE", "NTES", "MMS"):
        expect(clean, lambda m: m["moat_erosion"] == "" and m["erosion_severity"] == "none",
               "expected clean (rising returns / non-eroding margins must not trip)")

    print("REFUTE candidates (skeptic default-REFUTE):", [s for s in TARGETS if s in rows and is_refute_candidate(rows[s])])
    print()
    if failures:
        print("ACCEPTANCE FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("ACCEPTANCE PASSED: GLOB capped+REFUTE-candidate; CMCSA/IT/THC=CAP; ADBE/NTES/MMS clean.")


if __name__ == "__main__":
    main()
