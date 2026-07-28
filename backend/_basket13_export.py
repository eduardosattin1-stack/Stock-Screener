#!/usr/bin/env python3
"""Basket 13 — export the tracker to the frontend data module.

Reads _basket13_tracker.json (+ _basket13_out.json for the CRO conditions/entry limits)
and writes frontend/app/data/basket13.ts — the module the Catalyst Watch page imports.
Re-run after every inject/resolve, then ship via the §10 publishing flow (the data is
baked into the bundle, same as the board).

Usage: python _basket13_export.py
"""
import json, os, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
TRK = os.path.join(BASE, "_basket13_tracker.json")
OUTJ = os.path.join(BASE, "_basket13_out.json")
DIRJ = os.path.join(BASE, "_opus_debate", "_catalyst_director.json")
TS = os.path.join(ROOT, "frontend", "app", "data", "basket13.ts")

# IMPORT the cap dials — never mirror them (fixed 2026-07-28). This file used to keep its own
# copy and had drifted a full week stale: it was still publishing max_per_driver 2 and a
# bio_convergence lane cap of 5 to the UI, both LIFTED in inject on 2026-07-20. The page was
# showing the user caps that no longer existed.
import sys as _sys
_sys.path.insert(0, BASE)
from _basket13_inject import (MAX_PER_DRIVER, MAX_SUPER_PTS as MAX_SUPER_PCT, MAX_PER_LANE,
                              MAX_WATCHLIST, MAX_WATCHLIST_PER_DRIVER, UNCAPPED_DRIVERS,
                              UNCAPPED_CLUSTERS, INVESTED_PCT, EQUAL_WEIGHT)


def main():
    t = json.load(open(TRK, encoding="utf-8"))
    cro_cond, cro_check = {}, {}
    if os.path.exists(OUTJ):
        out = json.load(open(OUTJ, encoding="utf-8"))
        for v in out.get("cro") or []:
            if v.get("symbol"):
                cro_cond[v["symbol"]] = v.get("conditions") or []
                cro_check[v["symbol"]] = v.get("live_edge_check") or ""

    entries = []
    for e in t["entries"]:
        d = dict(e)
        det = e.get("cro_detail") or {}                       # self-contained: prefer the entry's stored CRO detail
        d["cro_conditions"] = det.get("conditions") or cro_cond.get(e["symbol"], [])
        d["cro_live_edge_check"] = det.get("live_edge_check") or cro_check.get(e["symbol"], "")
        # expected return % on the UNDERLYING (comparable with the live/realized marks):
        # binaries -> the CRO's recomputed EV; ratio names -> move to the fair-value target.
        # Pending (resting-limit) seats price the expectation off the LIMIT (the only fill price).
        basis = d.get("entry_price") or d.get("limit_price")
        if isinstance(d.get("expected_ev"), (int, float)):
            d["expected_return_pct"] = round(d["expected_ev"] * 100, 1)
        elif d.get("fair_value_target") and basis:
            d["expected_return_pct"] = round((d["fair_value_target"] / basis - 1) * 100, 1)
        else:
            d["expected_return_pct"] = None
        entries.append(d)

    unresolved = [e for e in entries if not e.get("resolution")]
    opene = [e for e in unresolved if e.get("status") != "PENDING_LIMIT"]
    pend = [e for e in unresolved if e.get("status") == "PENDING_LIMIT"]
    drv, clus, lanes = {}, {}, {}
    for e in unresolved:                # caps count pending as-if-filled
        drv[e["resolution_driver"]] = drv.get(e["resolution_driver"], 0) + 1
        clus[e["super_cluster"]] = round(clus.get(e["super_cluster"], 0.0) + (e["weight_pct"] or 0), 2)
        lanes[e.get("lane_canon")] = lanes.get(e.get("lane_canon"), 0) + 1
    invested = round(sum(e["weight_pct"] or 0 for e in opene), 2)
    pending_w = round(sum(e["weight_pct"] or 0 for e in pend), 2)

    # HONEST DATES (2026-07-28): "generated" is the LAST RUN'S date from the tracker ledger, not
    # export time — a re-export must never claim a new run happened. exported_at records the
    # export itself; marked_through says how fresh the NAV series is.
    runs = t.get("runs") or []
    marks_all = t.get("marks") or []
    last_run_date = (runs[-1].get("run_date") if runs else None) or datetime.date.today().isoformat()

    # latest Director read (the weekly debate output) — SEPARATE from the tracker's bi-weekly
    # run ledger, so the page can show this week's memo/decisions without a tracker stamp
    # (appending to runs[] would reset the 13-day re-debate self-gate — never do that here).
    latest_debate = None
    if os.path.exists(DIRJ):
        try:
            dj = json.load(open(DIRJ, encoding="utf-8"))
            latest_debate = {
                "asof": dj.get("asof"), "regime": dj.get("regime"), "risk_stance": dj.get("risk_stance"),
                "memo": dj.get("memo", ""), "ranking": dj.get("ranking", []),
                "assessments": [{k: a.get(k) for k in
                                 ("symbol", "cluster", "conviction", "would_seat", "posture",
                                  "expected_return_pct", "catalyst_status", "binding_reason",
                                  "cro_verdict", "cro_conviction")}
                                for a in dj.get("assessments", [])],
            }
        except Exception as e:
            print(f"  WARN latest debate unreadable ({e}) — page falls back to the run-ledger memo")

    payload = {
        "generated": last_run_date,
        "exported_at": datetime.date.today().isoformat(),
        "marked_through": marks_all[-1].get("date") if marks_all else None,
        "latest_debate": latest_debate,
        "invested_pct": invested,
        "pending_pct": pending_w,
        "cash_pct": round(100 - invested - pending_w, 2),
        "caps": {"max_per_driver": MAX_PER_DRIVER, "max_super_pct": MAX_SUPER_PCT,
                 "max_names": None,                      # head-count cap removed 2026-07-28
                 "max_per_lane": MAX_PER_LANE, "max_watchlist": MAX_WATCHLIST,
                 "max_watchlist_per_driver": MAX_WATCHLIST_PER_DRIVER,
                 "uncapped_drivers": sorted(UNCAPPED_DRIVERS),
                 "uncapped_clusters": sorted(UNCAPPED_CLUSTERS)},
        "sizing": {"equal_weight": EQUAL_WEIGHT, "invested_pct": INVESTED_PCT,
                   "weight_per_seat": round(INVESTED_PCT / len(unresolved), 4) if unresolved else None},
        "driver_utilization": dict(sorted(drv.items(), key=lambda kv: -kv[1])),
        "cluster_utilization": dict(sorted(clus.items(), key=lambda kv: -kv[1])),
        "lane_utilization": dict(sorted(lanes.items(), key=lambda kv: -kv[1])),
        "entries": entries,
        "watchlist": t.get("watchlist", []),    # on-deck: cap-blocked-but-wanted (renders below the basket)
        "watchlist_marks": t.get("watchlist_marks", []),   # on-deck equal-weight cohort NAV series (separate track record)
        "non_selections": t.get("non_selections", []),
        "runs": t.get("runs", []),
        "marks": t.get("marks", []),    # daily NAV series (_basket13_mark.py) — the track record
        # PRIOR BOOKS (2026-07-28): a re-founding restarts marks[] at 100, which would otherwise
        # make the realized record vanish from the UI. Ship the archived books' resolutions so the
        # closed track record stays visible and clearly labelled as a prior book.
        "prior_books": [{"closed": b.get("closed"), "reason": b.get("reason"),
                         "final_nav": b.get("final_nav"), "n_entries": b.get("n_entries"),
                         "resolutions": [{"symbol": e["symbol"], "entry_price": e.get("entry_price"),
                                          "expected_return_pct": None,
                                          "weight_pct": e.get("weight_pct"),
                                          **{k: v for k, v in (e.get("resolution") or {}).items()}}
                                         for e in b.get("entries", []) if e.get("resolution")]}
                        for b in t.get("book_archive", [])],
        # stamping corrections (e.g. a resolution reversed as a wrong assessment) — kept visible so
        # a reversal is auditable rather than a number that quietly changed
        "corrections": t.get("corrections", []),
        "memo": (t.get("runs") or [{}])[-1].get("memo", ""),
    }
    hdr = ("// Basket 13 — Catalyst sleeve (paper, event-resolution tracker view).\n"
           "// AUTO-GENERATED by backend/_basket13_export.py — do not hand-edit.\n")
    open(TS, "w", encoding="utf-8").write(
        hdr + f"export const BASKET13: any = {json.dumps(payload, ensure_ascii=False)};\n")
    res = [e for e in entries if e.get("resolution")]
    print(f"EXPORTED basket13.ts: {len(opene)} open + {len(res)} resolved entries, "
          f"{len(payload['non_selections'])} non-selections, invested {invested}%  -> {os.path.relpath(TS, ROOT)}")

    # ship the deep-dossier store (per-symbol, most recent wins) to the static
    # public dir — the /catalysts depth view fetches /basket13_dossiers.json and renders
    # the deep-dossier panel above the legacy board/backend dossier when a symbol has one.
    DSTORE = os.path.join(BASE, "_basket13_dossiers.json")
    if os.path.exists(DSTORE):
        pub = os.path.join(ROOT, "frontend", "public", "basket13_dossiers.json")
        data = json.load(open(DSTORE, encoding="utf-8"))
        json.dump(data, open(pub, "w", encoding="utf-8", newline="\n"), ensure_ascii=False)
        print(f"EXPORTED {len(data.get('dossiers', {}))} deep-dossiers -> {os.path.relpath(pub, ROOT)}")


if __name__ == "__main__":
    main()
