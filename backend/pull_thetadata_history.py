import os
import json
import logging
import datetime
import time
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from thetadata import ThetaClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
log = logging.getLogger("Theta-BulkExtractor")

CACHE_DIR = "Cache_Data/Theta_Historical"
os.makedirs(CACHE_DIR, exist_ok=True)

class RateLimiter:
    def __init__(self, max_rps):
        self.delay = 1.0 / max_rps
        self.last_call = 0.0
        self.lock = threading.Lock()
        
    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_call = time.time()

# Global Rate Limiter set to 18 RPS to be safe under the 20 RPS limit.
rate_limiter = RateLimiter(18)

def fetch_date(client, symbol, date_str):
    date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    max_retries = 3
    for retry in range(max_retries):
        try:
            rate_limiter.wait()
            # 1. Fetch Greeks
            greeks = client.option_history_greeks_eod(
                symbol=symbol,
                expiration="*",
                start_date=date_obj,
                end_date=date_obj,
                strike="*",
                right="both",
                strike_range=5 
            )
            
            rate_limiter.wait()
            # 2. Fetch Open Interest
            oi = client.option_history_open_interest(
                symbol=symbol,
                expiration="*",
                start_date=date_obj,
                end_date=date_obj,
                strike="*",
                right="both",
                strike_range=5 
            )
            
            if greeks is not None and not greeks.is_empty():
                df_greeks = greeks.to_pandas()
                if oi is not None and not oi.is_empty():
                    df_oi = oi.to_pandas()
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
                return df
            return None
        except Exception as e:
            if "No data" in str(e):
                return None
            if "Invalid session ID" in str(e) or "UNAUTHENTICATED" in str(e) or "session" in str(e).lower():
                log.error(f"FATAL: ThetaData session expired or invalid: {e}")
                import os
                os._exit(2)  # Hard exit to trigger wrapper restart
            if retry == max_retries - 1:
                log.warning(f"Failed to fetch {symbol} on {date_str}: {e}")
                return None
            time.sleep(2 ** retry) # Exponential backoff
    return None

def fetch_history_for_symbol(client, symbol, scan_dates):
    file_path = os.path.join(CACHE_DIR, f"{symbol}_theta.parquet")
    
    # 1. Filter target dates to >= "2019-01-01"
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
        return f"{symbol} already fully synced."
        
    log.info(f"Syncing {symbol}: {len(missing_dates)} missing dates...")
    
    dfs = []
    completed = 0
    # Query dates in parallel for this symbol
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch_date, client, symbol, d): d for d in missing_dates}
        for future in as_completed(futures):
            completed += 1
            res = future.result()
            if res is not None:
                dfs.append(res)
            # Log intermediate progress within the symbol
            if completed % 20 == 0 or completed == len(missing_dates):
                log.info(f"  {symbol} progress: {completed}/{len(missing_dates)} dates completed (fetched {len(dfs)} valid dataframes)")

    if dfs:
        new_df = pd.concat(dfs, ignore_index=True)
        if df_existing is not None and not df_existing.empty:
            final_df = pd.concat([df_existing, new_df], ignore_index=True)
            if 'scan_date' in final_df.columns:
                final_df.drop_duplicates(subset=['scan_date', 'expiration', 'strike', 'right'], inplace=True)
        else:
            final_df = new_df
        final_df.sort_values('scan_date', inplace=True)
        final_df.to_parquet(file_path, engine='pyarrow')
        return f"Finished {symbol} - added {len(dfs)} new dates, total {len(final_df)} rows saved."
    else:
        if df_existing is not None:
            return f"Finished {symbol} - 0 new dates added, preserved {len(df_existing)} existing rows."
        else:
            pd.DataFrame().to_parquet(file_path, engine='pyarrow')
            return f"Finished {symbol} - 0 rows (No historical data)."

if __name__ == "__main__":
    email = os.environ["THETA_EMAIL"]
    password = os.environ["THETA_PASSWORD"]
    
    allowed_symbols = set()
    txt_path = "theta_symbols.txt"
    if os.path.exists(txt_path):
        try:
            for encoding in ['utf-16le', 'utf-8']:
                try:
                    with open(txt_path, 'r', encoding=encoding) as f:
                        content = f.read()
                        allowed_symbols = set(content.replace('\ufeff', '').strip().split())
                        if allowed_symbols:
                            log.info(f"Loaded {len(allowed_symbols)} allowed symbols from {txt_path} using {encoding}")
                            break
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"Error loading {txt_path}: {e}")

    # 1. Build a map of Symbol -> List of exact historical scan dates
    symbol_dates = {}
    with open("scan_cache.jsonl", "r") as f:
        for line in f:
            rec = json.loads(line)
            sym = rec.get("symbol")
            dt = rec.get("scan_date")
            if sym and dt:
                if not allowed_symbols or sym in allowed_symbols:
                    if sym not in symbol_dates:
                        symbol_dates[sym] = set()
                    symbol_dates[sym].add(dt)
                
    for sym in symbol_dates:
        symbol_dates[sym] = sorted(list(symbol_dates[sym]))
        
    # Prioritize symbols that do not have a parquet file in Cache_Data/Theta_Historical yet
    missing_symbols = []
    existing_symbols = []
    for sym in symbol_dates.keys():
        file_path = os.path.join(CACHE_DIR, f"{sym}_theta.parquet")
        if not os.path.exists(file_path):
            missing_symbols.append(sym)
        else:
            existing_symbols.append(sym)
            
    symbols = sorted(missing_symbols) + sorted(existing_symbols)
    log.info(f"Prioritizing {len(missing_symbols)} missing symbols first, followed by {len(existing_symbols)} existing symbols (Total: {len(symbols)}).")
    
    # 2. Instantiate a single global ThetaClient as per API best practices
    client = ThetaClient(email=email, password=password)
    
    # 3. Process symbols sequentially, but query dates in parallel
    completed = 0
    for sym in symbols:
        completed += 1
        try:
            res = fetch_history_for_symbol(client, sym, symbol_dates[sym])
            log.info(f"Progress {completed}/{len(symbols)}: {res}")
        except Exception as e:
            log.error(f"Error on {sym}: {e}")
                
    log.info("ThetaData Bulk Sync Complete!")
