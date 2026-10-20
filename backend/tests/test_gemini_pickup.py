"""Gemini second-opinion pickup: per-seat classification (2026-10-20). No network, no files. Run:
    python backend/tests/test_gemini_pickup.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gemini_confirm"))
import pickup_week as P  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


ok = {"verdict": "CONFIRMED_WITH_CORRECTIONS", "kill_scope": "numbers", "revised_fv_px": None}
print("=== classify ===")
check("within 15%, a buy, upside, skeptic fine -> confirmed",
      P.classify(23.55, 21.9, 14.94, "A", ok)[0] == "confirmed")
check("0% gap but our record's number refuted -> repriced (MMS-type)",
      P.classify(78.0, 78.0, 61.3, "A", {"verdict": "REFUTED", "kill_scope": "numbers", "revised_fv_px": 77.5})[0] == "repriced")
check("21% gap -> repriced (ROCK-type)", P.classify(43.5, 55.0, 37.7, "B", ok)[0] == "repriced")
check("skeptic revises our value >10% without refuting -> repriced",
      P.classify(100, 100, 80, "B", {"verdict": "CONFIRMED_WITH_CORRECTIONS", "kill_scope": "numbers", "revised_fv_px": 85})[0] == "repriced")
check("gap over 30% -> disagreement", P.classify(60, 100, 50, "B", ok)[0] == "disagreement")
check("second model would pass (C) -> disagreement", P.classify(100, 100, 80, "C", ok)[0] == "disagreement")
check("no upside on the second model's value -> disagreement", P.classify(79, 85, 80, "B", ok)[0] == "disagreement")
check("skeptic kills our thesis -> disagreement",
      P.classify(100, 100, 80, "B", {"verdict": "REFUTED", "kill_scope": "thesis"})[0] == "disagreement")
check("reasons are plain language", "from ours" in " ".join(P.classify(60, 100, 50, "B", ok)[1]))

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
