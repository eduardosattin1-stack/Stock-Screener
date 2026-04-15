#!/usr/bin/env python3
"""
Cloud Run Job entry point for stock screener scans.
Runs a scan for the specified region and exits.

Usage (local):
  SCREEN_INDEX=sp500 python run_scan_job.py

Usage (Cloud Run Job):
  Set SCREEN_INDEX env var to: sp500, europe, global, nasdaq100, asia, brazil
"""
import os, sys, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scan_job")

def main():
    region = os.environ.get("SCREEN_INDEX", "sp500")
    log.info(f"=== CB Screener Scan Job ===")
    log.info(f"Region: {region}")
    log.info(f"Started: {datetime.now().isoformat()}")

    try:
        from screener_v6 import get_symbols, screen, format_report, send_email, update_signal_history, save_scan_to_gcs

        symbols = get_symbols(region)
        log.info(f"Symbols to scan: {len(symbols)}")

        results, macro = screen(symbols)
        log.info(f"Scan complete: {len(results)} results")

        report = format_report(results, region, macro=macro)
        update_signal_history(results)
        save_scan_to_gcs(results, region, macro=macro)

        today = datetime.now().strftime("%Y-%m-%d")
        send_email(f"CB Screener v7.1: {region.upper()} — {today}", report)

        log.info(f"Finished: {datetime.now().isoformat()}")
        log.info(f"Top composite: {results[0].symbol if results else 'none'} ({results[0].composite:.3f})" if results else "No results")

    except Exception as e:
        log.error(f"Scan failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
