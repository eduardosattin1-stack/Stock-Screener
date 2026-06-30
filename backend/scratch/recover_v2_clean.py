#!/usr/bin/env python3
"""CLEAN single-pass calibration recovery (supersedes the messy multi-pass attempt).

Restores calibration_tracking/v2 from the verified clean backup, then does the
recovery in ONE update_from_scan on the FMP-migrated + .bak-hardened tracker:
  0. RESTORE v2 from _bak_2026-06-30_fmp_recovery (clean frozen-Jun18 state),
     skipping stale .bak-* siblings so v2/ stays clean.
  B. clear the outage DROPPED rows (scan_date in the Jun19..26 outage window).
  C. re-stage the dropped cohorts from the scan archives (correct open-symbol dedup).
  D. ONE update_from_scan(latest_global, today): activate re-staged + Jun29 pendings,
     mark ALL open records forward Jun19->today, stage today.
Then VERIFY inline (accounting, last_bar_date, headline==nondropped, no dup record_ids).

Requires the two code fixes in calibration_tracker.py:
  - _fetch_bars_pooled no longer bails on `theta is None` (FMP path), and
  - _load_resolved_records / _load_entry_scan_dates skip non-.jsonl (.bak) siblings.

DRY unless APPLY=1.
"""
import json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FMP_API_KEY", "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA")
from google.cloud import storage
import calibration_tracker as ct

DRY = os.environ.get("APPLY") != "1"
TODAY = "2026-06-30"
OUTAGE = ["2026-06-19", "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"]
P = "calibration_tracking/v2"
BAK = "calibration_tracking/_bak_2026-06-30_fmp_recovery"
c = storage.Client(); b = c.bucket("screener-signals-carbonbridge")
load = lambda p: json.loads(b.blob(p).download_as_text())
def jl(p):
    bl = b.blob(p)
    return [json.loads(x) for x in bl.download_as_text().splitlines() if x.strip()] if bl.exists() else []

print(f"MODE: {'DRY RUN' if DRY else 'APPLY'}\n")

# --- 0. RESTORE v2 from the verified clean backup (skip stale .bak siblings) ---
restored = 0
if not DRY:
    for blob in c.list_blobs("screener-signals-carbonbridge", prefix=f"{BAK}/"):
        rel = blob.name[len(BAK) + 1:]
        if ".bak" in rel:
            continue  # do not restore stale .bak-* siblings into v2/
        b.copy_blob(blob, b, f"{P}/{rel}")
        restored += 1
    print(f"0. RESTORE: copied {restored} clean blobs {BAK}/ -> {P}/")
    # sanity: restored frozen state
    for rg in ["p10_30", "p20_60"]:
        op = load(f"{P}/{rg}/open_state.json").get("records", [])
        res = jl(f"{P}/{rg}/resolved/2026-06.jsonl")
        lbd = Counter(r.get("last_bar_date") for r in op)
        print(f"   {rg}: open={len(op)} last_bar_date={dict(lbd)} resolved={len(res)} "
              f"(touch={sum(1 for r in res if r.get('resolution')=='TOUCH')} "
              f"dropped={sum(1 for r in res if r.get('status')=='DROPPED')})")
else:
    print("0. RESTORE: (dry) would copy clean blobs from backup")

config = load(f"{P}/config.json")

# --- B. clear outage DROPPED rows ---
for rg in ["p10_30", "p20_60"]:
    rp = f"{P}/{rg}/resolved/2026-06.jsonl"
    res = jl(rp)
    keep = [r for r in res if not (r.get("status") == "DROPPED" and r.get("scan_date") in OUTAGE)]
    print(f"B {rg}: resolved {len(res)} -> {len(keep)} (removed {len(res)-len(keep)} outage DROPPED)")
    if not DRY:
        b.blob(rp).upload_from_string("\n".join(json.dumps(r) for r in keep) + "\n",
                                      content_type="application/json")

# --- C. re-stage dropped cohorts from archives ---
pdoc = load(f"{P}/pending_entries.json"); pending = pdoc.get("pending", [])
open_syms = {rg: {r["symbol"] for r in load(f"{P}/{rg}/open_state.json").get("records", [])}
             for rg in ["p10_30", "p20_60"]}
restaged = {rg: 0 for rg in ["p10_30", "p20_60"]}
for D in OUTAGE:
    stocks = load(f"scans/{D}_global.json").get("stocks", [])
    for rg, cfg in ct.REGIMES.items():
        restaged[rg] += ct._stage_pending_entries(stocks, D, cfg, config, pending, open_syms[rg])
print(f"C: re-staged p10_30 +{restaged['p10_30']}, p20_60 +{restaged['p20_60']}; pending now {len(pending)}")
if not DRY:
    pdoc["pending"] = pending
    b.blob(f"{P}/pending_entries.json").upload_from_string(json.dumps(pdoc), content_type="application/json")

# --- D. ONE catch-up run on FMP ---
if DRY:
    print(f"\nD: (dry) would run update_from_scan(latest_global, {TODAY}); re-run APPLY=1")
    sys.exit(0)
print(f"\nD: update_from_scan(latest_global, {TODAY}) on FMP ...")
ct._fetch_impl = None
counters = ct.update_from_scan(load("scans/latest_global.json").get("stocks", []), scan_date=TODAY)
print("D: counters:", json.dumps(counters))

# --- VERIFY ---
print("\n=== VERIFY ===")
s = load(f"{P}/summary.json")
print("summary as_of:", s.get("as_of"))
ok = True
for name, cfg in ct.REGIMES.items():
    op = load(f"{P}/{name}/open_state.json").get("records", [])
    ent = jl(f"{P}/{name}/entries/2026-06.jsonl")
    resolved = ct._load_resolved_records(cfg)
    nd = op + [r for r in resolved if r.get("status") != "DROPPED"]
    ndt = sum(1 for r in nd if r.get("resolution") == "TOUCH")
    nondrop = [r for r in resolved if r.get("status") != "DROPPED"]
    rid = Counter(r.get("record_id") for r in jl(f"{P}/{name}/resolved/2026-06.jsonl"))
    dups = sum(1 for v in rid.values() if v > 1)
    acct = len(ent) == len(op) + len(nondrop)
    lbd = Counter(r.get("last_bar_date") for r in op)
    h = cfg.horizon_label
    hl = s["horizons"][h]["headline"]; he = s["horizons"][h]["health"]
    headline_ok = hl["observed_touches_to_date"] == ndt
    print(f"{name}: open={len(op)} last_bar_date={dict(lbd)}")
    print(f"   entries={len(ent)} == open({len(op)})+nondropped({len(nondrop)}) -> {'OK' if acct else 'MISMATCH'}")
    print(f"   nondropped_touch={ndt}  headline_observed={hl['observed_touches_to_date']} -> {'OK' if headline_ok else 'MISMATCH'}")
    print(f"   dup_record_ids={dups} -> {'OK' if dups==0 else 'BAD'}")
    print(f"   headline: obs={hl['observed_touches_to_date']} exp={round(hl['expected_touches_to_date'],1)} "
          f"z={round(hl['z'],2) if hl['z'] is not None else None} status={he['status']} ks={he['kill_switch_active']}")
    ok = ok and acct and headline_ok and dups == 0
print("\nALL CONSISTENT" if ok else "\n*** INCONSISTENCY — investigate ***")
