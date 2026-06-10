#!/usr/bin/env python3
"""
Time Model Shared Feature Module — v4 feature spec.
===================================================
The ONLY place feature math lives for the time model. Imported by
time_model_data_steward.py / time_model_trainer.py (historical grid) and by
the live scanner (screener_v6.py / nightly scan job).

Design rules (binding):
  - Pure functions only: NO I/O, NO globals, NO FMP/Theta/GCS calls.
    Callers fetch raw inputs, this module computes.
  - Missing raw sections return None per feature — NO median substitution
    here. Median fills happen only in build_vector(), which reports which
    features were imputed.
  - Every kept feature reimplements the steward's training-time math
    exactly (technicals reuse time_model_feature_library verbatim;
    fundamentals are a pure refactor of the steward's
    extract_fundamentals; options replicate the steward per-capture
    chain logic on a normalized chain).

Feature tiers:
  per-symbol  : computed by compute_symbol_features(SymbolRawInputs)
  cross-sect. : computed by compute_cross_sectional_features() over the
                FULL scan universe (refuses to run on < 300 symbols)
"""

from dataclasses import dataclass
from typing import Optional

import math
import numpy as np
import pandas as pd

from time_model_feature_library import compute_price_technicals

FEATURE_SPEC_VERSION = "v4.0"

# Features dropped from the v3 (59-feature) set for v4. Reasons: constant in
# training (f_buyback_yield), perfectly collinear (f_drawdown, f_momentum_abs),
# universe-composition-sensitive ranks (f_momentum_20d_rank, f_quality_rank),
# or chain-window-sensitive aggregates with near-zero importance (opt_*).
V4_DROPS = [
    "f_buyback_yield",
    "f_drawdown",
    "f_momentum_abs",
    "f_momentum_20d_rank",
    "f_quality_rank",
    "f_opt_gamma_oi_x",
    "f_opt_skew_z",
    "opt_net_gamma",
    "opt_skew_25d",
    "opt_total_oi",
    "opt_volume_to_oi",
]

# The literal v4 keep-list: the 59 features in time_model_v3.pkl["features"]
# minus V4_DROPS. Materialized as a literal (sorted) so there is NO runtime
# dependency on the v3 pickle. Exactly 48 names.
FEATURES_V4 = [
    "f_altman_z_pit",
    "f_current_ratio",
    "f_debt_equity",
    "f_dist_52w_high",
    "f_dist_52w_low",
    "f_earnings_yield",
    "f_eps_growth",
    "f_fcf_yield",
    "f_gross_margin",
    "f_gross_margin_delta",
    "f_momentum_12m",
    "f_momentum_1m",
    "f_momentum_20d",
    "f_momentum_3m",
    "f_momentum_6m",
    "f_net_margin",
    "f_op_margin",
    "f_op_margin_delta",
    "f_opt_iv_momentum",
    "f_opt_iv_rank",
    "f_pb",
    "f_pb_rank",
    "f_pe",
    "f_piotroski_pit",
    "f_prox_raw",
    "f_ps",
    "f_quality",
    "f_rev_growth",
    "f_rev_growth_3y",
    "f_rev_growth_rank",
    "f_roa",
    "f_roe",
    "f_roe_over_pb",
    "f_roe_rank",
    "f_roic",
    "f_rsi",
    "f_rsi_rank",
    "f_rsi_x_quality",
    "f_rsi_x_revgrow",
    "f_sector_momentum",
    "f_trend_strength",
    "f_upside_rank",
    "f_vol_20d",
    "f_vol_60d",
    "f_volume_trend",
    "opt_atm_iv",
    "opt_atm_theta",
    "opt_atm_vega",
]
# NOTE: list must stay sorted() — trainer asserts and serving hard-asserts
# pkl["features"] == FEATURES_V4.
FEATURES_V4 = sorted(FEATURES_V4)
assert len(FEATURES_V4) == 48, f"FEATURES_V4 must have 48 names, got {len(FEATURES_V4)}"

# Technical features taken verbatim from time_model_feature_library
TECHNICAL_FEATURES = [
    "f_rsi", "f_trend_strength", "f_momentum_20d", "f_momentum_1m",
    "f_momentum_3m", "f_momentum_6m", "f_momentum_12m", "f_prox_raw",
    "f_dist_52w_high", "f_dist_52w_low", "f_vol_20d", "f_vol_60d",
    "f_volume_trend",
]

# Fundamental features (pure refactor of steward extract_fundamentals)
FUNDAMENTAL_FEATURES = [
    "f_net_margin", "f_gross_margin", "f_op_margin", "f_roe", "f_roa",
    "f_roic", "f_current_ratio", "f_pe", "f_ps", "f_pb", "f_fcf_yield",
    "f_earnings_yield", "f_rev_growth", "f_eps_growth", "f_rev_growth_3y",
    "f_op_margin_delta", "f_gross_margin_delta", "f_piotroski_pit",
    "f_altman_z_pit", "f_debt_equity",
]

OPTION_FEATURES = [
    "opt_atm_iv", "opt_atm_vega", "opt_atm_theta",
    "f_opt_iv_rank", "f_opt_iv_momentum",
]

# Cross-sectional features added by compute_cross_sectional_features()
CROSS_SECTIONAL_FEATURES = [
    "f_sector_momentum", "f_rsi_rank", "f_pb_rank",
    "f_rev_growth_rank", "f_roe_rank", "f_upside_rank",
]

# Refuse to compute cross-sectional ranks on degenerate partial scans
MIN_CROSS_SECTION = 300

# Client-side replica of the ThetaData strike_range used in the training
# captures (download_theta_expanded.py:125): keep the N strikes nearest the
# underlying, per expiration, per right.
STRIKES_NEAREST_UNDERLYING = 5

# IV-history transform windows (steward :374-390 semantics, cadence pinned)
IV_RANK_WINDOW = 252          # trailing samples, current included
IV_MOMENTUM_SAMPLES = 5       # diff over 5 samples of the weekly series


# ─────────────────────────────────────────────────────────────────────────────
# Raw input container
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SymbolRawInputs:
    """Raw, caller-fetched inputs for one symbol on one as-of date.

    daily_bars        : [{date, open, high, low, close, volume}] ascending,
                        ending at asof_date (entry bar last).
    income_annual /
    balance_annual /
    cashflow_annual /
    key_metrics_annual: FMP annual statement rows NEWEST-FIRST, already
                        PIT-filtered by the CALLER (steward: _pit_records;
                        scanner: latest cache = PIT by construction).
    option_chain      : EOD contracts as-of <= 7 calendar days before asof:
                        {right:'CALL'|'PUT', expiration, strike, delta, gamma,
                         theta, vega, implied_vol, iv_error, open_interest,
                         volume}. None when no chain is available.
    atm_iv_history    : [(date, atm_iv)] ascending, dates strictly <= asof,
                        <= 252 samples, EXCLUDING the current capture (the
                        current ATM IV is derived from option_chain; any
                        history sample dated == asof_date is dropped before
                        the transforms to avoid double counting).
    """
    symbol: str
    asof_date: str
    price: float
    daily_bars: list
    income_annual: list
    balance_annual: list
    cashflow_annual: list
    key_metrics_annual: list
    option_chain: Optional[list] = None
    atm_iv_history: Optional[list] = None


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers (steward-faithful)
# ─────────────────────────────────────────────────────────────────────────────
def _safe_divide(num, den):
    """Verbatim steward safe_divide semantics: 0.0 on zero/None denominator."""
    if den is None or den == 0:
        return 0.0
    return float(num) / float(den)


def _is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return bool(math.isnan(float(v)))
    except (TypeError, ValueError):
        return True


# ─────────────────────────────────────────────────────────────────────────────
# (a) Technicals — exact reuse of the steward path
# ─────────────────────────────────────────────────────────────────────────────
def compute_technical_features(daily_bars: list, asof_date: str) -> dict:
    """Run time_model_feature_library.compute_price_technicals over the bar
    history and take the LAST row — the steward's existing path verbatim, so
    historical parity is automatic (ewm/rolling values at the last row depend
    only on bars <= asof)."""
    if not daily_bars:
        raise ValueError("daily_bars is empty — technicals require price history")

    df = pd.DataFrame(daily_bars)
    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError("daily_bars rows must carry at least {date, close}")
    # _load_prices-style fallbacks for sparse bar dicts
    if "high" not in df.columns:
        df["high"] = df["close"]
    if "low" not in df.columns:
        df["low"] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["high"] = df["high"].fillna(df["close"])
    df["low"] = df["low"].fillna(df["close"])
    df["volume"] = df["volume"].fillna(0.0)

    df = df.sort_values("date").reset_index(drop=True)
    last_date = str(df["date"].iloc[-1])[:10]
    if last_date != str(asof_date)[:10]:
        raise ValueError(
            f"daily_bars must end at asof_date: last bar {last_date} != asof {asof_date}"
        )

    tech = compute_price_technicals(df)
    last = tech.iloc[-1]
    return {f: float(last[f]) for f in TECHNICAL_FEATURES}


# ─────────────────────────────────────────────────────────────────────────────
# (b) Fundamentals — pure refactor of steward extract_fundamentals(:155-273)
# ─────────────────────────────────────────────────────────────────────────────
def compute_fundamental_features(
    price: float,
    income_annual: list,
    balance_annual: list,
    cashflow_annual: list,
    key_metrics_annual: list,
) -> dict:
    """Faithful scalar refactor of the steward's extract_fundamentals, taking
    the four PIT-filtered (newest-first) statement lists instead of reading
    from disk. Given the same lists, returns bit-identical values (including
    the steward's 0.0 conventions for partially-missing fields).

    If ALL FOUR lists are empty/None the raw section is considered missing and
    every fundamental feature returns None (build_vector handles imputation
    and reports it)."""
    vi = income_annual or []
    vb = balance_annual or []
    vcf = cashflow_annual or []
    vkm = key_metrics_annual or []

    if not (vi or vb or vcf or vkm):
        return {f: None for f in FUNDAMENTAL_FEATURES}

    feats = {}
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
    feats["f_net_margin"] = _safe_divide(net_income, revenue)
    feats["f_gross_margin"] = _safe_divide(gross_profit, revenue)
    feats["f_op_margin"] = _safe_divide(operating_income, revenue)

    # Quality ratios
    feats["f_roe"] = min(_safe_divide(net_income, equity), 1.0) if equity > 0 else 0.0
    feats["f_roa"] = _safe_divide(net_income, total_assets)
    feats["f_roic"] = lkm.get("returnOnInvestedCapital") or 0.0
    feats["f_current_ratio"] = lkm.get("currentRatio") or 0.0

    # Valuation
    if price > 0 and shares > 0:
        feats["f_pe"] = _safe_divide(price, _safe_divide(net_income, shares)) if net_income > 0 else 0.0
        feats["f_ps"] = _safe_divide(price, _safe_divide(revenue, shares)) if revenue > 0 else 0.0
        feats["f_pb"] = _safe_divide(price, _safe_divide(equity, shares)) if equity > 0 else 0.0
    else:
        feats["f_pe"] = 0.0
        feats["f_ps"] = 0.0
        feats["f_pb"] = 0.0

    feats["f_fcf_yield"] = _safe_divide(fcf, price * shares) if price > 0 and shares > 0 else 0.0
    feats["f_earnings_yield"] = _safe_divide(eps, price) if price > 0 else 0.0

    # Growth (1y, 3y) — total growth, NOT CAGR
    def _growth(records, key, years):
        if len(records) > years and records[years].get(key, 0) not in (0, None):
            return _safe_divide(records[0].get(key, 0), records[years].get(key, 0)) - 1
        return 0.0

    feats["f_rev_growth"] = _growth(vi, "revenue", 1)
    feats["f_eps_growth"] = _growth(vi, "eps", 1)
    feats["f_rev_growth_3y"] = _growth(vi, "revenue", 3)

    # Op margin delta (1y)
    if len(vi) > 1:
        om0 = _safe_divide(vi[0].get("operatingIncome", 0), vi[0].get("revenue", 0) or 1)
        om1 = _safe_divide(vi[1].get("operatingIncome", 0), vi[1].get("revenue", 0) or 1)
        feats["f_op_margin_delta"] = om0 - om1
    else:
        feats["f_op_margin_delta"] = 0.0

    # Gross margin delta
    if len(vi) > 1:
        gm0 = _safe_divide(vi[0].get("grossProfit", 0), vi[0].get("revenue", 0) or 1)
        gm1 = _safe_divide(vi[1].get("grossProfit", 0), vi[1].get("revenue", 0) or 1)
        feats["f_gross_margin_delta"] = gm0 - gm1
    else:
        feats["f_gross_margin_delta"] = 0.0

    # Piotroski proxy (simplified, 0-5 — NOT the FMP 0-9 score)
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

    # Altman Z proxy (simplified, statement-derived — NOT FMP's altmanZScore)
    ebit = li.get("ebit", 0) or 0
    if total_assets > 0:
        wc = (lb.get("totalCurrentAssets", 0) or 0) - (lb.get("totalCurrentLiabilities", 0) or 0)
        z = (1.2 * _safe_divide(wc, total_assets)
             + 1.4 * _safe_divide(li.get("retainedEarnings", net_income), total_assets)
             + 3.3 * _safe_divide(ebit, total_assets)
             + 0.6 * _safe_divide(equity, (lb.get("totalLiabilities", 0) or 1))
             + 1.0 * _safe_divide(revenue, total_assets))
        feats["f_altman_z_pit"] = min(max(z, 0), 20)
    else:
        feats["f_altman_z_pit"] = 0.0

    feats["f_debt_equity"] = _safe_divide(lb.get("totalDebt", 0) or 0, equity) if equity > 0 else 0.0

    return feats


def compute_quality_score(feats: dict):
    """Scalar twin of time_model_feature_library.compute_pit_quality_score
    (:88-115), derived from the module's own proxy sub-features."""
    pio = feats.get("f_piotroski_pit")
    if _is_missing(pio):
        return None
    pio = float(pio)
    roe = 0.0 if _is_missing(feats.get("f_roe")) else float(feats["f_roe"])
    roic = 0.0 if _is_missing(feats.get("f_roic")) else float(feats["f_roic"])
    gm = 0.0 if _is_missing(feats.get("f_gross_margin")) else float(feats["f_gross_margin"])
    az = feats.get("f_altman_z_pit")

    score = (pio / 9.0) * 0.40
    if _is_missing(az):
        # redistribute the Altman weight to Piotroski (library NaN branch)
        score += (pio / 9.0) * 0.20
    else:
        score += min(float(az) / 20.0, 1.0) * 0.20
    score += min(max(roe, 0.0), 0.30) / 0.30 * 0.15
    score += min(max(roic, 0.0), 0.20) / 0.20 * 0.10
    score += min(gm, 0.60) / 0.60 * 0.15
    return min(score, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# (c) Options — steward per-capture chain logic (:347-368) on a normalized chain
# ─────────────────────────────────────────────────────────────────────────────
_CHAIN_NUMERIC_COLS = ["delta", "gamma", "theta", "vega", "implied_vol",
                       "open_interest", "volume"]


def normalize_chain(option_chain: list, underlying_price: float) -> list:
    """Normalize a raw option chain to the training-capture contract:

    1) per (expiration, right): keep the STRIKES_NEAREST_UNDERLYING strikes
       nearest the underlying price (client-side replica of the ThetaData
       strike_range used by download_theta_expanded.py:125);
    2) then the steward's quality filter: implied_vol > 0 and, when the
       iv_error field is present, iv_error < 0.1.

    Returns a list of contract dicts (possibly empty)."""
    if not option_chain:
        return []

    df = pd.DataFrame(option_chain)
    # Steward fills wholly-missing columns with 0.0 (:290-293)
    for col in _CHAIN_NUMERIC_COLS:
        if col not in df.columns:
            df[col] = 0.0
    if "right" not in df.columns:
        return []

    # 1) strike window replica (server-side selection happened BEFORE any
    #    iv filtering, so trim first, filter second)
    if ("strike" in df.columns and "expiration" in df.columns
            and underlying_price is not None and underlying_price > 0):
        df = df.copy()
        df["_dist"] = (pd.to_numeric(df["strike"], errors="coerce") - float(underlying_price)).abs()
        df = (
            df.sort_values("_dist", kind="stable")
              .groupby(["expiration", "right"], sort=False, group_keys=False)
              .head(STRIKES_NEAREST_UNDERLYING)
        )
        df = df.drop(columns=["_dist"]).sort_index()

    # 2) steward iv quality mask (:295-298)
    mask = df["implied_vol"] > 0
    if "iv_error" in df.columns:
        mask &= df["iv_error"] < 0.1
    df = df[mask]

    if df.empty:
        return []
    return df.to_dict("records")


def compute_chain_features(chain: list) -> dict:
    """Steward per-capture ATM logic (:347-368), lifted verbatim:
      opt_atm_iv    = implied_vol of the CALL with delta nearest 0.50
      opt_atm_vega  = vega  of the delta-nearest-0.50 call
      opt_atm_theta = theta of the delta-nearest-0.50 call
    Operates on an already-normalized chain. Empty chain -> all None."""
    if not chain:
        return {"opt_atm_iv": None, "opt_atm_vega": None, "opt_atm_theta": None}

    df = pd.DataFrame(chain)
    for col in _CHAIN_NUMERIC_COLS:
        if col not in df.columns:
            df[col] = 0.0
    calls = df[df["right"] == "CALL"]

    # ATM IV (delta AND implied_vol must be non-null — steward :348-353)
    atm_iv = 0.0
    if not calls.empty:
        calls_atm = calls.dropna(subset=["delta", "implied_vol"]).copy()
        if not calls_atm.empty:
            calls_atm["dist_50"] = (calls_atm["delta"] - 0.50).abs()
            atm_iv = float(calls_atm.loc[calls_atm["dist_50"].idxmin(), "implied_vol"])

    # ATM Greeks (only delta must be non-null — steward :356-368)
    atm_vega = 0.0
    atm_theta = 0.0
    if not calls.empty:
        calls_atm2 = calls.dropna(subset=["delta"]).copy()
        if not calls_atm2.empty:
            calls_atm2["dist_50"] = (calls_atm2["delta"] - 0.50).abs()
            atm_row = calls_atm2.loc[calls_atm2["dist_50"].idxmin()]
            atm_vega = float(atm_row.get("vega", 0) or 0)
            atm_theta = float(atm_row.get("theta", 0) or 0)

    return {"opt_atm_iv": atm_iv, "opt_atm_vega": atm_vega, "opt_atm_theta": atm_theta}


# ─────────────────────────────────────────────────────────────────────────────
# (d) IV-history transforms — pinned cadence, identical both sides
# ─────────────────────────────────────────────────────────────────────────────
def _history_values_before(atm_iv_history: list, asof_date: str) -> list:
    """[(date, iv)] -> chronologically sorted [(date, iv)] strictly before
    asof_date (samples dated == asof are dropped: the current capture's IV
    comes from the chain)."""
    if not atm_iv_history:
        return []
    asof = str(asof_date)[:10]
    rows = [(str(d)[:10], float(v)) for d, v in atm_iv_history
            if d is not None and v is not None and str(d)[:10] < asof]
    rows.sort(key=lambda x: x[0])
    return rows


def compute_iv_rank(current_iv: float, atm_iv_history: list, asof_date: str):
    """Trailing percentile rank of the current ATM IV within the last
    IV_RANK_WINDOW samples (current included) — steward :377 semantics
    (rolling(252, min_periods=1).rank(pct=True))."""
    if current_iv is None:
        return None
    hist = _history_values_before(atm_iv_history, asof_date)
    window = [v for _, v in hist[-(IV_RANK_WINDOW - 1):]] + [float(current_iv)]
    return float(pd.Series(window).rank(pct=True).iloc[-1])


def compute_iv_momentum(current_iv: float, atm_iv_history: list, asof_date: str):
    """Diff over IV_MOMENTUM_SAMPLES samples of the weekly-resampled
    (last-per-ISO-week) ATM IV series, current sample included at asof_date.
    Pinned v4 cadence: the training captures were weekly Fridays so the
    steward's diff(5) over captures ~= this definition; the weekly resample
    makes it identical for nightly-appended live histories.
    Insufficient samples -> 0.0 (steward diff(5).fillna(0.0) semantics)."""
    if current_iv is None:
        return None
    hist = _history_values_before(atm_iv_history, asof_date)
    dates = [d for d, _ in hist] + [str(asof_date)[:10]]
    values = [v for _, v in hist] + [float(current_iv)]

    s = pd.Series(values, index=pd.to_datetime(dates)).sort_index()
    iso = s.index.isocalendar()
    weekly = s.groupby([iso.year.values, iso.week.values]).last()
    wv = weekly.values
    if len(wv) >= IV_MOMENTUM_SAMPLES + 1:
        return float(wv[-1] - wv[-(IV_MOMENTUM_SAMPLES + 1)])
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol assembly
# ─────────────────────────────────────────────────────────────────────────────
def compute_symbol_features(raw: SymbolRawInputs) -> dict:
    """Compute every PER-SYMBOL feature (technicals, fundamentals, quality,
    options, engineered interactions) for one symbol on one as-of date.

    Returns {feature_name: float | None}; None marks a missing raw section.
    Cross-sectional features (f_sector_momentum + ranks) are NOT computed
    here — see compute_cross_sectional_features()."""
    feats: dict = {}

    # (a) technicals — library verbatim, last row
    feats.update(compute_technical_features(raw.daily_bars, raw.asof_date))

    # (b) fundamentals — steward extract_fundamentals refactor
    feats.update(compute_fundamental_features(
        raw.price, raw.income_annual, raw.balance_annual,
        raw.cashflow_annual, raw.key_metrics_annual,
    ))

    # quality (derived from the module's OWN proxy sub-features)
    feats["f_quality"] = compute_quality_score(feats)

    # (e) engineered interactions — steward :677-679
    rsi = feats["f_rsi"]
    q = feats["f_quality"]
    feats["f_rsi_x_quality"] = (
        ((100.0 - rsi) / 100.0) * q if q is not None else None
    )
    rg = feats["f_rev_growth"]
    feats["f_rsi_x_revgrow"] = (
        ((100.0 - rsi) / 100.0) * min(float(rg), 2.0) if rg is not None else None
    )
    roe, pb = feats["f_roe"], feats["f_pb"]
    if roe is None or pb is None:
        feats["f_roe_over_pb"] = None
    else:
        feats["f_roe_over_pb"] = float(roe) / float(pb) if pb > 0 else 0.0

    # (c)+(d) options
    if raw.option_chain:
        norm = normalize_chain(raw.option_chain, raw.price)
        chain_feats = compute_chain_features(norm)
        feats.update(chain_feats)
        cur_iv = chain_feats["opt_atm_iv"]
        feats["f_opt_iv_rank"] = compute_iv_rank(cur_iv, raw.atm_iv_history, raw.asof_date)
        feats["f_opt_iv_momentum"] = compute_iv_momentum(cur_iv, raw.atm_iv_history, raw.asof_date)
    else:
        for f in OPTION_FEATURES:
            feats[f] = None

    return feats


# ─────────────────────────────────────────────────────────────────────────────
# Cross-sectional pass — steward :733-756
# ─────────────────────────────────────────────────────────────────────────────
def compute_cross_sectional_features(
    per_symbol: dict, sector_by_symbol: dict, min_n: int = MIN_CROSS_SECTION
) -> dict:
    """One scan-date cross-section in, augmented dicts out.

    per_symbol       : {symbol: features-dict from compute_symbol_features}
    sector_by_symbol : {symbol: sector string}
    min_n            : minimum cross-section size guard (default
                       MIN_CROSS_SECTION); pass a smaller value explicitly
                       instead of monkeypatching the module global.

    Adds (steward :736-756 semantics):
      f_sector_momentum = per-sector MEDIAN of f_momentum_3m (raw return units)
      f_rsi_rank / f_pb_rank / f_rev_growth_rank / f_roe_rank
                        = within-date rank(pct=True, na_option='keep').fillna(0.5)
      f_upside_rank     = rank of f_sector_momentum (same semantics)

    MUST be called on the FULL scan universe — raises on < min_n
    symbols to prevent degenerate ranks on partial scans."""
    if len(per_symbol) < min_n:
        raise ValueError(
            f"cross-section too small: {len(per_symbol)} symbols < "
            f"{min_n} — ranks would be degenerate; pass the full scan universe"
        )

    symbols = list(per_symbol.keys())
    base = pd.DataFrame.from_dict(per_symbol, orient="index")
    base = base.reindex(symbols)
    sectors = pd.Series(
        {s: (sector_by_symbol.get(s) or "Unknown") for s in symbols}
    ).reindex(symbols)

    def _col(name):
        if name in base.columns:
            return pd.to_numeric(base[name], errors="coerce")
        return pd.Series(np.nan, index=base.index, dtype=float)

    # Sector momentum: per-sector median of f_momentum_3m in RAW return units,
    # then fillna(0.0) (steward :736-739 — fill happens BEFORE the rank pass)
    mom3 = _col("f_momentum_3m")
    sector_momentum = mom3.groupby(sectors).transform("median").fillna(0.0)

    rank_cols = {
        "f_rsi_rank": _col("f_rsi"),
        "f_pb_rank": _col("f_pb"),
        "f_rev_growth_rank": _col("f_rev_growth"),
        "f_roe_rank": _col("f_roe"),
        "f_upside_rank": sector_momentum,
    }
    ranks = {
        rank_name: vals.rank(pct=True, na_option="keep").fillna(0.5)
        for rank_name, vals in rank_cols.items()
    }

    out = {}
    for sym in symbols:
        d = dict(per_symbol[sym])
        d["f_sector_momentum"] = float(sector_momentum.loc[sym])
        for rank_name, series in ranks.items():
            d[rank_name] = float(series.loc[sym])
        out[sym] = d
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Vector assembly
# ─────────────────────────────────────────────────────────────────────────────
def build_vector(features: dict, medians: dict, feature_list=FEATURES_V4):
    """Ordered model-input vector.

    None/NaN -> medians[feature] (0.0 if the median itself is unknown), and
    the imputed feature names are RETURNED so the caller can log per-symbol
    imputation counts (a row predicted off medians is a different animal).
    Values are clipped to [-100, 100], matching trainer preprocessing.

    Returns (np.ndarray of shape (1, len(feature_list)), missing: list[str])."""
    vals = []
    missing = []
    for f in feature_list:
        v = features.get(f)
        if _is_missing(v):
            vals.append(float(medians.get(f, 0.0) if medians else 0.0))
            missing.append(f)
        else:
            vals.append(float(v))
    arr = np.asarray(vals, dtype=np.float64).reshape(1, -1)
    arr = np.clip(arr, -100.0, 100.0)
    return arr, missing
