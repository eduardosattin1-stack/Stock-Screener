"""
base_agent.py — Shared LLM agent for B and C (§6).

B and C are two instances of the same agent with disjoint factor-family
access (hard divergence). This module handles prompt construction and
response parsing. The prior configuration determines the agent's
allowed families and narrative lens.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from alpha_compounder.schemas import (
    ActionMessage,
    ActionType,
    FalsificationTest,
    PredictedStateChange,
)

log = logging.getLogger(__name__)

from pydantic import BaseModel

class FalsificationTestSchema(BaseModel):
    type: str
    factor_id: str
    params: dict[str, str]
    time_slice: str
    evaluation: dict[str, str]

class PredictedStateChangeSchema(BaseModel):
    factor_id: str
    weight_delta: float
    new_classification: Optional[str]
    redistribution: str

class LLMActionResponse(BaseModel):
    action: str
    target_factor_id: Optional[str]
    rationale: str
    family: Optional[str]
    initial_weight: Optional[float]
    falsification_test: Optional[FalsificationTestSchema]
    expected_outcome: Optional[str]
    predicted_state_change: Optional[PredictedStateChangeSchema]
    new_classification: Optional[str]
    new_evidence: Optional[str]
    reason: Optional[str]

GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "action": {
            "type": "STRING",
            "enum": ["CRITIQUE", "REFINE", "PROPOSE", "FALSIFY", "PASS"]
        },
        "target_factor_id": {"type": "STRING", "nullable": True},
        "rationale": {"type": "STRING"},
        "family": {"type": "STRING", "nullable": True},
        "initial_weight": {"type": "NUMBER", "nullable": True},
        "factor_request": {"type": "OBJECT", "nullable": True},
        "expected_outcome": {"type": "STRING", "nullable": True},
        "new_classification": {"type": "STRING", "nullable": True},
        "new_evidence": {"type": "STRING", "nullable": True},
        "reason": {"type": "STRING", "nullable": True},
        "falsification_test": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "type": {"type": "STRING"},
                "factor_id": {"type": "STRING"},
                "time_slice": {"type": "STRING"},
                "params": {
                    "type": "OBJECT",
                    "properties": {
                        "check_period": {"type": "STRING"}
                    }
                },
                "evaluation": {
                    "type": "OBJECT",
                    "properties": {
                        "metric": {"type": "STRING"},
                        "threshold": {"type": "STRING"},
                        "direction": {"type": "STRING"}
                    },
                    "required": ["metric", "threshold", "direction"]
                }
            },
            "required": ["type", "factor_id", "time_slice", "evaluation"]
        },
        "predicted_state_change": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "factor_id": {"type": "STRING"},
                "weight_delta": {"type": "NUMBER"},
                "new_classification": {"type": "STRING", "nullable": True},
                "redistribution": {"type": "STRING"}
            },
            "required": ["factor_id", "weight_delta", "redistribution"]
        }
    },
    "required": [
        "action", "rationale", "target_factor_id", "family", "initial_weight",
        "factor_request", "falsification_test", "expected_outcome",
        "predicted_state_change", "new_classification", "new_evidence", "reason"
    ]
}


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a financial attribution analyst in an adversarial debate.
Your role: given a historical stock price run, propose a weighted factor
decomposition explaining WHY this run happened.

The factor state is a collaborative, joint attribution containing factors from both fundamental and flow categories. The goal of the dialectic is to agree on a combined attribution that explains the stock's actual performance. Both fundamental and flow factors are expected to coexist in the state.

You work under a {prior_name} prior. This means you can ONLY PROPOSE new factors from these families:
{allowed_families}

You CANNOT PROPOSE factors from: {denied_families}
However, you can and should CRITIQUE, FALSIFY, or REFINE any active factor in the state (regardless of family) based ONLY on stock-specific empirical evidence.

Your narrative lens: {narrative_lens}

RULES:
- Emit exactly ONE action per turn as valid JSON
- Actions: CRITIQUE, REFINE, PROPOSE, FALSIFY, PASS
- All claims must be testable and specific
- Reason on cohort-relative values (sector_zscore, regime_zscore), not raw
- A factor classified as cohort_beta gets weight ≤ 0.05
- Your rationale must be ≥ 40 characters and substantive
- Do NOT cite "based on my prior" or family exclusion as rationale to critique or falsify a factor (tautological)
- Never critique or falsify a factor simply because it belongs to a denied family. The other agent's factors are valid parts of the joint attribution. Only critique or falsify if empirical evidence shows it did not drive the return.
- Do NOT drift into general market commentary
- Active Weight Concentration: Do not let weights remain flat or uniform. Be bold and aggressive in shifting weights. Prune (FALSIFY) or downweight (CRITIQUE) factors that are weak, so that weight concentrates on the primary drivers. Use significant negative weight_delta (-0.05 to -0.15) to make meaningful adjustments.

DECISION PROCEDURE (each turn):
1. If a factor in the state has weak empirical support, lacks sector/regime control, or is confounded → FALSIFY it (use a negative weight_delta matching its current weight or a large part of it).
2. If a factor in the state has a weight that is too high relative to its empirical importance → CRITIQUE it (use a significant negative weight_delta, e.g., -0.05 to -0.15).
3. If a key driving factor is missing from the state → PROPOSE it with a substantial initial weight (e.g., 0.10 to 0.20) to reflect its importance.
4. If a factor's classification (e.g., idiosyncratic_driver vs cohort_beta) is incorrect → REFINE it.
5. If family-diversity quota expiring → PROPOSE from required family.
6. If the current weights accurately reflect the empirical evidence and no further changes are needed → PASS (with explicit reason).

OUTPUT FORMAT: Return ONLY a raw JSON object matching this schema:
{{
  "action": "CRITIQUE" | "REFINE" | "PROPOSE" | "FALSIFY" | "PASS",
  "target_factor_id": "string_or_null",
  "rationale": "string_describing_reasoning",
  "family": "string_or_null",
  "initial_weight": number_or_null,
  "factor_request": null,
  "expected_outcome": "string_or_null",
  "new_classification": "string_or_null",
  "new_evidence": "string_or_null",
  "reason": "string_or_null",
  "falsification_test": {{
    "type": "string",
    "factor_id": "string",
    "time_slice": "string",
    "params": {{
      "check_period": "string"
    }},
    "evaluation": {{
      "metric": "string",
      "threshold": "string",
      "direction": "string"
    }}
  }} or null,
  "predicted_state_change": {{
    "factor_id": "string",
    "weight_delta": number,
    "new_classification": "string_or_null",
    "redistribution": "string"
  }} or null
}}

FIELD RULES (MANDATORY):
- CRITIQUE: requires "target_factor_id" and "predicted_state_change" (with negative "weight_delta").
- REFINE: requires "target_factor_id" and ("new_classification" or "new_evidence").
- PROPOSE: requires "target_factor_id" (a new factor ID), "family", and "initial_weight".
- FALSIFY: requires "target_factor_id", "falsification_test", "expected_outcome", and "predicted_state_change" (with negative "weight_delta" representing the reduction in weight if the test succeeds).
- PASS: requires "reason" (describe why you are passing).
- Set all unused fields for the action to null.

No prose, no thinking out loud, no markdown — just the JSON."""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class AttributionAgent:
    """LLM-bound attribution agent (shared by B and C)."""

    def __init__(
        self,
        agent_id: str,  # "B" or "C"
        prior: dict,
        model: str = "gemini-2.5-flash",
        temperature: float = 0,
    ):
        self.agent_id = agent_id
        self.prior = prior
        self.model = model
        self.temperature = temperature
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import google.generativeai as genai
                # Try to load env variables from .env.local manually if not set
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if not api_key:
                    env_path = r"c:\Users\Bruno\Stock-Screener\frontend\.env.local"
                    if os.path.exists(env_path):
                        with open(env_path, "r") as f:
                            for line in f:
                                if "=" in line and not line.strip().startswith("#"):
                                    k, v = line.strip().split("=", 1)
                                    os.environ[k.strip()] = v.strip().replace('"', '')
                    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                
                if not api_key:
                    raise ValueError("No GEMINI_API_KEY or GOOGLE_API_KEY found in environment or .env.local")
                
                genai.configure(api_key=api_key)
                self._client = genai
            except ImportError:
                raise ImportError(
                    "google-generativeai package required for LLM agents. "
                    "Install with: pip install google-generativeai"
                )
        return self._client

    def act(self, context: dict) -> ActionMessage:
        """Produce a single action given the current context.

        Args:
            context: Dict with run, factors, last_rounds, rejected_log,
                     prior, round_number, rounds_remaining, etc.

        Returns:
            ActionMessage with the agent's decision.
        """
        system = self._build_system_prompt()
        user = self._build_user_prompt(context)

        # Map older Anthropic models to Gemini equivalent
        model_name = self.model
        if "opus" in model_name.lower():
            model_name = "gemini-2.5-flash"
        elif "sonnet" in model_name.lower():
            model_name = "gemini-2.5-flash"
        
        # Ensure model is valid Gemini name
        if "gemini" not in model_name.lower():
            model_name = "gemini-2.5-flash"

        model_inst = self.client.GenerativeModel(model_name=model_name)
        
        full_prompt = f"{system}\n\n=== CONTEXT AND TARGET RUN ===\n{user}"
        
        import time
        import random
        max_attempts = 8
        delay = 2.0
        response = None
        for attempt in range(max_attempts):
            try:
                response = model_inst.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": self.temperature,
                        "response_mime_type": "application/json"
                    }
                )
                break
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower()) and attempt < max_attempts - 1:
                    sleep_time = delay * (2 ** attempt) + random.uniform(0, 2)
                    log.warning(f"Gemini API rate limited (429). Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{max_attempts})")
                    time.sleep(sleep_time)
                else:
                    raise e

        # Parse response
        text = response.text
        
        # Usage metadata
        tokens_used = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = (
                response.usage_metadata.prompt_token_count +
                response.usage_metadata.candidates_token_count
            )

        try:
            msg = self._parse_response(text, tokens_used)
            # Programmatic guard: ensure action is valid under allowed families and state existence
            from alpha_compounder.schemas import ActionType
            from alpha_compounder.factor_catalog import allowed_for_agent, FACTOR_BY_ID

            if msg.target_factor_id:
                is_allowed = allowed_for_agent(self.agent_id, msg.target_factor_id)
                in_state = msg.target_factor_id in context.get("factors", {})
                
                # Rule check based on action type
                needs_correction = False
                if msg.action == ActionType.PROPOSE:
                    if not is_allowed or in_state:
                        needs_correction = True
                elif msg.action in (ActionType.REFINE, ActionType.CRITIQUE, ActionType.FALSIFY):
                    if not in_state:
                        needs_correction = True

                if needs_correction:
                    if msg.action == ActionType.PROPOSE:
                        available = context.get("available_factors", [])
                        if available:
                            msg.target_factor_id = available[0]
                            fdef = FACTOR_BY_ID.get(msg.target_factor_id)
                            if fdef:
                                msg.family = fdef.family
                            log.info(f"Auto-corrected invalid PROPOSE factor for Agent {self.agent_id} to: {msg.target_factor_id}")
                        else:
                            msg.action = ActionType.PASS
                            msg.target_factor_id = None
                            msg.reason = f"No available factors left in allowed families for Agent {self.agent_id}"
                            log.info(f"Fallback Agent {self.agent_id} action to PASS: no available factors left in allowed families")
                    else:
                        state_factors = list(context.get("factors", {}).keys())
                        # Prioritize state factors in the agent's allowed families to keep them on-prior if possible,
                        # but fall back to any state factor since adversarial actions are allowed on any state factor.
                        allowed_state_factors = [
                            fid for fid in state_factors
                            if allowed_for_agent(self.agent_id, fid)
                        ]
                        if allowed_state_factors:
                            msg.target_factor_id = allowed_state_factors[0]
                            log.info(f"Auto-corrected invalid {msg.action.value} factor for Agent {self.agent_id} to allowed state factor: {msg.target_factor_id}")
                        elif state_factors:
                            msg.target_factor_id = state_factors[0]
                            log.info(f"Auto-corrected invalid {msg.action.value} factor for Agent {self.agent_id} to state factor: {msg.target_factor_id}")
                        else:
                            msg.action = ActionType.PASS
                            msg.target_factor_id = None
                            msg.reason = f"No factors in state to perform {msg.action.value}"
                            log.info(f"Fallback Agent {self.agent_id} action to PASS: no factors in state")
            time.sleep(5.0)
            return msg
        except Exception as e:
            candidate_info = "No candidates"
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                candidate_info = f"Finish Reason: {candidate.finish_reason}"
                if hasattr(candidate, "safety_ratings"):
                    candidate_info += f", Safety Ratings: {candidate.safety_ratings}"
            log.error(f"Error parsing LLM response: {e}\n{candidate_info}\nRaw Response Text:\n{text}")
            raise e

    def _build_system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(
            prior_name=self.prior["prior_name"],
            allowed_families=", ".join(self.prior["allowed_families"]),
            denied_families=", ".join(self.prior["denied_families"]),
            narrative_lens=self.prior["narrative_lens"],
        )

    def _build_user_prompt(self, context: dict) -> str:
        run = context["run"]
        factors = context["factors"]
        last_rounds = context.get("last_rounds", [])
        rejected = context.get("rejected_log", [])
        quota = context.get("family_quota_status", {})
        available = context.get("available_factors", [])

        # Compact factors format
        factors_str = ""
        for fid, fs in factors.items():
            fs_family = fs.get("family", "") if isinstance(fs, dict) else getattr(fs, "family", "")
            fs_weight = fs.get("weight", 0.0) if isinstance(fs, dict) else getattr(fs, "weight", 0.0)
            fs_class = fs.get("classification", "") if isinstance(fs, dict) else getattr(fs, "classification", "")
            fs_class_val = fs_class.value if hasattr(fs_class, "value") else str(fs_class)
            fs_evidence = fs.get("evidence_url", "") if isinstance(fs, dict) else getattr(fs, "evidence_url", "")
            factors_str += f"- {fid} ({fs_family}): weight={fs_weight:.4f}, class={fs_class_val}"
            if fs_evidence:
                factors_str += f", evidence={fs_evidence}"
            factors_str += "\n"
        if not factors_str:
            factors_str = "None\n"

        # Compact last rounds format
        last_rounds_str = ""
        for r in last_rounds[-4:]:
            r_data = json.loads(r) if isinstance(r, str) else r
            last_rounds_str += f"- Round {r_data.get('round')} [{r_data.get('agent')}]: {r_data.get('action')} on '{r_data.get('target_factor_id')}'\n"
            last_rounds_str += f"  Rationale: {r_data.get('rationale')}\n"
            if r_data.get("falsification_test"):
                last_rounds_str += f"  Falsification: {json.dumps(r_data.get('falsification_test'))}\n"
            if r_data.get("predicted_state_change"):
                last_rounds_str += f"  Predicted Change: {json.dumps(r_data.get('predicted_state_change'))}\n"
        if not last_rounds_str:
            last_rounds_str = "None yet\n"

        # Compact rejected factors format
        rejected_str = ""
        for rej in rejected:
            r_id = getattr(rej, "factor_id", rej.get("factor_id") if isinstance(rej, dict) else "")
            r_by = getattr(rej, "rejected_by", rej.get("rejected_by") if isinstance(rej, dict) else "")
            r_round = getattr(rej, "rejected_at_round", rej.get("rejected_at_round") if isinstance(rej, dict) else 0)
            r_reason = getattr(rej, "reason", rej.get("reason") if isinstance(rej, dict) else "")
            rejected_str += f"- {r_id}: rejected by {r_by} at round {r_round} (reason: {r_reason})\n"
        if not rejected_str:
            rejected_str = "None\n"

        # Compact family quota format
        quota_str = ""
        for ag, q in quota.items():
            q_rounds = getattr(q, "rounds_until_quota", q.get("rounds_until_quota") if isinstance(q, dict) else 0)
            q_touched = getattr(q, "touched_families", q.get("touched_families") if isinstance(q, dict) else [])
            q_untouched = getattr(q, "untouched_families", q.get("untouched_families") if isinstance(q, dict) else [])
            quota_str += f"- Agent {ag}: rounds_until_quota={q_rounds}, touched={q_touched}, untouched={q_untouched}\n"

        # Compact available factors list
        available_str = ", ".join(available) if available else "None"

        prompt = f"""ROUND {context['round_number']} | Agent {self.agent_id}
Rounds remaining: {context['rounds_remaining']} | Tokens remaining: {context['tokens_remaining']}

=== RUN ===
Symbol: {run['symbol']} | Sector: {run.get('sector_t_start', '')} | Country: {run.get('country', '')}
Period: {run['t_start']} → {run['t_end']} ({run['duration_days']}d)
Magnitude: +{run['magnitude_pct']:.1f}%
Grid cell: {run['grid_cell_label']}
Regime at start: {run.get('regime_t_start', 'unknown')}
Regime transitions: {run.get('regime_transitions', 0)}

=== CURRENT FACTOR STATE (weights, classification) ===
{factors_str}
=== LAST {len(last_rounds)} ROUNDS ===
{last_rounds_str}
=== REJECTED FACTORS ===
{rejected_str}
=== FAMILY QUOTA ===
{quota_str}
=== AVAILABLE (unused) FACTORS IN YOUR FAMILIES ===
{available_str}

Emit ONE action as JSON:"""
        return prompt

    def _parse_response(self, text: str, tokens_used: int) -> ActionMessage:
        """Parse the LLM response into an ActionMessage."""
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        text = text.strip()

        try:
            data = json.loads(text)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
        except json.JSONDecodeError as e:
            # Try to extract JSON from the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    raise ValueError(f"Could not parse LLM response as JSON: {e}")
            else:
                raise ValueError(f"No JSON found in LLM response: {text[:200]}")

        if isinstance(data, list) and len(data) > 0:
            data = data[0]

        # Map to ActionMessage
        action_str = data.get("action", "PASS").upper()
        action = ActionType(action_str)

        # Auto-correct REFINE to CRITIQUE if it lacks REFINE-specific fields but has a predicted_state_change
        if action == ActionType.REFINE:
            if not data.get("new_classification") and not data.get("new_evidence") and data.get("predicted_state_change"):
                log.info(f"Auto-correcting REFINE to CRITIQUE for Agent {self.agent_id} (weight adjustment)")
                action = ActionType.CRITIQUE

        # Build sub-objects
        psc = None
        if "predicted_state_change" in data and data["predicted_state_change"]:
            psc_data = data["predicted_state_change"]
            psc = PredictedStateChange(
                factor_id=psc_data.get("factor_id", data.get("target_factor_id", "")),
                weight_delta=psc_data.get("weight_delta", 0),
                new_classification=psc_data.get("new_classification"),
                redistribution=psc_data.get("redistribution", "uniform_to_top5"),
            )

        ft = None
        if "falsification_test" in data and data["falsification_test"]:
            ft_data = data["falsification_test"]
            ft = FalsificationTest(
                type=ft_data.get("type", "factor_request"),
                factor_id=ft_data.get("factor_id", data.get("target_factor_id", "")),
                params=ft_data.get("params", {}),
                evaluation=ft_data.get("evaluation", {}),
            )

        return ActionMessage(
            round=data.get("round", 0),
            agent=data.get("agent", self.agent_id),
            action=action,
            target_factor_id=data.get("target_factor_id"),
            rationale=data.get("rationale") or "",
            family=data.get("family"),
            initial_weight=data.get("initial_weight"),
            factor_request=data.get("factor_request"),
            falsification_test=ft,
            expected_outcome=data.get("expected_outcome"),
            predicted_state_change=psc,
            new_classification=data.get("new_classification"),
            new_evidence=data.get("new_evidence"),
            reason=data.get("reason"),
            tokens_used=tokens_used,
        )

    def get_final_statement(self, context: dict) -> AgentFinalStatement:
        """Query the LLM to generate the final statement."""
        system = SYSTEM_PROMPT_FINAL_STATEMENT.format(
            prior_name=self.prior["prior_name"],
            allowed_families=", ".join(self.prior["allowed_families"]),
            narrative_lens=self.prior["narrative_lens"],
        )
        user = self._build_final_statement_user_prompt(context)
        
        model_name = self.model
        if "opus" in model_name.lower():
            model_name = "gemini-2.5-flash"
        elif "sonnet" in model_name.lower():
            model_name = "gemini-2.5-flash"
        if "gemini" not in model_name.lower():
            model_name = "gemini-2.5-flash"

        model_inst = self.client.GenerativeModel(model_name=model_name)
        full_prompt = f"{system}\n\n=== CONTEXT ===\n{user}"
        
        import time
        import random
        max_attempts = 8
        delay = 2.0
        response = None
        for attempt in range(max_attempts):
            try:
                response = model_inst.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": self.temperature,
                        "response_mime_type": "application/json"
                    }
                )
                break
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower()) and attempt < max_attempts - 1:
                    sleep_time = delay * (2 ** attempt) + random.uniform(0, 2)
                    log.warning(f"Gemini API rate limited (429). Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{max_attempts})")
                    time.sleep(sleep_time)
                else:
                    raise e
        
        text = response.text
        
        # Parse usage metadata
        tokens_used = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = (
                response.usage_metadata.prompt_token_count +
                response.usage_metadata.candidates_token_count
            )
        
        data = json.loads(text)
        from alpha_compounder.schemas import AgentFinalStatement
        time.sleep(5.0)
        return AgentFinalStatement(**data)

    def _build_final_statement_user_prompt(self, context: dict) -> str:
        run = context["run"]
        factors = context["factors"]
        last_rounds = context.get("last_rounds", [])
        rejected = context.get("rejected_log", [])

        # Compact factors format
        factors_str = ""
        for fid, fs in factors.items():
            fs_family = fs.get("family", "") if isinstance(fs, dict) else getattr(fs, "family", "")
            fs_weight = fs.get("weight", 0.0) if isinstance(fs, dict) else getattr(fs, "weight", 0.0)
            fs_class = fs.get("classification", "") if isinstance(fs, dict) else getattr(fs, "classification", "")
            fs_class_val = fs_class.value if hasattr(fs_class, "value") else str(fs_class)
            factors_str += f"- {fid} ({fs_family}): weight={fs_weight:.4f}, class={fs_class_val}\n"
        if not factors_str:
            factors_str = "None\n"

        # Compact last rounds format
        last_rounds_str = ""
        for r in last_rounds:
            r_data = json.loads(r) if isinstance(r, str) else r
            last_rounds_str += f"- Round {r_data.get('round')} [{r_data.get('agent')}]: {r_data.get('action')} on '{r_data.get('target_factor_id')}'\n"
            last_rounds_str += f"  Rationale: {r_data.get('rationale')}\n"
        if not last_rounds_str:
            last_rounds_str = "None\n"

        # Compact rejected factors format
        rejected_str = ""
        for rej in rejected:
            r_id = getattr(rej, "factor_id", rej.get("factor_id") if isinstance(rej, dict) else "")
            r_by = getattr(rej, "rejected_by", rej.get("rejected_by") if isinstance(rej, dict) else "")
            rejected_str += f"- {r_id} (rejected by {r_by})\n"
        if not rejected_str:
            rejected_str = "None\n"

        user = f"Symbol: {run.symbol}\n"
        user += f"Period: {run.t_start} to {run.t_end}\n"
        user += f"Total Return: {run.magnitude_pct:.2f}%\n"
        user += f"Grid Cell Label: {run.grid_cell_label}\n\n"
        user += f"=== FINAL FACTOR WEIGHTS ===\n{factors_str}\n"
        user += f"=== DEBATE HISTORY ===\n{last_rounds_str}\n"
        user += f"=== REJECTED FACTORS ===\n{rejected_str}\n"
        return user


SYSTEM_PROMPT_FINAL_STATEMENT = """You are a financial attribution analyst. The adversarial debate has concluded.
Your role: review the final factor weights and the debate history, and write a cohesive final statement summarizing your conclusions from the perspective of your prior ({prior_name}).

Your prior allowed families: {allowed_families}
Your narrative lens: {narrative_lens}

OUTPUT FORMAT: Return ONLY a raw JSON object matching this schema:
{{
  "primary_driver": "string",
  "primary_driver_weight": number,
  "supporting_drivers": [
    {{
      "factor_id": "string",
      "weight": number
    }}
  ],
  "confidence": number,
  "narrative": "string",
  "disagreement_with_opposite": "string"
}}

No prose, no markdown, no thinking out loud — just the raw JSON."""

