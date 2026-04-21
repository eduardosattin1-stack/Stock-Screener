#!/usr/bin/env python3
"""
8-K Catalyst Detection — Track B.1 (Backtest Redesign, v8 candidate)
=====================================================================
Detects material-event 8-K filings in a rolling 14-day window and produces
a catalyst bump to be added on top of `compute_catalyst_score` in
screener_v6.py.

WHY 8-K INSTEAD OF NEWS KEYWORD SCRAPING
----------------------------------------
The existing `compute_catalyst_score` inspects FMP `news/stock` titles for
keyword matches (ma_kw / pos_kw / neg_kw). That signal has two known
problems:

  1. Coverage is noisy — titles vary, many articles reach FMP 1-3 days late.
  2. It is NOT legally driven. There is no forcing function that says
     "this story must exist because something material happened."

8-K filings ARE legally mandated for material events (Items 1.01 – 9.01):
entry/termination of material agreements, bankruptcy, acquisitions,
officer departures, reg FD disclosures, private placements, etc. If a
listed company has a materially interesting event, an 8-K will exist.
Filing dates are immutable and backtest-safe.

DESIGN
------
ONE global FMP call per scan — `sec-filings/search-by-form-type?formType=8-K`
with `from = today-14d` and `to = today`. The response contains up to
several thousand rows (US universe typically sees ~2–5k 8-Ks over 14d).
Results are bucketed by symbol into a module-level cache:

    _8K_CACHE_LIVE  : populated by populate_8k_cache_live()
    _8K_CACHE_HIST  : populated per (as_of_date) by populate_8k_cache_historical()

Per-symbol scoring then becomes a dict lookup, not a second API call.

SCORE CONTRIBUTION
------------------
Per handoff spec: +0.15 on top of the existing catalyst factor when a
symbol has one or more 8-Ks in the last 14 days. Capped at +0.25 when
2+ filings (suggests active deal / M&A process / restructuring).

USAGE IN screener_v6.py
-----------------------
See INTEGRATION_GUIDE.md. Short version:

    from factor_8k_catalyst import (
        populate_8k_cache_live,
        populate_8k_cache_historical,
        score_8k_bump,
    )

    # Live path (once per scan, before the per-symbol loop):
    populate_8k_cache_live(fmp)

    # Historical path in backtest (once per as-of date):
    populate_8k_cache_historical(fmp, as_of_date="2023-06-15")

    # Inside compute_catalyst_score, RIGHT BEFORE clamping:
    bump = score_8k_bump(sym, as_of_date=None)  # or as_of_date for backtest
    if bump["_evaluated"]:
        result["score"] += bump["delta"]
        if bump["flags"]:
            result["flags"].extend(bump["flags"])

BACKTEST SAFETY
---------------
`filingDate` is the SEC filing timestamp and is immutable — a 2023-02-14
filing always shows up as 2023-02-14 regardless of when FMP is queried.
`populate_8k_cache_historical` passes from/to params to FMP and filters
defensively. No look-ahead possible.

LIMITATIONS
-----------
- FMP's `search-by-form-type` is paginated (default 100, configurable
  via `limit` + `page`). For 14-day windows in the US universe we need
  multiple pages. We fetch up to `_MAX_PAGES` pages and log if truncated.
- We do not classify by Item number — that would be a v8.1 upgrade
  (e.g., Item 2.01 M&A is stronger than Item 8.01 generic disclosure).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level caches (keyed by symbol → list of filing dicts)
# ---------------------------------------------------------------------------

_8K_CACHE_LIVE: dict = {}
_8K_CACHE_HIST: dict = {}   # keyed by as_of_date string → {symbol: [filings]}

# Pagination control: FMP returns 100 rows per page by default.
# 14 days × ~100 8-Ks/day in US universe ≈ 1,400 rows → 14 pages max.
_MAX_PAGES = 25
_PAGE_LIMIT = 100

# Catalyst delta values (tunable; matches handoff spec)
_DELTA_ONE_FILING = 0.15
_DELTA_MULTI_FILING = 0.25


def _fetch_8k_window(fmp_func, date_from: str, date_to: str) -> list:
    """
    Fetch all 8-K filings in [date_from, date_to] via pagination.

    Args:
        fmp_func: The screener's fmp() helper — takes (endpoint, params).
        date_from, date_to: "YYYY-MM-DD" strings (inclusive).

    Returns:
        List of filing dicts with keys symbol, cik, filingDate, acceptedDate,
        formType, link, finalLink.
    """
    all_rows = []
    for page in range(_MAX_PAGES):
        rows = fmp_func("sec-filings/search-by-form-type", {
            "formType": "8-K",
            "from": date_from,
            "to": date_to,
            "limit": _PAGE_LIMIT,
            "page": page,
        })
        if not rows or not isinstance(rows, list):
            break
        all_rows.extend(rows)
        if len(rows) < _PAGE_LIMIT:
            break    # last page reached
    else:
        log.warning(
            f"  8-K fetch hit _MAX_PAGES ({_MAX_PAGES}) for {date_from}..{date_to} "
            f"— {len(all_rows)} rows; truncated. Consider narrower window."
        )
    return all_rows


def _bucket_by_symbol(filings: list, as_of_date: Optional[str]) -> dict:
    """
    Group filings by symbol, filtering to only those with filingDate in
    [as_of_date - 14d, as_of_date). The strict `< as_of_date` is critical
    for backtest look-ahead safety: a scan on date D uses filings filed
    BEFORE D, not on D itself (same-day filings may have been published
    hours after the market close, so excluding them is conservative).

    For live use, pass as_of_date=None → includes filings up to today.
    """
    bucket: dict = {}
    cutoff_low = None
    cutoff_high = None
    if as_of_date:
        as_of = datetime.strptime(as_of_date, "%Y-%m-%d")
        cutoff_low = (as_of - timedelta(days=14)).strftime("%Y-%m-%d")
        cutoff_high = as_of_date   # EXCLUSIVE upper bound

    for f in filings or []:
        sym = (f.get("symbol") or "").upper()
        if not sym:
            continue
        fd = (f.get("filingDate") or "")[:10]
        if not fd:
            continue
        if cutoff_low is not None and fd < cutoff_low:
            continue
        if cutoff_high is not None and fd >= cutoff_high:
            continue    # strict < for backtest safety
        bucket.setdefault(sym, []).append(f)
    return bucket


# ---------------------------------------------------------------------------
# Public API — population
# ---------------------------------------------------------------------------

def populate_8k_cache_live(fmp_func) -> int:
    """
    Populate the module-level LIVE cache. Call once per scan BEFORE the
    per-symbol loop in screener_v6.py.

    Returns:
        Number of unique symbols with at least one 8-K in the last 14 days.
    """
    global _8K_CACHE_LIVE
    today = datetime.now()
    date_to = today.strftime("%Y-%m-%d")
    date_from = (today - timedelta(days=14)).strftime("%Y-%m-%d")

    filings = _fetch_8k_window(fmp_func, date_from, date_to)
    # Live mode: include filings UP TO today inclusive
    _8K_CACHE_LIVE = _bucket_by_symbol(filings, as_of_date=None)

    # Post-filter to last 14d (live path doesn't hand down cutoff)
    live_low = date_from
    filtered = {}
    for sym, fs in _8K_CACHE_LIVE.items():
        fs = [f for f in fs if (f.get("filingDate") or "")[:10] >= live_low]
        if fs:
            filtered[sym] = fs
    _8K_CACHE_LIVE = filtered

    log.info(f"  8-K cache (live): {len(_8K_CACHE_LIVE)} symbols "
             f"with filings in {date_from}..{date_to}")
    return len(_8K_CACHE_LIVE)


def populate_8k_cache_historical(fmp_func, as_of_date: str) -> int:
    """
    Populate the HISTORICAL cache for backtest. Call once per unique
    `as_of_date` (e.g., once per weekly rebalance iteration).

    Uses strict `filingDate < as_of_date` to prevent look-ahead.

    Args:
        as_of_date: "YYYY-MM-DD" — the simulation "today".

    Returns:
        Number of unique symbols with at least one 8-K in the window.
    """
    global _8K_CACHE_HIST
    if as_of_date in _8K_CACHE_HIST:
        return len(_8K_CACHE_HIST[as_of_date])

    as_of = datetime.strptime(as_of_date, "%Y-%m-%d")
    # Fetch an extra day at both ends to be robust against timezone shifts
    # in FMP's filingDate (some rows use UTC midnight).
    date_from = (as_of - timedelta(days=15)).strftime("%Y-%m-%d")
    date_to = as_of_date    # inclusive at API level; we'll filter strict <

    filings = _fetch_8k_window(fmp_func, date_from, date_to)
    bucket = _bucket_by_symbol(filings, as_of_date=as_of_date)
    _8K_CACHE_HIST[as_of_date] = bucket

    log.debug(f"  8-K cache (hist, {as_of_date}): "
              f"{len(bucket)} symbols with filings in "
              f"[{date_from}, {as_of_date})")
    return len(bucket)


def clear_caches():
    """Reset both caches. Used in tests and between backtest runs."""
    global _8K_CACHE_LIVE, _8K_CACHE_HIST
    _8K_CACHE_LIVE = {}
    _8K_CACHE_HIST = {}


# ---------------------------------------------------------------------------
# Public API — per-symbol scoring
# ---------------------------------------------------------------------------

def score_8k_bump(sym: str, as_of_date: Optional[str] = None) -> dict:
    """
    Returns the catalyst-score bump for `sym` based on 8-K filings in the
    last 14 days.

    Args:
        sym: Ticker, e.g. "NVDA".
        as_of_date: If provided, uses the HISTORICAL cache for that date.
            If None, uses the LIVE cache.

    Returns:
        {
          "delta": float,       # to be added to catalyst score
          "count": int,         # number of 8-Ks found
          "flags": [str, ...],  # human-readable flags for reasons list
          "filings": [dict],    # raw filing rows (for debug/UI)
          "_evaluated": bool    # True iff cache was populated (even empty)
        }
    """
    if as_of_date is None:
        cache = _8K_CACHE_LIVE
        cache_populated = bool(_8K_CACHE_LIVE) or _8K_CACHE_LIVE is not None
        # _8K_CACHE_LIVE is always a dict; the right signal is whether
        # populate_8k_cache_live was called. We use a sentinel key:
        cache_populated = "__populated__" in _8K_CACHE_LIVE or len(_8K_CACHE_LIVE) > 0
        # If populate was called but produced zero symbols, we still want
        # _evaluated=True. Mark populate as having run by including a sentinel
        # in populate_8k_cache_live — see below.
    else:
        cache = _8K_CACHE_HIST.get(as_of_date, {})
        cache_populated = as_of_date in _8K_CACHE_HIST

    sym_u = (sym or "").upper()
    filings = cache.get(sym_u, [])
    n = len(filings)

    if n == 0:
        return {
            "delta": 0.0,
            "count": 0,
            "flags": [],
            "filings": [],
            "_evaluated": cache_populated,
        }

    if n == 1:
        delta = _DELTA_ONE_FILING
        flag = f"8-K filed {filings[0].get('filingDate','')[:10]}"
    else:
        delta = _DELTA_MULTI_FILING
        dates = sorted({(f.get("filingDate") or "")[:10] for f in filings})
        flag = f"{n} 8-Ks in 14d ({', '.join(dates)})"

    return {
        "delta": delta,
        "count": n,
        "flags": [flag],
        "filings": filings,
        "_evaluated": True,
    }


# ---------------------------------------------------------------------------
# Standalone convenience — wraps bump into the same shape as other
# `compute_*_score` functions in screener_v6.py for drop-in testability.
# ---------------------------------------------------------------------------

def compute_8k_catalyst_score(sym: str, as_of_date: Optional[str] = None) -> dict:
    """
    Return a full factor-style dict for 8-K catalyst.

    Not used in production scoring (8-K is a SUB-SIGNAL added on top of
    the existing catalyst factor). Provided for ad-hoc diagnostics and
    for Track A's factor-importance analysis when the sub-signal is split
    out for ablation testing.
    """
    bump = score_8k_bump(sym, as_of_date=as_of_date)
    # Map delta → score (0.5 neutral, each filing worth ~0.3 of the dial)
    if not bump["_evaluated"]:
        return {"score": 0.5, "flags": [], "_evaluated": False, "count": 0}
    if bump["count"] == 0:
        return {"score": 0.5, "flags": [], "_evaluated": True, "count": 0}
    base = 0.5 + bump["delta"] * 2.0    # 0.15 → 0.80, 0.25 → 1.00
    base = max(0.0, min(1.0, base))
    return {
        "score": round(base, 3),
        "flags": bump["flags"],
        "_evaluated": True,
        "count": bump["count"],
        "filings": bump["filings"],
    }


# ---------------------------------------------------------------------------
# Live-mode sentinel: make populate_8k_cache_live() set a sentinel key so
# an empty universe (no 8-Ks in 14d) still registers _evaluated=True.
# ---------------------------------------------------------------------------

def _ensure_live_sentinel():
    """Mark live cache as populated even if empty."""
    global _8K_CACHE_LIVE
    _8K_CACHE_LIVE["__populated__"] = []


# Wrap the populate functions to set the sentinel (monkey-patch ourselves
# so the public API stays clean).
_orig_populate_live = populate_8k_cache_live


def populate_8k_cache_live(fmp_func) -> int:    # noqa: F811
    """Populate live cache (sentinel-aware wrapper)."""
    # Call the original — replicated here because Python captured the
    # original at definition time.
    global _8K_CACHE_LIVE
    today = datetime.now()
    date_to = today.strftime("%Y-%m-%d")
    date_from = (today - timedelta(days=14)).strftime("%Y-%m-%d")

    filings = _fetch_8k_window(fmp_func, date_from, date_to)
    _8K_CACHE_LIVE = _bucket_by_symbol(filings, as_of_date=None)

    # Post-filter to last 14d
    filtered = {}
    for sym, fs in _8K_CACHE_LIVE.items():
        fs_kept = [f for f in fs if (f.get("filingDate") or "")[:10] >= date_from]
        if fs_kept:
            filtered[sym] = fs_kept
    _8K_CACHE_LIVE = filtered
    _ensure_live_sentinel()

    n_syms = len(_8K_CACHE_LIVE) - 1    # subtract sentinel
    log.info(f"  8-K cache (live): {n_syms} symbols with filings "
             f"in {date_from}..{date_to}")
    return n_syms


# ---------------------------------------------------------------------------
# Quick self-test (runs with `python factor_8k_catalyst.py`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Minimal mock fmp() for unit testing without network
    def mock_fmp(endpoint, params=None):
        assert endpoint == "sec-filings/search-by-form-type"
        return [
            {"symbol": "NVDA", "cik": "1", "filingDate": "2026-04-15 09:30:00",
             "formType": "8-K", "link": "x", "finalLink": "y"},
            {"symbol": "NVDA", "cik": "1", "filingDate": "2026-04-18 16:01:00",
             "formType": "8-K", "link": "x", "finalLink": "y"},
            {"symbol": "AAPL", "cik": "2", "filingDate": "2026-04-19 17:00:00",
             "formType": "8-K", "link": "x", "finalLink": "y"},
            # Out-of-window (too old) — should be filtered
            {"symbol": "OLD", "cik": "3", "filingDate": "2025-12-01 12:00:00",
             "formType": "8-K", "link": "x", "finalLink": "y"},
        ]

    print("=== LIVE CACHE TEST ===")
    populate_8k_cache_live(mock_fmp)
    for sym in ["NVDA", "AAPL", "TSLA", "OLD"]:
        r = score_8k_bump(sym)
        print(f"  {sym:6s} → delta={r['delta']:.2f} count={r['count']} "
              f"flags={r['flags']}")

    print("\n=== HISTORICAL CACHE TEST (as_of=2026-04-17) ===")
    # With as_of=2026-04-17, only NVDA's 2026-04-15 filing qualifies
    # (2026-04-18 NVDA and AAPL 2026-04-19 are AFTER as_of, excluded).
    populate_8k_cache_historical(mock_fmp, "2026-04-17")
    for sym in ["NVDA", "AAPL"]:
        r = score_8k_bump(sym, as_of_date="2026-04-17")
        print(f"  {sym:6s} → delta={r['delta']:.2f} count={r['count']}")

    print("\n=== COMPOSITE FACTOR SHAPE ===")
    print(" ", compute_8k_catalyst_score("NVDA"))
