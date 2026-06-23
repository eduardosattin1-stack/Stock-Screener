#!/usr/bin/env python3
"""seed_debate_history.py — ONE-TIME backfill of the per-symbol debate-history store.

Going forward, publish_to_frontend.py appends each weekly run's debate to
frontend/public/speculair_debate_history/<SYM>.json. This script seeds that store with a
PRIOR archived run (default: backend/_opus_debate/_archive_pre_20260606, the 2026-06-05 pass)
so the stock-page history dropdown has depth on day one. Idempotent: re-running for the same
(symbol, date) replaces that dated entry rather than duplicating it.

Usage:
  python backend/_opus_debate/seed_debate_history.py [ARCHIVE_DIR] [DATE] [--gcs]
    ARCHIVE_DIR  dir holding results_regime/ + dossiers/ (default _archive_pre_20260606)
    DATE         run date to stamp the entries (default 2026-06-05)
    --gcs        also push the per-symbol files to gs://.../scans/speculair_debate_history/
"""
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BK = Path(__file__).resolve().parent
BACKEND = BK.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "alpha_compounder"))
import gcs_io  # noqa: E402

PUB = ROOT / "frontend" / "public"
HIST_DIR = PUB / "speculair_debate_history"
HIST_DIR.mkdir(parents=True, exist_ok=True)

argv = [a for a in sys.argv[1:] if a != "--gcs"]
PUSH = "--gcs" in sys.argv
ARCHIVE = BK / (argv[0] if len(argv) > 0 else "_archive_pre_20260606")
DATE = argv[1] if len(argv) > 1 else "2026-06-05"
RES = ARCHIVE / "results_regime"
DOSS = ARCHIVE / "dossiers"


def load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def dossier_for(sym):
    p = DOSS / f"{sym}.md"
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def entry(rec, dossier, date_str):
    d = dossier or ""
    mm = re.search(r"CREDIBILITY_SCORE:\s*(\d+)", d)
    sc_i = max(1, min(5, int(mm.group(1)))) if mm else int(rec.get("interrogator_score", 0) or 0)
    tj = re.search(r"TRAJECTORY:\s*([A-Z]+)", d)
    return {
        "date": date_str, "timestamp": date_str + "T22:00:00+00:00",
        "verdict": rec.get("verdict", ""), "conviction": int(rec.get("conviction", 0) or 0),
        "trajectory": (tj.group(1) if tj else rec.get("trajectory", "")),
        "interrogator_score": sc_i,
        "transcript_source": rec.get("transcript_source", "fmp"), "source": rec.get("source", ""),
        "bull_thesis": rec.get("bull_thesis", ""), "bear_thesis": rec.get("bear_thesis", ""),
        "consensus_delta": rec.get("consensus_delta", ""), "forcing_function": rec.get("forcing_function", ""),
        "valley_of_death": rec.get("valley_of_death", ""), "positioning_washout": rec.get("positioning_washout", ""),
        "moderator_conclusion": rec.get("moderator_conclusion", ""),
        "interrogator_dossier": d, "engine": "opus-4.8-regime",
    }


if not RES.exists():
    print(f"ERROR: {RES} not found — nothing to seed.")
    sys.exit(1)

n = 0
for f in sorted(RES.glob("*.json")):
    sym = f.stem
    rec = load(f)
    if not rec or not rec.get("bull_thesis"):
        continue
    local = HIST_DIR / f"{sym}.json"
    hist = load(local)
    if not isinstance(hist, list):
        hist = []
    hist = [e for e in hist if isinstance(e, dict) and e.get("date") != DATE]  # replace same-date
    hist.append(entry(rec, dossier_for(sym), DATE))
    hist.sort(key=lambda e: e.get("date", ""))  # chronological, oldest first
    local.write_text(json.dumps(hist, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    n += 1
print(f"seeded {n} per-symbol history files (date {DATE}) -> {HIST_DIR}")

if PUSH:
    try:
        cmd = f'gcloud storage cp -r "{HIST_DIR}" "gs://{gcs_io.GCS_BUCKET}/scans/"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        print(f"GCS push scans/speculair_debate_history/: {'OK' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-200:]}")
    except Exception as e:
        print(f"GCS push history dir: ERROR {e}")
