"""Reliability fixes of 2026-11-12: value-seat monthly refresh, second-opinion trigger, run lock,
fresh-view gate, and a syntax check of the rendered weekly workflow. No network, no GCS, no writes
outside a temp directory.

    python backend/tests/test_reliability_fixes.py
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

BK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BK)); sys.path.insert(0, str(BK / "_opus_debate"))
import _seat_triggers as ST          # noqa: E402
import _post_common as PC            # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name)


# ── value-seat monthly refresh ───────────────────────────────────────────────
check("a value seat fully debated 78 days ago re-debates (the DUE.DE case)",
      "78d ago" in (ST.value_seat_refresh({"last_full_debate": "2026-08-24"}, "2026-11-10") or ""))
check("a value seat fully debated 28 days ago does not re-debate yet",
      ST.value_seat_refresh({"last_full_debate": "2026-10-13"}, "2026-11-10") is None)
check("a value seat fully debated 29 days ago re-debates (the INCH.L / 2618.HK case)",
      ST.value_seat_refresh({"last_full_debate": "2026-10-12"}, "2026-11-10") is not None)
check("a value seat with no full-debate date re-debates",
      ST.value_seat_refresh({}, "2026-11-10") is not None)
check("an unreadable date never forces a debate by itself",
      ST.value_seat_refresh({"last_full_debate": "not-a-date"}, "2026-11-10") is None)

# ── second opinion ───────────────────────────────────────────────────────────
entry = {"status": "repriced", "reasons": ["its value is -18% from ours"],
         "gemini": {"base_fv_px": 782.0}, "claude": {"base_fv_px": 950.0},
         "skeptic_on_ours": {"verdict": "REFUTED", "kill_scope": "numbers", "revised_fv_px": 891.0,
                             "correction_severity": "material", "finding": "segment tables not pulled"}}
blk = ST.second_opinion_block(entry, "2026-W46", "2026-11-11T13:24:32", "gemini-4-argon")
check("the bundle block carries both values and the skeptic's revised number",
      blk and blk["their_base_fv_px"] == 782.0 and blk["our_base_fv_px"] == 950.0
      and blk["skeptic_revised_fv_px"] == 891.0 and blk["generated_at"] == "2026-11-11")
check("a repricing after the last full debate triggers a full re-debate",
      "repriced" in (ST.second_opinion_trigger({"last_full_debate": "2026-10-12"}, blk) or ""))
check("it fires once: no trigger after the seat was fully re-debated since the opinion",
      ST.second_opinion_trigger({"last_full_debate": "2026-11-17"}, blk) is None)
conf = ST.second_opinion_block({"status": "confirmed", "gemini": {}, "claude": {}, "skeptic_on_ours": {}},
                               "2026-W46", "2026-11-11", "gemini-4-argon")
check("a plain confirmation never triggers", ST.second_opinion_trigger({"last_full_debate": "2026-10-12"}, conf) is None)
mat = ST.second_opinion_block({"status": "confirmed", "gemini": {}, "claude": {},
                               "skeptic_on_ours": {"correction_severity": "material", "finding": "x"}},
                              "2026-W46", "2026-11-11", "gemini-4-argon")
check("a confirmation carrying a MATERIAL correction does trigger",
      ST.second_opinion_trigger({"last_full_debate": "2026-10-12"}, mat) is not None)
check("an opinion with no date never triggers",
      ST.second_opinion_trigger({}, ST.second_opinion_block(entry, "2026-W46", None, "m")) is None)
check("no entry -> no block", ST.second_opinion_block(None) is None and ST.second_opinion_block({}) is None)

# ── fresh view ───────────────────────────────────────────────────────────────
T = "2026-11-10"
check("a full debate 8 days old is a fresh view", PC.has_fresh_view({"last_full_debate": "2026-11-02"}, T))
check("a full debate 36 days old is not (the ADBE case)", not PC.has_fresh_view({"last_full_debate": "2026-10-05"}, T))
check("a carried record with no stamp is not a fresh view", not PC.has_fresh_view({"carried": True}, T))
check("an unstamped record debated this run is a fresh view", PC.has_fresh_view({"carried": False}, T))
with tempfile.TemporaryDirectory() as td:
    apx = {"apex_basket": [{"symbol": "HELD", "decision": "KEEP"}, {"symbol": "STALE", "decision": "ADD"},
                           {"symbol": "FRESH", "decision": "ADD"}],
           "runner_ups": [{"symbol": "WANT", "needs_fresh_debate": True}, {"symbol": "OTHER"}],
           "value_memo": "ROTATION\nADDED: STALE, FRESH."}
    rows = {"HELD": {"last_full_debate": "2026-08-24"}, "STALE": {"last_full_debate": "2026-10-05"},
            "FRESH": {"last_full_debate": "2026-11-09"}}
    dem = PC.fresh_view_gate(apx, rows, {"HELD"}, out_dir=td, today=T, memo_keys=("value_memo",))
    seats = [p["symbol"] for p in apx["apex_basket"]]
    req = json.load(open(Path(td) / PC.FRESH_VIEW_REQUESTS, encoding="utf-8"))["requests"]
    check("the stale NEW seat is demoted; the held seat and the fresh add stay", dem == ["STALE"] and seats == ["HELD", "FRESH"])
    check("the demoted name leads the runner-ups", apx["runner_ups"][0]["symbol"] == "STALE")
    check("the memo carries a dated post-layer correction", apx["value_memo"].startswith("[POST-LAYER CORRECTION"))
    check("the demoted name AND the Director-flagged runner-up are queued for a full debate",
          set(req) == {"STALE", "WANT"})
    memo_before = apx["value_memo"]
    PC.fresh_view_gate(apx, rows, {"HELD"}, out_dir=td, today=T, memo_keys=("value_memo",))
    check("re-running the gate does not stamp the memo twice", apx["value_memo"] == memo_before)
    req2 = json.load(open(Path(td) / PC.FRESH_VIEW_REQUESTS, encoding="utf-8"))["requests"]
    check("re-running the gate keeps the demoted name queued", set(req2) == {"STALE", "WANT"})
    apx2 = {"apex_basket": [{"symbol": "HELD", "decision": "KEEP"}], "runner_ups": [], "value_memo": "m"}
    check("a book of held seats is never touched (an old held record is not this gate's business)",
          PC.fresh_view_gate(apx2, rows, {"HELD"}, out_dir=td, today=T) == [] and apx2["value_memo"] == "m")

# ── run lock + rendered workflow (imports the big module once; needs no network) ──
import weekly_opus_refresh as W      # noqa: E402
with tempfile.TemporaryDirectory() as td:
    st, pub = Path(td) / "state.json", Path(td) / "baskets.json"
    now = datetime(2026, 11, 10, 10, 9)
    st.write_text(json.dumps({"started_at": (now - timedelta(hours=12)).isoformat(), "pid": 1}), encoding="utf-8")
    check("a run that started 12h ago and has not published blocks a second prep (the 11-10 collision)",
          "has not published" in (W._run_in_flight(now, st, pub) or ""))
    pub.write_text("{}", encoding="utf-8")
    os.utime(pub, ((now - timedelta(hours=1)).timestamp(),) * 2)
    check("the same run, once it has published, no longer blocks", W._run_in_flight(now, st, pub) is None)
    os.utime(pub, ((now - timedelta(hours=20)).timestamp(),) * 2)
    check("a publish older than the run's start does not count as that run publishing",
          W._run_in_flight(now, st, pub) is not None)
    st.write_text(json.dumps({"started_at": (now - timedelta(hours=30)).isoformat(), "pid": 1}), encoding="utf-8")
    check("a run older than the lock window is treated as dead", W._run_in_flight(now, st, pub) is None)
    check("no state file -> nothing to protect", W._run_in_flight(now, Path(td) / "missing.json", pub) is None)
    js = (W._WORKFLOW_TEMPLATE
          .replace("__SYMS__", '["AAA"]').replace("__ONLINE_SYMS__", "[]").replace("__RECHECK_SYMS__", "[]")
          .replace("__RECHECK_INFO__", "{}").replace("__DELTA_SYMS__", '["BBB"]').replace("__COVERAGE_SYMS__", "[]")
          .replace("__SKEPTIC_SYMS__", "[]").replace("__SKEPTIC_LANES__", "{}").replace("__SKEPTIC_HINTS__", "{}")
          .replace("__PRIOR_SEATS__", "[]").replace("__DIRECTOR_MODEL__", W.DIRECTOR_MODEL)
          .replace("__SKEPTIC_MODEL__", W.SKEPTIC_MODEL).replace("__N_RADAR__", "1"))
    f = Path(td) / "wf.js"          # .js, as prep writes it: the harness wraps the script, so top-level return is legal
    f.write_text(js, encoding="utf-8", newline="\n")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, shell=(os.name == "nt"))
    check("the rendered weekly workflow is valid JavaScript (" + (r.stderr.strip()[:120] or "ok") + ")", r.returncode == 0)
    check("the workflow prompt carries the second-opinion step", "1d. SECOND OPINION" in js)
    check("the rendered workflow is pure ASCII (the Workflow validator rejects anything else)",
          all(ord(c) < 128 for c in js))
check("the value Director prompt ranks by the fair-value gap and carries the freshness rule",
      "RANK CANDIDATES BY `sop_mos_pct`" in W.VALUE_DIRECTOR_PROMPT and "NEW-SEAT FRESHNESS" in W.VALUE_DIRECTOR_PROMPT)

# ── TreasuryDirect schema drift (auction feed dead from 2026-07-27 to 2026-11-12) ──
import logging                        # noqa: E402
logging.disable(logging.CRITICAL)
import debt_cycle as DC               # noqa: E402
new_schema = [{"originalSecurityTerm": "10-Year", "securityTerm": "9-Year 11-Month",
               "competitiveAuctionCloseDate": "2026-07-08T00:00:00", "bidToCoverRatio": "2.59",
               "indirectBiddersCompetitiveParAwarded": "7367", "grandTotalParAwarded": "10000"},
              {"originalSecurityTerm": "30-Year", "securityTerm": "30-Year",
               "competitiveAuctionCloseDate": "2026-07-09T00:00:00", "bidToCoverRatio": "2.44",
               "indirectBiddersCompetitiveParAwarded": "7026", "grandTotalParAwarded": "10000"},
              {"originalSecurityTerm": "2-Year", "securityTerm": "2-Year",
               "competitiveAuctionCloseDate": "2026-07-09T00:00:00", "bidToCoverRatio": "2.6"}]
old_schema = [{"originalSecurityTerm": "10-Year", "securityTerm": "10-Year", "auctionDate": "2026-05-12",
               "bidToCoverRatio": "2.55", "indirectBidderAccepted": "26520000000", "totalAccepted": "39000000000"}]
rn, ro = DC._parse_auction_rows(new_schema), DC._parse_auction_rows(old_schema)
check("the auction parser reads TreasuryDirect's renamed fields (two rows, dated, with the indirect share)",
      len(rn) == 2 and rn[0]["date"] == "2026-07-08" and abs(rn[0]["indirect_pct"] - 0.7367) < 1e-9
      and rn[0]["reopening"] is True and rn[1]["term"] == "30y")
check("the auction parser still reads the old field names",
      len(ro) == 1 and ro[0]["date"] == "2026-05-12" and abs(ro[0]["indirect_pct"] - 0.68) < 1e-9)

print(f"\n{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
