#!/usr/bin/env python3
"""
Backtest Safety Stubs — Track B.2 + B.3 (Backtest Redesign, v8 candidate)
==========================================================================
Feature flags that the Track A simulator MUST honor to avoid look-ahead
bias and to support clean A/B ablation testing of already-integrated
factors.

TRACK B.2 — FORWARD ANALYST ESTIMATES
--------------------------------------
Status: already integrated in screener_v6.py (session 2026-04-20) via
        `get_analyst()` fetching `analyst-estimates`.

Problem: FMP exposes only the LATEST consensus per fiscal year — there
        is no historical "estimate as of 2023-06-15" endpoint. Using
        forward EPS in a historical backtest reads the 2026 consensus
        estimate into 2022 simulation: catastrophic look-ahead.

Required behavior in Track A:
  * LIVE code path: forward EPS contributes to the "upside" and
    "earnings" factors exactly as today.
  * BACKTEST code path: forward EPS is ZEROED OUT — the compute
    functions for `upside` and `earnings` must ignore it.

This module provides:
  * `BACKTEST_MODE`  — process-global feature flag (read by screener_v6
    and backtest_full when deciding which code path to take).
  * `EXCLUDED_IN_BACKTEST` — authoritative set of factor-fetch fields
    that must return None in backtest mode.
  * `guard_field(key, value)` — helper that returns `None` when in
    backtest mode and the key is in the excluded set; otherwise the
    value unchanged.

TRACK B.3 — SMART-MONEY CONCENTRATION BLEND (20%)
--------------------------------------------------
Status: already integrated in `get_institutional_flows()` (session
        2026-04-20), blending top-10 13F concentration at 20% weight
        into the institutional_flow score.

13F data has proper `filingDate` (45-day lag already honored) so it IS
backtest-safe. Track A should run TWO variants:

    Variant A: blend_pct = 0.20   (current production)
    Variant B: blend_pct = 0.00   (pure flow velocity, no concentration)

and compare OOS CAGR, Sharpe, max drawdown. If A beats B on at least
2 of the 3 metrics by a meaningful margin, keep the 20% blend. If not,
unblend.

This module provides:
  * `CONCENTRATION_BLEND_PCT` — configurable 0-1 multiplier for the
    concentration term inside `get_institutional_flows`.
  * `set_concentration_blend(pct)` — setter that Track A's sweep uses
    to toggle the blend per config.

USAGE (TRACK A SIMULATOR)
-------------------------
At the top of the backtest loop:

    from backtest_safety_stubs import set_backtest_mode
    set_backtest_mode(True)

Per-config sweep:

    from backtest_safety_stubs import set_concentration_blend
    for blend in [0.0, 0.20]:
        set_concentration_blend(blend)
        run_config(...)

USAGE (screener_v6.py)
----------------------
In `get_analyst()`, after fetching `analyst-estimates`:

    from backtest_safety_stubs import guard_field
    forward_eps = guard_field("forward_eps", forward_eps)

In `get_institutional_flows()`, where the concentration blend is applied:

    from backtest_safety_stubs import get_concentration_blend
    blend = get_concentration_blend()
    flow_score = velocity_score * (1 - blend) + concentration_score * blend
"""

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature-flag state
# ---------------------------------------------------------------------------

_BACKTEST_MODE = False
_CONCENTRATION_BLEND_PCT = 0.20    # default matches current production


# B.2 — Fields that must be None in backtest mode. Keep this set
# authoritative in ONE place; both screener_v6 and backtest_full import
# from here.
EXCLUDED_IN_BACKTEST = frozenset({
    # From get_analyst (analyst-estimates endpoint)
    "forward_eps",
    "forward_eps_yoy",
    "forward_revenue",
    "forward_revenue_yoy",
    # From get_analyst (price-target-consensus endpoint — latest-only)
    "price_target_consensus",
    "price_target_consensus_high",
    "price_target_consensus_low",
    # From ETF flow velocity (no historical data yet)
    "etf_flow_score",
    "etf_flow_delta_weight",
})


# ---------------------------------------------------------------------------
# B.2 — Backtest-mode field guards
# ---------------------------------------------------------------------------

def set_backtest_mode(on: bool) -> None:
    """Toggle backtest mode globally. Call once at start of backtest."""
    global _BACKTEST_MODE
    _BACKTEST_MODE = bool(on)
    log.info(f"  backtest_safety: BACKTEST_MODE = {_BACKTEST_MODE}")


def is_backtest_mode() -> bool:
    return _BACKTEST_MODE


def guard_field(key: str, value: Any) -> Any:
    """
    Return `value` unless we're in backtest mode AND `key` is in the
    excluded set, in which case return None.

    Usage example in screener_v6.py get_analyst():
        forward_eps = guard_field("forward_eps", forward_eps_raw)
    """
    if _BACKTEST_MODE and key in EXCLUDED_IN_BACKTEST:
        return None
    return value


def guard_dict(d: dict) -> dict:
    """
    Apply guard_field to every key in dict `d`. Returns a new dict with
    excluded fields set to None when in backtest mode.
    """
    if not _BACKTEST_MODE:
        return d
    return {k: (None if k in EXCLUDED_IN_BACKTEST else v) for k, v in d.items()}


# ---------------------------------------------------------------------------
# B.3 — Concentration blend A/B toggle
# ---------------------------------------------------------------------------

def set_concentration_blend(pct: float) -> None:
    """
    Set the top-10 13F concentration blend percentage (0.0 - 1.0).
    Default is 0.20 (current production).
    Track A's sweep toggles this per config: [0.00, 0.20].
    """
    global _CONCENTRATION_BLEND_PCT
    if not 0.0 <= pct <= 1.0:
        raise ValueError(f"blend must be in [0.0, 1.0], got {pct}")
    _CONCENTRATION_BLEND_PCT = float(pct)
    log.info(f"  backtest_safety: CONCENTRATION_BLEND_PCT = {pct:.2f}")


def get_concentration_blend() -> float:
    return _CONCENTRATION_BLEND_PCT


# ---------------------------------------------------------------------------
# B.3 — Helper to apply the blend inside get_institutional_flows
# ---------------------------------------------------------------------------

def apply_concentration_blend(
    velocity_score: Optional[float],
    concentration_score: Optional[float],
) -> Optional[float]:
    """
    Combine flow-velocity score and concentration score per the current
    blend setting. Returns None if velocity_score is None (the dominant
    signal is required; concentration alone is not enough).

    velocity_score: QoQ holder-count + net-shares flow score (0-1).
    concentration_score: top-10 13F holder concentration score (0-1).
    """
    if velocity_score is None:
        return None
    blend = _CONCENTRATION_BLEND_PCT
    if concentration_score is None or blend == 0.0:
        return velocity_score
    return round(velocity_score * (1.0 - blend) + concentration_score * blend, 4)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Default mode — nothing should be guarded
    assert guard_field("forward_eps", 2.41) == 2.41
    assert guard_field("price", 100.0) == 100.0

    # Enable backtest mode
    set_backtest_mode(True)
    assert guard_field("forward_eps", 2.41) is None
    assert guard_field("price", 100.0) == 100.0
    assert guard_dict({"forward_eps": 2.41, "price": 100.0}) == \
        {"forward_eps": None, "price": 100.0}

    set_backtest_mode(False)

    # Concentration blend
    set_concentration_blend(0.20)
    assert abs(apply_concentration_blend(0.80, 0.60) - 0.76) < 1e-6
    set_concentration_blend(0.00)
    assert apply_concentration_blend(0.80, 0.60) == 0.80
    set_concentration_blend(1.00)
    assert apply_concentration_blend(0.80, 0.60) == 0.60

    print("All backtest_safety_stubs unit checks PASSED")
