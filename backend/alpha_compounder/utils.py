"""
utils.py — PIT helpers, overlap resolution, and shared utilities.

All date-sensitive computations use PIT gating (filingDate ≤ as_of_date).
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PIT helpers
# ---------------------------------------------------------------------------

def latest_filed_before(statements: list[dict], as_of_date: str) -> Optional[dict]:
    """Return the most recent statement whose filingDate <= as_of_date.

    This is THE critical filter that prevents look-ahead.
    FMP returns filingDate as 'YYYY-MM-DD'. Lexicographic comparison works.
    """
    sorted_stmts = sorted(
        statements,
        key=lambda r: r.get("date", ""),
        reverse=True,
    )
    for row in sorted_stmts:
        filed = row.get("filingDate") or row.get("acceptedDate", "")[:10] or row.get("date", "")
        if filed and filed <= as_of_date:
            return row
    return None


def get_n_filed_before(statements: list[dict], as_of_date: str, n: int) -> list[dict]:
    """Return the N most recent statements filed before as_of_date."""
    sorted_stmts = sorted(
        statements,
        key=lambda r: r.get("date", ""),
        reverse=True,
    )
    result = []
    for row in sorted_stmts:
        filed = row.get("filingDate") or row.get("acceptedDate", "")[:10] or row.get("date", "")
        if filed and filed <= as_of_date:
            result.append(row)
            if len(result) >= n:
                break
    return result


# ---------------------------------------------------------------------------
# Growth computations
# ---------------------------------------------------------------------------

def safe_div(n: float, d: float) -> float:
    """Safe division, returns 0.0 on zero denominator."""
    return (n / d) if d else 0.0


def cagr(start_val: float, end_val: float, years: float) -> Optional[float]:
    """Compound annual growth rate. Returns None if inputs invalid."""
    if start_val <= 0 or end_val <= 0 or years <= 0:
        return None
    return (end_val / start_val) ** (1.0 / years) - 1.0


def yoy_delta(current: float, prior: float) -> Optional[float]:
    """Year-over-year growth rate. Returns None if prior is zero."""
    if prior == 0:
        return None
    return (current - prior) / abs(prior)


def acceleration(current_yoy: Optional[float], prior_yoy: Optional[float]) -> Optional[float]:
    """Growth acceleration = current_yoy - prior_yoy."""
    if current_yoy is None or prior_yoy is None:
        return None
    return current_yoy - prior_yoy


def trajectory_slope(values: list[float]) -> Optional[float]:
    """Simple linear regression slope over sequential values.
    Returns slope per period. Requires >= 3 values."""
    if len(values) < 3:
        return None
    n = len(values)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------

def resolve_overlaps(
    runs: list[dict],
    min_separation_days: int = 180,
) -> list[dict]:
    """Resolve overlapping runs for the same symbol.

    When two runs overlap or are within min_separation_days, prefer:
    1. Larger magnitude
    2. Longer duration (tiebreaker)

    Returns a non-overlapping subset.
    """
    if not runs:
        return []

    # Sort by magnitude descending, then duration descending
    sorted_runs = sorted(
        runs,
        key=lambda r: (-r.get("magnitude_pct", 0), -r.get("duration_days", 0)),
    )

    accepted = []
    for candidate in sorted_runs:
        c_start = candidate["t_start"]
        c_end = candidate["t_end"]

        overlaps = False
        for existing in accepted:
            if candidate.get("symbol") != existing.get("symbol"):
                continue

            e_start = existing["t_start"]
            e_end = existing["t_end"]

            # Check if runs overlap or are too close
            if isinstance(c_start, str):
                from datetime import datetime
                c_start_d = datetime.strptime(c_start, "%Y-%m-%d").date()
                c_end_d = datetime.strptime(c_end, "%Y-%m-%d").date()
                e_start_d = datetime.strptime(e_start, "%Y-%m-%d").date()
                e_end_d = datetime.strptime(e_end, "%Y-%m-%d").date()
            else:
                c_start_d, c_end_d = c_start, c_end
                e_start_d, e_end_d = e_start, e_end

            # Overlap or within separation window
            gap = max(
                (c_start_d - e_end_d).days,
                (e_start_d - c_end_d).days,
            )
            if gap < min_separation_days:
                overlaps = True
                break

        if not overlaps:
            accepted.append(candidate)

    return accepted


# ---------------------------------------------------------------------------
# Greedy trough-peak extraction
# ---------------------------------------------------------------------------

def greedy_trough_peak_pairs(
    prices: list[dict],
    min_magnitude: float,
    max_magnitude: float,
    min_duration_days: int,
    max_duration_days: int,
) -> list[dict]:
    """Extract (trough, peak) pairs from OHLCV data that match
    the given magnitude and duration bands.

    prices: list of dicts with 'date', 'close', 'adjClose' keys,
            sorted by date ascending.

    Returns list of candidate dicts with:
      t_start, t_end, trough_price, peak_price, magnitude_pct, duration_days
    """
    if not prices or len(prices) < 2:
        return []

    candidates = []
    n = len(prices)

    # Use adjClose for split-adjusted prices
    closes = []
    dates = []
    for p in prices:
        c = p.get("adjClose") or p.get("close", 0)
        if c and c > 0:
            closes.append(float(c))
            if "date_parsed" in p:
                d_val = p["date_parsed"]
            else:
                d_val = p["date"]
                if isinstance(d_val, str):
                    from datetime import datetime
                    d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                p["date_parsed"] = d_val
            dates.append(d_val)

    if len(closes) < 2:
        return []

    j_max = 0
    delta = timedelta(days=max_duration_days)

    # Greedy scan: for each potential trough, find the best peak
    for i in range(len(closes) - 1):
        trough_price = closes[i]
        t_start = dates[i]

        best_peak_price = trough_price
        best_peak_idx = i
        last_appended_peak_idx = -1

        # Slide j_max forward to the first index beyond max_duration_days
        max_date = t_start + delta
        while j_max < len(dates) and dates[j_max] <= max_date:
            j_max += 1

        for j in range(i + 1, j_max):
            if closes[j] > best_peak_price:
                best_peak_price = closes[j]
                best_peak_idx = j

                if best_peak_idx != last_appended_peak_idx:
                    peak_price = best_peak_price
                    t_end = dates[best_peak_idx]
                    duration = (t_end - t_start).days

                    if duration >= min_duration_days:
                        if duration <= max_duration_days:
                            magnitude = ((peak_price - trough_price) / trough_price) * 100
                            if min_magnitude <= magnitude <= max_magnitude:
                                candidates.append({
                                    "t_start": t_start,
                                    "t_end": t_end,
                                    "trough_price": trough_price,
                                    "peak_price": peak_price,
                                    "magnitude_pct": round(magnitude, 2),
                                    "duration_days": duration,
                                })
                                last_appended_peak_idx = best_peak_idx

    # Deduplicate: if two candidates share >50% overlap in time,
    # keep the one with higher magnitude
    if len(candidates) > 1:
        candidates.sort(key=lambda c: -c["magnitude_pct"])
        deduped = []
        for c in candidates:
            dominated = False
            for d in deduped:
                overlap = _time_overlap_pct(c, d)
                if overlap > 0.5:
                    dominated = True
                    break
            if not dominated:
                deduped.append(c)
        candidates = deduped

    # Convert dates back to string format for downstream consumption
    for c in candidates:
        c["t_start"] = str(c["t_start"])
        c["t_end"] = str(c["t_end"])

    return candidates


def _time_overlap_pct(a: dict, b: dict) -> float:
    """Fraction of A's time range that overlaps with B."""
    from datetime import datetime

    def to_date(s):
        return datetime.strptime(s, "%Y-%m-%d").date() if isinstance(s, str) else s

    a_start, a_end = to_date(a["t_start"]), to_date(a["t_end"])
    b_start, b_end = to_date(b["t_start"]), to_date(b["t_end"])

    overlap_start = max(a_start, b_start)
    overlap_end = min(a_end, b_end)

    if overlap_start >= overlap_end:
        return 0.0

    overlap_days = (overlap_end - overlap_start).days
    a_days = (a_end - a_start).days
    return overlap_days / max(a_days, 1)


# ---------------------------------------------------------------------------
# Kendall tau for convergence checking
# ---------------------------------------------------------------------------

def kendall_tau(ranking_a: list[str], ranking_b: list[str]) -> float:
    """Kendall tau-b rank correlation between two ordered lists of factor IDs.
    Returns value in [-1, 1] where 1 = identical ordering."""
    # Build position maps
    if not ranking_a or not ranking_b:
        return 0.0

    common = set(ranking_a) & set(ranking_b)
    if len(common) < 2:
        return 0.0

    # Filter to common elements, preserving order
    a = [x for x in ranking_a if x in common]
    b = [x for x in ranking_b if x in common]

    pos_b = {x: i for i, x in enumerate(b)}
    b_order = [pos_b[x] for x in a]

    # Count concordant and discordant pairs
    n = len(b_order)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if b_order[i] < b_order[j]:
                concordant += 1
            elif b_order[i] > b_order[j]:
                discordant += 1

    total = concordant + discordant
    if total == 0:
        return 1.0
    return (concordant - discordant) / total


def mean_kendall_tau(rankings: list[list[str]]) -> float:
    """Mean pairwise Kendall tau across a list of top-5 rankings."""
    if len(rankings) < 2:
        return 0.0

    taus = []
    for i in range(len(rankings)):
        for j in range(i + 1, len(rankings)):
            taus.append(kendall_tau(rankings[i], rankings[j]))

    return statistics.mean(taus) if taus else 0.0


# ---------------------------------------------------------------------------
# Max drawdown computation
# ---------------------------------------------------------------------------

def max_drawdown(closes: list[float]) -> float:
    """Compute max drawdown as a negative fraction (e.g., -0.18 = -18%).
    Returns 0.0 if no drawdown."""
    if not closes or len(closes) < 2:
        return 0.0

    peak = closes[0]
    mdd = 0.0
    for price in closes:
        if price > peak:
            peak = price
        dd = (price - peak) / peak  # negative
        if dd < mdd:
            mdd = dd
    return mdd
