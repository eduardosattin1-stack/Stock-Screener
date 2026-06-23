"""
schemas.py — Pydantic models for all shared data structures (§10).

Every schema enforces the contracts from the spec. Validation rules
are encoded as Pydantic validators so the orchestrator rejects
malformed data at the boundary.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    CRITIQUE = "CRITIQUE"
    REFINE = "REFINE"
    PROPOSE = "PROPOSE"
    FALSIFY = "FALSIFY"
    PASS = "PASS"


class ConvergenceStatus(str, Enum):
    CONTINUE = "CONTINUE"
    CONVERGED_STABILITY = "CONVERGED_STABILITY"
    CONVERGED_SATURATION = "CONVERGED_SATURATION"
    CONVERGED_FORCED = "CONVERGED_FORCED"
    CONVERGED_BUDGET = "CONVERGED_BUDGET"
    AMBIGUOUS_AT_CAP = "AMBIGUOUS_AT_CAP"
    MALFORMED = "MALFORMED"
    IN_PROGRESS = "IN_PROGRESS"


class FactorClassification(str, Enum):
    IDIOSYNCRATIC_DRIVER = "idiosyncratic_driver"
    COHORT_BETA = "cohort_beta"
    ENABLING_CONDITION = "enabling_condition"
    COINCIDENT_ARTIFACT = "coincident_artifact"
    CONFOUNDED = "confounded"


class RunType(str, Enum):
    FUNDAMENTAL_LED = "fundamental_led"
    FLOW_LED = "flow_led"
    BALANCED = "balanced"
    UNATTRIBUTABLE = "unattributable"


class TimeSlice(str, Enum):
    BASELINE = "baseline"
    PRIMING = "priming"
    CONCURRENT = "concurrent"


# ---------------------------------------------------------------------------
# Run record (Agent A output)
# ---------------------------------------------------------------------------

class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    exchange: str
    t_start: date
    t_end: date
    duration_days: int
    magnitude_pct: float
    peak_price: float
    trough_price: float
    terminal_price: float
    mdd_during_run: float          # max drawdown as negative fraction, e.g. -0.18
    persistence_pct: float         # terminal / peak ratio
    grid_cell_label: str
    sector_t_start: str = ""
    industry_t_start: str = ""
    country: str = ""
    mcap_t_start_usd: float = 0
    adv_20d_t_start_usd: float = 0
    regime_t_start: str = ""
    regime_t_end: str = ""
    regime_transitions: int = 0
    year_t_start: int = 0
    year_t_end: int = 0
    archetype_label: str = ""
    trajectory_shape: str = ""
    sector_source: str = "current"   # "historical" or "current"
    extraction_version: str = "agent_a_v1.0"

    @field_validator("magnitude_pct")
    @classmethod
    def magnitude_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("magnitude_pct must be positive")
        return v

    @field_validator("duration_days")
    @classmethod
    def duration_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("duration_days must be positive")
        return v


# ---------------------------------------------------------------------------
# Factor result (Factor Service output)
# ---------------------------------------------------------------------------

class FactorResult(BaseModel):
    factor_id: str
    run_id: str
    time_slice: TimeSlice
    params: dict[str, Any] = Field(default_factory=dict)
    raw_value: float
    sector_zscore: float = 0.0
    regime_zscore: float = 0.0
    confidence: float = 1.0        # data completeness 0-1
    evidence_url: str = ""
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    pit_filing_dates_used: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Falsification test (embedded in action messages)
# ---------------------------------------------------------------------------

class FalsificationTest(BaseModel):
    type: str = "factor_request"
    factor_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    time_slice: TimeSlice = TimeSlice.PRIMING
    evaluation: dict[str, Any] = Field(default_factory=dict)
    # evaluation must contain: metric, threshold, direction

    @field_validator("evaluation")
    @classmethod
    def evaluation_complete(cls, v: dict) -> dict:
        required = {"metric", "threshold", "direction"}
        if v and not required.issubset(v.keys()):
            raise ValueError(f"evaluation must contain {required}, got {set(v.keys())}")
        return v


# ---------------------------------------------------------------------------
# Predicted state change
# ---------------------------------------------------------------------------

class PredictedStateChange(BaseModel):
    factor_id: str
    weight_delta: float = 0.0
    new_classification: Optional[str] = None
    redistribution: Optional[str] = "uniform_to_top5"


# ---------------------------------------------------------------------------
# Action message (per-round agent output)
# ---------------------------------------------------------------------------

class ActionMessage(BaseModel):
    round: int
    agent: Literal["B", "C"]
    action: ActionType
    target_factor_id: Optional[str] = None
    rationale: str = ""
    family: Optional[str] = None     # required for PROPOSE
    initial_weight: Optional[float] = None   # required for PROPOSE
    factor_request: Optional[dict[str, Any]] = None   # required for PROPOSE
    falsification_test: Optional[FalsificationTest] = None
    expected_outcome: Optional[str] = None
    predicted_state_change: Optional[PredictedStateChange] = None
    new_classification: Optional[str] = None   # for REFINE
    new_evidence: Optional[str] = None         # for REFINE or revived PROPOSE
    reason: Optional[str] = None               # for PASS
    tokens_used: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ActionMessage":
        a = self.action
        if a == ActionType.CRITIQUE:
            if not self.target_factor_id:
                raise ValueError("CRITIQUE requires target_factor_id")
            if not self.predicted_state_change:
                raise ValueError("CRITIQUE requires predicted_state_change")
        elif a == ActionType.REFINE:
            if not self.target_factor_id:
                raise ValueError("REFINE requires target_factor_id")
            if not self.new_classification and not self.new_evidence:
                raise ValueError("REFINE requires new_classification or new_evidence")
        elif a == ActionType.PROPOSE:
            if not self.target_factor_id:
                raise ValueError("PROPOSE requires target_factor_id")
            if not self.family:
                raise ValueError("PROPOSE requires family")
        elif a == ActionType.FALSIFY:
            if not self.target_factor_id:
                raise ValueError("FALSIFY requires target_factor_id")
            if not self.falsification_test:
                raise ValueError("FALSIFY requires falsification_test")
            if not self.expected_outcome:
                raise ValueError("FALSIFY requires expected_outcome")
        elif a == ActionType.PASS:
            if not self.reason:
                raise ValueError("PASS requires reason")
        return self

    @field_validator("rationale")
    @classmethod
    def rationale_not_boilerplate(cls, v: str) -> str:
        if v and len(v) < 40:
            raise ValueError("rationale must be >= 40 characters")
        return v


# ---------------------------------------------------------------------------
# Factor state (within live loop)
# ---------------------------------------------------------------------------

class FactorState(BaseModel):
    weight: float = 0.0
    classification: FactorClassification = FactorClassification.IDIOSYNCRATIC_DRIVER
    family: str = ""
    introduced_by: Literal["B", "C"] = "B"
    introduced_at_round: int = 0
    last_modified_round: int = 0
    evidence_url: str = ""


# ---------------------------------------------------------------------------
# Rejected factor log entry
# ---------------------------------------------------------------------------

class RejectedFactor(BaseModel):
    factor_id: str
    rejected_at_round: int
    rejected_by: Literal["B", "C"]
    reason: str
    can_be_revived: bool = False


# ---------------------------------------------------------------------------
# Family quota status
# ---------------------------------------------------------------------------

class FamilyQuotaStatus(BaseModel):
    touched_families: list[str] = Field(default_factory=list)
    untouched_families: list[str] = Field(default_factory=list)
    rounds_until_quota: int = 10


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

class BudgetStatus(BaseModel):
    tokens_used: int = 0
    tokens_remaining: int = 60_000
    wall_clock_seconds: float = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Convergence history entry
# ---------------------------------------------------------------------------

class ConvergenceEntry(BaseModel):
    round: int
    kendall_tau_last8: float = 0.0


# ---------------------------------------------------------------------------
# Loop state (live during attribution)
# ---------------------------------------------------------------------------

class LoopState(BaseModel):
    run_id: str
    pipeline_run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_count: int = 0
    status: ConvergenceStatus = ConvergenceStatus.IN_PROGRESS
    active_agent_next: Literal["B", "C"] = "B"
    prior_b: str = "fundamental_only_v1.0"
    prior_c: str = "flow_microstructure_only_v1.0"
    factors: dict[str, FactorState] = Field(default_factory=dict)
    rejected_log: list[RejectedFactor] = Field(default_factory=list)
    family_quota_status: dict[str, FamilyQuotaStatus] = Field(default_factory=dict)
    convergence_history: list[ConvergenceEntry] = Field(default_factory=list)
    budget: BudgetStatus = Field(default_factory=BudgetStatus)
    consecutive_invalid: dict[str, int] = Field(
        default_factory=lambda: {"B": 0, "C": 0}
    )
    consecutive_passes: dict[str, int] = Field(
        default_factory=lambda: {"B": 0, "C": 0}
    )
    rounds: list[dict] = Field(default_factory=list)   # serialized ActionMessages


# ---------------------------------------------------------------------------
# Agent final statement
# ---------------------------------------------------------------------------

class AgentFinalStatement(BaseModel):
    primary_driver: str
    primary_driver_weight: float
    supporting_drivers: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.5
    narrative: str = ""
    disagreement_with_opposite: str = ""


# ---------------------------------------------------------------------------
# Final attribution (converged output)
# ---------------------------------------------------------------------------

class Attribution(BaseModel):
    run_id: str
    pipeline_run_id: str
    status: ConvergenceStatus
    rounds_used: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    prior_b: str = "fundamental_only_v1.0"
    prior_c: str = "flow_microstructure_only_v1.0"
    final_weights: dict[str, float] = Field(default_factory=dict)
    final_classifications: dict[str, str] = Field(default_factory=dict)
    rejected_factors: list[dict[str, str]] = Field(default_factory=list)
    fundamental_weight_total: float = 0.0
    flow_weight_total: float = 0.0
    run_type: RunType = RunType.BALANCED
    agent_b_final_statement: Optional[AgentFinalStatement] = None
    agent_c_final_statement: Optional[AgentFinalStatement] = None
    kendall_tau_at_convergence: float = 0.0
    ambiguity_score: float = 0.0
    converged_at: datetime = Field(default_factory=datetime.utcnow)
    factor_cache_url: str = ""
    dialectic_url: str = ""

    @model_validator(mode="after")
    def derive_run_type(self) -> "Attribution":
        f = self.fundamental_weight_total
        fl = self.flow_weight_total
        if f > 0.65:
            object.__setattr__(self, "run_type", RunType.FUNDAMENTAL_LED)
        elif fl > 0.65:
            object.__setattr__(self, "run_type", RunType.FLOW_LED)
        elif f < 0.45 and fl < 0.45:
            object.__setattr__(self, "run_type", RunType.UNATTRIBUTABLE)
        else:
            object.__setattr__(self, "run_type", RunType.BALANCED)
        return self


# ---------------------------------------------------------------------------
# Playbook cell (Agent D output)
# ---------------------------------------------------------------------------

class PlaybookCell(BaseModel):
    key: dict[str, Any]            # {"regime", "year", "grid_cell"}
    n_runs: int = 0
    n_confident: int = 0
    n_ambiguous: int = 0
    run_type_distribution: dict[str, int] = Field(default_factory=dict)
    top_factors_b_side: list[dict[str, Any]] = Field(default_factory=list)
    top_factors_c_side: list[dict[str, Any]] = Field(default_factory=list)
    median_profile: dict[str, Any] = Field(default_factory=dict)
    sub_clusters: list[dict[str, Any]] = Field(default_factory=list)
    entry_valuation_profile: dict[str, Any] = Field(default_factory=dict)
    duration_profile: dict[str, Any] = Field(default_factory=dict)
    magnitude_profile: dict[str, Any] = Field(default_factory=dict)
    failure_mode_warnings: list[str] = Field(default_factory=list)
