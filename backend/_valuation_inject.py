#!/usr/bin/env python3
"""Fold a _valuation_workflow.js output into the _valuation.json sidecar (accumulating,
so partial runs merge). _enrich_board.py reads _valuation.json; _post_board.py computes R:R.
Usage: python _valuation_inject.py <workflow_output.json>"""
import json, sys, os
BASE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(BASE, "_valuation.json")

out = json.load(open(sys.argv[1], encoding="utf-8"))
res = out.get("result", out)
rows = res.get("results", res if isinstance(res, list) else [])
val = json.load(open(F, encoding="utf-8")) if os.path.exists(F) else {}
added = 0
for r in rows:
    if r and r.get("symbol") and r.get("valuation_method"):
        val[str(r["symbol"]).upper()] = r
        added += 1
json.dump(val, open(F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"VALUATION sidecar: +{added} of {len(rows)} -> {len(val)} names total in _valuation.json")
