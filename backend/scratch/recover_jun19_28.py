#!/usr/bin/env python3
"""Recover the calibration cohorts dropped during the 2026-06-19..30 ThetaData outage,
and catch up the frozen open records — all on the FMP-migrated tracker.

Outage: ThetaData 401 from ~Jun 19 -> activation/marking failed -> open records frozen
at last_bar_date 2026-06-18, and the Jun 19/22/23/24/25/26 cohorts were DROPPED_NO_BAR
after 3 attempts. The Jun-11 IAC straggler is a legit pre-outage drop (kept).

Recovery (FMP, no ThetaData):
  A. back up every calibration_tracking/v2 blob touched.
  B. remove the outage DROPPED rows from resolved/2026-06.jsonl (both regimes).
  C. re-stage the dropped cohorts from the scan archives (full iv/dd/edge data) via the
     tracker's own _stage_pending_entries (applies the correct open-symbol dedup).
  D. one update_from_scan(latest_global, scan_date=today): activates the re-staged
     cohorts + the Jun-29 pending at their scan-date EOD close (FMP), marks ALL open
     records forward to today, stages today's cohort.

DRY_RUN unless APPLY=1.
"""
import json, os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FMP_API_KEY", "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA")
from google.cloud import storage
import calibration_tracker as ct

DRY = os.environ.get("APPLY") != "1"
TODAY = "2026-06-30"
OUTAGE_SCAN_DATES = ["2026-06-19", "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"]
P = "calibration_tracking/v2"
c = storage.Client(); b = c.bucket("screener-signals-carbonbridge")
load = lambda p: json.loads(b.blob(p).download_as_text())
def load_jsonl(p): return [json.loads(x) for x in b.blob(p).download_as_text().splitlines() if x.strip()] if b.blob(p).exists() else []
def write_text(p, t):
    if DRY: return
    if b.blob(p).exists(): b.blob(p + ".bak-fmp-recovery").rewrite(b.blob(p))
    b.blob(p).upload_from_string(t, content_type="application/json")

print(f"MODE: {'DRY RUN (no writes)' if DRY else 'APPLY (writing + backups)'}\n")

# --- full-prefix backup (covers everything update_from_scan rewrites in step D) ---
BAK = "calibration_tracking/_bak_2026-06-30_fmp_recovery"
if not DRY:
    n = 0
    for blob in c.list_blobs("screener-signals-carbonbridge", prefix=f"{P}/"):
        b.copy_blob(blob, b, blob.name.replace(P, BAK, 1)); n += 1
    print(f"BACKUP: copied {n} blobs -> {BAK}/\n")

config = load(f"{P}/config.json")

# --- B. clear outage DROPPED rows from resolved (keep TOUCH/TERMINAL + Jun-11 IAC drop) ---
for rg in ["p10_30", "p20_60"]:
    rp = f"{P}/{rg}/resolved/2026-06.jsonl"
    res = load_jsonl(rp)
    keep = [r for r in res if not (r.get("status") == "DROPPED" and r.get("scan_date") in OUTAGE_SCAN_DATES)]
    removed = len(res) - len(keep)
    print(f"B {rg}: resolved {len(res)} -> {len(keep)} (removed {removed} outage DROPPED rows)")
    write_text(rp, "\n".join(json.dumps(r) for r in keep) + "\n")

# --- C. re-stage the dropped cohorts from archives (full data, correct dedup) ---
pdoc = load(f"{P}/pending_entries.json")
pending = pdoc.get("pending", [])
print(f"\nC: current pending {len(pending)} (scan_dates {sorted(set(p['scan_date'] for p in pending))})")
open_syms = {rg: {r["symbol"] for r in load(f"{P}/{rg}/open_state.json").get('records', [])} for rg in ["p10_30", "p20_60"]}
restaged = {rg: 0 for rg in ["p10_30", "p20_60"]}
for D in OUTAGE_SCAN_DATES:
    arch = load(f"scans/{D}_global.json")
    stocks = arch.get("stocks", [])
    for rg, cfg in ct.REGIMES.items():
        n = ct._stage_pending_entries(stocks, D, cfg, config, pending, open_syms[rg])
        restaged[rg] += n
print(f"C: re-staged from archives -> p10_30 +{restaged['p10_30']}, p20_60 +{restaged['p20_60']}; pending now {len(pending)}")
pdoc["pending"] = pending
write_text(f"{P}/pending_entries.json", json.dumps(pdoc))

# --- D. one catch-up run on FMP: activate re-staged + Jun-29, mark all forward, stage today ---
if DRY:
    print(f"\nD: DRY RUN — would run update_from_scan(latest_global, scan_date={TODAY})")
    print("Re-run with APPLY=1.")
else:
    print(f"\nD: running update_from_scan(latest_global, scan_date={TODAY}) on FMP ...")
    lg = load("scans/latest_global.json")
    counters = ct.update_from_scan(lg.get("stocks", []), scan_date=TODAY)
    print("D: counters:", json.dumps(counters))
    print("APPLIED. Backups at <blob>.bak-fmp-recovery")
