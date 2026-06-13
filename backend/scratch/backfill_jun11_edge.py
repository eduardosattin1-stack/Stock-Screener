#!/usr/bin/env python3
"""Backfill vol-adjusted edge for the 2026-06-11 cohort.

Source: scratch/_vol_edge_jun11_v2.json (edge = live p_model - mean(p_model|vol),
computed from Jun-11 archive probs + ThetaData-recomputed Jun-11 f_vol_60d against
the calibration-free model-pred vol baseline).

Regime-aware: p10_30 record["edge"] <- edge_p10_30, p20_60 <- edge_p20_60.
Summary records get edge_30d / edge_60d.

DRY_RUN unless APPLY=1. Backs up each blob to <path>.bak-edge-backfill.
"""
import json, os
from google.cloud import storage

DRY_RUN = os.environ.get("APPLY") != "1"
BUCKET, P = "screener-signals-carbonbridge", "calibration_tracking/v2"
REGIME_FIELD = {"p10_30": "edge_p10_30", "p20_60": "edge_p20_60"}

c = storage.Client(); b = c.bucket(BUCKET)
edges = json.load(open("scratch/_vol_edge_jun11_v2.json"))["edges"]
print(f"edge source: {len(edges)} symbols with recomputed Jun-11 edge")
print(f"MODE: {'DRY RUN' if DRY_RUN else 'APPLY (writing + backups)'}\n")


def load(p): return json.loads(b.blob(p).download_as_text())
def load_jsonl(p): return [json.loads(x) for x in b.blob(p).download_as_text().splitlines() if x.strip()]
def write(p, text):
    if DRY_RUN: return
    if b.blob(p).exists(): b.blob(p + ".bak-edge-backfill").rewrite(b.blob(p))
    b.blob(p).upload_from_string(text, content_type="application/json")


def patch(records, field, label):
    n = 0
    for r in records:
        if r.get("edge") is not None: continue
        e = edges.get(r.get("symbol"), {}).get(field)
        if e is not None:
            r["edge"] = e; n += 1
    print(f"  {label:40s} patched={n:4d}")
    return n


total = 0
for regime, field in REGIME_FIELD.items():
    for sub, loader, fmt in [("entries/2026-06.jsonl", load_jsonl, "jsonl"),
                             ("open_state.json", load, "json"),
                             ("resolved/2026-06.jsonl", load_jsonl, "jsonl")]:
        path = f"{P}/{regime}/{sub}"
        if not b.blob(path).exists(): continue
        if fmt == "jsonl":
            recs = loader(path); total += patch(recs, field, f"{regime}/{sub} ({len(recs)})")
            write(path, "\n".join(json.dumps(r) for r in recs) + "\n")
        else:
            doc = loader(path); total += patch(doc.get("records", []), field, f"{regime}/{sub} ({len(doc.get('records', []))})")
            write(path, json.dumps(doc))

# summary
sp = f"{P}/summary.json"; summ = load(sp); n = 0
for r in summ.get("records", []):
    sym = r.get("symbol")
    if r.get("edge_30d") is None and edges.get(sym, {}).get("edge_p10_30") is not None:
        r["edge_30d"] = edges[sym]["edge_p10_30"]; n += 1
    if r.get("edge_60d") is None and edges.get(sym, {}).get("edge_p20_60") is not None:
        r["edge_60d"] = edges[sym]["edge_p20_60"]
print(f"  {'summary.json records[]':40s} patched={n:4d}")
total += n
write(sp, json.dumps(summ))

# how many will badge (strict: edge>=.10 & decile>=8)
badge = 0
dec = {}
for regime in REGIME_FIELD:
    st = load(f"{P}/{regime}/open_state.json")
    dec[regime] = {r["symbol"]: r.get("decile") for r in st["records"]}
for sym, e in edges.items():
    e30 = e.get("edge_p10_30"); e60 = e.get("edge_p20_60")
    if (e30 is not None and e30 >= 0.10 and (dec["p10_30"].get(sym) or 0) >= 8) or \
       (e60 is not None and e60 >= 0.10 and (dec["p20_60"].get(sym) or 0) >= 8):
        badge += 1
print(f"\nTOTAL patched: {total}   stocks that will show BEATS VOL badge: {badge}")
print("DRY RUN — re-run with APPLY=1." if DRY_RUN else "APPLIED. Backups at <path>.bak-edge-backfill")
