"""Basket means bought (2026-10-13). No network. Run: python backend/tests/test_seat_means_bought.py
A NEW seat whose own debate says wait is a runner-up, not a basket member; held seats are untouched."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_opus_debate"))
sys.path.insert(0, os.path.join(HERE, ".."))
import _post_common as pc  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def book():
    return {"director_memo": "ROTATION\nADDED: ...", "runner_ups": [{"symbol": "OLD"}], "apex_basket": [
        {"symbol": "BUYNOW", "decision": "ADD", "entry_posture": "scale_in", "cro_verdict": "A"},
        {"symbol": "WAITPX", "decision": "ADD", "entry_posture": "wait_for_weakness", "cro_verdict": "B", "cro_add_px": 411.0},
        {"symbol": "WAITEV", "decision": "ADD", "entry_posture": "on_confirmation: 22 Oct update", "cro_verdict": "B"},
        {"symbol": "HELDW", "decision": "KEEP", "entry_posture": "wait_for_weakness", "cro_verdict": "B", "cro_add_px": 15.0},
        {"symbol": "OVERR", "decision": "ADD", "entry_posture": "wait_for_weakness", "cro_verdict": "B",
         "entry_posture_source": "director-override"},
        {"symbol": "BGRADE", "decision": "ADD", "cro_verdict": "B"},
    ]}


b = book()
held = {p["symbol"] for p in b["apex_basket"] if p["decision"] != "ADD"}
moved = pc.seat_means_bought(b, held, "director_memo")
seats = [p["symbol"] for p in b["apex_basket"]]
check("wait-for-price ADD -> runner-up", "WAITPX" in moved and "WAITPX" not in seats, (moved, seats))
check("wait-for-event ADD -> runner-up", "WAITEV" in moved)
check("B grade with no enter-now posture -> runner-up", "BGRADE" in moved)
check("buy-now ADD stays seated", "BUYNOW" in seats)
check("HELD wait-graded seat is untouched (keep != buy here)", "HELDW" in seats)
check("dated Director override keeps its seat", "OVERR" in seats)
ru = [r["symbol"] for r in b["runner_ups"]]
check("moved names go to the FRONT of runner_ups, old ones kept", ru[:3] == ["WAITPX", "WAITEV", "BGRADE"] and ru[-1] == "OLD", ru)
trig = {r["symbol"]: r.get("runner_up_trigger") for r in b["runner_ups"]}
check("price trigger stamped", trig["WAITPX"] == "buys near 411", trig)
check("event trigger stamped", trig["WAITEV"].startswith("buys after 22 Oct"), trig)
check("memo gets the seat-rule note on top", b["director_memo"].startswith("SEAT RULE"))
b2 = {"apex_basket": [{"symbol": "X", "decision": "ADD", "entry_posture": "scale_in", "cro_verdict": "A"}], "runner_ups": []}
check("nothing to move -> book and memo untouched", pc.seat_means_bought(b2, set()) == [] and len(b2["apex_basket"]) == 1 and "director_memo" not in b2)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
