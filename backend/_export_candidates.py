#!/usr/bin/env python3
"""Export ALL catalyst-watch candidates (manual + widen + sweep, deduped) to
JSON (full detail-page reports) + CSV (flattened). Pulls the exact
CatalystScanReport the detail page renders, via the local Next API.
Usage: python _export_candidates.py   (dev server must be running on :3000)"""
import json, csv, os, sys
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
HOST = "http://localhost:3000"
# RAW intermediate (the pre-enrichment merge). _enrich_board reads these and writes the
# real deliverable catalyst_candidates_231.{json,csv}. Separate files = no read-own-output cycle.
JSON_OUT = os.path.join(BASE, "_catalyst_raw.json")
CSV_OUT = os.path.join(BASE, "_catalyst_raw.csv")

# source tagging
def load_syms(path):
    try:
        import re
        t = open(path, encoding="utf-8").read()
        return set(re.findall(r'symbol:\s*["\']([A-Z0-9.\-]+)["\']', t))
    except FileNotFoundError:
        return set()

sweep_syms = {b["symbol"].upper() for b in json.load(open(os.path.join(BASE, "_sweep_board.json"), encoding="utf-8"))}
widen_syms = load_syms(os.path.join(ROOT, "frontend/app/data/catalystBoardWiden.ts"))

def source_of(sym):
    s = sym.upper()
    if s in sweep_syms: return "sweep"
    if s in widen_syms: return "widen"
    return "manual"

def g(d, *path, default=""):
    cur = d
    for p in path:
        if isinstance(cur, dict): cur = cur.get(p)
        else: return default
    return cur if cur is not None else default

cand = requests.get(f"{HOST}/api/catalysts/candidates", params={"raw": 1}, timeout=30).json()
syms = [c["symbol"] for c in cand if c.get("symbol")]
print(f"{len(syms)} candidates; fetching reports...")

reports, rows, fails = [], [], []
for i, sym in enumerate(syms):
    try:
        r = requests.get(f"{HOST}/api/catalysts/scan", params={"symbol": sym, "raw": 1}, timeout=30)
        d = r.json()
        if not d or d.get("error"):
            fails.append(sym); continue
    except Exception as e:
        fails.append(f"{sym}:{e}"); continue
    d["_source"] = source_of(sym)
    reports.append(d)
    opt = d.get("options_signals") or {}
    rows.append({
        "symbol": d.get("symbol", sym),
        "company_name": d.get("company_name", ""),
        "source": d["_source"],
        "tier": d.get("tier", ""),
        "lane": d.get("lane", ""),
        "recommendation": d.get("recommendation", ""),
        "catalyst_density_score": d.get("catalyst_density_score", ""),
        "adjusted_loeb_score": d.get("adjusted_loeb_score", ""),
        "rr_ratio": d.get("upside_downside_ratio", ""),
        "price": d.get("price", ""),
        "market_cap": d.get("market_cap", ""),
        "catalyst_nature": d.get("catalyst_nature", ""),
        "re_rate_status": d.get("re_rate_status", ""),
        "edge": d.get("edge", ""),
        "instrument": d.get("instrument", ""),
        "verdict": d.get("verify_verdict", "") or d.get("verdict", ""),
        "thesis_summary": d.get("analysis_summary", ""),
        "catalyst_title": g(d, "bloom_catalysts", "catalyst_1", "title"),
        "catalyst_desc": g(d, "bloom_catalysts", "catalyst_1", "description"),
        "catalyst_evidence": g(d, "bloom_catalysts", "catalyst_1", "evidence"),
        "milestone_desc": g(d, "bloom_catalysts", "catalyst_2", "description"),
        "verify_desc": g(d, "bloom_catalysts", "catalyst_3", "description"),
        "verify_evidence": g(d, "bloom_catalysts", "catalyst_3", "evidence"),
        "loeb_catalyst_density": g(d, "loeb_criteria", "catalyst_density", "analysis"),
        "loeb_sum_of_parts": g(d, "loeb_criteria", "sum_of_parts", "analysis"),
        "loeb_activism": g(d, "loeb_criteria", "activism_potential", "analysis"),
        "loeb_risk_reward": g(d, "loeb_criteria", "risk_reward", "analysis"),
        "opt_iv_current": opt.get("iv_current", ""),
        "opt_pc_ratio": opt.get("pc_oi_ratio", ""),
        "opt_skew_25d": opt.get("skew_25d", ""),
        "opt_term_structure": opt.get("term_structure", ""),
        "opt_total_oi": opt.get("total_oi", ""),
        "opt_implied_move_pct": opt.get("implied_earnings_move_pct", ""),
        "opt_sentiment_flag": opt.get("market_sentiment_flag", ""),
        "opt_interpretation": opt.get("overall_interpretation", ""),
        "primary_source": g(d, "recent_events", 0, "link") if isinstance(d.get("recent_events"), list) and d.get("recent_events") else "",
        "cache_timestamp": d.get("cache_timestamp", ""),
    })
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/{len(syms)}")

json.dump({"count": len(reports), "generated": "2026-06-08", "candidates": reports},
          open(JSON_OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
with open(CSV_OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

bys = {}
for d in reports: bys[d["_source"]] = bys.get(d["_source"], 0) + 1
with_opt = sum(1 for d in reports if (d.get("options_signals") or {}).get("iv_current") is not None)
print(f"\nEXPORTED {len(reports)} candidates  (by source: {bys})")
print(f"  with live options IV: {with_opt}")
if fails: print(f"  FAILED ({len(fails)}): {fails[:20]}")
print(f"JSON -> {JSON_OUT}")
print(f"CSV  -> {CSV_OUT}")
