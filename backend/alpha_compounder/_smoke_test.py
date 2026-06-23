"""Quick smoke test for the alpha_compounder package."""
from alpha_compounder.config import GRID_CELLS, PRIOR_B, PRIOR_C, DEFAULT_BUDGET
from alpha_compounder.schemas import RunRecord, ActionMessage, Attribution, LoopState
from alpha_compounder.factor_catalog import ALL_FACTORS, allowed_for_agent
from alpha_compounder.factor_service import FactorService
from alpha_compounder.orchestrator.loop import init_state, check_convergence
from alpha_compounder.agents.base_agent import AttributionAgent
from alpha_compounder.gcs_io import gcs_write_json, local_write_json
from macro_regime import classify_pit

print("ALL IMPORTS OK")
print(f"  {len(GRID_CELLS)} grid cells, {len(ALL_FACTORS)} factors")
b_count = sum(1 for f in ALL_FACTORS if allowed_for_agent("B", f.factor_id))
c_count = sum(1 for f in ALL_FACTORS if allowed_for_agent("C", f.factor_id))
print(f"  B can access: {b_count} factors")
print(f"  C can access: {c_count} factors")
print(f"  Budget: {DEFAULT_BUDGET.max_tokens_per_run} tokens, {DEFAULT_BUDGET.max_rounds_per_run} rounds")

# Test schema validation
from datetime import date
run = RunRecord(
    symbol="NVDA", exchange="NASDAQ",
    t_start=date(2023, 1, 6), t_end=date(2024, 6, 20),
    duration_days=530, magnitude_pct=480.3,
    peak_price=140.76, trough_price=14.30, terminal_price=130.42,
    mdd_during_run=-0.18, persistence_pct=0.93,
    grid_cell_label="compounder_long",
)
print(f"  RunRecord validated: {run.symbol} +{run.magnitude_pct}%")

# Test Trajectory Shape logic
from alpha_compounder.agent_a.discovery import _build_run_record
from alpha_compounder.config import GridCell

meta = {"exchange": "NASDAQ", "sector": "Tech", "industry": "Semis", "country": "US"}
cell = GridCell(label="test_cell", mag_low=0.0, mag_high=100.0, dur_low_days=0, dur_high_days=100)
candidate = {"t_start": "2023-01-01", "t_end": "2023-01-06", "peak_price": 20.0, "trough_price": 10.0, "magnitude_pct": 100.0, "duration_days": 5}

# 1. Linear
linear_prices = [
    {"date": f"2023-01-0{i+1}", "adjClose": 10.0 + 2.0 * i} for i in range(6)
]
linear_rec = _build_run_record("TEST", candidate, cell, meta, linear_prices)
print(f"  Linear RunRecord shape: {linear_rec['trajectory_shape']}")

# 2. Front-loaded
front_prices = [
    {"date": "2023-01-01", "adjClose": 10.0},
    {"date": "2023-01-02", "adjClose": 17.0},
    {"date": "2023-01-03", "adjClose": 19.0},
    {"date": "2023-01-04", "adjClose": 19.5},
    {"date": "2023-01-05", "adjClose": 19.8},
    {"date": "2023-01-06", "adjClose": 20.0},
]
front_rec = _build_run_record("TEST", candidate, cell, meta, front_prices)
print(f"  Front-loaded RunRecord shape: {front_rec['trajectory_shape']}")

# 3. Back-loaded
back_prices = [
    {"date": "2023-01-01", "adjClose": 10.0},
    {"date": "2023-01-02", "adjClose": 10.2},
    {"date": "2023-01-03", "adjClose": 10.5},
    {"date": "2023-01-04", "adjClose": 11.0},
    {"date": "2023-01-05", "adjClose": 13.0},
    {"date": "2023-01-06", "adjClose": 20.0},
]
back_rec = _build_run_record("TEST", candidate, cell, meta, back_prices)
print(f"  Back-loaded RunRecord shape: {back_rec['trajectory_shape']}")

# Test Kendall tau
from alpha_compounder.utils import kendall_tau, mean_kendall_tau
tau = kendall_tau(["a","b","c","d","e"], ["a","b","c","d","e"])
print(f"  Kendall tau (identical): {tau}")
tau2 = kendall_tau(["a","b","c","d","e"], ["e","d","c","b","a"])
print(f"  Kendall tau (reversed): {tau2}")

print("\nSMOKE TEST PASSED")
