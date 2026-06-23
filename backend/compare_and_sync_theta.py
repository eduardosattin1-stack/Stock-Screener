import os
import json
import logging
import datetime
import threading
import codecs
from pathlib import Path
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from thetadata import ThetaClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
log = logging.getLogger("Theta-SyncManager")

# Paths
workspace_dir = Path("c:/Users/Bruno/Stock-Screener")
backend_dir = workspace_dir / "backend"
cache_dir = backend_dir / "Cache_Data"
theta_cache_dir = cache_dir / "Theta_Historical"
sp500_history_path = backend_dir / "backtest_v9" / "data" / "sp500_history.json"
expanded_manifest_path = backend_dir / "expanded_universe_manifest.json"
scan_cache_path = backend_dir / "scan_cache.jsonl"
brain_dir = Path("C:/Users/Bruno/.gemini/antigravity/brain/029308eb-3681-49ff-aa53-b91934f48670")
report_path = brain_dir / "universe_comparison_report.md"

os.makedirs(theta_cache_dir, exist_ok=True)

# Concurrency configurations (Standard Tier allows 4 concurrent requests)
MAX_CONCURRENT_REQUESTS = 4
sema = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

def clean_symbol(s):
    if not s:
        return ""
    return s.replace("\ufeff", "").strip().upper()

def fetch_history_for_symbol(client, symbol, scan_dates):
    """
    Worker function executed inside a ThreadPool. 
    Uses the globally shared client and respects the concurrency semaphore.
    """
    file_path = os.path.join(theta_cache_dir, f"{symbol}_theta.parquet")
    
    # Filter target dates to >= "2019-01-01"
    target_dates = [d for d in scan_dates if d >= "2019-01-01"]
    if not target_dates:
        return f"{symbol} has no target dates >= 2019-01-01."
        
    df_existing = None
    existing_dates = set()
    if os.path.exists(file_path):
        try:
            df_existing = pd.read_parquet(file_path)
            if not df_existing.empty and 'scan_date' in df_existing.columns:
                existing_dates = set(df_existing['scan_date'].unique())
        except Exception as e:
            log.warning(f"Error reading existing file for {symbol}: {e}")
            df_existing = None
            
    missing_dates = [d for d in target_dates if d not in existing_dates]
    if not missing_dates:
        return f"{symbol} already fully synced (all target dates present)."
        
    all_rows = []
    
    for date_str in missing_dates:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        import time
        max_retries = 3
        greeks_df_polars = None
        oi_df_polars = None
        for retry in range(max_retries):
            try:
                with sema:
                    time.sleep(0.1) # Hard rate limit buffer
                    # 1. Fetch Greeks
                    greeks_df_polars = client.option_history_greeks_eod(
                        symbol=symbol,
                        expiration="*",
                        start_date=date_obj,
                        end_date=date_obj,
                        strike="*",
                        right="both",
                        strike_range=5 
                    )
                    
                    # 2. Fetch Open Interest
                    oi_df_polars = client.option_history_open_interest(
                        symbol=symbol,
                        expiration="*",
                        start_date=date_obj,
                        end_date=date_obj,
                        strike="*",
                        right="both",
                        strike_range=5 
                    )
                break # Success, break retry loop
            except Exception as e:
                err_msg = str(e)
                if "No data" in err_msg:
                    greeks_df_polars = None
                    oi_df_polars = None
                    break # No data, stop retrying
                log.warning(f"Error fetching options for {symbol} on {date_str} (retry {retry+1}/{max_retries}): {type(e)}: {e}")
                if retry == max_retries - 1:
                    raise RuntimeError(f"Persistent failure for {symbol} on {date_str}: {e}") from e
                time.sleep(2 ** retry) # Exponential backoff
                
        # Process outside of the semaphore to release the API token quickly
        if greeks_df_polars is not None and not greeks_df_polars.empty:
            df_greeks = greeks_df_polars
            
            if oi_df_polars is not None and not oi_df_polars.empty:
                df_oi = oi_df_polars
                # Merge on the contract signature
                df = pd.merge(
                    df_greeks, 
                    df_oi[['expiration', 'strike', 'right', 'open_interest']], 
                    on=['expiration', 'strike', 'right'], 
                    how='left'
                )
            else:
                df = df_greeks
                df['open_interest'] = 0.0
                
            df['scan_date'] = date_str
        else:
            # Create a placeholder row to mark the date as synced but empty
            df = pd.DataFrame([{
                'symbol': symbol,
                'scan_date': date_str,
                'expiration': None,
                'strike': None,
                'right': 'NONE',
                'delta': None,
                'implied_vol': None,
                'open_interest': 0.0,
                'gamma': 0.0
            }])
            
        all_rows.append(df)
        
        # Save incrementally after each date to prevent data loss and show progress
        try:
            if os.path.exists(file_path):
                df_existing = pd.read_parquet(file_path)
            else:
                df_existing = pd.DataFrame()
                
            if not df_existing.empty:
                if 'scan_date' in df_existing.columns:
                    df_existing = df_existing[df_existing['scan_date'] != date_str]
                final_df = pd.concat([df_existing, df], ignore_index=True)
            else:
                final_df = df
                
            final_df.sort_values('scan_date', inplace=True)
            final_df.to_parquet(file_path, engine='pyarrow')
            
            # Print incremental progress
            log.info(f"[{symbol}] Synced date {date_str} ({len(df)} rows). Cache total: {len(final_df)}")
        except Exception as e:
            log.error(f"Failed to write incremental parquet for {symbol} on {date_str}: {e}")
            
    # Read final row count to report
    total_saved_rows = 0
    try:
        if os.path.exists(file_path):
            total_saved_rows = len(pd.read_parquet(file_path, columns=[]))
    except Exception:
        pass
        
    return f"Finished {symbol} - processed {len(missing_dates)} dates. Total cached rows: {total_saved_rows}."

def run_comparison_and_sync():
    log.info("Connecting to local Theta Terminal...")
    client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"], dataframe_type="pandas")
    
    # 1. Fetch available symbols from ThetaData
    log.info("Fetching available option symbols from ThetaData...")
    available_symbols_df = client.option_list_symbols()
    available_symbols = set(clean_symbol(s) for s in available_symbols_df['symbol'].tolist() if s)
    log.info(f"ThetaData has {len(available_symbols)} option-enabled symbols available.")

    # 2. Load S&P 500 history
    sp500_symbols = set()
    if sp500_history_path.exists():
        with open(sp500_history_path, "r") as f:
            sp500_data = json.load(f)
        for date_str, sym_list in sp500_data.items():
            for s in sym_list:
                clean_s = clean_symbol(s)
                if clean_s:
                    sp500_symbols.add(clean_s)
    
    # 3. Load Expanded Universe Manifest
    expanded_symbols = set()
    if expanded_manifest_path.exists():
        with open(expanded_manifest_path, "r") as f:
            manifest_data = json.load(f)
        for item in manifest_data:
            s = clean_symbol(item.get("symbol"))
            if s:
                expanded_symbols.add(s)

    # 4. Check cache status
    cached_symbols = set()
    if theta_cache_dir.exists():
        for f in os.listdir(theta_cache_dir):
            if f.upper().endswith("_THETA.PARQUET"):
                sym = clean_symbol(f[:-14])
                cached_symbols.add(sym)

    # 5. Compute comparisons
    sp500_available = sp500_symbols.intersection(available_symbols)
    sp500_cached = sp500_symbols.intersection(cached_symbols)
    sp500_missing_but_available = sp500_available.difference(sp500_cached)

    expanded_available = expanded_symbols.intersection(available_symbols)
    expanded_cached = expanded_symbols.intersection(cached_symbols)
    expanded_missing_but_available = expanded_available.difference(expanded_cached)

    # Generate Report
    md = []
    md.append("# ThetaData Universe Comparison Report\n")
    md.append(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append("This report compares our target backtest universes (S&P 500 constituents and the Expanded Universe) with the list of symbols available for option data download from ThetaData API.\n")
    
    md.append("## 1. Summary Statistics\n")
    md.append("| Metric | S&P 500 Universe | Expanded Universe |")
    md.append("|---|---|---|")
    md.append(f"| **Total Target Symbols** | {len(sp500_symbols)} | {len(expanded_symbols)} |")
    md.append(f"| **Available on ThetaData** | {len(sp500_available)} | {len(expanded_available)} |")
    md.append(f"| **Currently Cached** | {len(sp500_cached)} | {len(expanded_cached)} |")
    md.append(f"| **Available but Missing** | {len(sp500_missing_but_available)} | {len(expanded_missing_but_available)} |")
    md.append(f"| **Not Available on ThetaData** | {len(sp500_symbols - sp500_available)} | {len(expanded_symbols - expanded_available)} |")
    md.append("\n")

    md.append("## 2. Missing but Available S&P 500 Symbols (Sync Targets)\n")
    md.append(f"There are **{len(sp500_missing_but_available)}** symbols in the S&P 500 universe that are available on ThetaData but missing from our cache. We will prioritize syncing these first.\n")
    md.append(", ".join(sorted(list(sp500_missing_but_available))))
    md.append("\n")

    report_path.write_text("\n".join(md), encoding="utf-8")
    log.info(f"Comparison report saved to {report_path}")

    # 6. Load dates from scan_cache.jsonl for target symbols
    log.info("Loading scan dates from scan_cache.jsonl...")
    symbol_dates = {}
    if scan_cache_path.exists():
        with open(scan_cache_path, "r") as f:
            for line in f:
                rec = json.loads(line)
                sym = clean_symbol(rec.get("symbol"))
                dt = rec.get("scan_date")
                if sym and dt:
                    # We target all available S&P 500 symbols
                    if sym in sp500_available:
                        if sym not in symbol_dates:
                            symbol_dates[sym] = set()
                        symbol_dates[sym].add(dt)
    
    # Sort dates
    for sym in symbol_dates:
        symbol_dates[sym] = sorted(list(symbol_dates[sym]))
        
    target_symbols = sorted(list(symbol_dates.keys()))
    log.info(f"Found scan dates for {len(target_symbols)} missing S&P 500 symbols.")
    
    if not target_symbols:
        log.info("No missing S&P 500 symbols found with scan dates. Nothing to sync.")
        return

    # Let's download option data!
    # To be conservative, let's limit to the first 10 symbols to verify stability and performance,
    # or run a full sync. Let's start a thread pool to sync them.
    log.info(f"Starting option data sync for {len(target_symbols)} symbols...")
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_history_for_symbol, client, sym, symbol_dates[sym]): sym 
            for sym in target_symbols
        }
        for future in as_completed(futures):
            sym = futures[future]
            completed += 1
            try:
                res = future.result()
                if completed % 5 == 0 or "added" in res:
                    log.info(f"Progress {completed}/{len(target_symbols)}: {res}")
            except Exception as e:
                log.error(f"Worker crashed on {sym}: {e}")

    log.info("Option data sync completed successfully!")

if __name__ == "__main__":
    run_comparison_and_sync()
