"""
preflight.py — Pre-run sanity check to catch obvious configuration errors before calling LLMs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime
from alpha_compounder.factor_catalog import ALL_FACTORS
from alpha_compounder.config import PRIOR_B, PRIOR_C
from alpha_compounder.agent_e.validation import APPROVAL_THRESHOLD_OVERALL_CAGR

EXPECTED_SPEC_VERSION = "2.1"


class PreflightWarning:
    """Represents a warning or critical issue identified during preflight checks."""
    def __init__(self, level: str, message: str):
        self.level = level  # "CRITICAL" or "WARNING"
        self.message = message

    def __repr__(self) -> str:
        return f"{self.level}: {self.message}"

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


def CRITICAL(message: str) -> PreflightWarning:
    return PreflightWarning("CRITICAL", message)


def WARNING(message: str) -> PreflightWarning:
    return PreflightWarning("WARNING", message)


def read_spec_version() -> str:
    """Find and parse the spec version from alpha-compounder-spec-v2.md."""
    paths = [
        r"C:\Users\Bruno\Desktop\alpha-compounder-spec-v2.1.md",
        r"C:\Users\Bruno\Stock-Screener\alpha-compounder-spec-v2.1.md",
        r"C:\Users\Bruno\Stock-Screener\backend\alpha-compounder-spec-v2.1.md",
        r"C:\Users\Bruno\Desktop\alpha-compounder-spec-v2.md",
        r"C:\Users\Bruno\Stock-Screener\alpha-compounder-spec-v2.md",
        r"C:\Users\Bruno\Stock-Screener\backend\alpha-compounder-spec-v2.md",
        r"C:\Users\Bruno\Stock-Screener\temp_spec.md"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    first_line = f.readline()
                    m = re.search(r"\(v([\d\.]+)\)", first_line)
                    if m:
                        return m.group(1)
            except Exception:
                pass
    return "unknown"


def load_factor_catalog() -> list[str]:
    """Load list of factor IDs from catalog."""
    return [f.factor_id for f in ALL_FACTORS]


def load_prior(name: str) -> dict:
    """Load prior config dictionary."""
    if name == "fundamental_only":
        return PRIOR_B
    elif name == "flow_microstructure_only":
        return PRIOR_C
    return {}


def preflight_check(args) -> list[PreflightWarning]:
    """Catch obvious config errors before spending compute."""
    issues: list[PreflightWarning] = []

    # 1. Window must be long enough for compounder cells
    if hasattr(args, "window") and args.window:
        try:
            window = args.window.split(":")
            window_start = datetime.strptime(window[0], "%Y-%m-%d")
            window_end = datetime.strptime(window[1], "%Y-%m-%d")
            window_years = (window_end - window_start).days / 365.25
            if window_years < 2.5 and not getattr(args, "smoke_test", False):
                issues.append(CRITICAL(
                    f"Window is {window_years:.1f}yr. Compounder cells (>=250 days) cannot populate "
                    f"meaningfully in <2.5yr. Pass --smoke-test to bypass for plumbing tests."
                ))
        except Exception as e:
            issues.append(CRITICAL(f"Failed to parse window option '{args.window}': {e}"))

    # 2. Cache directory exists and non-empty
    if hasattr(args, "cache_dir") and args.cache_dir:
        cache_dir = Path(args.cache_dir)
        if not cache_dir.exists():
            issues.append(CRITICAL(f"Cache dir {cache_dir} does not exist."))
        else:
            files_v1 = list(cache_dir.glob("*_historical_price_eod.json"))
            files_v2 = list(cache_dir.glob("historical-price-eod/full/*.json"))
            files_v3 = list(cache_dir.glob("income-statement/*.json"))
            total_files = len(files_v1) + len(files_v2) + len(files_v3)
            if total_files < 100:
                issues.append(CRITICAL(
                    f"Cache dir has only {total_files} files (need >=100). Run download_fmp_raw.py first."
                ))

    # 3. Gate thresholds (Agent E)
    if getattr(args, "override_target_cagr", None) is not None:
        override_val = args.override_target_cagr
        if override_val != APPROVAL_THRESHOLD_OVERALL_CAGR:
            if not getattr(args, "override_gate_thresholds", False):
                issues.append(CRITICAL(
                    f"Gate threshold modified to {override_val} from spec {APPROVAL_THRESHOLD_OVERALL_CAGR}. "
                    f"Requires --override-gate-thresholds + justification."
                ))
            elif not getattr(args, "override_justification", None) or len(getattr(args, "override_justification", "")) >= 40:
                issues.append(CRITICAL(
                    f"Gate threshold override requires --override-justification with less than 40 characters."
                ))

    # 4. Spec version pinned
    spec_version = read_spec_version()
    if spec_version != EXPECTED_SPEC_VERSION:
        issues.append(WARNING(
            f"Spec version {spec_version} != expected {EXPECTED_SPEC_VERSION}. Update or pin."
        ))

    # 5. Catalog vs priors sanity
    catalog_factors = load_factor_catalog()
    prior_b = load_prior("fundamental_only")
    prior_c = load_prior("flow_microstructure_only")
    seeded_b = set(prior_b.get("initial_factor_priors", {}).keys())
    seeded_c = set(prior_c.get("initial_factor_priors", {}).keys())

    unknown_b = seeded_b - set(catalog_factors)
    unknown_c = seeded_c - set(catalog_factors)
    if unknown_b or unknown_c:
        issues.append(CRITICAL(
            f"Prior seeds reference factor_ids not in catalog. "
            f"B unknown: {unknown_b}. C unknown: {unknown_c}."
        ))

    return issues
