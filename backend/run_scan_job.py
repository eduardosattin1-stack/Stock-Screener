#!/usr/bin/env python3
"""
run_scan_job.py — Cloud Run Job entrypoint for scheduled scans
================================================================
Runs a full screener scan, writes latest_{region}.json to GCS, and
triggers post-scan tracking + rebalance + options suggestions.

Invoked by:
  - gcloud scheduler jobs run (via Cloud Scheduler targeting screener-sp500)
  - Manual GitHub Actions workflow_dispatch

*NOTE: Single-region runner. Set REGIONS_TO_SCAN below to change. Currently: ["global"].*
"""
import os, sys, json, logging
from datetime import datetime

# Make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_scan_job")


def _load_scan_from_gcs(region: str) -> list:
    import requests
    url = f"https://storage.googleapis.com/screener-signals-carbonbridge/latest_{region}.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                return data.get("stocks", [])
            if isinstance(data, list):
                return data
    except Exception as e:
        log.warning(f"Could not reload scan from GCS: {e}")
    return []


def main():
    # HARDCODED REGIONS TO SCAN SEQUENTIALLY
    REGIONS_TO_SCAN = ["global"]
    log.info(f"═══ Scan job starting: processing {len(REGIONS_TO_SCAN)} regions sequentially ═══")

    import screener_v6
    import signal_tracker
    import tradier_options

    for region in REGIONS_TO_SCAN:
        log.info(f"═══ Processing region={region} ═══")

        # ─── 1. Run the screener ───
        try:
            sys.argv = ["screener_v6.py", "--region", region]
            screener_v6.main()
        except Exception as e:
            log.error(f"[{region}] Screener failed: {e}", exc_info=True)
            continue # Skip to the next region if this one crashes

        # ─── 2. Speculair Debate Pipeline — DISABLED on Cloud Run (2026-06-10) ───
        # The debate runs LOCALLY on Claude Code (weekly speculair-opus-weekly skill), which
        # publishes the authoritative speculair_baskets.json. Running the keyless cross-model
        # engine here every night REWROTE that file (wiped engine=opus-4.8-claude-code-subagents,
        # shrank per_methodology_baskets 203 -> 71 picks). Nightly NAV marking is handled by
        # _mark_speculair_nav() inside screener_v6.main() — no debate needed.
        if os.environ.get("SPECULAIR_DEBATE_CLOUDRUN", "").lower() in ("1", "true", "yes"):
            try:
                from live_debate_engine import debate_and_allocate
                log.info(f"[{region}] Running Speculair debate pipeline...")
                debate_and_allocate(dry_run=False)
                log.info(f"[{region}] Debate pipeline complete.")
            except Exception as e:
                log.error(f"[{region}] Debate pipeline failed: {e}", exc_info=True)
        else:
            log.info(f"[{region}] Speculair debate skipped — runs locally via the weekly Claude Code "
                     f"skill (set SPECULAIR_DEBATE_CLOUDRUN=1 to re-enable here).")

        log.info(f"═══ Completed processing region={region} ═══")

    log.info(f"═══ Consolidated Scan job complete ═══")


if __name__ == "__main__":
    main()
