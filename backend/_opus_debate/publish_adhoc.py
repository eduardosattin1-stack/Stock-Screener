#!/usr/bin/env python3
"""Publish an ad-hoc single-name debate to its stock page (debate-history rails).

Usage: python publish_adhoc.py SYM [--gcs]
Reads _adhoc_results/{SYM}.json + _adhoc_skeptic/{SYM}.json + _adhoc_director/{SYM}.json and writes
frontend/public/speculair_debate_history/{SYM}.json (standard SpeculairDebateCard fields — no
scale/catalyst block, so it renders as a clean debate, no header badge). Pushes to GCS with --gcs.
"""
import json, os, datetime, subprocess, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HIST = os.path.join(ROOT, "frontend", "public", "speculair_debate_history")
GCS = "gs://screener-signals-carbonbridge/scans/speculair_debate_history"
TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

FIELDS = ["company", "sector", "signal_type", "bull_thesis", "bear_thesis", "sop_bull", "sop_bear",
          "sop_fair_value", "sop_breakdown", "risk_reward", "catalyst_status", "peer_comps_note",
          "verdict", "conviction", "value_conviction", "moat", "moat_trend", "secular_threat",
          "secular_theme", "consensus_delta", "valley_of_death", "positioning_washout",
          "forcing_function", "moderator_conclusion", "interrogator_dossier", "interrogator_score",
          "trajectory", "current_price", "target_px"]


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: publish_adhoc.py SYM [--gcs]"); sys.exit(1)
    sym = args[0].upper()

    r = _load(os.path.join(HERE, "_adhoc_results", sym + ".json"))
    if not r:
        print(f"FATAL: no _adhoc_results/{sym}.json"); sys.exit(1)
    if not (r.get("interrogator_dossier") or "").strip():
        md = os.path.join(HERE, "dossiers", sym + ".md")
        if os.path.exists(md):
            r["interrogator_dossier"] = open(md, encoding="utf-8").read()
    sk = _load(os.path.join(HERE, "_adhoc_skeptic", sym + ".json")) or {}
    d = (_load(os.path.join(HERE, "_adhoc_director", sym + ".json")) or {}).get("assessment", {})

    entry = {"date": TODAY, "source": r.get("source", "opus_adhoc_online"),
             "transcript_source": r.get("transcript_source", "web")}
    for k in FIELDS:
        if k in r:
            entry[k] = r[k]
    entry["skeptic_verdict"] = sk.get("verdict", "")
    entry["skeptic_kill_fact"] = sk.get("kill_fact", "")
    entry["director_conviction"] = d.get("director_conviction")
    entry["would_seat"] = d.get("would_seat")
    entry["director_posture"] = d.get("posture")
    entry["director_thesis"] = d.get("thesis")

    os.makedirs(HIST, exist_ok=True)
    hp = os.path.join(HIST, sym + ".json")
    existing = _load(hp) if os.path.exists(hp) else []
    if not isinstance(existing, list):
        existing = []
    existing = [e for e in existing if e.get("date") != TODAY]
    hist = [entry] + existing
    hist.sort(key=lambda e: e.get("date", ""), reverse=True)
    json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if "--gcs" in sys.argv:
        gcloud = shutil.which("gcloud") or "gcloud"
        try:
            subprocess.run([gcloud, "storage", "cp", hp, GCS + "/" + sym + ".json"],
                           check=True, capture_output=True, text=True)
            print(f"  uploaded -> {GCS}/{sym}.json")
        except Exception as e:
            print(f"  WARN gcs: {e}")

    print(f"{sym}: verdict={entry.get('verdict')} conviction={entry.get('conviction')}/5 "
          f"value_conv={entry.get('value_conviction')} director={entry.get('director_conviction')} "
          f"would_seat={entry.get('would_seat')} skeptic={entry.get('skeptic_verdict')}")
    print(f"published -> {hp}")


if __name__ == "__main__":
    main()
