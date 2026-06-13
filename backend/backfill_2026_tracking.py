#!/usr/bin/env python3
"""
backfill_2026_tracking.py
=========================
One-time script that replays the screener's portfolio-selection logic across
2026 to build a complete paper-tracking state (methodology_tracking.json).

Data sources (all local / GCS cached – NO live FMP API calls):
  1. Parquet rankings (Jan-Mar 2026, monthly)
  2. GCS SP500 scan archives  (Apr-May 2026, ~daily)
  3. FMP local cache for leverage gate on parquet dates
  4. Sector data from latest_global.json
  5. FMP cached historical prices for inter-rebalance returns

Usage:
    python backfill_2026_tracking.py            # full run
    python backfill_2026_tracking.py --dry-run   # print plan, don't write
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# ──────────────────────────── Configuration ──────────────────────────── #

BASE_DIR = Path(__file__).resolve().parent                         # backend/
FRONTEND_PUBLIC = BASE_DIR.parent / "frontend" / "public"
OUTPUT_PATH = FRONTEND_PUBLIC / "methodology_tracking.json"

PARQUET_ROOT = BASE_DIR / "backtest_v9" / "methodologies"
FMP_CACHE = BASE_DIR / "fmp_cache"
BALANCE_CACHE = FMP_CACHE / "balance-sheet-statement"
INCOME_CACHE = FMP_CACHE / "income-statement"
PRICE_CACHE = FMP_CACHE / "historical-price-eod"
SECTOR_FILE = FRONTEND_PUBLIC / "latest_global.json"
TEMP_SCANS_DIR = BASE_DIR / "temp_scans"

TARGET_POSITIONS = 20
MAX_PER_SECTOR = TARGET_POSITIONS // 2          # 10
EQUAL_WEIGHT = 1.0 / TARGET_POSITIONS           # 0.05
MOS_FLOOR = -1.0
LEVERAGE_LIMIT = 3.0

METHODOLOGY_PARQUET_MAP: dict[str, str] = {
    "dcf_fcff":            "intrinsic/dcf_fcff",
    "earnings_yield_gap":  "emerging/earnings_yield_gap",
    "ev_gross_profit":     "multiples/ev_gross_profit",
    "rd_capitalized_dcf":  "emerging/rd_capitalized_dcf",
    "owner_earnings":      "intrinsic/owner_earnings",
    "epv":                 "intrinsic/epv_greenwald",
    "graham_revised":      "v8fusion/graham_revised",
    "acquirers_multiple":  "multiples/acquirers_multiple",
    "iv15_deep_value":     "v8fusion/iv15_deep_value",
}

MOS_FIELD_MAP: dict[str, str] = {
    "dcf_fcff":            "dcf_fcff_mos",
    "earnings_yield_gap":  "earnings_yield_gap_mos",
    "ev_gross_profit":     "ev_gross_profit_mos",
    "rd_capitalized_dcf":  "rd_capitalized_dcf_mos",
    "owner_earnings":      "owner_earnings_mos",
    "epv":                 "epv_mos",
    "graham_revised":      "graham_revised_mos",
    "acquirers_multiple":  "acquirers_multiple_mos",
    "iv15_deep_value":     "iv15_deep_value_mos",
}

METHODOLOGY_METRIC_MAP: dict[str, str] = {
    "dcf_fcff":            "dcf_fcff_mos",
    "earnings_yield_gap":  "ey_gap",
    "ev_gross_profit":     "gp_ta",
    "rd_capitalized_dcf":  "rd_capitalized_dcf_mos",
    "owner_earnings":      "owner_earnings_mos",
    "epv":                 "epv_mos",
    "graham_revised":      "graham_revised_mos",
    "acquirers_multiple":  "acquirers_multiple",
    "iv15_deep_value":     "iv15_deep_value_mos",
}


PARQUET_DATES = ["2026-01-26", "2026-02-23", "2026-03-30"]

GCS_SP500_FILES = [
    "2026-04-17_sp500.json",
    "2026-04-18_sp500.json",
    "2026-04-19_sp500.json",
    "2026-04-20_sp500.json",
    "2026-04-21_sp500.json",
    "2026-04-22_sp500.json",
    "2026-04-23_sp500.json",
    "2026-04-24_sp500.json",
    "2026-04-25_sp500.json",
    "2026-04-26_sp500.json",
    "2026-04-28_sp500.json",
    "2026-04-29_sp500.json",
    "2026-05-01_sp500.json",
    "2026-05-03_sp500.json",
    "2026-05-04_sp500.json",
    "2026-05-05_sp500.json",
]

GCS_BUCKET = "gs://screener-signals-carbonbridge/scans"

BASELINE_RETURNS: dict[str, dict[str, float]] = {
    # Values from METHODOLOGIES_CONFIG.annualReturns in page.tsx
    # For methodologies without explicit annualReturns, we use CAGR-ratio approximation
    "dcf_fcff":           {"2021": 0.082,  "2022": -0.124, "2023": 0.075,  "2024": 0.091,  "2025": 0.055},
    "earnings_yield_gap": {"2021": 0.324,  "2022": -0.082, "2023": 0.301,  "2024": 0.345,  "2025": 0.238},
    "ev_gross_profit":    {"2021": 0.105,  "2022": -0.058, "2023": 0.100,  "2024": 0.122,  "2025": 0.103},  # CAGR ratio
    "rd_capitalized_dcf": {"2021": 0.104,  "2022": -0.058, "2023": 0.099,  "2024": 0.121,  "2025": 0.102},  # CAGR ratio
    "owner_earnings":     {"2021": 0.184,  "2022":  0.042, "2023": 0.201,  "2024": 0.225,  "2025": 0.240},
    "epv":                {"2021": 0.108,  "2022": -0.060, "2023": 0.103,  "2024": 0.125,  "2025": 0.106},  # CAGR ratio
    "graham_revised":     {"2021": 0.124,  "2022":  0.051, "2023": 0.142,  "2024": 0.160,  "2025": 0.155},
    "acquirers_multiple": {"2021": 0.117,  "2022": -0.065, "2023": 0.112,  "2024": 0.136,  "2025": 0.115},  # CAGR ratio
    "iv15_deep_value":    {"2021": 0.117,  "2022": -0.065, "2023": 0.112,  "2024": 0.136,  "2025": 0.115},  # CAGR ratio
}

log = logging.getLogger("backfill")

# ──────────────────────────── Helpers ──────────────────────────── #


def _load_json(path: Path) -> Any:
    """Load a JSON file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.debug("Could not load %s: %s", path, exc)
        return None


def _load_sector_map() -> dict[str, str]:
    """symbol -> sector from latest_global.json."""
    data = _load_json(SECTOR_FILE)
    if not data:
        log.warning("No sector file found at %s", SECTOR_FILE)
        return {}
    return {s["symbol"]: s.get("sector", "Unknown") for s in data.get("stocks", [])}


def _load_fmp_balance(sym: str) -> dict | None:
    """Return most recent balance-sheet payload entry for sym."""
    data = _load_json(BALANCE_CACHE / f"{sym}.json")
    if data and data.get("payload"):
        return data["payload"][0]
    return None


def _load_fmp_income(sym: str) -> dict | None:
    """Return most recent income-statement payload entry for sym."""
    data = _load_json(INCOME_CACHE / f"{sym}.json")
    if data and data.get("payload"):
        return data["payload"][0]
    return None


def _load_price_history(sym: str) -> dict[str, float]:
    """date-string -> close price from FMP historical cache."""
    data = _load_json(PRICE_CACHE / f"{sym}.json")
    if not data or not data.get("payload"):
        return {}
    return {entry["date"]: entry["close"] for entry in data["payload"] if "close" in entry}


def _get_price_on_date(prices: dict[str, float], date_str: str) -> float | None:
    """Return the close price on *date_str*, or the closest prior date."""
    if date_str in prices:
        return prices[date_str]
    # Try up to 7 days back for weekends / holidays
    from datetime import timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    for offset in range(1, 8):
        alt = (dt - timedelta(days=offset)).strftime("%Y-%m-%d")
        if alt in prices:
            return prices[alt]
    return None


def _latest_price(prices: dict[str, float]) -> tuple[str, float] | None:
    """Return (date, close) for the most recent date in the cache."""
    if not prices:
        return None
    latest_date = max(prices.keys())
    return (latest_date, prices[latest_date])


def _passes_leverage_gate(net_debt: float | None, ebitda: float | None) -> bool:
    """
    Return True if the stock passes the leverage gate (net_debt / ebitda < 3.0).
    If ebitda <= 0, only pass if net_debt <= 0.
    Missing data → pass (conservative).
    """
    if net_debt is None or ebitda is None:
        return True  # missing data, let it through
    if ebitda <= 0:
        return net_debt <= 0
    return (net_debt / ebitda) < LEVERAGE_LIMIT


def _lookup_metric_on_date(
    symbol: str,
    date_str: str,
    methodology_key: str,
    parquet_df: pd.DataFrame | None,
    gcs_scans: dict[str, list[dict]],
) -> float:
    """
    Look up a stock's raw ranking metric value on a specific date.
    """
    metric_field = METHODOLOGY_METRIC_MAP[methodology_key]
    
    # If it is in parquet
    if date_str in PARQUET_DATES and parquet_df is not None:
        snap = parquet_df[(parquet_df["as_of_date"] == date_str) & (parquet_df["symbol"] == symbol)]
        if not snap.empty:
            val_field = metric_field
            if val_field not in snap.columns:
                val_field = "margin_of_safety"
            return float(snap.iloc[0][val_field])
            
    # If it is in GCS scans
    elif date_str in gcs_scans:
        stocks = gcs_scans[date_str]
        for s in stocks:
            if s["symbol"] == symbol:
                return float(s.get(metric_field, s.get("margin_of_safety", 0.0)))
                
    return 0.0



# ──────────────────────── Data Loading ──────────────────────── #


def load_parquet_rankings() -> dict[str, pd.DataFrame]:
    """
    Load all methodology parquet files and filter to 2026 dates.
    Returns {methodology_key: DataFrame}.
    """
    result: dict[str, pd.DataFrame] = {}
    for mkey, subpath in METHODOLOGY_PARQUET_MAP.items():
        pq_path = PARQUET_ROOT / subpath / "rankings.parquet"
        if not pq_path.exists():
            log.warning("Parquet not found: %s", pq_path)
            continue
        df = pd.read_parquet(pq_path)
        df = df[df["as_of_date"].isin(PARQUET_DATES)].copy()
        log.info("  %s: %d rows for 2026 dates", mkey, len(df))
        result[mkey] = df
    return result


def download_gcs_scans() -> list[Path]:
    """Download SP500 scan archives from GCS if not already cached locally."""
    TEMP_SCANS_DIR.mkdir(exist_ok=True)
    paths: list[Path] = []
    for fname in GCS_SP500_FILES:
        local = TEMP_SCANS_DIR / fname
        if local.exists():
            log.debug("  Already cached: %s", fname)
        else:
            src = f"{GCS_BUCKET}/{fname}"
            log.info("  Downloading %s ...", fname)
            try:
                subprocess.run(
                    f'gsutil cp "{src}" "{local}"',
                    check=True, capture_output=True, text=True,
                    shell=True,
                )
            except subprocess.CalledProcessError as exc:
                log.error("  gsutil failed for %s: %s", fname, exc.stderr.strip())
                continue
        paths.append(local)
    return paths


def load_gcs_scans(paths: list[Path]) -> dict[str, list[dict]]:
    """
    Load downloaded scan archives.
    Returns {date_string: [stock_dict, ...]}
    """
    result: dict[str, list[dict]] = {}
    for p in paths:
        data = _load_json(p)
        if not data:
            continue
        scan_date = data.get("scan_date", "")
        if not scan_date:
            # Derive from filename: 2026-04-17_sp500.json → 2026-04-17
            scan_date = p.stem.split("_")[0]
        stocks = data.get("stocks", [])
        result[scan_date] = stocks
        log.debug("  Loaded %s: %d stocks", scan_date, len(stocks))
    return result


# ──────────────────── Portfolio Selection ──────────────────── #


def select_portfolio_parquet(
    df: pd.DataFrame,
    date_str: str,
    sector_map: dict[str, str],
) -> list[dict]:
    """
    Select top-20 from a parquet ranking snapshot for a single date.
    Returns list of {symbol, price, margin_of_safety, sector}.
    """
    snap = df[df["as_of_date"] == date_str].copy()
    if snap.empty:
        return []

    # Filter MoS floor
    snap = snap[snap["margin_of_safety"] > MOS_FLOOR]

    # Leverage gate using FMP cache
    passed_rows = []
    for _, row in snap.iterrows():
        sym = row["symbol"]
        bs = _load_fmp_balance(sym)
        inc = _load_fmp_income(sym)
        net_debt = bs["netDebt"] if bs and "netDebt" in bs else None
        ebitda = None
        if inc:
            ebitda = inc.get("ebitda")
            if ebitda is None:
                op_inc = inc.get("operatingIncome")
                da = inc.get("depreciationAndAmortization")
                if op_inc is not None and da is not None:
                    ebitda = op_inc + da
        if _passes_leverage_gate(net_debt, ebitda):
            passed_rows.append(row)

    if not passed_rows:
        return []

    # Sort by MoS desc
    passed_rows.sort(key=lambda r: r["margin_of_safety"], reverse=True)

    # Sector diversification: max MAX_PER_SECTOR per sector
    selected: list[dict] = []
    sector_counts: dict[str, int] = defaultdict(int)
    for row in passed_rows:
        if len(selected) >= TARGET_POSITIONS:
            break
        sym = row["symbol"]
        sector = sector_map.get(sym, "Unknown")
        if sector_counts[sector] >= MAX_PER_SECTOR:
            continue
        sector_counts[sector] += 1
        selected.append({
            "symbol": sym,
            "price": float(row["price"]),
            "margin_of_safety": float(row["margin_of_safety"]),
            "sector": sector,
        })

    return selected


def select_portfolio_scan(
    stocks: list[dict],
    methodology_key: str,
) -> list[dict]:
    """
    Select top-20 from a GCS scan archive for a specific methodology.
    Returns list of {symbol, price, margin_of_safety, sector}.
    """
    mos_field = MOS_FIELD_MAP[methodology_key]

    # Filter to stocks with this MoS field present
    candidates = []
    for s in stocks:
        mos = s.get(mos_field)
        if mos is None:
            continue
        if mos <= MOS_FLOOR:
            continue
        candidates.append(s)

    # Leverage gate from stock object fields
    gated = []
    for s in candidates:
        net_debt = s.get("net_debt_local")
        ebit = s.get("ebit_local")
        depreciation = s.get("depreciation_local")
        ebitda = None
        if ebit is not None and depreciation is not None:
            ebitda = ebit + depreciation
        elif ebit is not None:
            ebitda = ebit  # fallback if depreciation missing
        if _passes_leverage_gate(net_debt, ebitda):
            gated.append(s)

    # Sort by MoS desc
    gated.sort(key=lambda s: s.get(mos_field, -999), reverse=True)

    # Sector diversification
    selected: list[dict] = []
    sector_counts: dict[str, int] = defaultdict(int)
    for s in gated:
        if len(selected) >= TARGET_POSITIONS:
            break
        sector = s.get("sector", "Unknown")
        if sector_counts[sector] >= MAX_PER_SECTOR:
            continue
        sector_counts[sector] += 1
        selected.append({
            "symbol": s["symbol"],
            "price": float(s["price"]),
            "margin_of_safety": float(s.get(mos_field, 0)),
            "sector": sector,
        })

    return selected


# ──────────────────── Rebalance Tracking ──────────────────── #


def build_methodology_tracking(
    methodology_key: str,
    parquet_df: pd.DataFrame | None,
    gcs_scans: dict[str, list[dict]],
    sector_map: dict[str, str],
    all_price_cache: dict[str, dict[str, float]],
) -> dict:
    """
    Build the full tracking structure for one methodology across all 2026 dates.
    """
    # Collect all rebalance dates in order
    rebalance_dates: list[str] = []

    # Parquet dates
    for d in PARQUET_DATES:
        rebalance_dates.append(d)

    # GCS scan dates (sorted)
    gcs_dates = sorted(gcs_scans.keys())
    for d in gcs_dates:
        if d not in rebalance_dates:
            rebalance_dates.append(d)

    rebalance_dates.sort()

    rebalances: list[dict] = []
    all_exits: list[dict] = []
    prev_holdings: dict[str, dict] = {}  # symbol -> {entry_price, entry_date}
    period_returns: list[float] = []     # for YTD chaining

    for i, date_str in enumerate(rebalance_dates):
        log.debug("    %s: rebalance on %s", methodology_key, date_str)

        # Select portfolio for this date
        if date_str in PARQUET_DATES and parquet_df is not None:
            portfolio = select_portfolio_parquet(parquet_df, date_str, sector_map)
        elif date_str in gcs_scans:
            portfolio = select_portfolio_scan(gcs_scans[date_str], methodology_key)
        else:
            log.warning("    No data for %s on %s", methodology_key, date_str)
            continue

        if not portfolio:
            log.warning("    Empty portfolio for %s on %s", methodology_key, date_str)
            continue

        current_symbols = {p["symbol"] for p in portfolio}
        current_prices = {p["symbol"]: p["price"] for p in portfolio}

        # Determine entries and exits
        entries = []
        exits = []

        # Exits: stocks in prev_holdings but not in current
        for sym, info in prev_holdings.items():
            if sym not in current_symbols:
                # Get exit price: price on this date
                exit_price = current_prices.get(sym)
                if exit_price is None:
                    # Look up from price cache
                    ph = all_price_cache.get(sym, {})
                    exit_price = _get_price_on_date(ph, date_str)
                if exit_price is not None and info["entry_price"] > 0:
                    ret = (exit_price - info["entry_price"]) / info["entry_price"]
                else:
                    ret = 0.0
                    exit_price = exit_price or 0.0
                
                # Look up specific exit metric at the exit date
                exit_metric = _lookup_metric_on_date(sym, date_str, methodology_key, parquet_df, gcs_scans)
                
                exit_record = {
                    "symbol": sym,
                    "entry_price": info["entry_price"],
                    "entry_date": info["entry_date"],
                    "entry_metric": round(info.get("entry_metric", 0.0), 4),
                    "exit_price": round(exit_price, 2),
                    "exit_date": date_str,
                    "exit_metric": round(exit_metric, 4),
                    "return": round(ret, 4),
                }
                exits.append(exit_record)
                all_exits.append(exit_record)

        # Entries: stocks in current but not in prev_holdings
        for sym in current_symbols:
            if sym not in prev_holdings:
                entry_metric = _lookup_metric_on_date(sym, date_str, methodology_key, parquet_df, gcs_scans)
                entries.append({
                    "symbol": sym,
                    "price": current_prices[sym],
                    "date": date_str,
                    "entry_metric": round(entry_metric, 4),
                })

        # Compute period return for the PREVIOUS period (if there was one)
        if i > 0 and prev_holdings:
            stock_returns = []
            for sym, info in prev_holdings.items():
                # Price at this rebalance date
                price_now = current_prices.get(sym)
                if price_now is None:
                    ph = all_price_cache.get(sym, {})
                    price_now = _get_price_on_date(ph, date_str)
                price_start = info.get("period_start_price", info["entry_price"])
                if price_now is not None and price_start > 0:
                    stock_returns.append(
                        (price_now - price_start) / price_start
                    )
            if stock_returns:
                period_ret = sum(stock_returns) / len(stock_returns)
                period_returns.append(period_ret)

        # Update holdings
        new_holdings: dict[str, dict] = {}
        for p in portfolio:
            sym = p["symbol"]
            if sym in prev_holdings:
                # Continuing: preserve original entry, but set period start price
                new_holdings[sym] = {
                    "entry_price": prev_holdings[sym]["entry_price"],
                    "entry_date": prev_holdings[sym]["entry_date"],
                    "entry_metric": prev_holdings[sym]["entry_metric"],
                    "period_start_price": p["price"],
                }
            else:
                # New entry
                entry_metric = _lookup_metric_on_date(sym, date_str, methodology_key, parquet_df, gcs_scans)
                new_holdings[sym] = {
                    "entry_price": p["price"],
                    "entry_date": date_str,
                    "entry_metric": round(entry_metric, 4),
                    "period_start_price": p["price"],
                }
        prev_holdings = new_holdings

        rebalances.append({
            "date": date_str,
            "holdings": sorted(current_symbols),
            "entries": entries,
            "exits": exits,
        })


    # Final period: from last rebalance to latest available price
    if prev_holdings:
        stock_returns_final = []
        for sym, info in prev_holdings.items():
            ph = all_price_cache.get(sym, {})
            latest = _latest_price(ph)
            price_start = info.get("period_start_price", info["entry_price"])
            if latest and price_start > 0:
                _, close = latest
                stock_returns_final.append(
                    (close - price_start) / price_start
                )
        if stock_returns_final:
            final_period_ret = sum(stock_returns_final) / len(stock_returns_final)
            period_returns.append(final_period_ret)

    # YTD return: chain all period returns
    ytd = 1.0
    for pr in period_returns:
        ytd *= (1.0 + pr)
    ytd_return = ytd - 1.0

    # Build current_holdings list
    current_holdings = []
    for sym, info in sorted(prev_holdings.items()):
        current_holdings.append({
            "symbol": sym,
            "entry_price": info["entry_price"],
            "entry_date": info["entry_date"],
            "entry_metric": round(info.get("entry_metric", 0.0), 4),
            "weight": EQUAL_WEIGHT,
        })


    tracking_start = rebalance_dates[0] if rebalance_dates else None

    return {
        "rebalances": rebalances,
        "current_holdings": current_holdings,
        "all_exits_2026": all_exits,
        "ytd_return": round(ytd_return, 4),
        "tracking_start": tracking_start,
        "rebalance_count": len(rebalances),
    }


# ──────────────────── Main Pipeline ──────────────────── #


def main():
    parser = argparse.ArgumentParser(description="Backfill 2026 methodology tracking")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen, don't write files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    log.info("=" * 60)
    log.info("Backfill 2026 Methodology Tracking")
    log.info("=" * 60)

    # ── Step 1: Load sector map ──
    log.info("[1/5] Loading sector map ...")
    sector_map = _load_sector_map()
    log.info("  Loaded %d symbols with sectors", len(sector_map))

    # ── Step 2: Load parquet rankings ──
    log.info("[2/5] Loading parquet rankings ...")
    parquet_data = load_parquet_rankings()
    log.info("  Loaded %d methodologies from parquet", len(parquet_data))

    # ── Step 3: GCS scan archives ──
    # NOTE: The April-May 2026 GCS archives don't contain per-methodology MoS
    # fields (dcf_fcff_mos, etc.). Those fields were added to the screener later.
    # The tracking system will extend from the next live screener run onward.
    log.info("[3/5] Checking GCS scan archives ...")
    gcs_scans: dict[str, list[dict]] = {}
    if not args.dry_run:
        scan_paths = download_gcs_scans()
        # Only load scans that have per-methodology MoS fields
        for p in scan_paths:
            data = _load_json(p)
            if not data or not data.get("stocks"):
                continue
            sample_stock = data["stocks"][0] if data["stocks"] else {}
            if sample_stock.get("dcf_fcff_mos") is not None:
                scan_date = data.get("scan_date", p.stem.split("_")[0])
                gcs_scans[scan_date] = data["stocks"]
                log.info("  Loaded %s: %d stocks (has MoS fields)", scan_date, len(data["stocks"]))
            else:
                log.info("  Skipped %s: no per-methodology MoS fields (pre-v7.3 archive)", p.name)
    log.info("  Usable GCS scan dates: %d", len(gcs_scans))
    if not gcs_scans:
        log.info("  (This is expected — MoS fields were added after these archives were created)")
        log.info("  The tracking system will extend from the next live screener run onward.")

    # ── Step 4: Pre-load price cache for all symbols we'll encounter ──
    log.info("[4/5] Pre-loading price cache ...")
    all_symbols: set[str] = set()
    for df in parquet_data.values():
        all_symbols.update(df["symbol"].unique())
    for stocks in gcs_scans.values():
        all_symbols.update(s["symbol"] for s in stocks)
    log.info("  Universe: %d unique symbols", len(all_symbols))

    all_price_cache: dict[str, dict[str, float]] = {}
    loaded = 0
    for sym in sorted(all_symbols):
        prices = _load_price_history(sym)
        if prices:
            all_price_cache[sym] = prices
            loaded += 1
    log.info("  Loaded price histories for %d / %d symbols", loaded, len(all_symbols))

    # ── Step 5: Build tracking for each methodology ──
    log.info("[5/5] Building tracking state for %d methodologies ...",
             len(METHODOLOGY_PARQUET_MAP))

    all_rebalance_dates: set[str] = set()
    methodologies_output: dict[str, dict] = {}

    for mkey in sorted(METHODOLOGY_PARQUET_MAP.keys()):
        log.info("  Processing: %s", mkey)
        pq_df = parquet_data.get(mkey)
        tracking = build_methodology_tracking(
            mkey, pq_df, gcs_scans, sector_map, all_price_cache,
        )
        methodologies_output[mkey] = tracking
        for rb in tracking["rebalances"]:
            all_rebalance_dates.add(rb["date"])

    # ── Build baseline history — prefer the latest replay results over hardcoded ──
    # baseline_history.json is written by replay_baseline.py (the real PIT replay).
    # Use its 'equal'-weighting by_year; fall back to BASELINE_RETURNS only if absent.
    real_baseline: dict[str, dict[str, float]] = {}
    for cand in [FRONTEND_PUBLIC / "baseline_history.json", BASE_DIR / "baseline_history.json"]:
        _bh = _load_json(cand)
        if _bh and isinstance(_bh.get("methodologies"), dict):
            for mkey in METHODOLOGY_PARQUET_MAP:
                by_year = ((_bh["methodologies"].get(mkey) or {}).get("equal") or {}).get("by_year") or {}
                if by_year:
                    real_baseline[mkey] = {str(y): float(v) for y, v in by_year.items()}
            if real_baseline:
                log.info("  Baseline sourced from %s (latest replay results)", cand.name)
                break
    if not real_baseline:
        log.warning("  baseline_history.json not found/empty — falling back to hardcoded BASELINE_RETURNS")

    baseline_history: dict[str, dict[str, float]] = {}
    for year in ["2021", "2022", "2023", "2024", "2025"]:
        baseline_history[year] = {}
        for mkey in METHODOLOGY_PARQUET_MAP:
            baseline_history[year][mkey] = real_baseline.get(mkey, {}).get(year, BASELINE_RETURNS[mkey][year])

    # ── Assemble final output ──
    output = {
        "tracking_year": 2026,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rebalance_dates": sorted(all_rebalance_dates),
        "methodologies": methodologies_output,
        "baseline_history": baseline_history,
    }

    # ── Summary table ──
    log.info("")
    log.info("=" * 78)
    log.info("%-22s  %10s  %10s  %10s  %10s",
             "Methodology", "YTD Ret", "Holdings", "Exits", "Rebalances")
    log.info("-" * 78)
    for mkey in sorted(methodologies_output.keys()):
        m = methodologies_output[mkey]
        log.info("%-22s  %9.2f%%  %10d  %10d  %10d",
                 mkey,
                 m["ytd_return"] * 100,
                 len(m["current_holdings"]),
                 len(m["all_exits_2026"]),
                 m["rebalance_count"])
    log.info("=" * 78)

    if args.dry_run:
        log.info("[DRY RUN] Would write %s", OUTPUT_PATH)
        log.info("[DRY RUN] JSON payload: %d bytes",
                 len(json.dumps(output, indent=2).encode()))
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        log.info("Wrote %s (%d bytes)", OUTPUT_PATH, OUTPUT_PATH.stat().st_size)

    # GCS upload hint
    gcs_dest = "gs://screener-signals-carbonbridge/methodology_tracking.json"
    log.info("")
    log.info("To upload to GCS, run:")
    log.info("  gsutil cp %s %s", OUTPUT_PATH, gcs_dest)

    log.info("")
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
