#!/usr/bin/env python3
"""Basket 13 — Catalyst sleeve: append-only event-resolution tracker (the calibration loop).

Sidecar _basket13_tracker.json — deliberately NOT the rebalance/NAV trackers
(_update_apex_tracking / methodology_tracking): those chain a daily equal-weight NAV and
overwrite positions in place, which fights per-name resolution stamps. Catalyst positions
RESOLVE, they do not rebalance: every entry is stamped once at entry and later carries exactly
ONE resolution stamp; non-selections are recorded too (selection calibration needs the
counterfactuals). This is the loop that re-fits the • dials (entry edge thresholds 2.5/1.5,
lane tilt 0.12, lane priors, and the cap dials below) against realized outcomes — quarterly.

STAMP HONESTY RULES (2026-06-11 review):
  * entry_price = the LIVE price the CRO verified (parsed from its live check, or the
    structured live_price field on newer runs) — NEVER the dossier reference price. The
    expected metrics are live recomputes, so the bases must match or realized-vs-expected
    is incoherent. entry_price_source records which basis was used.
  * A CRO entry-limit condition is enforced at stamp time: live > limit -> the position is
    stamped PENDING_LIMIT (a resting limit order, not held; fills via the daily mark when
    the close trades through the limit). No fiction fills.
  * A hedge leg in the CRO conditions (e.g. "short 0.7720 CTAS per UNF") is recorded on the
    entry; the daily mark computes hedge-aware returns.
  * Driver re-tags (Director driver != board driver) are logged on the run record.
  * risk_to_floor_pct is COMPUTED and stored per entry, never quoted from the memo.
  * CLUSTER-CAP BASIS (pinned): <=40 weight-POINTS of NAV per super-cluster (i.e. 40% of
    NAV). Not "% of invested weight" — that basis is unstable: excluding one small seat
    shrinks the denominator and can flip unrelated clusters into breach. The review doc
    reports both bases. Pending entries count toward all caps as-if-filled.

Modes:
  python _basket13_inject.py <workflow_output.json> [--force] [--entry-date YYYY-MM-DD]
                             [--restamp] [--exclude SYM=reason ...]
  python _basket13_inject.py resolve SYMBOL --type FIRED_WIN --price 12.3 [--date YYYY-MM-DD] [--notes "..."]
  python _basket13_inject.py report

PAPER basket only — no orders are ever placed; expression/size are recorded for calibration.
"""
import json, os, re, sys, argparse, datetime, statistics

BASE = os.path.dirname(os.path.abspath(__file__))
TRK  = os.path.join(BASE, "_basket13_tracker.json")
CAND = os.path.join(BASE, "_basket13_candidates.json")

RES_TYPES = ["FIRED_WIN", "FIRED_LOSS", "SLIPPED", "THESIS_BROKEN", "EDGE_GONE", "EXPIRED"]

# ---- cap dials (•) — re-fit from realized outcomes (see `report`); NOT constants ----
MAX_PER_DRIVER     = 2
MAX_SUPER_PTS      = 40.0    # weight-POINTS of NAV per super-cluster (pinned basis — see header)
MIN_NAMES, MAX_NAMES = 8, 12
RISK_TO_FLOOR_PCT  = 1.5     # weight_pct * (live-floor)/live <= this, per ratio name
BINARY_PREMIUM_PCT = 2.0     # weight_pct <= this for a binary defined-risk structure
TOL = 1e-3                   # float tolerance on cap checks

HEADER = ("Basket 13 catalyst sleeve — append-only event-resolution tracker. Positions RESOLVE, "
          "they do not rebalance. Every entry must eventually carry exactly one resolution; "
          "non-selections are recorded for selection calibration. Entry prices are the CRO-verified "
          "LIVE prices (entry_price_source on each stamp); CRO entry limits are enforced at stamp "
          "time (PENDING_LIMIT, no fiction fills). The • dials (entry edge thresholds 2.5/1.5, lane "
          "tilt 0.12, lane priors, and the cap dials in _basket13_inject.py) are STARTING VALUES, "
          "re-fit QUARTERLY from the realized analytics emitted by `report` — not constants.")


def load_tracker():
    if os.path.exists(TRK):
        return json.load(open(TRK, encoding="utf-8"))
    return {"header": HEADER, "entries": [], "non_selections": [], "runs": [], "marks": []}


def save_tracker(t):
    t["header"] = HEADER
    json.dump(t, open(TRK, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def open_entry(t, sym):
    """Most-recent OPEN (unresolved) entry for sym, or None."""
    for e in reversed(t["entries"]):
        if e["symbol"] == sym and not e.get("resolution"):
            return e
    return None


# ------------------------------------------------------- CRO-text deterministic parsers
def cro_live_price(v, sym):
    """The live price the CRO verified. Prefer the structured field (newer runs); else parse
    the live_edge_check text: symbol-prefixed 'SYM live $X' first (disambiguates multi-leg
    checks like UNF/CTAS), then the leading 'Live $X'."""
    if isinstance(v.get("live_price"), (int, float)) and v["live_price"] > 0:
        return float(v["live_price"]), "cro_structured"
    txt = v.get("live_edge_check") or ""
    m = re.search(rf"{re.escape(sym)}\s+live\s+(?:\$|EUR\s*)?([\d,]+(?:\.\d+)?)", txt, re.I)
    if not m:
        m = re.search(r"\blive\s+(?:\$|EUR\s*)?([\d,]+(?:\.\d+)?)", txt, re.I)
    if m:
        return float(m.group(1).replace(",", "")), "cro_live_check"
    return None, None


def entry_limit_of(conditions):
    """Parse a CRO entry-limit condition ('enter UNF <= ~$267', 'Entry limit <= $4.80')."""
    for c in conditions or []:
        m = re.search(r"(?:enter|entry)[^<>]*?<=\s*~?\$?\s*([\d]+(?:\.\d+)?)", c, re.I)
        if m:
            return float(m.group(1))
    return None


def hedge_of(v):
    """Parse a hedge leg from CRO conditions ('short 0.7720 CTAS per ...') + its reference
    price from the live check ('CTAS live $179.87')."""
    for c in v.get("conditions") or []:
        m = re.search(r"short\s+([\d.]+)\s+([A-Z]{1,6})\s+per", c, re.I)
        if m:
            ratio, hsym = float(m.group(1)), m.group(2).upper()
            pm = re.search(rf"{hsym}\s+live\s+\$?([\d,]+(?:\.\d+)?)", v.get("live_edge_check") or "", re.I)
            return {"symbol": hsym, "ratio": -ratio,
                    "price_at_entry": float(pm.group(1).replace(",", "")) if pm else None,
                    "basis": c}
    return None


def rtf_pct(weight, live, floor):
    """Computed risk-to-floor: % of NAV lost if the name trades to its floor."""
    if isinstance(live, (int, float)) and isinstance(floor, (int, float)) and live > 0 and live > floor:
        return round(weight * (live - floor) / live, 3)
    return None


# --------------------------------------------------------------- cap validation
def validate(picks, bysym, live_px=None):
    """Deterministic hard-cap assertion on the Director output. Returns a list of violations.
    live_px: {SYM: stamped/limit price} — caps are checked at the price the book actually
    carries. Pending (resting-limit) picks count toward every cap as-if-filled."""
    live_px = live_px or {}
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
        if w > MAX_SUPER_PTS + TOL:
            v.append(f"SUPER_CLUSTER {sc}: {w:.1f} NAV weight-points > {MAX_SUPER_PTS}")
    for p in picks:
        c = bysym.get(p["symbol"], {})
        w = p.get("weight_pct") or 0
        exp = (p.get("expression") or {}).get("type")
        vm, staging = c.get("valuation_method"), c.get("staging")
        live = live_px.get(p["symbol"]) or c.get("live_price")
        floor = c.get("downside_floor")
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
def inject(path, force=False, entry_date=None, restamp=False, excludes=None):
    excludes = dict(excludes or [])
    out = json.load(open(path, encoding="utf-8"))
    res = out.get("result", out)
    director = res.get("director") or res          # tolerate {director:{...}} or the director obj itself
    picks_all = director.get("picks") or []
    passed = list(director.get("passed") or [])
    memo = director.get("memo", "")
    cro_by = {v["symbol"]: v for v in (res.get("cro") or []) if v.get("symbol")}
    cands = json.load(open(CAND, encoding="utf-8"))["candidates"]
    bysym = {c["symbol"]: c for c in cands}
    stamp_date = entry_date or datetime.date.today().isoformat()

    # explicit stamp-time exclusions (e.g. an unverifiable blocking condition) -> counterfactuals
    picks, excluded = [], []
    for p in picks_all:
        if p["symbol"] in excludes:
            excluded.append(p)
            passed.append({"symbol": p["symbol"],
                           "passed_because": f"EXCLUDED AT STAMP: {excludes[p['symbol']]}"})
        else:
            picks.append(p)

    # the price the book actually carries per pick: CRO live, capped at the entry limit when pending
    live_map, src_map, pend_map, hedge_map = {}, {}, {}, {}
    for p in picks:
        sym = p["symbol"]
        v = cro_by.get(sym) or {}
        live, src = cro_live_price(v, sym)
        if live is None:
            live, src = bysym.get(sym, {}).get("live_price"), "board_snapshot"
        limit = entry_limit_of(v.get("conditions"))
        if limit is not None and isinstance(live, (int, float)) and live > limit + TOL:
            pend_map[sym] = limit                  # resting limit — not held at stamp
            live_map[sym] = limit                  # caps checked as-if-filled at the limit
        else:
            live_map[sym] = live
        src_map[sym] = src
        h = hedge_of(v)
        if h:
            hedge_map[sym] = h

    # driver re-tags (Director vs board) — logged, never silent
    retags = [{"symbol": p["symbol"], "from": bysym.get(p["symbol"], {}).get("resolution_driver"),
               "to": p.get("resolution_driver"), "authority": "Director (CRO-conditioned)"}
              for p in picks
              if p.get("resolution_driver") and bysym.get(p["symbol"], {}).get("resolution_driver")
              and p["resolution_driver"] != bysym[p["symbol"]]["resolution_driver"]]

    # COMBINED-BOOK caps: existing UNRESOLVED entries are LOCKED (run to resolution) and consume
    # headroom. Validate held + new together; never re-pick a locked name. (restamp = fresh book.)
    held = [] if restamp else [e for e in load_tracker().get("entries", []) if not e.get("resolution")]
    held_syms = {e["symbol"] for e in held}
    picks = [p for p in picks if p["symbol"] not in held_syms]
    held_pseudo = [{"symbol": e["symbol"], "weight_pct": e.get("weight_pct"),
                    "resolution_driver": e.get("resolution_driver"), "super_cluster": e.get("super_cluster"),
                    "expression": e.get("expression") or {}} for e in held]
    bysym_v, live_v = dict(bysym), dict(live_map)
    for e in held:                          # held names may be absent from candidates (--exclude-held)
        bysym_v[e["symbol"]] = {"valuation_method": e.get("valuation_method"), "staging": e.get("staging"),
                                "downside_floor": e.get("downside_floor"), "super_cluster": e.get("super_cluster"),
                                "live_price": e.get("entry_price")}
        live_v[e["symbol"]] = e.get("entry_price") or e.get("limit_price")

    viol = validate(held_pseudo + picks, bysym_v, live_px=live_v)
    if viol:
        print("CAP VALIDATION FAILED — basket NOT stamped:")
        for x in viol:
            print("  X " + x)
        if not force:
            sys.exit(1)
        print("  (--force: stamping anyway)")

    t = load_tracker()
    if restamp:
        t["entries"], t["non_selections"], t["runs"] = [], [], []
        t["marks"] = [{"date": stamp_date, "nav": 100.0, "basket_ret_pct": 0.0, "seats": {},
                       "note": "inception — entries stamped at CRO-verified live prices"}]

    added, skipped, pending = [], [], []
    for p in picks:
        sym = p["symbol"]
        c = bysym.get(sym, {})
        if open_entry(t, sym):
            skipped.append(sym)
            continue
        is_pend = sym in pend_map
        ep = None if is_pend else live_map.get(sym)
        entry = {
            "symbol": sym, "status": "PENDING_LIMIT" if is_pend else "OPEN",
            "order_date": stamp_date,
            "entry_date": None if is_pend else stamp_date,
            "entry_price": ep,
            "entry_price_source": src_map.get(sym),
            "limit_price": pend_map.get(sym),
            "weight_pct": p.get("weight_pct"),
            "risk_to_floor_pct": rtf_pct(p.get("weight_pct") or 0, live_map.get(sym), c.get("downside_floor"))
                                 if (c.get("valuation_method") != "binary_prob"
                                     or (p.get("expression") or {}).get("type") == "equity") else None,
            "score": c.get("score"), "board_priority": c.get("board_priority"),
            "edge_grade": c.get("edge_grade"), "computed_rr": c.get("computed_rr"),
            "ev_pct": c.get("ev_pct"), "lane_canon": c.get("lane_canon"),
            "resolution_driver": p.get("resolution_driver") or c.get("resolution_driver"),
            "super_cluster": p.get("super_cluster") or c.get("super_cluster"),
            "valuation_method": c.get("valuation_method"),
            "downside_floor": c.get("downside_floor"), "fair_value_target": c.get("fair_value_target"),
            "dated_milestone": c.get("dated_milestone"), "staging": bool(c.get("staging")),
            "expression": p.get("expression") or {},
            "hedge": hedge_map.get(sym),
            "expected_rr": p.get("expected_rr"), "expected_ev": p.get("expected_ev"),
            "entry_rationale": p.get("entry_rationale", ""),
            "invalidation": p.get("invalidation", ""), "review_trigger": p.get("review_trigger", ""),
            "cro_verdict": (cro_by.get(sym) or {}).get("verdict", ""),
            # full CRO four-surface detail stored on the entry -> the review doc is self-contained
            # across runs (each re-debate overwrites _basket13_out.json; the held seats keep theirs).
            "cro_detail": {k: (cro_by.get(sym) or {}).get(k) for k in
                           ("live_edge_check", "tradeability_note", "window_note", "driver_confirmed", "conditions")},
            "resolution": None,
        }
        t["entries"].append(entry)
        (pending if is_pend else added).append(sym)

    for p in passed:                                # counterfactuals (incl. stamp-time exclusions)
        c = bysym.get(p["symbol"], {})
        t["non_selections"].append({
            "symbol": p["symbol"], "date": stamp_date, "passed_because": p.get("passed_because", ""),
            "score": c.get("score"), "edge_grade": c.get("edge_grade"),
            "lane_canon": c.get("lane_canon"), "resolution_driver": c.get("resolution_driver"),
        })
    t["runs"].append({"run_date": stamp_date, "stamped_at": datetime.date.today().isoformat(),
                      "restamp": bool(restamp),
                      "n_picks": len(picks), "n_passed": len(passed), "n_added": len(added),
                      "n_pending": len(pending), "n_excluded_at_stamp": len(excluded),
                      "n_skipped_open": len(skipped), "cap_violations": len(viol),
                      "retags": retags, "memo": memo})
    save_tracker(t)
    print(f"INJECTED {len(added)} held {added}"
          + (f" + {len(pending)} PENDING_LIMIT {pending}" if pending else "")
          + (f" + {len(excluded)} excluded-at-stamp {[p['symbol'] for p in excluded]}" if excluded else "")
          + (f"; skipped (already open): {skipped}" if skipped else ""))
    if retags:
        print(f"  re-tags logged: " + "; ".join(f"{r['symbol']} {r['from']} -> {r['to']}" for r in retags))
    print(f"  + {len(passed)} non-selections recorded; caps {'OK' if not viol else 'FORCED'}  -> {TRK}")


# ---------------------------------------------------------------------- resolve
def resolve(symbol, rtype, price, date=None, notes=""):
    t = load_tracker()
    e = open_entry(t, symbol)
    if e is None:
        print(f"No OPEN entry for {symbol}.")
        sys.exit(1)
    if e.get("status") == "PENDING_LIMIT":
        rdate = date or datetime.date.today().isoformat()
        e["resolution"] = {"resolution_date": rdate, "resolution_type": rtype, "exit_price": price,
                           "realized_return_pct": None, "realized_rr": None, "days_held": 0,
                           "catalyst_fired": False, "notes": f"(never filled — resting limit cancelled) {notes}"}
        save_tracker(t)
        print(f"CANCELLED pending {symbol}: {rtype} (never filled)  -> {TRK}")
        return
    rdate = date or datetime.date.today().isoformat()
    ep, fl = e.get("entry_price"), e.get("downside_floor")
    ret = (price / ep - 1) if (ep and price is not None) else None
    h = e.get("hedge")
    if h and h.get("price_at_entry") and notes:
        pass  # hedge-leg exit P&L must be supplied in notes; underlying ret stays the headline
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
    op = [e for e in entries if not e.get("resolution") and e.get("status") != "PENDING_LIMIT"]
    pend = [e for e in entries if not e.get("resolution") and e.get("status") == "PENDING_LIMIT"]
    print(f"BASKET 13 tracker — {len(entries)} entries ({len(res)} resolved, {len(op)} open, {len(pend)} pending-limit), "
          f"{len(t['non_selections'])} non-selections, {len(t.get('runs', []))} runs, {len(t.get('marks', []))} marks")
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
        ap.add_argument("--entry-date", default=None, dest="entry_date")
        ap.add_argument("--restamp", action="store_true",
                        help="rebuild the inaugural record (clears entries/non-selections/runs/marks, seeds NAV=100)")
        ap.add_argument("--exclude", action="append", default=[],
                        help="SYM=reason — drop a Director pick to non-selections with the logged reason")
        a = ap.parse_args(sys.argv[1:])
        exc = []
        for x in a.exclude:
            sym, _, reason = x.partition("=")
            exc.append((sym.strip(), reason.strip() or "excluded at stamp"))
        inject(a.path, a.force, a.entry_date, a.restamp, exc)


if __name__ == "__main__":
    main()
