#!/usr/bin/env python3
"""
replay_baseline.py — Point-in-time (PIT) replay of the 9 methodology baskets
=============================================================================
Produces a REAL screener-native 5-year baseline by re-running the screener's
own valuation + selection over the historical universe, month by month.

WHY THIS EXISTS
  The frontend's per-methodology track records are hardcoded literals + a
  sin()-wiggle (`getBasketReturn`). This script replaces them with an honest
  replay: for each month T it values the whole cached universe AS OF T (using
  only statements filed on/before T), runs the screener's exact gates +
  ranking, takes the top-20 per methodology, holds to T+1, and chains the
  price returns into per-year + full-period stats.

PARITY
  - Valuation: imports and calls screener_v6.get_value() UNCHANGED. The 6
    absolute-MOS methods (dcf_fcff, rd_capitalized_dcf, owner_earnings, epv,
    graham_revised, iv15_deep_value) and all the raw fields come straight from it.
  - The 3 cross-sectional rank methods (ev_gross_profit, earnings_yield_gap,
    acquirers_multiple) + the leverage gate + sector-cap selection are MIRRORED
    verbatim from screener_v6.save_methodology_picks(). If you ever change that
    function's selection logic, re-sync the SELECTION block below (marked).

PIT DISCIPLINE
  - cached_fmp is monkeypatched to serve the on-disk cache trimmed to
    filingDate <= T (statements) / date <= T (key-metrics, ratios).
  - FMP_OFFLINE=1 so every other (uncached) fmp() call returns None — no network,
    no lookahead. Those feed only non-load-bearing fields; the 9 MOS are
    self-computed from statements.
  - Piotroski/Altman are RECOMPUTED PIT from the as-of statements (FMP's
    financial-scores endpoint is current-only → using it would be lookahead).
  - KNOWN DIVERGENCE FROM LIVE (documented, accepted): G2b (forward-EPS-decline
    gate) is inactive here because FMP analyst-estimates is current-only — there
    is no PIT forward number. forward_eps_growth is passed as 0.0, so the replay
    is marginally more permissive on cyclical-peak names than today's live screener.

OUTPUT
  baseline_history.json  (next to this script). Frontend reads it to replace the
  hardcoded METHODOLOGIES_CONFIG returns + delete getBasketReturn.

RUN
  # prerequisites: deploy income-statement limit:15, then repopulate the cache:
  #   python download_fmp_expanded.py            (deep statements persist now)
  # smoke test (1 date, 1 methodology, verbose) — DO THIS FIRST:
  python replay_baseline.py --smoke
  # full run:
  python replay_baseline.py --start 2021-01 --end 2025-12 --rebalance monthly

FIRST-RUN VERIFY (search for "VERIFY#"):
  1. profile cache present (sector/industry for the G4 gate + sector cap)
  2. market_cap = asof_price * shares  (shares from latest as-of income stmt)
  3. delisting/zero-price handling (return uses last close <= T+1)
  4. get_value runs clean offline with the monkeypatched cache
"""

import os, sys, json, math, argparse, logging
from datetime import datetime, timezone

# ── env MUST be set before importing screener_v6 ───────────────────────────
os.environ["FMP_OFFLINE"] = "1"          # no network; uncached fmp() -> None
os.environ.pop("FORCE_CACHE_REFRESH", None)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)
CACHE_DIR = os.path.join(BACKEND_DIR, "fmp_cache")

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("replay")
log.setLevel(logging.INFO)

import screener_v6 as S   # get_value, Stock, _sector_class, _methodology_applicable, constants
import fmp_cache

# ── global the patched cache reader keys off (set per rebalance) ───────────
ASOF_DATE = "9999-12-31"   # ISO yyyy-mm-dd; statements with filingDate>ASOF are hidden

DATED_STATEMENTS = {"income-statement", "balance-sheet-statement", "cash-flow-statement"}
DATED_OTHER      = {"key-metrics", "ratios"}   # trimmed by 'date' (no filingDate field)

# ───────────────────────── on-disk cache helpers ──────────────────────────
_raw_cache = {}   # (endpoint, sym) -> payload list (unfiltered), loaded once

def _load_payload(endpoint, sym):
    key = (endpoint, sym)
    if key in _raw_cache:
        return _raw_cache[key]
    # mirror fmp_cache._cache_path endpoint folding
    ep = endpoint
    if ep == "historical-price-eod/full":
        ep = "historical-price-eod"
    safe = sym.replace("/", "_").replace(" ", "_").upper()
    path = os.path.join(CACHE_DIR, ep, f"{safe}.json")
    payload = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f).get("payload")
        except Exception as e:
            log.debug(f"cache read fail {path}: {e}")
    _raw_cache[key] = payload
    return payload


def patched_cached_fmp(endpoint, symbol, fetcher, ttl_days=None, cache_key_suffix=""):
    """Serve the on-disk cache, trimmed to ASOF_DATE. financial-scores is
    suppressed (we inject PIT Piotroski/Altman ourselves)."""
    if endpoint == "financial-scores":
        return None
    payload = _load_payload(endpoint, symbol)
    if not payload:
        return None
    if endpoint in DATED_STATEMENTS:
        out = [r for r in payload if (r.get("filingDate") or r.get("date") or "") <= ASOF_DATE]
        return out or None
    if endpoint in DATED_OTHER:
        out = [r for r in payload if (r.get("date") or "") <= ASOF_DATE]
        return out or None
    # profile / anything else: serve as-is (static-ish; sector/industry only)
    return payload


# install the monkeypatch (get_value resolves cached_fmp via screener_v6's module global)
S.cached_fmp = patched_cached_fmp


# ───────────────────────── price cache (as-of close) ──────────────────────
_price_cache = {}   # sym -> list[(date, close)] sorted ASC

def _price_series(sym):
    if sym in _price_cache:
        return _price_cache[sym]
    payload = _load_payload("historical-price-eod", sym) or []
    ser = sorted(((r.get("date", ""), float(r.get("close") or 0.0)) for r in payload
                  if r.get("close") is not None), key=lambda x: x[0])
    _price_cache[sym] = ser
    return ser

def price_asof(sym, date_iso):
    """Latest split-adjusted close with date <= date_iso. (date, close) or (None,None)."""
    ser = _price_series(sym)
    lo, hi, ans = 0, len(ser) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if ser[mid][0] <= date_iso:
            ans = ser[mid]; lo = mid + 1
        else:
            hi = mid - 1
    return (ans[0], ans[1]) if ans and ans[1] > 0 else (None, None)


# ───────────────────────── profile (sector/industry) ──────────────────────
# VERIFY#1 — needs fmp_cache/profile/{SYM}.json. Without it, G4 + sector cap degrade
# (everything classifies 'operating' / sector 'Unknown' -> baskets cap at 6/sector).
def profile_sector_industry(sym):
    p = _load_payload("profile", sym)
    if p and isinstance(p, list) and p:
        rec = p[0]
        return (rec.get("sector") or "", rec.get("industry") or "")
    return ("", "")


# ───────────────────────── PIT Piotroski / Altman ─────────────────────────
def _f(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            try: return float(v)
            except Exception: pass
    return 0.0

def pit_scores(inc, bs, cf, market_cap):
    """Recompute Piotroski F-score (0-9) and Altman-Z from the two latest
    as-of annual statements. Returns (piotroski:int, altman_z:float).
    Insufficient history -> (0, 0.0): the >=3 gate then excludes the name
    (consistent with the live 5-year-history requirement)."""
    def by_year(rows):
        m = {}
        for r in rows or []:
            y = (r.get("fiscalYear") or (r.get("date") or "")[:4])
            if y: m[str(y)] = r
        return m
    iY, bY, cY = by_year(inc), by_year(bs), by_year(cf)
    years = sorted(set(iY) & set(bY) & set(cY))
    if not years:
        return 0, 0.0
    yT = years[-1]
    i_t, b_t, c_t = iY[yT], bY[yT], cY[yT]

    # Altman-Z (uses latest year only)
    TA  = _f(b_t, "totalAssets")
    TL  = _f(b_t, "totalLiabilities")
    WC  = _f(b_t, "totalCurrentAssets") - _f(b_t, "totalCurrentLiabilities")
    RE  = _f(b_t, "retainedEarnings")
    EBIT= _f(i_t, "operatingIncome", "ebit")
    SAL = _f(i_t, "revenue")
    z = 0.0
    if TA > 0:
        z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 1.0*(SAL/TA)
        if TL > 0:
            z += 0.6*(market_cap / TL)

    # Piotroski (needs t-1)
    if len(years) < 2:
        return 0, round(z, 3)
    yP = years[-2]
    i_p, b_p, c_p = iY[yP], bY[yP], cY[yP]
    TA_p = _f(b_p, "totalAssets")
    NI_t, NI_p = _f(i_t, "netIncome", "bottomLineNetIncome"), _f(i_p, "netIncome", "bottomLineNetIncome")
    CFO_t = _f(c_t, "operatingCashFlow", "netCashProvidedByOperatingActivities")
    roa_t = NI_t / TA if TA > 0 else 0.0
    roa_p = NI_p / TA_p if TA_p > 0 else 0.0
    score = 0
    score += 1 if roa_t > 0 else 0                                  # 1 ROA>0
    score += 1 if CFO_t > 0 else 0                                  # 2 CFO>0
    score += 1 if roa_t > roa_p else 0                              # 3 dROA>0
    score += 1 if CFO_t > NI_t else 0                               # 4 accruals (CFO>NI)
    ltd_t = _f(b_t, "longTermDebt", "totalDebt"); ltd_p = _f(b_p, "longTermDebt", "totalDebt")
    lev_t = ltd_t / TA if TA > 0 else 0.0; lev_p = ltd_p / TA_p if TA_p > 0 else 0.0
    score += 1 if lev_t < lev_p else 0                              # 5 leverage down
    cr_t = (_f(b_t,"totalCurrentAssets")/_f(b_t,"totalCurrentLiabilities")) if _f(b_t,"totalCurrentLiabilities")>0 else 0.0
    cr_p = (_f(b_p,"totalCurrentAssets")/_f(b_p,"totalCurrentLiabilities")) if _f(b_p,"totalCurrentLiabilities")>0 else 0.0
    score += 1 if cr_t > cr_p else 0                                # 6 current ratio up
    sh_t = _f(i_t,"weightedAverageShsOutDil","weightedAverageShsOut")
    sh_p = _f(i_p,"weightedAverageShsOutDil","weightedAverageShsOut")
    score += 1 if (sh_p > 0 and sh_t <= sh_p) else 0               # 7 no dilution
    gm_t = (_f(i_t,"grossProfit")/_f(i_t,"revenue")) if _f(i_t,"revenue")>0 else 0.0
    gm_p = (_f(i_p,"grossProfit")/_f(i_p,"revenue")) if _f(i_p,"revenue")>0 else 0.0
    score += 1 if gm_t > gm_p else 0                               # 8 gross margin up
    at_t = (_f(i_t,"revenue")/TA) if TA>0 else 0.0
    at_p = (_f(i_p,"revenue")/TA_p) if TA_p>0 else 0.0
    score += 1 if at_t > at_p else 0                               # 9 asset turnover up
    return score, round(z, 3)


# ───────────────────────── value the universe AS OF T ─────────────────────
def universe_symbols():
    d = os.path.join(CACHE_DIR, "income-statement")
    return sorted(fn[:-5] for fn in os.listdir(d) if fn.endswith(".json"))

def value_universe(date_iso, symbols):
    """Return list[Stock] valued as of date_iso (PIT)."""
    global ASOF_DATE
    ASOF_DATE = date_iso
    # _raw_cache.clear()    # force re-trim at the new date (cheap; files are small)
    # Note: raw payloads are static, filtering is done dynamically by ASOF_DATE in patched_cached_fmp.
    # Disabling clear() preserves parsed JSON in memory, making the multi-year backtest 20x-50x faster.
    out = []
    for sym in symbols:
        pdate, price = price_asof(sym, date_iso)
        if price is None:          # not trading as of T
            continue
        try:
            v = S.get_value(sym, price, price_currency="USD", forward_eps_growth=0.0)  # VERIFY#4
        except Exception as e:
            log.debug(f"{sym} get_value fail @ {date_iso}: {e}")
            continue
        if not v or v.get("dcf_fcff_mos", -1.0) == -1.0 and v.get("epv_mos", -1.0) == -1.0 \
                and v.get("graham_revised_mos", -1.0) == -1.0:
            # nothing valued (e.g. price<=0 path or no statements as-of) — still
            # keep for rank methods only if it has the raw fields; otherwise skip
            if not v or v.get("total_assets", 0) <= 0:
                continue

        inc = patched_cached_fmp("income-statement", sym, None) or []
        bs  = patched_cached_fmp("balance-sheet-statement", sym, None) or []
        cf  = patched_cached_fmp("cash-flow-statement", sym, None) or []
        inc_sorted = sorted(inc, key=lambda x: x.get("date", ""))
        shares = 0.0
        if inc_sorted:
            shares = _f(inc_sorted[-1], "weightedAverageShsOutDil", "weightedAverageShsOut")
        market_cap = price * shares if shares > 0 else 0.0          # VERIFY#2
        trailing_eps_yoy = None
        if len(inc_sorted) >= 2:
            _e0 = _f(inc_sorted[-1], "epsDiluted", "eps"); _e1 = _f(inc_sorted[-2], "epsDiluted", "eps")
            if _e1 > 0:                     # only meaningful off a positive base
                trailing_eps_yoy = (_e0 - _e1) / abs(_e1)
        piotroski, altman = pit_scores(inc, bs, cf, market_cap)

        sector, industry = profile_sector_industry(sym)

        s = S.Stock(symbol=sym) if "symbol" in S.Stock.__dataclass_fields__ else S.Stock()
        s.symbol = sym
        s.price = price
        s.sector = sector
        s.industry = industry
        s.market_cap = market_cap
        s.piotroski = piotroski
        s.altman_z = altman
        # absolute-MOS + raw fields straight from get_value
        for fld in ("dcf_fcff_mos","rd_capitalized_dcf_mos","owner_earnings_mos","epv_mos",
                    "graham_revised_mos","iv15_deep_value_mos",
                    "cycle_flag","norm_scale","years_history","structural_break",
                    "forward_eps_growth","net_debt_local","ebit_local","depreciation_local",
                    "net_debt","ebit","gross_profit","total_assets","eps_latest","fx_to_price",
                    "iv15_nogrowth_agreement","iv15_saturated"):
            if fld in v:
                setattr(s, fld, v[fld])
        s._asof_price_date = pdate
        s._trailing_eps_yoy = trailing_eps_yoy
        out.append(s)
    return out


# ───────────────────────── SELECTION (mirror of save_methodology_picks) ────
# >>> If screener_v6.save_methodology_picks selection changes, re-sync this block.
RISK_FREE       = getattr(S, "RISK_FREE", 0.045)
# Boost = 10% of each method's max MOS amplitude, so incumbency is the SAME
# relative strength everywhere. Rank methods are compressed (ev_gp ±0.15,
# ey_gap ±0.125, acquirers ±0.20), so the old flat 0.05 was ~3x too strong and
# cemented below-median incumbents (ev_gross_profit: 24.5mo avg hold, -42% DD).
HYST_FRAC       = 0.10
_MOS_AMPLITUDE  = {"ev_gross_profit": 0.15, "earnings_yield_gap": 0.125, "acquirers_multiple": 0.20}
def _hyst_boost(k):
    return HYST_FRAC * _MOS_AMPLITUDE.get(k, 0.50)  # absolute methods: 0.10*0.50 = 0.05 (unchanged)
EARNINGS_BASED  = {"dcf_fcff","rd_capitalized_dcf","owner_earnings","epv","graham_revised","iv15_deep_value"}
METHOD_MOS = {
    "dcf_fcff":"dcf_fcff_mos", "earnings_yield_gap":"earnings_yield_gap_mos",
    "ev_gross_profit":"ev_gross_profit_mos", "rd_capitalized_dcf":"rd_capitalized_dcf_mos",
    "owner_earnings":"owner_earnings_mos", "epv":"epv_mos", "graham_revised":"graham_revised_mos",
    "acquirers_multiple":"acquirers_multiple_mos", "iv15_deep_value":"iv15_deep_value_mos",
}

def _passes_leverage_gate(s):
    ebitda = (getattr(s,"ebit_local",0.0) or 0.0) + (getattr(s,"depreciation_local",0.0) or 0.0)
    net_debt = getattr(s,"net_debt_local",0.0) or 0.0
    if ebitda <= 0.0:
        return net_debt <= 0.0
    return (net_debt / ebitda) < 3.0

def _rank_methods(all_results):
    """Assign the 3 cross-sectional rank pseudo-MOS in place."""
    # EV/GP
    for s in all_results:
        ta = getattr(s,"total_assets",0.0) or 0.0
        s.gp_ta = (getattr(s,"gross_profit",0.0) or 0.0)/ta if ta > 0 else 0.0
    gp = sorted(all_results, key=lambda x: x.gp_ta); N = len(gp)
    for i,s in enumerate(gp):
        rp = i/(N-1) if N>1 else 0.5
        s.ev_gross_profit_mos = (rp-0.5)*0.3
    # EY gap
    for s in all_results:
        ey = ((getattr(s,"eps_latest",0.0) or 0.0)*(getattr(s,"fx_to_price",1.0) or 1.0))/s.price if s.price>0 else 0.0
        s.ey_gap = ey - RISK_FREE
    ey = sorted(all_results, key=lambda x: x.ey_gap); N = len(ey)
    for i,s in enumerate(ey):
        rp = i/(N-1) if N>1 else 0.5
        s.earnings_yield_gap_mos = (rp-0.5)*0.25
    # Acquirer's multiple
    am = []
    for s in all_results:
        ev = (getattr(s,"market_cap",0.0) or 0.0) + (getattr(s,"net_debt",0.0) or 0.0)
        ebit = getattr(s,"ebit",0.0) or 0.0
        if ev>0 and ebit>0 and 0 < ev/ebit <= 100:
            s.acquirers_multiple = ev/ebit; am.append(s)
        else:
            s.acquirers_multiple = 999.0; s.acquirers_multiple_mos = -1.0
    am.sort(key=lambda x: x.acquirers_multiple); M = len(am)
    for j,s in enumerate(am):
        rp = j/(M-1) if M>1 else 0.5
        s.acquirers_multiple_mos = (0.5-rp)*0.4

def _best_portfolio(candidates, target=20):
    """Sector cap = max 30% (=6) per sector. Greedy. Returns up to `target`."""
    limit = max(1, round(target*0.3)); port=[]; sc={}
    for s in candidates:
        sec = getattr(s,"sector","") or "Unknown"
        if sc.get(sec,0) < limit:
            port.append(s); sc[sec]=sc.get(sec,0)+1
            if len(port)==target: break
    return port

def build_baskets(all_results, incumbents):
    """{method: [top<=20 Stock]} for one rebalance. `incumbents` = {method: set(syms)} from prior month."""
    _rank_methods(all_results)
    out = {}
    for key, mos_field in METHOD_MOS.items():
        held = incumbents.get(key, set())
        cands = []
        for s in all_results:
            mos_val = getattr(s, mos_field, -1.0)
            if mos_val is None or mos_val <= -1.0:
                continue
            sc = S._sector_class(s)
            s._sc = sc
            if not S._methodology_applicable(key, sc):              # G4
                continue
            if key in EARNINGS_BASED and (getattr(s,"structural_break",False) or getattr(s,"years_history",99) < 5):
                continue                                            # G2a
            # G2b inactive (forward_eps_growth==0 in replay) — kept for fidelity of structure
            if key in EARNINGS_BASED and getattr(s,"forward_eps_growth",0.0) <= -0.25:
                continue
            # G2b PIT proxy: drop cyclical-peak earnings-method names whose TRAILING annual
            # EPS has rolled over (>=25% YoY off a positive base). Forward consensus (live
            # G2b's input) has no PIT source, so this catches the confirmed-rollover subset.
            if key in EARNINGS_BASED and getattr(s, "cycle_flag", "NORMAL") == "PEAK_CYCLE":
                _tey = getattr(s, "_trailing_eps_yoy", None)
                if _tey is not None and _tey <= -0.25:
                    continue
            if key == "iv15_deep_value":                            # G3
                if not getattr(s,"iv15_nogrowth_agreement",True):
                    continue
                if getattr(s,"iv15_saturated",False):
                    mos_val = min(0.50, mos_val)
            if _passes_leverage_gate(s) and (getattr(s,"piotroski",0) or 0) >= 3:
                eff = mos_val
                if key in EARNINGS_BASED and getattr(s,"cycle_flag","NORMAL") == "PEAK_CYCLE":
                    ns = getattr(s,"norm_scale",1.0) or 1.0
                    if ns > 0:
                        eff = max(-1.0, min(0.95, 1.0 - (1.0 - mos_val)/ns))
                s._temp_mos = eff + (_hyst_boost(key) if s.symbol in held else 0.0)
                s._sel_mos = mos_val   # clean MOS for weighting (pre-hysteresis, pre-norm)
                cands.append(s)
        cands.sort(key=lambda x: x._temp_mos, reverse=True)
        out[key] = _best_portfolio(cands, 20)
    return out
# <<< end mirror


# ───────────────────────── returns + stats ────────────────────────────────
def basket_return(holdings, t0, t1):
    """(equal_ret, mos_ret) price returns for `holdings` from t0 to t1.
    Missing price at t1 -> uses last close <= t1 (captures most of a delisting drop)."""
    rets, weights = [], []
    for s in holdings:
        _, p0 = price_asof(s.symbol, t0)
        _, p1 = price_asof(s.symbol, t1)
        if not p0 or not p1:
            continue
        rets.append(p1/p0 - 1.0)
        weights.append(max(getattr(s, "_sel_mos", 0.0), 0.0))
    if not rets:
        return 0.0, 0.0
    eq = sum(rets)/len(rets)
    wsum = sum(weights)
    mw = (sum(w*r for w,r in zip(weights,rets))/wsum) if wsum > 0 else eq
    return eq, mw

def stats_from_monthly(monthly):
    """monthly: list[(date_end, ret)]. -> dict of cagr/mdd/sharpe/win_rate/by_year."""
    if not monthly:
        return {}
    eq = 1.0; curve=[1.0]; peak=1.0; mdd=0.0
    by_year_factor = {}
    for d, r in monthly:
        eq *= (1.0+r); curve.append(eq)
        peak = max(peak, eq); mdd = min(mdd, eq/peak - 1.0)
        y = d[:4]; by_year_factor[y] = by_year_factor.get(y, 1.0)*(1.0+r)
    n = len(monthly)
    years = n/12.0
    cagr = eq**(1.0/years) - 1.0 if years > 0 and eq > 0 else 0.0
    mean = sum(r for _,r in monthly)/n
    var = sum((r-mean)**2 for _,r in monthly)/n
    sd = math.sqrt(var)
    sharpe = ((mean - RISK_FREE/12.0)/sd)*math.sqrt(12) if sd > 0 else 0.0
    win = sum(1 for _,r in monthly if r > 0)/n
    return {
        "cagr": round(cagr,4), "total_return": round(eq-1.0,4),
        "max_drawdown": round(mdd,4), "sharpe": round(sharpe,3),
        "win_rate": round(win,3), "months": n,
        "by_year": {y: round(f-1.0,4) for y,f in sorted(by_year_factor.items())},
    }


# ───────────────────────── rebalance dates ────────────────────────────────
def month_ends(start_ym, end_ym):
    """List of yyyy-mm-28..31 month-end ISO dates inclusive (uses 'last close<=date' so 28 is safe)."""
    sy, sm = map(int, start_ym.split("-")); ey, em = map(int, end_ym.split("-"))
    out=[]; y,m = sy,sm
    while (y, m) <= (ey, em):
        # use day 28 as a robust 'month end' anchor for the as-of close lookup
        out.append(f"{y:04d}-{m:02d}-28")
        m += 1
        if m > 12: m = 1; y += 1
    return out


# ───────────────────────── main ───────────────────────────────────────────
def run(start_ym, end_ym, smoke=False):
    syms = universe_symbols()
    log.info(f"Universe: {len(syms)} symbols  |  cache: {CACHE_DIR}")
    dates = month_ends(start_ym, end_ym)
    if smoke:
        dates = dates[:2]
        log.info(f"SMOKE: dates={dates}")

    # value the universe at each rebalance date once, build baskets with hysteresis
    baskets_by_date = {}     # date -> {method: [Stock]}
    incumbents = {}          # method -> set(syms) carried from prior month
    for di, d in enumerate(dates):
        stocks = value_universe(d, syms)
        baskets = build_baskets(stocks, incumbents)
        baskets_by_date[d] = baskets
        incumbents = {k: {s.symbol for s in v} for k, v in baskets.items()}
        if smoke:
            for k, v in baskets.items():
                log.info(f"  {d} {k:20s} n={len(v):2d}  top5={[s.symbol for s in v[:5]]}")
        else:
            sizes = {k: len(v) for k, v in baskets.items()}
            log.info(f"  {d}: baskets built {sizes}")

    # ── dump per-month picks for the bias audit (audit_baskets.py) ──
    import csv
    picks_path = os.path.join(BACKEND_DIR, "baseline_picks.csv")
    with open(picks_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date","method","rank","symbol","sector","sector_class",
                    "market_cap","sel_mos","piotroski","altman_z","cycle_flag",
                    "years_history","price","last_price_date"])
        for d in sorted(baskets_by_date):
            for method, holds in baskets_by_date[d].items():
                for rank, s in enumerate(holds, 1):
                    w.writerow([d, method, rank, s.symbol,
                                getattr(s,"sector","") or "", getattr(s,"_sc","") or "",
                                round(getattr(s,"market_cap",0) or 0, 2),
                                round(getattr(s,"_sel_mos",0) or 0, 4),
                                getattr(s,"piotroski",0), getattr(s,"altman_z",0),
                                getattr(s,"cycle_flag","") or "",
                                getattr(s,"years_history",0),
                                round(s.price,4), getattr(s,"_asof_price_date","") or ""])
    log.info(f"Wrote {picks_path}")

    if smoke:
        # one methodology, one period return, full detail
        if len(dates) >= 2:
            k = "dcf_fcff"
            eq, mw = basket_return(baskets_by_date[dates[0]][k], dates[0], dates[1])
            log.info(f"\nSMOKE return {k} {dates[0]}->{dates[1]}: equal={eq:+.4f} mos={mw:+.4f}")
            log.info("Smoke OK. If sizes are ~20 and returns are finite, run the full replay.")
        return

    # chain monthly returns per methodology, per weighting
    methods = list(METHOD_MOS.keys())
    monthly = {k: {"equal": [], "mos": []} for k in methods}
    turnover = {k: [] for k in methods}
    for i in range(len(dates)-1):
        t0, t1 = dates[i], dates[i+1]
        for k in methods:
            holds = baskets_by_date[t0][k]
            eq, mw = basket_return(holds, t0, t1)
            monthly[k]["equal"].append((t1, eq))
            monthly[k]["mos"].append((t1, mw))
            prev = {s.symbol for s in holds}
            nxt  = {s.symbol for s in baskets_by_date[t1][k]}
            turnover[k].append(1.0 - (len(prev & nxt)/len(prev) if prev else 1.0))

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "rebalance": "monthly", "top_n": 20, "weightings": ["equal", "mos"],
            "transaction_costs": 0.0, "return_type": "price (split-adj, ex-dividends)",
            "piotroski_altman": "recomputed PIT from as-of statements",
            "g2b_forward_decline": "PIT proxy — PEAK_CYCLE + trailing EPS YoY <= -25%",
            "period": f"{start_ym}..{end_ym}", "universe_size": len(syms),
        },
        "methodologies": {},
    }
    for k in methods:
        result["methodologies"][k] = {
            "equal": {**stats_from_monthly(monthly[k]["equal"]),
                      "avg_turnover": round(sum(turnover[k])/len(turnover[k]), 3) if turnover[k] else 0.0},
            "mos":   {**stats_from_monthly(monthly[k]["mos"]),
                      "avg_turnover": round(sum(turnover[k])/len(turnover[k]), 3) if turnover[k] else 0.0},
        }

    out_path = os.path.join(BACKEND_DIR, "baseline_history.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    log.info(f"\nWrote {out_path}")
    for k in methods:
        e = result["methodologies"][k]["equal"]; m = result["methodologies"][k]["mos"]
        log.info(f"  {k:20s} EW cagr={e.get('cagr',0):+.3f} mdd={e.get('max_drawdown',0):+.3f} "
                 f"sharpe={e.get('sharpe',0):+.2f} | MOSw cagr={m.get('cagr',0):+.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-01")
    ap.add_argument("--end",   default="2025-12")
    ap.add_argument("--rebalance", default="monthly", choices=["monthly"])
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    run(a.start, a.end, smoke=a.smoke)
