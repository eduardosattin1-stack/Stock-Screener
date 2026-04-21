#!/usr/bin/env python3
"""
run_scan_job.py — Cloud Run Job entrypoint for scheduled scans
================================================================
Runs a full screener scan, writes latest_{region}.json to GCS, and
triggers post-scan tracking + rebalance + options suggestions.

Sequence (SP500 / NASDAQ example):
  1. screener_v6.main() — full scan, writes latest_{region}.json
  2. signal_tracker.update_from_scan() — BUY/SELL + p10 tracking
  3. rebalance_engine.run_rebalance_from_scan() — compute close/open actions
  4. tradier_options.suggest_spreads_for_portfolio() — options overlay candidates

Only US regions (sp500, nasdaq, nasdaq100) trigger rebalance + options.
Europe and global scans update trackers only.

Invoked by:
  - gcloud scheduler jobs run (via Cloud Scheduler)
  - Manual GitHub Actions workflow_dispatch

Region is passed via SCREEN_INDEX env var (set by the Cloud Run Job spec).
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
    region = os.environ.get("SCREEN_INDEX", "sp500")
    log.info(f"═══ Scan job starting: region={region} ═══")

    # ─── 1. Run the screener ───
    try:
        import screener_v6
        # screener_v6.main() reads args from sys.argv; we clear them first.
        sys.argv = ["screener_v6.py", "--region", region]
        screener_v6.main()
    except Exception as e:
        log.error(f"Screener failed: {e}", exc_info=True)
        sys.exit(1)

    log.info("Screener complete; running post-scan hooks…")

    # ─── 2. Reload scan output ───
    stocks = _load_scan_from_gcs(region)
    if not stocks:
        log.warning("Could not reload scan output — post-scan hooks skipped")
        return
    log.info(f"Loaded {len(stocks)} stocks from latest_{region}.json")

    # ─── 3. Signal tracker (all regions) ───
    try:
        import signal_tracker
        signal_tracker.update_from_scan(stocks, region)
    except Exception as e:
        log.error(f"signal_tracker failed: {e}", exc_info=True)

    # ─── 4. Rebalance engine (US markets only) ───
    rebalance_report = {}
    if region in ["sp500", "nasdaq", "nasdaq100"]:
        try:
            import rebalance_engine
            rebalance_report = rebalance_engine.run_rebalance_from_scan(stocks, region)
            summary = rebalance_report.get("summary", {}) if rebalance_report else {}
            if summary.get("actions_required"):
                log.info(f"REBALANCE: {len(rebalance_report['closes'])} close(s), "
                         f"{len(rebalance_report['opens'])} open(s)")
        except Exception as e:
            log.error(f"rebalance_engine failed: {e}", exc_info=True)
    else:
        log.info(f"Rebalance skipped (region={region}, production strategy is US-only)")

    # ─── 5. Tradier options overlay (US markets only, after rebalance) ───
    if region in ["sp500", "nasdaq", "nasdaq100"] and rebalance_report:
        try:
            import tradier_options
            if not os.environ.get("TRADIER_TOKEN"):
                log.info("TRADIER_TOKEN not set — options layer skipped")
            else:
                opt_result = tradier_options.suggest_spreads_for_portfolio(rebalance_report)
                log.info(f"Options: {len(opt_result.get('suggestions', []))} suggested, "
                         f"{len(opt_result.get('gated', []))} gated")
        except Exception as e:
            log.error(f"tradier_options failed: {e}", exc_info=True)

    log.info(f"═══ Scan job complete: region={region} ═══")


if __name__ == "__main__":
    main()
