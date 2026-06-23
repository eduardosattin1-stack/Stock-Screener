#!/usr/bin/env python3
"""Offline smoke test for the v4 serving feature path (NO network).

Builds time_model_features.SymbolRawInputs for a handful of liquid US names
straight from the local fmp_cache (the same payload shapes the live scanner
exposes via stock._raw_statements + the chart stash), runs
compute_symbol_features, and asserts per-symbol non-null coverage of
FEATURES_V4.

option_chain=None is expected offline -> the 5 opt_*/f_opt_* features are
None and the 6 cross-sectional features are not computed per-symbol, so the
per-symbol ceiling is 48 - 5 - 6 = 37 non-null features.

Run:  python test_serving_features.py        (from backend/)
"""
import json
import os
import sys

from time_model_features import (
    FEATURES_V4,
    OPTION_FEATURES,
    CROSS_SECTIONAL_FEATURES,
    SymbolRawInputs,
    compute_symbol_features,
)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FMP_CACHE_DIR = os.path.join(BACKEND_DIR, "fmp_cache")

# Liquid US names with full statement + price coverage in the local cache,
# spread across sectors (tech / energy / industrial).
TEST_SYMBOLS = ["AAPL", "MSFT", "NVDA", "XOM", "CAT"]

MIN_NON_NULL = 30          # of 48 — per task acceptance criterion
MIN_SYMBOLS_PASSING = 3    # at least 3 of 5 symbols must clear MIN_NON_NULL


def _load_cache_json(endpoint: str, symbol: str) -> list:
    """Read an fmp_cache file and unwrap the {'payload': [...]} envelope
    (same convention as time_model_data_steward._get_json)."""
    path = os.path.join(FMP_CACHE_DIR, endpoint, f"{symbol}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        print(f"  WARN {symbol}: failed to read {endpoint}: {e}")
        return []
    if isinstance(data, dict) and "payload" in data:
        data = data["payload"]
    return data if isinstance(data, list) else []


def _stmts_newest_first(rows: list) -> list:
    """Mirror of screener_v6._stmts_newest_first (builder wants newest-first)."""
    if not rows:
        return []
    return sorted([r for r in rows if isinstance(r, dict)],
                  key=lambda x: x.get("date") or "", reverse=True)


def _load_daily_bars(symbol: str, n_bars: int = 300) -> list:
    """Last n_bars of the cached EOD history, slimmed to the 6 builder fields
    (mirror of the scanner's _ml_inputs stash), sorted ascending."""
    data = _load_cache_json("historical-price-eod", symbol)
    bars = []
    for d in data:
        close = d.get("close") or d.get("adjClose")
        if not close or float(close) <= 0:
            continue
        bars.append({
            "date": d.get("date", ""),
            "open": d.get("open"),
            "high": d.get("high"),
            "low": d.get("low"),
            "close": float(close),
            "volume": d.get("volume"),
        })
    bars.sort(key=lambda b: b["date"])
    return bars[-n_bars:]


def build_raw_inputs(symbol: str):
    bars = _load_daily_bars(symbol)
    if not bars:
        print(f"  WARN {symbol}: no cached price history — skipping")
        return None
    inc = _stmts_newest_first(_load_cache_json("income-statement", symbol))
    bal = _stmts_newest_first(_load_cache_json("balance-sheet-statement", symbol))
    cfl = _stmts_newest_first(_load_cache_json("cash-flow-statement", symbol))
    km = _stmts_newest_first(_load_cache_json("key-metrics", symbol))
    return SymbolRawInputs(
        symbol=symbol,
        asof_date=bars[-1]["date"][:10],
        price=float(bars[-1]["close"]),
        daily_bars=bars,
        income_annual=inc,
        balance_annual=bal,
        cashflow_annual=cfl,
        key_metrics_annual=km,
        option_chain=None,      # offline: opt_* features expected None
        atm_iv_history=None,
    )


def _is_null(v) -> bool:
    if v is None:
        return True
    try:
        return v != v  # NaN
    except Exception:
        return True


def main() -> int:
    assert len(FEATURES_V4) == 48, f"FEATURES_V4 must be 48 names, got {len(FEATURES_V4)}"
    opt_set = set(OPTION_FEATURES)
    xsect_set = set(CROSS_SECTIONAL_FEATURES)

    passing = 0
    results = {}
    for sym in TEST_SYMBOLS:
        raw = build_raw_inputs(sym)
        if raw is None:
            results[sym] = (0, FEATURES_V4)
            continue
        feats = compute_symbol_features(raw)

        non_null = [f for f in FEATURES_V4 if not _is_null(feats.get(f))]
        missing = [f for f in FEATURES_V4 if _is_null(feats.get(f))]
        results[sym] = (len(non_null), missing)

        # Offline sanity: missing should only be opt_* (no chain) and
        # cross-sectional (not computed per-symbol) features, plus at most
        # technicals that legitimately NaN on short history.
        unexpected = [f for f in missing if f not in opt_set and f not in xsect_set]
        print(f"{sym:>6}: {len(non_null)}/48 non-null "
              f"(asof {raw.asof_date}, {len(raw.daily_bars)} bars, "
              f"{len(raw.income_annual)} income stmts)")
        print(f"        missing ({len(missing)}): {', '.join(missing)}")
        if unexpected:
            print(f"        NOTE — missing beyond opt_*/cross-sectional: {unexpected}")

        if len(non_null) >= MIN_NON_NULL:
            passing += 1

    print(f"\n{passing}/{len(TEST_SYMBOLS)} symbols with >= {MIN_NON_NULL}/48 non-null features")
    assert passing >= MIN_SYMBOLS_PASSING, (
        f"FAIL: only {passing} symbols reached {MIN_NON_NULL}/48 non-null "
        f"(need >= {MIN_SYMBOLS_PASSING}): "
        + "; ".join(f"{s}={n}" for s, (n, _) in results.items())
    )
    print("PASS: serving feature coverage OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
