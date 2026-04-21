#!/usr/bin/env python3
"""
run_scan_job.py — Cloud Run Job entrypoint for scheduled scans
================================================================
Runs a full screener scan, writes latest_{region}.json to GCS, and
triggers post-scan tracking + rebalance + options suggestions.

Invoked by:
  - gcloud scheduler jobs run (via Cloud Scheduler targeting screener-sp500)
  - Manual GitHub Actions workflow_dispatch

*NOTE: Hijacked to run both SP500 and NASDAQ sequentially in one job run.*
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
    REGIONS_TO_SCAN = ["sp500", "nasdaq"]
    log.info(f"═══ Scan job starting: processing {len(REGIONS_TO_SCAN)} regions sequentially ═══")

    import screener_v6
    import signal_tracker
    import rebalance_engine
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

        log.info(f"[{region}] Screener complete; running post-scan hooks…")

        # ─── 2. Reload scan output ───
        stocks = _load_scan_from_gcs(region)
        if not stocks:
            log.warning(f"[{region}] Could not reload scan output — hooks skipped")
            continue
        log.info(f"[{region}] Loaded {len(stocks)} stocks from latest_{region}.json")

        # ─── 3. Signal tracker ───
        try:
            signal_tracker.update_from_scan(stocks, region)
        except Exception as e:
            log.error(f"[{region}] signal_tracker failed: {e}", exc_info=True)

        # ─── 4. Rebalance engine ───
        rebalance_report = {}
        if region in ["sp500", "nasdaq", "nasdaq100"]:
            try:
                rebalance_report = rebalance_engine.run_rebalance_from_scan(stocks, region)
                summary = rebalance_report.get("summary", {}) if rebalance_report else {}
                if summary.get("actions_required"):
                    log.info(f"[{region}] REBALANCE: {len(rebalance_report['closes'])} close(s), "
                             f"{len(rebalance_report['opens'])} open(s)")
            except Exception as e:
                log.error(f"[{region}] rebalance_engine failed: {e}", exc_info=True)

        # ─── 5. Tradier options overlay ───
        if region in ["sp500", "nasdaq", "nasdaq100"] and rebalance_report:
            try:
                if not os.environ.get("TRADIER_TOKEN"):
                    log.info(f"[{region}] TRADIER_TOKEN not set — options skipped")
                else:
                    opt_result = tradier_options.suggest_spreads_for_portfolio(rebalance_report)
                    log.info(f"[{region}] Options: {len(opt_result.get('suggestions', []))} suggested")
            except Exception as e:
                log.error(f"[{region}] tradier_options failed: {e}", exc_info=True)

        log.info(f"═══ Completed processing region={region} ═══")

    log.info(f"═══ Consolidated Scan job complete ═══")


if __name__ == "__main__":
    main()
