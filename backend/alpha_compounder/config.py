"""
config.py — Grid cells, priors, budget defaults, and pipeline constants.

All tunable parameters in one place. Priors are versioned; changing them
produces a new attributions directory (never overwrite).
"""

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# GCS paths
# ---------------------------------------------------------------------------

GCS_BUCKET = "screener-signals-carbonbridge"
GCS_PREFIX = "alpha-compounder/v1"

# ---------------------------------------------------------------------------
# Grid cells (§2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridCell:
    label: str
    mag_low: float       # percent, e.g. 100 = +100%
    mag_high: float      # percent, float('inf') for unbounded
    dur_low_days: int
    dur_high_days: int

GRID_CELLS = [
    GridCell("momentum_short",    100, 200,   60,  250),
    GridCell("momentum_durable",  100, 200,  250,  730),
    GridCell("breakout_short",    200, 400,   60,  250),
    GridCell("compounder_mid",    200, 400,  250,  730),
    GridCell("compounder_long",   400, 800,  250,  730),
    GridCell("monster",           800, float("inf"), 250, 1825),
]

# ---------------------------------------------------------------------------
# Quality filters (§4)
# ---------------------------------------------------------------------------

QUALITY_FILTERS = {
    "max_drawdown_during_run":  0.35,    # ≤ 35%
    "persistence_threshold":    0.70,    # terminal ≥ 70% of peak
    "persistence_days":         90,      # for ≥ 90 days after t_end
    "min_mcap_usd":             300_000_000,
    "min_adv_20d_usd":          5_000_000,
    "min_price":                5.0,
    "min_run_separation_days":  180,
    "min_history_days":         200,     # symbol must have ≥200 days in window
}

# ---------------------------------------------------------------------------
# Archetype taxonomy (§4 — optional LLM labeling)
# ---------------------------------------------------------------------------

ARCHETYPE_TAXONOMY = [
    "post_covid_recovery", "ai_re_rate", "glp1_breakout",
    "rate_cut_beneficiary", "earnings_breakout", "sop_re_rate",
    "product_cycle", "turnaround", "macro_tailwind",
    "secular_growth", "other_propose",
]

# ---------------------------------------------------------------------------
# Priors (§8) — hard divergence
# ---------------------------------------------------------------------------

PRIOR_B = {
    "prior_name": "fundamental_only",
    "version": "1.0",
    "allowed_families": [
        "fundamental_delta", "quality_regime_change",
        "valuation_reset", "earnings_momentum",
    ],
    "denied_families": [
        "analyst_dynamics", "smart_money",
        "narrative_sentiment", "macro_market_context",
        "options_derivatives",
    ],
    "initial_family_weights": {
        "fundamental_delta": 0.30,
        "quality_regime_change": 0.25,
        "earnings_momentum": 0.25,
        "valuation_reset": 0.20,
    },
    "initial_factor_priors": {
        "revenue_yoy_acceleration": 0.10,
        "eps_yoy_acceleration": 0.10,
        "gross_margin_delta_12m": 0.08,
        "operating_margin_delta_12m": 0.07,
        "fcf_cagr_3yr": 0.07,
        "eps_beats_last_4q": 0.07,
        "roic_trajectory": 0.06,
        "pe_at_t_start": 0.05,
        "piotroski_delta_2yr": 0.05,
    },
    "action_mix_bias": {
        "CRITIQUE": 0.20, "REFINE": 0.30,
        "PROPOSE": 0.30, "FALSIFY": 0.20,
    },
    "narrative_lens": (
        "Only the income statement, balance sheet, cash flow, and resulting "
        "valuation matter. If those don't explain it, attribution is unresolved "
        "— better to say so than to invent a story. Re-rates without underlying "
        "business improvement are confounded with cohort/regime dynamics and "
        "should be downweighted."
    ),
}

PRIOR_C = {
    "prior_name": "flow_microstructure_only",
    "version": "1.0",
    "allowed_families": [
        "analyst_dynamics", "smart_money",
        "narrative_sentiment", "macro_market_context",
        "options_derivatives",
    ],
    "denied_families": [
        "fundamental_delta", "quality_regime_change",
        "valuation_reset", "earnings_momentum",
    ],
    "initial_family_weights": {
        "analyst_dynamics": 0.25,
        "smart_money": 0.22,
        "narrative_sentiment": 0.20,
        "macro_market_context": 0.18,
        "options_derivatives": 0.15,
    },
    "initial_factor_priors": {
        "pt_revision_velocity_60d": 0.10,
        "upgrade_cluster_density_90d": 0.08,
        "eps_estimate_revision_breadth_60d": 0.07,
        "news_catalyst_keyword_score": 0.07,
        "inst_holder_count_qoq": 0.06,
        "insider_net_buy_ratio_6m": 0.06,
        "transcript_sentiment_delta_2q": 0.05,
        "sector_relative_strength_at_start": 0.05,
        "volume_to_oi_ratio": 0.05,
    },
    "action_mix_bias": {
        "CRITIQUE": 0.20, "REFINE": 0.25,
        "PROPOSE": 0.35, "FALSIFY": 0.20,
    },
    "narrative_lens": (
        "Stocks move because flows change. Fundamentals justify after the fact, "
        "but the discontinuity is in positioning, attention, and analyst "
        "revisions. If flow signal doesn't explain it, the run was either "
        "pure-fundamental (rare for episodic runs) or unattributable."
    ),
}

# ---------------------------------------------------------------------------
# Budget defaults (§11)
# ---------------------------------------------------------------------------

@dataclass
class BudgetConfig:
    max_tokens_per_run: int = 25_000
    max_seconds_per_run: int = 480       # 8 min
    max_rounds_per_run: int = 30
    max_concurrent_runs: int = 20
    max_pipeline_cost_usd: Optional[float] = 5.0    # USD cost cap per pipeline run

DEFAULT_BUDGET = BudgetConfig()

# ---------------------------------------------------------------------------
# LLM config
# ---------------------------------------------------------------------------

LLM_MODEL_ATTRIBUTION = "gemini-2.5-flash"  # high-quality dialectic
LLM_MODEL_SWEEP = "gemini-2.5-flash"              # cost-bounded sweeps
LLM_TEMPERATURE = 0                               # reproducibility

# ---------------------------------------------------------------------------
# Default time window
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_START = "2018-01-01"
DEFAULT_WINDOW_END = "2025-06-30"

# ---------------------------------------------------------------------------
# Factor classifications (§6)
# ---------------------------------------------------------------------------

FACTOR_CLASSIFICATIONS = {
    "idiosyncratic_driver":  {"weight_ceiling": 1.0},
    "cohort_beta":           {"weight_ceiling": 0.05},
    "enabling_condition":    {"weight_ceiling": 0.20},
    "coincident_artifact":   {"weight_ceiling": 0.05},
    "confounded":            {"weight_ceiling": 0.15},
}

# ---------------------------------------------------------------------------
# Convergence thresholds (§5)
# ---------------------------------------------------------------------------

CONVERGENCE = {
    "stability_tau_threshold": 0.9,
    "stability_window": 8,
    "saturation_window": 15,
    "saturation_max_weight_delta": 0.05,
    "forced_tau_threshold": 0.5,
    "consecutive_pass_limit": 3,
}
