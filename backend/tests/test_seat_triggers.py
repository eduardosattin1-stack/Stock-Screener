"""Held-seat re-debate triggers (2026-10-19): price from the last FULL debate, results release,
macro change. No network: fetchers are injected. Run:
    python backend/tests/test_seat_triggers.py
Background: on 2026-10-19 INTU sat +19% above its 2026-09-29 full debate while the price trigger
read +5.6% (weekly delta updates restate the reference price), 9980.HK / 267260.KS could never be
re-underwritten on their own results (no FMP transcript), and nothing re-checked a seat when the
macro read moved.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import _seat_triggers as ST  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def boom(*a, **k):
    raise AssertionError("must not be called")


TODAY = datetime.now().strftime("%Y-%m-%d")


def days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


print("=== 1. price reference = the last FULL debate ===")
delta_rec = {"update_mode": "delta", "last_full_debate": "2026-09-29", "valuation": {"live_price": 302.75}}
px, src = ST.full_debate_price(delta_rec, "INTU", True, lambda s, d: 268.03 if d == "2026-09-29" else None,
                               lambda pr: pr["valuation"]["live_price"])
check("a delta-restated seat is measured from the close on its full-debate date (INTU 268.03, not 302.75)",
      px == 268.03 and "2026-09-29" in src, (px, src))
px, src = ST.full_debate_price(dict(delta_rec, full_debate_px=268.0), "INTU", True, boom, None)
check("a stamped full_debate_px wins and never hits the network", px == 268.0, (px, src))
full_rec = {"update_mode": "full", "last_full_debate": "2026-10-12", "valuation": {"live_price": 58.87}}
px, _ = ST.full_debate_price(full_rec, "MMS", True, boom, lambda pr: pr["valuation"]["live_price"])
check("a record that is still the full debate uses its own price (no network)", px == 58.87, px)
px, _ = ST.full_debate_price(delta_rec, "XYZ", False, boom, lambda pr: pr["valuation"]["live_price"])
check("a non-seat never hits the network (legacy debate price)", px == 302.75, px)
px, _ = ST.full_debate_price(delta_rec, "INTU", True, lambda s, d: None, lambda pr: pr["valuation"]["live_price"])
check("history unavailable -> falls back to the record price (fail-open)", px == 302.75, px)

print("\n=== 2. results release ===")
rows = [{"date": "2026-11-19", "epsActual": None, "revenueActual": None},
        {"date": "2026-08-25", "epsActual": 4.03, "revenueActual": 3.9e9},
        {"date": "2025-10-24", "epsActual": None, "revenueActual": 1.0e9}]
check("newest REPORTED date on or before today (future/unreported rows ignored)",
      ST.last_report_date(rows, "2026-10-19") == "2026-08-25", ST.last_report_date(rows, "2026-10-19"))
check("revenue-only print counts as reported",
      ST.last_report_date(rows[2:], "2026-10-19") == "2025-10-24")
check("release after the full debate -> trigger",
      "results released 2026-10-20" in (ST.release_trigger({"last_full_debate": "2026-08-10"}, "2026-10-20") or ""))
check("release on/before the full debate -> no trigger",
      ST.release_trigger({"last_full_debate": "2026-08-25"}, "2026-08-25") is None)
check("no report date / no debate date -> no trigger (fail-open)",
      ST.release_trigger({"last_full_debate": "2026-08-25"}, None) is None and ST.release_trigger({}, "2026-10-01") is None)

print("\n=== 3. macro change ===")
check("live read: quadrant + phase", ST.macro_now({"quadrant": "REFLATION", "quadrant_inputs": {"ok": True},
                                                   "debt_cycle": {"debt_cycle_phase": "DISCIPLINE"}})
      == {"quadrant": "REFLATION", "phase": "DISCIPLINE"})
check("stale quadrant inputs -> quadrant unknown (fail-open)",
      ST.macro_now({"quadrant": "GOLDILOCKS", "quadrant_inputs": {"ok": False}})["quadrant"] is None)
check("note parse: enum token", ST.quadrant_from_note("growth up x hot: REFLATION read") == "REFLATION")
check("note parse: plain word", ST.quadrant_from_note("In a reflationary backdrop") == "REFLATION")
check("note parse: 'risk-off' prose is NOT the RISK_OFF quadrant", ST.quadrant_from_note("a risk-off tape") is None)
ledger = [{"date": "2026-07-20", "book": "cycle", "debt_cycle_phase": "EXPANSION"},
          {"date": "2026-07-27", "book": "cycle", "debt_cycle_phase": "DISCIPLINE"},
          {"date": "2026-08-03", "book": "other", "debt_cycle_phase": "FORCING"}]
check("phase on a date = latest cycle row on or before it",
      ST.phase_on("2026-07-25", ledger) == "EXPANSION" and ST.phase_on("2026-09-01", ledger) == "DISCIPLINE")
check("stamped macro read wins",
      ST.macro_at_full_debate({"macro_at_full_debate": {"quadrant": "GOLDILOCKS", "phase": "DISCIPLINE"}})
      == {"quadrant": "GOLDILOCKS", "phase": "DISCIPLINE"})
check("legacy full record: quadrant from its note, phase from the ledger",
      ST.macro_at_full_debate({"update_mode": "full", "last_full_debate": "2026-07-22",
                               "macro_fit_note": "GOLDILOCKS backdrop"}, ledger)
      == {"quadrant": "GOLDILOCKS", "phase": "EXPANSION"})
check("legacy DELTA record: note ignored (a delta may have rewritten it) -> quadrant unknown",
      ST.macro_at_full_debate({"update_mode": "delta", "last_full_debate": "2026-08-10",
                               "macro_fit_note": "REFLATION"}, ledger)["quadrant"] is None)
B = {"quadrant": "REFLATION", "phase": "DISCIPLINE"}
check("no change -> no trigger", ST.macro_exposure({"macro_fit": "HEADWIND"}, B, dict(B)) is None)
check("change but the seat is not exposed -> no trigger",
      ST.macro_exposure({"macro_fit": "NEUTRAL"}, B, {"quadrant": "STAGFLATION", "phase": "DISCIPLINE"}, "mixed", "cash_now") is None)
r = ST.macro_exposure({"macro_fit": "HEADWIND"}, B, {"quadrant": "STAGFLATION", "phase": "DISCIPLINE"})
check("change + debate called macro a headwind -> trigger", r and "REFLATION -> STAGFLATION" in r and "headwind" in r, r)
r = ST.macro_exposure({"macro_fit": "NEUTRAL"}, {"quadrant": "GOLDILOCKS", "phase": None},
                      {"quadrant": "REFLATION", "phase": None}, "exposed")
check("into REFLATION + inflation-exposed margins -> trigger", r and "2021-22 inflation" in r, r)
check("into GOLDILOCKS + inflation-exposed margins -> no trigger",
      ST.macro_exposure({"macro_fit": "NEUTRAL"}, {"quadrant": "REFLATION", "phase": None},
                        {"quadrant": "GOLDILOCKS", "phase": None}, "exposed") is None)
r = ST.macro_exposure({"macro_fit": "NEUTRAL"}, {"quadrant": None, "phase": "EXPANSION"},
                      {"quadrant": None, "phase": "DISCIPLINE"}, None, "story")
check("into DISCIPLINE + story-duration name -> trigger", r and "EXPANSION -> DISCIPLINE" in r, r)
check("UNKNOWN now never triggers (a data gap must not churn the book)",
      ST.macro_exposure({"macro_fit": "HEADWIND"}, B, {"quadrant": None, "phase": None}) is None)
check("UNKNOWN at the debate never triggers",
      ST.macro_exposure({"macro_fit": "HEADWIND"}, {"quadrant": None, "phase": None}, B) is None)
NOW = {"quadrant": "STAGFLATION", "phase": "DISCIPLINE"}
cands = [(s, {"macro_fit": "HEADWIND", "last_full_debate": d, "macro_at_full_debate": {"quadrant": "REFLATION", "phase": "DISCIPLINE"}})
         for s, d in (("CCC", "2026-10-01"), ("AAA", "2026-08-01"), ("BBB", "2026-09-01"))]
cands.append(("DDD", {"macro_fit": "NEUTRAL", "last_full_debate": "2026-07-01",
                      "macro_at_full_debate": {"quadrant": "REFLATION", "phase": "DISCIPLINE"}}))
promo, defer = ST.promote_macro_seats(cands, NOW, cap=2)
check("cap: the two OLDEST exposed seats are promoted, the rest deferred; unexposed untouched",
      sorted(promo) == ["AAA", "BBB"] and defer == ["CCC"], (promo, defer))
check("nothing live now -> nothing promoted", ST.promote_macro_seats(cands, {"quadrant": None, "phase": None}) == ({}, []))

print("\n=== lane-stamp helpers ===")
rec = {"update_mode": "full", "valuation": {"live_price": 59.39}}
c1 = ST.stamp_full_debate(rec, "2026-10-19", {"quadrant": "REFLATION", "phase": "DISCIPLINE"})
c2 = ST.stamp_full_debate(rec, "2026-10-19", {"quadrant": "REFLATION", "phase": "DISCIPLINE"})
check("full debate stamps price + macro read; idempotent", c1 and not c2 and rec["full_debate_px"] == 59.39
      and rec["macro_at_full_debate"]["quadrant"] == "REFLATION", rec)
d = {"update_mode": "delta", "full_debate_px": None}
ST.carry_full_stamps(d, {"full_debate_px": 268.03, "full_debate_px_date": "2026-09-29",
                         "macro_at_full_debate": {"quadrant": "GOLDILOCKS"}})
check("delta keeps the anchor's stamps", d["full_debate_px"] == 268.03 and d["macro_at_full_debate"]["quadrant"] == "GOLDILOCKS", d)
d2 = {"full_debate_px": 1.0}
ST.carry_full_stamps(d2, {"full_debate_px": 2.0})
check("a stamp already on the delta is never overwritten", d2["full_debate_px"] == 1.0)

print("\n=== integration: weekly_opus_refresh routing + lane-stamp (temp dirs, no network) ===")
_cwd = os.getcwd()
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import weekly_opus_refresh as W  # noqa: E402  (chdirs to backend/ on import)
os.chdir(_cwd)
os.environ.pop("FORCE_FULL_DEBATE", None)
with tempfile.TemporaryDirectory() as td:
    prior = Path(td) / "prior"
    prior.mkdir()

    def put(sym, rec):
        (prior / f"{sym}.json").write_text(json.dumps(rec), encoding="utf-8")

    lfd = days_ago(20)
    put("INTU", {"symbol": "INTU", "update_mode": "delta", "last_full_debate": lfd, "debated_at": days_ago(7),
                 "catalyst_status": "SOFT_EXTENDED", "valuation": {"live_price": 302.75}})
    hist = lambda s, dt: 268.03 if dt == lfd else None   # noqa: E731
    no_rel = lambda s: [{"date": days_ago(60), "epsActual": 1.0}]   # noqa: E731
    dec, why, _ = W._carry_or_debate("INTU", {"price": 300.0}, [], prior, {"INTU"}, live_px=319.65,
                                     hist_close_fn=hist, report_rows_fn=no_rel)
    check("INTU: +19% since its full debate -> FULL re-debate", dec == "debate" and "since the last full debate" in why, why)
    dec, why, _ = W._carry_or_debate("INTU", {"price": 300.0}, [], prior, {"INTU"}, live_px=319.65,
                                     hist_close_fn=lambda s, dt: None, report_rows_fn=no_rel)
    check("control: measured from the weekly restatement it stays a delta (the old blind spot)",
          dec == "debate" and why == "seat-relevant-only", why)

    put("9980.HK", {"symbol": "9980.HK", "update_mode": "delta", "last_full_debate": days_ago(42),
                    "debated_at": days_ago(7), "full_debate_px": 100.0, "valuation": {"live_price": 99.5}})
    rel = lambda s: [{"date": days_ago(3), "epsActual": 2.6}, {"date": days_ago(-10), "epsActual": None}]   # noqa: E731
    dec, why, _ = W._carry_or_debate("9980.HK", {"price": 97.4}, [], prior, {"9980.HK"}, live_px=97.4,
                                     hist_close_fn=boom, report_rows_fn=rel)
    check("9980.HK: reported after its full debate, no transcript -> FULL re-debate",
          dec == "debate" and why.startswith("results released"), why)
    dec, why, _ = W._carry_or_debate("9980.HK", {"price": 97.4}, [], prior, {"9980.HK"}, live_px=97.4,
                                     hist_close_fn=boom, report_rows_fn=boom)
    check("earnings feed down -> no release trigger, stays a delta (fail-open)",
          dec == "debate" and why == "seat-relevant-only", why)

    put("ABC", {"symbol": "ABC", "update_mode": "full", "debated_at": days_ago(5), "last_full_debate": days_ago(5),
                "valuation": {"live_price": 100.0}})
    dec, why, _ = W._carry_or_debate("ABC", {"price": 104.0}, [], prior, set(), hist_close_fn=boom, report_rows_fn=boom)
    check("non-seat: no release/history calls, behaviour unchanged (carry)", dec == "carry", why)

    # lane-stamp: point the module's dirs at the temp tree
    root = Path(td) / "root"
    (root / "inputs").mkdir(parents=True)
    (root / "results_regime").mkdir()
    (root / "_archive_prev" / "results_regime").mkdir(parents=True)
    (root / "macro_regime.json").write_text(json.dumps({"quadrant": "REFLATION", "quadrant_inputs": {"ok": True},
                                                        "debt_cycle": {"debt_cycle_phase": "DISCIPLINE"}}), encoding="utf-8")
    for s, mode in (("FULL1", "full"), ("DELTA1", "delta"), ("DELTA2", "delta")):
        (root / "inputs" / f"{s}.json").write_text(json.dumps({"symbol": s, "methodologies": [],
                                                               "debate_run": TODAY, "transcript_date": ""}), encoding="utf-8")
        (root / "results_regime" / f"{s}.json").write_text(json.dumps(
            {"symbol": s, "update_mode": mode, "last_full_debate": TODAY if mode == "full" else "2026-08-24",
             "valuation": {"live_price": 50.0}}), encoding="utf-8")
    (root / "_archive_prev" / "results_regime" / "DELTA1.json").write_text(json.dumps(
        {"full_debate_px": 17.2, "full_debate_px_date": "2026-08-24",
         "macro_at_full_debate": {"quadrant": "GOLDILOCKS", "phase": "DISCIPLINE"}}), encoding="utf-8")
    saved = (W.ROOT, W.INP, W.RES, W._hist_close)
    W.ROOT, W.INP, W.RES = root, root / "inputs", root / "results_regime"
    W._hist_close = lambda s, dt: 17.2 if (s, dt) == ("DELTA2", "2026-08-24") else None
    try:
        W.lane_stamp()
    finally:
        W.ROOT, W.INP, W.RES, W._hist_close = saved
    f1 = json.load(open(root / "results_regime" / "FULL1.json"))
    d1 = json.load(open(root / "results_regime" / "DELTA1.json"))
    d2 = json.load(open(root / "results_regime" / "DELTA2.json"))
    check("lane-stamp: a full debate stamps its price + the live macro read",
          f1.get("full_debate_px") == 50.0 and f1.get("macro_at_full_debate", {}).get("quadrant") == "REFLATION", f1)
    check("lane-stamp: a delta keeps its anchor's stamps (not today's price or macro)",
          d1.get("full_debate_px") == 17.2 and d1.get("macro_at_full_debate", {}).get("quadrant") == "GOLDILOCKS", d1)
    check("lane-stamp: a pre-stamp delta is backfilled once from the full-debate close",
          d2.get("full_debate_px") == 17.2 and "closing price" in str(d2.get("full_debate_px_source")), d2)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
