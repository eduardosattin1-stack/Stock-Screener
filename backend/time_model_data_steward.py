#!/usr/bin/env python3
"""
Time-Model Data Steward — Builds training data for the multi-agent time model.
===============================================================================

Rebuilt to decouple from scan_cache.jsonl:
  - Generates a dense regular grid (every 5th trading day) for all symbols.
  - Computes all technical features PIT-correctly in-house from daily prices.
  - Computes PIT-correct Quality Score and sector momentum.
  - Integrates ThetaData options features + derived trailing options transforms.
  - Computes forward touch targets (p10/p20) from adjusted price data.

Output: time_model_training_data.parquet
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# Import feature library
from time_model_feature_library import compute_price_technicals, compute_pit_quality_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("TimeModel-DataSteward")

# Paths relative to this script
BACKEND = os.path.dirname(os.path.abspath(__file__))
CACHE_DATA = os.path.join(BACKEND, "Cache_Data")
THETA_DIR = os.path.join(CACHE_DATA, "Theta_Historical")
FMP_CACHE_DIR = os.path.join(BACKEND, "fmp_cache")
THETA_SYMBOLS_PATH = os.path.join(BACKEND, "theta_symbols.txt")
MANIFEST_PATH = os.path.join(BACKEND, "expanded_universe_manifest.json")

# Minimum date for ThetaData coverage
MIN_DATE = "2019-01-01"

# Conservative lag (days) applied to a fiscal period-end date when the real
# SEC filingDate is unavailable.
FILING_LAG_DAYS = 90

# Max gap (calendar days) when as-of matching a scan_date to the most recent options snapshot.
THETA_ASOF_TOLERANCE_DAYS = 7


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def safe_divide(num, den):
    if den is None or den == 0:
        return 0.0
    return float(num) / float(den)


def _load_theta_symbols(path: str) -> set:
    """Load the ThetaData universe from theta_symbols.txt."""
    symbols = set()
    if not os.path.exists(path):
        log.warning(f"theta_symbols.txt not found at {path}")
        return symbols
    for encoding in ["utf-16le", "utf-8"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
                cand = set(content.replace("\ufeff", "").strip().split())
                if cand and all(all(c.isupper() or c.isdigit() or c == '.' or c == '-' for c in s) and 1 <= len(s) <= 10 for s in cand):
                    symbols = cand
                    break
        except Exception:
            continue
    log.info(f"Loaded {len(symbols)} symbols from theta_symbols.txt")
    return symbols



def _load_universe_manifest(path: str) -> dict:
    """Load sector, industry, country, company name from manifest."""
    manifest = {}
    if not os.path.exists(path):
        log.warning(f"Manifest not found at {path}")
        return manifest
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                sym = item.get("symbol")
                if sym:
                    manifest[sym] = {
                        "sector": item.get("sector", "Unknown"),
                        "industry": item.get("industry", "Unknown"),
                        "country": item.get("country", "US"),
                        "company_name": item.get("company_name", ""),
                    }
    except Exception as e:
        log.error(f"Failed to load manifest: {e}")
    log.info(f"Loaded metadata for {len(manifest)} symbols from manifest.")
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
# FMP Fundamentals (PIT-correct)
# ─────────────────────────────────────────────────────────────────────────────
_JSON_CACHE = {}


def _get_json(path: str) -> list:
    if path not in _JSON_CACHE:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "payload" in data:
                        data = data["payload"]
                    _JSON_CACHE[path] = data if isinstance(data, list) else []
            except Exception:
                _JSON_CACHE[path] = []
        else:
            _JSON_CACHE[path] = []
    return _JSON_CACHE[path]


def _pit_records(data_list: list, scan_date: str) -> list:
    """Filter records to those available on or before scan_date (PIT-correct)."""
    valid = []
    for r in data_list:
        filing = r.get("filingDate")
        if filing:
            eff = filing
        else:
            period_end = r.get("date")
            if not period_end:
                continue
            try:
                eff = (
                    datetime.strptime(period_end[:10], "%Y-%m-%d")
                    + timedelta(days=FILING_LAG_DAYS)
                ).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
        if eff <= scan_date:
            valid.append((eff, r))
    valid.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in valid]


def extract_fundamentals(symbol: str, scan_date: str, price: float) -> dict:
    """Extract PIT-correct fundamental features for a (symbol, scan_date)."""
    feats = {}

    def _load(endpoint, flat_slug):
        hier = os.path.join(FMP_CACHE_DIR, endpoint, f"{symbol}.json")
        d = _get_json(hier)
        if d:
            return d
        flat = os.path.join(CACHE_DATA, f"{symbol}_{flat_slug}.json")
        return _get_json(flat)

    inc = _load("income-statement", "income_statement")
    bs = _load("balance-sheet-statement", "balance_sheet")
    cf = _load("cash-flow-statement", "cash_flow")
    km = _load("key-metrics", "key_metrics")

    vi = _pit_records(inc, scan_date)
    vb = _pit_records(bs, scan_date)
    vcf = _pit_records(cf, scan_date)
    vkm = _pit_records(km, scan_date)

    li = vi[0] if vi else {}
    lb = vb[0] if vb else {}
    lcf = vcf[0] if vcf else {}
    lkm = vkm[0] if vkm else {}

    revenue = li.get("revenue", 0) or 0
    net_income = li.get("netIncome", 0) or 0
    gross_profit = li.get("grossProfit", 0) or 0
    operating_income = li.get("operatingIncome", 0) or 0
    eps = li.get("eps", 0) or 0
    equity = lb.get("totalStockholdersEquity", 0) or 0
    total_assets = lb.get("totalAssets", 0) or 0
    fcf = lcf.get("freeCashFlow", 0) or 0
    shares = li.get("weightedAverageShsOutDil", 0) or li.get("weightedAverageShsOut", 0) or 0

    # Margins
    feats["f_net_margin"] = safe_divide(net_income, revenue)
    feats["f_gross_margin"] = safe_divide(gross_profit, revenue)
    feats["f_op_margin"] = safe_divide(operating_income, revenue)

    # Quality ratios
    feats["f_roe"] = min(safe_divide(net_income, equity), 1.0) if equity > 0 else 0.0
    feats["f_roa"] = safe_divide(net_income, total_assets)
    feats["f_roic"] = lkm.get("returnOnInvestedCapital") or 0.0
    feats["f_current_ratio"] = lkm.get("currentRatio") or 0.0

    # Valuation
    if price > 0 and shares > 0:
        feats["f_pe"] = safe_divide(price, safe_divide(net_income, shares)) if net_income > 0 else 0.0
        feats["f_ps"] = safe_divide(price, safe_divide(revenue, shares)) if revenue > 0 else 0.0
        feats["f_pb"] = safe_divide(price, safe_divide(equity, shares)) if equity > 0 else 0.0
    else:
        feats["f_pe"] = 0.0
        feats["f_ps"] = 0.0
        feats["f_pb"] = 0.0

    feats["f_fcf_yield"] = safe_divide(fcf, price * shares) if price > 0 and shares > 0 else 0.0
    feats["f_earnings_yield"] = safe_divide(eps, price) if price > 0 else 0.0

    # Growth (1y, 3y)
    def _growth(records, key, years):
        if len(records) > years and records[years].get(key, 0) not in (0, None):
            return safe_divide(records[0].get(key, 0), records[years].get(key, 0)) - 1
        return 0.0

    feats["f_rev_growth"] = _growth(vi, "revenue", 1)
    feats["f_eps_growth"] = _growth(vi, "eps", 1)
    feats["f_rev_growth_3y"] = _growth(vi, "revenue", 3)

    # Op margin delta (1y)
    if len(vi) > 1:
        om0 = safe_divide(vi[0].get("operatingIncome", 0), vi[0].get("revenue", 0) or 1)
        om1 = safe_divide(vi[1].get("operatingIncome", 0), vi[1].get("revenue", 0) or 1)
        feats["f_op_margin_delta"] = om0 - om1
    else:
        feats["f_op_margin_delta"] = 0.0

    # Gross margin delta
    if len(vi) > 1:
        gm0 = safe_divide(vi[0].get("grossProfit", 0), vi[0].get("revenue", 0) or 1)
        gm1 = safe_divide(vi[1].get("grossProfit", 0), vi[1].get("revenue", 0) or 1)
        feats["f_gross_margin_delta"] = gm0 - gm1
    else:
        feats["f_gross_margin_delta"] = 0.0

    # Piotroski proxy (simplified)
    piot = 0
    if net_income > 0:
        piot += 1
    if fcf > 0:
        piot += 1
    if feats["f_roa"] > 0:
        piot += 1
    if feats["f_roe"] > 0:
        piot += 1
    if feats["f_rev_growth"] > 0:
        piot += 1
    feats["f_piotroski_pit"] = piot

    # Altman Z proxy (simplified)
    ev = lkm.get("enterpriseValue", 0) or 0
    ebit = li.get("ebit", 0) or 0
    if total_assets > 0:
        wc = (lb.get("totalCurrentAssets", 0) or 0) - (lb.get("totalCurrentLiabilities", 0) or 0)
        z = (1.2 * safe_divide(wc, total_assets)
             + 1.4 * safe_divide(li.get("retainedEarnings", net_income), total_assets)
             + 3.3 * safe_divide(ebit, total_assets)
             + 0.6 * safe_divide(equity, (lb.get("totalLiabilities", 0) or 1))
             + 1.0 * safe_divide(revenue, total_assets))
        feats["f_altman_z_pit"] = min(max(z, 0), 20)
    else:
        feats["f_altman_z_pit"] = 0.0

    feats["f_debt_equity"] = safe_divide(lb.get("totalDebt", 0) or 0, equity) if equity > 0 else 0.0
    feats["f_buyback_yield"] = 0.0

    return feats


# ─────────────────────────────────────────────────────────────────────────────
# ThetaData Options Features
# ─────────────────────────────────────────────────────────────────────────────
def _process_single_symbol(sym: str) -> list:
    """Extract options features from ThetaData parquet for a single symbol. Runs in parallel."""
    cache_path = os.path.join(THETA_DIR, f"{sym}_theta.parquet")
    if not os.path.exists(cache_path):
        return []

    try:
        df = pd.read_parquet(cache_path)
        if df.empty or "scan_date" not in df.columns:
            return []

        for col in ["gamma", "open_interest", "implied_vol", "delta", "right",
                     "theta", "vega", "volume"]:
            if col not in df.columns:
                df[col] = 0.0

        mask = (df["implied_vol"] > 0)
        if "iv_error" in df.columns:
            mask &= df["iv_error"] < 0.1
        df = df[mask].copy()

        if df.empty:
            return []

        # Gamma × OI
        df["gamma_oi"] = df["gamma"].fillna(0) * df["open_interest"].fillna(0)
        df["gamma_signed"] = np.where(
            df["right"] == "CALL", df["gamma_oi"], -df["gamma_oi"]
        )

        # Per-scan_date aggregation
        sym_records = []
        for scan_dt, grp in df.groupby("scan_date"):
            row = {"symbol": sym, "scan_date": str(scan_dt)}
            row["opt_net_gamma"] = grp["gamma_signed"].sum()

            total_oi = grp["open_interest"].sum()
            total_vol = grp["volume"].sum() if "volume" in grp.columns else 0
            row["opt_total_oi"] = total_oi
            row["opt_volume_to_oi"] = safe_divide(total_vol, total_oi)

            # 25-delta skew
            puts = grp[grp["right"] == "PUT"].copy()
            calls = grp[grp["right"] == "CALL"].copy()

            put_iv_25 = None
            if not puts.empty and "delta" in puts.columns:
                puts_valid = puts.dropna(subset=["delta", "implied_vol"])
                if not puts_valid.empty:
                    puts_valid = puts_valid.copy()
                    puts_valid["dist"] = (puts_valid["delta"] - (-0.25)).abs()
                    put_iv_25 = puts_valid.loc[puts_valid["dist"].idxmin(), "implied_vol"]

            call_iv_25 = None
            if not calls.empty and "delta" in calls.columns:
                calls_valid = calls.dropna(subset=["delta", "implied_vol"])
                if not calls_valid.empty:
                    calls_valid = calls_valid.copy()
                    calls_valid["dist"] = (calls_valid["delta"] - 0.25).abs()
                    call_iv_25 = calls_valid.loc[calls_valid["dist"].idxmin(), "implied_vol"]

            row["opt_skew_25d"] = (
                float(put_iv_25 - call_iv_25)
                if put_iv_25 is not None and call_iv_25 is not None
                else 0.0
            )

            # ATM IV
            atm_iv = 0.0
            if not calls.empty:
                calls_atm = calls.dropna(subset=["delta", "implied_vol"]).copy()
                if not calls_atm.empty:
                    calls_atm["dist_50"] = (calls_atm["delta"] - 0.50).abs()
                    atm_iv = float(calls_atm.loc[calls_atm["dist_50"].idxmin(), "implied_vol"])
            row["opt_atm_iv"] = atm_iv

            # ATM Greeks
            if not calls.empty:
                calls_atm2 = calls.dropna(subset=["delta"]).copy()
                if not calls_atm2.empty:
                    calls_atm2["dist_50"] = (calls_atm2["delta"] - 0.50).abs()
                    atm_row = calls_atm2.loc[calls_atm2["dist_50"].idxmin()]
                    row["opt_atm_vega"] = float(atm_row.get("vega", 0) or 0)
                    row["opt_atm_theta"] = float(atm_row.get("theta", 0) or 0)
                else:
                    row["opt_atm_vega"] = 0.0
                    row["opt_atm_theta"] = 0.0
            else:
                row["opt_atm_vega"] = 0.0
                row["opt_atm_theta"] = 0.0

            sym_records.append(row)

        # Trailing transforms (strictly past options captures)
        if sym_records:
            df_sym = pd.DataFrame(sym_records).sort_values("scan_date")
            
            # Trailing 252 capture days IV rank
            df_sym["f_opt_iv_rank"] = df_sym["opt_atm_iv"].rolling(252, min_periods=1).rank(pct=True)
            
            # IV Momentum
            df_sym["f_opt_iv_momentum"] = df_sym["opt_atm_iv"].diff(5).fillna(0.0)
            
            # Skew Z-score (trailing 252d)
            mean_skew = df_sym["opt_skew_25d"].rolling(252, min_periods=1).mean()
            std_skew = df_sym["opt_skew_25d"].rolling(252, min_periods=1).std().replace(0.0, np.nan)
            df_sym["f_opt_skew_z"] = ((df_sym["opt_skew_25d"] - mean_skew) / std_skew).fillna(0.0)
            
            # Gamma OI interaction
            df_sym["f_opt_gamma_oi_x"] = df_sym["opt_net_gamma"] * df_sym["opt_volume_to_oi"]
            
            return df_sym.to_dict("records")

    except Exception as e:
        log.debug(f"Failed theta extraction for {sym}: {e}")
        return []

    return []


def extract_theta_features(symbols: list) -> pd.DataFrame:
    """Extract options features from ThetaData parquets for all symbols, with trailing transforms (Parallel)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    
    all_records = []
    
    # We have 20 cores, use up to 12 workers to process in parallel
    max_workers = min(12, os.cpu_count() or 4)
    log.info(f"Extracting ThetaData options features in parallel using {max_workers} processes...")
    
    total = len(symbols)
    completed = 0
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_single_symbol, sym): sym for sym in symbols}
        
        for future in as_completed(futures):
            sym = futures[future]
            try:
                records = future.result()
                if records:
                    all_records.extend(records)
            except Exception as e:
                log.error(f"Error processing symbol {sym}: {e}")
            
            completed += 1
            if completed % 200 == 0 or completed == total:
                log.info(f"  ThetaData options progress: {completed}/{total} symbols processed")

    if not all_records:
        log.warning("No ThetaData features extracted!")
        return pd.DataFrame()

    df_theta = pd.DataFrame(all_records)
    df_theta["scan_date"] = df_theta["scan_date"].astype(str)
    log.info(
        f"Extracted ThetaData features: {len(df_theta)} rows, "
        f"{df_theta['symbol'].nunique()} symbols"
    )
    return df_theta


# ─────────────────────────────────────────────────────────────────────────────
# Forward-Looking Targets
# ─────────────────────────────────────────────────────────────────────────────
_PRICE_CACHE = {}


def _load_prices(symbol: str) -> list:
    """Load daily prices from FMP cache, sorted chronologically."""
    if symbol in _PRICE_CACHE:
        return _PRICE_CACHE[symbol]

    hier = os.path.join(FMP_CACHE_DIR, "historical-price-eod", f"{symbol}.json")
    data = _get_json(hier)
    if not data:
        flat = os.path.join(CACHE_DATA, f"{symbol}_historical_price.json")
        data = _get_json(flat)

    if not data:
        _PRICE_CACHE[symbol] = []
        return []

    prices = []
    for d in data:
        close = d.get("close") or d.get("adjClose")
        if close and float(close) > 0:
            prices.append({
                "date": d.get("date", ""),
                "close": float(close),
                "high": float(d.get("high", close) or close),
                "low": float(d.get("low", close) or close),
                "volume": float(d.get("volume", 0.0) or 0.0),
            })

    prices.sort(key=lambda x: x["date"])
    _PRICE_CACHE[symbol] = prices
    return prices


def _evict_symbol_cache(symbol: str) -> None:
    for k in list(_JSON_CACHE.keys()):
        base = os.path.basename(k)
        if base == f"{symbol}.json" or base.startswith(f"{symbol}_"):
            _JSON_CACHE.pop(k, None)
    _PRICE_CACHE.pop(symbol, None)


def compute_targets(entry_price: float, daily_after: list) -> dict:
    """Forward touch targets over the 60 forward TRADING bars (entry bar
    excluded; daily_after[0] is the first bar after entry).

    bars_to_10pct / bars_to_20pct are 1-INDEXED first-touch bars (bar 1 =
    first bar after entry; -1 if never touched within 60 bars), so
    bars_to_Xpct == days_to_Xpct + 1. By construction:
      hit_10pct_60d == (1 <= bars_to_10pct <= 60)
      hit_20pct_60d == (1 <= bars_to_20pct <= 60)
    (days_to_20pct, 0-indexed, is kept for backward compatibility.)
    """
    result = {
        "hit_10pct_30d": 0,
        "hit_10pct_60d": 0,
        "hit_20pct_30d": 0,
        "hit_20pct_60d": 0,
        "max_dd_30d": 0.0,
        "max_dd_60d": 0.0,
        "days_to_20pct": -1,
        "bars_to_10pct": -1,
        "bars_to_20pct": -1,
        "max_gain_60d": 0.0,
    }

    if not daily_after or entry_price <= 0:
        return result

    max_dd_30 = 0.0
    max_dd_60 = 0.0
    found_10 = False
    found_20 = False

    for i, bar in enumerate(daily_after):
        if i >= 60:
            break

        high_gain = (bar["high"] - entry_price) / entry_price * 100
        low_gain = (bar["low"] - entry_price) / entry_price * 100
        close_gain = (bar["close"] - entry_price) / entry_price * 100

        worst = min(close_gain, low_gain)
        if i < 30 and worst < max_dd_30:
            max_dd_30 = worst
        if worst < max_dd_60:
            max_dd_60 = worst

        best = max(close_gain, high_gain)
        if best > result["max_gain_60d"]:
            result["max_gain_60d"] = best

        if i < 30:
            if high_gain >= 10:
                result["hit_10pct_30d"] = 1
            if high_gain >= 20:
                result["hit_20pct_30d"] = 1

        if high_gain >= 10:
            result["hit_10pct_60d"] = 1
            if not found_10:
                result["bars_to_10pct"] = i + 1
                found_10 = True
        if high_gain >= 20:
            result["hit_20pct_60d"] = 1
            if not found_20:
                result["days_to_20pct"] = i
                result["bars_to_20pct"] = i + 1
                found_20 = True

    result["max_dd_30d"] = round(max_dd_30, 2)
    result["max_dd_60d"] = round(max_dd_60, 2)
    result["max_gain_60d"] = round(result["max_gain_60d"], 2)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main Build Pipeline
# ─────────────────────────────────────────────────────────────────────────────
class TimeModelDataSteward:
    def __init__(
        self,
        symbols_path: str = THETA_SYMBOLS_PATH,
        manifest_path: str = MANIFEST_PATH,
        output_path: str = "time_model_training_data.parquet",
    ):
        self.symbols_path = symbols_path
        self.manifest_path = manifest_path
        self.output_path = os.path.join(BACKEND, output_path)

    def build(self) -> str:
        log.info("=" * 70)
        log.info("  TIME MODEL DATA STEWARD — Building Training Data (Dense Panel)")
        log.info("=" * 70)

        # 1. Load universe
        theta_syms = _load_theta_symbols(self.symbols_path)
        if not theta_syms:
            log.error("No symbols loaded from theta_symbols.txt — aborting.")
            sys.exit(1)

        manifest = _load_universe_manifest(self.manifest_path)

        # 2. Build the Dense regular grid (Every 5th trading day)
        log.info("\n── Step 1: Generating Dense Regular Grid & Price Technicals ──")
        grid_rows = []
        
        symbols = list(theta_syms)
        total_syms = len(symbols)
        processed = 0

        for sym in symbols:
            prices = _load_prices(sym)
            if not prices or len(prices) < 252 + 60:
                # Need at least 252 prior bars and 60 forward bars
                _evict_symbol_cache(sym)
                continue
                
            df_prices = pd.DataFrame(prices)
            # Vectorized indicators calculation
            df_prices = compute_price_technicals(df_prices)
            
            # Find the indices of trading days >= 252 and with >= 60 days forward
            N = len(df_prices)
            valid_indices = []
            for i in range(252, N - 60):
                row_date = df_prices.iloc[i]["date"]
                if row_date >= MIN_DATE:
                    valid_indices.append(i)
            
            # Sample every 5th day
            sampled_i = valid_indices[::5]
            
            # Get metadata from manifest
            meta = manifest.get(sym, {"sector": "Unknown", "industry": "Unknown", "country": "US"})
            
            for idx in sampled_i:
                row_price = df_prices.iloc[idx]
                
                # Forward price window for targets
                forward_bars = prices[idx + 1 : idx + 61]
                targets = compute_targets(row_price["close"], forward_bars)
                
                features = {
                    "symbol": sym,
                    "scan_date": row_price["date"],
                    "price": float(row_price["close"]),
                    "sector": meta["sector"],
                    "industry": meta["industry"],
                    "country": meta["country"],
                    
                    # Technical features
                    "f_rsi": float(row_price["f_rsi"]),
                    "f_trend_strength": float(row_price["f_trend_strength"]),
                    "f_momentum_20d": float(row_price["f_momentum_20d"]),
                    "f_momentum_1m": float(row_price["f_momentum_1m"]),
                    "f_momentum_3m": float(row_price["f_momentum_3m"]),
                    "f_momentum_6m": float(row_price["f_momentum_6m"]),
                    "f_momentum_12m": float(row_price["f_momentum_12m"]),
                    "f_prox_raw": float(row_price["f_prox_raw"]),
                    "f_dist_52w_high": float(row_price["f_dist_52w_high"]),
                    "f_dist_52w_low": float(row_price["f_dist_52w_low"]),
                    "f_vol_20d": float(row_price["f_vol_20d"]),
                    "f_vol_60d": float(row_price["f_vol_60d"]),
                    "f_volume_trend": float(row_price["f_volume_trend"]),
                }
                # Add targets
                features.update(targets)
                features["target_valid"] = 1
                
                grid_rows.append(features)
                
            _evict_symbol_cache(sym)
            processed += 1
            if processed % 200 == 0 or processed == total_syms:
                log.info(f"  Prices & technicals: {processed}/{total_syms} symbols processed")

        df = pd.DataFrame(grid_rows)
        log.info(f"Generated regular grid: {len(df)} rows, {df['symbol'].nunique()} symbols")

        if df.empty:
            log.error("Grid is empty — aborting.")
            sys.exit(1)

        # 3. Extract FMP fundamentals (PIT-correct)
        log.info("\n── Step 2: Extracting FMP Fundamentals (PIT) ──")
        fund_records = []
        symbols_present = df["symbol"].unique()
        total_p = len(symbols_present)
        
        for i, sym in enumerate(symbols_present):
            sym_df = df[df["symbol"] == sym]
            for _, row in sym_df.iterrows():
                feats = extract_fundamentals(sym, row["scan_date"], row["price"])
                feats["_idx"] = row.name
                fund_records.append(feats)
            _evict_symbol_cache(sym)
            if (i + 1) % 200 == 0 or (i + 1) == total_p:
                log.info(f"  Fundamentals: {i + 1}/{total_p} symbols extracted")

        df_fund = pd.DataFrame(fund_records).set_index("_idx")
        df = df.join(df_fund)
        log.info(f"  Joined {len(df_fund.columns)} fundamental features")

        # Compute PIT Quality Score and interactions
        log.info("\n── Step 3: Computing PIT Quality Scores and Technical Interactions ──")
        df["f_quality"] = compute_pit_quality_score(df)
        
        df["f_rsi_x_quality"] = ((100.0 - df["f_rsi"]) / 100.0) * df["f_quality"]
        df["f_rsi_x_revgrow"] = ((100.0 - df["f_rsi"]) / 100.0) * df["f_rev_growth"].fillna(0.0).clip(upper=2.0)
        df["f_roe_over_pb"] = np.where(df["f_pb"].fillna(0.0) > 0, df["f_roe"].fillna(0.0) / df["f_pb"].fillna(1.0), 0.0)
        df["f_momentum_abs"] = df["f_momentum_20d"].abs()
        df["f_drawdown"] = 1.0 - df["f_prox_raw"]

        # 4. Extract ThetaData options features
        log.info("\n── Step 4: Extracting and Merging ThetaData Options Features ──")
        df_theta = extract_theta_features(symbols)

        if not df_theta.empty:
            df["scan_date_dt"] = pd.to_datetime(df["scan_date"], errors="coerce")
            df["_row_id"] = np.arange(len(df))

            df_theta_m = df_theta.copy()
            df_theta_m["scan_date_dt"] = pd.to_datetime(df_theta_m["scan_date"], errors="coerce")
            df_theta_m = (
                df_theta_m.dropna(subset=["scan_date_dt"])
                          .drop(columns=["scan_date"])
                          .sort_values("scan_date_dt")
                          .reset_index(drop=True)
            )

            df = (
                pd.merge_asof(
                    df.sort_values("scan_date_dt"),
                    df_theta_m,
                    on="scan_date_dt",
                    by="symbol",
                    direction="backward",
                    tolerance=pd.Timedelta(days=THETA_ASOF_TOLERANCE_DAYS),
                )
                .sort_values("_row_id")
                .reset_index(drop=True)
            )
            df.drop(columns=["scan_date_dt", "_row_id"], inplace=True)

            opt_cols = [c for c in df.columns if c.startswith("opt_") or c.startswith("f_opt_")]
            for c in opt_cols:
                df[c] = df[c].fillna(0.0)

            matched = int((df[opt_cols].abs().sum(axis=1) > 0).sum()) if opt_cols else 0
            log.info(
                f"  Joined {len(opt_cols)} options features via merge_asof; "
                f"{matched}/{len(df)} rows ({matched / max(len(df), 1):.1%}) matched options"
            )
            del df_theta, df_theta_m
        else:
            log.warning("  No ThetaData options features found — setting options columns to 0.0")
            for col in [
                "opt_net_gamma", "opt_total_oi", "opt_volume_to_oi",
                "opt_skew_25d", "opt_atm_iv", "opt_atm_vega", "opt_atm_theta",
                "f_opt_iv_rank", "f_opt_iv_momentum", "f_opt_skew_z", "f_opt_gamma_oi_x",
            ]:
                df[col] = 0.0

        # 5. Compute Cross-Sectional Sector Momentum (PIT-safe median)
        log.info("\n── Step 5: Computing Cross-Sectional Sector Momentum ──")
        # Sector median of 3-month momentum for each scan date
        sector_medians = df.groupby(["scan_date", "sector"])["f_momentum_3m"].median().reset_index()
        sector_medians.rename(columns={"f_momentum_3m": "f_sector_momentum"}, inplace=True)
        df = pd.merge(df, sector_medians, on=["scan_date", "sector"], how="left")
        df["f_sector_momentum"] = df["f_sector_momentum"].fillna(0.0)

        # 6. Compute within-date percentile ranks (PIT-safe)
        log.info("\n── Step 6: Computing Within-Date Percentile Ranks ──")
        for col, rank_col in [
            ("f_momentum_20d", "f_momentum_20d_rank"),
            ("f_rsi", "f_rsi_rank"),
            ("f_pb", "f_pb_rank"),
            ("f_quality", "f_quality_rank"),
            ("f_rev_growth", "f_rev_growth_rank"),
            ("f_roe", "f_roe_rank"),
            ("f_sector_momentum", "f_upside_rank"),  # Map sector momentum to upside rank as PIT proxy
        ]:
            if col in df.columns:
                df[rank_col] = df.groupby("scan_date")[col].rank(pct=True, na_option="keep")
            else:
                df[rank_col] = 0.5
            df[rank_col] = df[rank_col].fillna(0.5)

        # 7. Finalize and Save
        df = df[df["target_valid"] == 1].copy()
        df.drop(columns=["target_valid"], inplace=True)
        
        # Fill missing values: numeric columns with 0.0, non-numeric with 'Unknown'
        import pandas.api.types as ptypes
        for col in df.columns:
            if ptypes.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(0.0)
            else:
                df[col] = df[col].fillna("Unknown")

        # Downcast float64 to float32
        float_cols = df.select_dtypes(include=["float64"]).columns
        df[float_cols] = df[float_cols].astype("float32")

        # Save atomically
        tmp_path = self.output_path + ".tmp"
        df.to_parquet(tmp_path, engine="pyarrow", index=False)
        os.replace(tmp_path, self.output_path)

        universe_n = len(theta_syms)
        covered_n = df["symbol"].nunique()
        coverage = covered_n / max(universe_n, 1)

        log.info("\n" + "=" * 70)
        log.info(f"  Training data saved: {self.output_path}")
        log.info(f"  Shape: {df.shape}")
        log.info(f"  Symbols: {covered_n}/{universe_n} universe ({coverage:.1%} coverage)")
        log.info(f"  Date range: {df['scan_date'].min()} → {df['scan_date'].max()}")
        log.info("=" * 70)

        for t in ["hit_10pct_30d", "hit_10pct_60d", "hit_20pct_30d", "hit_20pct_60d"]:
            if t in df.columns:
                rate = df[t].mean()
                log.info(f"  {t}: {rate:.1%} positive rate ({int(df[t].sum())}/{len(df)})")
        log.info("=" * 70)

        return self.output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Time Model Data Steward")
    parser.add_argument("--symbols", default=THETA_SYMBOLS_PATH)
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--output", default="time_model_training_data.parquet")
    args = parser.parse_args()

    steward = TimeModelDataSteward(
        symbols_path=args.symbols,
        manifest_path=args.manifest,
        output_path=args.output,
    )
    steward.build()
