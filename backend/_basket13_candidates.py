#!/usr/bin/env python3
"""Basket 13 — Catalyst sleeve: universe handoff from Catalyst Watch.

Reads the enriched Catalyst Watch deliverable (catalyst_candidates_231.json) and emits
_basket13_candidates.json — the entry + staging pool the basket-13 catalyst debate
(_basket13_gen.py) attacks. NO scoring here; a pure filter on the native enriched fields.
`score`/`board_priority` are carried through untouched.

Two buckets:
  ENTRY   : tier==ACTIVE, edge_grade in {H,M}, no blocking edge_flag, and a dated milestone
            (valuation.expected_close_date) within MILESTONE_WINDOW_MONTHS.
  STAGING : tier==WATCH with edge_grade==H  OR  (lane_priority<=STAGING_LANE_PRIORITY AND
            edge_grade in {H,M}). The soft-dated forced-sellers/spins (MGNI/PUBM class) that
            would otherwise die in WATCH. Marked staging:true -> equity-only, half-weight cap
            (enforced downstream by the Director; no options on an undated catalyst).

NOTE on the milestone: the board has no discrete `dated_milestone` field; the only structured
date is `valuation.expected_close_date`. ACTIVE names with no such date ("undated") or dated
outside the window are EXCLUDED from entries and reported (never silently dropped).

All `•` values are STARTING DIALS, re-fit from _basket13_tracker.json realized outcomes
(see `_basket13_inject.py report`) — not constants.

Usage: python _basket13_candidates.py
"""
import json, os, datetime, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
SRC  = os.path.join(ROOT, "catalyst_candidates_231.json")
OUT  = os.path.join(BASE, "_basket13_candidates.json")
TRK  = os.path.join(BASE, "_basket13_tracker.json")

# ---- dials (•) — re-fit from realized outcomes, not constants ----
MILESTONE_WINDOW_MONTHS = 6        # • ACTIVE entries need a dated milestone within this
EDGE_OK   = {"H", "M"}             # • acceptable edge grades
BLOCKING  = {"QUARANTINED", "NO_UPSIDE", "TRADING_THROUGH_TERMS",
             "FLOOR_GE_LIVE", "NO_BREAK_DOWNSIDE"}   # hard blockers (THIN/TINY_FLOOR are soft caps)
STAGING_LANE_PRIORITY = 2          # • forced_seller(1)/spinoff(2) reach staging at edge>=M
TARGET_MAX = 30                    # • if the pool exceeds this, tighten to H-edge ACTIVE + staging

# native enriched fields carried through verbatim (+ derived score/live_price/milestone/staging)
CARRY = ["symbol", "company_name", "board_priority", "tier", "lane_canon", "lane_priority",
         "resolution_driver", "edge_grade", "computed_rr", "ev_pct", "payoff", "win_prob",
         "valuation_method", "fair_value_target", "downside_floor", "instrument", "edge_flags"]

# resolution_driver -> super-cluster rollup (mirrors _post_board.SUPER; default Idiosyncratic).
# The Director enforces a max %-weight per super-cluster against these three.
SUPER = {
    "FDA_approval_decision": "FDA/biotech", "FDA_clinical_readout": "FDA/biotech",
    "US_antitrust": "Deal-completion", "US_sector_regulator": "Deal-completion",
    "CFIUS_FDI": "Deal-completion", "Foreign_regulator": "Deal-completion",
    "Deal_close_generic": "Deal-completion", "Shareholder_vote": "Deal-completion",
}
def super_cluster_of(driver):
    return SUPER.get(driver, "Idiosyncratic")


def milestone_of(r):
    """Dated milestone = valuation.expected_close_date (the only structured date on the board).
    Returns (iso_str|None, days_from_today|None)."""
    iso = (r.get("valuation") or {}).get("expected_close_date") or None
    if not iso:
        return None, None
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return iso, None
    return iso, (d - datetime.date.today()).days


def live_price_of(r):
    for k in ("live_price", "price", "reference_price"):
        p = r.get(k)
        if isinstance(p, (int, float)) and p > 0:
            return float(p)
    return None


def main(exclude_held=False):
    board = json.load(open(SRC, encoding="utf-8"))["candidates"]
    window_days = round(MILESTONE_WINDOW_MONTHS * 30.4)
    entries, staging, excluded = [], [], []

    # "holds run to resolution": drop names already in the book (any UNRESOLVED entry) so a
    # re-debate only considers names NOT currently held/pending.
    held = set()
    if exclude_held and os.path.exists(TRK):
        held = {str(e["symbol"]).upper() for e in json.load(open(TRK, encoding="utf-8")).get("entries", [])
                if not e.get("resolution")}

    for r in board:
        if str(r.get("symbol", "")).upper() in held:
            continue
        tier = r.get("tier")
        edge = r.get("edge_grade")
        flags = set(r.get("edge_flags") or [])
        blocked = flags & BLOCKING
        lane_pri = r.get("lane_priority") or 9
        iso, days = milestone_of(r)
        lp = live_price_of(r)

        def rec(staging_flag):
            d = {k: r.get(k) for k in CARRY}
            d["score"] = r.get("adjusted_loeb_score")
            d["live_price"] = lp
            d["dated_milestone"] = iso
            d["days_to_milestone"] = days
            d["valuation_asof"] = (r.get("valuation") or {}).get("valuation_asof")
            d["super_cluster"] = super_cluster_of(r.get("resolution_driver"))
            d["staging"] = staging_flag
            return d

        # ENTRY: ACTIVE, good edge, unblocked, dated within the forward window
        if tier == "ACTIVE" and edge in EDGE_OK and not blocked:
            if days is not None and 0 <= days <= window_days:
                entries.append(rec(False))
            else:
                reason = "undated" if days is None else ("past" if days < 0 else ">window")
                excluded.append((r.get("symbol"), iso, days, reason))
            continue

        # STAGING: WATCH, soft-dated forced-seller/spin or H-edge, unblocked
        if tier == "WATCH" and not blocked and (
                edge == "H" or (lane_pri <= STAGING_LANE_PRIORITY and edge in EDGE_OK)):
            staging.append(rec(True))

    # tighten if oversized: keep only H-edge ACTIVE entries (+ all staging)
    tightened = False
    if len(entries) + len(staging) > TARGET_MAX:
        entries = [c for c in entries if c["edge_grade"] == "H"]
        tightened = True
    cands = entries + staging

    out = {"generated": datetime.date.today().isoformat(), "source": os.path.basename(SRC),
           "count": len(cands), "entry_count": len(entries), "staging_count": len(staging),
           "milestone_window_months": MILESTONE_WINDOW_MONTHS, "tightened": tightened,
           "candidates": cands}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    print(f"BASKET13 candidates: {len(cands)}  (entry={len(entries)}, staging={len(staging)})"
          + ("  [TIGHTENED -> H-edge ACTIVE + staging]" if tightened else ""))
    print("  entries : " + ", ".join(
        f"{c['symbol']}({c['edge_grade']},{c['lane_canon']},{c['days_to_milestone']}d)" for c in entries))
    print("  staging : " + ", ".join(
        f"{c['symbol']}({c['edge_grade']},{c['lane_canon']})" for c in staging))
    for reason in (">window", "undated", "past"):
        names = [f"{s}({iso},{d}d)" if d is not None else f"{s}({iso})"
                 for s, iso, d, rr in excluded if rr == reason]
        if names:
            print(f"  excluded ACTIVE [{reason}]: {', '.join(names)}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-held", action="store_true",
                    help="drop names with an open/pending tracker entry (new-candidates-only re-debate)")
    a = ap.parse_args()
    main(exclude_held=a.exclude_held)
