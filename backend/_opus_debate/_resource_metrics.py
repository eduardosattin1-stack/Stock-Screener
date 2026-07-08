#!/usr/bin/env python3
"""Future Resources — deterministic margin-torque metrics (FUTURE_RESOURCES_SPEC.md §3).

No AISC endpoint exists on FMP; these are honest proxies computed from data Stage B of
fr_universe() already fetches (ttm_ebitda, ttm_revenue) plus one small additional live fetch
(commodity_beta_2y needs get_chart; gm_trajectory needs a 4y annual income-statement pull for the
two non-commodity chains). Reuse-first: weekly log-return resampling mirrors
_opus_debate/_value_post.py::weekly_logrets exactly (kept local here so this module has no
cross-import on a sibling post-processor — the _moat.py precedent for a standalone metrics module).

These are Director SCORING INPUTS, never a ranking that picks members (Do-NOT #2: deterministic
guards never pick). Non-commodity chains (robotics_automation, quantum) never get fcf_torque_10pct
or the cohort margin band — there is no spot price to be levered to; they get gm_trajectory instead
(the disruptor rubric's pricing-power lie detector, reused because it did real work there).
"""
import math
from datetime import datetime as _dt

# cohorts smaller than this fall back to fixed margin bands (percentiles are unstable on e.g.
# uranium's n~6-8 producer cohort)
MIN_COHORT_FOR_PERCENTILE = 8
FIXED_BANDS = [(0.45, "high>45%"), (0.25, "mid25-45%"), (float("-inf"), "low<25%")]


def ebitda_margin_band(ttm_ebitda, ttm_revenue, cohort_margins):
    """Cost-curve-position proxy: this name's EBITDA margin vs its chain cohort. Returns
    (margin, band_or_percentile_str) or (None, None) if inputs are unusable. `cohort_margins` is
    the list of EBITDA margins for every OTHER Lane A member sharing this name's primary chain
    (percentile is computed over that peer set, not the whole universe)."""
    if not isinstance(ttm_ebitda, (int, float)) or not isinstance(ttm_revenue, (int, float)) or ttm_revenue <= 0:
        return None, None
    margin = ttm_ebitda / ttm_revenue
    peers = [m for m in (cohort_margins or []) if isinstance(m, (int, float))]
    if len(peers) >= MIN_COHORT_FOR_PERCENTILE:
        pctile = round(100 * sum(1 for m in peers if m <= margin) / len(peers), 1)
        return round(margin, 4), f"p{pctile}"
    for floor, label in FIXED_BANDS:
        if margin > floor:
            return round(margin, 4), label
    return round(margin, 4), FIXED_BANDS[-1][1]


def fcf_torque_10pct(ttm_revenue, ttm_ebitda, commodity_revenue_share):
    """FCF-leverage proxy: incremental commodity price flows through at ~full incremental margin,
    so a +/-10% commodity move adds/subtracts ~10% * exposed-revenue from EBITDA. Symmetric — the
    Director must read this as downside torque too, not just upside. Commodity-chain names only
    (the caller never invokes this for robotics/quantum members)."""
    if not isinstance(ttm_revenue, (int, float)) or not isinstance(ttm_ebitda, (int, float)) or ttm_ebitda == 0:
        return None
    share = commodity_revenue_share if isinstance(commodity_revenue_share, (int, float)) else 1.0
    share = max(0.0, min(1.0, share))
    return round(100 * (0.10 * ttm_revenue * share) / abs(ttm_ebitda), 1)


def _weekly_logrets(chart):
    """Resample an ascending OHLCV chart to the last close of each ISO week -> {YYYY-WW: logret}.
    Local copy of _opus_debate/_value_post.py::weekly_logrets (kept dependency-light per the
    _moat.py precedent — this module imports no sibling post-processor)."""
    byweek = {}
    for row in chart or []:
        d, c = row.get("date"), (row.get("adjClose") or row.get("close"))
        if not d or not isinstance(c, (int, float)) or c <= 0:
            continue
        try:
            y, w, _ = _dt.strptime(d[:10], "%Y-%m-%d").isocalendar()
        except Exception:
            continue
        byweek[f"{y}-{w:02d}"] = c
    keys = sorted(byweek)
    return {keys[i]: math.log(byweek[keys[i]] / byweek[keys[i - 1]])
            for i in range(1, len(keys)) if byweek[keys[i - 1]] > 0}


def commodity_beta_2y(symbol, market_symbol, get_chart_fn):
    """Empirical cross-check on the torque proxy: regress 2y weekly log-returns of `symbol` vs
    `market_symbol` (the chain's commodity.fmp_symbol, or its proxy_etf when the commodity itself
    is off-FMP — e.g. URA for uranium, BOTZ/QTUM for the non-commodity chains as a factor-exposure
    read, clearly a proxy). Returns (beta, n_weeks) or (None, 0) on insufficient overlap.
    `get_chart_fn` is injected (symbol, days) -> chart-or-None, so this is unit-testable offline."""
    if not symbol or not market_symbol:
        return None, 0
    sym_r = _weekly_logrets(get_chart_fn(symbol, 760))
    mkt_r = _weekly_logrets(get_chart_fn(market_symbol, 760))
    common = sorted(set(sym_r) & set(mkt_r))
    if len(common) < 20:                       # too few overlapping weeks for a meaningful slope
        return None, len(common)
    xs = [mkt_r[k] for k in common]
    ys = [sym_r[k] for k in common]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    var = sum((x - mx) ** 2 for x in xs)
    if var <= 0:
        return None, len(common)
    return round(cov / var, 2), len(common)


_GM_CACHE_NAME = "_gm_trajectory_cache.json"


def gm_trajectory(symbol, fmp_income_statement_fn):
    """Non-commodity-chain metric (robotics_automation, quantum): gross-margin direction over the
    last up-to-4 fiscal years — the disruptor rubric's pricing-power lie detector (expanding GM on
    growing revenue = pricing power; compressing GM = commoditization), reused here because it did
    real work there and these two chains have no spot price to be levered to instead.
    `fmp_income_statement_fn` is injected: (symbol) -> list of annual income-statement rows
    (ascending-or-descending, most-recent-first assumed, each with revenue/grossProfit), or None.
    Returns (direction_str, margins_oldest_to_newest) or (None, []) if unusable."""
    rows = fmp_income_statement_fn(symbol) or []
    margins = []
    for r in rows[:4]:
        rev, gp = r.get("revenue"), r.get("grossProfit")
        if isinstance(rev, (int, float)) and rev > 0 and isinstance(gp, (int, float)):
            margins.append(round(gp / rev, 4))
    margins = list(reversed(margins))           # oldest -> newest
    if len(margins) < 2:
        return None, margins
    delta = margins[-1] - margins[0]
    if delta > 0.02:
        direction = f"expanding {margins[0]*100:.0f}%->{margins[-1]*100:.0f}% over {len(margins)-1}y"
    elif delta < -0.02:
        direction = f"compressing {margins[0]*100:.0f}%->{margins[-1]*100:.0f}% over {len(margins)-1}y"
    else:
        direction = f"flat ~{margins[-1]*100:.0f}% over {len(margins)-1}y"
    return direction, margins
