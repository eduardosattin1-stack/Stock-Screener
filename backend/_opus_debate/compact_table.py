#!/usr/bin/env python3
"""Print a compact, conviction-sorted table of every Opus debate result for the Director."""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

root = Path(__file__).resolve().parent / (sys.argv[1] if len(sys.argv) > 1 else "results")
rows = []
for f in sorted(root.glob("*.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    rows.append((
        d.get("conviction", 0) or 0,
        d.get("symbol", f.stem),
        d.get("sector", ""),
        d.get("verdict", ""),
        (d.get("forcing_function") or "").replace("\n", " ")[:200],
        (d.get("consensus_delta") or "").replace("\n", " ")[:260],
        d.get("source", ""),
    ))
rows.sort(key=lambda r: (-r[0], r[1] or ""))
elig = sum(1 for r in rows if r[0] >= 3)
print(f"{len(rows)} debated records | eligible (conviction>=3): {elig}")
print("CONV | SYM | SECTOR | VERDICT | FORCING_FUNCTION | CONSENSUS_DELTA | SOURCE")
for r in rows:
    print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]}")
