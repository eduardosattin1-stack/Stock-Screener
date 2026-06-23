"""
factor_service.py — Shared Factor Service for Agents B and C.

Single Python service. All factors PIT-gated by filingDate or equivalent
reception date. Agents never call FMP directly — they request factors
through the orchestrator, which delegates to this service.

Caches all computations so re-runs are deterministic for the factor side.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

# Add parent directory to path for existing module imports
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from alpha_compounder.factor_catalog import FACTOR_BY_ID, FactorDef
from alpha_compounder.schemas import FactorResult, TimeSlice
from alpha_compounder.utils import (
    acceleration,
    cagr,
    get_n_filed_before,
    latest_filed_before,
    safe_div,
    trajectory_slope,
    yoy_delta,
)

log = logging.getLogger(__name__)


class FactorService:
    """Compute any requested factor from FMP data, PIT-gated.

    The same service is used by both Agent B and Agent C.
    Family gating is enforced by the orchestrator, not here.
    """

    def __init__(self, fmp_func, rate_limit_func=None):
        """
        Args:
            fmp_func: The FMP API caller (screener_v6.fmp or equivalent).
            rate_limit_func: Optional sleep function for rate limiting.
        """
        self.fmp = fmp_func
        self.sleep = rate_limit_func or (lambda: None)
        self._cache: dict[str, FactorResult] = {}

    def compute(
        self,
        run_id: str,
        factor_id: str,
        symbol: str,
        t_start: str,
        t_end: str,
        params: dict | None = None,
        time_slice: TimeSlice = TimeSlice.PRIMING,
        sector: str = "",
    ) -> Optional[FactorResult]:
        """Compute a factor for a given run.

        Returns FactorResult or None if computation fails.
        """
        cache_key = f"{run_id}:{factor_id}:{time_slice.value}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        fdef = FACTOR_BY_ID.get(factor_id)
        if not fdef:
            log.warning(f"Unknown factor_id: {factor_id}")
            return None

        params = params or {}

        # Determine the as_of_date based on time_slice
        if time_slice == TimeSlice.BASELINE:
            as_of = t_start
        elif time_slice == TimeSlice.PRIMING:
            as_of = t_start
        else:  # CONCURRENT
            as_of = t_end

        try:
            result = self._dispatch(
                fdef, run_id, symbol, t_start, t_end,
                as_of, params, time_slice, sector,
            )
        except Exception as e:
            log.warning(f"Factor compute failed: {factor_id} for {symbol}: {e}")
            return None

        if result:
            self._cache[cache_key] = result

        return result

    # ------------------------------------------------------------------
    # Dispatch to family-specific compute functions
    # ------------------------------------------------------------------

    def _dispatch(
        self, fdef: FactorDef, run_id: str, symbol: str,
        t_start: str, t_end: str, as_of: str,
        params: dict, time_slice: TimeSlice, sector: str,
    ) -> Optional[FactorResult]:
        """Route to the appropriate compute function."""

        compute_fn = _COMPUTE_REGISTRY.get(fdef.factor_id)
        if not compute_fn:
            log.debug(f"No compute function for {fdef.factor_id} (stub)")
            return None

        raw_value, confidence, pit_dates = compute_fn(
            self, symbol, as_of, t_start, t_end, params,
        )

        if raw_value is None:
            return None

        return FactorResult(
            factor_id=fdef.factor_id,
            run_id=run_id,
            time_slice=time_slice,
            params=params,
            raw_value=raw_value,
            confidence=confidence,
            pit_filing_dates_used=pit_dates,
            # sector_zscore and regime_zscore populated later by cohort comparison
        )

    # ------------------------------------------------------------------
    # Data fetchers (PIT-gated)
    # ------------------------------------------------------------------

    def _fetch_income_statements(self, symbol: str, limit: int = 10) -> list[dict]:
        """Fetch annual income statements."""
        data = self.fmp("income-statement", {
            "symbol": symbol, "period": "annual", "limit": limit,
        })
        self.sleep()
        return data or []

    def _fetch_balance_sheets(self, symbol: str, limit: int = 10) -> list[dict]:
        """Fetch annual balance sheet statements."""
        data = self.fmp("balance-sheet-statement", {
            "symbol": symbol, "period": "annual", "limit": limit,
        })
        self.sleep()
        return data or []

    def _fetch_cash_flows(self, symbol: str, limit: int = 10) -> list[dict]:
        """Fetch annual cash flow statements."""
        data = self.fmp("cash-flow-statement", {
            "symbol": symbol, "period": "annual", "limit": limit,
        })
        self.sleep()
        return data or []

    def _fetch_key_metrics(self, symbol: str, limit: int = 10) -> list[dict]:
        """Fetch key metrics."""
        data = self.fmp("key-metrics", {
            "symbol": symbol, "period": "annual", "limit": limit,
        })
        self.sleep()
        return data or []

    def _fetch_ratios(self, symbol: str, limit: int = 10) -> list[dict]:
        """Fetch financial ratios."""
        data = self.fmp("ratios", {
            "symbol": symbol, "period": "annual", "limit": limit,
        })
        self.sleep()
        return data or []

    def _fetch_earnings_surprises(self, symbol: str) -> list[dict]:
        """Fetch earnings surprises."""
        data = self.fmp("earnings-surprises", {"symbol": symbol})
        self.sleep()
        return data or []

    def _fetch_price_history(self, symbol: str, from_date: str, to_date: str) -> list[dict]:
        """Fetch OHLCV price history."""
        data = self.fmp("historical-price-eod/full", {
            "symbol": symbol, "from": from_date, "to": to_date,
        })
        self.sleep()
        return data or []

    def _fetch_grades(self, symbol: str) -> list[dict]:
        """Fetch analyst grade changes."""
        data = self.fmp("grades", {"symbol": symbol})
        self.sleep()
        return data or []

    def _fetch_institutional(self, symbol: str) -> list[dict]:
        """Fetch 13F institutional ownership."""
        data = self.fmp("institutional-ownership/symbol-positions-summary", {
            "symbol": symbol,
        })
        self.sleep()
        return data or []

    def _fetch_insider_trading(self, symbol: str) -> list[dict]:
        """Fetch insider trading data."""
        data = self.fmp("insider-trading", {"symbol": symbol})
        self.sleep()
        return data or []

    def _fetch_options_data(self, symbol: str) -> Any | None:
        """Fetch historical options data from ThetaData parquet cache."""
        import pandas as pd
        cache_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "Cache_Data", "Theta_Historical"
        )
        file_path = os.path.join(cache_dir, f"{symbol}_theta.parquet")
        if not os.path.exists(file_path):
            return None
        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                return None
            df['scan_date'] = pd.to_datetime(df['scan_date'])
            return df
        except Exception as e:
            log.warning(f"Error loading options data for {symbol}: {e}")
            return None



# ---------------------------------------------------------------------------
# Compute functions registry
# ---------------------------------------------------------------------------
# Each function signature:
#   fn(service, symbol, as_of, t_start, t_end, params)
#   -> (raw_value, confidence, pit_dates_used)
# ---------------------------------------------------------------------------

def _compute_revenue_yoy_acceleration(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 3)
    if len(filed) < 3:
        return None, 0, []
    rev = [s.get("revenue", 0) for s in filed]
    yoy_0 = yoy_delta(rev[0], rev[1])
    yoy_1 = yoy_delta(rev[1], rev[2])
    acc = acceleration(yoy_0, yoy_1)
    if acc is None:
        return None, 0, []
    pit = [s.get("filingDate", "") for s in filed]
    return round(acc, 4), 1.0, pit


def _compute_revenue_cagr_3yr(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 4)
    if not filed:
        return None, 0, []
    rev_end = filed[0].get("revenue", 0) or 0
    if len(filed) >= 4:
        rev_start = filed[3].get("revenue", 0) or 0
        years = 3.0
        start_idx = 3
    elif len(filed) >= 3:
        rev_start = filed[2].get("revenue", 0) or 0
        years = 2.0
        start_idx = 2
    elif len(filed) >= 2:
        rev_start = filed[1].get("revenue", 0) or 0
        years = 1.0
        start_idx = 1
    else:
        return None, 0, []
    c = cagr(rev_start, rev_end, years)
    if c is None:
        return None, 0, []
    pit = [filed[0].get("filingDate", ""), filed[start_idx].get("filingDate", "")]
    return round(c, 4), 1.0, pit


def _compute_eps_yoy_acceleration(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 3)
    if len(filed) < 3:
        return None, 0, []
    eps = [s.get("epsdiluted", 0) for s in filed]
    yoy_0 = yoy_delta(eps[0], eps[1])
    yoy_1 = yoy_delta(eps[1], eps[2])
    acc = acceleration(yoy_0, yoy_1)
    if acc is None:
        return None, 0, []
    pit = [s.get("filingDate", "") for s in filed]
    return round(acc, 4), 1.0, pit


def _compute_eps_cagr_3yr(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 4)
    if not filed:
        return None, 0, []
    eps_end = filed[0].get("epsdiluted", 0) or filed[0].get("eps", 0) or 0
    if len(filed) >= 4:
        eps_start = filed[3].get("epsdiluted", 0) or filed[3].get("eps", 0) or 0
        years = 3.0
        start_idx = 3
    elif len(filed) >= 3:
        eps_start = filed[2].get("epsdiluted", 0) or filed[2].get("eps", 0) or 0
        years = 2.0
        start_idx = 2
    elif len(filed) >= 2:
        eps_start = filed[1].get("epsdiluted", 0) or filed[1].get("eps", 0) or 0
        years = 1.0
        start_idx = 1
    else:
        return None, 0, []
    c = cagr(abs(eps_start), abs(eps_end), years)
    if c is None:
        return None, 0, []
    if eps_start < 0 and eps_end > 0:
        c = abs(c)  # turnaround
    elif eps_start > 0 and eps_end < 0:
        c = -abs(c)
    pit = [filed[0].get("filingDate", ""), filed[start_idx].get("filingDate", "")]
    return round(c, 4), 1.0, pit


def _compute_fcf_yoy_acceleration(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_cash_flows(symbol)
    filed = get_n_filed_before(stmts, as_of, 3)
    if len(filed) < 3:
        return None, 0, []
    fcf = [s.get("freeCashFlow", 0) for s in filed]
    yoy_0 = yoy_delta(fcf[0], fcf[1])
    yoy_1 = yoy_delta(fcf[1], fcf[2])
    acc = acceleration(yoy_0, yoy_1)
    if acc is None:
        return None, 0, []
    pit = [s.get("filingDate", "") for s in filed]
    return round(acc, 4), 1.0, pit


def _compute_fcf_cagr_3yr(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_cash_flows(symbol)
    filed = get_n_filed_before(stmts, as_of, 4)
    if not filed:
        return None, 0, []
    fcf_end = filed[0].get("freeCashFlow", 0) or 0
    if len(filed) >= 4:
        fcf_start = filed[3].get("freeCashFlow", 0) or 0
        years = 3.0
        start_idx = 3
    elif len(filed) >= 3:
        fcf_start = filed[2].get("freeCashFlow", 0) or 0
        years = 2.0
        start_idx = 2
    elif len(filed) >= 2:
        fcf_start = filed[1].get("freeCashFlow", 0) or 0
        years = 1.0
        start_idx = 1
    else:
        return None, 0, []
    c = cagr(max(fcf_start, 1), max(fcf_end, 1), years)
    if c is None:
        return None, 0, []
    pit = [filed[0].get("filingDate", ""), filed[start_idx].get("filingDate", "")]
    return round(c, 4), 1.0, pit


def _compute_gross_margin_delta_12m(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 2)
    if len(filed) < 2:
        return None, 0, []
    gm_0 = safe_div(filed[0].get("grossProfit", 0), filed[0].get("revenue", 1))
    gm_1 = safe_div(filed[1].get("grossProfit", 0), filed[1].get("revenue", 1))
    delta_bps = (gm_0 - gm_1) * 10000
    pit = [s.get("filingDate", "") for s in filed]
    return round(delta_bps, 1), 1.0, pit


def _compute_operating_margin_delta_12m(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 2)
    if len(filed) < 2:
        return None, 0, []
    om_0 = safe_div(filed[0].get("operatingIncome", 0), filed[0].get("revenue", 1))
    om_1 = safe_div(filed[1].get("operatingIncome", 0), filed[1].get("revenue", 1))
    delta_bps = (om_0 - om_1) * 10000
    pit = [s.get("filingDate", "") for s in filed]
    return round(delta_bps, 1), 1.0, pit


def _compute_net_margin_delta_12m(svc, symbol, as_of, t_start, t_end, params):
    stmts = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(stmts, as_of, 2)
    if len(filed) < 2:
        return None, 0, []
    nm_0 = safe_div(filed[0].get("netIncome", 0), filed[0].get("revenue", 1))
    nm_1 = safe_div(filed[1].get("netIncome", 0), filed[1].get("revenue", 1))
    delta_bps = (nm_0 - nm_1) * 10000
    pit = [s.get("filingDate", "") for s in filed]
    return round(delta_bps, 1), 1.0, pit


def _compute_roic_trajectory(svc, symbol, as_of, t_start, t_end, params):
    metrics = svc._fetch_key_metrics(symbol)
    filed = get_n_filed_before(metrics, as_of, 4)
    if len(filed) < 3:
        return None, 0, []
    roics = [s.get("returnOnCapitalEmployed", 0) or 0 for s in reversed(filed)]
    slope = trajectory_slope(roics)
    if slope is None:
        return None, 0, []
    pit = [s.get("filingDate", "") for s in filed]
    return round(slope, 4), 1.0, pit


def _compute_roe_trajectory(svc, symbol, as_of, t_start, t_end, params):
    metrics = svc._fetch_key_metrics(symbol)
    filed = get_n_filed_before(metrics, as_of, 4)
    if len(filed) < 3:
        return None, 0, []
    roes = [s.get("returnOnEquity", 0) or 0 for s in reversed(filed)]
    slope = trajectory_slope(roes)
    if slope is None:
        return None, 0, []
    pit = [s.get("filingDate", "") for s in filed]
    return round(slope, 4), 1.0, pit


def _compute_piotroski_delta_2yr(svc, symbol, as_of, t_start, t_end, params):
    from fundamental_scores_pit import compute_piotroski_pit
    inc = svc._fetch_income_statements(symbol)
    bal = svc._fetch_balance_sheets(symbol)
    cf = svc._fetch_cash_flows(symbol)
    p_now, _ = compute_piotroski_pit(inc, bal, cf, as_of)
    # 2 years prior
    two_yr = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=730)).strftime("%Y-%m-%d")
    p_then, _ = compute_piotroski_pit(inc, bal, cf, two_yr)
    if p_now is None or p_then is None:
        return None, 0, []
    return float(p_now - p_then), 1.0, [as_of, two_yr]


def _compute_eps_beats_last_4q(svc, symbol, as_of, t_start, t_end, params):
    surprises = svc._fetch_earnings_surprises(symbol)
    if not surprises:
        return None, 0, []
    # Filter to before as_of, take last 4
    valid = [s for s in surprises if (s.get("date", "") or "") <= as_of]
    valid.sort(key=lambda s: s.get("date", ""), reverse=True)
    last_4 = valid[:4]
    if len(last_4) < 4:
        return None, 0.5, []
    beats = sum(1 for s in last_4 if (s.get("actualEarningResult", 0) or 0) >
                (s.get("estimatedEarning", 0) or 0))
    return float(beats), 1.0, [s.get("date", "") for s in last_4]


def _compute_eps_surprise_magnitude_4q_avg(svc, symbol, as_of, t_start, t_end, params):
    surprises = svc._fetch_earnings_surprises(symbol)
    if not surprises:
        return None, 0, []
    valid = [s for s in surprises if (s.get("date", "") or "") <= as_of]
    valid.sort(key=lambda s: s.get("date", ""), reverse=True)
    last_4 = valid[:4]
    if len(last_4) < 4:
        return None, 0.5, []
    magnitudes = []
    for s in last_4:
        est = s.get("estimatedEarning", 0) or 0
        act = s.get("actualEarningResult", 0) or 0
        if est != 0:
            magnitudes.append((act - est) / abs(est) * 100)
    if not magnitudes:
        return None, 0, []
    avg = sum(magnitudes) / len(magnitudes)
    return round(avg, 2), 1.0, [s.get("date", "") for s in last_4]


def _compute_pe_at_t_start(svc, symbol, as_of, t_start, t_end, params):
    ratios = svc._fetch_ratios(symbol)
    filed = latest_filed_before(ratios, as_of)
    if not filed:
        km = svc._fetch_key_metrics(symbol)
        filed_km = latest_filed_before(km, as_of)
        if not filed_km:
            return None, 0, []
        pe = filed_km.get("peRatio", 0) or 0
        pit_date = filed_km.get("filingDate") or filed_km.get("date", "")
    else:
        pe = filed.get("priceToEarningsRatio", 0) or 0
        pit_date = filed.get("filingDate") or filed.get("date", "")
    if pe <= 0 or pe > 1000:
        return None, 0.5, []
    return round(pe, 2), 1.0, [pit_date]


def _compute_ps_at_t_start(svc, symbol, as_of, t_start, t_end, params):
    ratios = svc._fetch_ratios(symbol)
    filed = latest_filed_before(ratios, as_of)
    if not filed:
        km = svc._fetch_key_metrics(symbol)
        filed_km = latest_filed_before(km, as_of)
        if not filed_km:
            return None, 0, []
        ps = filed_km.get("priceToSalesRatio", 0) or 0
        pit_date = filed_km.get("filingDate") or filed_km.get("date", "")
    else:
        ps = filed.get("priceToSalesRatio", 0) or 0
        pit_date = filed.get("filingDate") or filed.get("date", "")
    if ps <= 0:
        return None, 0.5, []
    return round(ps, 2), 1.0, [pit_date]


def _compute_inst_holder_count_qoq(svc, symbol, as_of, t_start, t_end, params):
    inst = svc._fetch_institutional(symbol)
    if not inst or len(inst) < 2:
        return None, 0, []
    # Sort by date descending, filter to before as_of
    valid = sorted(
        [i for i in inst if (i.get("date", "") or "") <= as_of],
        key=lambda i: i.get("date", ""),
        reverse=True,
    )
    if len(valid) < 2:
        return None, 0, []
    count_now = valid[0].get("investorsHolding", 0) or 0
    count_prev = valid[1].get("investorsHolding", 0) or 0
    if count_prev == 0:
        return None, 0, []
    delta = (count_now - count_prev) / count_prev
    return round(delta, 4), 1.0, [valid[0].get("date", ""), valid[1].get("date", "")]


def _compute_insider_net_buy_ratio_6m(svc, symbol, as_of, t_start, t_end, params):
    trades = svc._fetch_insider_trading(symbol)
    if not trades:
        return None, 0, []
    cutoff = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=180)).strftime("%Y-%m-%d")
    recent = [t for t in trades if cutoff <= (t.get("filingDate", "") or "") <= as_of]
    if not recent:
        return None, 0, []
    buys = sum(1 for t in recent if (t.get("transactionType", "") or "").lower() in
               ("p-purchase", "purchase", "a-award"))
    sells = sum(1 for t in recent if (t.get("transactionType", "") or "").lower() in
                ("s-sale", "sale", "d-disposition"))
    total = buys + sells
    if total == 0:
        return None, 0, []
    ratio = (buys - sells) / total
    return round(ratio, 4), 1.0, [cutoff, as_of]


def _compute_upgrade_cluster_density_90d(svc, symbol, as_of, t_start, t_end, params):
    grades = svc._fetch_grades(symbol)
    if not grades:
        return None, 0, []
    cutoff = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    recent = [g for g in grades if cutoff <= (g.get("date", "") or "") <= as_of]
    upgrades = sum(1 for g in recent if (g.get("newGrade", "") or "").lower() in
                   ("buy", "outperform", "overweight", "strong buy"))
    downgrades = sum(1 for g in recent if (g.get("newGrade", "") or "").lower() in
                     ("sell", "underperform", "underweight", "strong sell"))
    return float(upgrades - downgrades), 1.0, [cutoff, as_of]


def _compute_vix_level_at_start(svc, symbol, as_of, t_start, t_end, params):
    vix = svc._fetch_price_history("^VIX", t_start, t_start)
    if not vix:
        return None, 0, []
    close = vix[0].get("close", 0) if vix else 0
    return round(float(close), 2), 1.0, [t_start]


def _compute_yield_curve_slope_at_start(svc, symbol, as_of, t_start, t_end, params):
    rates = svc.fmp("treasury-rates", {"from": t_start, "to": t_start})
    if not rates:
        return None, 0, []
    r = rates[0] if rates else {}
    y10 = r.get("year10", 0) or 0
    y2 = r.get("year2", 0) or 0
    spread_bp = (y10 - y2) * 100
    return round(spread_bp, 1), 1.0, [t_start]


def _compute_acquirers_multiple(svc, symbol, as_of, t_start, t_end, params):
    km_stmts = svc._fetch_key_metrics(symbol)
    km_filed = get_n_filed_before(km_stmts, as_of, 1)
    if not km_filed:
        return None, 0, []
    latest_km = km_filed[0]
    ev = latest_km.get("enterpriseValue", 0) or 0
    
    inc_stmts = svc._fetch_income_statements(symbol)
    inc_filed = get_n_filed_before(inc_stmts, as_of, 1)
    if not inc_filed:
        return None, 0, []
    latest_inc = inc_filed[0]
    ebit = latest_inc.get("ebit", 0) or 0
    
    val = safe_div(ev, ebit) if ebit > 0 else 100.0
    pit = [latest_km.get("filingDate") or latest_km.get("date", ""), latest_inc.get("filingDate") or latest_inc.get("date", "")]
    return round(val, 4), 1.0, pit


def _compute_epv_to_ev(svc, symbol, as_of, t_start, t_end, params):
    km_stmts = svc._fetch_key_metrics(symbol)
    km_filed = get_n_filed_before(km_stmts, as_of, 1)
    if not km_filed:
        return None, 0, []
    latest_km = km_filed[0]
    ev = latest_km.get("enterpriseValue", 0) or 0
    if ev <= 0:
        return None, 0, []

    inc_stmts = svc._fetch_income_statements(symbol)
    inc_filed = get_n_filed_before(inc_stmts, as_of, 1)
    if not inc_filed:
        return None, 0, []
    latest_inc = inc_filed[0]
    ebit = latest_inc.get("ebit", 0) or 0
    tax_expense = latest_inc.get('incomeTaxExpense', 0) or 0
    pre_tax = latest_inc.get('incomeBeforeTax', 1) or 1
    
    tax_rate = max(0.0, min(0.35, safe_div(tax_expense, pre_tax)))
    epv = safe_div(ebit * (1.0 - tax_rate), 0.10)
    
    val = safe_div(epv, ev)
    pit = [latest_km.get("filingDate") or latest_km.get("date", ""), latest_inc.get("filingDate") or latest_inc.get("date", "")]
    return round(val, 4), 1.0, pit


def _compute_iv15_discount(svc, symbol, as_of, t_start, t_end, params):
    inc_stmts = svc._fetch_income_statements(symbol)
    inc_filed = get_n_filed_before(inc_stmts, as_of, 4)
    if not inc_filed:
        return None, 0, []
    latest_inc = inc_filed[0]
    shares = latest_inc.get("weightedAverageShsOut", 0) or 0
    if shares <= 0:
        return None, 0, []

    cf_stmts = svc._fetch_cash_flows(symbol)
    cf_filed = get_n_filed_before(cf_stmts, as_of, 1)
    if not cf_filed:
        return None, 0, []
    fcf = cf_filed[0].get("freeCashFlow", 0) or 0
    if fcf <= 0:
        return None, 0, []

    eps_end = inc_filed[0].get("eps", 0) or 0
    if len(inc_filed) >= 4:
        eps_start = inc_filed[3].get("eps", 0) or 0
        n_years = 3.0
    elif len(inc_filed) >= 3:
        eps_start = inc_filed[2].get("eps", 0) or 0
        n_years = 2.0
    elif len(inc_filed) >= 2:
        eps_start = inc_filed[1].get("eps", 0) or 0
        n_years = 1.0
    else:
        eps_start = eps_end
        n_years = 1.0

    if eps_start != 0 and eps_end > eps_start:
        eps_growth_3y = safe_div(eps_end - eps_start, abs(eps_start)) / n_years
    else:
        eps_growth_3y = 0.05

    g = max(0.0, min(20.0, eps_growth_3y * 100)) if eps_growth_3y > 0 else 5.0
    g_blend = min(0.40, max(0.02, g / 100.0))
    terminal_mult = min(20.0, max(8.0, g_blend * 100 * 2))
    terminal_fcf = fcf * ((1 + g_blend) ** 15)
    terminal_mcap = terminal_fcf * terminal_mult
    iv15_val = safe_div(terminal_mcap, shares * 8.137)
    
    prices = svc._fetch_price_history(symbol, as_of, as_of)
    if not prices:
        from datetime import datetime, timedelta
        as_of_dt = datetime.strptime(as_of, "%Y-%m-%d")
        start_p = (as_of_dt - timedelta(days=5)).strftime("%Y-%m-%d")
        prices = svc._fetch_price_history(symbol, start_p, as_of)
    if not prices:
        return None, 0, []
    prices_sorted = sorted(prices, key=lambda p: p.get("date", ""), reverse=True)
    current_price = float(prices_sorted[0].get("adjClose") or prices_sorted[0].get("close", 0))
    if current_price <= 0 or iv15_val <= 0:
        return None, 0, []

    val = safe_div(current_price, iv15_val)
    pit = [latest_inc.get("filingDate") or latest_inc.get("date", ""), cf_filed[0].get("filingDate") or cf_filed[0].get("date", ""), prices_sorted[0].get("date", "")]
    return round(val, 4), 1.0, pit


def _compute_mom_26w(svc, symbol, as_of, t_start, t_end, params):
    from datetime import datetime, timedelta
    as_of_dt = datetime.strptime(as_of, "%Y-%m-%d")
    start_date = (as_of_dt - timedelta(days=182)).strftime("%Y-%m-%d")
    prices = svc._fetch_price_history(symbol, start_date, as_of)
    if not prices or len(prices) < 5:
        return None, 0, []
    prices_sorted = sorted(prices, key=lambda p: p.get("date", ""))
    p_start = float(prices_sorted[0].get("adjClose") or prices_sorted[0].get("close", 0))
    p_end = float(prices_sorted[-1].get("adjClose") or prices_sorted[-1].get("close", 0))
    if p_start <= 0:
        return None, 0, []
    mom = (p_end - p_start) / p_start
    pit = [prices_sorted[0].get("date", ""), prices_sorted[-1].get("date", "")]
    return round(mom, 4), 1.0, pit


def _compute_volume_to_oi_ratio(svc, symbol, as_of, t_start, t_end, params):
    import pandas as pd
    df = svc._fetch_options_data(symbol)
    if df is None or df.empty:
        return None, 0.0, []

    as_of_dt = pd.to_datetime(as_of)
    unique_dates = df['scan_date'].unique()
    if len(unique_dates) == 0:
        return None, 0.0, []

    closest_date = min(unique_dates, key=lambda d: abs(d - as_of_dt))
    if abs(closest_date - as_of_dt).days > 5:
        return None, 0.0, []

    day_df = df[df['scan_date'] == closest_date]
    if day_df.empty:
        return None, 0.0, []

    total_oi_today = float(day_df['open_interest'].sum())
    total_volume_today = float(day_df['volume'].sum())
    if total_oi_today > 0:
        volume_to_oi = float(total_volume_today / total_oi_today)
        return round(volume_to_oi, 4), 1.0, [closest_date.strftime("%Y-%m-%d")]
    else:
        return None, 0.0, []


def get_price_on_date(svc, symbol, date_str):
    from datetime import datetime, timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    start = (dt - timedelta(days=5)).strftime("%Y-%m-%d")
    prices = svc._fetch_price_history(symbol, start, date_str)
    if not prices:
        return 0.0
    prices_sorted = sorted(prices, key=lambda p: p.get("date", ""))
    return float(prices_sorted[-1].get("adjClose") or prices_sorted[-1].get("close", 0))


def std_dev(lst):
    n = len(lst)
    if n <= 1:
        return 0.0
    mean = sum(lst) / n
    variance = sum((x - mean) ** 2 for x in lst) / (n - 1)
    return variance ** 0.5


def _compute_altman_z_delta_2yr(svc, symbol, as_of, t_start, t_end, params):
    from fundamental_scores_pit import compute_altman_z_pit
    
    inc = svc._fetch_income_statements(symbol)
    bal = svc._fetch_balance_sheets(symbol)
    if not inc or not bal:
        return None, 0, []
        
    p_now = get_price_on_date(svc, symbol, as_of)
    z_now, _ = compute_altman_z_pit(inc, bal, as_of, price_on_date=p_now)
    
    two_yr = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=730)).strftime("%Y-%m-%d")
    p_then = get_price_on_date(svc, symbol, two_yr)
    z_then, _ = compute_altman_z_pit(inc, bal, two_yr, price_on_date=p_then)
    
    if z_now is None or z_then is None:
        return None, 0, []
    return float(z_now - z_then), 1.0, [as_of, two_yr]


def _compute_bvps_cagr_3yr(svc, symbol, as_of, t_start, t_end, params):
    ratios = svc._fetch_ratios(symbol)
    filed = get_n_filed_before(ratios, as_of, 4)
    if not filed:
        return None, 0, []
    bvps_now = filed[0].get("bookValuePerShare", 0) or 0
    if len(filed) >= 4:
        bvps_then = filed[3].get("bookValuePerShare", 0) or 0
        years = 3.0
        start_idx = 3
    elif len(filed) >= 3:
        bvps_then = filed[2].get("bookValuePerShare", 0) or 0
        years = 2.0
        start_idx = 2
    elif len(filed) >= 2:
        bvps_then = filed[1].get("bookValuePerShare", 0) or 0
        years = 1.0
        start_idx = 1
    else:
        return None, 0, []
    if bvps_now <= 0 or bvps_then <= 0:
        return None, 0, []
    c = cagr(bvps_then, bvps_now, years)
    if c is None:
        return None, 0, []
    pit = [filed[0].get("filingDate", ""), filed[start_idx].get("filingDate", "")]
    return round(c, 4), 1.0, pit


def _compute_bvps_consistency(svc, symbol, as_of, t_start, t_end, params):
    ratios = svc._fetch_ratios(symbol)
    filed = get_n_filed_before(ratios, as_of, 4)
    if len(filed) < 3:
        return None, 0, []
    bvps_vals = [s.get("bookValuePerShare", 0) or 0 for s in filed]
    if any(b <= 0 for b in bvps_vals):
        return None, 0, []
    growths = []
    for i in range(len(bvps_vals) - 1):
        g = (bvps_vals[i] / bvps_vals[i+1]) - 1.0
        growths.append(g)
    val = std_dev(growths)
    pit = [s.get("filingDate", "") for s in filed]
    return round(val, 4), 1.0, pit


def _compute_share_count_delta_3yr(svc, symbol, as_of, t_start, t_end, params):
    inc = svc._fetch_income_statements(symbol)
    filed = get_n_filed_before(inc, as_of, 4)
    if not filed:
        return None, 0, []
    shares_now = filed[0].get("weightedAverageShsOutDil") or filed[0].get("weightedAverageShsOut", 0) or 0
    if len(filed) >= 4:
        shares_then = filed[3].get("weightedAverageShsOutDil") or filed[3].get("weightedAverageShsOut", 0) or 0
        start_idx = 3
    elif len(filed) >= 3:
        shares_then = filed[2].get("weightedAverageShsOutDil") or filed[2].get("weightedAverageShsOut", 0) or 0
        start_idx = 2
    elif len(filed) >= 2:
        shares_then = filed[1].get("weightedAverageShsOutDil") or filed[1].get("weightedAverageShsOut", 0) or 0
        start_idx = 1
    else:
        return None, 0, []
    if shares_now <= 0 or shares_then <= 0:
        return None, 0, []
    val = (shares_now - shares_then) / shares_then
    pit = [filed[0].get("filingDate", ""), filed[start_idx].get("filingDate", "")]
    return round(val, 4), 1.0, pit


def _compute_pb_at_t_start(svc, symbol, as_of, t_start, t_end, params):
    ratios = svc._fetch_ratios(symbol)
    filed = latest_filed_before(ratios, as_of)
    if not filed:
        return None, 0, []
    pb = filed.get("priceToBookRatio", 0) or 0
    if pb <= 0:
        return None, 0.5, []
    pit_date = filed.get("filingDate") or filed.get("acceptedDate", "")[:10] or filed.get("date", "")
    return round(pb, 2), 1.0, [pit_date]


def _compute_dcf_gap_at_t_start(svc, symbol, as_of, t_start, t_end, params):
    inc = svc._fetch_income_statements(symbol)
    bal = svc._fetch_balance_sheets(symbol)
    cf = svc._fetch_cash_flows(symbol)
    
    inc_filed = latest_filed_before(inc, as_of)
    bal_filed = latest_filed_before(bal, as_of)
    cf_filed = latest_filed_before(cf, as_of)
    
    if not (inc_filed and bal_filed and cf_filed):
        return None, 0, []
        
    price = get_price_on_date(svc, symbol, as_of)
    if price <= 0:
        return None, 0, []
        
    fcf = cf_filed.get("freeCashFlow", 0) or 0
    if fcf <= 0:
        net_inc = inc_filed.get("netIncome", 0) or 0
        if net_inc > 0:
            fcf = net_inc * 0.7
        else:
            return None, 0.5, []
            
    inc_3 = get_n_filed_before(inc, as_of, 3)
    growth_rate = 0.08
    if len(inc_3) >= 3:
        rev_now = inc_3[0].get("revenue", 0) or 0
        rev_then = inc_3[-1].get("revenue", 0) or 0
        if rev_now > 0 and rev_then > 0:
            cagr_val = cagr(rev_then, rev_now, 2.0)
            if cagr_val is not None:
                growth_rate = max(0.02, min(cagr_val, 0.15))
                
    r = 0.09
    g_p = 0.025
    
    pv_fcf = 0.0
    fcf_t = fcf
    for t in range(1, 6):
        fcf_t = fcf_t * (1.0 + growth_rate)
        pv_fcf += fcf_t / ((1.0 + r) ** t)
        
    tv = (fcf_t * (1.0 + g_p)) / (r - g_p)
    pv_tv = tv / ((1.0 + r) ** 5)
    
    enterprise_value = pv_fcf + pv_tv
    cash = bal_filed.get("cashAndCashEquivalents", 0) or 0
    debt = bal_filed.get("totalDebt", 0) or 0
    equity_value = enterprise_value + cash - debt
    
    shares = inc_filed.get("weightedAverageShsOutDil") or inc_filed.get("weightedAverageShsOut", 0) or 0
    if shares <= 0:
        return None, 0, []
        
    dcf_price = equity_value / shares
    if dcf_price <= 0:
        return None, 0, []
        
    dcf_gap = (dcf_price - price) / price
    pit = [s.get("filingDate") or s.get("date", "") for s in [inc_filed, bal_filed, cf_filed]]
    return round(dcf_gap, 4), 1.0, pit


def _compute_owner_earnings_yield_at_t_start(svc, symbol, as_of, t_start, t_end, params):
    inc = svc._fetch_income_statements(symbol)
    inc_filed = latest_filed_before(inc, as_of)
    cf = svc._fetch_cash_flows(symbol)
    cf_filed = latest_filed_before(cf, as_of)
    km = svc._fetch_key_metrics(symbol)
    km_filed = latest_filed_before(km, as_of)
    
    if not (inc_filed and cf_filed and km_filed):
        return None, 0, []
        
    net_income = cf_filed.get("netIncome", 0) or inc_filed.get("netIncome", 0) or 0
    dep_amort = cf_filed.get("depreciationAndAmortization", 0) or inc_filed.get("depreciationAndAmortization", 0) or 0
    capex = cf_filed.get("capitalExpenditure", 0) or 0
    
    oe = net_income + dep_amort - abs(capex)
    ev = km_filed.get("enterpriseValue", 0) or 0
    if ev <= 0:
        return None, 0, []
    val = oe / ev
    pit = [s.get("filingDate") or s.get("date", "") for s in [inc_filed, cf_filed, km_filed]]
    return round(val, 4), 1.0, pit


def _get_or_compute_transcript_sentiment(symbol: str, safe_sym: str, t: dict, backend_dir: str) -> Optional[float]:
    """Helper to load from local sentiment cache or call Claude API."""
    import json
    import requests
    cache_dir = os.path.join(backend_dir, "fmp_cache", "transcript_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    cache_file = os.path.join(cache_dir, f"{safe_sym}_{t['year']}_Q{t['quarter']}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if cached_data.get("_evaluated"):
                return float(cached_data.get("sentiment", 0.0))
        except Exception as e:
            log.warning(f"Failed to read local transcript sentiment cache {cache_file}: {e}")
            
    # Miss: call Claude API
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_KEY", "")
    if not anthropic_key:
        log.warning(f"No ANTHROPIC_KEY or ANTHROPIC_API_KEY found. Skipping sentiment analysis for {symbol}.")
        return None
        
    content = t["content"][:8000]
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": f"""Analyze this earnings call transcript for {symbol}. Return ONLY a JSON object with:
- "sentiment": float from -1.0 (very bearish) to 1.0 (very bullish) based on management tone, guidance, and confidence
- "summary": string, one-sentence key takeaway (max 100 chars)
- "confidence_signals": list of 2-3 specific bullish/bearish signals you detected

Focus on: forward guidance strength, margin commentary, demand trends, management confidence vs hedging language.

Transcript excerpt:
{content}"""}],
            },
            timeout=30,
        )
        if resp.status_code == 200:
            api_data = resp.json()
            text = ""
            for block in api_data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            
            # Parse JSON
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text.strip())
            
            sentiment = float(parsed.get("sentiment", 0.0))
            summary = parsed.get("summary", "")[:100]
            score = min(max((sentiment + 1) / 2, 0.0), 1.0)
            
            result = {
                "sentiment": sentiment,
                "summary": summary,
                "score": score,
                "_evaluated": True,
                "_cached_at": datetime.now().isoformat()
            }
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            
            log.info(f"Successfully computed sentiment for {symbol} {t['year']}Q{t['quarter']}: {sentiment}")
            return sentiment
        else:
            log.warning(f"Claude API failed for {symbol}: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        log.warning(f"Error calling Claude API for {symbol} {t['year']}Q{t['quarter']}: {e}")
        return None


def _compute_transcript_sentiment_delta_2q(svc, symbol, as_of, t_start, t_end, params):
    import glob
    import re
    import json
    
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    transcript_dir = os.path.join(_backend_dir, "fmp_cache", "earning-call-transcript")
    if not os.path.exists(transcript_dir):
        return None, 0.0, []
        
    safe_sym = symbol.replace("/", "_").replace(" ", "_").upper()
    
    pattern = os.path.join(transcript_dir, f"{safe_sym}_*.json")
    files = glob.glob(pattern)
    if len(files) < 2:
        return None, 0.0, []
        
    valid_transcripts = []
    for fpath in files:
        try:
            basename = os.path.basename(fpath)
            match = re.search(r'_(\d{4})Q(\d)\.json$', basename)
            if not match:
                continue
            year = int(match.group(1))
            quarter = int(match.group(2))
            
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            payload = data.get("payload")
            if not payload or not isinstance(payload, list) or len(payload) == 0:
                continue
            entry = payload[0]
            date_str = entry.get("date")
            if not date_str:
                continue
            
            if date_str <= as_of:
                valid_transcripts.append({
                    "date": date_str,
                    "year": year,
                    "quarter": quarter,
                    "content": entry.get("content", "")
                })
        except Exception as e:
            log.warning(f"Error processing transcript file {fpath}: {e}")
            
    valid_transcripts.sort(key=lambda x: x["date"], reverse=True)
    
    if len(valid_transcripts) < 2:
        return None, 0.0, []
        
    t0 = valid_transcripts[0]
    t1 = valid_transcripts[1]
    
    sentiment_t0 = _get_or_compute_transcript_sentiment(symbol, safe_sym, t0, _backend_dir)
    if sentiment_t0 is None:
        return None, 0.0, []
        
    sentiment_t1 = _get_or_compute_transcript_sentiment(symbol, safe_sym, t1, _backend_dir)
    if sentiment_t1 is None:
        return None, 0.0, []
        
    delta = sentiment_t0 - sentiment_t1
    return round(delta, 4), 1.0, [t0["date"], t1["date"]]



# ---------------------------------------------------------------------------
# Registry: factor_id -> compute function
# ---------------------------------------------------------------------------

_COMPUTE_REGISTRY = {
    # Family 1 — Fundamental delta
    "revenue_yoy_acceleration": _compute_revenue_yoy_acceleration,
    "revenue_cagr_3yr": _compute_revenue_cagr_3yr,
    "eps_yoy_acceleration": _compute_eps_yoy_acceleration,
    "eps_cagr_3yr": _compute_eps_cagr_3yr,
    "fcf_yoy_acceleration": _compute_fcf_yoy_acceleration,
    "fcf_cagr_3yr": _compute_fcf_cagr_3yr,
    "gross_margin_delta_12m": _compute_gross_margin_delta_12m,
    "operating_margin_delta_12m": _compute_operating_margin_delta_12m,
    "net_margin_delta_12m": _compute_net_margin_delta_12m,
    "roic_trajectory": _compute_roic_trajectory,
    "roe_trajectory": _compute_roe_trajectory,
    "altman_z_delta_2yr": _compute_altman_z_delta_2yr,
    "bvps_cagr_3yr": _compute_bvps_cagr_3yr,
    "bvps_consistency": _compute_bvps_consistency,
    "share_count_delta_3yr": _compute_share_count_delta_3yr,
    # Family 2 — Quality regime change
    "piotroski_delta_2yr": _compute_piotroski_delta_2yr,
    # Family 4 — Earnings momentum
    "eps_beats_last_4q": _compute_eps_beats_last_4q,
    "eps_surprise_magnitude_4q_avg": _compute_eps_surprise_magnitude_4q_avg,
    # Family 3 — Valuation reset
    "pe_at_t_start": _compute_pe_at_t_start,
    "ps_at_t_start": _compute_ps_at_t_start,
    "pb_at_t_start": _compute_pb_at_t_start,
    "acquirers_multiple": _compute_acquirers_multiple,
    "epv_to_ev": _compute_epv_to_ev,
    "iv15_discount": _compute_iv15_discount,
    "dcf_gap_at_t_start": _compute_dcf_gap_at_t_start,
    "owner_earnings_yield_at_t_start": _compute_owner_earnings_yield_at_t_start,
    # Family 5 — Analyst dynamics
    "upgrade_cluster_density_90d": _compute_upgrade_cluster_density_90d,
    # Family 6 — Smart money
    "inst_holder_count_qoq": _compute_inst_holder_count_qoq,
    "insider_net_buy_ratio_6m": _compute_insider_net_buy_ratio_6m,
    # Family 8 — Macro
    "vix_level_at_start": _compute_vix_level_at_start,
    "yield_curve_slope_at_start": _compute_yield_curve_slope_at_start,
    "mom_26w": _compute_mom_26w,
    # Family 9 — Options / derivatives
    "volume_to_oi_ratio": _compute_volume_to_oi_ratio,
    # Family 7 — Narrative / sentiment
    "transcript_sentiment_delta_2q": _compute_transcript_sentiment_delta_2q,
}

# Factors not yet in registry get stubbed (return None).
# Adding compute functions is incremental — existing attributions remain valid.
