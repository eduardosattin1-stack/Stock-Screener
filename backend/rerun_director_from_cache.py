#!/usr/bin/env python3
"""
rerun_director_from_cache.py — fast local review of the Speculair Apex Director.

Reuses the REAL pipeline (live_debate_engine.debate_and_allocate) end-to-end, but
makes Tier-1 transcript resolution cache-aware and network-free: every symbol that
already has a cached debate (with real theses) is served as a cache hit, and any
symbol without one is treated as "no transcript". The result is that NO Tier-1 LLM
debates or FMP transcript fetches run — only Tier 2 (the Apex Director, claude-opus-4-7)
executes live, over the full debated gate-passing universe.

Writes frontend/public/speculair_baskets.json LOCALLY ONLY (never GCS). Used to
review the §2 free 2-20 / 0-100-conviction director output before promoting.

Usage:
  python rerun_director_from_cache.py
"""
from __future__ import annotations

import sys

import live_debate_engine as E
from live_debate_engine import debate_and_allocate, load_api_keys, load_debate_cache

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    load_api_keys()

    # Force the Director past its cost-guard for this manual review re-run. The guard
    # (live_debate_engine L~1515) otherwise holds the basket because director_last_run is
    # recent; cadence 0 makes `days_since < cadence` always False → the Director runs.
    # One-off ~EUR20 opus call, intentional (applies the tightened G3b to the live basket).
    E.DIRECTOR_CADENCE_DAYS = 0

    # Latest cached transcript date per symbol (only entries with a real thesis).
    cache = load_debate_cache()
    by_sym: dict[str, str] = {}
    for key, val in cache.items():
        if not isinstance(val, dict):
            continue
        if val.get("bull_thesis") in (None, "", "API Timeout/Failure"):
            continue
        sym = key.split("|", 1)[0]
        date = val.get("transcript_date") or (key.split("|", 1)[1] if "|" in key else "")
        if sym not in by_sym or date > by_sym[sym]:
            by_sym[sym] = date
    E.log.info(f"[rerun] {len(by_sym)} symbols have a cached debate with real theses")

    def cache_only_resolve(symbol: str, before_date: str = None, max_transcripts: int = 8) -> dict:
        """Network-free transcript resolver: return the cached transcript date so the
        existing cache-hit path fires; otherwise report no transcript."""
        date = by_sym.get(symbol)
        if not date:
            return {"transcript_count": 0, "transcript_dates": [], "all_transcripts": []}
        return {
            "transcript_count": 1,
            "transcript_dates": [date],
            "all_transcripts": [{
                "date": date,
                "content": "[served from debate cache]",
                "filename": f"{symbol}_{date}.json",
                "source": "cache",
            }],
        }

    # Patch the multi-transcript resolver used by run_tier1.
    E.resolve_transcripts = cache_only_resolve

    output = debate_and_allocate(dry_run=False, push_gcs=False)
    if not output:
        E.log.error("[rerun] pipeline returned no output")
        return 1

    apex = output.get("apex_basket", [])
    memo = output.get("director_memo", "")
    E.log.info(f"[rerun] DONE — apex={len(apex)} memo_fallback={'Fallback' in memo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
