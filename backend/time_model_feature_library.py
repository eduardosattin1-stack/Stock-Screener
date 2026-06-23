#!/usr/bin/env python3
"""
Time Model Feature Library — Vectorized and PIT-correct indicators.
==================================================================
Provides vectorized technical indicator calculations and quality scoring
to build time model training datasets without data leakage.
"""

import numpy as np
import pandas as pd

def compute_rsi(close_series: pd.Series, period: int = 14) -> pd.Series:
    """Vectorized calculation of Relative Strength Index (RSI) using ewm."""
    delta = close_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Wilde's smoothing (exponentially weighted moving average with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    
    # Handle zero division bounds: if avg_loss is 0, RSI is 100 (or 50 if both are 0)
    rsi = np.where(
        avg_loss == 0.0,
        np.where(avg_gain == 0.0, 50.0, 100.0),
        100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    )
    return pd.Series(rsi, index=close_series.index).fillna(50.0)

def compute_price_technicals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute EOD technical indicators on a DataFrame of daily bars.
    
    Expects df columns: ['date', 'open', 'high', 'low', 'close', 'volume'].
    Returns a copy of df with technical features appended.
    """
    df = df.sort_values("date").copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    
    # 1. RSI
    df["f_rsi"] = compute_rsi(close, 14)
    
    # 2. SMAs
    df["f_sma50"] = close.rolling(50, min_periods=1).mean()
    df["f_sma200"] = close.rolling(200, min_periods=1).mean()
    
    # 3. Trend strength
    df["f_trend_strength"] = (df["f_sma50"] - df["f_sma200"]) / df["f_sma200"].replace(0.0, np.nan)
    df["f_trend_strength"] = df["f_trend_strength"].fillna(0.0)
    
    # 4. Momentum returns
    df["f_momentum_20d"] = close.pct_change(20).fillna(0.0)
    df["f_momentum_1m"] = close.pct_change(21).fillna(0.0)
    df["f_momentum_3m"] = close.pct_change(63).fillna(0.0)
    df["f_momentum_6m"] = close.pct_change(126).fillna(0.0)
    df["f_momentum_12m"] = close.pct_change(252).fillna(0.0)
    
    # 5. 52-week high & low (252 trading days)
    yh = high.rolling(252, min_periods=1).max()
    yl = low.rolling(252, min_periods=1).min()
    
    # Proximity to 52-week high
    df["f_prox_raw"] = (close - yl) / (yh - yl).replace(0.0, np.nan)
    df["f_prox_raw"] = df["f_prox_raw"].fillna(0.5).clip(0.0, 1.0)
    
    # 6. Distances from 52-week extremes
    df["f_dist_52w_high"] = (close - yh) / yh.replace(0.0, np.nan)
    df["f_dist_52w_high"] = df["f_dist_52w_high"].fillna(0.0)
    
    df["f_dist_52w_low"] = (close - yl) / yl.replace(0.0, np.nan)
    df["f_dist_52w_low"] = df["f_dist_52w_low"].fillna(0.0)
    
    # 7. Realized Volatility
    log_ret = np.log(close / close.shift(1).replace(0.0, np.nan)).fillna(0.0)
    df["f_vol_20d"] = log_ret.rolling(20).std().fillna(0.0) * np.sqrt(252)
    df["f_vol_60d"] = log_ret.rolling(60).std().fillna(0.0) * np.sqrt(252)
    
    # 8. Volume trend
    vol_mean_20 = volume.rolling(20, min_periods=1).mean()
    vol_mean_120 = volume.rolling(120, min_periods=1).mean()
    df["f_volume_trend"] = vol_mean_20 / vol_mean_120.replace(0.0, np.nan)
    df["f_volume_trend"] = df["f_volume_trend"].fillna(1.0)
    
    return df

def compute_pit_quality_score(df: pd.DataFrame) -> pd.Series:
    """Compute the PIT-correct Quality Score from fundamental metrics."""
    pio = df["f_piotroski_pit"].fillna(0.0)
    az = df.get("f_altman_z_pit") # may contain NaN
    roe = df["f_roe"].fillna(0.0)
    roic = df["f_roic"].fillna(0.0)
    gm = df["f_gross_margin"].fillna(0.0)
    
    score = (pio / 9.0) * 0.40
    
    # Handle Altman Z presence/absence
    if az is not None:
        az_nan = az.isna()
        # Case 1: Altman Z is present
        az_score = (az / 20.0).clip(upper=1.0) * 0.20
        # Case 2: Altman Z is missing (redistribute to Piotroski)
        missing_redist = (pio / 9.0) * 0.20
        
        score += np.where(az_nan, missing_redist, az_score)
    else:
        # All missing
        score += (pio / 9.0) * 0.20
        
    score += roe.clip(lower=0.0).clip(upper=0.30) / 0.30 * 0.15
    score += roic.clip(lower=0.0).clip(upper=0.20) / 0.20 * 0.10
    score += gm.clip(upper=0.60) / 0.60 * 0.15
    
    return score.clip(upper=1.0)
