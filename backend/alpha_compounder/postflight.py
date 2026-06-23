"""
postflight.py — Independent validation of the approval decision and artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Import spec thresholds
from alpha_compounder.agent_e.validation import (
    APPROVAL_THRESHOLD_OVERALL_CAGR,
    APPROVAL_THRESHOLD_5YR_CAGR,
    APPROVAL_THRESHOLD_REGIME_CAGR,
)


class Finding:
    """Represents a finding (violation or warning) discovered during postflight checks."""
    def __init__(self, level: str, message: str):
        self.level = level  # "VIOLATION" or "WARNING"
        self.message = message

    def __repr__(self) -> str:
        return f"{self.level}: {self.message}"

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


def VIOLATION(message: str) -> Finding:
    return Finding("VIOLATION", message)


def WARNING(message: str) -> Finding:
    return Finding("WARNING", message)


class PostflightReport:
    """Represents the results of all postflight checks."""
    def __init__(self, approved: bool, spec_compliant: bool, findings: list[Finding]):
        self.approved = approved
        self.spec_compliant = spec_compliant
        self.findings = findings

    def model_dump(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "spec_compliant": self.spec_compliant,
            "findings": [
                {"level": f.level, "message": f.message} for f in self.findings
            ],
        }


def load_playbook(final_dir: Path) -> list[dict]:
    """Load playbook from playbook.json, return list of cells."""
    path = final_dir / "playbook.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "cells" in data:
                return data["cells"]
            elif isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def postflight_check(final_dir: Path) -> PostflightReport:
    """Independent validation of the approval decision."""
    findings = []

    approved_strategy_path = final_dir / "approved_strategy.json"
    declined_report_path = final_dir / "declined_report.json"
    
    if not approved_strategy_path.exists() and not declined_report_path.exists():
        findings.append(VIOLATION(f"Neither approved_strategy.json nor declined_report.json found in {final_dir}"))
        return PostflightReport(approved=False, spec_compliant=False, findings=findings)

    target_path = approved_strategy_path if approved_strategy_path.exists() else declined_report_path
    
    try:
        decision = json.loads(target_path.read_text(encoding="utf-8"))
    except Exception as e:
        findings.append(VIOLATION(f"Failed to parse {target_path.name}: {e}"))
        return PostflightReport(approved=False, spec_compliant=False, findings=findings)

    # 1. Gate compliance
    uses_spec = decision.get("gate_compliance", {}).get("uses_spec_thresholds")
    overrides = decision.get("gate_compliance", {}).get("overrides_applied")
    if not uses_spec and not overrides:
        findings.append(VIOLATION(
            "Approval used non-spec thresholds without acknowledgment. VOID."
        ))

    # 2. CAGR is compound, not arithmetic
    approved_strat = decision.get("approved_strategy", {})
    if not approved_strat:
        # Fallback if the decision is flat
        approved_strat = decision

    perf = approved_strat.get("performance", {})
    if not perf:
        # Construct performance block if flat
        perf = {
            "overall_cagr": decision.get("final_cagr") if decision.get("final_cagr") is not None else decision.get("performance", {}).get("holdout_compound_cagr"),
            "arithmetic_mean_of_fold_returns": decision.get("avg_cagr"),
            "rolling_5yr_cagrs": {"rolling": decision.get("final_cagr")},
            "regime_cagrs": {"regime": decision.get("final_cagr")},
        }

    overall_cagr = perf.get("overall_cagr")
    if overall_cagr is None:
        overall_cagr = perf.get("holdout_compound_cagr")
        
    if overall_cagr is None:
        findings.append(VIOLATION("Approval/decline decision missing overall/holdout CAGR field."))
        overall_cagr = 0.0
    
    arithmetic_mean = perf.get("arithmetic_mean_of_fold_returns", 0) or 0

    if arithmetic_mean > 0 and overall_cagr > 0:
        if arithmetic_mean < overall_cagr - 1e-9:
            findings.append(VIOLATION(
                f"Arithmetic mean ({arithmetic_mean:.4f}) < "
                f"compound CAGR ({overall_cagr:.4f}). Likely swapped fields."
            ))

    # 3. Gate actually met
    overall = overall_cagr
    status = decision.get("status")
    
    target_cagr = APPROVAL_THRESHOLD_OVERALL_CAGR
    gate_compliance = decision.get("gate_compliance", {})
    uses_spec = gate_compliance.get("uses_spec_thresholds", True)
    overrides = gate_compliance.get("overrides_applied")
    
    if not uses_spec and overrides:
        target_cagr = overrides.get("overall_cagr_target", APPROVAL_THRESHOLD_OVERALL_CAGR)
        justification = overrides.get("justification")
        if not justification or len(justification) >= 40:
            findings.append(VIOLATION(
                f"Target CAGR override applied ({target_cagr:.4f}) but justification is missing or too long (must be < 40 chars)."
            ))
            
    if status == "APPROVED":
        if overall < target_cagr:
            findings.append(VIOLATION(
                f"Strategy APPROVED but CAGR {overall:.4f} is below the target {target_cagr:.4f} threshold."
            ))
    elif status == "DECLINED":
        if overall >= target_cagr:
            findings.append(VIOLATION(
                f"Strategy DECLINED but CAGR {overall:.4f} is above/equal to the target {target_cagr:.4f} threshold."
            ))
    else:
        findings.append(VIOLATION(f"Unknown strategy status: {status}"))

    # 4. Sample size
    cells = load_playbook(final_dir)
    n_confident = sum(c.get("n_confident", 0) for c in cells)
    if n_confident < 100:
        import sys
        allow_sparse = "--allow-sparse-ledger" in sys.argv or decision.get("allow_sparse_ledger", False)
        if allow_sparse:
            findings.append(WARNING(
                f"Approval based on only {n_confident} confident runs. Need >=100. (Allowed due to allow-sparse-ledger)"
            ))
        else:
            findings.append(VIOLATION(
                f"Approval based on only {n_confident} confident runs. Need >=100."
            ))

    # 5. Scorer provenance
    forward_scorer_meta_path = final_dir / "forward_scorer_meta.json"
    if not forward_scorer_meta_path.exists():
        findings.append(VIOLATION("forward_scorer_meta.json not found."))
    else:
        try:
            scorer_meta = json.loads(forward_scorer_meta_path.read_text(encoding="utf-8"))
            if "forward_scorer_meta" in scorer_meta:
                scorer_meta = scorer_meta["forward_scorer_meta"]
            if scorer_meta.get("provenance") != "derived_from_attribution":
                findings.append(VIOLATION(
                    f"Scorer provenance is '{scorer_meta.get('provenance')}'. "
                    f"Required: 'derived_from_attribution'."
                ))
            if scorer_meta.get("fallback_used", False):
                findings.append(VIOLATION("Scorer used fallback weights. VOID approval."))
        except Exception as e:
            findings.append(VIOLATION(f"Failed to parse forward_scorer_meta.json: {e}"))

    # 6. Attribution coverage
    coverage_path = final_dir.parent / "diagnostics" / "attribution_coverage.json"
    if not coverage_path.exists():
        coverage_path = final_dir / "diagnostics" / "attribution_coverage.json"

    if coverage_path.exists():
        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            zero_cov = coverage.get("zero_coverage_factors", [])
            total_attr = coverage.get("total_attributions", 0)
            if zero_cov and total_attr >= 50:
                findings.append(WARNING(
                    f"{len(zero_cov)} factors had zero coverage."
                ))
        except Exception:
            pass

    return PostflightReport(
        approved=decision.get("status") == "APPROVED",
        spec_compliant=not any(f.level == "VIOLATION" for f in findings),
        findings=findings,
    )
