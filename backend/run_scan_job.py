#!/usr/bin/env python3
"""
run_scan_job.py — Consolidated Cloud Run Job entrypoint for scheduled scans
=============================================================================
Sequentially runs full screener scans and triggers post-scan tracking,
rebalancing, and options suggestions for multiple regions in a single run.

Invoked by:
  - gcloud scheduler jobs run (via Cloud Scheduler)
  - Manual GitHub Actions workflow_dispatch

This job runs one time per day and iterates through the defined production
strategy regions sequentially.
"""
import os, sys, json, logging
from datetime import datetime

# Make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_scan_job")


def _load_scan_from_gcs(region: str) -> list:
    """Read latest_{region}.json back from GCS. Used as the authoritative
    list of stocks for all post-scan hooks, to ensure what's tracked/
    rebalanced is exactly what was persisted."""
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
    # Define the regions you want to scan sequentially.
    REGIONS_TO_SCAN = ["sp500", "nasdaq", "russell2000"]
    log.info(f"═══ Consolidated Scan job starting: processing {len(REGIONS_TO_SCAN)} regions sequentially ═══")

    import screener_v6
    import signal_tracker
    import rebalance_engine
    import tradier_options

    for region in REGIONS_TO_SCAN:
        log.info(f"═══ Processing region={region} ═══")

        # ─── 1. Run the screener for this region ───
        try:
            # screener_v6.main() reads args from sys.argv; we must update it for each iteration.
            sys.argv = ["screener_v6.py", "--region", region]
            screener_v6.main()
        except Exception as e:
            log.error(f"[{region}] Screener failed: {e}", exc_info=True)
            # Proceed to the next region if this one fails to keep the entire job from crashing.
            continue 

        log.info(f"[{region}] Screener complete; running post-scan hooks…")

        # ─── 2. Reload scan output ───
        stocks = _load_scan_from_gcs(region)
        if not stocks:
            log.warning(f"[{region}] Could not reload scan output — post-scan hooks skipped")
            continue
        log.info(f"[{region}] Loaded {len(stocks)} stocks from latest_{region}.json")

        # ─── 3. Signal tracker (all regions) ───
        try:
            signal_tracker.update_from_scan(stocks, region)
        except Exception as e:
            log.error(f"[{region}] signal_tracker failed: {e}", exc_info=True)

        # ─── 4. Rebalance engine (all production strategy regions) ───
        rebalance_report = {}
        if region in ["sp500", "nasdaq", "nasdaq100", "russell2000"]:
            try:
                rebalance_report = rebalance_engine.run_rebalance_from_scan(stocks, region)
                summary = rebalance_report.get("summary", {}) if rebalance_report else {}
                if summary.get("actions_required"):
                    log.info(f"[{region}] REBALANCE: {len(rebalance_report['closes'])} close(s), "
                             f"{len(rebalance_report['opens'])} open(s)")
            except Exception as e:
                log.error(f"[{region}] rebalance_engine failed: {e}", exc_info=True)
        else:
            log.info(f"[{region}] Rebalance skipped (region={region}, production strategy is US-only)")

        # ─── 5. Tradier options overlay (after rebalance) ───
        if region in ["sp500", "nasdaq", "nasdaq100", "russell2000"] and rebalance_report:
            try:
                if not os.environ.get("TRADIER_TOKEN"):
                    log.info(f"[{region}] TRADIER_TOKEN not set — options layer skipped")
                else:
                    opt_result = tradier_options.suggest_spreads_for_portfolio(rebalance_report)
                    log.info(f"[{region}] Options: {len(opt_result.get('suggestions', []))} suggested, "
                             f"{len(opt_result.get('gated', []))} gated")
            except Exception as e:
                log.error(f"[{region}] tradier_options failed: {e}", exc_info=True)

        log.info(f"═══ Completed processing region={region} ═══")

    log.info(f"═══ Consolidated Scan job complete ═══")


if __name__ == "__main__":
    main()
