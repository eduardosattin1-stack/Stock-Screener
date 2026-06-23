#!/usr/bin/env python3
"""Backfill dd_pred (predicted max drawdown) for the 2026-06-11 cohort.

Same idea as backfill_jun11_iv.py: the Jun-11 cohort was staged before the
predicted-drawdown wiring, so dd_pred is null. The Jun-11 scan archive carries
expected_dd_30d / expected_dd_60d — the model's entry-time forecast.

Regime-aware: p10_30 records get expected_dd_30d, p20_60 get expected_dd_60d.
Summary records get dd_pred_30d (from p10_30) and dd_pred_60d (from p20_60).

DRY_RUN unless APPLY=1. Backs up each blob to <path>.bak-dd-backfill.
"""
import json
import os

from google.cloud import storage

DRY_RUN = os.environ.get("APPLY") != "1"
BUCKET = "screener-signals-carbonbridge"
P = "calibration_tracking/v2"
ARCHIVE = "scans/2026-06-11_global.json"
# regime -> archive field
REGIME_DD = {"p10_30": "expected_dd_30d", "p20_60": "expected_dd_60d"}

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
        b.blob(path + ".bak-dd-backfill").rewrite(blob)
    b.blob(path).upload_from_string(text, content_type="application/json")


# sym -> {expected_dd_30d, expected_dd_60d} (nonzero only; 0.0 = no prediction)
arch = load(ARCHIVE)
dd = {}
for s in arch.get("stocks", []):
    sym = s.get("symbol")
    if not sym:
        continue
    d30, d60 = s.get("expected_dd_30d"), s.get("expected_dd_60d")
    dd[sym] = (round(float(d30), 2) if d30 else None,
               round(float(d60), 2) if d60 else None)
print(f"Jun-11 archive: {sum(1 for v in dd.values() if v[0] is not None)} symbols carry expected_dd_30d")
print(f"MODE: {'DRY RUN (no writes)' if DRY_RUN else 'APPLY (writing + backups)'}\n")


def patch_regime_records(records, field_idx, label):
    n = 0
    for r in records:
        sym = r.get("symbol")
        if r.get("dd_pred") is not None:
            continue
        v = dd.get(sym, (None, None))[field_idx]
        if v is not None:
            r["dd_pred"] = v
            n += 1
    print(f"  {label:42s} patched={n:4d}")
    return n


total = 0
for regime, field in REGIME_DD.items():
    idx = 0 if field == "expected_dd_30d" else 1
    ep = f"{P}/{regime}/entries/2026-06.jsonl"
    entries = load_jsonl(ep)
    total += patch_regime_records(entries, idx, f"{regime}/entries ({len(entries)})")
    backup_and_write_text(ep, "\n".join(json.dumps(r) for r in entries) + "\n")

    op = f"{P}/{regime}/open_state.json"
    ost = load(op)
    total += patch_regime_records(ost.get("records", []), idx, f"{regime}/open_state ({len(ost.get('records', []))})")
    backup_and_write_text(op, json.dumps(ost))

    rp = f"{P}/{regime}/resolved/2026-06.jsonl"
    if b.blob(rp).exists():
        res = load_jsonl(rp)
        total += patch_regime_records(res, idx, f"{regime}/resolved ({len(res)})")
        backup_and_write_text(rp, "\n".join(json.dumps(r) for r in res) + "\n")

# summary.json records[] — set both horizons by symbol
sp = f"{P}/summary.json"
summ = load(sp)
n = 0
for r in summ.get("records", []):
    sym = r.get("symbol")
    d30, d60 = dd.get(sym, (None, None))
    if r.get("dd_pred_30d") is None and d30 is not None:
        r["dd_pred_30d"] = d30; n += 1
    if r.get("dd_pred_60d") is None and d60 is not None:
        r["dd_pred_60d"] = d60
print(f"  {'summary.json records[]':42s} patched={n:4d} (dd_pred_30d; dd_pred_60d set in tandem)")
total += n
backup_and_write_text(sp, json.dumps(summ))

print(f"\nTOTAL regime/summary records patched: {total}")
print("DRY RUN — re-run with APPLY=1." if DRY_RUN else "APPLIED. Backups at <path>.bak-dd-backfill")
