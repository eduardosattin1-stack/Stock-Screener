#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Setup path and imports
sys_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, sys_path)

from opportunistic_catalysts import get_catalyst_candidates, run_catalyst_scan, _load_deep_scans_cache

log = logging.getLogger("run_universe_scan")

def run_universe_scan(limit=None, max_workers=10):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log.info("Starting batch catalyst scan for the candidate universe...")
    
    # 1. Fetch candidates from latest scan data (current cap is 400)
    candidates = get_catalyst_candidates()
    total_candidates = len(candidates)
    log.info(f"Loaded {total_candidates} candidates for catalyst scanning.")
    
    if limit:
        candidates = candidates[:limit]
        total_candidates = len(candidates)
        log.info(f"Scanning limit set to: {total_candidates}")
        
    # Enable batch scan mode to suppress individual GCS writes during concurrent execution
    os.environ["BATCH_SCAN_MODE"] = "1"
    
    # 2. Parallel scan each candidate to build/update cache
    success_count = 0
    cache = _load_deep_scans_cache()
    
    def scan_symbol(idx, symbol):
        symbol_upper = symbol.upper().strip()
        if symbol_upper in cache:
            entry = cache[symbol_upper]
            summary = entry.get("data", {}).get("analysis_summary", "")
            is_mock = "being monitored for potential" in summary
            if not is_mock:
                log.info(f"[{idx+1}/{total_candidates}] {symbol} already successfully scanned. Skipping LLM call.")
                return True
        
        log.info(f"[{idx+1}/{total_candidates}] Deep scanning {symbol}...")
        try:
            # force_refresh=True will run a fresh Claude scan and update local cache
            run_catalyst_scan(symbol, force_refresh=True)
            return True
        except Exception as e:
            log.error(f"Failed to scan {symbol}: {e}")
            return False

    log.info(f"Running scans concurrently with {max_workers} worker threads...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(scan_symbol, i, cand["symbol"]): cand["symbol"]
            for i, cand in enumerate(candidates)
        }
        
        # Process as they complete
        for fut in concurrent.futures.as_completed(futures):
            symbol = futures[fut]
            try:
                if fut.result():
                    success_count += 1
            except Exception as e:
                log.error(f"Unexpected error scanning {symbol}: {e}")

    # Remove batch scan mode flag
    if "BATCH_SCAN_MODE" in os.environ:
        del os.environ["BATCH_SCAN_MODE"]

    # 3. Perform a single, consolidated GCS sync at the end of the batch run
    try:
        from alpha_compounder.gcs_io import gcs_write_json
        log.info("Syncing consolidated cache to GCS...")
        cache = _load_deep_scans_cache()
        if gcs_write_json("scans/deep_scans_cache.json", cache):
            log.info("Successfully synced consolidated cache to GCS.")
        else:
            log.warning("GCS sync returned False (local fallback active).")
    except Exception as e:
        log.error(f"Failed to sync consolidated cache to GCS: {e}")

    log.info(f"Batch universe scan complete. Successfully scanned {success_count}/{total_candidates} candidates.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of scanned symbols for testing")
    parser.add_argument("--workers", type=int, default=10, help="Number of parallel worker threads")
    args = parser.parse_args()
    
    run_universe_scan(limit=args.limit, max_workers=args.workers)
