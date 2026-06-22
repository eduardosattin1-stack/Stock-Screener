#!/usr/bin/env python3
"""Publish the ad-hoc AMZN debate to the AMZN stock page (debate-history rails).

Reads _adhoc_results/AMZN.json + _adhoc_skeptic/AMZN.json + _amzn_director.json and writes
frontend/public/speculair_debate_history/AMZN.json (the standard SpeculairDebateCard fields —
no scale/catalyst block, so it renders as a clean debate, no header badge). Pushes to GCS.
"""
import json, os, datetime, subprocess, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SYM = "AMZN"
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
    r = _load(os.path.join(HERE, "_adhoc_results", SYM + ".json"))
    if not r:
        print(f"FATAL: no _adhoc_results/{SYM}.json"); sys.exit(1)
    if not (r.get("interrogator_dossier") or "").strip():
        md = os.path.join(HERE, "dossiers", SYM + ".md")
        if os.path.exists(md):
            r["interrogator_dossier"] = open(md, encoding="utf-8").read()
    sk = _load(os.path.join(HERE, "_adhoc_skeptic", SYM + ".json")) or {}
    d = (_load(os.path.join(HERE, "_amzn_director.json")) or {}).get("assessment", {})

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
    hp = os.path.join(HIST, SYM + ".json")
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
            subprocess.run([gcloud, "storage", "cp", hp, GCS + "/" + SYM + ".json"],
                           check=True, capture_output=True, text=True)
            print(f"  uploaded -> {GCS}/{SYM}.json")
        except Exception as e:
            print(f"  WARN gcs: {e}")

    print(f"AMZN: verdict={entry.get('verdict')} conviction={entry.get('conviction')}/5 "
          f"value_conv={entry.get('value_conviction')} director={entry.get('director_conviction')} "
          f"would_seat={entry.get('would_seat')} skeptic={entry.get('skeptic_verdict')}")
    print(f"published -> {hp}")


if __name__ == "__main__":
    main()
