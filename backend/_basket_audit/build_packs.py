"""Basket audit 2026-11: build one evidence pack per methodology basket (read-only inputs).

Inputs (all read-only):
  scratch copies of scans/methodology_picks.json + scans/methodology_tracking.json (passed as args)
  backend/_opus_debate/latest_global.json            the 2026-11-07 scan (3,430 names, 194 fields)
  backend/_opus_debate/results_regime/*.json         this week's debate records
  backend/_opus_debate/value_grade_input.json        scan-vs-debate fields
  backend/_opus_debate/_radar_universe.json          which baskets put each name in the debate universe
  frontend/public/speculair_{baskets,value_apex}.json  the published books
  backend/_opus_debate/_px_cache/                    daily closes (fetched for missing names)

Output: backend/_basket_audit/packs/<basket>.json and packs/_overview.json

    python backend/_basket_audit/build_packs.py <methodology_picks.json> <methodology_tracking.json>
"""
import collections
import datetime as dt
import json
import logging
import os
import statistics as st
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
HERE = Path(__file__).resolve().parent
BK = HERE.parent
REPO = BK.parent
OD = BK / "_opus_debate"
sys.path.insert(0, str(BK)); sys.path.insert(0, str(OD))
import _signal_score as SS  # noqa: E402

PICKS = json.load(open(sys.argv[1], encoding="utf-8"))
TRACK = json.load(open(sys.argv[2], encoding="utf-8"))
SCAN = json.load(open(OD / "latest_global.json", encoding="utf-8"))
SCAN_BY = {s["symbol"]: s for s in SCAN["stocks"]}
TODAY = dt.date(2026, 11, 12)

METRIC = {"dcf_fcff": "dcf_fcff_mos", "earnings_yield_gap": "earnings_yield_gap_mos",
          "ev_gross_profit": "ev_gross_profit_mos", "rd_capitalized_dcf": "rd_capitalized_dcf_mos",
          "owner_earnings": "owner_earnings_mos", "epv": "epv_mos", "graham_revised": "graham_revised_mos",
          "acquirers_multiple": "acquirers_multiple_mos", "ev_gp": "ev_gp_mos",
          "iv15_deep_value": "iv15_deep_value_mos", "convergence": "consensus_mos",
          "fundamental_momentum": "momentum_mos"}


def num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def D(s):
    return dt.date.fromisoformat(str(s)[:10])


# ── debate join ──────────────────────────────────────────────────────────────
REC = {}
for f in (OD / "results_regime").glob("*.json"):
    try:
        r = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if isinstance(r, dict):
        REC[r.get("symbol") or f.stem] = r
GIN = {x["symbol"]: x for x in json.load(open(OD / "value_grade_input.json", encoding="utf-8"))}
RADAR = {x["symbol"]: x for x in json.load(open(OD / "_radar_universe.json", encoding="utf-8"))}
REGIME = json.load(open(REPO / "frontend" / "public" / "speculair_baskets.json", encoding="utf-8"))
VALUE = json.load(open(REPO / "frontend" / "public" / "speculair_value_apex.json", encoding="utf-8"))
REG_SEATS = [p["symbol"] for p in REGIME.get("apex_basket", [])]
VAL_SEATS = [p["symbol"] for p in (VALUE.get("apex_basket") or VALUE.get("apex") or [])]
REG_RUN = [p.get("symbol") for p in REGIME.get("runner_ups", []) if isinstance(p, dict)]
VAL_RUN = [p.get("symbol") for p in VALUE.get("runner_ups", []) if isinstance(p, dict)]

# ── prices ───────────────────────────────────────────────────────────────────
need = set(["ACWI", "SPY"])
for b in PICKS["methodologies"].values():
    need |= {p["symbol"] for p in b.get("picks", [])} | {e["symbol"] for e in b.get("exits", [])}
for b in TRACK["methodologies"].values():
    need |= {h["symbol"] for h in b.get("current_holdings", [])} | {e["symbol"] for e in b.get("all_exits_2026", [])}
    for rb in b.get("rebalances", []):
        need |= set(rb.get("holdings") or [])
import live_debate_engine as E  # noqa: E402
E.load_api_keys()
PX = SS.load_prices(sorted(need), offline=False, key=E.get_key("FMP_API_KEY"))


def close_on(sym, day):
    q = SS._onbefore(PX.get(sym), day, lag=7)
    return q[1] if q else None


def ret_between(sym, d0, d1):
    a, b = close_on(sym, d0), close_on(sym, d1)
    return round(b / a - 1, 4) if a and b and a > 0 else None


def debate_of(sym):
    r, g = REC.get(sym) or {}, GIN.get(sym) or {}
    ng = r.get("numeric_gate")
    return {"in_debate_universe": sym in REC, "grade": r.get("verdict"), "value_conviction": r.get("value_conviction"),
            "conviction": r.get("conviction"), "thesis_state": r.get("thesis_state"), "entry_mode": r.get("entry_mode"),
            "update_mode": r.get("update_mode"), "last_full_debate": str(r.get("last_full_debate") or "")[:10],
            "numeric_gate": (ng.get("status") if isinstance(ng, dict) else ng),
            "forensic_gate": g.get("forensic_gate"), "debate_discount_pct": g.get("sop_mos_pct"),
            "scan_headline_mos_pct": g.get("scan_headline_mos_pct"), "peak_flag": g.get("peak_flag"),
            "freshness_stale": g.get("freshness_stale"), "funded_solvency": g.get("funded_solvency"),
            "moat": r.get("moat"), "secular_threat": r.get("secular_threat"),
            "regime_seat": sym in REG_SEATS, "value_seat": sym in VAL_SEATS,
            "regime_runner_up": sym in REG_RUN, "value_runner_up": sym in VAL_RUN}


def scan_brief(sym, key):
    s = SCAN_BY.get(sym) or {}
    keep = ("price", "currency", "fx_to_price", "market_cap", "sector", "sector_class", "country", "exchange",
            "years_history", "structural_break", "structural_break_reason", "cycle_flag", "norm_scale",
            "methodology_applicable", "net_debt", "p_fcf", "fcf_margin", "roic_avg", "revenue_yoy", "eps_yoy",
            "gross_margin", "net_margin", "altman_z", "piotroski", "pct_off_52w_high", "price_vs_sma200",
            "dcf_value", "epv_value", "graham_revised", "owner_earnings", "rd_capitalized_dcf", "iv15_deep_value",
            "consensus_fv", "momentum_fv", "acquirers_multiple", "ev_gp", "gp_ta", "iv15_saturated",
            "iv15_nogrowth_agreement") + tuple(METRIC.values())
    return {k: s.get(k) for k in keep if s.get(k) is not None} if s else {"in_scan": False}


OUT = HERE / "packs"
OUT.mkdir(parents=True, exist_ok=True)
overview = {"built": TODAY.isoformat(), "scan_date": str(SCAN.get("scan_date"))[:10], "scan_names": len(SCAN["stocks"]),
            "picks_last_updated": PICKS.get("last_updated"), "methodology_version": PICKS.get("methodology_version"),
            "tracking": {k: TRACK.get(k) for k in ("tracking_year", "reconstruction_note", "rebalance_cadence",
                                                   "rebalance_cadence_days", "rebalance_dates", "holdings_status")},
            "regime_seats": REG_SEATS, "value_seats": VAL_SEATS, "baskets": {}}
sets = {}
for key, b in PICKS["methodologies"].items():
    mfield = METRIC[key]
    picks = b.get("picks", [])
    sets[key] = {p["symbol"] for p in picks}
    # where the metric sits in the whole scan
    allv = sorted([num(s.get(mfield)) for s in SCAN["stocks"] if num(s.get(mfield)) is not None and s.get(mfield) > -1.0], reverse=True)
    pick_m = [num(p.get("mos")) for p in picks if num(p.get("mos")) is not None]
    cutoff = min(pick_m) if pick_m else None
    ties_at_cut = sum(1 for v in allv if cutoff is not None and abs(v - cutoff) < 1e-9)
    distinct_top = len(set(round(v, 4) for v in allv[:60]))
    rows = []
    for p in picks:
        sym = p["symbol"]
        ed = D(p["entry_date"]) if p.get("entry_date") else None
        scan_rank = None
        sv = num((SCAN_BY.get(sym) or {}).get(mfield))
        if sv is not None:
            scan_rank = 1 + sum(1 for v in allv if v > sv + 1e-12)
        rows.append({"symbol": sym, "entry_date": p.get("entry_date"), "entry_price": p.get("entry_price"),
                     "price_in_file": p.get("price"), "mos_in_file": p.get("mos"), "entry_metric": p.get("entry_metric"),
                     "fair_value": p.get("fair_value"), "weight": p.get("weight"),
                     "metric_in_scan": sv, "rank_in_scan_by_metric": scan_rank,
                     "return_since_entry_close": ret_between(sym, ed, TODAY) if ed else None,
                     "acwi_same_window": ret_between("ACWI", ed, TODAY) if ed else None,
                     "last_close": close_on(sym, TODAY),
                     "flags": {k: p.get(k) for k in ("cycle_flag", "structural_break", "structural_break_reason",
                                                     "methodology_applicable", "iv15_saturated", "norm_scale",
                                                     "mos_source", "consensus_votes", "consensus_agreement",
                                                     "years_history", "sector", "sector_class", "technical_signal")},
                     "scan": scan_brief(sym, key), "debate": debate_of(sym)})
    tr = TRACK["methodologies"].get(key, {})
    exits = []
    for e in tr.get("all_exits_2026", []):
        xd = D(e["exit_date"]) if e.get("exit_date") else None
        exits.append({**e, "return_after_exit_to_now": ret_between(e["symbol"], xd, TODAY) if xd else None,
                      "acwi_after_exit": ret_between("ACWI", xd, TODAY) if xd else None,
                      "still_in_scan": e["symbol"] in SCAN_BY,
                      "metric_in_scan_now": num((SCAN_BY.get(e["symbol"]) or {}).get(mfield)),
                      "debate": {k: v for k, v in debate_of(e["symbol"]).items() if k in ("grade", "value_conviction", "regime_seat", "value_seat")}})
    rebs = [{"date": r.get("date"), "n_holdings": len(r.get("holdings") or []),
             "entries": r.get("entries"), "exits": r.get("exits"), "methodology_version": r.get("methodology_version")}
            for r in tr.get("rebalances", [])]
    recent_exits = b.get("exits", [])
    g = collections.Counter(str(r["debate"]["grade"]) for r in rows)
    disc = [r["debate"]["debate_discount_pct"] for r in rows if num(r["debate"]["debate_discount_pct"]) is not None]
    scanm = [r["mos_in_file"] for r in rows if num(r["mos_in_file"]) is not None]
    rets = [r["return_since_entry_close"] for r in rows if r["return_since_entry_close"] is not None]
    exc = [r["return_since_entry_close"] - r["acwi_same_window"] for r in rows
           if r["return_since_entry_close"] is not None and r["acwi_same_window"] is not None]
    # a move beyond +/-300% between two closes is a broken vendor price series, not a return
    # (50GP.L flips 77 -> 0.77 -> 74.75 in FMP: pounds vs pence). Flag it and keep it out of the means.
    for e in exits:
        if e["return_after_exit_to_now"] is not None and abs(e["return_after_exit_to_now"]) > 3:
            e["price_series_break"] = True
    for r in rows:
        if r["return_since_entry_close"] is not None and abs(r["return_since_entry_close"]) > 3:
            r["price_series_break"] = True
    rets = [r["return_since_entry_close"] for r in rows if r["return_since_entry_close"] is not None and not r.get("price_series_break")]
    exc = [r["return_since_entry_close"] - r["acwi_same_window"] for r in rows
           if r["return_since_entry_close"] is not None and r["acwi_same_window"] is not None and not r.get("price_series_break")]
    post = [e["return_after_exit_to_now"] - e["acwi_after_exit"] for e in exits
            if e["return_after_exit_to_now"] is not None and e["acwi_after_exit"] is not None
            and not e.get("price_series_break")]
    summ = {"metric_field": mfield, "n_picks": len(picks),
            "qualifiers_in_scan": len(allv), "scan_names_above_zero": sum(1 for v in allv if v > 0),
            "cutoff_metric_of_basket": cutoff, "names_tied_at_cutoff_in_scan": ties_at_cut,
            "distinct_metric_values_in_top60": distinct_top,
            "metric_values_at_or_above_0.95_in_scan": sum(1 for v in allv if v >= 0.949),
            "entry_date_counts": dict(sorted(collections.Counter(str(p.get("entry_date"))[:10] for p in picks).items())),
            "debate_grades_of_picks": dict(g), "picks_not_in_debate_universe": [r["symbol"] for r in rows if not r["debate"]["in_debate_universe"]],
            "picks_excluded_by_forensic_gate": [r["symbol"] for r in rows if r["debate"]["forensic_gate"] == "EXCLUDE"],
            "picks_rejected_by_numeric_gate": [r["symbol"] for r in rows if r["debate"]["numeric_gate"] in ("REJECT", "EXCLUDE_ELIGIBILITY")],
            "median_metric_of_picks": round(st.median(scanm), 4) if scanm else None,
            "median_debate_discount_pct_of_picks": round(st.median(disc), 1) if disc else None,
            "regime_seats_from_basket": [s for s in REG_SEATS if s in sets[key]],
            "value_seats_from_basket": [s for s in VAL_SEATS if s in sets[key]],
            "mean_return_since_entry": round(st.mean(rets), 4) if rets else None,
            "mean_excess_vs_acwi_since_entry": round(st.mean(exc), 4) if exc else None,
            "share_of_picks_beating_acwi": round(sum(1 for x in exc if x > 0) / len(exc), 2) if exc else None,
            "n_exits_2026_logged": len(exits),
            "exits_flagged_unpriced": sum(1 for e in exits if e.get("unpriced_exit")),
            "exits_with_exit_metric_zero": sum(1 for e in exits if e.get("exit_metric") in (0, 0.0)),
            "mean_excess_AFTER_exit_vs_acwi": round(st.mean(post), 4) if post else None,
            "tracking": {k: tr.get(k) for k in ("ytd_return", "realized_ytd", "tracking_start", "rebalance_count",
                                                "rebalances_before_reconstruction")},
            "nav_history": tr.get("nav_history"),
            "picks_file_header": {k: b.get(k) for k in ("average_mos", "ytd_return", "tracking_start", "rebalance_count")},
            "tracking_holdings_vs_picks_file": {
                "in_tracking_not_in_picks": sorted({h["symbol"] for h in tr.get("current_holdings", [])} - sets[key]),
                "in_picks_not_in_tracking": sorted(sets[key] - {h["symbol"] for h in tr.get("current_holdings", [])})}}
    json.dump({"basket": key, "summary": summ, "picks": rows, "rebalances_since_reconstruction": rebs,
               "all_exits_2026": exits, "recent_exits_in_picks_file": recent_exits,
               "tracking_current_holdings": tr.get("current_holdings")},
              open(OUT / f"{key}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    overview["baskets"][key] = {k: summ[k] for k in ("n_picks", "qualifiers_in_scan", "cutoff_metric_of_basket",
                                                     "names_tied_at_cutoff_in_scan", "debate_grades_of_picks",
                                                     "median_metric_of_picks", "median_debate_discount_pct_of_picks",
                                                     "regime_seats_from_basket", "value_seats_from_basket",
                                                     "mean_excess_vs_acwi_since_entry", "share_of_picks_beating_acwi",
                                                     "n_exits_2026_logged", "mean_excess_AFTER_exit_vs_acwi", "tracking")}
keys = list(sets)
overview["overlap_shared_names"] = {a: {b: len(sets[a] & sets[b]) for b in keys} for a in keys}
allnames = set().union(*sets.values())
cnt = collections.Counter(s for v in sets.values() for s in v)
overview["unique_names_across_baskets"] = len(allnames)
overview["names_by_number_of_baskets"] = dict(sorted(collections.Counter(cnt.values()).items()))
overview["seat_origin"] = {s: sorted(k for k in keys if s in sets[k]) for s in sorted(set(REG_SEATS) | set(VAL_SEATS))}
overview["debate_universe_size"] = len(REC)
overview["debate_universe_from_baskets"] = sum(1 for s in REC if s in allnames)
json.dump(overview, open(OUT / "_overview.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("packs written:", sorted(p.name for p in OUT.glob("*.json")))
print("unique names", len(allnames), "| by #baskets", overview["names_by_number_of_baskets"])
for k in keys:
    o = overview["baskets"][k]
    print(f"{k:22} picks={o['n_picks']:>2} qualifiers={o['qualifiers_in_scan']:>4} tied@cut={o['names_tied_at_cutoff_in_scan']:>3} "
          f"grades={o['debate_grades_of_picks']} excess_vs_ACWI={o['mean_excess_vs_acwi_since_entry']} "
          f"beat={o['share_of_picks_beating_acwi']} exits={o['n_exits_2026_logged']} after_exit_excess={o['mean_excess_AFTER_exit_vs_acwi']} "
          f"ytd={o['tracking'].get('ytd_return')} seats R{o['regime_seats_from_basket']} V{o['value_seats_from_basket']}")
print("seat origin:", overview["seat_origin"])
