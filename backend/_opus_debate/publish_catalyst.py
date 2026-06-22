#!/usr/bin/env python3
"""Publish the Basket-13 catalyst diagnostic to the stock pages + a master JSON.

Same rails as publish_scaleout.py: writes speculair_debate_history/{SYM}.json per name
(surfaces the "Speculair Debate" tab + full SpeculairDebateCard) and, instead of the
franchise `scale` block, a `catalyst` block the header renders as a CATALYST badge
(event · CRO-verdict · Director-0-100). Pushes to GCS so the badges go live.
"""
import json, os, sys, glob, subprocess, datetime, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.join(HERE, "_catalyst_results")
SKEP = os.path.join(HERE, "_catalyst_skeptic")
DOSSIER = os.path.join(HERE, "dossiers")
DIRECTOR = os.path.join(HERE, "_catalyst_director.json")
HIST = os.path.join(ROOT, "frontend", "public", "speculair_debate_history")
MASTER = os.path.join(HERE, "_catalyst_master.json")
GCS_PREFIX = "gs://screener-signals-carbonbridge/scans/speculair_debate_history"
TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

DEBATE_FIELDS = [
    "company", "cluster", "driver", "bull_thesis", "bear_thesis", "sop_bull", "sop_bear",
    "sop_fair_value", "sop_breakdown", "risk_reward", "catalyst_status", "catalyst_summary",
    "dated_milestone", "forcing_function", "verdict", "conviction", "value_conviction",
    "moat", "moat_trend", "secular_threat", "secular_theme", "consensus_delta",
    "valley_of_death", "positioning_washout", "moderator_conclusion",
    "interrogator_dossier", "interrogator_score", "trajectory",
    "live_price", "target_px", "downside_floor",
]


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    push = "--gcs" in sys.argv
    os.makedirs(HIST, exist_ok=True)
    director = _load(DIRECTOR) or {}
    dassess = {a.get("symbol", "").upper(): a for a in (director.get("assessments") or [])}

    master, published = {}, []
    for rf in sorted(glob.glob(os.path.join(RES, "*.json"))):
        sym = os.path.splitext(os.path.basename(rf))[0].upper()
        r = _load(rf)
        if not r:
            continue
        if not (r.get("interrogator_dossier") or "").strip():
            md = os.path.join(DOSSIER, sym + ".md")
            if os.path.exists(md):
                r["interrogator_dossier"] = open(md, encoding="utf-8").read()
        sk = _load(os.path.join(SKEP, sym + ".json")) or {}
        a = dassess.get(sym, {})

        catalyst = {
            "driver": r.get("driver") or a.get("driver"),
            "cluster": r.get("cluster") or a.get("cluster"),
            "catalyst_status": r.get("catalyst_status"),
            "dated_milestone": r.get("dated_milestone"),
            "cro_verdict": r.get("verdict"),
            "cro_conviction": r.get("conviction"),
            "director_conviction": a.get("conviction"),
            "skeptic_verdict": sk.get("verdict"),
            "posture": a.get("posture"),
            "expected_return_pct": a.get("expected_return_pct"),
            "live_price": r.get("live_price"),
            "target_px": r.get("target_px"),
            "downside_floor": r.get("downside_floor"),
            "binding_reason": a.get("binding_reason") or r.get("catalyst_summary"),
        }

        entry = {"date": TODAY, "source": r.get("source", "opus_catalyst_online")}
        for k in DEBATE_FIELDS:
            if k in r:
                entry[k] = r[k]
        entry["skeptic_verdict"] = sk.get("verdict", "")
        entry["skeptic_kill_fact"] = sk.get("kill_fact", "")
        entry["catalyst"] = catalyst

        hp = os.path.join(HIST, sym + ".json")
        existing = _load(hp) if os.path.exists(hp) else []
        if not isinstance(existing, list):
            existing = []
        existing = [e for e in existing if e.get("date") != TODAY]
        hist = [entry] + existing
        hist.sort(key=lambda e: e.get("date", ""), reverse=True)
        json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        published.append(sym)

        rec = dict(r)
        rec["skeptic"] = sk
        rec["catalyst"] = catalyst
        master[sym] = rec

    json.dump({
        "generated_at": datetime.datetime.now().isoformat(),
        "theme": "Basket-13 catalyst funnel — event-driven special situations (diagnostic)",
        "n_names": len(master),
        "regime": director.get("regime", ""),
        "risk_stance": director.get("risk_stance", ""),
        "n_verdict_a": director.get("n_verdict_a"),
        "n_conv5": director.get("n_conv5"),
        "n_dir80": director.get("n_dir80"),
        "ranking": director.get("ranking", []),
        "correlation_memo": director.get("correlation_memo", ""),
        "director_memo": director.get("memo", ""),
        "names": master,
    }, open(MASTER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if push and published:
        gcloud = shutil.which("gcloud") or "gcloud"
        srcs = [os.path.join(HIST, s + ".json") for s in published]
        try:
            subprocess.run([gcloud, "storage", "cp", *srcs, GCS_PREFIX + "/"],
                           check=True, capture_output=True, text=True)
            print(f"  uploaded {len(srcs)} -> {GCS_PREFIX}/")
        except Exception as e:
            print(f"  WARN gcs: {e}")

    print(f"\npublished: {len(published)} -> {HIST}")
    print(f"master:    {MASTER}")
    print(f"dir-80+:   {director.get('n_dir80')} | verdict-A: {director.get('n_verdict_a')}")


if __name__ == "__main__":
    main()
