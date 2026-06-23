"""
loop.py — Main orchestrator for the B↔C adversarial attribution loop (§5).

Deterministic Python. Manages round scheduling, state I/O, convergence
checks, budget enforcement, and anti-mode-collapse rules. LLM calls
are delegated to agents/base_agent.py.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from alpha_compounder.config import (
    CONVERGENCE,
    DEFAULT_BUDGET,
    GCS_PREFIX,
    PRIOR_B,
    PRIOR_C,
    BudgetConfig,
)
from alpha_compounder.factor_catalog import (
    B_FAMILIES,
    C_FAMILIES,
    FACTOR_BY_ID,
    allowed_for_agent,
    get_available_factors,
)
from alpha_compounder.schemas import (
    ActionMessage,
    ActionType,
    Attribution,
    AgentFinalStatement,
    BudgetStatus,
    ConvergenceEntry,
    ConvergenceStatus,
    FactorState,
    FamilyQuotaStatus,
    LoopState,
    RejectedFactor,
    RunRecord,
    RunType,
)
from alpha_compounder.utils import kendall_tau, mean_kendall_tau

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Convergence checking (§5)
# ---------------------------------------------------------------------------

def check_convergence(state: LoopState, budget: Optional[BudgetConfig] = None) -> ConvergenceStatus:
    """Evaluate convergence criteria."""
    recent = state.rounds[-CONVERGENCE["stability_window"]:]

    # Extract top-5 rankings from recent rounds
    def _top5_from_round_data(r_data: dict) -> list[str]:
        """Get top-5 factor IDs by weight at a given round."""
        snapshot = r_data.get("factors_snapshot", {})
        if not snapshot:
            snapshot = {fid: fs.weight for fid, fs in state.factors.items()}
        sorted_factors = sorted(
            snapshot.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return [fid for fid, _ in sorted_factors[:5]]

    tau = 0.0
    if len(recent) >= CONVERGENCE["stability_window"]:
        rankings = []
        for r in recent:
            r_data = json.loads(r) if isinstance(r, str) else r
            rankings.append(_top5_from_round_data(r_data))
        if len(rankings) >= 2:
            tau = mean_kendall_tau(rankings)

    # Update convergence history
    if state.round_count > 0:
        state.convergence_history.append(
            ConvergenceEntry(round=state.round_count, kendall_tau_last8=round(tau, 4))
        )

    # 1. Stability: top-5 weights stable over last 8 rounds
    if len(recent) >= CONVERGENCE["stability_window"] and tau >= CONVERGENCE["stability_tau_threshold"]:
        return ConvergenceStatus.CONVERGED_STABILITY

    # 2. Saturation: no new factors + tiny weight changes
    sat_window = CONVERGENCE["saturation_window"]
    if len(recent) >= sat_window:
        last_n = recent[-sat_window:]
        has_propose = any(
            (json.loads(r) if isinstance(r, str) else r).get("action") == "PROPOSE"
            for r in last_n
        )
        if not has_propose:
            # Check weight deltas
            max_delta = 0.0
            for r in last_n:
                r_data = json.loads(r) if isinstance(r, str) else r
                psc = r_data.get("predicted_state_change", {})
                if psc:
                    delta = abs(psc.get("weight_delta", 0))
                    max_delta = max(max_delta, delta)
            if max_delta < CONVERGENCE["saturation_max_weight_delta"]:
                return ConvergenceStatus.CONVERGED_SATURATION

    # 3. Hard cap
    max_rounds = budget.max_rounds_per_run if budget is not None else DEFAULT_BUDGET.max_rounds_per_run
    if state.round_count >= max_rounds:
        if tau >= CONVERGENCE["forced_tau_threshold"]:
            return ConvergenceStatus.CONVERGED_FORCED
        else:
            return ConvergenceStatus.AMBIGUOUS_AT_CAP

    return ConvergenceStatus.CONTINUE


# ---------------------------------------------------------------------------
# Validation rules (§10)
# ---------------------------------------------------------------------------

def validate_action(
    msg: ActionMessage,
    state: LoopState,
) -> tuple[bool, str]:
    """Validate an action message against all rules.
    Returns (is_valid, reason)."""

    # 1. Factor ID in catalog (for PROPOSE)
    if msg.action == ActionType.PROPOSE:
        if msg.target_factor_id not in FACTOR_BY_ID:
            return False, f"Unknown factor_id: {msg.target_factor_id}"

    # 2. Factor in allowed family (only enforced for PROPOSE)
    if msg.target_factor_id and msg.action == ActionType.PROPOSE:
        if not allowed_for_agent(msg.agent, msg.target_factor_id):
            return False, (
                f"Factor {msg.target_factor_id} not in {msg.agent}'s allowed families"
            )

    # 3. Factor exists in state (for CRITIQUE, REFINE, FALSIFY)
    if msg.action in (ActionType.CRITIQUE, ActionType.REFINE, ActionType.FALSIFY):
        if msg.target_factor_id not in state.factors:
            return False, (
                f"Factor {msg.target_factor_id} not in current state "
                f"(required for {msg.action.value})"
            )

    # 4. Not in rejected log (for PROPOSE, unless new evidence)
    if msg.action == ActionType.PROPOSE:
        for rej in state.rejected_log:
            if rej.factor_id == msg.target_factor_id and not rej.can_be_revived:
                if not msg.new_evidence:
                    return False, (
                        f"Factor {msg.target_factor_id} is in rejected log "
                        f"and no new_evidence provided"
                    )

    # 5. Weight delta signed (for CRITIQUE)
    if msg.action == ActionType.CRITIQUE and msg.predicted_state_change:
        wd = msg.predicted_state_change.weight_delta
        if wd >= 0:
            return False, "CRITIQUE weight_delta must be negative"

    # 6. FALSIFY test concrete
    if msg.action == ActionType.FALSIFY:
        if msg.falsification_test:
            ev = msg.falsification_test.evaluation
            if not ev or not all(k in ev for k in ("metric", "threshold", "direction")):
                return False, "FALSIFY evaluation must specify metric, threshold, direction"

    # 7. Rationale minimum length
    if msg.action != ActionType.PASS and msg.rationale and len(msg.rationale) < 40:
        return False, f"Rationale too short ({len(msg.rationale)} chars, need >= 40)"

    return True, ""


# ---------------------------------------------------------------------------
# Anti-mode-collapse checks (§5)
# ---------------------------------------------------------------------------

def check_anti_mode_collapse(
    msg: ActionMessage,
    state: LoopState,
) -> tuple[bool, str]:
    """Check anti-mode-collapse rules. Returns (is_valid, reason)."""

    agent = msg.agent

    # 1. Family diversity quota: every 10 rounds, must touch a new family
    if agent in state.family_quota_status:
        quota = state.family_quota_status[agent]
        if quota.rounds_until_quota <= 0 and quota.untouched_families:
            if msg.action == ActionType.PASS:
                return False, (
                    f"Family diversity quota expired: must touch one of "
                    f"{quota.untouched_families}"
                )

    # 2. No echo: PROPOSE can't Jaccard-match last 3 PROPOSEs
    if msg.action == ActionType.PROPOSE:
        recent_proposes = []
        for r in reversed(state.rounds):
            r_data = json.loads(r) if isinstance(r, str) else r
            if r_data.get("agent") == agent and r_data.get("action") == "PROPOSE":
                recent_proposes.append(r_data.get("target_factor_id", ""))
                if len(recent_proposes) >= 3:
                    break
        if msg.target_factor_id in recent_proposes:
            return False, (
                f"Echo detected: {msg.target_factor_id} was proposed in last 3 PROPOSEs"
            )

    # 3. Weight gravity check disabled to allow weights to exceed 0.50
    pass

    return True, ""


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def init_state(
    run: RunRecord,
    pipeline_run_id: str,
    prior_b: dict,
    prior_c: dict,
) -> LoopState:
    """Initialize the loop state for a run."""

    # Seed factors from both priors' initial_factor_priors
    factors = {}
    for fid, weight in prior_b.get("initial_factor_priors", {}).items():
        if fid in FACTOR_BY_ID:
            factors[fid] = FactorState(
                weight=weight,
                family=FACTOR_BY_ID[fid].family,
                introduced_by="B",
            )
    for fid, weight in prior_c.get("initial_factor_priors", {}).items():
        if fid in FACTOR_BY_ID:
            factors[fid] = FactorState(
                weight=weight,
                family=FACTOR_BY_ID[fid].family,
                introduced_by="C",
            )

    # Normalize weights to sum to 1.0
    total = sum(f.weight for f in factors.values())
    if total > 0:
        for fid in factors:
            factors[fid].weight = round(factors[fid].weight / total, 4)

    # Family quota status
    b_allowed = list(B_FAMILIES)
    c_allowed = list(C_FAMILIES)

    return LoopState(
        run_id=run.run_id,
        pipeline_run_id=pipeline_run_id,
        prior_b=f"{prior_b['prior_name']}_v{prior_b['version']}",
        prior_c=f"{prior_c['prior_name']}_v{prior_c['version']}",
        factors=factors,
        family_quota_status={
            "B": FamilyQuotaStatus(
                touched_families=[],
                untouched_families=b_allowed,
                rounds_until_quota=10,
            ),
            "C": FamilyQuotaStatus(
                touched_families=[],
                untouched_families=c_allowed,
                rounds_until_quota=10,
            ),
        },
        budget=BudgetStatus(
            tokens_remaining=DEFAULT_BUDGET.max_tokens_per_run,
        ),
    )


def execute_action(state: LoopState, msg: ActionMessage) -> None:
    """Apply an action to the state."""

    if msg.action == ActionType.CRITIQUE:
        fid = msg.target_factor_id
        if fid in state.factors and msg.predicted_state_change:
            delta = msg.predicted_state_change.weight_delta
            old_weight = state.factors[fid].weight
            new_weight = max(0.0, old_weight + delta)
            redistributed = old_weight - new_weight
            state.factors[fid].weight = new_weight
            state.factors[fid].last_modified_round = state.round_count

            # Redistribute to top-5 by weight (excluding target)
            others = sorted(
                [(k, v) for k, v in state.factors.items() if k != fid],
                key=lambda kv: kv[1].weight,
                reverse=True,
            )[:5]
            if others:
                share = redistributed / len(others)
                for k, v in others:
                    state.factors[k].weight += share

    elif msg.action == ActionType.REFINE:
        fid = msg.target_factor_id
        if fid in state.factors:
            if msg.new_classification:
                state.factors[fid].classification = msg.new_classification
            state.factors[fid].last_modified_round = state.round_count

    elif msg.action == ActionType.PROPOSE:
        fid = msg.target_factor_id
        initial_w = msg.initial_weight or 0.10
        state.factors[fid] = FactorState(
            weight=initial_w,
            family=msg.family or FACTOR_BY_ID.get(fid, {}).family,
            introduced_by=msg.agent,
            introduced_at_round=state.round_count,
            last_modified_round=state.round_count,
        )
        # Normalize weights
        total = sum(f.weight for f in state.factors.values())
        if total > 0:
            for k in state.factors:
                state.factors[k].weight = round(
                    state.factors[k].weight / total, 4
                )

    elif msg.action == ActionType.FALSIFY:
        fid = msg.target_factor_id
        # The falsification test result determines the action
        # For now, apply the predicted state change
        if fid in state.factors and msg.predicted_state_change:
            delta = msg.predicted_state_change.weight_delta
            new_classification = msg.predicted_state_change.new_classification
            if new_classification:
                state.factors[fid].classification = new_classification
            old_weight = state.factors[fid].weight
            new_weight = max(0.0, old_weight + delta)
            redistributed = old_weight - new_weight
            state.factors[fid].weight = new_weight
            state.factors[fid].last_modified_round = state.round_count

            # If weight drops to 0, move to rejected log
            if new_weight <= 0.01:
                state.rejected_log.append(RejectedFactor(
                    factor_id=fid,
                    rejected_at_round=state.round_count,
                    rejected_by=msg.agent,
                    reason=msg.rationale or "FALSIFY test rejected",
                ))
                del state.factors[fid]

            # Redistribute to top-5 by weight (excluding target)
            others = sorted(
                [(k, v) for k, v in state.factors.items() if k != fid],
                key=lambda kv: kv[1].weight,
                reverse=True,
            )[:5]
            if others:
                share = redistributed / len(others)
                for k, v in others:
                    state.factors[k].weight += share

    # Update family quota
    if msg.target_factor_id and msg.agent in state.family_quota_status:
        fdef = FACTOR_BY_ID.get(msg.target_factor_id)
        if fdef:
            quota = state.family_quota_status[msg.agent]
            if fdef.family not in quota.touched_families:
                quota.touched_families.append(fdef.family)
                if fdef.family in quota.untouched_families:
                    quota.untouched_families.remove(fdef.family)
            # Reset countdown every 10 rounds
            if state.round_count % 10 == 0:
                quota.rounds_until_quota = 10
            else:
                quota.rounds_until_quota = max(0, quota.rounds_until_quota - 1)

    # Track consecutive PASSes
    if msg.action == ActionType.PASS:
        state.consecutive_passes[msg.agent] = (
            state.consecutive_passes.get(msg.agent, 0) + 1
        )
    else:
        state.consecutive_passes[msg.agent] = 0

    # Serialize and append round with factors snapshot
    round_data = msg.model_dump(mode="json")
    round_data["factors_snapshot"] = {fid: fs.weight for fid, fs in state.factors.items()}
    state.rounds.append(round_data)


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------

def finalize_attribution(
    state: LoopState,
    status: ConvergenceStatus,
    agent_b_final_statement: Optional[AgentFinalStatement] = None,
    agent_c_final_statement: Optional[AgentFinalStatement] = None,
) -> Attribution:
    """Build the final Attribution from the converged state."""

    # Compute weight totals by prior
    fundamental_total = sum(
        fs.weight for fid, fs in state.factors.items()
        if FACTOR_BY_ID.get(fid) and FACTOR_BY_ID[fid].family in B_FAMILIES
    )
    flow_total = sum(
        fs.weight for fid, fs in state.factors.items()
        if FACTOR_BY_ID.get(fid) and FACTOR_BY_ID[fid].family in C_FAMILIES
    )

    # Build final weights dict
    final_weights = {fid: round(fs.weight, 4) for fid, fs in state.factors.items()}
    final_classifications = {
        fid: fs.classification.value if hasattr(fs.classification, "value")
        else str(fs.classification)
        for fid, fs in state.factors.items()
    }

    # Rejected factors
    rejected = [
        {"factor_id": r.factor_id, "reason": r.reason}
        for r in state.rejected_log
    ]

    # Compute Kendall tau at convergence
    tau = 0.0
    if state.convergence_history:
        tau = state.convergence_history[-1].kendall_tau_last8

    # Ambiguity score: 1 - tau (higher = more ambiguous)
    ambiguity = round(1.0 - tau, 4)

    return Attribution(
        run_id=state.run_id,
        pipeline_run_id=state.pipeline_run_id,
        status=status,
        rounds_used=state.round_count,
        tokens_used=state.budget.tokens_used,
        cost_usd=state.budget.cost_usd,
        prior_b=state.prior_b,
        prior_c=state.prior_c,
        final_weights=final_weights,
        final_classifications=final_classifications,
        rejected_factors=rejected,
        fundamental_weight_total=round(fundamental_total, 4),
        flow_weight_total=round(flow_total, 4),
        kendall_tau_at_convergence=tau,
        ambiguity_score=ambiguity,
        agent_b_final_statement=agent_b_final_statement,
        agent_c_final_statement=agent_c_final_statement,
        factor_cache_url=f"gs://{GCS_PREFIX}/factor_cache/{state.run_id}.json",
        dialectic_url=f"gs://{GCS_PREFIX}/attributions/{state.run_id}/",
    )


def _get_statements_and_finalize(
    state: LoopState,
    status: ConvergenceStatus,
    run: RunRecord,
    agent_b,
    agent_c,
) -> Attribution:
    """Helper to generate final statements and finalize attribution."""
    agent_b_statement = None
    agent_c_statement = None
    
    # Try generating final statements
    try:
        statement_context = {
            "run": run,
            "factors": state.factors,
            "last_rounds": state.rounds,
            "rejected_log": state.rejected_log,
        }
        log.info("Generating Agent B final statement...")
        agent_b_statement = agent_b.get_final_statement(statement_context)
        log.info("Generating Agent C final statement...")
        agent_c_statement = agent_c.get_final_statement(statement_context)
    except Exception as e:
        log.warning(f"Failed to generate final statements: {e}")
        
    return finalize_attribution(
        state=state,
        status=status,
        agent_b_final_statement=agent_b_statement,
        agent_c_final_statement=agent_c_statement,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_attribution_loop(
    run: RunRecord,
    factor_service,
    agent_b,
    agent_c,
    prior_b: dict = None,
    prior_c: dict = None,
    budget: BudgetConfig = None,
    pipeline_run_id: str = None,
) -> Attribution:
    """Execute the B↔C adversarial attribution loop for a single run.

    Args:
        run: The RunRecord to attribute
        factor_service: FactorService instance
        agent_b: Agent B (fundamental-only)
        agent_c: Agent C (flow-only)
        prior_b/c: Prior configs (default from config.py)
        budget: Budget config
        pipeline_run_id: UUID for this pipeline execution
    """
    prior_b = prior_b or PRIOR_B
    prior_c = prior_c or PRIOR_C
    budget = budget or DEFAULT_BUDGET
    pipeline_run_id = pipeline_run_id or str(uuid.uuid4())

    state = init_state(run, pipeline_run_id, prior_b, prior_c)
    start_time = time.time()

    log.info(f"Attribution loop: {run.symbol} [{run.t_start} → {run.t_end}] "
             f"+{run.magnitude_pct:.0f}% ({run.grid_cell_label})")

    while True:
        active = "B" if state.round_count % 2 == 0 else "C"
        agent = agent_b if active == "B" else agent_c
        prior = prior_b if active == "B" else prior_c

        # Build context for the agent
        context = _build_context(state, active, prior, run)

        # Call the LLM agent (with retries)
        msg = None
        retries = 0
        while retries < 3:
            try:
                msg = agent.act(context)
                msg.round = state.round_count
                msg.agent = active

                # Validate
                valid, reason = validate_action(msg, state)
                if not valid:
                    log.warning(f"  Round {state.round_count} [{active}]: "
                                f"INVALID — {reason}")
                    state.consecutive_invalid[active] += 1
                    retries += 1
                    continue

                # Anti-mode-collapse
                valid, reason = check_anti_mode_collapse(msg, state)
                if not valid:
                    log.warning(f"  Round {state.round_count} [{active}]: "
                                f"MODE_COLLAPSE — {reason}")
                    retries += 1
                    continue

                break
            except Exception as e:
                log.warning(f"  Round {state.round_count} [{active}]: "
                            f"LLM error — {e}")
                retries += 1

        if msg is None or retries >= 3:
            state.consecutive_invalid[active] += 1
            if state.consecutive_invalid[active] >= 3:
                log.error(f"  MALFORMED: 3 consecutive invalid retries from {active}")
                return finalize_attribution(state, ConvergenceStatus.MALFORMED)
            continue

        # Reset invalid counter on success
        state.consecutive_invalid[active] = 0

        # Execute action
        execute_action(state, msg)
        state.round_count += 1

        # Update budget
        state.budget.tokens_used += msg.tokens_used
        state.budget.tokens_remaining = (
            budget.max_tokens_per_run - state.budget.tokens_used
        )
        state.budget.wall_clock_seconds = time.time() - start_time

        # Log progress
        log.info(f"  Round {state.round_count} [{active}]: "
                 f"{msg.action.value} → {msg.target_factor_id or msg.reason or ''}")

        # Check convergence
        if state.round_count >= 2:
            log.info(f"  → Asymmetric Loop forced finalization after {state.round_count} rounds.")
            return _get_statements_and_finalize(state, ConvergenceStatus.CONVERGED_STABILITY, run, agent_b, agent_c)

        convergence = check_convergence(state, budget)
        if convergence != ConvergenceStatus.CONTINUE:
            log.info(f"  → {convergence.value} at round {state.round_count}")
            return _get_statements_and_finalize(state, convergence, run, agent_b, agent_c)

        # Check budget
        if state.budget.tokens_used >= budget.max_tokens_per_run:
            log.info(f"  → CONVERGED_BUDGET at round {state.round_count}")
            return _get_statements_and_finalize(state, ConvergenceStatus.CONVERGED_BUDGET, run, agent_b, agent_c)
        if state.budget.wall_clock_seconds >= budget.max_seconds_per_run:
            log.info(f"  → CONVERGED_BUDGET (time) at round {state.round_count}")
            return _get_statements_and_finalize(state, ConvergenceStatus.CONVERGED_BUDGET, run, agent_b, agent_c)

        # Check consecutive PASSes
        for ag in ("B", "C"):
            if state.consecutive_passes.get(ag, 0) >= CONVERGENCE["consecutive_pass_limit"]:
                log.info(f"  → CONVERGED_SATURATION ({ag} passed 3x)")
                return _get_statements_and_finalize(
                    state, ConvergenceStatus.CONVERGED_SATURATION, run, agent_b, agent_c
                )


def _build_context(
    state: LoopState,
    active: str,
    prior: dict,
    run: RunRecord,
) -> dict:
    """Build the context bundle for an agent's turn."""
    return {
        "run": run.model_dump(mode="json"),
        "factors": {
            fid: fs.model_dump(mode="json")
            for fid, fs in state.factors.items()
        },
        "last_rounds": state.rounds[-8:],
        "rejected_log": [r.model_dump(mode="json") for r in state.rejected_log],
        "prior": prior,
        "round_number": state.round_count,
        "rounds_remaining": DEFAULT_BUDGET.max_rounds_per_run - state.round_count,
        "tokens_remaining": state.budget.tokens_remaining,
        "family_quota_status": (
            state.family_quota_status[active].model_dump(mode="json")
            if active in state.family_quota_status else {}
        ),
        "available_factors": [
            f.factor_id for f in get_available_factors(active)
            if f.factor_id not in state.factors
        ],
    }
