#!/usr/bin/env python3
"""
ThetaData Expanded Universe Options/Greeks Downloader
=====================================================
Downloads EOD greeks + open interest for all FMP expanded universe symbols
that have options available on ThetaData.

Features:
- REST API (no Theta Terminal needed)
- Fully resumable — skips already-synced dates
- Weekly scan dates auto-generated from 2019-01-01 to present
- Incremental parquet saves after each symbol
- Rate-limited to stay under ThetaData Standard tier limits
- Priority ordering: large caps first, then mid, then small

Usage:
    python download_theta_expanded.py                  # full run
    python download_theta_expanded.py --dry-run        # preview only
    python download_theta_expanded.py --max-symbols 50 # cap symbols
    python download_theta_expanded.py --start-from ZM   # resume from symbol
"""

import os
import sys
import json
import time
import logging
import argparse
import datetime
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────
THETA_EMAIL = os.environ["THETA_EMAIL"]
THETA_PASS  = os.environ["THETA_PASSWORD"]

BACKEND_DIR  = Path(__file__).resolve().parent
CACHE_DIR    = BACKEND_DIR / "Cache_Data" / "Theta_Historical"
MANIFEST     = BACKEND_DIR / "expanded_universe_manifest.json"
SCAN_CACHE   = BACKEND_DIR / "scan_cache.jsonl"
PROGRESS_LOG = BACKEND_DIR / "theta_download_progress.json"

# ThetaData Standard tier: 4 concurrent, 20 RPS
MAX_WORKERS       = 1       # sequential symbol processing (dates parallel)
MAX_DATE_WORKERS  = 12      # parallel date fetches within a symbol (optimized to avoid session invalidation)
RATE_LIMIT_RPS    = 16      # conservative under 20 RPS
START_DATE        = datetime.date(2019, 1, 1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BACKEND_DIR / "theta_expanded.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("Theta-Expanded")


# ── Rate Limiter ───────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, max_rps: float):
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


rate_limiter = RateLimiter(RATE_LIMIT_RPS)


# ── Generate weekly scan dates ─────────────────────────────────────────
def generate_weekly_dates(start: datetime.date, end: datetime.date) -> list[str]:
    """Generate weekly (Friday) dates from start to end."""
    dates = []
    # Start from the first Friday on or after start_date
    d = start
    while d.weekday() != 4:  # 4 = Friday
        d += datetime.timedelta(days=1)
    while d <= end:
        dates.append(d.strftime("%Y-%m-%d"))
        d += datetime.timedelta(days=7)
    return dates


def load_scan_dates_from_jsonl() -> dict[str, list[str]]:
    """Load existing scan dates from scan_cache.jsonl."""
    symbol_dates: dict[str, set[str]] = {}
    if SCAN_CACHE.exists():
        with open(SCAN_CACHE) as f:
            for line in f:
                rec = json.loads(line)
                sym = rec.get("symbol", "").strip().upper()
                dt = rec.get("scan_date")
                if sym and dt:
                    symbol_dates.setdefault(sym, set()).add(dt)
    return {sym: sorted(dates) for sym, dates in symbol_dates.items()}


# ── Fetch a single date ───────────────────────────────────────────────
def fetch_date(client, symbol: str, date_str: str) -> pd.DataFrame | None:
    """Fetch greeks + OI for one symbol on one date."""
    date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    max_retries = 3

    for retry in range(max_retries):
        try:
            rate_limiter.wait()
            greeks = client.option_history_greeks_eod(
                symbol=symbol,
                expiration="*",
                start_date=date_obj,
                end_date=date_obj,
                strike="*",
                right="both",
                strike_range=5,
            )

            rate_limiter.wait()
            oi = client.option_history_open_interest(
                symbol=symbol,
                expiration="*",
                start_date=date_obj,
                end_date=date_obj,
                strike="*",
                right="both",
                strike_range=5,
            )

            if greeks is not None and not greeks.empty:
                df = greeks
                if oi is not None and not oi.empty:
                    df = pd.merge(
                        df,
                        oi[["expiration", "strike", "right", "open_interest"]],
                        on=["expiration", "strike", "right"],
                        how="left",
                    )
                else:
                    df["open_interest"] = 0.0
                df["scan_date"] = date_str
                return df
            return None

        except Exception as e:
            err_str = str(e)
            if "Invalid session ID" in err_str or "UNAUTHENTICATED" in err_str:
                log.error(f"Session expired/unauthenticated error: {err_str}")
                log.error("Session expired! Crashing so outer loop can restart...")
                import os
                os._exit(1)
            if "No data" in err_str or "no data" in err_str.lower():
                return pd.DataFrame([{
                    "scan_date": date_str,
                    "expiration": None,
                    "strike": None,
                    "right": None,
                    "open_interest": 0.0
                }])
            if retry == max_retries - 1:
                log.warning(f"  Failed {symbol} {date_str}: {e}")
                return pd.DataFrame([{
                    "scan_date": date_str,
                    "expiration": None,
                    "strike": None,
                    "right": None,
                    "open_interest": 0.0
                }])
            time.sleep(2 ** retry)

    return None


# ── Process one symbol ─────────────────────────────────────────────────
def process_symbol(client, symbol: str, target_dates: list[str]) -> dict:
    """Download all missing dates for a symbol, save incrementally."""
    file_path = CACHE_DIR / f"{symbol}_theta.parquet"

    # Load existing data
    existing_dates: set[str] = set()
    df_existing = None
    if file_path.exists():
        try:
            df_existing = pd.read_parquet(file_path)
            if not df_existing.empty and "scan_date" in df_existing.columns:
                existing_dates = set(df_existing["scan_date"].unique())
        except Exception:
            df_existing = None

    # Filter to missing dates only
    missing = [d for d in target_dates if d not in existing_dates]
    if not missing:
        return {"symbol": symbol, "status": "synced", "new_dates": 0, "rows": 0}

    # Fetch missing dates in parallel (within symbol)
    new_dfs: list[pd.DataFrame] = []
    errors = 0

    with ThreadPoolExecutor(max_workers=MAX_DATE_WORKERS) as pool:
        futures = {pool.submit(fetch_date, client, symbol, d): d for d in missing}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result()
                if result is not None:
                    new_dfs.append(result)
            except Exception as e:
                errors += 1
                log.warning(f"  {symbol} date error: {e}")

            if completed % 50 == 0:
                log.info(
                    f"  {symbol}: {completed}/{len(missing)} dates "
                    f"({len(new_dfs)} with data, {errors} errors)"
                )

    # Merge and save
    total_rows = 0
    if new_dfs:
        new_df = pd.concat(new_dfs, ignore_index=True)
        if df_existing is not None and not df_existing.empty:
            final_df = pd.concat([df_existing, new_df], ignore_index=True)
            if "scan_date" in final_df.columns:
                final_df.drop_duplicates(
                    subset=["scan_date", "expiration", "strike", "right"],
                    inplace=True,
                )
        else:
            final_df = new_df
        final_df.sort_values("scan_date", inplace=True)
        final_df.to_parquet(file_path, engine="pyarrow")
        total_rows = len(final_df)
    elif df_existing is None:
        # No data at all — write empty parquet as a marker
        pd.DataFrame().to_parquet(file_path, engine="pyarrow")

    return {
        "symbol": symbol,
        "status": "downloaded",
        "new_dates": len(new_dfs),
        "missing_dates": len(missing),
        "rows": total_rows,
        "errors": errors,
    }


# ── Progress tracking ──────────────────────────────────────────────────
def load_progress() -> dict:
    if PROGRESS_LOG.exists():
        with open(PROGRESS_LOG) as f:
            return json.load(f)
    return {"completed_symbols": [], "stats": {}}


def save_progress(progress: dict):
    with open(PROGRESS_LOG, "w") as f:
        json.dump(progress, f, indent=2)


# ── Main ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ThetaData Expanded Universe Downloader")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no downloads")
    parser.add_argument("--max-symbols", type=int, default=0, help="Limit number of symbols")
    parser.add_argument("--start-from", type=str, default="", help="Resume from this symbol")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("ThetaData Expanded Universe Options Downloader")
    log.info("=" * 60)

    os.makedirs(CACHE_DIR, exist_ok=True)

    # 1. Load FMP expanded universe
    log.info("\n[1/4] Loading FMP expanded universe...")
    with open(MANIFEST) as f:
        manifest = json.load(f)
    fmp_symbols = {d["symbol"]: d for d in manifest}
    log.info(f"  FMP universe: {len(fmp_symbols)} symbols")

    # 2. Get ThetaData available option symbols
    log.info("\n[2/4] Connecting to ThetaData REST API...")
    from thetadata import ThetaClient

    client = ThetaClient(email=THETA_EMAIL, password=THETA_PASS, dataframe_type="pandas")
    
    # Wrap gRPC stub methods with a default timeout (20s) to prevent indefinite hangs
    timeout_seconds = 20.0
    for attr_name in dir(client.stub):
        if attr_name.startswith("Get"):
            orig_method = getattr(client.stub, attr_name)
            if callable(orig_method):
                def make_wrapper(method):
                    def wrapper(*args, **kwargs):
                        if "timeout" not in kwargs:
                            kwargs["timeout"] = timeout_seconds
                        return method(*args, **kwargs)
                    return wrapper
                setattr(client.stub, attr_name, make_wrapper(orig_method))
    log.info(f"  Successfully wrapped client.stub gRPC methods with a default timeout of {timeout_seconds}s")

    syms_df = client.option_list_symbols()
    theta_available = set(syms_df["symbol"].tolist())
    log.info(f"  ThetaData option symbols available: {len(theta_available)}")

    # 3. Build target list: FMP symbols with options available, sorted by market cap
    targets = []
    for sym, info in fmp_symbols.items():
        if sym in theta_available:
            targets.append((sym, info.get("market_cap", 0), info.get("band", "")))

    # Sort by market cap descending (large caps first)
    targets.sort(key=lambda x: -x[1])
    log.info(f"  FMP symbols with options: {len(targets)}")

    # Filter out already-cached (fully synced) symbols
    cached_syms = set(
        f.replace("_theta.parquet", "")
        for f in os.listdir(CACHE_DIR)
        if f.endswith("_theta.parquet")
    )

    # Load existing scan dates from scan_cache.jsonl
    scan_dates_map = load_scan_dates_from_jsonl()

    # Generate weekly dates for symbols without scan_cache entries
    today = datetime.date.today()
    weekly_dates = generate_weekly_dates(START_DATE, today)
    log.info(f"  Weekly scan dates: {len(weekly_dates)} (from {START_DATE} to {today})")

    # Build final download list
    download_list = []
    for sym, mcap, band in targets:
        # Use scan_cache dates if available, otherwise weekly dates
        dates = scan_dates_map.get(sym, weekly_dates)
        dates = [d for d in dates if d >= "2019-01-01"]
        download_list.append((sym, mcap, band, dates))

    # Handle --start-from
    if args.start_from:
        start_sym = args.start_from.upper()
        idx = next((i for i, (s, _, _, _) in enumerate(download_list) if s == start_sym), None)
        if idx is not None:
            download_list = download_list[idx:]
            log.info(f"  Resuming from {start_sym} (index {idx})")
        else:
            log.warning(f"  Symbol {start_sym} not found in download list")

    if args.max_symbols > 0:
        download_list = download_list[: args.max_symbols]

    # Count how many actually need work (not fully synced)
    need_work = []
    already_synced = 0
    for sym, mcap, band, dates in download_list:
        if sym in cached_syms:
            # Check if it's fully synced
            fp = CACHE_DIR / f"{sym}_theta.parquet"
            try:
                df = pd.read_parquet(fp, columns=["scan_date"])
                existing = set(df["scan_date"].unique())
                missing = [d for d in dates if d not in existing]
                if missing:
                    need_work.append((sym, mcap, band, dates))
                else:
                    already_synced += 1
            except Exception:
                need_work.append((sym, mcap, band, dates))
        else:
            need_work.append((sym, mcap, band, dates))

    total_dates = sum(len(d) for _, _, _, d in need_work)
    total_calls = total_dates * 2  # greeks + OI per date
    est_hours = total_calls / RATE_LIMIT_RPS / 3600

    log.info(f"\n[3/4] Download Plan:")
    log.info(f"  Total targets:     {len(download_list)}")
    log.info(f"  Already synced:    {already_synced}")
    log.info(f"  Need work:         {len(need_work)}")
    log.info(f"  Total dates:       {total_dates:,}")
    log.info(f"  Est. API calls:    {total_calls:,}")
    log.info(f"  Est. time:         {est_hours:.1f} hours ({est_hours/24:.1f} days)")
    log.info(f"  Rate limit:        {RATE_LIMIT_RPS} RPS")

    # Band breakdown
    band_counts = {}
    for _, mcap, band, _ in need_work:
        b = band or ("large" if mcap >= 10e9 else "mid" if mcap >= 2e9 else "small")
        band_counts[b] = band_counts.get(b, 0) + 1
    for b in sorted(band_counts):
        log.info(f"    {b}: {band_counts[b]} symbols")

    if args.dry_run:
        log.info("\n[DRY RUN] Stopping here. No data downloaded.")
        # Show first 20 symbols
        log.info("  First 20 symbols to download:")
        for sym, mcap, band, dates in need_work[:20]:
            log.info(f"    {sym:8s} mcap={mcap/1e9:7.1f}B  dates={len(dates)}")
        return

    # 4. Download!
    log.info(f"\n[4/4] Downloading {len(need_work)} symbols...")
    progress = load_progress()
    total_downloaded = 0
    total_errors = 0
    start_time = time.time()

    for i, (sym, mcap, band, dates) in enumerate(need_work):
        elapsed = time.time() - start_time
        rate = (i / elapsed * 3600) if elapsed > 0 and i > 0 else 0
        eta_hours = ((len(need_work) - i) / rate) if rate > 0 else 0

        log.info(
            f"  [{i+1}/{len(need_work)}] {sym} "
            f"(mcap={mcap/1e9:.1f}B, {len(dates)} dates) "
            f"| elapsed={elapsed/3600:.1f}h | ETA={eta_hours:.1f}h"
        )

        try:
            result = process_symbol(client, sym, dates)
            total_downloaded += result.get("new_dates", 0)
            total_errors += result.get("errors", 0)

            log.info(
                f"    -> {result['status']}: "
                f"{result.get('new_dates', 0)}/{result.get('missing_dates', 0)} dates, "
                f"{result.get('rows', 0)} total rows"
            )

            # Track progress
            progress["completed_symbols"].append(sym)
            progress["stats"][sym] = result
            if (i + 1) % 10 == 0:
                save_progress(progress)

        except Exception as e:
            log.error(f"    -> FAILED: {e}")
            total_errors += 1

    save_progress(progress)

    elapsed = time.time() - start_time
    log.info("\n" + "=" * 60)
    log.info("EXTRACTION COMPLETE")
    log.info("=" * 60)
    log.info(f"  Symbols processed:  {len(need_work)}")
    log.info(f"  Dates downloaded:   {total_downloaded:,}")
    log.info(f"  Errors:             {total_errors}")
    log.info(f"  Total time:         {elapsed/3600:.1f} hours")
    log.info(f"  Avg per symbol:     {elapsed/max(len(need_work),1):.1f}s")


if __name__ == "__main__":
    main()
