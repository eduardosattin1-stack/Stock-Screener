"""Free-float floor (2026-10-13). No network. Run: python backend/tests/test_free_float.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import free_float as FF  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "ff.json")
    json.dump({"by_symbol": {"KARE.AT": {"free_float_pct": 4.2, "below_min": True},
                             "DUE.DE": {"free_float_pct": 73.6, "below_min": False}}}, open(p, "w", encoding="utf-8"))
    apx = {"apex_basket": [{"symbol": "DUE.DE"}, {"symbol": "KARE.AT"}, {"symbol": "NOFLOAT"}],
           "runner_ups": [{"symbol": "INCH.L"}, {"symbol": "KARE.AT"}]}
    out = FF.float_demote(apx, p)
    seats = [x["symbol"] for x in apx["apex_basket"]]
    check("KARE.AT (4.2% float) demoted", out == ["KARE.AT"] and "KARE.AT" not in seats, (out, seats))
    check("demoted name goes to the FRONT of runner_ups, no duplicate",
          [r["symbol"] for r in apx["runner_ups"]] == ["KARE.AT", "INCH.L"], apx["runner_ups"])
    check("reason stamped", apx["runner_ups"][0].get("free_float_demoted") and "15%" in apx["runner_ups"][0]["free_float_reason"])
    check("unknown float never blocks (fail-open)", "NOFLOAT" in seats)
    check("a healthy float stays seated and carries its figure",
          "DUE.DE" in seats and apx["apex_basket"][0].get("free_float_pct") == 73.6)
    apx2 = {"apex_basket": [{"symbol": "DUE.DE"}]}
    check("missing file = no demotion", FF.float_demote(apx2, os.path.join(td, "absent.json")) == [] and len(apx2["apex_basket"]) == 1)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
