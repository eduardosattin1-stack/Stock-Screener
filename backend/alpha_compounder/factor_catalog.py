"""
factor_catalog.py — Factor definitions (§7) with family gating.

Each factor maps to an FMP endpoint (or computation), a family, and a
compute function signature. The catalog is versioned — adding factors
does not invalidate existing attributions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class FactorDef:
    factor_id: str
    family: str
    description: str
    fmp_sources: list[str] = field(default_factory=list)
    requires_quarterly: bool = False
    requires_price_history: bool = False


# ---------------------------------------------------------------------------
# Family 1 — Fundamental delta (B-allowed, C-denied)
# ---------------------------------------------------------------------------

FUNDAMENTAL_DELTA = [
    FactorDef("revenue_yoy_acceleration", "fundamental_delta",
              "YoY revenue growth (T-0) − YoY revenue growth (T-12m)",
              ["income-statement"]),
    FactorDef("revenue_cagr_3yr", "fundamental_delta",
              "3-year revenue CAGR ending at most recent reported FY before t_start",
              ["income-statement"]),
    FactorDef("eps_yoy_acceleration", "fundamental_delta",
              "YoY EPS growth Δ",
              ["income-statement"]),
    FactorDef("eps_cagr_3yr", "fundamental_delta",
              "3-year diluted EPS CAGR",
              ["income-statement"]),
    FactorDef("fcf_yoy_acceleration", "fundamental_delta",
              "YoY FCF growth Δ",
              ["cash-flow-statement"]),
    FactorDef("fcf_cagr_3yr", "fundamental_delta",
              "3-year FCF CAGR",
              ["cash-flow-statement"]),
    FactorDef("gross_margin_delta_12m", "fundamental_delta",
              "Gross margin (T-0) − gross margin (T-12m), bps",
              ["income-statement"]),
    FactorDef("operating_margin_delta_12m", "fundamental_delta",
              "Operating margin Δ, bps",
              ["income-statement"]),
    FactorDef("net_margin_delta_12m", "fundamental_delta",
              "Net margin Δ, bps",
              ["income-statement"]),
    FactorDef("roic_trajectory", "fundamental_delta",
              "ROIC slope over last 4 reported FYs",
              ["key-metrics", "ratios"]),
    FactorDef("roe_trajectory", "fundamental_delta",
              "ROE slope over last 4 reported FYs",
              ["key-metrics", "ratios"]),
]

# ---------------------------------------------------------------------------
# Family 2 — Quality regime change (B-allowed, C-denied)
# ---------------------------------------------------------------------------

QUALITY_REGIME_CHANGE = [
    FactorDef("piotroski_delta_2yr", "quality_regime_change",
              "Piotroski F-Score Δ from 2 FYs prior",
              ["income-statement", "balance-sheet-statement", "cash-flow-statement"]),
    FactorDef("altman_z_delta_2yr", "quality_regime_change",
              "Altman Z Δ from 2 FYs prior",
              ["income-statement", "balance-sheet-statement"]),
    FactorDef("bvps_cagr_3yr", "quality_regime_change",
              "Book value per share 3-year CAGR",
              ["balance-sheet-statement"]),
    FactorDef("bvps_consistency", "quality_regime_change",
              "Std dev of YoY BVPS growth (lower = more consistent)",
              ["balance-sheet-statement"]),
    FactorDef("share_count_delta_3yr", "quality_regime_change",
              "Diluted share count Δ over 3 years (buyback indicator if negative)",
              ["income-statement"]),
]

# ---------------------------------------------------------------------------
# Family 3 — Valuation reset (B-allowed, C-denied)
# ---------------------------------------------------------------------------

VALUATION_RESET = [
    FactorDef("pe_at_t_start", "valuation_reset",
              "P/E at t_start",
              ["key-metrics"], requires_price_history=True),
    FactorDef("ps_at_t_start", "valuation_reset",
              "P/S at t_start",
              ["key-metrics"], requires_price_history=True),
    FactorDef("pb_at_t_start", "valuation_reset",
              "P/B at t_start",
              ["key-metrics"], requires_price_history=True),
    FactorDef("pfcf_at_t_start", "valuation_reset",
              "P/FCF at t_start",
              ["key-metrics"], requires_price_history=True),
    FactorDef("dcf_gap_at_t_start", "valuation_reset",
              "(FMP DCF − price) / price at t_start",
              ["discounted-cash-flow"], requires_price_history=True),
    FactorDef("owner_earnings_yield_at_t_start", "valuation_reset",
              "Owner earnings yield at t_start",
              ["income-statement", "cash-flow-statement"], requires_price_history=True),
    FactorDef("pe_multiple_expansion", "valuation_reset",
              "(P/E at t_end) / (P/E at t_start) − 1",
              ["key-metrics"], requires_price_history=True),
    FactorDef("acquirers_multiple", "valuation_reset",
              "Acquirers Multiple (EV / EBIT), penalty 100 if EBIT <= 0",
              ["key-metrics", "income-statement"]),
    FactorDef("epv_to_ev", "valuation_reset",
              "Earnings Power Value to Enterprise Value ratio",
              ["key-metrics", "income-statement"]),
    FactorDef("iv15_discount", "valuation_reset",
              "Discount to 15% hurdle rate intrinsic value",
              ["income-statement", "cash-flow-statement"], requires_price_history=True),
]

# ---------------------------------------------------------------------------
# Family 4 — Earnings momentum (B-allowed, C-denied)
# ---------------------------------------------------------------------------

EARNINGS_MOMENTUM = [
    FactorDef("eps_beats_last_4q", "earnings_momentum",
              "Count of EPS beats in 4 quarters before t_start (0-4)",
              ["earnings-surprises"], requires_quarterly=True),
    FactorDef("eps_surprise_magnitude_4q_avg", "earnings_momentum",
              "Average % surprise across last 4 quarters",
              ["earnings-surprises"], requires_quarterly=True),
    FactorDef("revenue_beat_streak", "earnings_momentum",
              "Consecutive revenue beats before t_start",
              ["earnings-surprises"], requires_quarterly=True),
    FactorDef("guidance_reaction_window", "earnings_momentum",
              "Avg 5-day return after last 4 earnings reports",
              ["earnings-surprises", "historical-price-eod/full"],
              requires_quarterly=True, requires_price_history=True),
]

# ---------------------------------------------------------------------------
# Family 5 — Analyst dynamics (C-allowed, B-denied)
# ---------------------------------------------------------------------------

ANALYST_DYNAMICS = [
    FactorDef("pt_revision_velocity_60d", "analyst_dynamics",
              "(PT consensus T-0) / (PT consensus T-60d) − 1",
              ["price-target-consensus"]),
    FactorDef("pt_revision_velocity_1y", "analyst_dynamics",
              "1-year PT revision velocity",
              ["price-target-consensus"]),
    FactorDef("upgrade_cluster_density_90d", "analyst_dynamics",
              "Count of upgrades − downgrades in 90 days before t_start",
              ["grades"]),
    FactorDef("eps_estimate_revision_breadth_60d", "analyst_dynamics",
              "% of analysts revising EPS up minus % revising down",
              ["analyst-estimates"]),
]

# ---------------------------------------------------------------------------
# Family 6 — Smart money (C-allowed, B-denied)
# ---------------------------------------------------------------------------

SMART_MONEY = [
    FactorDef("inst_holder_count_qoq", "smart_money",
              "13F holder count QoQ change in quarter before t_start",
              ["institutional-ownership/symbol-positions-summary"]),
    FactorDef("inst_holder_count_yoy", "smart_money",
              "Same, YoY",
              ["institutional-ownership/symbol-positions-summary"]),
    FactorDef("inst_shares_held_qoq", "smart_money",
              "13F total shares held QoQ Δ",
              ["institutional-ownership/symbol-positions-summary"]),
    FactorDef("insider_net_buy_ratio_6m", "smart_money",
              "(insider buys − sells) / total over 6 months pre t_start",
              ["insider-trading"]),
    FactorDef("congressional_trade_cluster", "smart_money",
              "Count of senate+house buys in 6 months pre t_start",
              ["senate-trades", "house-trades"]),
]

# ---------------------------------------------------------------------------
# Family 7 — Narrative / sentiment (C-allowed, B-denied)
# ---------------------------------------------------------------------------

NARRATIVE_SENTIMENT = [
    FactorDef("transcript_sentiment_delta_2q", "narrative_sentiment",
              "Claude-scored sentiment Δ across last 2 transcripts before t_start",
              ["earning-call-transcript"]),
    FactorDef("news_catalyst_keyword_score", "narrative_sentiment",
              "Keyword cluster score over [t_start-30d, t_start+7d]",
              ["stock-news"]),
    FactorDef("news_volume_anomaly", "narrative_sentiment",
              "News article count in 30d pre t_start vs trailing 12m average",
              ["stock-news"]),
]

# ---------------------------------------------------------------------------
# Family 8 — Macro / market context (C-allowed, B-denied)
# ---------------------------------------------------------------------------

MACRO_MARKET_CONTEXT = [
    FactorDef("regime_transition_during_run", "macro_market_context",
              "Boolean: did regime change during run",
              []),  # computed from macro_regime.py
    FactorDef("sector_momentum_concurrent", "macro_market_context",
              "Sector 60d return at t_start",
              ["sector-performance"]),
    FactorDef("sector_relative_strength_at_start", "macro_market_context",
              "Symbol's 60d return − sector 60d return at t_start",
              ["historical-price-eod/full", "sector-performance"]),
    FactorDef("vix_level_at_start", "macro_market_context",
              "VIX at t_start",
              ["historical-price-eod/full"]),
    FactorDef("yield_curve_slope_at_start", "macro_market_context",
              "10y − 2y at t_start",
              ["treasury-rates"]),
    FactorDef("style_rotation_signal", "macro_market_context",
              "Growth−Value spread Δ over 90d pre t_start",
              ["historical-price-eod/full"]),
    FactorDef("mom_26w", "macro_market_context",
              "26-week price momentum",
              ["historical-price-eod/full"], requires_price_history=True),
]


# ---------------------------------------------------------------------------
# Family 9 — Options / derivatives (C-allowed, B-denied; populated by Agent F)
# ---------------------------------------------------------------------------

OPTIONS_DERIVATIVES = [
    FactorDef("volume_to_oi_ratio", "options_derivatives",
              "Ratio of total options volume to total open interest on the scan date",
              ["options_historical"]),
]


# ---------------------------------------------------------------------------
# Full catalog
# ---------------------------------------------------------------------------

ALL_FACTORS: list[FactorDef] = (
    FUNDAMENTAL_DELTA
    + QUALITY_REGIME_CHANGE
    + VALUATION_RESET
    + EARNINGS_MOMENTUM
    + ANALYST_DYNAMICS
    + SMART_MONEY
    + NARRATIVE_SENTIMENT
    + MACRO_MARKET_CONTEXT
    + OPTIONS_DERIVATIVES
)

FACTOR_BY_ID: dict[str, FactorDef] = {f.factor_id: f for f in ALL_FACTORS}

FAMILY_FACTORS: dict[str, list[FactorDef]] = {}
for _f in ALL_FACTORS:
    FAMILY_FACTORS.setdefault(_f.family, []).append(_f)

# Family→agent access mapping
B_FAMILIES = {"fundamental_delta", "quality_regime_change",
              "valuation_reset", "earnings_momentum"}
C_FAMILIES = {"analyst_dynamics", "smart_money",
              "narrative_sentiment", "macro_market_context",
              "options_derivatives"}


def allowed_for_agent(agent: Literal["B", "C"], factor_id: str) -> bool:
    """Check if a factor is accessible to the given agent."""
    fdef = FACTOR_BY_ID.get(factor_id)
    if not fdef:
        return False
    families = B_FAMILIES if agent == "B" else C_FAMILIES
    return fdef.family in families


def get_available_factors(agent: Literal["B", "C"]) -> list[FactorDef]:
    """Return all factors accessible to the given agent."""
    families = B_FAMILIES if agent == "B" else C_FAMILIES
    return [f for f in ALL_FACTORS if f.family in families]
