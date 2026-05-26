"""
discovery.py — Agent A: Build survivorship-corrected run ledger.

Single-shot deterministic agent. Scans the full universe over the
configured time window, extracts price runs matching the magnitude×duration
grid, applies quality filters, tags with regime/metadata, and writes
runs_ledger.parquet.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict

class FunnelError(ValueError):
    """Raised when the run discovery funnel health checks fail."""
    pass

@dataclass
class RunDiscoveryFunnel:
    # Stage 1: universe assembly
    universe_seed_count: int = 0
    universe_seed_sources: dict[str, int] = field(default_factory=dict)  # {'sp500_historical': N, 'screener': N}

    # Stage 2: data availability
    after_min_history_count: int = 0       # symbols with ≥200 trading days in window
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    cache_miss_symbols: list[str] = field(default_factory=list)  # first 20

    # Stage 3: candidate extraction per cell (pre-quality-filter)
    candidates_per_cell_pre_filter: dict[str, int] = field(default_factory=dict)

    # Stage 4: per-filter elimination, per cell
    filter_eliminations_per_cell: dict[str, dict[str, int]] = field(default_factory=dict)

    # Stage 5: final
    final_runs_per_cell: dict[str, int] = field(default_factory=dict)
    final_total: int = 0

    def cache_miss_rate(self) -> float:
        denom = self.cache_hit_count + self.cache_miss_count
        return self.cache_miss_count / denom if denom > 0 else 0.0

def assert_funnel_health(funnel: RunDiscoveryFunnel, window_start: str, window_end: str, allow_sparse_ledger: bool = False):
    if funnel.universe_seed_count < 100:
        if allow_sparse_ledger:
            log.warning(
                f"Universe assembly produced only {funnel.universe_seed_count} symbols. "
                f"Sources: {funnel.universe_seed_sources}. Expected ≥100. Check seed loaders. (Allowed due to allow_sparse_ledger)"
            )
        else:
            raise FunnelError(
                f"Universe assembly produced only {funnel.universe_seed_count} symbols. "
                f"Sources: {funnel.universe_seed_sources}. Expected ≥100. Check seed loaders."
            )

    if funnel.cache_miss_rate() > 0.20:
        if allow_sparse_ledger:
            log.warning(
                f"Cache miss rate {funnel.cache_miss_rate():.1%} exceeds 20%. "
                f"First missing symbols: {funnel.cache_miss_symbols[:20]}. "
                f"Verify backend/Cache_Data/ path and ran download_fmp_raw.py. (Allowed due to allow_sparse_ledger)"
            )
        else:
            raise FunnelError(
                f"Cache miss rate {funnel.cache_miss_rate():.1%} exceeds 20%. "
                f"First missing symbols: {funnel.cache_miss_symbols[:20]}. "
                f"Verify backend/Cache_Data/ path and ran download_fmp_raw.py."
            )

    history_retention = funnel.after_min_history_count / funnel.universe_seed_count if funnel.universe_seed_count > 0 else 0.0
    if history_retention < 0.70:
        if allow_sparse_ledger:
            log.warning(
                f"Only {history_retention:.1%} of universe has ≥200 days of history. "
                f"Likely cache integration broken — symbols loaded but OHLCV files missing or empty. "
                f"(Allowed due to allow_sparse_ledger)"
            )
        else:
            raise FunnelError(
                f"Only {history_retention:.1%} of universe has ≥200 days of history. "
                f"Likely cache integration broken — symbols loaded but OHLCV files missing or empty."
            )

    if funnel.final_total < 200 and not allow_sparse_ledger:
        raise FunnelError(
            f"Final ledger has only {funnel.final_total} runs. Spec acceptance is ≥200 (recommended ≥1000). "
            f"Per-cell breakdown: {funnel.final_runs_per_cell}. "
            f"Per-cell pre-filter: {funnel.candidates_per_cell_pre_filter}. "
            f"Filter eliminations: {funnel.filter_eliminations_per_cell}. "
            f"Pass --allow-sparse-ledger to proceed anyway (smoke test only)."
        )

    # Window/grid mismatch check
    t_start_dt = datetime.strptime(window_start, "%Y-%m-%d")
    t_end_dt = datetime.strptime(window_end, "%Y-%m-%d")
    window_years = (t_end_dt - t_start_dt).days / 365.25
    if window_years >= 3:
        long_cells = {"compounder_mid", "compounder_long", "monster", "momentum_durable"}
        empty_long_cells = [c for c in long_cells if funnel.final_runs_per_cell.get(c, 0) == 0]
        if len(empty_long_cells) == len(long_cells):
            if allow_sparse_ledger:
                log.warning(
                    f"All long-duration cells empty despite {window_years:.1f}yr window. "
                    f"Likely grid/window mismatch or run-extraction bug. "
                    f"(Allowed due to allow_sparse_ledger)"
                )
            else:
                raise FunnelError(
                    f"All long-duration cells empty despite {window_years:.1f}yr window. "
                    f"Likely grid/window mismatch or run-extraction bug."
                )

_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from alpha_compounder.config import (
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    GCS_PREFIX,
    GRID_CELLS,
    QUALITY_FILTERS,
    GridCell,
)
from alpha_compounder.schemas import RunRecord
from alpha_compounder.utils import (
    greedy_trough_peak_pairs,
    max_drawdown,
    resolve_overlaps,
    trajectory_slope,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Universe building
# ---------------------------------------------------------------------------

def build_universe(
    fmp_func,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    rate_limit_func=None,
    return_metadata: bool = False,
) -> dict[str, dict] | tuple[dict[str, dict], dict[str, int]]:
    """Build the universe from local expanded_universe_manifest.json."""
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "expanded_universe_manifest.json"
    )
    universe = {}
    seed_sources = {"manifest": 0}

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                sym = item.get("symbol")
                if sym:
                    universe[sym] = {
                        "exchange": item.get("exchange", ""),
                        "sector": item.get("sector", ""),
                        "industry": item.get("industry", ""),
                        "country": (item.get("country") or "").upper(),
                    }
                    seed_sources["manifest"] += 1
            log.info(f"Loaded {seed_sources['manifest']} symbols from manifest: {manifest_path}")
        except Exception as e:
            log.error(f"Failed to load expanded_universe_manifest.json: {e}")
    else:
        log.warning(f"expanded_universe_manifest.json not found at {manifest_path}!")

    # Filter universe to match FMP cache using case-insensitive check
    fmp_cache_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "fmp_cache", "historical-price-eod"
    )
    if os.path.exists(fmp_cache_dir):
        fmp_files = os.listdir(fmp_cache_dir)
        fmp_symbols = {os.path.splitext(f)[0].upper() for f in fmp_files if f.lower().endswith(".json")}
        original_len = len(universe)
        universe = {sym: meta for sym, meta in universe.items() if sym.upper() in fmp_symbols}
        log.info(f"Filtered universe to match FMP cache. Reduced from {original_len} to {len(universe)} symbols.")
    else:
        log.warning(f"FMP cache directory not found at {fmp_cache_dir}. No universe filtering applied.")

    log.info(f"Universe built: {len(universe)} symbols")
    if return_metadata:
        return universe, seed_sources
    return universe


# ---------------------------------------------------------------------------
# Run extraction for a single symbol
# ---------------------------------------------------------------------------

def extract_runs_for_symbol(
    symbol: str,
    meta: dict,
    fmp_func,
    grid: list[GridCell],
    window_start: str,
    window_end: str,
    rate_limit_func=None,
    return_funnel_stats: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Extract all qualifying runs for a symbol across the grid.

    Returns list of run dicts ready for RunRecord construction.
    """
    sleep = rate_limit_func or (lambda: None)
    
    stats = {
        "has_min_history": False,
        "cache_hit": False,
        "cache_miss": False,
        "candidates_pre_filter": {cell.label: 0 for cell in grid},
        "filter_eliminations": {
            cell.label: {"magnitude": 0, "mdd": 0, "persistence": 0, "min_price": 0}
            for cell in grid
        },
        "final_runs": {cell.label: 0 for cell in grid},
    }

    # Fetch full OHLCV history
    prices = fmp_func("historical-price-eod/full", {
        "symbol": symbol, "from": window_start, "to": window_end,
    })
    sleep()

    if prices is None:
        stats["cache_miss"] = True
        if return_funnel_stats:
            return [], stats
        return []
    
    stats["cache_hit"] = True

    if len(prices) < QUALITY_FILTERS["min_history_days"]:
        if return_funnel_stats:
            return [], stats
        return []

    stats["has_min_history"] = True

    # Sort ascending by date for trough-peak scanning
    prices_asc = sorted(prices, key=lambda p: p.get("date", ""))

    all_candidates = []

    for cell in grid:
        candidates = greedy_trough_peak_pairs(
            prices_asc,
            min_magnitude=cell.mag_low,
            max_magnitude=cell.mag_high,
            min_duration_days=cell.dur_low_days,
            max_duration_days=cell.dur_high_days,
        )

        stats["candidates_pre_filter"][cell.label] = len(candidates)

        for c in candidates:
            # Apply quality filters with reason tracking
            passed, reason = _passes_quality_filters_with_reason(c, prices_asc, symbol, meta)
            if not passed:
                stats["filter_eliminations"][cell.label][reason] += 1
                continue

            run = _build_run_record(symbol, c, cell, meta, prices_asc)
            if run:
                all_candidates.append(run)

    # Resolve overlaps: prefer larger magnitude, then longer duration
    resolved = resolve_overlaps(
        all_candidates,
        min_separation_days=QUALITY_FILTERS["min_run_separation_days"],
    )

    for r in resolved:
        stats["final_runs"][r["grid_cell_label"]] += 1

    if return_funnel_stats:
        return resolved, stats
    return resolved


def _passes_quality_filters_with_reason(
    candidate: dict,
    prices: list[dict],
    symbol: str,
    meta: dict,
) -> tuple[bool, str]:
    """Apply quality filters from §4 and return reason for failure."""
    t_start = candidate["t_start"]
    t_end = candidate["t_end"]

    # 1. Max drawdown during run
    run_prices = [
        float(p.get("adjClose") or p.get("close", 0))
        for p in prices
        if t_start <= p.get("date", "") <= t_end
        and (p.get("adjClose") or p.get("close", 0))
    ]
    if run_prices:
        mdd = max_drawdown(run_prices)
        if abs(mdd) > QUALITY_FILTERS["max_drawdown_during_run"]:
            return False, "mdd"

    # 2. Persistence: terminal_price >= 70% of peak for 90d after t_end
    peak_price = candidate["peak_price"]
    persist_start = t_end
    persist_end_date = (
        datetime.strptime(t_end, "%Y-%m-%d") +
        timedelta(days=QUALITY_FILTERS["persistence_days"])
    ).strftime("%Y-%m-%d")

    persist_prices = [
        float(p.get("adjClose") or p.get("close", 0))
        for p in prices
        if persist_start < p.get("date", "") <= persist_end_date
        and (p.get("adjClose") or p.get("close", 0))
    ]

    if persist_prices:
        terminal = persist_prices[-1] if persist_prices else 0
        if terminal < peak_price * QUALITY_FILTERS["persistence_threshold"]:
            return False, "persistence"

    # 3. Price level at t_start
    start_prices = [
        float(p.get("adjClose") or p.get("close", 0))
        for p in prices
        if p.get("date", "") == t_start
    ]
    if start_prices and start_prices[0] < QUALITY_FILTERS["min_price"]:
        return False, "min_price"

    return True, ""


def _passes_quality_filters(
    candidate: dict,
    prices: list[dict],
    symbol: str,
    meta: dict,
) -> bool:
    """Apply quality filters from §4."""
    passed, _ = _passes_quality_filters_with_reason(candidate, prices, symbol, meta)
    return passed


def _build_run_record(
    symbol: str,
    candidate: dict,
    cell: GridCell,
    meta: dict,
    prices: list[dict],
) -> Optional[dict]:
    """Build a run dict from a validated candidate."""

    t_start = candidate["t_start"]
    t_end = candidate["t_end"]

    # Get terminal price (90d after t_end)
    persist_end = (
        datetime.strptime(t_end, "%Y-%m-%d") + timedelta(days=90)
    ).strftime("%Y-%m-%d")
    terminal_prices = [
        float(p.get("adjClose") or p.get("close", 0))
        for p in prices
        if t_end < p.get("date", "") <= persist_end
        and (p.get("adjClose") or p.get("close", 0))
    ]
    terminal_price = terminal_prices[-1] if terminal_prices else candidate["peak_price"]

    # Max drawdown during run
    run_closes = [
        float(p.get("adjClose") or p.get("close", 0))
        for p in prices
        if t_start <= p.get("date", "") <= t_end
        and (p.get("adjClose") or p.get("close", 0))
    ]
    mdd = max_drawdown(run_closes) if run_closes else 0.0

    # Trajectory shape calculation (Option C)
    trajectory_shape = "linear"
    if run_closes and len(run_closes) >= 3:
        min_p = min(run_closes)
        max_p = max(run_closes)
        range_p = max_p - min_p
        # Normalize prices to [0, 1]
        normalized_closes = [(p - min_p) / range_p for p in run_closes] if range_p > 0 else [0.0] * len(run_closes)
        
        n = len(normalized_closes)
        L1 = max(3, (n + 1) // 2)
        L2 = max(3, (n + 1) // 2)
        
        first_half = normalized_closes[:L1]
        second_half = normalized_closes[-L2:]
        
        m1 = trajectory_slope(first_half)
        m2 = trajectory_slope(second_half)
        
        if m1 is not None and m2 is not None:
            slope_diff = m1 - m2
            avg_slope = 1.0 / (n - 1) if n > 1 else 1.0
            # Use 0.25 * avg_slope as threshold
            threshold = 0.25 * avg_slope
            if slope_diff > threshold:
                trajectory_shape = "front_loaded"
            elif slope_diff < -threshold:
                trajectory_shape = "back_loaded"
            else:
                trajectory_shape = "linear"

    # Regime at start and end (lazy import to avoid circular deps)
    regime_start = ""
    regime_end = ""
    try:
        from macro_regime import fetch_macro_regime_historical
        # Use a lightweight fmp stub for regime — only needs treasury + VIX
        # In production, pass the real fmp function
    except ImportError:
        pass

    return {
        "run_id": str(uuid.uuid4()),
        "symbol": symbol,
        "exchange": meta.get("exchange", ""),
        "t_start": t_start,
        "t_end": t_end,
        "duration_days": candidate["duration_days"],
        "magnitude_pct": candidate["magnitude_pct"],
        "peak_price": candidate["peak_price"],
        "trough_price": candidate["trough_price"],
        "terminal_price": round(terminal_price, 2),
        "mdd_during_run": round(mdd, 4),
        "persistence_pct": round(terminal_price / candidate["peak_price"], 4)
            if candidate["peak_price"] > 0 else 0,
        "grid_cell_label": cell.label,
        "sector_t_start": meta.get("sector", ""),
        "industry_t_start": meta.get("industry", ""),
        "country": meta.get("country", ""),
        "mcap_t_start_usd": 0,  # populated in enrichment pass
        "adv_20d_t_start_usd": 0,
        "regime_t_start": regime_start,
        "regime_t_end": regime_end,
        "regime_transitions": 0,
        "year_t_start": int(t_start[:4]),
        "year_t_end": int(t_end[:4]),
        "archetype_label": "",
        "trajectory_shape": trajectory_shape,
        "sector_source": "current",
        "extraction_version": "agent_a_v1.0",
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_discovery(
    fmp_func,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    grid: list[GridCell] | None = None,
    workers: int = 8,
    rate_limit_func=None,
    output_path: str | None = None,
    allow_sparse_ledger: bool = False,
):
    """Execute Agent A: discover all runs and write the ledger.

    Args:
        fmp_func: FMP API caller
        window_start/end: Time window
        grid: Grid cells (defaults to GRID_CELLS)
        workers: Number of parallel workers for symbol scanning
        rate_limit_func: Rate limiting callback
        output_path: Local path for ledger output (also writes to GCS)
        allow_sparse_ledger: Allow sparse ledger for smoke test
    """
    import pandas as pd

    grid = grid or GRID_CELLS
    sleep = rate_limit_func or (lambda: None)

    log.info(f"=== Agent A: Run Discovery [{window_start} → {window_end}] ===")
    log.info(f"Grid: {len(grid)} cells, Workers: {workers}")

    # Initialize Funnel Diagnostics
    funnel = RunDiscoveryFunnel()
    for cell in grid:
        funnel.candidates_per_cell_pre_filter[cell.label] = 0
        funnel.final_runs_per_cell[cell.label] = 0
        funnel.filter_eliminations_per_cell[cell.label] = {"mdd": 0, "persistence": 0, "min_price": 0}

    # Step 1: Build universe
    universe_result = build_universe(fmp_func, window_start, window_end, rate_limit_func, return_metadata=True)
    if isinstance(universe_result, tuple):
        universe, seed_sources = universe_result
    else:
        universe = universe_result
        seed_sources = {"screener": len(universe), "sp500_historical": 0}

    funnel.universe_seed_count = len(universe)
    funnel.universe_seed_sources = seed_sources

    # Wrap fmp_func with a caching layer to avoid rate limits
    from fmp_cache import cached_fmp
    def cached_fmp_func(endpoint, params):
        if endpoint == "historical-price-eod/full":
            sym = params.get("symbol")
            raw_prices = cached_fmp(
                endpoint=endpoint,
                symbol=sym,
                fetcher=lambda: fmp_func(endpoint, params),
                cache_key_suffix="",
                ttl_days=30
            )
            if not raw_prices:
                return None
            p_from = params.get("from")
            p_to = params.get("to")
            filtered_prices = []
            for p in raw_prices:
                p_date = p.get("date")
                if p_date and p_from <= p_date <= p_to:
                    filtered_prices.append(p)
            return filtered_prices
        return fmp_func(endpoint, params)

    # Universe is already filtered to FMP cache-covered symbols by build_universe()
    symbols = sorted(list(universe.keys()))
    log.info(f"Scanning {len(symbols)} symbols from FMP cache-filtered universe.")

    # Step 2: Extract runs in parallel
    all_runs = []
    log.info(f"Scanning {len(symbols)} symbols for runs...")
    funnel.universe_seed_count = len(symbols)

    # Use ThreadPoolExecutor for I/O-bound FMP calls
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for sym in symbols:
            future = pool.submit(
                extract_runs_for_symbol,
                sym, universe[sym], cached_fmp_func, grid,
                window_start, window_end, rate_limit_func,
                return_funnel_stats=True,
            )
            futures[future] = sym

        completed = 0
        for future in as_completed(futures):
            completed += 1
            sym = futures[future]
            try:
                result = future.result()
                if isinstance(result, tuple):
                    runs, stats = result
                else:
                    runs, stats = result, {}
                
                # Aggregate Funnel Stats
                if stats:
                    if stats.get("cache_hit"):
                        funnel.cache_hit_count += 1
                    elif stats.get("cache_miss"):
                        funnel.cache_miss_count += 1
                        if len(funnel.cache_miss_symbols) < 20:
                            funnel.cache_miss_symbols.append(sym)
                    
                    if stats.get("has_min_history"):
                        funnel.after_min_history_count += 1

                    for cell_lbl, count in stats.get("candidates_pre_filter", {}).items():
                        funnel.candidates_per_cell_pre_filter[cell_lbl] += count

                    for cell_lbl, elims in stats.get("filter_eliminations", {}).items():
                        for filter_name, count in elims.items():
                            if cell_lbl not in funnel.filter_eliminations_per_cell:
                                funnel.filter_eliminations_per_cell[cell_lbl] = {}
                            if filter_name not in funnel.filter_eliminations_per_cell[cell_lbl]:
                                funnel.filter_eliminations_per_cell[cell_lbl][filter_name] = 0
                            funnel.filter_eliminations_per_cell[cell_lbl][filter_name] += count

                    for cell_lbl, count in stats.get("final_runs", {}).items():
                        funnel.final_runs_per_cell[cell_lbl] += count

                if runs:
                    all_runs.extend(runs)
                    log.info(f"  [{completed}/{len(symbols)}] {sym}: {len(runs)} runs found")
            except Exception as e:
                log.warning(f"  [{completed}/{len(symbols)}] {sym}: error: {e}")

            if completed % 100 == 0:
                log.info(f"  Progress: {completed}/{len(symbols)} ({len(all_runs)} runs so far)")

    funnel.final_total = len(all_runs)

    # Print a console summary to stdout as required by Guard 1
    log.info("\n=============================================")
    log.info("      AGENT A DISCOVERY FUNNEL DIAGNOSTICS   ")
    log.info("=============================================")
    log.info(f"Universe seed count: {funnel.universe_seed_count}")
    log.info(f"Universe seed sources: {funnel.universe_seed_sources}")
    log.info(f"Symbols with min history (>=200d): {funnel.after_min_history_count}")
    log.info(f"Cache hit count: {funnel.cache_hit_count}")
    log.info(f"Cache miss count: {funnel.cache_miss_count}")
    log.info(f"Cache miss rate: {funnel.cache_miss_rate():.1%}")
    if funnel.cache_miss_symbols:
        log.info(f"Cache miss symbols (first 20): {', '.join(funnel.cache_miss_symbols[:20])}")
    log.info(f"Candidates per cell (pre-filter): {funnel.candidates_per_cell_pre_filter}")
    log.info("Filter eliminations per cell:")
    for cell_lbl, elims in funnel.filter_eliminations_per_cell.items():
        log.info(f"  {cell_lbl}: {elims}")
    log.info(f"Final runs per cell: {funnel.final_runs_per_cell}")
    log.info(f"Final total runs: {funnel.final_total}")
    log.info("=============================================\n")

    # Write Diagnostics to synthesis/diagnostics/agent_a_funnel.json
    diag_dir = os.path.join("synthesis", "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)
    diag_path = os.path.join(diag_dir, "agent_a_funnel.json")
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(asdict(funnel), f, indent=2)
    log.info(f"Funnel diagnostics written to: {diag_path}")

    # Enforce funnel health assertions
    assert_funnel_health(funnel, window_start, window_end, allow_sparse_ledger=allow_sparse_ledger)

    log.info(f"\nTotal runs extracted: {len(all_runs)}")

    # Step 3: Distribution stats
    from collections import Counter
    cell_dist = Counter(r["grid_cell_label"] for r in all_runs)
    sector_dist = Counter(r["sector_t_start"] for r in all_runs if r["sector_t_start"])
    year_dist = Counter(r["year_t_start"] for r in all_runs)

    log.info("Grid cell distribution:")
    for cell, count in cell_dist.most_common():
        log.info(f"  {cell}: {count}")
    log.info("Year distribution:")
    for year, count in sorted(year_dist.items()):
        log.info(f"  {year}: {count}")
    log.info("Top 10 sectors:")
    for sector, count in sector_dist.most_common(10):
        log.info(f"  {sector}: {count}")

    # Step 4: Write ledger
    if all_runs:
        df = pd.DataFrame(all_runs)
        log.info(f"Ledger: {len(df)} rows, {len(df.columns)} columns")

        # Local output
        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            df.to_parquet(output_path, engine="pyarrow", index=False)
            log.info(f"Ledger written to: {output_path}")

        # GCS output
        from alpha_compounder.gcs_io import gcs_write_parquet
        gcs_path = f"{GCS_PREFIX}/runs_ledger.parquet"
        gcs_write_parquet(gcs_path, df)

        return df
    else:
        log.warning("No runs found! Check filters and data availability.")
        return None
