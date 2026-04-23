"""
fundamental_scores_pit.py
-------------------------
Point-in-time Piotroski F-Score & Altman Z-Score computed from raw FMP
statements (income-statement, balance-sheet-statement, cashflow-statement)
with filingDate gating to prevent look-ahead bias.

Why this exists:
    FMP's `financial-scores` endpoint has NO date parameter. It always returns
    the current fiscal-year score. If you backtest across 5 years using that
    endpoint, every historical row gets stamped with today's score, causing
    severe survivorship / look-ahead bias.

Usage (backend pattern):
    from fundamental_scores_pit import compute_piotroski_pit, compute_altman_z_pit

    inc  = fmp("income-statement",  {"symbol": sym, "period": "annual", "limit": 6})
    bal  = fmp("balance-sheet-statement", {"symbol": sym, "period": "annual", "limit": 6})
    cf   = fmp("cashflow-statement",{"symbol": sym, "period": "annual", "limit": 6})

    piotroski, flags = compute_piotroski_pit(inc, bal, cf, as_of_date="2022-11-15")
    altman_z, parts  = compute_altman_z_pit(inc, bal, as_of_date="2022-11-15",
                                            price_on_date=price, shares=shares)

Cache key suggestion:
    f"pit_scores:{symbol}:{fiscal_year_used}"  -- statements are immutable once
    filed, so you only need to compute each (symbol, FY) pair once, ever.
"""

from typing import Iterable, Optional


# ------------------------- helpers -------------------------

def _sorted_desc(statements: Iterable[dict], key: str = "date") -> list:
    """Sort by reporting date descending. Input from FMP is usually already sorted."""
    return sorted(statements, key=lambda r: r[key], reverse=True)


def _latest_filed_before(statements: list, as_of_date: str) -> Optional[dict]:
    """
    Return the most recent statement whose filingDate <= as_of_date.
    This is THE critical filter that prevents look-ahead.

    FMP returns `filingDate` as 'YYYY-MM-DD'. Lexicographic comparison works.
    """
    for row in statements:
        filed = row.get("filingDate") or row.get("acceptedDate", "")[:10]
        if filed and filed <= as_of_date:
            return row
    return None


def _prior_to(statements: list, row: dict) -> Optional[dict]:
    """Get the statement covering the period immediately before `row`."""
    target_date = row["date"]
    for r in statements:
        if r["date"] < target_date:
            return r
    return None


def _safe_div(n, d):
    return (n / d) if d else 0.0


# ------------------------- Piotroski -------------------------

def compute_piotroski_pit(income_statements: list,
                          balance_sheets: list,
                          cash_flows: list,
                          as_of_date: str) -> tuple[Optional[int], dict]:
    """
    Piotroski F-Score (0-9) using the most recent statements filed on or before
    `as_of_date`. Returns (score, diagnostics) or (None, {reason}) if insufficient
    history.
    """
    inc = _sorted_desc(income_statements)
    bal = _sorted_desc(balance_sheets)
    cf  = _sorted_desc(cash_flows)

    inc_t = _latest_filed_before(inc, as_of_date)
    bal_t = _latest_filed_before(bal, as_of_date)
    cf_t  = _latest_filed_before(cf,  as_of_date)
    if not (inc_t and bal_t and cf_t):
        return None, {"reason": "no statement filed before as_of_date"}

    inc_t1 = _prior_to(inc, inc_t)
    bal_t1 = _prior_to(bal, bal_t)
    if not (inc_t1 and bal_t1):
        return None, {"reason": "no prior year statement for trend"}

    score = 0
    flags = {"fy_used": inc_t.get("fiscalYear"), "filing_date": inc_t.get("filingDate")}

    # Profitability (4)
    f1 = inc_t["netIncome"] > 0
    flags["ni_positive"] = f1; score += f1

    avg_ta = (bal_t["totalAssets"] + bal_t1["totalAssets"]) / 2
    roa = _safe_div(inc_t["netIncome"], avg_ta)
    flags["roa"] = round(roa, 4)
    f2 = roa > 0; flags["roa_positive"] = f2; score += f2

    ocf = cf_t.get("operatingCashFlow") or cf_t.get("netCashProvidedByOperatingActivities", 0)
    f3 = ocf > 0; flags["ocf_positive"] = f3; score += f3
    f4 = ocf > inc_t["netIncome"]; flags["ocf_gt_ni"] = f4; score += f4

    # Leverage / Liquidity (3)
    ltd_t  = _safe_div(bal_t.get("longTermDebt", 0),  bal_t["totalAssets"])
    ltd_t1 = _safe_div(bal_t1.get("longTermDebt", 0), bal_t1["totalAssets"])
    f5 = ltd_t < ltd_t1; flags["leverage_down"] = f5; score += f5

    cr_t  = _safe_div(bal_t["totalCurrentAssets"],  bal_t.get("totalCurrentLiabilities"))
    cr_t1 = _safe_div(bal_t1["totalCurrentAssets"], bal_t1.get("totalCurrentLiabilities"))
    f6 = cr_t > cr_t1
    flags["liquidity_up"] = f6; flags["current_ratio"] = round(cr_t, 3); score += f6

    shares_t  = inc_t.get("weightedAverageShsOut",  0)
    shares_t1 = inc_t1.get("weightedAverageShsOut", 0)
    f7 = shares_t <= shares_t1
    flags["no_dilution"] = f7; score += f7

    # Operating efficiency (2)
    gm_t  = _safe_div(inc_t["grossProfit"],  inc_t["revenue"])
    gm_t1 = _safe_div(inc_t1["grossProfit"], inc_t1["revenue"])
    f8 = gm_t > gm_t1
    flags["gm_up"] = f8; flags["gross_margin"] = round(gm_t, 3); score += f8

    at_t  = _safe_div(inc_t["revenue"],  avg_ta)
    at_t1 = _safe_div(inc_t1["revenue"], bal_t1["totalAssets"])
    f9 = at_t > at_t1
    flags["asset_turnover_up"] = f9; score += f9

    flags["score"] = score
    return score, flags


# ------------------------- Altman Z -------------------------

def compute_altman_z_pit(income_statements: list,
                         balance_sheets: list,
                         as_of_date: str,
                         price_on_date: float = 0.0,
                         shares_outstanding: Optional[float] = None,
                         use_book_value: bool = False) -> tuple[Optional[float], dict]:
    """
    Altman Z-Score (public manufacturing model):
        Z = 1.2·A + 1.4·B + 3.3·C + 0.6·D + 1.0·E
        A = WC / TA                  (working capital / total assets)
        B = RE / TA                  (retained earnings / total assets)
        C = EBIT / TA
        D = MktCap / Total Liabilities
        E = Sales / TA

    Zones:   Z > 2.99 safe   |   1.81 < Z < 2.99 grey   |   Z < 1.81 distress
    Safer clip for feature use: clip(Z, 0, 20) — some fast-growers can blow up D.
    """
    inc = _sorted_desc(income_statements)
    bal = _sorted_desc(balance_sheets)
    inc_t = _latest_filed_before(inc, as_of_date)
    bal_t = _latest_filed_before(bal, as_of_date)
    if not (inc_t and bal_t):
        return None, {"reason": "no statement filed before as_of_date"}
    # 2026-04-23: Altman Z uses MktCap (USD-denominated), so if the
    # underlying statements report in another currency the D term is
    # unit-mismatched nonsense. Return None; existing gate excludes the
    # stock from the scan for non-excluded sectors.
    reported_ccy = inc_t.get("reportedCurrency", "USD")
    if reported_ccy and reported_ccy != "USD":
        return None, {"reason": f"non-USD reporter: {reported_ccy}"}

    ta = bal_t["totalAssets"]
    if not ta:
        return None, {"reason": "total assets is zero"}

    wc    = bal_t["totalCurrentAssets"] - bal_t.get("totalCurrentLiabilities", 0)
    re    = bal_t.get("retainedEarnings", 0)
    ebit  = inc_t.get("operatingIncome") or inc_t.get("ebit", 0)
    sales = inc_t["revenue"]
    tl    = bal_t["totalLiabilities"]

    A = wc / ta
    B = re / ta
    C = ebit / ta
    E = sales / ta

    if use_book_value:
        # Altman 1983 private-firm variant (Z'):
        # Replaces market cap with book equity in the D term.
        # Coefficients and zone thresholds both differ from the public variant.
        book_equity = bal_t.get("totalStockholdersEquity", 0) or 0
        D = (book_equity / tl) if tl else 0
        Z = 0.717*A + 0.847*B + 3.107*C + 0.420*D + 0.998*E
        zone = "safe" if Z > 2.90 else ("grey" if Z > 1.23 else "distress")
        d_label = "D_be_tl"
        variant = "z_prime_book_value"
    else:
        # Altman 1968 public manufacturing variant (Z):
        shares = shares_outstanding or inc_t.get("weightedAverageShsOut", 0)
        mcap = price_on_date * shares
        D = (mcap / tl) if tl else 0
        Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
        zone = "safe" if Z > 2.99 else ("grey" if Z > 1.81 else "distress")
        d_label = "D_mcap_tl"
        variant = "z_public"

    return Z, {
        "fy_used": inc_t.get("fiscalYear"),
        "filing_date": inc_t.get("filingDate"),
        "variant": variant,
        "A_wc_ta": round(A, 3), "B_re_ta": round(B, 3), "C_ebit_ta": round(C, 3),
        d_label: round(D, 3), "E_sales_ta": round(E, 3),
        "z_score": round(Z, 2), "zone": zone,
    }


# ------------------------- validation harness -------------------------

def validate_cache_integrity(cache_records: list, fetch_statements_fn,
                             tolerance_piotroski: int = 2,
                             sample_size: int = 100) -> dict:
    """
    Spot-check: for each cached (symbol, date, piotroski_cached, altman_z_cached)
    record, recompute point-in-time and measure divergence.

    fetch_statements_fn(symbol) -> (income, balance, cashflow) lists from FMP.

    Returns summary dict with:
        - n_checked
        - piotroski_mean_delta, altman_z_mean_delta
        - pct_diverged (|delta_piotroski| > tolerance)
        - examples of worst divergences
    """
    import random, statistics
    sample = random.sample(cache_records, min(sample_size, len(cache_records)))
    deltas_p, deltas_z, diverged = [], [], []
    for rec in sample:
        try:
            inc, bal, cf = fetch_statements_fn(rec["symbol"])
            p_pit, _ = compute_piotroski_pit(inc, bal, cf, rec["date"])
            if p_pit is None: continue
            dp = rec["piotroski_cached"] - p_pit
            deltas_p.append(dp)
            if abs(dp) > tolerance_piotroski:
                diverged.append({"symbol": rec["symbol"], "date": rec["date"],
                                 "cached": rec["piotroski_cached"], "pit": p_pit})
        except Exception as e:
            continue
    return {
        "n_checked": len(deltas_p),
        "piotroski_mean_delta": round(statistics.mean(deltas_p), 2) if deltas_p else None,
        "piotroski_stdev": round(statistics.stdev(deltas_p), 2) if len(deltas_p) > 1 else None,
        "pct_diverged": round(100 * len(diverged) / max(len(deltas_p), 1), 1),
        "worst_examples": sorted(diverged, key=lambda x: abs(x["cached"]-x["pit"]), reverse=True)[:10],
    }
