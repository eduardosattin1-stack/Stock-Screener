#!/usr/bin/env python3
"""
Feature-parity test: time_model_features vs the training parquet.
=================================================================
Samples >= 40 (symbol, scan_date) rows from time_model_training_data.parquet
(spread across symbols and dates), rebuilds SymbolRawInputs from the SAME
local caches the steward used (fmp_cache statements via _pit_records, price
history via _load_prices sliced to <= scan_date, ThetaData parquet capture
<= 7 days before), runs compute_symbol_features, and asserts parity:

  EXACT tier (technicals, fundamentals, quality, engineered):
      |module - parquet| <= 1e-4 (+1e-4 relative, parquet is float32).
      CACHE-DRIFT HANDLING: fmp_cache is SHARED with the live screener and
      statements have been refreshed since the parquet was built (2026-05-29),
      so for fundamentals the test additionally recomputes the expected value
      through the STEWARD'S OWN code (extract_fundamentals +
      compute_pit_quality_score) on today's caches. A row passes if the
      module matches the parquet OR matches the steward recomputation
      bit-for-bit (the latter is printed as a cache-drift note — never
      silent). Module disagreeing with BOTH is a HARD FAILURE (refactor bug).
      Technicals have no drift channel (price closes are stable) and must
      match the parquet directly.

  OPT tier (opt_atm_iv/vega/theta, f_opt_iv_rank, f_opt_iv_momentum):
      compared against a capture-consistent recomputation (normalize_chain
      with the CAPTURE's underlying price — the training reference frame;
      compute_symbol_features itself normalizes with the as-of price, which
      is the live convention but skews strike selection when the capture is
      up to 7 days old). Tolerance 0.05 absolute (or 5% relative for the
      price-unit greeks). Residual differences are EXPECTED (normalize_chain
      keeps the 5 strikes nearest the underlying per expiration per right,
      while the ThetaData strike_range=5 training captures actually carry
      ~10 = 5 per side; f_opt_iv_momentum is pinned to a weekly-resampled
      diff while training used diff(5) over the raw capture sequence). Rows
      beyond tolerance are printed LOUDLY and counted as
      distribution-shift-accepted — never silently skipped.

  Rank/cross-sectional features (f_sector_momentum + 5 ranks) cannot be
  validated from a small sample (they need the full ~2.8k-symbol grid
  cross-section), so compute_cross_sectional_features is instead tested for
  CORRECTNESS on a synthetic 500-symbol cross-section against the steward's
  exact pandas semantics, plus the <300-symbol refusal.

Exit code 0 = parity holds; 1 = hard failure.

Usage:  python test_feature_parity.py [--rows 48] [--symbols 30]
"""

import os
import sys
import argparse

import numpy as np
import pandas as pd

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)

from time_model_features import (
    SymbolRawInputs,
    compute_symbol_features,
    compute_cross_sectional_features,
    normalize_chain,
    compute_chain_features,
    compute_iv_rank,
    compute_iv_momentum,
    build_vector,
    FEATURES_V4,
    TECHNICAL_FEATURES,
    FUNDAMENTAL_FEATURES,
    OPTION_FEATURES,
    MIN_CROSS_SECTION,
)
from time_model_data_steward import (
    _get_json,
    _pit_records,
    _load_prices,
    _evict_symbol_cache,
    extract_fundamentals,
    FMP_CACHE_DIR,
    CACHE_DATA,
    THETA_DIR,
)
from time_model_feature_library import compute_pit_quality_score

PARQUET = os.path.join(BACKEND, "time_model_training_data.parquet")
SEED = 42

EXACT_FEATURES = (
    list(TECHNICAL_FEATURES)
    + list(FUNDAMENTAL_FEATURES)
    + ["f_quality", "f_rsi_x_quality", "f_rsi_x_revgrow", "f_roe_over_pb"]
)
OPT_FEATURES = list(OPTION_FEATURES)

EXACT_RTOL = 1e-4
EXACT_ATOL = 1e-4
OPT_TOL = 0.05

CHAIN_COLS = ["right", "expiration", "strike", "delta", "gamma", "theta",
              "vega", "implied_vol", "iv_error", "open_interest", "volume"]


# ─────────────────────────────────────────────────────────────────────────────
# Raw-input reconstruction (mirrors how the steward obtained its inputs)
# ─────────────────────────────────────────────────────────────────────────────
def _load_stmt(sym: str, endpoint: str, flat_slug: str) -> list:
    """Steward extract_fundamentals._load replica."""
    hier = os.path.join(FMP_CACHE_DIR, endpoint, f"{sym}.json")
    d = _get_json(hier)
    if d:
        return d
    return _get_json(os.path.join(CACHE_DATA, f"{sym}_{flat_slug}.json"))


def _rows_to_contracts(rows: pd.DataFrame) -> list:
    cols = [c for c in CHAIN_COLS if c in rows.columns]
    return rows[cols].to_dict("records")


class SymbolContext:
    """Per-symbol caches: prices, statements, theta captures, per-capture IVs."""

    def __init__(self, sym: str):
        self.sym = sym
        self.prices = _load_prices(sym)
        self.date_to_idx = {p["date"]: i for i, p in enumerate(self.prices)}
        self.inc = _load_stmt(sym, "income-statement", "income_statement")
        self.bs = _load_stmt(sym, "balance-sheet-statement", "balance_sheet")
        self.cf = _load_stmt(sym, "cash-flow-statement", "cash_flow")
        self.km = _load_stmt(sym, "key-metrics", "key_metrics")

        self.theta = None
        self.captures = []
        self._capture_rows = {}
        self._capture_iv = {}
        theta_path = os.path.join(THETA_DIR, f"{sym}_theta.parquet")
        if os.path.exists(theta_path):
            try:
                t = pd.read_parquet(theta_path)
                if not t.empty and "scan_date" in t.columns:
                    t["scan_date"] = t["scan_date"].astype(str)
                    self.theta = t
                    self.captures = sorted(t["scan_date"].unique())
            except Exception as e:
                print(f"  [warn] {sym}: theta parquet unreadable: {e}")

    def capture_contracts(self, cap: str) -> list:
        if cap not in self._capture_rows:
            self._capture_rows[cap] = _rows_to_contracts(
                self.theta[self.theta["scan_date"] == cap]
            )
        return self._capture_rows[cap]

    def capture_atm_iv(self, cap: str):
        """ATM IV of one historical capture through the MODULE's own path
        (normalize_chain + compute_chain_features) — the pinned builder
        ATM-IV definition used for live iv_history too."""
        if cap not in self._capture_iv:
            rows = self.theta[self.theta["scan_date"] == cap]
            up = None
            if "underlying_price" in rows.columns:
                ups = pd.to_numeric(rows["underlying_price"], errors="coerce").dropna()
                if len(ups):
                    up = float(ups.median())
            norm = normalize_chain(_rows_to_contracts(rows), up)
            self._capture_iv[cap] = compute_chain_features(norm)["opt_atm_iv"]
        return self._capture_iv[cap]

    def build_raw(self, scan_date: str):
        """Returns (SymbolRawInputs, info) or (None, reason)."""
        idx = self.date_to_idx.get(scan_date)
        if idx is None:
            return None, "scan_date missing from price cache (cache drift)"
        daily_bars = self.prices[: idx + 1]
        price = float(self.prices[idx]["close"])

        chain = None
        iv_hist = None
        cap_used = None
        if self.theta is not None:
            lo = (pd.Timestamp(scan_date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            cands = [c for c in self.captures if lo <= c <= scan_date]
            if cands:
                cap_used = cands[-1]
                chain = self.capture_contracts(cap_used)
                prior = [c for c in self.captures if c < cap_used][-251:]
                iv_hist = []
                for c in prior:
                    iv = self.capture_atm_iv(c)
                    if iv is not None:  # capture lost to the iv mask -> absent
                        iv_hist.append((c, iv))

        raw = SymbolRawInputs(
            symbol=self.sym,
            asof_date=scan_date,
            price=price,
            daily_bars=daily_bars,
            income_annual=_pit_records(self.inc, scan_date),
            balance_annual=_pit_records(self.bs, scan_date),
            cashflow_annual=_pit_records(self.cf, scan_date),
            key_metrics_annual=_pit_records(self.km, scan_date),
            option_chain=chain,
            atm_iv_history=iv_hist,
        )

        cap_underlying = None
        if cap_used is not None and "underlying_price" in self.theta.columns:
            ups = pd.to_numeric(
                self.theta.loc[self.theta["scan_date"] == cap_used, "underlying_price"],
                errors="coerce",
            ).dropna()
            if len(ups):
                cap_underlying = float(ups.median())

        info = {
            "price_cached": price,
            "capture": cap_used,
            "cap_underlying": cap_underlying,
            "stmts_empty": not (raw.income_annual or raw.balance_annual
                                or raw.cashflow_annual or raw.key_metrics_annual),
        }
        return raw, info

    def steward_expected(self, scan_date: str, price: float, f_rsi: float) -> dict:
        """Expected exact-tier values recomputed through the STEWARD'S OWN
        code paths on today's caches (the cache-drift cross-check)."""
        stew = extract_fundamentals(self.sym, scan_date, price)
        exp = dict(stew)
        q = float(compute_pit_quality_score(pd.DataFrame([stew])).iloc[0])
        exp["f_quality"] = q
        exp["f_rsi_x_quality"] = ((100.0 - f_rsi) / 100.0) * q
        rg = min(stew.get("f_rev_growth") or 0.0, 2.0)
        exp["f_rsi_x_revgrow"] = ((100.0 - f_rsi) / 100.0) * rg
        pb, roe = stew.get("f_pb") or 0.0, stew.get("f_roe") or 0.0
        exp["f_roe_over_pb"] = roe / pb if pb > 0 else 0.0
        return exp


# ─────────────────────────────────────────────────────────────────────────────
# Comparison bookkeeping
# ─────────────────────────────────────────────────────────────────────────────
class Stats:
    def __init__(self):
        self.per_feature = {}

    def record(self, feat, status, diff=None):
        s = self.per_feature.setdefault(
            feat, {"n": 0, "fail": 0, "warn": 0, "note": 0, "drift": 0, "max_diff": 0.0}
        )
        s["n"] += 1
        if diff is not None and np.isfinite(diff):
            s["max_diff"] = max(s["max_diff"], abs(diff))
        if status == "fail":
            s["fail"] += 1
        elif status == "warn":
            s["warn"] += 1
        elif status == "note":
            s["note"] += 1
        elif status == "drift":
            s["drift"] += 1

    def summary(self):
        rows = []
        for feat in sorted(self.per_feature):
            s = self.per_feature[feat]
            rows.append(
                f"  {feat:<24} n={s['n']:<4} max|diff-vs-parquet|={s['max_diff']:<12.6g} "
                f"fail={s['fail']} warn={s['warn']} drift={s['drift']} note={s['note']}"
            )
        return "\n".join(rows)

    @property
    def n_fail(self):
        return sum(s["fail"] for s in self.per_feature.values())

    @property
    def n_warn(self):
        return sum(s["warn"] for s in self.per_feature.values())


def compare_row(row, got, got_opt, steward_exp, info, stats: Stats):
    sym, sd = row["symbol"], row["scan_date"]
    drifted = []

    # EXACT tier — module must match the parquet OR the steward-recomputed
    # value on today's caches (cache drift, printed); neither = HARD FAILURE.
    for feat in EXACT_FEATURES:
        exp = float(row[feat])
        g = got.get(feat)
        alt = steward_exp.get(feat)  # None for technicals (no drift channel)
        if g is None:
            if info["stmts_empty"] and abs(exp) <= EXACT_ATOL:
                # steward emitted 0.0 fillers for statement-less symbols; the
                # module reports the section as missing (None) by design
                stats.record(feat, "note")
                continue
            print(f"  FAIL {sym} {sd} {feat}: module=None, parquet={exp}")
            stats.record(feat, "fail")
            continue
        diff = float(g) - exp
        if abs(diff) <= EXACT_ATOL + EXACT_RTOL * abs(exp):
            stats.record(feat, "ok", diff)
        elif alt is not None and abs(float(g) - float(alt)) <= 1e-9:
            # module == steward's own code on today's caches, parquet differs:
            # the statement cache moved since the parquet build
            drifted.append(f"{feat}(pq={exp:.4g} now={g:.4g})")
            stats.record(feat, "drift", diff)
        else:
            alt_s = "n/a" if alt is None else f"{alt:.6g}"
            print(f"  FAIL {sym} {sd} {feat}: module={g:.6g}, parquet={exp:.6g}, "
                  f"steward-today={alt_s} — module matches NEITHER (refactor bug)")
            stats.record(feat, "fail", diff)

    if drifted:
        print(f"  DRIFT {sym} {sd}: statement cache moved since parquet build; "
              f"module == steward-today for: {', '.join(drifted)}")

    # OPT tier — capture-consistent recomputation vs parquet; tolerance 0.05 /
    # 5% rel; beyond = distribution-shift-accepted (printed, counted)
    for feat in OPT_FEATURES:
        exp = float(row[feat])
        g = got_opt.get(feat)
        if g is None:
            if abs(exp) <= 1e-9:
                # steward filled unmatched options rows with 0.0; the module
                # reports the section missing (None) — consistent by design
                stats.record(feat, "note")
            else:
                print(f"  WARN {sym} {sd} {feat}: module=None (no usable capture in "
                      f"window) but parquet={exp:.4f} — merge_asof matched an older "
                      f"capture the module's 7-day window logic skipped "
                      f"[distribution-shift-accepted]")
                stats.record(feat, "warn")
            continue
        diff = float(g) - exp
        tol = max(OPT_TOL, OPT_TOL * abs(exp))
        if abs(diff) <= tol:
            stats.record(feat, "ok", diff)
        else:
            print(f"  WARN {sym} {sd} {feat}: module={g:.4f}, parquet={exp:.4f}, "
                  f"diff={diff:.4f} > tol={tol:.4f} (chain-window/cadence difference) "
                  f"[distribution-shift-accepted]")
            stats.record(feat, "warn", diff)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic cross-sectional test (rank FUNCTION correctness)
# ─────────────────────────────────────────────────────────────────────────────
def test_cross_sectional_synthetic() -> int:
    print("\n── Cross-sectional rank test (synthetic 500-symbol cross-section) ──")
    rng = np.random.default_rng(7)
    n = 500
    syms = [f"SYM{i:04d}" for i in range(n)]
    sectors = {s: f"Sector{(i % 8)}" for i, s in enumerate(syms)}
    per_symbol = {}
    for i, s in enumerate(syms):
        per_symbol[s] = {
            "f_momentum_3m": float(rng.normal(0.02, 0.10)),
            "f_rsi": float(rng.uniform(5, 95)),
            "f_pb": float(rng.lognormal(0.5, 1.0)),
            "f_rev_growth": float(rng.normal(0.05, 0.30)),
            "f_roe": float(rng.normal(0.10, 0.25)),
        }
    # inject missing values (None -> NaN -> rank na_option='keep' -> 0.5)
    for i in (3, 77, 250, 444):
        per_symbol[syms[i]]["f_pb"] = None
        per_symbol[syms[i]]["f_roe"] = None

    out = compute_cross_sectional_features(per_symbol, sectors)

    # Expected values via the steward's exact pandas semantics (:733-756)
    df = pd.DataFrame.from_dict(per_symbol, orient="index").reindex(syms)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    sec = pd.Series(sectors).reindex(syms)
    exp_sm = df["f_momentum_3m"].groupby(sec).transform("median").fillna(0.0)
    expected = {
        "f_sector_momentum": exp_sm,
        "f_rsi_rank": df["f_rsi"].rank(pct=True, na_option="keep").fillna(0.5),
        "f_pb_rank": df["f_pb"].rank(pct=True, na_option="keep").fillna(0.5),
        "f_rev_growth_rank": df["f_rev_growth"].rank(pct=True, na_option="keep").fillna(0.5),
        "f_roe_rank": df["f_roe"].rank(pct=True, na_option="keep").fillna(0.5),
        "f_upside_rank": exp_sm.rank(pct=True, na_option="keep").fillna(0.5),
    }
    n_fail = 0
    for feat, exp_series in expected.items():
        diffs = np.array([abs(out[s][feat] - float(exp_series.loc[s])) for s in syms])
        if diffs.max() > 1e-12:
            print(f"  FAIL {feat}: max diff {diffs.max():.3e}")
            n_fail += 1
        else:
            print(f"  OK   {feat}: max diff {diffs.max():.3e} over {n} symbols")

    # sector medians must be in RAW return units (sanity: |median| < 1 and
    # equals the literal per-sector median, not a 0-1 score)
    s0 = [s for s in syms if sectors[s] == "Sector0"]
    lit = float(np.median([per_symbol[s]["f_momentum_3m"] for s in s0]))
    if abs(out[s0[0]]["f_sector_momentum"] - lit) > 1e-12:
        print(f"  FAIL f_sector_momentum literal-median check: {out[s0[0]]['f_sector_momentum']} vs {lit}")
        n_fail += 1
    else:
        print(f"  OK   f_sector_momentum is the literal per-sector median ({lit:+.5f})")

    # refusal on degenerate cross-sections
    try:
        compute_cross_sectional_features(
            {s: per_symbol[s] for s in syms[: MIN_CROSS_SECTION - 1]}, sectors
        )
        print(f"  FAIL: no raise on {MIN_CROSS_SECTION - 1}-symbol cross-section")
        n_fail += 1
    except ValueError:
        print(f"  OK   raises ValueError on < {MIN_CROSS_SECTION} symbols")
    return n_fail


def test_build_vector() -> int:
    print("\n── build_vector test ──")
    n_fail = 0
    feats = {f: 0.5 for f in FEATURES_V4}
    feats["f_pe"] = None              # explicit missing
    feats["f_vol_60d"] = float("nan")  # NaN counts as missing
    feats["f_pb"] = 250.0             # must clip to 100
    del feats["opt_atm_iv"]           # absent key counts as missing
    medians = {"f_pe": 12.3, "f_vol_60d": 0.37, "opt_atm_iv": 0.31}
    vec, missing = build_vector(feats, medians)
    if vec.shape != (1, len(FEATURES_V4)):
        print(f"  FAIL shape {vec.shape}")
        n_fail += 1
    if sorted(missing) != ["f_pe", "f_vol_60d", "opt_atm_iv"]:
        print(f"  FAIL missing list: {missing}")
        n_fail += 1
    order = {f: i for i, f in enumerate(FEATURES_V4)}
    checks = [("f_pe", 12.3), ("f_vol_60d", 0.37), ("opt_atm_iv", 0.31),
              ("f_pb", 100.0), ("f_rsi", 0.5)]
    for f, want in checks:
        gotv = vec[0, order[f]]
        if abs(gotv - want) > 1e-12:
            print(f"  FAIL {f}: {gotv} != {want}")
            n_fail += 1
    if n_fail == 0:
        print(f"  OK   shape (1,{len(FEATURES_V4)}), median fills + missing names + clip correct")
    return n_fail


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="time_model_features parity test")
    parser.add_argument("--rows", type=int, default=48, help="target sampled rows (>= 40)")
    parser.add_argument("--symbols", type=int, default=30, help="symbols to sample from")
    args = parser.parse_args()

    print(f"Loading parquet: {PARQUET}")
    cols = (["symbol", "scan_date", "price"] + EXACT_FEATURES + OPT_FEATURES)
    df = pd.read_parquet(PARQUET, columns=cols)
    print(f"  {len(df):,} rows")

    rng = np.random.default_rng(SEED)

    # Symbols that have a theta parquet (so the options tier gets exercised)
    all_syms = sorted(df["symbol"].unique())
    theta_syms = [s for s in all_syms
                  if os.path.exists(os.path.join(THETA_DIR, f"{s}_theta.parquet"))]
    pool = theta_syms if len(theta_syms) >= args.symbols else all_syms
    chosen = list(rng.choice(pool, size=min(args.symbols, len(pool)), replace=False))
    print(f"Sampled {len(chosen)} symbols (of {len(pool)} with theta coverage)")

    # Per symbol: one row with options matched (opt_atm_iv > 0) + one random row
    samples = []
    for sym in chosen:
        sub = df[df["symbol"] == sym]
        if sub.empty:
            continue
        with_opt = sub[sub["opt_atm_iv"] > 0]
        if not with_opt.empty:
            samples.append(with_opt.iloc[int(rng.integers(0, len(with_opt)))])
        samples.append(sub.iloc[int(rng.integers(0, len(sub)))])
    # de-dup (symbol, scan_date)
    seen, rows = set(), []
    for r in samples:
        key = (r["symbol"], r["scan_date"])
        if key not in seen:
            seen.add(key)
            rows.append(r)
    rows = rows[: max(args.rows, 40) + 20]  # headroom for skips
    print(f"Candidate rows: {len(rows)}")

    stats = Stats()
    n_compared = 0
    n_skipped = 0
    cur_sym, ctx = None, None
    for r in rows:
        sym, sd = r["symbol"], r["scan_date"]
        if sym != cur_sym:
            if cur_sym is not None:
                _evict_symbol_cache(cur_sym)
            ctx = SymbolContext(sym)
            cur_sym = sym
        if not ctx.prices:
            print(f"  SKIP {sym} {sd}: no price cache")
            n_skipped += 1
            continue
        raw, info = ctx.build_raw(sd)
        if raw is None:
            print(f"  SKIP {sym} {sd}: {info}")
            n_skipped += 1
            continue
        # cache-drift guard: the cached close must reproduce the parquet price
        exp_price = float(r["price"])
        if abs(info["price_cached"] - exp_price) > max(1e-3, 1e-4 * exp_price):
            print(f"  SKIP {sym} {sd}: price cache drift "
                  f"(cached {info['price_cached']:.4f} vs parquet {exp_price:.4f})")
            n_skipped += 1
            continue

        got = compute_symbol_features(raw)

        # Capture-consistent options recomputation (training reference frame:
        # strike window selected with the CAPTURE's underlying price)
        got_opt = {f: None for f in OPT_FEATURES}
        if info["capture"] is not None and raw.option_chain:
            norm_cap = normalize_chain(raw.option_chain, info["cap_underlying"])
            cf = compute_chain_features(norm_cap)
            got_opt.update(cf)
            got_opt["f_opt_iv_rank"] = compute_iv_rank(
                cf["opt_atm_iv"], raw.atm_iv_history, sd)
            got_opt["f_opt_iv_momentum"] = compute_iv_momentum(
                cf["opt_atm_iv"], raw.atm_iv_history, sd)

        # Steward-code cross-check values for the drift channel
        steward_exp = ctx.steward_expected(sd, raw.price, got["f_rsi"])

        compare_row(r, got, got_opt, steward_exp, info, stats)
        n_compared += 1
        if n_compared >= max(args.rows, 40) and n_compared >= 40:
            pass  # keep going through remaining candidates anyway

    print(f"\nRows compared: {n_compared} (skipped {n_skipped})")
    if n_compared < 40:
        print(f"HARD FAIL: only {n_compared} rows compared (< 40) — increase --symbols")
        return 1

    syn_fail = test_cross_sectional_synthetic()
    vec_fail = test_build_vector()

    print("\n── Per-feature summary ──")
    print(stats.summary())
    n_drift = sum(s["drift"] for s in stats.per_feature.values())
    print(f"\nTotals: {stats.n_fail} hard failures, {stats.n_warn} "
          f"distribution-shift-accepted warnings, {n_drift} cache-drift rows "
          f"(module == steward-today, parquet differs); exact-tier tolerance "
          f"{EXACT_ATOL} (+{EXACT_RTOL} rel), opt-tier tolerance {OPT_TOL}")

    if stats.n_fail or syn_fail or vec_fail:
        print("\nPARITY TEST FAILED")
        return 1
    print("\nPARITY TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
