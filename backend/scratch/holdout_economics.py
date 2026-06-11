#!/usr/bin/env python3
"""
Per-decile STOCK-ARM strategy economics on the embargoed holdout (v4 models).

For each target in {clf_10pct_30d (+10% barrier, K=30), clf_20pct_60d (+20%, K=60)}:
  - Score holdout (scan_date >= 2025-06-01) with models_holdout_v3 + isotonic
    calibrators, assign deciles via meta edges (searchsorted side='right' + 1).
  - Strategy return per row: touched (1 <= bars_to <= K) -> +barrier (sold AT
    barrier); else terminal K-trading-bar close-to-close return, reconstructed
    from the FMP price cache via the steward's _load_prices (same close series
    targets were computed from; entry bar = scan_date bar, window bar = idx+K).
  - Benchmarks: pooled equal-weight strategy mean; pure buy-and-hold K-bar
    close-to-close (no barrier) per decile + pooled; D10-D1 and (D9+D10)-pooled.
  - Friction: net of 20bps round trip. Risk: return / |mean max-DD|.
  - Vol-control: f_vol_60d quintiles x model decile (<=3 vs >=8) spread.

Sign convention: max_dd_30d/max_dd_60d in the parquet are NEGATIVE percents
(worst of close/low gain vs entry close within the window, capped at 0).
Returns are reported in PERCENT per window. Do NOT annualize: rows overlap
(same symbol every 5th trading day), K=30 bars ~ 10.5 non-overlapping
periods/yr but naive compounding overstates significance.

Usage:  python scratch/holdout_economics.py   (from backend/, PYTHONIOENCODING=utf-8)
Writes: scratch/holdout_economics_results.json (all tables, machine-readable)
"""
import os
import sys
import json
import time

import numpy as np
import pandas as pd
import joblib

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from time_model_data_steward import _load_prices, _evict_symbol_cache  # noqa: E402

PARQUET = os.path.join(BACKEND, "time_model_training_data.parquet")
PKL = os.path.join(BACKEND, "time_model_v4.pkl")
META = os.path.join(BACKEND, "time_model_v4_meta.json")
OUT_JSON = os.path.join(BACKEND, "scratch", "holdout_economics_results.json")

HOLDOUT_START = "2025-06-01"
FRICTION = 0.20  # 20 bps round trip, in percent units

TARGETS = {
    "clf_10pct_30d": dict(barrier=10.0, K=30, bars_col="bars_to_10pct",
                          hit_col="hit_10pct_30d", dd_col="max_dd_30d"),
    "clf_20pct_60d": dict(barrier=20.0, K=60, bars_col="bars_to_20pct",
                          hit_col="hit_20pct_60d", dd_col="max_dd_60d"),
}


def reconstruct_terminal_closes(df):
    """Per symbol: load steward price series, map scan_date -> bar index,
    grab close[idx], close[idx+30], close[idx+60]. Returns arrays aligned to
    df.index (NaN where dropped) + drop counters."""
    entry_close = pd.Series(np.nan, index=df.index)
    term30 = pd.Series(np.nan, index=df.index)
    term60 = pd.Series(np.nan, index=df.index)
    drops = {"no_prices": 0, "unmappable_date": 0, "short_forward": 0}

    t0 = time.time()
    syms = df.groupby("symbol", sort=False)
    for n_sym, (sym, g) in enumerate(syms, 1):
        prices = _load_prices(sym)
        if not prices:
            drops["no_prices"] += len(g)
            continue
        dmap = {p["date"][:10]: i for i, p in enumerate(prices)}
        closes = np.array([p["close"] for p in prices], dtype=float)
        _evict_symbol_cache(sym)  # keep memory flat across ~2.8k symbols

        ix = np.array([dmap.get(d[:10], -1) for d in g["scan_date"].values])
        mappable = ix >= 0
        ok = mappable & (ix + 60 < len(closes))
        drops["unmappable_date"] += int((~mappable).sum())
        drops["short_forward"] += int((mappable & ~ok).sum())
        if ok.any():
            gi = g.index[ok]
            entry_close.loc[gi] = closes[ix[ok]]
            term30.loc[gi] = closes[ix[ok] + 30]
            term60.loc[gi] = closes[ix[ok] + 60]
        if n_sym % 500 == 0:
            print(f"  ... {n_sym} symbols mapped ({time.time()-t0:.0f}s)")
    print(f"  price reconstruction: {n_sym} symbols in {time.time()-t0:.0f}s")
    return entry_close, term30, term60, drops


def main():
    pkl = joblib.load(PKL)
    meta = json.load(open(META, encoding="utf-8"))
    features = list(pkl["features"])
    medians = pkl["medians"]

    df = pd.read_parquet(PARQUET, filters=[("scan_date", ">=", HOLDOUT_START)])
    df = df.reset_index(drop=True)
    print(f"Holdout slice: {len(df):,} rows, {df['symbol'].nunique()} symbols, "
          f"{df['scan_date'].min()} .. {df['scan_date'].max()}")

    # ── Score both targets (fillna medians, clip ±100, pkl feature order) ──
    X = df[features].fillna(medians).clip(-100, 100)
    for T in TARGETS:
        raw = pkl["models_holdout_v3"][T][0].predict_proba(X)[:, 1]
        p = pkl["calibrators_holdout_v3"][T].predict(raw)
        edges = np.asarray(meta["decile_table"][T]["edges"], dtype=float)
        df[f"p_{T}"] = p
        df[f"dec_{T}"] = np.searchsorted(edges, p, side="right") + 1

    # ── Terminal close reconstruction from the price cache ──
    entry_close, term30, term60, drops = reconstruct_terminal_closes(df)
    df["entry_close"], df["term30"], df["term60"] = entry_close, term30, term60
    n_dropped = int(df["entry_close"].isna().sum())
    mism = (df["entry_close"] / df["price"] - 1).abs() > 1e-4
    print(f"Drops: {drops} (total rows dropped: {n_dropped}); "
          f"entry-close vs parquet price mismatches >1bp: {int(mism.fillna(False).sum())}")

    results = {"holdout": {"n_rows": int(len(df)),
                           "n_symbols": int(df["symbol"].nunique()),
                           "scan_date_min": str(df["scan_date"].min()),
                           "scan_date_max": str(df["scan_date"].max()),
                           "drops": drops, "n_dropped": n_dropped,
                           "entry_close_mismatch_gt_1bp": int(mism.fillna(False).sum())},
               "friction_bps_roundtrip": 20,
               "targets": {}}

    for T, cfg in TARGETS.items():
        K, barrier = cfg["K"], cfg["barrier"]
        term_col = "term30" if K == 30 else "term60"
        d = df[df["entry_close"].notna()].copy()

        touched = (d[cfg["bars_col"]] >= 1) & (d[cfg["bars_col"]] <= K)
        bh_ret = (d[term_col] / d["entry_close"] - 1.0) * 100.0     # buy & hold K bars
        strat_ret = np.where(touched, barrier, bh_ret)               # sold AT barrier
        d["touched"], d["bh_ret"], d["strat_ret"] = touched, bh_ret, strat_ret
        dec = d[f"dec_{T}"]

        # ── Sanity vs meta decile_table (on the FULL scored slice, pre-drop) ──
        mt = meta["decile_table"][T]
        full_dec = df[f"dec_{T}"]
        cnt_diff, hr_diff = [], []
        for q in range(1, 11):
            m_full = full_dec == q
            cnt_diff.append(int(m_full.sum()) - int(mt["count"][q - 1]))
            hr = df.loc[m_full, cfg["hit_col"]].mean() if m_full.any() else np.nan
            hr_diff.append(float(hr) - float(mt["hit_rate"][q - 1]))
        sanity = {"max_abs_count_diff": int(np.max(np.abs(cnt_diff))),
                  "count_diff_by_decile": cnt_diff,
                  "max_abs_hit_rate_diff": float(np.nanmax(np.abs(hr_diff))),
                  "hit_consistency_check": bool(
                      (touched.astype(int) == d[cfg["hit_col"]].astype(int)).all())}

        # ── Per-decile economics ──
        rows = []
        for q in range(1, 11):
            m = dec == q
            n = int(m.sum())
            sr = d.loc[m, "strat_ret"]
            nt = d.loc[m & ~d["touched"], "bh_ret"]                 # terminal-only
            dd = d.loc[m, cfg["dd_col"]]
            mean_dd = float(dd.mean())
            mean_sr = float(sr.mean())
            rows.append({
                "decile": q, "n": n,
                "touch_rate": float(d.loc[m, "touched"].mean()),
                "mean_strat_ret_pct": mean_sr,
                "median_strat_ret_pct": float(sr.median()),
                "mean_terminal_only_ret_pct": float(nt.mean()) if len(nt) else None,
                "mean_bh_ret_pct": float(d.loc[m, "bh_ret"].mean()),
                "mean_max_dd_pct": mean_dd,
                "share_dd_le_-20pct": float((dd <= -20.0).mean()),
                "mean_bars_to_touch": float(d.loc[m & d["touched"], cfg["bars_col"]].mean())
                                      if d.loc[m, "touched"].any() else None,
                "mean_strat_net20bps_pct": mean_sr - FRICTION,
                "ret_over_abs_dd": mean_sr / abs(mean_dd) if mean_dd != 0 else None,
            })

        pooled = {"mean_strat_ret_pct": float(d["strat_ret"].mean()),
                  "median_strat_ret_pct": float(d["strat_ret"].median()),
                  "mean_bh_ret_pct": float(d["bh_ret"].mean()),
                  "touch_rate": float(d["touched"].mean()),
                  "mean_strat_net20bps_pct": float(d["strat_ret"].mean()) - FRICTION,
                  "n": int(len(d))}

        def _dec_stat(q, key):
            return rows[q - 1][key]

        top2 = d[dec >= 9]
        spreads = {
            "strat_D10_minus_D1": _dec_stat(10, "mean_strat_ret_pct") - _dec_stat(1, "mean_strat_ret_pct"),
            "bh_D10_minus_D1": _dec_stat(10, "mean_bh_ret_pct") - _dec_stat(1, "mean_bh_ret_pct"),
            "strat_D9D10_minus_pooled": float(top2["strat_ret"].mean()) - pooled["mean_strat_ret_pct"],
            "bh_D9D10_minus_pooled": float(top2["bh_ret"].mean()) - pooled["mean_bh_ret_pct"],
            "touch_D10_minus_D1": _dec_stat(10, "touch_rate") - _dec_stat(1, "touch_rate"),
        }
        # Barrier-mechanic share: strategy minus buy-and-hold, pooled (selection-free)
        spreads["barrier_mechanic_pooled_strat_minus_bh"] = (
            pooled["mean_strat_ret_pct"] - pooled["mean_bh_ret_pct"])

        # ── Vol-control: f_vol_60d quintiles x decile<=3 vs >=8 ──
        vol = X.loc[d.index, "f_vol_60d"]
        vq = pd.qcut(vol, 5, labels=False, duplicates="drop") + 1
        vol_ctrl = []
        for v in range(1, 6):
            mv = vq == v
            lo, hi = mv & (dec <= 3), mv & (dec >= 8)
            vol_ctrl.append({
                "vol_quintile": v, "n_lo": int(lo.sum()), "n_hi": int(hi.sum()),
                "vol_60d_median": float(vol[mv].median()),
                "touch_lo": float(d.loc[lo, "touched"].mean()) if lo.any() else None,
                "touch_hi": float(d.loc[hi, "touched"].mean()) if hi.any() else None,
                "strat_lo_pct": float(d.loc[lo, "strat_ret"].mean()) if lo.any() else None,
                "strat_hi_pct": float(d.loc[hi, "strat_ret"].mean()) if hi.any() else None,
            })
            vol_ctrl[-1]["touch_spread"] = (
                (vol_ctrl[-1]["touch_hi"] - vol_ctrl[-1]["touch_lo"])
                if vol_ctrl[-1]["touch_hi"] is not None and vol_ctrl[-1]["touch_lo"] is not None else None)
            vol_ctrl[-1]["strat_spread_pct"] = (
                (vol_ctrl[-1]["strat_hi_pct"] - vol_ctrl[-1]["strat_lo_pct"])
                if vol_ctrl[-1]["strat_hi_pct"] is not None and vol_ctrl[-1]["strat_lo_pct"] is not None else None)

        results["targets"][T] = {"config": cfg, "sanity_vs_meta": sanity,
                                 "per_decile": rows, "pooled": pooled,
                                 "spreads": spreads, "vol_control": vol_ctrl}

        # ── Print ──
        print(f"\n{'='*118}\n{T}  (barrier +{barrier:.0f}%, K={K} trading bars)  "
              f"n={len(d):,}  | sanity: max|count diff|={sanity['max_abs_count_diff']}, "
              f"max|hit-rate diff|={sanity['max_abs_hit_rate_diff']:.4f}, "
              f"touch==hit: {sanity['hit_consistency_check']}\n{'='*118}")
        hdr = (f"{'dec':>3} {'n':>7} {'touch':>6} {'meanSR%':>8} {'medSR%':>7} "
               f"{'termOnly%':>9} {'BH%':>7} {'meanDD%':>8} {'DD<=-20':>8} "
               f"{'bars2T':>6} {'net20bp%':>8} {'ret/|DD|':>8}")
        print(hdr); print("-" * len(hdr))
        for r in rows:
            print(f"{r['decile']:>3} {r['n']:>7,} {r['touch_rate']:>6.3f} "
                  f"{r['mean_strat_ret_pct']:>8.2f} {r['median_strat_ret_pct']:>7.2f} "
                  f"{(r['mean_terminal_only_ret_pct'] if r['mean_terminal_only_ret_pct'] is not None else float('nan')):>9.2f} "
                  f"{r['mean_bh_ret_pct']:>7.2f} {r['mean_max_dd_pct']:>8.2f} "
                  f"{r['share_dd_le_-20pct']:>8.3f} "
                  f"{(r['mean_bars_to_touch'] if r['mean_bars_to_touch'] is not None else float('nan')):>6.1f} "
                  f"{r['mean_strat_net20bps_pct']:>8.2f} "
                  f"{(r['ret_over_abs_dd'] if r['ret_over_abs_dd'] is not None else float('nan')):>8.2f}")
        print(f"POOLED: strat {pooled['mean_strat_ret_pct']:.2f}% (med {pooled['median_strat_ret_pct']:.2f}%), "
              f"BH {pooled['mean_bh_ret_pct']:.2f}%, touch {pooled['touch_rate']:.3f}, "
              f"net20bps {pooled['mean_strat_net20bps_pct']:.2f}%")
        print(f"SPREADS: strat D10-D1 {spreads['strat_D10_minus_D1']:+.2f}pp | "
              f"BH D10-D1 {spreads['bh_D10_minus_D1']:+.2f}pp | "
              f"strat (D9+D10)-pooled {spreads['strat_D9D10_minus_pooled']:+.2f}pp | "
              f"BH (D9+D10)-pooled {spreads['bh_D9D10_minus_pooled']:+.2f}pp | "
              f"barrier mechanic (pooled strat-BH) {spreads['barrier_mechanic_pooled_strat_minus_bh']:+.2f}pp")
        print("VOL-CONTROL (f_vol_60d quintile: dec<=3 vs dec>=8):")
        for v in vol_ctrl:
            t_lo = f"{v['touch_lo']:.3f}" if v['touch_lo'] is not None else "  n/a"
            t_hi = f"{v['touch_hi']:.3f}" if v['touch_hi'] is not None else "  n/a"
            s_lo = f"{v['strat_lo_pct']:+.2f}" if v['strat_lo_pct'] is not None else "  n/a"
            s_hi = f"{v['strat_hi_pct']:+.2f}" if v['strat_hi_pct'] is not None else "  n/a"
            ts = f"{v['touch_spread']:+.3f}" if v['touch_spread'] is not None else "n/a"
            ss = f"{v['strat_spread_pct']:+.2f}pp" if v['strat_spread_pct'] is not None else "n/a"
            print(f"  Q{v['vol_quintile']} (vol med {v['vol_60d_median']:5.1f}): "
                  f"touch {t_lo} -> {t_hi} (spread {ts}) | "
                  f"strat {s_lo}% -> {s_hi}% (spread {ss}) | n {v['n_lo']:,}/{v['n_hi']:,}")

    print("\nNOTE: per-window returns only. K=30 bars ~10.5 periods/yr but rows "
          "overlap (same symbol every 5th day) -> do not annualize naively. "
          "Universe = present-day optionable list (survivorship); holdout = one "
          "~9-month regime; max_dd_* are NEGATIVE percents.")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
