"""Screen plausibility checks in weekly prep (Bruno 2026-11-28, after the Week 48 basket audit).

Offline: no network, no GCS. Run: python backend/tests/test_screen_checks.py
"""
import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import weekly_opus_refresh as W  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def basket(*rows):
    return {"picks": [{"symbol": s, "fair_value": f, "price": p} for s, f, p in rows]}


SRC = {
    "dcf_fcff": basket(("CTVA", 39.0, 7.89), ("CLEAN", 12.0, 10.0), ("MIXED", 50.0, 10.0)),
    "epv": basket(("CTVA", 36.6, 7.89)),
    "acquirers_multiple": basket(("MIXED", 12.0, 10.0)),
    "graham_revised": basket(("GRAHAMONLY", 90.0, 10.0), ("CLEAN", 80.0, 10.0)),
}
RET = {"fundamental_momentum", "graham_revised"}
UNI = {"CTVA": ["dcf_fcff", "epv"], "CLEAN": ["dcf_fcff"], "MIXED": ["dcf_fcff", "acquirers_multiple"]}
CORP = {"CTVA": [{"date": "2026-10-01", "kind": "spin-off", "ratio": "1333:200"}]}
LIVE = {"CTVA": 8.23, "CLEAN": 10.1, "MIXED": 16.0}

notes, imp = W._screen_checks(UNI, SRC, RET, LIVE, CORP)

check("a name whose every basket claims >3x the price is 'implausible only'", "CTVA" in imp)
check("one plausible basket keeps a name out of 'implausible only'", "MIXED" not in imp)
check("a clean name gets no note", "CLEAN" not in notes)
check("a retired basket's claim is ignored (graham 8x on CLEAN)", "CLEAN" not in notes)
check("the spin-off is named with its date",
      any("spin-off took effect on 2026-10-01" in m for m in notes.get("CTVA", [])))
check("each >3x basket gets its own note", sum("screen puts fair value" in m for m in notes["CTVA"]) == 2)
check("a screen price far from the live quote is flagged (MIXED 10 vs 16)",
      any("away from the live quote" in m for m in notes.get("MIXED", [])))
check("a screen price within the band is not flagged (CTVA 7.89 vs 8.23)",
      not any("away from the live quote" in m for m in notes["CTVA"]))
check("exactly 3.0x is not flagged (threshold is strictly above)",
      not W._screen_checks({"X": ["epv"]}, {"epv": basket(("X", 30.0, 10.0))}, set(), {}, {})[0])

block = W._screen_checks_block(notes["CTVA"])
check("the bundle block has the header and one line per note",
      block.startswith("\n\n=== SCREEN DATA CHECKS") and block.count("\n- ") == len(notes["CTVA"]))
check("no notes -> empty block", W._screen_checks_block(None) == "" and W._screen_checks_block([]) == "")
check("the block is plain ASCII (bundles feed agents; keep the house text clean)", block.isascii())
check("numbers never print in scientific notation", W._num(397100.0) == "397,100" and "e+" not in W._num(1e9))
check("small prices keep their precision", W._num(9.135) == "9.135" and W._num(39.857) == "39.86")
check("graham_revised is retired from the debate universe (source check)",
      'RETIRED_METHS = {"fundamental_momentum", "graham_revised"}' in Path(W.__file__).read_text(encoding="utf-8"))
check("screen tags are not counted as baskets", {"apex", "value_apex", "second_opinion"} <= W.SCREEN_TAGS)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
