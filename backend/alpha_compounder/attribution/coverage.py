# alpha_compounder/attribution/coverage.py

from dataclasses import dataclass
from typing import Sequence
import os
import json

def median(lst):
    if not lst:
        return 0.0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    else:
        return (s[n // 2 - 1] + s[n // 2]) / 2.0

class InsufficientAttributionsError(ValueError):
    pass

class CatalogLoadingError(ValueError):
    pass

@dataclass
class AttributionCoverageReport:
    total_attributions: int
    coverage_by_factor: dict[str, float]      # factor_id -> fraction of runs where used
    coverage_by_family: dict[str, float]
    zero_coverage_factors: list[str]
    low_coverage_factors: list[str]            # 0 < coverage < 0.05
    high_weight_factors: list[tuple[str, float]]  # factors with median weight > 0.15
    catalog_loaded: list[str]                  # what was actually available to agents
    catalog_used: list[str]                    # what actually showed up in attributions

def attribution_coverage(
    attributions: dict[str, dict],  # run_id -> attribution dict
    catalog: list[str],
    catalog_to_family: dict[str, str],
) -> AttributionCoverageReport:
    coverage_count = {f: 0 for f in catalog}
    family_count: dict[str, int] = {}

    for attr in attributions.values():
        seen_families = set()
        # attribution has final_weights dict
        fw = attr.get("final_weights", {})
        for factor_id, weight in fw.items():
            if factor_id in coverage_count and weight > 0.05:
                coverage_count[factor_id] += 1
                fam = catalog_to_family.get(factor_id)
                if fam and fam not in seen_families:
                    family_count[fam] = family_count.get(fam, 0) + 1
                    seen_families.add(fam)

    total = len(attributions)
    coverage_pct = {f: c / total for f, c in coverage_count.items()} if total > 0 else {}
    family_pct = {f: c / total for f, c in family_count.items()} if total > 0 else {}

    # Calculate high weight factors
    # For a factor f with coverage > 0.2, find median weight across runs where f is present in final_weights
    high_weight_factors = []
    for f, p in coverage_pct.items():
        if p > 0.2:
            weights = [attr.get("final_weights", {}).get(f, 0.0) for attr in attributions.values() if f in attr.get("final_weights", {})]
            high_weight_factors.append((f, median(weights)))

    return AttributionCoverageReport(
        total_attributions=total,
        coverage_by_factor=coverage_pct,
        coverage_by_family=family_pct,
        zero_coverage_factors=[f for f, p in coverage_pct.items() if p == 0],
        low_coverage_factors=[f for f, p in coverage_pct.items() if 0 < p < 0.05],
        high_weight_factors=high_weight_factors,
        catalog_loaded=catalog,
        catalog_used=[f for f, p in coverage_pct.items() if p > 0],
    )

def assert_attribution_health(report: AttributionCoverageReport, allow_sparse_ledger: bool = False):
    if report.total_attributions < 100:
        if allow_sparse_ledger:
            print(f"WARNING: Only {report.total_attributions} attributions completed. Need >=100. (Allowed due to allow_sparse_ledger)")
        else:
            raise InsufficientAttributionsError(
                f"Only {report.total_attributions} attributions completed. "
                f"Need >=100 before synthesis. Check Agent A funnel."
            )

    if report.zero_coverage_factors:
        if report.total_attributions < 50 or allow_sparse_ledger:
            print(f"WARNING: {len(report.zero_coverage_factors)} factors with zero coverage, "
                  f"but only {report.total_attributions} runs -- may be sample size. (Allowed due to allow_sparse_ledger)")
        else:
            raise CatalogLoadingError(
                f"With {report.total_attributions} runs, these factors never appeared: "
                f"{report.zero_coverage_factors}. Likely catalog-loading or seeding bug. "
                f"Verify priors in §8 reference these factor_ids correctly."
            )

    # Family-level check: each family should appear in some attributions
    expected_families = {
        "fundamental_delta", "quality_regime_change", "valuation_reset", "earnings_momentum",
        "analyst_dynamics", "smart_money", "narrative_sentiment", "macro_market_context",
    }
    missing_families = expected_families - set(report.coverage_by_family.keys())
    if missing_families:
        if report.total_attributions >= 100:
            raise CatalogLoadingError(
                f"These families never appeared in any attribution: {missing_families}. "
                f"Indicates the family is not loaded or denied for both priors."
            )
        else:
            print(f"WARNING: Missing families in attributions (total_attributions < 100): {missing_families}")
