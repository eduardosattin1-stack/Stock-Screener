#!/usr/bin/env python3
"""Backfill iv_entry/ivr_entry for the 2026-06-11 calibration cohort.

The Jun-11 cohort was staged before the IV-capture field-name fix, so every
record has null iv_entry/ivr_entry. The scan archive that staged them
(scans/2026-06-11_global.json, scan_date 2026-06-11) carries entry-date
options_iv_current / options_iv_rank — the faithful "IV at entry" value.

This patches, per regime (p10_30, p20_60), the durable stores AND the served
summary, keyed by symbol:
  entries/2026-06.jsonl, open_state.json, resolved/2026-06.jsonl, summary.json

DRY_RUN=True only reports. Set DRY_RUN=False to write (backs up each blob to
<path>.bak-iv-backfill first).
"""
import json
import os

from google.cloud import storage

DRY_RUN = os.environ.get("APPLY") != "1"
BUCKET = "screener-signals-carbonbridge"
P = "calibration_tracking/v2"
ARCHIVE = "scans/2026-06-11_global.json"
REGIMES = ["p10_30", "p20_60"]

c = storage.Client()
b = c.bucket(BUCKET)


def load(path):
    return json.loads(b.blob(path).download_as_text())


def load_jsonl(path):
    txt = b.blob(path).download_as_text()
    return [json.loads(ln) for ln in txt.splitlines() if ln.strip()]


def backup_and_write_text(path, text):
    if DRY_RUN:
        return
    blob = b.blob(path)
    if blob.exists():
        bak = b.blob(path + ".bak-iv-backfill")
        bak.rewrite(blob)  # server-side copy of current content
    b.blob(path).upload_from_string(text, content_type="application/json")


# 1. Build sym -> (iv, ivr) from the Jun-11 staging archive (non-null only)
arch = load(ARCHIVE)
iv_map = {}
for s in arch.get("stocks", []):
    sym = s.get("symbol")
    iv = s.get("options_iv_current")
    ivr = s.get("options_iv_rank")
    if sym and iv is not None:
        iv_map[sym] = (round(float(iv), 4),
                       round(float(ivr), 1) if ivr is not None else None)
print(f"Jun-11 archive: {len(iv_map)} symbols carry options_iv_current  (scan_date {arch.get('scan_date')})")
print(f"MODE: {'DRY RUN (no writes)' if DRY_RUN else 'APPLY (writing + backups)'}\n")


def patch_records(records, label):
    """Set iv_entry/ivr_entry on records that have a symbol in iv_map and are
    currently null. Returns (n_patched, n_already, n_no_iv)."""
    n_patched = n_already = n_no_iv = 0
    for r in records:
        sym = r.get("symbol")
        if r.get("iv_entry") is not None:
            n_already += 1
            continue
        if sym in iv_map:
            r["iv_entry"], r["ivr_entry"] = iv_map[sym]
            n_patched += 1
        else:
            n_no_iv += 1
    print(f"  {label:42s} patched={n_patched:4d}  already={n_already:4d}  no-iv-in-archive={n_no_iv}")
    return n_patched


total = 0
for regime in REGIMES:
    # entries jsonl
    ep = f"{P}/{regime}/entries/2026-06.jsonl"
    entries = load_jsonl(ep)
    total += patch_records(entries, f"{regime}/entries/2026-06.jsonl ({len(entries)})")
    backup_and_write_text(ep, "\n".join(json.dumps(r) for r in entries) + "\n")

    # open_state
    op = f"{P}/{regime}/open_state.json"
    ost = load(op)
    total += patch_records(ost.get("records", []), f"{regime}/open_state.json ({len(ost.get('records', []))})")
    backup_and_write_text(op, json.dumps(ost))

    # resolved jsonl (may not exist)
    rp = f"{P}/{regime}/resolved/2026-06.jsonl"
    if b.blob(rp).exists():
        res = load_jsonl(rp)
        total += patch_records(res, f"{regime}/resolved/2026-06.jsonl ({len(res)})")
        backup_and_write_text(rp, "\n".join(json.dumps(r) for r in res) + "\n")

# summary.json records[] (what the UI reads)
sp = f"{P}/summary.json"
summ = load(sp)
total += patch_records(summ.get("records", []), f"summary.json records[] ({len(summ.get('records', []))})")
backup_and_write_text(sp, json.dumps(summ))

print(f"\nTOTAL records patched: {total}")
if DRY_RUN:
    print("DRY RUN — nothing written. Re-run with APPLY=1 to write (backs up each blob first).")
else:
    print("APPLIED. Backups at <path>.bak-iv-backfill")
