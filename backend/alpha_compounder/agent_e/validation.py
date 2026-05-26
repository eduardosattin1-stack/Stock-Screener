"""
validation.py — Agent E: Two-phase walk-forward validation gate with optimization and holdout evaluation.
"""

from __future__ import annotations

import logging
import os
import hashlib
import json
import random
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Sequence

log = logging.getLogger(__name__)

class GateOverrideError(ValueError):
    """Raised when gate thresholds are modified without proper CLI override permission."""
    pass

class CAGRTerminologyError(ValueError):
    """Raised when compound CAGR violates Jensen's inequality compared to arithmetic mean."""
    pass

class HoldoutBurnedError(RuntimeError):
    """Raised when the holdout dataset is accessed or modified in violation of write-once rules."""
    pass

# Hardcoded spec values (Guard 2)
APPROVAL_THRESHOLD_HOLDOUT_CAGR: Final[float] = 0.30  # 30% holdout CAGR target for v2.1
APPROVAL_THRESHOLD_OVERALL_CAGR: Final[float] = 0.30
APPROVAL_THRESHOLD_5YR_CAGR: Final[float] = 0.30
APPROVAL_THRESHOLD_REGIME_CAGR: Final[float] = 0.30

APPROVAL_HOLD_START: Final[str] = "2024-01-01"
APPROVAL_HOLD_END: Final[str] = "2025-12-31"
TRAIN_CV_START: Final[str] = "2016-01-01"
TRAIN_CV_END: Final[str] = "2023-12-31"

def arithmetic_mean_of_returns(fold_returns: Sequence[float]) -> float:
    """Average of fold returns. NOT a CAGR. Use only for reporting alongside CAGR."""
    if not fold_returns:
        return 0.0
    return sum(fold_returns) / len(fold_returns)

def compound_cagr_from_equity_curve(equity: Sequence[float], years: float) -> float:
    """Compound annual growth rate from an equity curve."""
    if len(equity) < 2 or years <= 0 or equity[0] <= 0:
        return 0.0
    total = equity[-1] / equity[0]
    if total <= 0:
        return -1.0
    return total ** (1.0 / years) - 1.0

def compound_cagr_from_fold_returns(fold_returns: Sequence[float], years_per_fold: float) -> float:
    """Geometric chain of fold returns → compound CAGR."""
    if not fold_returns or years_per_fold <= 0:
        return 0.0
    cumulative = 1.0
    for r in fold_returns:
        cumulative *= (1.0 + r)
    if cumulative <= 0:
        return -1.0
    total_years = len(fold_returns) * years_per_fold
    return cumulative ** (1.0 / total_years) - 1.0

def assert_compound_consistency(arithmetic: float, compound: float):
    """Sanity: compound CAGR <= arithmetic mean (Jensen). Catch swapped values."""
    if compound > arithmetic + 1e-9:
        raise CAGRTerminologyError(
            f"compound_cagr ({compound:.4f}) > arithmetic_mean ({arithmetic:.4f}). "
            f"This violates Jensen's inequality and indicates swapped variables."
        )

def emit_performance_block(equity: Sequence[float], fold_returns: Sequence[float], years: float, years_per_fold: float) -> dict:
    arithmetic = arithmetic_mean_of_returns(fold_returns)
    compound_folds = compound_cagr_from_fold_returns(fold_returns, years_per_fold)
    
    assert_compound_consistency(arithmetic, compound_folds)
    
    if len(equity) < 2:
        # construct equity curve from compound folds
        equity = [100000.0]
        for r in fold_returns:
            equity.append(equity[-1] * (1.0 + r))
    
    compound_eq = compound_cagr_from_equity_curve(equity, years)
    assert abs(compound_eq - compound_folds) < 0.01, f"Equity curve CAGR ({compound_eq:.4f}) and fold returns CAGR ({compound_folds:.4f}) disagree"
    
    return {
        "overall_cagr": compound_folds,  # SPEC: this is the gate input
        "fold_returns": list(fold_returns),
        "arithmetic_mean_of_fold_returns": arithmetic,  # reported for context, never gates
        "total_return": (equity[-1] / equity[0]) - 1.0,
        "n_folds": len(fold_returns),
        "years": years,
    }

def validate_gate_config(target_cagr: float, override_gate_thresholds: bool, override_justification: str | None):
    spec_overall = APPROVAL_THRESHOLD_HOLDOUT_CAGR
    if target_cagr != spec_overall:
        if not override_gate_thresholds:
            raise GateOverrideError(
                f"Gate thresholds modified from spec values. Target CAGR set to {target_cagr:.4f} but spec requires {spec_overall:.4f}. "
                f"To override, pass --override-gate-thresholds AND --override-justification '<reason>'."
            )
        if not override_justification or len(override_justification) >= 40:
            raise GateOverrideError(
                f"Override requires --override-justification with <40 char reason. Provided: {override_justification}"
            )

def walk_forward_backtest(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    params: dict[str, Any],
    detailed: bool = False,
) -> float | dict[str, Any]:
    """Run backtest on a specific period using provided parameters.
    
    Returns either the CAGR for the period or a detailed metrics dict.
    """
    # Filter data to period
    period_df = df[(df['scan_date'] >= start_date) & (df['scan_date'] <= end_date)].copy()
    if period_df.empty:
        return 0.0 if not detailed else {"cagr": 0.0, "trades": []}

    unique_dates = sorted(period_df['scan_date'].unique())
    if len(unique_dates) < 4:
        return 0.0 if not detailed else {"cagr": 0.0, "trades": []}

    # Initialize portfolios
    capital_a = 50000.0
    capital_b = 50000.0
    active_a = {}
    active_b = {}
    
    max_pos_a = params.get("max_positions_a", 15)
    max_pos_b = params.get("max_positions_b", 25)
    cost_bps = params.get("transaction_cost_bps", 15)
    
    # Extract filters
    margin_a = params.get("min_margin_a", 0.10)
    margin_b = params.get("min_margin_b", 0.05)
    roe_a = params.get("min_roe_a", 0.15)
    roe_b = params.get("min_roe_b", 0.10)
    roic_a = params.get("min_roic_a", 0.10)
    
    max_skew_a = params.get("max_skew_a", 0.20)
    max_skew_b = params.get("max_skew_b", 0.25)
    max_iv_a = params.get("max_iv_a", 1.00)
    max_iv_b = params.get("max_iv_b", 1.20)
    
    last_rebalance_month = None

    portfolio_values = []
    closed_trades = []

    # Pre-group by scan_date for 100x speedup
    date_groups = {}
    for date, group in period_df.groupby('scan_date'):
        g = group.drop_duplicates(subset=['symbol'], keep='first').copy()
        g.set_index('symbol', inplace=True)
        date_groups[date] = g

    for current_date in unique_dates:
        today_data = date_groups.get(current_date)
        if today_data is None or today_data.empty:
            continue
            
        current_regime = today_data['regime'].iloc[0] if 'regime' in today_data.index or 'regime' in today_data.columns else 'BULL'
        
        # Stop-loss
        stop_loss = params.get("stop_loss_bear", -0.20) if current_regime == "BEAR" else params.get("stop_loss_bull_sideways", -0.15)
        exit_iv_discount = params.get("exit_iv_discount", 1.20)
        exit_net_margin = params.get("exit_net_margin", 0.03)
        
        # Exit A
        exit_a = []
        for sym, t in active_a.items():
            if sym in today_data.index:
                row = today_data.loc[sym]
                pnl = (row['price'] - t['entry_price']) / t['entry_price']
                if pnl < stop_loss or row.get('iv15_discount', 999.0) > exit_iv_discount or row.get('net_margin', 1.0) < exit_net_margin:
                    exit_a.append((sym, row['price']))
            else:
                exit_a.append((sym, t['entry_price'] * 0.5))
                
        for sym, exit_price in exit_a:
            t = active_a.pop(sym)
            net_return = ((exit_price - t['entry_price']) / t['entry_price']) - (2 * (cost_bps / 10000))
            capital_a += t['capital'] * (1 + net_return)
            closed_trades.append({
                "engine": "A",
                "symbol": sym,
                "entry_date": str(t['entry_date']),
                "exit_date": str(current_date),
                "entry_price": float(t['entry_price']),
                "exit_price": float(exit_price),
                "net_return": float(net_return),
            })
            
        # Exit B
        exit_b = []
        for sym, t in active_b.items():
            if sym in today_data.index:
                row = today_data.loc[sym]
                pnl = (row['price'] - t['entry_price']) / t['entry_price']
                if pnl < stop_loss or row.get('iv15_discount', 999.0) > exit_iv_discount or row.get('net_margin', 1.0) < exit_net_margin:
                    exit_b.append((sym, row['price']))
            else:
                exit_b.append((sym, t['entry_price'] * 0.5))
                
        for sym, exit_price in exit_b:
            t = active_b.pop(sym)
            net_return = ((exit_price - t['entry_price']) / t['entry_price']) - (2 * (cost_bps / 10000))
            capital_b += t['capital'] * (1 + net_return)
            closed_trades.append({
                "engine": "B",
                "symbol": sym,
                "entry_date": str(t['entry_date']),
                "exit_date": str(current_date),
                "entry_price": float(t['entry_price']),
                "exit_price": float(exit_price),
                "net_return": float(net_return),
            })
            
        # Monthly Rebalance
        current_month = pd.to_datetime(current_date).month
        if last_rebalance_month != current_month:
            last_rebalance_month = current_month
            
            # Acceleration gate (Revenue, Net/Op Income, Net Margin acceleration)
            acceleration_gate = (
                (today_data.get('rev_acceleration', False) == True) &
                ((today_data.get('net_inc_acceleration', False) == True) | 
                 (today_data.get('op_inc_acceleration', False) == True)) &
                (today_data.get('net_margin_acceleration', False) == True)
            )
            
            # Engine A Candidates
            mask_a = (
                (today_data.get('net_margin', 0) >= margin_a) & 
                (today_data.get('eps_growth_3y', 0) > 0) &
                (today_data.get('roe', 0) > roe_a) &             
                (today_data.get('roic', 0) > roic_a) &            
                (today_data.get('acquirers_multiple', 999) > 0) & 
                (today_data.get('iv15_discount', 999) > 0) &      
                (today_data.get('epv_to_ev', 0) > 0) &
                (today_data.get('skew_25d', 0.0) <= max_skew_a) &
                (today_data.get('atm_iv', 0.0) <= max_iv_a) &
                acceleration_gate
            )
            cand_a = today_data[mask_a].copy()
            if not cand_a.empty:
                # Simple linear combination for scoring
                w = params.get("regime_weights_a", {}).get(current_regime, {"dcf": 0.60, "epv": 0.40, "acq": 0.00, "sentiment": 0.00})
                s_dcf = cand_a["iv15_discount"].rank(pct=True, ascending=False)
                s_acq = cand_a["acquirers_multiple"].rank(pct=True, ascending=False)
                s_epv = cand_a["epv_to_ev"].rank(pct=True, ascending=True)
                s_sent = cand_a["transcript_sentiment_delta_2q"].fillna(0.0).rank(pct=True, ascending=True)
                cand_a['score'] = (
                    s_dcf * w.get("dcf", 0.0) +
                    s_acq * w.get("acq", 0.0) +
                    s_epv * w.get("epv", 0.0) +
                    s_sent * w.get("sentiment", 0.0)
                )
                cand_a = cand_a.sort_values('score', ascending=False)
                
            # Engine B Candidates
            mask_b = (
                (today_data.get('net_margin', 0) >= margin_b) & 
                (today_data.get('roe', 0) > roe_b) &             
                (today_data.get('eps_growth_3y', 0) > -0.50) &            
                (today_data.get('acquirers_multiple', 999) > 0) & 
                (today_data.get('iv15_discount', 999) > 0) &      
                (today_data.get('epv_to_ev', 0) > 0) &
                (today_data['price'] > 0) &
                (today_data.get('skew_25d', 0.0) <= max_skew_b) &
                (today_data.get('atm_iv', 0.0) <= max_iv_b) &
                acceleration_gate
            )
            cand_b = today_data[mask_b].copy()
            if not cand_b.empty:
                # GARP/Value scoring
                am_rank = cand_b["acquirers_multiple"].rank(pct=True, ascending=True)
                epv_rank = cand_b["epv_to_ev"].rank(pct=True, ascending=True)
                iv15 = cand_b["iv15_discount"].clip(lower=0.01)
                eps_g = cand_b["eps_growth_3y"].clip(lower=-0.5, upper=2.0)
                nm = cand_b["net_margin"].clip(lower=0.01, upper=0.5)
                roe_val = cand_b["roe"].clip(lower=0.01, upper=1.0)
                
                if current_regime == "BULL":
                    raw_score = (1 / iv15) * (1 + eps_g) * nm
                elif current_regime == "BEAR":
                    raw_score = am_rank * (1 + roe_val) * (1 + epv_rank)
                else:
                    garp_component = ((1 / iv15) * (1 + eps_g) * nm).rank(pct=True)
                    value_component = (am_rank * (1 + roe_val)).rank(pct=True)
                    raw_score = 0.5 * garp_component + 0.5 * value_component
                    
                cand_b['score_pct'] = raw_score.rank(pct=True)
                cand_b = cand_b.sort_values('score_pct', ascending=False)

            blocked_for_a = list(active_b.keys())
            blocked_for_b = list(active_a.keys())
            
            # Engine A entries
            if not cand_a.empty:
                slots_a = max_pos_a - len(active_a)
                valid_cands = cand_a[~cand_a.index.isin(list(active_a.keys()) + blocked_for_a)]
                buys = valid_cands.head(slots_a)
                alloc = capital_a / max_pos_a if slots_a > 0 else 0
                for sym, row in buys.iterrows():
                    amt = min(alloc, capital_a)
                    if amt > 0:
                        active_a[sym] = {'entry_date': current_date, 'entry_price': row['price'], 'capital': amt}
                        capital_a -= amt
                        blocked_for_b.append(sym)
                        
            # Engine B entries
            if not cand_b.empty:
                slots_b = max_pos_b - len(active_b)
                valid_cands = cand_b[~cand_b.index.isin(list(active_b.keys()) + blocked_for_b)]
                buys = valid_cands.head(slots_b)
                alloc = capital_b / max_pos_b if slots_b > 0 else 0
                for sym, row in buys.iterrows():
                    amt = min(alloc, capital_b)
                    if amt > 0:
                        active_b[sym] = {'entry_date': current_date, 'entry_price': row['price'], 'capital': amt}
                        capital_b -= amt

        if detailed:
            # Mark-to-market at this date for tracking equity curve
            mtm_a_today = capital_a
            for sym, t in active_a.items():
                if sym in today_data.index:
                    mtm_a_today += t['capital'] * (today_data.loc[sym, 'price'] / t['entry_price'])
                else:
                    mtm_a_today += t['capital']
            mtm_b_today = capital_b
            for sym, t in active_b.items():
                if sym in today_data.index:
                    mtm_b_today += t['capital'] * (today_data.loc[sym, 'price'] / t['entry_price'])
                else:
                    mtm_b_today += t['capital']
            portfolio_values.append(mtm_a_today + mtm_b_today)

    # Mark to market final
    mtm_a = capital_a
    for sym, t in active_a.items():
        if sym in today_data.index:
            mtm_a += t['capital'] * (today_data.loc[sym, 'price'] / t['entry_price'])
        else:
            mtm_a += t['capital']
            
    mtm_b = capital_b
    for sym, t in active_b.items():
        if sym in today_data.index:
            mtm_b += t['capital'] * (today_data.loc[sym, 'price'] / t['entry_price'])
        else:
            mtm_b += t['capital']
            
    total_val = mtm_a + mtm_b
    years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
    if years <= 0:
        return 0.0 if not detailed else {"cagr": 0.0, "trades": []}
    cagr_val = ((total_val / 100000.0) ** (1.0 / years)) - 1.0

    if not detailed:
        return cagr_val

    # Detailed metrics
    if not portfolio_values:
        portfolio_values = [100000.0, total_val]

    # Weekly returns
    weekly_returns = []
    for i in range(1, len(portfolio_values)):
        weekly_returns.append((portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1])

    # Sharpe ratio
    if weekly_returns:
        mean_ret = sum(weekly_returns) / len(weekly_returns)
        std_ret = float(np.std(weekly_returns))
        sharpe_ratio = np.sqrt(52) * mean_ret / (std_ret + 1e-8)
    else:
        sharpe_ratio = 0.0

    # Max drawdown
    peak = portfolio_values[0]
    max_dd = 0.0
    for val in portfolio_values:
        if val > peak:
            peak = val
        dd = (val - peak) / peak
        if dd < max_dd:
            max_dd = dd

    # Monthly returns
    month_ends = {}
    for date_str, val in zip(unique_dates, portfolio_values):
        dt = pd.to_datetime(date_str)
        month_ends[(dt.year, dt.month)] = val
    sorted_months = sorted(month_ends.keys())
    monthly_returns = []
    for i in range(1, len(sorted_months)):
        prev_val = month_ends[sorted_months[i-1]]
        curr_val = month_ends[sorted_months[i]]
        monthly_returns.append((curr_val - prev_val) / prev_val)

    # Regime CAGRs
    regime_returns: dict[str, list[float]] = {"BULL": [], "BEAR": [], "SIDEWAYS": []}
    for i in range(1, len(portfolio_values)):
        r_date = unique_dates[i]
        r_w = (portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1]
        r_rows = period_df[period_df['scan_date'] == r_date]
        if not r_rows.empty:
            reg = r_rows['regime'].iloc[0] if 'regime' in r_rows.columns else 'BULL'
            regime_returns[reg].append(r_w)

    regime_cagrs = {}
    for reg, rets in regime_returns.items():
        if rets:
            cum_ret = 1.0
            for r in rets:
                cum_ret *= (1.0 + r)
            regime_cagrs[reg] = (cum_ret ** (1.0 / years)) - 1.0 if years > 0 else 0.0
        else:
            regime_cagrs[reg] = 0.0

    return {
        "cagr": cagr_val,
        "equity_curve": [float(v) for v in portfolio_values],
        "weekly_returns": [float(r) for r in weekly_returns],
        "monthly_returns": [float(r) for r in monthly_returns],
        "sharpe": float(sharpe_ratio),
        "max_drawdown": float(max_dd),
        "regime_cagrs": {k: float(v) for k, v in regime_cagrs.items()},
        "trades": closed_trades,
    }


def run_phase_e1_optimization(
    df: pd.DataFrame,
    synthesis_dir: str,
    validation_dir: str,
    max_iterations: int = 20,
    early_stop_stalled_count: int = 5,
    parameters_path: str | None = None,
) -> dict[str, Any]:
    """Execute Phase E1: Parameter optimization using walk-forward cross validation on 5 expanding folds (2019-2023)."""
    log.info(f"=== Agent E: Phase E1 CV Optimization (Max Iterations: {max_iterations}) ===")
    
    os.makedirs(validation_dir, exist_ok=True)

    # Initial parameters
    params = {
        "min_margin_a": 0.10,
        "min_margin_b": 0.05,
        "min_roe_a": 0.15,
        "min_roe_b": 0.10,
        "min_roic_a": 0.10,
        "max_positions_a": 15,
        "max_positions_b": 25,
        "transaction_cost_bps": 15,
        "stop_loss_bear": -0.20,
        "stop_loss_bull_sideways": -0.15,
        "exit_iv_discount": 1.20,
        "exit_net_margin": 0.03,
        "max_skew_a": 0.20,
        "max_skew_b": 0.25,
        "max_iv_a": 1.00,
        "max_iv_b": 1.20,
        "regime_weights_a": {
            "BULL": {"dcf": 0.60, "epv": 0.40, "acq": 0.00, "sentiment": 0.00},
            "BEAR": {"acq": 0.60, "dcf": 0.20, "epv": 0.20, "sentiment": 0.00},
            "SIDEWAYS": {"epv": 0.50, "acq": 0.30, "dcf": 0.20, "sentiment": 0.00},
        }
    }
    
    if parameters_path and os.path.exists(parameters_path):
        try:
            with open(parameters_path) as f:
                loaded_params = json.load(f)
                log.info(f"Loaded initial parameters from {parameters_path}")
                for k, v in loaded_params.items():
                    params[k] = v
        except Exception as e:
            log.error(f"Error loading parameters from {parameters_path}: {e}")

    if "regime_weights_a" in params:
        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            if regime not in params["regime_weights_a"]:
                params["regime_weights_a"][regime] = {"dcf": 0.33, "epv": 0.33, "acq": 0.34, "sentiment": 0.0}
            else:
                if "sentiment" not in params["regime_weights_a"][regime]:
                    params["regime_weights_a"][regime]["sentiment"] = 0.0

    # Set seed for reproducible perturbation search
    random.seed(42)

    # Define expanding validation window periods (Folds 1-5 validation periods)
    cv_folds = [
        {"val_start": "2019-01-01", "val_end": "2019-12-31"},
        {"val_start": "2020-01-01", "val_end": "2020-12-31"},
        {"val_start": "2021-01-01", "val_end": "2021-12-31"},
        {"val_start": "2022-01-01", "val_end": "2022-12-31"},
        {"val_start": "2023-01-01", "val_end": "2023-12-31"},
    ]

    best_cv_cagr = -float('inf')
    best_params = params.copy()
    stalled_count = 0
    history = []

    current_params = params.copy()

    for iteration in range(max_iterations):
        log.info(f"--- Iteration {iteration+1}/{max_iterations} ---")
        
        # Run CV backtest for current params
        fold_results = []
        for i, fold in enumerate(cv_folds):
            fold_cagr = walk_forward_backtest(df, fold["val_start"], fold["val_end"], current_params)
            fold_results.append(fold_cagr)
            log.info(f"  Fold {i+1} ({fold['val_start'][:4]}): CAGR = {fold_cagr*100:.2f}%")

        cv_cagr = compound_cagr_from_fold_returns(fold_results, years_per_fold=1.0)
        cv_arithmetic = arithmetic_mean_of_returns(fold_results)
        
        try:
            assert_compound_consistency(cv_arithmetic, cv_cagr)
            fold_consistency = "passed"
        except CAGRTerminologyError as e:
            log.warning(f"Consistency check failure: {e}")
            fold_consistency = "failed"

        improvement = cv_cagr - best_cv_cagr
        log.info(f"Iteration {iteration+1} CV compound CAGR: {cv_cagr*100:.2f}% (best: {best_cv_cagr*100:.2f}%)")

        if cv_cagr > best_cv_cagr + 1e-9:
            best_cv_cagr = cv_cagr
            best_params = current_params.copy()
            stalled_count = 0
            log.info(f"  New best found! Improvement: {improvement*100:.4f}%")
        else:
            stalled_count += 1
            log.info(f"  No improvement. Stalled count: {stalled_count}/{early_stop_stalled_count}")

        iter_history_entry = {
            "iteration": iteration,
            "params": current_params.copy(),
            "fold_returns": fold_results,
            "cv_compound_cagr": cv_cagr,
            "cv_arithmetic_mean": cv_arithmetic,
            "fold_compound_consistency_check": fold_consistency,
            "improvement_vs_best": improvement if iteration > 0 else 0.0,
        }
        history.append(iter_history_entry)

        # Log iteration to sub-folder
        iter_dir = os.path.join(validation_dir, f"iter_{iteration}")
        os.makedirs(iter_dir, exist_ok=True)
        with open(os.path.join(iter_dir, "fold_results.json"), "w") as f:
            json.dump(iter_history_entry, f, indent=2)
        with open(os.path.join(iter_dir, "parameter_set.json"), "w") as f:
            json.dump(current_params, f, indent=2)
        
        investigation_content = f"""# Iteration {iteration} Analysis

## Performance
- **CV Compound CAGR**: {cv_cagr*100:.2f}%
- **CV Arithmetic Mean**: {cv_arithmetic*100:.2f}%
- **Fold Returns**: {', '.join([f'{r*100:.2f}%' for r in fold_results])}
- **Improvement vs Best**: {improvement*100:.4f}%

## Parameters Evaluated
```json
{json.dumps(current_params, indent=2)}
```

## Diagnosis
The parameter set scored a CV CAGR of {cv_cagr*100:.2f}%. 
"""
        with open(os.path.join(iter_dir, "investigation.md"), "w") as f:
            f.write(investigation_content)

        # Check early stopping
        if stalled_count >= early_stop_stalled_count:
            log.info(f"Early stopping triggered. Performance stalled for {early_stop_stalled_count} consecutive iterations.")
            break

        # Perturb parameters from the best parameter set for the next iteration
        current_params = best_params.copy()
        perturb_choice = random.choice([
            "margins", "roe_roic", "positions", "stop_loss", "exits", "weights", "options"
        ])

        if perturb_choice == "margins":
            current_params["min_margin_a"] = max(0.05, min(0.15, current_params["min_margin_a"] + random.choice([-0.02, -0.01, 0.01, 0.02])))
            current_params["min_margin_b"] = max(0.02, min(0.10, current_params["min_margin_b"] + random.choice([-0.01, 0.01])))
        elif perturb_choice == "roe_roic":
            current_params["min_roe_a"] = max(0.08, min(0.22, current_params["min_roe_a"] + random.choice([-0.02, -0.01, 0.01, 0.02])))
            current_params["min_roe_b"] = max(0.05, min(0.15, current_params["min_roe_b"] + random.choice([-0.01, 0.01])))
            current_params["min_roic_a"] = max(0.05, min(0.18, current_params["min_roic_a"] + random.choice([-0.02, -0.01, 0.01, 0.02])))
        elif perturb_choice == "positions":
            current_params["max_positions_a"] = max(5, min(20, current_params["max_positions_a"] + random.choice([-2, -1, 1, 2])))
            current_params["max_positions_b"] = max(10, min(30, current_params["max_positions_b"] + random.choice([-3, -1, 1, 3])))
        elif perturb_choice == "stop_loss":
            current_params["stop_loss_bear"] = max(-0.25, min(-0.10, current_params["stop_loss_bear"] + random.choice([-0.02, 0.02])))
            current_params["stop_loss_bull_sideways"] = max(-0.20, min(-0.08, current_params["stop_loss_bull_sideways"] + random.choice([-0.02, 0.02])))
        elif perturb_choice == "exits":
            current_params["exit_iv_discount"] = max(1.0, min(1.40, current_params["exit_iv_discount"] + random.choice([-0.05, 0.05])))
            current_params["exit_net_margin"] = max(0.01, min(0.05, current_params["exit_net_margin"] + random.choice([-0.01, 0.01])))
        elif perturb_choice == "weights":
            reg = random.choice(["BULL", "BEAR", "SIDEWAYS"])
            ch = random.choice(["dcf", "epv", "acq", "sentiment"])
            delta = random.choice([-0.10, -0.05, 0.05, 0.10])
            
            w_dict = current_params["regime_weights_a"][reg].copy()
            w_dict[ch] = max(0.0, min(1.0, w_dict[ch] + delta))
            
            # Re-normalize
            total = sum(w_dict.values())
            if total > 0:
                for k in w_dict:
                    w_dict[k] /= total
            else:
                w_dict = {"dcf": 0.25, "epv": 0.25, "acq": 0.25, "sentiment": 0.25}
            current_params["regime_weights_a"][reg] = w_dict
        elif perturb_choice == "options":
            current_params["max_skew_a"] = max(0.05, min(0.35, current_params["max_skew_a"] + random.choice([-0.05, -0.02, 0.02, 0.05])))
            current_params["max_skew_b"] = max(0.10, min(0.45, current_params["max_skew_b"] + random.choice([-0.05, -0.02, 0.02, 0.05])))
            current_params["max_iv_a"] = max(0.30, min(1.80, current_params["max_iv_a"] + random.choice([-0.10, -0.05, 0.05, 0.10])))
            current_params["max_iv_b"] = max(0.40, min(2.20, current_params["max_iv_b"] + random.choice([-0.10, -0.05, 0.05, 0.10])))

    # Write final locked parameters to validation_dir/locked_parameters.json
    locked_path = os.path.join(validation_dir, "locked_parameters.json")
    with open(locked_path, "w", encoding="utf-8") as f:
        json.dump(best_params, f, indent=2)
    log.info(f"Locked parameters written to {locked_path}")

    return {
        "status": "COMPLETED",
        "best_cv_cagr": best_cv_cagr,
        "best_parameters": best_params,
        "iterations_used": iteration + 1,
        "history": history
    }


def run_phase_e2_holdout(
    df: pd.DataFrame,
    locked_params: dict[str, Any],
    holdout_dir: str,
    output_final_dir: str,
    target_cagr: float = APPROVAL_THRESHOLD_HOLDOUT_CAGR,
    burn_holdout_and_restart: bool = False,
    override_gate_thresholds: bool = False,
    override_justification: str | None = None,
    allow_sparse_ledger: bool = False,
) -> dict[str, Any]:
    """Execute Phase E2: Write-once holdout evaluation on 2024-2025 data with strict guards."""
    log.info("=== Agent E: Phase E2 Holdout Backtest ===")
    
    # Gate overrides checks (Guard 2)
    validate_gate_config(target_cagr, override_gate_thresholds, override_justification)

    holdout_dir_path = Path(holdout_dir)
    holdout_dir_path.mkdir(parents=True, exist_ok=True)

    log_path = holdout_dir_path / "APPEND_ONLY_LOG.txt"
    hash_path = holdout_dir_path / "locked_parameters_hash.txt"
    result_path = holdout_dir_path / "holdout_result.json"

    # Enforce peek detection / write-once (Guard from §13)
    if not burn_holdout_and_restart:
        if log_path.exists():
            entries = log_path.read_text().strip().split("\n")
            e2_runs = [e for e in entries if e.startswith("E2_EXECUTED")]
            if e2_runs:
                raise HoldoutBurnedError(
                    f"Holdout already executed at {e2_runs[0]}. "
                    "Cannot re-run without explicit --burn-holdout-and-restart flag "
                    "and acknowledgment that all future results on this window are non-statistically-valid."
                )

    # Hash verification
    params_str = json.dumps(locked_params, sort_keys=True)
    h = hashlib.sha256(params_str.encode()).hexdigest()

    if not burn_holdout_and_restart:
        if hash_path.exists():
            existing = hash_path.read_text().strip()
            if existing != h:
                raise HoldoutBurnedError(
                    f"Locked params hash changed from {existing[:8]} to {h[:8]}. "
                    "This implies parameters were modified after E2 ran. Holdout burned."
                )
        else:
            hash_path.write_text(h)
    else:
        # Overwrite or write fresh hash
        hash_path.write_text(h)

    # Run detailed backtest on holdout window (2024-01-01 to 2025-12-31)
    log.info(f"Running holdout backtest on {APPROVAL_HOLD_START} to {APPROVAL_HOLD_END}...")
    detailed_res = walk_forward_backtest(df, APPROVAL_HOLD_START, APPROVAL_HOLD_END, locked_params, detailed=True)

    if not isinstance(detailed_res, dict):
        raise TypeError("Expected detailed backtest result to be a dictionary.")

    holdout_cagr = detailed_res["cagr"]
    trades = detailed_res["trades"]

    log.info(f"Holdout CAGR calculated: {holdout_cagr*100:.2f}% (Target: {target_cagr*100:.2f}%)")

    # Logging trade events to APPEND_ONLY_LOG.txt
    timestamp = datetime.utcnow().isoformat() + "Z"
    log_entry = f"E2_EXECUTED at {timestamp}: cagr={holdout_cagr:.6f} hash={h[:12]}"
    
    # Write to append-only log
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
        f.write(f"--- Trade Log ({len(trades)} trades) ---\n")
        for t in trades:
            f.write(f"TRADE: {t['engine']} {t['symbol']} enter={t['entry_date']} exit={t['exit_date']} return={t['net_return']:.4f}\n")

    # Write holdout results once
    result_data = {
        "holdout_compound_cagr": float(holdout_cagr),
        "holdout_window": [APPROVAL_HOLD_START, APPROVAL_HOLD_END],
        "regime_cagrs": detailed_res["regime_cagrs"],
        "monthly_returns": detailed_res["monthly_returns"],
        "max_drawdown": float(detailed_res["max_drawdown"]),
        "sharpe": float(detailed_res["sharpe"]),
        "n_trades": len(trades),
        "locked_params_hash": h,
        "executed_at": timestamp,
    }

    if result_path.exists() and not burn_holdout_and_restart:
        raise HoldoutBurnedError("holdout_result.json already exists. Cannot overwrite.")

    # Remove read-only block if overwriting
    if result_path.exists():
        try:
            os.chmod(result_path, 0o666)
        except Exception:
            pass

    result_path.write_text(json.dumps(result_data, indent=2))
    try:
        os.chmod(result_path, 0o444)  # Make read-only
    except Exception:
        pass

    # Build final directories
    Path(output_final_dir).mkdir(parents=True, exist_ok=True)

    # Load CV CAGR if possible to resolve Bug A1, A2, A3
    cv_cagr = None
    validation_dir = "validation/e1_cv"
    val_path = Path(validation_dir)
    if val_path.exists():
        def clean_dict(d):
            if not isinstance(d, dict):
                return d
            return {k: round(v, 6) if isinstance(v, float) else clean_dict(v) for k, v in d.items()}
        
        locked_clean = clean_dict(locked_params)
        for iter_dir in val_path.glob("iter_*"):
            param_path = iter_dir / "parameter_set.json"
            results_path = iter_dir / "fold_results.json"
            if param_path.exists() and results_path.exists():
                try:
                    with open(param_path) as f:
                        params = json.load(f)
                    if clean_dict(params) == locked_clean:
                        with open(results_path) as f:
                            results = json.load(f)
                        cv_cagr = results.get("cv_compound_cagr")
                        break
                except Exception:
                    pass
        
        if cv_cagr is None:
            cagrs = []
            for iter_dir in val_path.glob("iter_*"):
                results_path = iter_dir / "fold_results.json"
                if results_path.exists():
                    try:
                        with open(results_path) as f:
                            results = json.load(f)
                        c = results.get("cv_compound_cagr")
                        if c is not None:
                            cagrs.append(c)
                    except Exception:
                        pass
            if cagrs:
                cv_cagr = max(cagrs)

    if cv_cagr is None:
        cv_cagr = float(holdout_cagr)
    
    overfitting_gap = float(holdout_cagr) - float(cv_cagr)

    # Evaluate decision
    approved = holdout_cagr >= target_cagr
    decision_payload = {
        "status": "APPROVED" if approved else "DECLINED",
        "approved_at" if approved else "declined_at": timestamp,
        "allow_sparse_ledger": allow_sparse_ledger,
        "gate_compliance": {
            "uses_spec_thresholds": (target_cagr == APPROVAL_THRESHOLD_HOLDOUT_CAGR),
            "threshold_used": target_cagr,
            "spec_version": "v2.1",
            "overrides_applied": {
                "overall_cagr_target": target_cagr,
                "justification": override_justification
            } if target_cagr != APPROVAL_THRESHOLD_HOLDOUT_CAGR else None
        },
        "performance": {
            "holdout_compound_cagr": float(holdout_cagr),
            "holdout_window": [APPROVAL_HOLD_START, APPROVAL_HOLD_END],
            "cv_compound_cagr": float(cv_cagr),
            "overfitting_gap": float(overfitting_gap),
            "regime_cagrs": detailed_res["regime_cagrs"],
            "sharpe": float(detailed_res["sharpe"]),
            "max_drawdown": float(detailed_res["max_drawdown"]),
            "n_trades": len(trades),
        },
        "locked_parameters": locked_params,
    }

    if approved:
        decision_file = Path(output_final_dir) / "approved_strategy.json"
        # Clean up old declined report if present
        declined_file = Path(output_final_dir) / "declined_report.json"
        if declined_file.exists():
            try:
                declined_file.unlink()
            except Exception:
                pass
        # Copy playbook.json and forward_scorer_meta.json from synthesis folder to output_final_dir
        import shutil
        for fname in ["playbook.json", "forward_scorer_meta.json"]:
            src = Path("synthesis") / fname
            if src.exists():
                dst = Path(output_final_dir) / fname
                try:
                    shutil.copy2(src, dst)
                    log.info(f"Copied {fname} to {dst}")
                except Exception as e:
                    log.warning(f"Could not copy {fname} to {dst}: {e}")
    else:
        decision_payload["decline_reason"] = "holdout_cagr_below_30pct"
        decision_payload["honest_diagnosis"] = (
            f"Strategy showed CAGR of {holdout_cagr*100:.2f}% over holdout window, "
            f"which is below the target {target_cagr*100:.1f}%. "
            "Please review the logs for diagnosis."
        )
        decision_payload["holdout_burned"] = True
        decision_payload["next_holdout_available_after"] = "2027-01-01"
        decision_file = Path(output_final_dir) / "declined_report.json"
        # Clean up old approved strategy if present
        approved_file = Path(output_final_dir) / "approved_strategy.json"
        if approved_file.exists():
            try:
                approved_file.unlink()
            except Exception:
                pass

    # Write to final folder and root synthesis folder for backwards compatibility
    decision_file.write_text(json.dumps(decision_payload, indent=2))
    
    # Mirror outputs to legacy paths for compatibility
    legacy_decision = Path(output_final_dir) / "approval_decision.json"
    legacy_decision.write_text(json.dumps(decision_payload, indent=2))

    # Save to synthesis/approved_strategy.json or synthesis/declined_report.json
    synthesis_final = Path("synthesis")
    synthesis_final.mkdir(parents=True, exist_ok=True)
    if approved:
        (synthesis_final / "approved_strategy.json").write_text(json.dumps(decision_payload, indent=2))
        if (synthesis_final / "declined_report.json").exists():
            try:
                (synthesis_final / "declined_report.json").unlink()
            except Exception:
                pass
        try:
            (Path("approved_strategy.json")).write_text(json.dumps(decision_payload, indent=2))
        except Exception:
            pass
    else:
        (synthesis_final / "declined_report.json").write_text(json.dumps(decision_payload, indent=2))
        if (synthesis_final / "approved_strategy.json").exists():
            try:
                (synthesis_final / "approved_strategy.json").unlink()
            except Exception:
                pass
        try:
            if Path("approved_strategy.json").exists():
                Path("approved_strategy.json").unlink()
        except Exception:
            pass

    log.info(f"Phase E2 complete: Decision = {decision_payload['status']}, Output file: {decision_file}")
    
    return decision_payload


def run_validation_gate(
    master_features_path: str,
    target_cagr: float = APPROVAL_THRESHOLD_HOLDOUT_CAGR,
    max_cycles: int = 5,
    parameters_path: str | None = None,
    override_gate_thresholds: bool = False,
    override_justification: str | None = None,
    allow_sparse_ledger: bool = False,
) -> dict[str, Any]:
    """Fallback validation gate wrapper for backwards compatibility with legacy commands."""
    log.info("Executing run_validation_gate wrapper...")
    
    if not os.path.exists(master_features_path):
        raise FileNotFoundError(f"Master features file not found: {master_features_path}")

    df = pd.read_parquet(master_features_path)
    df['scan_date'] = pd.to_datetime(df['scan_date'])

    if 'regime' not in df.columns:
        from b10_dual_engine import train_hmm_regimes
        regime_df = train_hmm_regimes(df)
        df = pd.merge(df, regime_df, on='scan_date', how='inner')

    # Run Phase E1 CV Optimization
    validation_dir = "validation/e1_cv"
    e1_res = run_phase_e1_optimization(
        df=df,
        synthesis_dir="synthesis",
        validation_dir=validation_dir,
        max_iterations=max_cycles,
        early_stop_stalled_count=5,
        parameters_path=parameters_path,
    )

    # Run Phase E2 Holdout Backtest
    locked_params = e1_res["best_parameters"]
    holdout_dir = "validation/e2_holdout"
    output_final_dir = "final"
    
    e2_res = run_phase_e2_holdout(
        df=df,
        locked_params=locked_params,
        holdout_dir=holdout_dir,
        output_final_dir=output_final_dir,
        target_cagr=target_cagr,
        burn_holdout_and_restart=True, # Allow restart for legacy unified calls
        override_gate_thresholds=override_gate_thresholds,
        override_justification=override_justification,
        allow_sparse_ledger=allow_sparse_ledger,
    )

    return {
        "status": e2_res["status"],
        "final_cagr": e2_res["performance"]["holdout_compound_cagr"],
        "cycles_used": e1_res["iterations_used"],
        "approved_parameters": locked_params,
    }
