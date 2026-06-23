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

import threading
import time
import json

log = logging.getLogger("run_universe_scan")

progress_lock = threading.Lock()
completed_count = 0
start_time = None
last_gcs_write_time = 0.0

def _write_progress(symbol, completed, total, status="scanning"):
    global last_gcs_write_time
    # Run under lock
    elapsed = (datetime.now() - start_time).total_seconds()
    avg_speed = completed / elapsed if elapsed > 0 else 0.0
    est_remaining = (total - completed) / avg_speed if avg_speed > 0 else 0.0
    
    progress_data = {
        "status": status,
        "total_symbols": total,
        "completed_count": completed,
        "current_symbol": symbol,
        "start_time": start_time.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "average_seconds_per_ticker": round(1 / avg_speed, 2) if avg_speed > 0 else 0.0,
        "estimated_remaining_seconds": round(est_remaining, 1),
        "speed_stats": f"{avg_speed:.2f} symbols/sec" if status == "scanning" else ("Done" if status == "completed" else "Idle")
    }
    
    # Save local progress
    try:
        progress_file = os.path.join(sys_path, "scan_progress.json")
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to write local progress: {e}")
        
    # Rate-limited GCS sync (at most once every 5 seconds, or always on completion/start)
    now_time = time.time()
    if status in ("completed", "failed") or completed == 0 or (now_time - last_gcs_write_time >= 5.0):
        last_gcs_write_time = now_time
        try:
            from alpha_compounder.gcs_io import gcs_write_json
            gcs_write_json("scans/scan_progress.json", progress_data)
        except Exception as e:
            log.warning(f"Failed to sync progress to GCS: {e}")

def run_universe_scan(limit=None, max_workers=10, force_refresh=False):
    global completed_count, start_time
    if os.environ.get("FORCE_REFRESH_CATALYSTS", "").lower() in ("1", "true", "yes"):
        force_refresh = True
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
    
    # Initialize progress variables
    completed_count = 0
    start_time = datetime.now()
    _write_progress("STARTING", 0, total_candidates, "scanning")
    
    # 2. Parallel scan each candidate to build/update cache
    success_count = 0
    cache = _load_deep_scans_cache()
    
    def scan_symbol(idx, symbol):
        global completed_count
        symbol_upper = symbol.upper().strip()
        already_scanned = False
        
        if symbol_upper in cache:
            entry = cache[symbol_upper]
            summary = entry.get("data", {}).get("analysis_summary", "")
            is_mock = "being monitored for potential" in summary
            if not is_mock:
                log.info(f"[{idx+1}/{total_candidates}] {symbol} already successfully scanned. Skipping LLM call.")
                already_scanned = True
        
        success = True
        if not already_scanned or force_refresh:
            log.info(f"[{idx+1}/{total_candidates}] Deep scanning {symbol}...")
            try:
                # force_refresh=True will run a fresh Claude scan and update local cache
                run_catalyst_scan(symbol, force_refresh=True)
            except Exception as e:
                log.error(f"Failed to scan {symbol}: {e}")
                success = False
                
        # Update progress in a thread-safe manner
        with progress_lock:
            completed_count += 1
            current_completed = completed_count
        _write_progress(symbol_upper, current_completed, total_candidates, "scanning")
        
        return success

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

    # Write completed progress
    _write_progress("FINISHED", completed_count, total_candidates, "completed")
    log.info(f"Batch universe scan complete. Successfully scanned {success_count}/{total_candidates} candidates.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of scanned symbols for testing")
    parser.add_argument("--workers", type=int, default=10, help="Number of parallel worker threads")
    parser.add_argument("--force", action="store_true", help="Force refresh even if already scanned")
    args = parser.parse_args()
    
    run_universe_scan(limit=args.limit, max_workers=args.workers, force_refresh=args.force)
