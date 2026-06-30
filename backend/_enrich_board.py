#!/usr/bin/env python3
"""_enrich_board.py — the single-source build stage for Catalyst Watch.

Pipeline (manual §6/§9):  raw merged export  →  _post_board.process()  →  enriched.
Reads the RAW merged 231-board (produced by _export_candidates.py from the 3 sources),
runs the deterministic post-skeptic pass, merges the corrected scores/tiers + new
columns back onto the nested CatalystScanReports, and emits:
  * catalyst_candidates_231.{json,csv}            (the deliverable export, now CORRECTED)
  * frontend/app/data/catalystBoardEnriched.ts    (THE single source the routes read)

NONE-tier names are kept in CATALYST_BOARD_ENRICHED (so the detail page can still show
the audit trail of *why* they were dropped) but excluded from CATALYST_CANDIDATES_ENRICHED
(so they vanish from the board list — manual §6 inject rule).

Usage:  python _enrich_board.py [raw_export.json] [--tilt 0.12]
"""
import json, sys, os, argparse
import pandas as pd
from _post_board import process, COLS, LANE_PRIORITY, SUPER, TILT_DEFAULT

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
RAW_JSON = os.path.join(BASE, "_catalyst_raw.json")   # input: pre-enrichment merge (from _export_candidates)
RAW_CSV  = os.path.join(BASE, "_catalyst_raw.csv")
DELIV_JSON = os.path.join(ROOT, "catalyst_candidates_231.json")   # output: the enriched deliverable
DELIV_CSV  = os.path.join(ROOT, "catalyst_candidates_231.csv")
TS_OUT   = os.path.join(ROOT, "frontend/app/data/catalystBoardEnriched.ts")

TIER_RANK = {"ACTIVE": 0, "CONTINGENT": 1, "WATCH": 2, "NONE": 9}
SRC_RANK  = {"manual": 0, "widen": 1, "sweep": 2}

VAL_F = os.path.join(BASE, "_valuation.json")   # optional sidecar: {SYMBOL: {valuation schema}}
# scalar valuation fields merged into the flat df so process() can compute R:R
VAL_SCALARS = ["valuation_method", "fair_value_target", "downside_floor", "reference_price",
               "reference_rr", "deal_price", "undisturbed_price", "win_prob", "target_on_win",
               "downside_on_loss", "recovery_value", "announced_return_per_share", "residual_value"]
# new fields the pass adds that we thread onto each nested report
ENRICH_FIELDS = ["lane_canon", "lane_priority", "edge_grade", "verify_status",
                 "resolution_driver", "board_priority", "corrections",
                 "adjusted_loeb_score_orig", "tier_orig", "rr_ratio_orig",
                 # phase-2 edge axis (computed by _post_board against a fresh quote)
                 "computed_rr", "ev_pct", "win_prob", "payoff", "up_leg", "down_leg",
                 "live_price", "drift", "rr_stale", "edge_flags", "sop_built",
                 "valuation_method", "fair_value_target", "downside_floor",
                 "valuation_basis", "reference_price", "reference_rr"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="?", default=RAW_JSON)
    ap.add_argument("--tilt", type=float, default=TILT_DEFAULT)
    args = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    # nested reports (frontend shape) + flat df (process() shape)
    nested = json.load(open(args.raw, encoding="utf-8"))["candidates"]
    df = pd.read_csv(RAW_CSV)

    # merge the optional valuation sidecar so process() can compute the lane-aware R:R
    val = {}
    if os.path.exists(VAL_F):
        val = {str(k).upper(): v for k, v in json.load(open(VAL_F, encoding="utf-8")).items()}
        for col in VAL_SCALARS:
            df[col] = [(val.get(str(s).upper()) or {}).get(col) for s in df[COLS["symbol"]]]
        df["_val"] = [val.get(str(s).upper()) for s in df[COLS["symbol"]]]   # full dict for sop_reconcile

    df, deltas = process(df, args.tilt)
    if "_val" in df.columns:
        df = df.drop(columns=["_val"])   # don't serialize the dict into the CSV deliverable

    # index the corrected flat rows by symbol
    by_sym = {str(r[COLS["symbol"]]): r for _, r in df.iterrows()}

    def clean(v):
        if isinstance(v, float) and pd.isna(v): return None
        return v

    for rep in nested:
        rep.pop("recommendation", None)   # dead field: the sweep hardcoded "WATCH" for every name and
                                          # never computes a real Loeb call; the UI no longer reads it.
        row = by_sym.get(rep["symbol"])
        if row is None:
            continue
        corr_score = clean(row[COLS["score"]])
        corr_tier  = clean(row[COLS["tier"]])
        corr_rr    = clean(row[COLS["rr"]])
        # apply corrections onto the nested report (catalyst_density_score stays RAW for the
        # raw→adjusted divergence display; adjusted/final carry the corrected value)
        rep["adjusted_loeb_score"] = corr_score
        rep["final_adjusted_loeb"] = corr_score
        rep["tier"] = corr_tier
        rep["upside_downside_ratio"] = corr_rr          # null when the 1.8 template was stripped
        for f in ENRICH_FIELDS:
            rep[f] = clean(row.get(f))
        rep["corrections"] = list(row.get("corrections") or [])
        rep["edge_flags"] = list(row.get("edge_flags") or [])
        rep["valuation"] = val.get(str(rep["symbol"]).upper())   # full build incl sop_components

    # write corrected deliverables (JSON nested + CSV flat)
    json.dump({"count": len(nested), "generated": __import__("datetime").date.today().isoformat(), "tilt": args.tilt,
               "candidates": nested},
              open(DELIV_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    df.to_csv(DELIV_CSV, index=False, encoding="utf-8-sig")

    # ---- generate the single-source frontend module ----
    board = {rep["symbol"]: rep for rep in nested}
    def sort_key(rep):
        return (TIER_RANK.get(rep.get("tier"), 3),
                -(rep.get("board_priority") or 0),
                rep.get("lane_priority") or 9,
                SRC_RANK.get(rep.get("_source"), 2),
                rep.get("symbol"))
    cand = []
    for rep in sorted([r for r in nested if r.get("tier") in ("ACTIVE", "CONTINGENT", "WATCH")], key=sort_key):
        cand.append({
            "symbol": rep["symbol"], "name": rep.get("company_name"),
            "price": rep.get("price"), "market_cap": rep.get("market_cap"),
            "catalyst_score": rep.get("catalyst_density_score"),
            "adjusted_loeb_score": rep.get("adjusted_loeb_score"),
            "flags": [x for x in [rep.get("tier"), rep.get("lane")] if x],
            "has_special_flag": rep.get("tier") == "ACTIVE",
            "categories": [rep.get("lane")],
            "rr_ratio": rep.get("upside_downside_ratio"),
            "resolution_driver": rep.get("resolution_driver"),
            "lane_canon": rep.get("lane_canon"),
            "board_priority": rep.get("board_priority"),
            "edge_grade": rep.get("edge_grade"),
            "computed_rr": rep.get("computed_rr"),
            "ev_pct": rep.get("ev_pct"), "win_prob": rep.get("win_prob"), "payoff": rep.get("payoff"),
            "valuation_method": rep.get("valuation_method"),
            "edge_flags": rep.get("edge_flags") or [],
            "is_scanned": True, "convergence_score": None,
        })
    # driver-concentration over ACTIVE (the §3 #5 hidden-factor view)
    act = [r for r in nested if r.get("tier") == "ACTIVE"]
    conc = {}
    for r in act:
        sup = SUPER.get(r.get("resolution_driver"), "Idiosyncratic")
        conc[sup] = conc.get(sup, 0) + 1
    conc_pct = {k: round(100 * v / max(len(act), 1)) for k, v in sorted(conc.items(), key=lambda kv: -kv[1])}

    hdr = ("// Catalyst Watch — ENRICHED single-source board (raw merge → _post_board pass).\n"
           "// AUTO-GENERATED by backend/_enrich_board.py — do not hand-edit.\n")
    ts = (hdr +
          f"export const CATALYST_DRIVER_CONCENTRATION: Record<string, number> = {json.dumps(conc_pct)};\n"
          f"export const CATALYST_BOARD_ENRICHED: Record<string, any> = {json.dumps(board, ensure_ascii=False)};\n"
          f"export const CATALYST_CANDIDATES_ENRICHED: any[] = {json.dumps(cand, ensure_ascii=False)};\n")
    open(TS_OUT, "w", encoding="utf-8").write(ts)

    n_none = sum(1 for r in nested if r.get("tier") == "NONE")
    print(f"ENRICHED {len(nested)} reports | board(non-NONE)={len(cand)} | NONE-excluded={n_none} | corrections={len(deltas)}")
    print(f"  driver concentration (ACTIVE n={len(act)}): {conc_pct}")
    print(f"  wrote catalyst_candidates_231.json/.csv + {os.path.relpath(TS_OUT, ROOT)}")

if __name__ == "__main__":
    main()
