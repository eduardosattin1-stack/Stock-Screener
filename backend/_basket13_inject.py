#!/usr/bin/env python3
"""Basket 13 — Catalyst sleeve: append-only event-resolution tracker (the calibration loop).

Sidecar _basket13_tracker.json — deliberately NOT the rebalance/NAV trackers
(_update_apex_tracking / methodology_tracking): those chain a daily equal-weight NAV and
overwrite positions in place, which fights per-name resolution stamps. Catalyst positions
RESOLVE, they do not rebalance: every entry is stamped once at entry and later carries exactly
ONE resolution stamp; non-selections are recorded too (selection calibration needs the
counterfactuals). This is the loop that re-fits the • dials (entry edge thresholds 2.5/1.5,
lane tilt 0.12, lane priors, and the cap dials below) against realized outcomes — quarterly.

Modes:
  python _basket13_inject.py <director_workflow_output.json> [--force]   # validate caps, append entries + non-selections
  python _basket13_inject.py resolve SYMBOL --type FIRED_WIN --price 12.3 [--date YYYY-MM-DD] [--notes "..."]
  python _basket13_inject.py report                                      # hit-rate + realized-vs-expected R:R by lane/driver/edge + slippage

PAPER basket only — no orders are ever placed; expression/size are recorded for calibration.
"""
import json, os, sys, argparse, datetime, statistics

BASE = os.path.dirname(os.path.abspath(__file__))
TRK  = os.path.join(BASE, "_basket13_tracker.json")
CAND = os.path.join(BASE, "_basket13_candidates.json")

RES_TYPES = ["FIRED_WIN", "FIRED_LOSS", "SLIPPED", "THESIS_BROKEN", "EDGE_GONE", "EXPIRED"]

# ---- cap dials (•) — re-fit from realized outcomes (see `report`); NOT constants ----
MAX_PER_DRIVER     = 2
MAX_SUPER_PCT      = 40.0
MIN_NAMES, MAX_NAMES = 8, 12
RISK_TO_FLOOR_PCT  = 1.5     # weight_pct * (live-floor)/live <= this, per ratio name
BINARY_PREMIUM_PCT = 2.0     # weight_pct <= this for a binary defined-risk structure
TOL = 1e-3                   # float tolerance on cap checks

HEADER = ("Basket 13 catalyst sleeve — append-only event-resolution tracker. Positions RESOLVE, "
          "they do not rebalance. Every entry must eventually carry exactly one resolution; "
          "non-selections are recorded for selection calibration. The • dials (entry edge thresholds "
          "2.5/1.5, lane tilt 0.12, lane priors, and the cap dials in _basket13_inject.py) are STARTING "
          "VALUES, re-fit QUARTERLY from the realized hit-rate / realized-vs-expected R:R / slippage "
          "analytics emitted by `report` — not constants.")


def load_tracker():
    if os.path.exists(TRK):
        return json.load(open(TRK, encoding="utf-8"))
    return {"header": HEADER, "entries": [], "non_selections": [], "runs": []}


def save_tracker(t):
    t["header"] = HEADER
    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def open_entry(t, sym):
    """Most-recent OPEN (unresolved) entry for sym, or None."""
    for e in reversed(t["entries"]):
        if e["symbol"] == sym and not e.get("resolution"):
            return e
    return None


# --------------------------------------------------------------- cap validation
def validate(picks, bysym):
    """Deterministic hard-cap assertion on the Director output. Returns a list of violations."""
    v, n = [], len(picks)
    if not (MIN_NAMES <= n <= MAX_NAMES):
        v.append(f"COUNT {n} outside [{MIN_NAMES},{MAX_NAMES}]")
    bydrv = {}
    for p in picks:
        bydrv.setdefault(p.get("resolution_driver"), []).append(p["symbol"])
    for drv, syms in bydrv.items():
        if len(syms) > MAX_PER_DRIVER:
            v.append(f"DRIVER {drv}: {len(syms)} names ({','.join(syms)}) > {MAX_PER_DRIVER}")
    bysc = {}
    for p in picks:
        sc = p.get("super_cluster") or bysym.get(p["symbol"], {}).get("super_cluster")
        bysc[sc] = bysc.get(sc, 0.0) + (p.get("weight_pct") or 0)
    for sc, w in bysc.items():
        if w > MAX_SUPER_PCT + TOL:
            v.append(f"SUPER_CLUSTER {sc}: {w:.1f}% > {MAX_SUPER_PCT}%")
    for p in picks:
        c = bysym.get(p["symbol"], {})
        w = p.get("weight_pct") or 0
        exp = (p.get("expression") or {}).get("type")
        vm, staging = c.get("valuation_method"), c.get("staging")
        live, floor = c.get("live_price"), c.get("downside_floor")
        if vm == "binary_prob" and not staging:
            if exp not in ("debit_spread", "defined_risk_option"):
                v.append(f"{p['symbol']} binary expression '{exp}' not defined-risk")
            if w > BINARY_PREMIUM_PCT + TOL:
                v.append(f"{p['symbol']} binary weight {w:.1f}% > {BINARY_PREMIUM_PCT}% premium-at-risk")
        elif vm != "binary_prob" and isinstance(live, (int, float)) and isinstance(floor, (int, float)) and live > 0 and live > floor:
            rtf = w * (live - floor) / live
            if rtf > RISK_TO_FLOOR_PCT + TOL:
                v.append(f"{p['symbol']} risk-to-floor {rtf:.2f}% > {RISK_TO_FLOOR_PCT}% (w={w}, live={live}, floor={floor})")
        if staging:
            half = 0.5 * (100.0 / max(n, 1))
            if exp != "equity":
                v.append(f"{p['symbol']} STAGING must be equity, got '{exp}'")
            if w > half + 0.5:
                v.append(f"{p['symbol']} STAGING weight {w:.1f}% > half-normal {half:.1f}%")
    return v


# ----------------------------------------------------------------------- inject
def inject(path, force=False):
    out = json.load(open(path, encoding="utf-8"))
    res = out.get("result", out)
    director = res.get("director") or res          # tolerate {director:{...}} or the director obj itself
    picks = director.get("picks") or []
    passed = director.get("passed") or []
    memo = director.get("memo", "")
    cro_by = {v["symbol"]: v for v in (res.get("cro") or []) if v.get("symbol")}
    cands = json.load(open(CAND, encoding="utf-8"))["candidates"]
    bysym = {c["symbol"]: c for c in cands}

    viol = validate(picks, bysym)
    if viol:
        print("CAP VALIDATION FAILED — basket NOT stamped:")
        for x in viol:
            print("  X " + x)
        if not force:
            sys.exit(1)
        print("  (--force: stamping anyway)")

    t = load_tracker()
    today = datetime.date.today().isoformat()
    added, skipped = [], []
    for p in picks:
        sym = p["symbol"]
        c = bysym.get(sym, {})
        if open_entry(t, sym):
            skipped.append(sym)
            continue
        t["entries"].append({
            "symbol": sym, "entry_date": today,
            "entry_price": c.get("live_price"), "weight_pct": p.get("weight_pct"),
            "score": c.get("score"), "board_priority": c.get("board_priority"),
            "edge_grade": c.get("edge_grade"), "computed_rr": c.get("computed_rr"),
            "ev_pct": c.get("ev_pct"), "lane_canon": c.get("lane_canon"),
            "resolution_driver": p.get("resolution_driver") or c.get("resolution_driver"),
            "super_cluster": p.get("super_cluster") or c.get("super_cluster"),
            "valuation_method": c.get("valuation_method"),
            "downside_floor": c.get("downside_floor"), "fair_value_target": c.get("fair_value_target"),
            "dated_milestone": c.get("dated_milestone"), "staging": bool(c.get("staging")),
            "expression": p.get("expression") or {},
            "expected_rr": p.get("expected_rr"), "expected_ev": p.get("expected_ev"),
            "invalidation": p.get("invalidation", ""), "review_trigger": p.get("review_trigger", ""),
            "cro_verdict": (cro_by.get(sym) or {}).get("verdict", ""),
            "resolution": None,
        })
        added.append(sym)

    for p in passed:                                # counterfactuals
        c = bysym.get(p["symbol"], {})
        t["non_selections"].append({
            "symbol": p["symbol"], "date": today, "passed_because": p.get("passed_because", ""),
            "score": c.get("score"), "edge_grade": c.get("edge_grade"),
            "lane_canon": c.get("lane_canon"), "resolution_driver": c.get("resolution_driver"),
        })
    t["runs"].append({"run_date": today, "n_picks": len(picks), "n_passed": len(passed),
                      "n_added": len(added), "n_skipped_open": len(skipped),
                      "cap_violations": len(viol), "memo": memo})
    save_tracker(t)
    print(f"INJECTED {len(added)} entries {added}" + (f"; skipped (already open): {skipped}" if skipped else ""))
    print(f"  + {len(passed)} non-selections recorded; caps {'OK' if not viol else 'FORCED'}  -> {TRK}")


# ---------------------------------------------------------------------- resolve
def resolve(symbol, rtype, price, date=None, notes=""):
    t = load_tracker()
    e = open_entry(t, symbol)
    if e is None:
        print(f"No OPEN entry for {symbol}.")
        sys.exit(1)
    rdate = date or datetime.date.today().isoformat()
    ep, fl = e.get("entry_price"), e.get("downside_floor")
    ret = (price / ep - 1) if (ep and price is not None) else None
    rr = None
    if ret is not None and isinstance(fl, (int, float)) and ep and ep > fl:
        rr = round(ret / ((ep - fl) / ep), 3)
    try:
        days = (datetime.date.fromisoformat(rdate) - datetime.date.fromisoformat(e["entry_date"])).days
    except Exception:
        days = None
    fired = rtype in ("FIRED_WIN", "FIRED_LOSS", "THESIS_BROKEN")
    e["resolution"] = {"resolution_date": rdate, "resolution_type": rtype, "exit_price": price,
                       "realized_return_pct": round(ret, 4) if ret is not None else None,
                       "realized_rr": rr, "days_held": days, "catalyst_fired": fired, "notes": notes}
    save_tracker(t)
    tail = f"  (ret={ret:+.1%} rr={rr} days={days})" if ret is not None else ""
    print(f"RESOLVED {symbol}: {rtype} @ {price}{tail}  -> {TRK}")


# ----------------------------------------------------------------------- report
def _band(es, key):
    groups = {}
    for e in es:
        groups.setdefault(key(e), []).append(e)
    for g, gs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        wins = sum(1 for e in gs if e["resolution"]["resolution_type"] == "FIRED_WIN")
        decided = sum(1 for e in gs if e["resolution"]["resolution_type"] in ("FIRED_WIN", "FIRED_LOSS"))
        rr = [e["resolution"]["realized_rr"] for e in gs if e["resolution"].get("realized_rr") is not None]
        exp = [e["expected_rr"] for e in gs if isinstance(e.get("expected_rr"), (int, float))]
        hit = f"{wins}/{decided}" if decided else "0/0"
        mrr = f"{statistics.mean(rr):+.2f}" if rr else "—"
        mexp = f"{statistics.mean(exp):+.2f}" if exp else "—"
        print(f"    {str(g):24} n={len(gs):2}  hit(win/decided)={hit:6}  realized_rr={mrr:6}  vs expected={mexp}")


def report():
    t = load_tracker()
    entries = t["entries"]
    res = [e for e in entries if e.get("resolution")]
    op = [e for e in entries if not e.get("resolution")]
    print(f"BASKET 13 tracker — {len(entries)} entries ({len(res)} resolved, {len(op)} open), "
          f"{len(t['non_selections'])} non-selections, {len(t.get('runs', []))} runs")
    if not res:
        print("  no resolved positions yet — analytics begin once positions resolve.")
        return
    print("\n  by lane:");   _band(res, lambda e: e.get("lane_canon"))
    print("\n  by driver:"); _band(res, lambda e: e.get("resolution_driver"))
    print("\n  by edge band:"); _band(res, lambda e: e.get("edge_grade"))
    slip = []
    for e in res:
        dm, rd = e.get("dated_milestone"), e["resolution"]["resolution_date"]
        try:
            if dm:
                slip.append((datetime.date.fromisoformat(rd) - datetime.date.fromisoformat(dm[:10])).days)
        except Exception:
            pass
    sl_ct = sum(1 for e in res if e["resolution"]["resolution_type"] == "SLIPPED")
    if slip:
        print(f"\n  slippage (resolution - milestone date): mean {statistics.mean(slip):+.0f}d, "
              f"median {statistics.median(slip):+.0f}d, n={len(slip)}; SLIPPED resolutions={sl_ct}")
    print("\n  -> re-fit the • edge thresholds (2.5/1.5), tilt (0.12), and lane priors from the above (quarterly).")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "report":
        report()
    elif mode == "resolve":
        ap = argparse.ArgumentParser(prog="_basket13_inject.py resolve")
        ap.add_argument("symbol")
        ap.add_argument("--type", required=True, choices=RES_TYPES, dest="rtype")
        ap.add_argument("--price", type=float, required=True)
        ap.add_argument("--date", default=None)
        ap.add_argument("--notes", default="")
        a = ap.parse_args(sys.argv[2:])
        resolve(a.symbol, a.rtype, a.price, a.date, a.notes)
    else:
        ap = argparse.ArgumentParser(prog="_basket13_inject.py")
        ap.add_argument("path")
        ap.add_argument("--force", action="store_true")
        a = ap.parse_args(sys.argv[1:])
        inject(a.path, a.force)


if __name__ == "__main__":
    main()
