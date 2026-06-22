#!/usr/bin/env python3
"""Publish the scale-out 45-name debate to the frontend + a master "every comment" JSON.

Reads the artifacts written by _scaleout_debate.mjs:
  _scaleout_results/{SYM}.json   - per-name Interrogator/Architect/CRO debate
  _scaleout_skeptic/{SYM}.json   - per-name adversarial kill-check
  _scaleout_director.json        - cross-basket Scale-Director (scale_tier/conviction/...)

Writes:
  frontend/public/speculair_debate_history/{SYM}.json   - dated debate entry per name
        (this alone surfaces the "Speculair Debate" tab + full debate card on each
         stock page; see frontend page.tsx debateData memo — history-present => hasDebate)
  backend/_opus_debate/_scaleout_master.json            - the consolidated "every comment" file

With --gcs it also uploads each history file to
  gs://screener-signals-carbonbridge/scans/speculair_debate_history/{SYM}.json
so the stock page's GCS-first fetch serves it immediately (public/ is the Vercel fallback).

The scale-out names do NOT join the apex/value/disruptor baskets — this is a per-stock
discussion + scale-tier overlay only, with zero NAV pollution.
"""
import json, os, sys, glob, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))                 # backend/_opus_debate
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))            # repo root
RES_DIR = os.path.join(HERE, "_scaleout_results")
SKEP_DIR = os.path.join(HERE, "_scaleout_skeptic")
DOSSIER_DIR = os.path.join(HERE, "dossiers")
DIRECTOR_FILE = os.path.join(HERE, "_scaleout_director.json")
HIST_DIR = os.path.join(ROOT, "frontend", "public", "speculair_debate_history")
MASTER_FILE = os.path.join(HERE, "_scaleout_master.json")
GCS_PREFIX = "gs://screener-signals-carbonbridge/scans/speculair_debate_history"

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
BASKET_LABELS = {"A": "OPTICAL", "B": "GRID", "C": "THERMAL",
                 "D": "PWR-SEMI", "E": "POWER-GEN", "F": "MEMORY"}

# Narrative fields carried verbatim from the debate result into the stock-page history entry.
DEBATE_FIELDS = [
    "company", "basket", "basket_label", "sector",
    "bull_thesis", "bear_thesis", "sop_bull", "sop_bear",
    "sop_fair_value", "sop_breakdown", "risk_reward",
    "catalyst_status", "peer_comps_note", "role_in_scaleout",
    "verdict", "conviction", "value_conviction",
    "moat", "moat_trend", "secular_threat", "secular_theme",
    "consensus_delta", "valley_of_death", "positioning_washout",
    "forcing_function", "moderator_conclusion",
    "interrogator_dossier", "interrogator_score", "trajectory",
    "current_price", "market_cap", "listing_note",
]


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARN could not read {os.path.basename(path)}: {e}")
        return None


def main():
    push_gcs = "--gcs" in sys.argv
    os.makedirs(HIST_DIR, exist_ok=True)

    director = _load(DIRECTOR_FILE) or {}
    assess = {a.get("symbol", "").upper(): a
              for a in (director.get("assessments") or []) if a.get("symbol")}

    result_files = sorted(glob.glob(os.path.join(RES_DIR, "*.json")))
    if not result_files:
        print("FATAL: no _scaleout_results/*.json — did the debate run?")
        sys.exit(1)

    master_names = {}
    published, skipped, no_scale, refuted = [], [], [], []
    tier_counts = {"CORE": 0, "LEVER": 0, "TACTICAL": 0, "PASS": 0, "(none)": 0}

    for rf in result_files:
        sym = os.path.splitext(os.path.basename(rf))[0].upper()
        res = _load(rf)
        if not res:
            skipped.append(sym)
            continue

        # dossier fallback: if the agent didn't inline interrogator_dossier, read the .md
        if not (res.get("interrogator_dossier") or "").strip():
            md = os.path.join(DOSSIER_DIR, sym + ".md")
            if os.path.exists(md):
                with open(md, encoding="utf-8") as f:
                    res["interrogator_dossier"] = f.read()

        skep = _load(os.path.join(SKEP_DIR, sym + ".json")) or {}
        a = assess.get(sym, {})

        scale = None
        if a:
            tier = (a.get("scale_tier") or "").upper() or None
            scale = {
                "tier": tier,
                "conviction": a.get("scale_conviction"),
                "basket": a.get("basket") or res.get("basket"),
                "basket_label": res.get("basket_label")
                or BASKET_LABELS.get((a.get("basket") or res.get("basket") or ""), ""),
                "role": a.get("role"),
                "rationale": a.get("scale_rationale"),
                "demand_durability": a.get("demand_durability"),
                "valuation_posture": a.get("valuation_posture"),
                "would_seat": a.get("would_seat"),
                "posture": a.get("posture"),
                "expected_return_pct": a.get("expected_return_pct"),
            }
            tier_counts[tier if tier in tier_counts else "(none)"] += 1
        else:
            no_scale.append(sym)
            tier_counts["(none)"] += 1

        sv = (skep.get("verdict") or "").upper()
        if sv == "REFUTED":
            refuted.append(sym)

        # ---- the dated stock-page debate entry ----
        entry = {"date": TODAY, "source": res.get("source", "opus_scaleout_online")}
        for k in DEBATE_FIELDS:
            if k in res:
                entry[k] = res[k]
        entry["basket_label"] = res.get("basket_label") or BASKET_LABELS.get(res.get("basket", ""), "")
        entry["skeptic_verdict"] = skep.get("verdict", "")
        entry["skeptic_kill_fact"] = skep.get("kill_fact", "")
        entry["skeptic_corrections"] = skep.get("corrections", "")
        entry["skeptic_evidence"] = skep.get("evidence", [])
        if scale:
            entry["scale"] = scale

        # merge with any existing history (preserve prior debates; replace same-date entry)
        hist_path = os.path.join(HIST_DIR, sym + ".json")
        existing = _load(hist_path) if os.path.exists(hist_path) else []
        if not isinstance(existing, list):
            existing = []
        existing = [e for e in existing if e.get("date") != TODAY]
        history = [entry] + existing
        history.sort(key=lambda e: e.get("date", ""), reverse=True)
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        published.append(sym)

        # ---- master "every comment" record ----
        rec = dict(res)
        rec["skeptic"] = skep
        if scale:
            rec["scale"] = scale
        master_names[sym] = rec

    master = {
        "generated_at": datetime.datetime.now().isoformat(),
        "theme": "AI scale-out / scale-up compute build-out",
        "n_names": len(master_names),
        "regime": director.get("regime", ""),
        "risk_stance": director.get("risk_stance", ""),
        "thesis_overview": director.get("thesis_overview", ""),
        "baskets": {k: BASKET_LABELS[k] for k in BASKET_LABELS},
        "basket_ranking": director.get("basket_ranking", {}),
        "top_picks": director.get("top_picks", []),
        "correlation_memo": director.get("correlation_memo", ""),
        "director_memo": director.get("memo", ""),
        "tier_counts": tier_counts,
        "names": master_names,
    }
    with open(MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)

    if push_gcs and published:
        print(f"\nUploading {len(published)} history files to GCS...")
        # shutil.which resolves gcloud.cmd on Windows (a bare "gcloud" in a subprocess
        # list skips PATHEXT and fails WinError 2); fall back to a shell glob otherwise.
        import shutil
        gcloud = shutil.which("gcloud") or "gcloud"
        ok = 0
        for sym in published:
            src = os.path.join(HIST_DIR, sym + ".json")
            try:
                subprocess.run([gcloud, "storage", "cp", src, f"{GCS_PREFIX}/{sym}.json"],
                               check=True, capture_output=True, text=True)
                ok += 1
            except Exception as e:
                print(f"  WARN gcs cp {sym}: {e}")
        print(f"  uploaded {ok}/{len(published)} to {GCS_PREFIX}/")

    print("\n=== scale-out publish summary ===")
    print(f"published debate history : {len(published)} names -> {HIST_DIR}")
    print(f"master 'every comment'   : {MASTER_FILE}")
    print(f"tier counts              : {tier_counts}")
    print(f"top_picks                : {', '.join(master.get('top_picks', []) or []) or '(director file missing)'}")
    if refuted:
        print(f"skeptic REFUTED          : {', '.join(refuted)}")
    if no_scale:
        print(f"NO director scale (badge will not show): {', '.join(no_scale)}")
    if skipped:
        print(f"SKIPPED (no debate result): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
