#!/usr/bin/env python3
"""Moat durability / terminal-erosion classifier.

Shared by the screener (weekly_opus_refresh.value_input) and the regime post-processor
(_opus_debate/_regime_post.py). PURE computation over already-loaded JSON — no FMP fetch, no API key.

A SECOND family of teeth, ADDITIVE to (never replacing) the cyclical-peak/stale-anchor gates. Those
catch earnings at a cycle high or a stale post-event anchor; this catches a moat whose terminal value
is bleeding — a falling returns/margin franchise that is cheap because it is structurally shrinking.

Reuse-first: per-year series come from the scan's buffett_history.rows (revenue_mm/net_income_mm/
equity_mm) — so net-margin and ROE trends are ROIC/operating-margin PROXIES (ROE is leverage- and
buyback-distorted, hence used only as a corroborating trend, never alone), and gross_margin_trend is
reused from the scan. No new FMP fetch. The deterministic gate is intentionally CONSERVATIVE
(cap, never exclude): hard exclusion of a value-destroyer is delegated to the skeptic via
erosion_severity (a value-destroying name enters the skeptic as a default-REFUTE candidate).
"""

_MOAT_HURDLE = {  # rough after-tax cost-of-capital floor by broad GICS sector
    "technology": 0.10, "communication services": 0.09, "consumer cyclical": 0.09,
    "consumer defensive": 0.08, "healthcare": 0.09, "industrials": 0.09,
    "financial services": 0.08, "energy": 0.09, "utilities": 0.07, "real estate": 0.07,
    "basic materials": 0.09,
}


def _moat_hurdle(sector):
    return _MOAT_HURDLE.get((sector or "").strip().lower(), 0.09)


def _series_trend(series, rel=0.10):
    """Sign of the OLS slope across an evenly-spaced series, expressed as total change over the window
    relative to the mean level (unit-free). Returns rising | falling | stable | unknown."""
    pts = [x for x in series if isinstance(x, (int, float))]
    if len(pts) < 3:
        return "unknown"
    n = len(pts)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(pts) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((xs[i] - mx) * (pts[i] - my) for i in range(n)) / denom
    change = slope * (n - 1) / (abs(my) or 1.0)
    if change > rel:
        return "rising"
    if change < -rel:
        return "falling"
    return "stable"


def _moat_score(roic_frac, gm_trend, nm_trend, roe_trend, rev_trend, revenue_decel, roic_below):
    """Transparent 0-100 composite for display + risk/reward allocation (higher = more durable)."""
    sc = 50.0
    if isinstance(roic_frac, (int, float)):
        sc += min(max((roic_frac - 0.09) / 0.30, -0.5), 0.5) * 40  # ±20 by ROIC level vs hurdle band
    for t in (nm_trend, roe_trend):
        sc += {"rising": 7, "stable": 0, "falling": -9}.get(t, 0)
    sc += {"expanding": 8, "stable": 0, "eroding": -9}.get(gm_trend, 0)
    sc += {"rising": 4, "stable": 0, "falling": -6}.get(rev_trend, 0)
    if revenue_decel:
        sc -= 5
    if roic_below:
        sc -= 10
    return int(max(0, min(100, round(sc))))


def moat_features(u, s, r):
    """Compute deterministic moat-durability features + the cap-only erosion gate for one name.
    u = _radar_universe row, s = scan (latest_global) record, r = debate result. No new FMP fetch."""
    rows = [x for x in ((s.get("buffett_history") or {}).get("rows") or []) if isinstance(x, dict)][-6:]
    rev = [x.get("revenue_mm") for x in rows]
    ni = [x.get("net_income_mm") for x in rows]
    eq = [x.get("equity_mm") for x in rows]
    nm_series = [ni[i] / rev[i] for i in range(len(rows))
                 if isinstance(ni[i], (int, float)) and isinstance(rev[i], (int, float)) and rev[i] > 0]
    roe_series = [ni[i] / eq[i] for i in range(len(rows))
                  if isinstance(ni[i], (int, float)) and isinstance(eq[i], (int, float)) and eq[i] > 0]
    nm_trend = _series_trend(nm_series)
    roe_trend = _series_trend(roe_series)
    rev_trend = _series_trend([x for x in rev if isinstance(x, (int, float))])
    gm_raw = (s.get("gross_margin_trend") or u.get("gross_margin_trend") or "").strip().lower()
    gm_trend = {"expanding": "expanding", "contracting": "eroding", "stable": "stable"}.get(gm_raw, "unknown")

    roic = u.get("roic_avg")
    roic_frac = (roic / 100.0) if (isinstance(roic, (int, float)) and abs(roic) > 1.5) else roic  # tolerate pct
    hurdle = _moat_hurdle(r.get("sector", ""))
    roic_below = bool(isinstance(roic_frac, (int, float)) and roic_frac < hurdle)

    rev_yoy = u.get("revenue_yoy")
    rev_cagr = u.get("revenue_cagr_3y")
    revenue_decel = bool(
        (isinstance(rev_yoy, (int, float)) and isinstance(rev_cagr, (int, float))
         and rev_cagr > 0 and rev_yoy < rev_cagr * 0.5)
        or rev_trend == "falling"
    )

    margins_eroding = gm_trend == "eroding" or nm_trend == "falling"
    margins_expanding = gm_trend == "expanding" and nm_trend in ("rising", "stable")  # noqa: F841 (kept for clarity)
    returns_falling = roe_trend == "falling" or nm_trend == "falling"
    returns_rising = roe_trend == "rising" and nm_trend in ("rising", "stable")

    # CLEAN only when returns are rising, margins are not eroding, AND the franchise earns its keep.
    # A sub-cost-of-capital name can never auto-clean (that is the GLOB/CMCSA guard).
    clean = returns_rising and not margins_eroding and not roic_below
    cap = (not clean) and (
        returns_falling
        or (margins_eroding and revenue_decel)
        or (roic_below and (revenue_decel or margins_eroding))
    )
    erosion = "CAP" if cap else ""

    severity = "none"
    if erosion == "CAP":
        severity = "value-destroying" if (roic_below and returns_falling and margins_eroding) else "eroding"

    return {
        "moat_score": _moat_score(roic_frac, gm_trend, nm_trend, roe_trend, rev_trend, revenue_decel, roic_below),
        "moat_erosion": erosion,            # "" | "CAP"  — the deterministic teeth (0.5 size cap)
        "erosion_severity": severity,       # none | eroding | value-destroying  — skeptic priority signal
        "roic_level": round(roic_frac, 4) if isinstance(roic_frac, (int, float)) else None,
        "roic_below_hurdle": roic_below,
        "returns_trend": "falling" if returns_falling else ("rising" if returns_rising else "stable"),
        "net_margin_trend": nm_trend, "roe_trend": roe_trend,
        "gross_margin_trend": gm_trend, "revenue_trend": rev_trend,
        "revenue_decelerating": revenue_decel,
    }


# Back-compat alias (weekly_opus_refresh / tests historically referenced the underscore name).
_moat_features = moat_features
