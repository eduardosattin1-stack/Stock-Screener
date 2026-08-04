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
import json, os, datetime, argparse, re

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


# --- prose-date fallback (2026-07-21) ---------------------------------------
# BUG this fixes: `valuation.expected_close_date` is the board's ONLY structured date,
# and it holds M&A CLOSE dates — FDA catalysts (PDUFA/AdCom/readout) never populate it,
# their dates live only in the bloom_catalysts/analysis PROSE. So hard-dated FDA binaries
# (CAPR: AdCom Jul-29 + PDUFA Aug-22) were bucketed "undated" and dropped before the debate.
# 82 ACTIVE board names had a null expected_close_date but a dated event in prose.
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_CATALYST_KW = re.compile(
    r"PDUFA|AdCom|advisory committee|action date|readout|topline|CHMP|outside date|"
    r"decision date|approval decision|target action", re.I)
_DATE_MDY = re.compile(r"\b([A-Za-z]{3,9})\.?[\s-](\d{1,2})[,\s-]+(20\d\d)\b")  # "August 22, 2026" / "Nov-22-2026"
_DATE_ISO = re.compile(r"\b(20\d\d)-(\d{2})-(\d{2})\b")                       # "2026-08-22"

def _month_no(name):
    """Full-name lookup, then unambiguous-prefix fallback (nov→november, sept→september).
    Fixes the 2026-08-04 SVRA case: 'PDUFA reset to Nov-22-2026' — a HARD date — was
    bucketed 'undated' because _MONTHS only held full names. Quarter/month-only prose
    ('Q4-2026', 'January 2027') still never parses: that exclusion is policy, not a bug."""
    s = (name or "").lower().rstrip(".")
    if s in _MONTHS:
        return _MONTHS[s]
    hits = [v for k, v in _MONTHS.items() if len(s) >= 3 and k.startswith(s)]
    return hits[0] if len(hits) == 1 else None

def _prose_milestone(r, today):
    """Earliest FUTURE catalyst date parsed from board prose, used ONLY when the structured
    expected_close_date is null. Conservative: a date counts only if it sits in the SAME
    keyword-bearing segment as a catalyst keyword (so an unrelated date — a filing date, a
    52-week-low date — is not mistaken for the milestone). Returns (iso, days, snippet)."""
    bc = r.get("bloom_catalysts") or {}
    texts = []
    for v in bc.values():
        if isinstance(v, dict):
            texts += [str(v.get("description") or ""), str(v.get("evidence") or "")]
    texts += [str(r.get("analysis_summary") or ""),
              str((r.get("valuation") or {}).get("valuation_basis") or "")]
    found = []                                        # (date, snippet)
    for t in texts:
        for seg in re.split(r"[;.]", t):
            if not _CATALYST_KW.search(seg):
                continue
            for m in _DATE_MDY.finditer(seg):
                mon = _month_no(m.group(1))
                if not mon:
                    continue
                try:
                    found.append((datetime.date(int(m.group(3)), mon, int(m.group(2))), seg.strip()[:80]))
                except ValueError:
                    pass
            for m in _DATE_ISO.finditer(seg):
                try:
                    found.append((datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), seg.strip()[:80]))
                except ValueError:
                    pass
    fut = sorted((d for d in found if d[0] >= today), key=lambda x: x[0])
    if not fut:
        return None, None, None
    d, snip = fut[0]
    return d.isoformat(), (d - today).days, snip

def milestone_of(r):
    """Dated milestone. Prefers the structured valuation.expected_close_date; falls back to
    the earliest future catalyst date parsed from prose (FDA/readout names). Returns
    (iso_str|None, days_from_today|None, source) where source in
    {"expected_close_date", "prose", None}."""
    iso = (r.get("valuation") or {}).get("expected_close_date") or None
    if iso:
        try:
            d = datetime.date.fromisoformat(str(iso)[:10])
            return iso, (d - datetime.date.today()).days, "expected_close_date"
        except ValueError:
            return iso, None, "expected_close_date"
    iso2, days2, _snip = _prose_milestone(r, datetime.date.today())
    return iso2, days2, ("prose" if iso2 else None)


def live_price_of(r):
    for k in ("live_price", "price", "reference_price"):
        p = r.get(k)
        if isinstance(p, (int, float)) and p > 0:
            return float(p)
    return None


def main(exclude_held=False):
    src_doc = json.load(open(SRC, encoding="utf-8"))
    board = src_doc["candidates"]
    # freshness check (warn-only, never fatal): the board is swept bi-weekly; a stale source
    # usually means the Monday catalyst-watch sweep was missed or rolled back
    src_generated = src_doc.get("generated")
    try:
        src_age_days = (datetime.date.today() - datetime.date.fromisoformat(src_generated)).days
    except (TypeError, ValueError):
        src_age_days = round((datetime.datetime.now() - datetime.datetime.fromtimestamp(
            os.path.getmtime(SRC))).total_seconds() / 86400)
    if src_age_days > 4:
        print(f"WARN: {os.path.basename(SRC)} is {src_age_days} days old "
              f"(generated={src_generated}) — sweep missed or rolled back; trading the prior board")
    window_days = round(MILESTONE_WINDOW_MONTHS * 30.4)
    entries, staging, excluded, prose_rescued = [], [], [], []

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
        iso, days, msrc = milestone_of(r)
        if msrc == "prose" and days is not None and 0 <= days <= window_days:
            prose_rescued.append((r.get("symbol"), iso, days))
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
           "source_generated": src_generated, "source_age_days": src_age_days,
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
    if prose_rescued:
        print(f"  prose-date rescued ({len(prose_rescued)} — dated via bloom_catalysts/analysis, "
              f"not expected_close_date): "
              + ", ".join(f"{s}({iso},{d}d)" for s, iso, d in prose_rescued))
    print(f"-> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-held", action="store_true",
                    help="drop names with an open/pending tracker entry (new-candidates-only re-debate)")
    a = ap.parse_args()
    main(exclude_held=a.exclude_held)
