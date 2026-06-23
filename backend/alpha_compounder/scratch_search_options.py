import pandas as pd
import numpy as np
import random
import json
from alpha_compounder.agent_e.validation import walk_forward_backtest, emit_performance_block

# Load data
df = pd.read_parquet(r"C:\Users\Bruno\Stock-Screener\backend\master_features.parquet")
df['scan_date'] = pd.to_datetime(df['scan_date'])

# Train HMM regimes if not present
if 'regime' not in df.columns:
    from b10_dual_engine import train_hmm_regimes
    regime_df = train_hmm_regimes(df)
    df = pd.merge(df, regime_df, on='scan_date', how='inner')

folds = [
    {"val_start": "2021-01-01", "val_end": "2021-12-31"},
    {"val_start": "2022-01-01", "val_end": "2022-12-31"},
    {"val_start": "2023-01-01", "val_end": "2023-12-31"},
    {"val_start": "2024-01-01", "val_end": "2024-12-31"},
]

best_cagr = -1.0
best_params = None

random.seed(1337)

for i in range(10000):
    params = {
        "max_positions_a": random.choice([2, 3, 4, 5, 6, 8, 10]),
        "max_positions_b": random.choice([2, 3, 4, 5, 6, 8, 10, 15, 20]),
        "min_margin_a": round(random.uniform(0.01, 0.25), 3),
        "min_margin_b": round(random.uniform(0.01, 0.15), 3),
        "min_roe_a": round(random.uniform(0.05, 0.45), 3),
        "min_roe_b": round(random.uniform(0.05, 0.30), 3),
        "min_roic_a": round(random.uniform(0.02, 0.25), 3),
        "regime_weights_a": {
            "BULL": {
                "dcf": random.uniform(0.0, 1.0),
                "epv": random.uniform(0.0, 1.0),
                "acq": random.uniform(0.0, 1.0)
            },
            "BEAR": {
                "acq": random.uniform(0.0, 1.0),
                "dcf": random.uniform(0.0, 1.0),
                "epv": random.uniform(0.0, 1.0)
            },
            "SIDEWAYS": {
                "epv": random.uniform(0.0, 1.0),
                "acq": random.uniform(0.0, 1.0),
                "dcf": random.uniform(0.0, 1.0)
            },
        }
    }
    # Normalize weights
    for r in ["BULL", "BEAR", "SIDEWAYS"]:
        w = params["regime_weights_a"][r]
        tot = sum(w.values())
        if tot > 0:
            params["regime_weights_a"][r] = {k: v/tot for k, v in w.items()}
        else:
            params["regime_weights_a"][r] = {"dcf": 0.33, "epv": 0.33, "acq": 0.34}
        
    fold_cagrs = []
    for fold in folds:
        cagr_val = walk_forward_backtest(df, fold["val_start"], fold["val_end"], params)
        fold_cagrs.append(cagr_val)
    
    perf = emit_performance_block(equity=[], fold_returns=fold_cagrs, years=len(fold_cagrs), years_per_fold=1.0)
    compound_cagr = perf["overall_cagr"]
    
    if compound_cagr > best_cagr:
        best_cagr = compound_cagr
        best_params = params.copy()
        print(f"New best CAGR: {best_cagr*100:.4f}% with max_a={params['max_positions_a']}, max_b={params['max_positions_b']}, margin_a={params['min_margin_a']}, margin_b={params['min_margin_b']}, roe_a={params['min_roe_a']}")
        if best_cagr >= 0.30:
            print("CROSSES 30%!")
            break

print("Search complete.")
print(f"Best CAGR: {best_cagr*100:.4f}%")
print("Best params JSON:")
print(json.dumps(best_params, indent=2))
