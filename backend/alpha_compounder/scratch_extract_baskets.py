import pandas as pd
import numpy as np
import json

# Load data
df = pd.read_parquet(r"C:\Users\Bruno\Stock-Screener\backend\master_features.parquet")
df['scan_date'] = pd.to_datetime(df['scan_date'])

# Train HMM regimes if not present
if 'regime' not in df.columns:
    from b10_dual_engine import train_hmm_regimes
    regime_df = train_hmm_regimes(df)
    df = pd.merge(df, regime_df, on='scan_date', how='inner')

params = {
  "max_positions_a": 8,
  "max_positions_b": 2,
  "min_margin_a": 0.033,
  "min_margin_b": 0.014,
  "min_roe_a": 0.181,
  "min_roe_b": 0.252,
  "min_roic_a": 0.071,
  "regime_weights_a": {
    "BULL": {
      "dcf": 0.3456380779093661,
      "epv": 0.21422169910364441,
      "acq": 0.44014022298698946
    },
    "BEAR": {
      "acq": 0.36254871115506165,
      "dcf": 0.28257417287411846,
      "epv": 0.35487711597081983
    },
    "SIDEWAYS": {
      "epv": 0.0747241915305719,
      "acq": 0.4841547032699384,
      "dcf": 0.44112110519948966
    }
  }
}

folds = [
    {"year": 2021, "start": "2021-01-01", "end": "2021-12-31"},
    {"year": 2022, "start": "2022-01-01", "end": "2022-12-31"},
    {"year": 2023, "start": "2023-01-01", "end": "2023-12-31"},
    {"year": 2024, "start": "2024-01-01", "end": "2024-12-31"},
]

def run_backtest_collect_trades(df, start_date, end_date, params):
    period_df = df[(df['scan_date'] >= start_date) & (df['scan_date'] <= end_date)].copy()
    if period_df.empty:
        return []

    unique_dates = sorted(period_df['scan_date'].unique())
    if len(unique_dates) < 4:
        return []

    # Initialize portfolios
    capital_a = 50000.0
    capital_b = 50000.0
    active_a = {}
    active_b = {}
    
    max_pos_a = params.get("max_positions_a", 15)
    max_pos_b = params.get("max_positions_b", 25)
    cost_bps = params.get("transaction_cost_bps", 15)
    
    margin_a = params.get("min_margin_a", 0.10)
    margin_b = params.get("min_margin_b", 0.05)
    roe_a = params.get("min_roe_a", 0.15)
    roe_b = params.get("min_roe_b", 0.10)
    roic_a = params.get("min_roic_a", 0.10)
    
    last_rebalance_month = None
    trades = [] # list of dicts

    for current_date in unique_dates:
        today_data = period_df[period_df['scan_date'] == current_date].copy()
        if today_data.empty:
            continue
            
        current_regime = today_data['regime'].iloc[0] if 'regime' in today_data.columns else 'BULL'
        today_data.set_index('symbol', inplace=True)
        today_data = today_data[~today_data.index.duplicated(keep='first')]
        
        # Stop-loss
        stop_loss = -0.20 if current_regime == "BEAR" else -0.15
        
        # Exit A
        exit_a = []
        for sym, t in active_a.items():
            if sym in today_data.index:
                row = today_data.loc[sym]
                pnl = (row['price'] - t['entry_price']) / t['entry_price']
                if pnl < stop_loss or row.get('iv15_discount', 999.0) > 1.20 or row.get('net_margin', 1.0) < 0.03:
                    exit_a.append((sym, row['price'], f"SL/Rule (PnL: {pnl*100:.1f}%)"))
            else:
                exit_a.append((sym, t['entry_price'] * 0.5, "Missing Symbol data (Exit @ 0.5x)"))
                 
        for sym, exit_price, reason in exit_a:
            t = active_a.pop(sym)
            net_return = ((exit_price - t['entry_price']) / t['entry_price']) - (2 * (cost_bps / 10000))
            capital_a += t['capital'] * (1 + net_return)
            trades.append({
                "engine": "A",
                "symbol": sym,
                "entry_date": str(t['entry_date'].date()) if isinstance(t['entry_date'], pd.Timestamp) else str(t['entry_date']),
                "exit_date": str(current_date.date()) if isinstance(current_date, pd.Timestamp) else str(current_date),
                "entry_price": t['entry_price'],
                "exit_price": exit_price,
                "gain_pct": net_return * 100,
                "status": f"Exited: {reason}"
            })
            
        # Exit B
        exit_b = []
        for sym, t in active_b.items():
            if sym in today_data.index:
                row = today_data.loc[sym]
                pnl = (row['price'] - t['entry_price']) / t['entry_price']
                if pnl < stop_loss or row.get('iv15_discount', 999.0) > 1.20 or row.get('net_margin', 1.0) < 0.03:
                    exit_b.append((sym, row['price'], f"SL/Rule (PnL: {pnl*100:.1f}%)"))
            else:
                exit_b.append((sym, t['entry_price'] * 0.5, "Missing Symbol data (Exit @ 0.5x)"))
                
        for sym, exit_price, reason in exit_b:
            t = active_b.pop(sym)
            net_return = ((exit_price - t['entry_price']) / t['entry_price']) - (2 * (cost_bps / 10000))
            capital_b += t['capital'] * (1 + net_return)
            trades.append({
                "engine": "B",
                "symbol": sym,
                "entry_date": str(t['entry_date'].date()) if isinstance(t['entry_date'], pd.Timestamp) else str(t['entry_date']),
                "exit_date": str(current_date.date()) if isinstance(current_date, pd.Timestamp) else str(current_date),
                "entry_price": t['entry_price'],
                "exit_price": exit_price,
                "gain_pct": net_return * 100,
                "status": f"Exited: {reason}"
            })
            
        # Monthly Rebalance
        current_month = pd.to_datetime(current_date).month
        if last_rebalance_month != current_month:
            last_rebalance_month = current_month
            
            # Engine A Candidates
            mask_a = (
                (today_data.get('net_margin', 0) >= margin_a) & 
                (today_data.get('eps_growth_3y', 0) > 0) &
                (today_data.get('roe', 0) > roe_a) &             
                (today_data.get('roic', 0) > roic_a) &            
                (today_data.get('acquirers_multiple', 999) > 0) & 
                (today_data.get('iv15_discount', 999) > 0) &      
                (today_data.get('epv_to_ev', 0) > 0)
            )
            cand_a = today_data[mask_a].copy()
            if not cand_a.empty:
                w = params.get("regime_weights_a", {}).get(current_regime, {"dcf": 0.60, "epv": 0.40, "acq": 0.00})
                s_dcf = cand_a["iv15_discount"].rank(pct=True, ascending=False)
                s_acq = cand_a["acquirers_multiple"].rank(pct=True, ascending=False)
                s_epv = cand_a["epv_to_ev"].rank(pct=True, ascending=True)
                cand_a['score'] = s_dcf * w.get("dcf", 0.0) + s_acq * w.get("acq", 0.0) + s_epv * w.get("epv", 0.0)
                cand_a = cand_a.sort_values('score', ascending=False)
                
            # Engine B Candidates
            mask_b = (
                (today_data.get('net_margin', 0) >= margin_b) & 
                (today_data.get('roe', 0) > roe_b) &             
                (today_data.get('eps_growth_3y', 0) > -0.50) &            
                (today_data.get('acquirers_multiple', 999) > 0) & 
                (today_data.get('iv15_discount', 999) > 0) &      
                (today_data.get('epv_to_ev', 0) > 0) &
                (today_data['price'] > 0)
            )
            cand_b = today_data[mask_b].copy()
            if not cand_b.empty:
                am_rank = cand_b["acquirers_multiple"].rank(pct=True, ascending=True)
                epv_rank = cand_b["epv_to_ev"].rank(pct=True, ascending=True)
                iv15 = cand_b["iv15_discount"].clip(lower=0.01)
                eps_g = cand_b["eps_growth_3y"].clip(lower=-0.5, upper=2.0)
                nm = cand_b["net_margin"].clip(lower=0.01, upper=0.5)
                
                if current_regime == "BULL":
                    raw_score = (1 / iv15) * (1 + eps_g) * nm
                elif current_regime == "BEAR":
                    roe_val = cand_b["roe"].clip(lower=0.01, upper=1.0)
                    raw_score = am_rank * (1 + roe_val) * (1 + epv_rank)
                else:
                    roe_val = cand_b["roe"].clip(lower=0.01, upper=1.0)
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

    # At the end of the period, record all remaining active positions as "Held"
    for sym, t in active_a.items():
        exit_price = today_data.loc[sym, 'price'] if sym in today_data.index else t['entry_price']
        net_return = ((exit_price - t['entry_price']) / t['entry_price'])
        trades.append({
            "engine": "A",
            "symbol": sym,
            "entry_date": str(t['entry_date'].date()) if isinstance(t['entry_date'], pd.Timestamp) else str(t['entry_date']),
            "exit_date": str(unique_dates[-1].date()) if isinstance(unique_dates[-1], pd.Timestamp) else str(unique_dates[-1]),
            "entry_price": t['entry_price'],
            "exit_price": exit_price,
            "gain_pct": net_return * 100,
            "status": "Held (Mark-to-Market)"
        })
        
    for sym, t in active_b.items():
        exit_price = today_data.loc[sym, 'price'] if sym in today_data.index else t['entry_price']
        net_return = ((exit_price - t['entry_price']) / t['entry_price'])
        trades.append({
            "engine": "B",
            "symbol": sym,
            "entry_date": str(t['entry_date'].date()) if isinstance(t['entry_date'], pd.Timestamp) else str(t['entry_date']),
            "exit_date": str(unique_dates[-1].date()) if isinstance(unique_dates[-1], pd.Timestamp) else str(unique_dates[-1]),
            "entry_price": t['entry_price'],
            "exit_price": exit_price,
            "gain_pct": net_return * 100,
            "status": "Held (Mark-to-Market)"
        })
        
    return trades

print("# BACKTEST TRADES AND SCENARIOS BY FOLD/YEAR")
for fold in folds:
    print(f"\n## Fold: {fold['year']} ({fold['start']} to {fold['end']})")
    trades = run_backtest_collect_trades(df, fold["start"], fold["end"], params)
    
    # Engine A Trades
    print(f"\n### Engine A (Quality Growth Portfolio) Baskets")
    t_a = [t for t in trades if t["engine"] == "A"]
    if not t_a:
        print("No Engine A trades recorded.")
    else:
        print("| Symbol | Entry Date | Exit Date | Entry Price | Exit Price | Gain % | Status |")
        print("|---|---|---|---|---|---|---|")
        for row in t_a:
            print(f"| {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {row['entry_price']:.2f} | {row['exit_price']:.2f} | {row['gain_pct']:.2f}% | {row['status']} |")
        
    # Engine B Trades
    print(f"\n### Engine B (Deep Value / GARP Portfolio) Baskets")
    t_b = [t for t in trades if t["engine"] == "B"]
    if not t_b:
        print("No Engine B trades recorded.")
    else:
        print("| Symbol | Entry Date | Exit Date | Entry Price | Exit Price | Gain % | Status |")
        print("|---|---|---|---|---|---|---|")
        for row in t_b:
            print(f"| {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {row['entry_price']:.2f} | {row['exit_price']:.2f} | {row['gain_pct']:.2f}% | {row['status']} |")

