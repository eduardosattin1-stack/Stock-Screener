#!/usr/bin/env python3
"""Commodity-macro dials + the winner scoreboard for the MINING book (Tavi-Costa layer).

FUTURE_RESOURCES_SPLIT_SPEC.md §2. Produces `_opus_debate/mining/commodity_macro.json`, which the
/commodities page renders and the Mining Director cites. Driven by `mining-macro` in
weekly_opus_refresh.py; all market inputs come through `screener_v6.fmp` (injected, never imported
at module scope) so the math is unit-testable with zero network.

═══ THE GOLD SEAM (read before touching the scoreboard) ═══
CLAUDE.md: gold / reserve assets are a FALSIFICATION check ONLY, never a scored input — the
momentum-loop guard, because a momentum-scored gold book would have bought the Jan-2026 top. That
invariant is enforced here in two places and both are load-bearing:
  1. D4 (gold-vs-real-rate divergence) is DISPLAY-ONLY. It is excluded from the scoreboard entirely.
  2. Any chain whose taxonomy commodity block says `monetary_metal: true` has its MOMENTUM leg and
     its percentile-PROXY setup leg neutralized to their midpoints (stamped
     `monetary_metal_excluded`). Gold's own price action therefore cannot score the precious chain;
     it ranks on miners-confirmation (are the equities confirming the metal?), the Dalio phase tilt,
     and genuine cost-curve economics (`vs_incentive_pct`, an analyst supply-cost figure — NOT a
     price percentile), which stays allowed precisely because it is not momentum.
Displayed gold dials are data for a human to look at. Nothing computed from them may reach a score,
a cap, a weight, or the phase machine.

One subtlety worth stating so nobody "fixes" it later: the miners-confirmation leg IS allowed to
react to the metal price, because it measures the RATIO of miners to metal, and it can only ever
react CONTRARILY — a gold spike the equities refuse to confirm scores the chain DOWN (an
unconfirmed, paper move). A metal rip lowering the score is the guard working. What is forbidden is
the metal's own level or momentum ADDING points, which is why the setup and momentum legs are hard-
frozen for monetary chains. test_mining_macro.py M3 pins both halves of this.

WHAT THIS MODULE MUST NOT DO
  - Never import `debt_cycle` and never call `fetch_debt_cycle` (`_write_macro_regime` is the only
    site allowed to tick the phase state machine). It READS the already-published
    `_opus_debate/macro_regime.json` for the phase, nothing more.
  - Never use FRED/TreasuryDirect: every input is FMP, so this mode has no environment-specific
    fetch path and behaves identically on the operator box and in a sandbox.
  - Never gate membership, size a position, or move conviction. The scoreboard RANKS setups for
    display and Director citation. The debate pipeline picks the names.

FAIL-OPEN: every missing leg pays its exact neutral midpoint, so an outage compresses all scores
symmetrically toward the middle and can never single out one chain. The mode always writes a
payload (even fully degraded) and exits 0; non-zero only on a filesystem failure.
"""
import json
import os
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
MINING_DIR = HERE / "mining"
CACHE_F = MINING_DIR / "_commodity_macro_cache.json"
OUT_F = MINING_DIR / "commodity_macro.json"
TAX_F = HERE / "mining_chains.json"
REGIME_F = MINING_DIR / "regime_state.json"
MACRO_SNAPSHOT_F = HERE / "macro_regime.json"

VERSION = "mining-macro-v1"
MIN_PCTILE_OBS = 252            # below this a percentile is null, never fabricated
CACHE_MAX_STALE_DAYS = 14

# Commodity + index series (D1-D8). ESUSD/DXUSD are context, not commodities.
CORE_SERIES = ["GCUSD", "SIUSD", "HGUSD", "CLUSD", "PLUSD", "PAUSD", "ALIUSD", "ESUSD", "DXUSD"]
CORE_ETFS = ["GDX", "GLD", "XME", "URA", "COPX", "REMX", "SIL"]
MOMENTUM_TABLE = [("GCUSD", "Gold"), ("SIUSD", "Silver"), ("HGUSD", "Copper"),
                  ("PLUSD", "Platinum"), ("PAUSD", "Palladium"), ("ALIUSD", "Aluminum"),
                  ("URA", "Uranium (URA proxy)")]

# Dalio phase -> scoreboard points (hand-tuned priors, PHASE_DURATION_CAPS precedent). UNKNOWN is
# the neutral midpoint on both sides: a macro outage must not advantage or penalize either cohort.
PHASE_TILT_POINTS = {
    "EXPANSION":    {"monetary": 8,  "industrial": 15},
    "DISCIPLINE":   {"monetary": 15, "industrial": 8},
    "FORCING":      {"monetary": 20, "industrial": 4},
    "MONETIZATION": {"monetary": 20, "industrial": 20},
    "UNKNOWN":      {"monetary": 10, "industrial": 10},
}
NEUTRAL_SETUP, NEUTRAL_MOM, NEUTRAL_CONF = 15.0, 15.0, 10.0


# ────────────────────────────── pure math (unit-tested, no I/O) ──────────────────────────────
def _pctile(x, hist):
    """Empirical percentile of x within hist: 100*(#below + 0.5*#equal)/n. None below
    MIN_PCTILE_OBS observations — a percentile off 40 points is noise dressed as precision."""
    vals = [h for h in (hist or []) if isinstance(h, (int, float))]
    if not isinstance(x, (int, float)) or len(vals) < MIN_PCTILE_OBS:
        return None
    below = sum(1 for h in vals if h < x)
    equal = sum(1 for h in vals if h == x)
    return round(100.0 * (below + 0.5 * equal) / len(vals), 1)


def _joint(a, b):
    """Inner-join two [(date, close)] series on date -> [(date, a_close, b_close)] ascending."""
    bm = dict(b or [])
    return [(d, ca, bm[d]) for d, ca in (a or []) if d in bm]


def _rebase(series, base=100.0):
    """[(date, close)] -> [(date, close/first*base)]; [] if the first close is unusable."""
    rows = [(d, c) for d, c in (series or []) if isinstance(c, (int, float)) and c > 0]
    if not rows:
        return []
    first = rows[0][1]
    return [(d, c / first * base) for d, c in rows]


def _chg(series, days):
    """Fractional change over `days` trading observations (not calendar days). None if short."""
    rows = [c for _, c in (series or []) if isinstance(c, (int, float)) and c > 0]
    if len(rows) < days + 1:
        return None
    prev = rows[-1 - days]
    return (rows[-1] / prev - 1) if prev > 0 else None


def _dma(series, n):
    rows = [c for _, c in (series or []) if isinstance(c, (int, float))]
    return round(statistics.fmean(rows[-n:]), 6) if len(rows) >= n else None


def _trend(series, chg_3m):
    """50/200 DMA crossover confirmed by 3m direction; 'mixed' when they disagree."""
    d50, d200 = _dma(series, 50), _dma(series, 200)
    if d50 is None or d200 is None or chg_3m is None:
        return "unknown"
    if d50 > d200 and chg_3m > 0:
        return "up"
    if d50 < d200 and chg_3m < 0:
        return "down"
    return "mixed"


def _direction(chg, band=0.02):
    if chg is None:
        return "unknown"
    return "rising" if chg >= band else ("falling" if chg <= -band else "flat")


def _confirmation(chg_3m):
    if chg_3m is None:
        return "unknown"
    return "confirming" if chg_3m >= 0.02 else ("diverging" if chg_3m <= -0.02 else "flat")


def _ratio_series(a, b):
    """Pointwise a/b over the joint dates."""
    return [(d, ca / cb) for d, ca, cb in _joint(a, b) if isinstance(cb, (int, float)) and cb > 0]


def _weekly(series, points=52):
    """Downsample to ~`points` weekly closes for the page's sparklines (payload stays small)."""
    rows = [(d, round(float(c), 6)) for d, c in (series or []) if isinstance(c, (int, float))]
    if not rows:
        return []
    weekly = rows[::5][-points:]                      # ~5 trading days per week
    if weekly and weekly[-1][0] != rows[-1][0]:
        weekly = weekly[1:] + [rows[-1]]              # always end on the latest close
    return weekly


def _rolling_12m_returns(series, lookback_days=1260, window=252):
    """Daily 12m returns over the trailing 5y — the distribution D8/the momentum leg ranks today's
    momentum against ('how strong is this by this commodity's OWN standards')."""
    rows = [c for _, c in (series or []) if isinstance(c, (int, float)) and c > 0]
    rows = rows[-(lookback_days + window):]
    return [rows[i] / rows[i - window] - 1 for i in range(window, len(rows)) if rows[i - window] > 0]


# ────────────────────────────── fetch layer (injected fmp) ──────────────────────────────
def _eod(fmp_func, sym, years=6, today=None):
    """FMP historical EOD -> [(date, close)] ascending. [] on any failure (fmp returns None)."""
    end = today or date.today()
    start = end - timedelta(days=int(365.25 * years))
    rows = None
    for ep in ("historical-price-eod/full", "historical-price-eod/light"):
        rows = fmp_func(ep, {"symbol": sym, "from": start.isoformat(), "to": end.isoformat()})
        if isinstance(rows, list) and rows:
            break
    if not isinstance(rows, list) or not rows:
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d, c = r.get("date"), r.get("adjClose", r.get("close"))
        if d and isinstance(c, (int, float)) and c > 0:
            out.append((str(d)[:10], float(c)))
    out.sort(key=lambda t: t[0])
    return out


def _cpi_yoy_series(fmp_func, years=6, today=None):
    """Realized CPI YoY, in percent, as [(date, yoy_pct)].

    LOAD-BEARING: FMP's `inflationRate` is MARKET-IMPLIED EXPECTED inflation (~2.3%), NOT realized
    CPI (~4%) — the same trap documented in debt_cycle.py. Primary path is the CPI index series with
    a real 12-month-ago comparison; the fallback is stamped so a reader knows which one they got."""
    end = today or date.today()
    start = end - timedelta(days=int(365.25 * (years + 1)))
    rows = fmp_func("economic-indicators", {"name": "CPI", "from": start.isoformat(),
                                            "to": end.isoformat()})
    pts = []
    for r in (rows if isinstance(rows, list) else []):
        if isinstance(r, dict) and r.get("date") and isinstance(r.get("value"), (int, float)):
            pts.append((str(r["date"])[:10], float(r["value"])))
    pts.sort(key=lambda t: t[0])
    if len(pts) >= 13:
        yoy = []
        for i, (d, v) in enumerate(pts):
            tgt = (datetime.strptime(d, "%Y-%m-%d").date() - timedelta(days=350)).isoformat()
            prior = [p for p in pts[:i] if p[0] <= tgt]
            if prior and prior[-1][1] > 0:
                yoy.append((d, round((v / prior[-1][1] - 1) * 100, 2)))
        if yoy:
            return yoy, "realized_cpi"
    rows = fmp_func("economic-indicators", {"name": "inflationRate", "from": start.isoformat(),
                                            "to": end.isoformat()})
    pts = [(str(r["date"])[:10], float(r["value"]))
           for r in (rows if isinstance(rows, list) else [])
           if isinstance(r, dict) and r.get("date") and isinstance(r.get("value"), (int, float))]
    pts.sort(key=lambda t: t[0])
    return pts, "expected_inflation_proxy"


def gather(fmp_func, symbols=None, etfs=None, today=None, cache_path=None):
    """Fetch every series, falling back per-series to the local cache (≤14d) then to empty.
    Returns (data, meta) where meta records each series' source so the payload can be honest."""
    symbols = symbols if symbols is not None else CORE_SERIES
    etfs = etfs if etfs is not None else CORE_ETFS
    cache_p = Path(cache_path) if cache_path else CACHE_F
    cache = {}
    if cache_p.exists():
        try:
            cache = json.loads(cache_p.read_text(encoding="utf-8")) or {}
        except Exception:
            cache = {}
    cached_series = cache.get("SERIES") or {}
    cache_asof = cache.get("ASOF")
    stale_days = None
    if cache_asof:
        try:
            stale_days = (date.today() - datetime.strptime(cache_asof, "%Y-%m-%d").date()).days
        except Exception:
            stale_days = None
    cache_usable = stale_days is not None and stale_days <= CACHE_MAX_STALE_DAYS

    data, meta = {}, {"source": {}, "cache_asof": cache_asof, "cache_stale_days": stale_days}
    for sym in list(symbols) + list(etfs):
        rows = _eod(fmp_func, sym, today=today)
        if rows:
            data[sym] = rows
            meta["source"][sym] = "live"
        elif cache_usable and cached_series.get(sym):
            data[sym] = [(d, c) for d, c in cached_series[sym]]
            meta["source"][sym] = "cache"
        else:
            data[sym] = []
            meta["source"][sym] = "missing"

    tr = fmp_func("treasury-rates", {"from": ((today or date.today()) - timedelta(days=400)).isoformat(),
                                     "to": (today or date.today()).isoformat()})
    treasury = sorted([r for r in (tr if isinstance(tr, list) else []) if isinstance(r, dict) and r.get("date")],
                      key=lambda r: r["date"])
    if treasury:
        meta["source"]["TREASURY"] = "live"
    elif cache_usable and cache.get("TREASURY"):
        treasury = cache["TREASURY"]
        meta["source"]["TREASURY"] = "cache"
    else:
        meta["source"]["TREASURY"] = "missing"

    cpi, cpi_basis = _cpi_yoy_series(fmp_func, today=today)
    if cpi:
        meta["source"]["CPI"] = "live"
    elif cache_usable and cache.get("CPI"):
        cpi, cpi_basis = cache["CPI"], cache.get("CPI_BASIS", "cache")
        meta["source"]["CPI"] = "cache"
    else:
        meta["source"]["CPI"] = "missing"
    meta["cpi_basis"] = cpi_basis

    data["_TREASURY"], data["_CPI"] = treasury, cpi
    if any(v == "live" for v in meta["source"].values()):
        try:
            cache_p.parent.mkdir(parents=True, exist_ok=True)
            cache_p.write_text(json.dumps({
                "ASOF": (today or date.today()).isoformat(),
                "SERIES": {k: v for k, v in data.items() if not k.startswith("_") and v},
                "TREASURY": treasury, "CPI": cpi, "CPI_BASIS": cpi_basis}), encoding="utf-8")
        except Exception as e:
            print(f"WARN mining-macro: cache write failed ({e}) — continuing")
    return data, meta


# ────────────────────────────── the dials ──────────────────────────────
def _dial(id_, label, source, **kw):
    d = {"id": id_, "label": label, "source": source}
    d.update(kw)
    return d


def build_dials(data, meta):
    """D1-D8. Every dial carries id/label/source and, where meaningful, a weekly `series` for the
    page's sparkline. A dial with no usable data is emitted with null fields and source=missing —
    never omitted, so the page can say what is broken instead of silently shrinking."""
    src = meta.get("source", {})
    dials = {}

    def s(sym):
        return data.get(sym) or []

    def worst(*syms):
        vals = [src.get(x, "missing") for x in syms]
        return "missing" if "missing" in vals else ("cache" if "cache" in vals else "live")

    # D1 — commodities vs equities (the Costa flagship)
    legs = ["GCUSD", "SIUSD", "HGUSD", "CLUSD"]
    basket_ratio = []
    if all(s(x) for x in legs + ["ESUSD"]):
        common = set(dict(s(legs[0])))
        for x in legs[1:] + ["ESUSD"]:
            common &= set(dict(s(x)))
        dates = sorted(common)
        if dates:
            reb = {}
            for x in legs + ["ESUSD"]:
                m = dict(s(x))
                base = m[dates[0]]
                reb[x] = {d: m[d] / base * 100 for d in dates} if base > 0 else {}
            if all(reb.values()):
                basket_ratio = [(d, statistics.fmean([reb[x][d] for x in legs]) / reb["ESUSD"][d])
                                for d in dates if reb["ESUSD"][d] > 0]
    c3, c12 = _chg(basket_ratio, 63), _chg(basket_ratio, 252)
    dials["commodities_vs_equities"] = _dial(
        "commodities_vs_equities", "Commodities vs equities", worst(*legs, "ESUSD"),
        level=round(basket_ratio[-1][1], 4) if basket_ratio else None,
        chg_3m_pct=round(c3 * 100, 2) if c3 is not None else None,
        chg_12m_pct=round(c12 * 100, 2) if c12 is not None else None,
        pctile=_pctile(basket_ratio[-1][1], [v for _, v in basket_ratio]) if basket_ratio else None,
        pctile_window="6y (own joint history)",
        insufficient_history=len(basket_ratio) < MIN_PCTILE_OBS,
        direction=_direction(c3), series=_weekly(basket_ratio),
        read="An equal-weight gold/silver/copper/oil basket against the S&P. A low percentile means "
             "the complex is historically cheap versus equities; rising off a low percentile is the "
             "Costa setup.")

    # D2 — copper/gold (growth signal)
    cg = _ratio_series(s("HGUSD"), s("GCUSD"))
    c3 = _chg(cg, 63)
    dials["copper_gold"] = _dial(
        "copper_gold", "Copper / gold", worst("HGUSD", "GCUSD"),
        level=round(cg[-1][1], 6) if cg else None,
        chg_3m_pct=round(c3 * 100, 2) if c3 is not None else None,
        pctile=_pctile(cg[-1][1], [v for _, v in cg]) if cg else None,
        pctile_window="6y", insufficient_history=len(cg) < MIN_PCTILE_OBS,
        trend=_trend(cg, c3), series=_weekly(cg),
        read="The market's growth vote. Rising = reflation/industrial bid; falling = a gold-led "
             "defensive or debasement bid.")

    # D3 — silver/gold (debasement risk appetite)
    sg = _ratio_series(s("SIUSD"), s("GCUSD"))
    c3 = _chg(sg, 63)
    dials["silver_gold"] = _dial(
        "silver_gold", "Silver / gold", worst("SIUSD", "GCUSD"),
        level=round(sg[-1][1], 6) if sg else None,
        chg_3m_pct=round(c3 * 100, 2) if c3 is not None else None,
        pctile=_pctile(sg[-1][1], [v for _, v in sg]) if sg else None,
        pctile_window="6y", insufficient_history=len(sg) < MIN_PCTILE_OBS,
        trend=_trend(sg, c3), series=_weekly(sg),
        read="Breadth inside a monetary-metal move. Silver outperforming = speculative breadth "
             "confirming; a gold-only rally is the narrow, fearful phase.")

    # D4 — gold vs real rates. DISPLAY ONLY — excluded from every score by construction.
    gold_yoy = _chg(s("GCUSD"), 252)
    gold_yoy_pct = round(gold_yoy * 100, 2) if gold_yoy is not None else None
    treasury, cpi = data.get("_TREASURY") or [], data.get("_CPI") or []
    real_now = real_1y = real_chg = None
    if treasury and cpi:
        def _y10(row):
            v = row.get("year10")
            return float(v) if isinstance(v, (int, float)) else None
        now_row = next((r for r in reversed(treasury) if _y10(r) is not None), None)
        back = [r for r in treasury if r.get("date", "") <= (
            datetime.strptime(treasury[-1]["date"][:10], "%Y-%m-%d").date() - timedelta(days=365)
        ).isoformat() and _y10(r) is not None]
        prior_row = back[-1] if back else None
        if now_row and cpi:
            real_now = round(_y10(now_row) - cpi[-1][1], 2)
        if prior_row and len(cpi) > 1:
            tgt = (datetime.strptime(prior_row["date"][:10], "%Y-%m-%d").date()).isoformat()
            prior_cpi = [p for p in cpi if p[0] <= tgt]
            if prior_cpi:
                real_1y = round(_y10(prior_row) - prior_cpi[-1][1], 2)
        if real_now is not None and real_1y is not None:
            real_chg = round(real_now - real_1y, 2)
    if gold_yoy_pct is not None and real_chg is not None:
        if gold_yoy_pct >= 10 and real_chg >= 0:
            cls = "debasement_divergence"
        elif (gold_yoy_pct > 0) != (real_chg > 0):
            cls = "classical"
        else:
            cls = "neutral"
    else:
        cls = "unknown"
    dials["gold_vs_real_rates"] = _dial(
        "gold_vs_real_rates", "Gold vs real rates", worst("GCUSD", "TREASURY", "CPI"),
        gold_yoy_pct=gold_yoy_pct, real_10y_now_pct=real_now, real_10y_1y_ago_pct=real_1y,
        real_10y_change_pp=real_chg, classification=cls,
        real_rate_basis=meta.get("cpi_basis"), series=_weekly(s("GCUSD")),
        display_only=True, never_input_to="debt_cycle scoring and the winner scoreboard",
        read="Gold rallying into flat or rising real rates means the classical anchor has broken — "
             "the monetary-debasement tell. DISPLAYED ONLY: this reading scores nothing, here or "
             "in the debt-cycle engine (the momentum-loop guard).")

    # D5 — miners vs metal (are the equities confirming?)
    gdx_gld = _ratio_series(s("GDX"), s("GLD"))
    g3 = _chg(gdx_gld, 63)
    xme_cu = []
    j = _joint(s("XME"), s("HGUSD"))
    if j:
        j = j[-504:]
        b1, b2 = j[0][1], j[0][2]
        if b1 > 0 and b2 > 0:
            xme_cu = [(d, (a / b1) / (b / b2)) for d, a, b in j if b > 0]
    x3 = _chg(xme_cu, 63)
    dials["miners_vs_metal"] = _dial(
        "miners_vs_metal", "Miners vs metal", worst("GDX", "GLD", "XME", "HGUSD"),
        gdx_gld={"level": round(gdx_gld[-1][1], 6) if gdx_gld else None,
                 "chg_3m_pct": round(g3 * 100, 2) if g3 is not None else None,
                 "pctile": _pctile(gdx_gld[-1][1], [v for _, v in gdx_gld]) if gdx_gld else None,
                 "confirmation": _confirmation(g3), "series": _weekly(gdx_gld)},
        xme_copper={"level": round(xme_cu[-1][1], 6) if xme_cu else None,
                    "chg_3m_pct": round(x3 * 100, 2) if x3 is not None else None,
                    "confirmation": _confirmation(x3), "series": _weekly(xme_cu)},
        window_days=63, window_label="3m",
        read="Metal up while its miners lag is an unconfirmed move — paper, or late. Miners leading "
             "means the equity market believes the margin story.")

    # D6 — curve (different tenors from debt_cycle's scored 30y-3m; never scored here)
    s2s10 = s3m10 = d2s10 = d3m10 = None
    if treasury:
        last = treasury[-1]
        def _f(row, k):
            v = row.get(k)
            return float(v) if isinstance(v, (int, float)) else None
        y10, y2, m3 = _f(last, "year10"), _f(last, "year2"), _f(last, "month3")
        if y10 is not None and y2 is not None:
            s2s10 = round((y10 - y2) * 100, 1)
        if y10 is not None and m3 is not None:
            s3m10 = round((y10 - m3) * 100, 1)
        prior = treasury[max(0, len(treasury) - 64)]
        py10, py2, pm3 = _f(prior, "year10"), _f(prior, "year2"), _f(prior, "month3")
        if s2s10 is not None and py10 is not None and py2 is not None:
            d2s10 = round(s2s10 - (py10 - py2) * 100, 1)
        if s3m10 is not None and py10 is not None and pm3 is not None:
            d3m10 = round(s3m10 - (py10 - pm3) * 100, 1)

    def _shape(bp):
        if bp is None:
            return "unknown"
        return "inverted" if bp < 0 else ("flat" if bp <= 50 else "steep")
    dials["curve"] = _dial(
        "curve", "Yield curve", src.get("TREASURY", "missing"),
        spread_2s10s_bp=s2s10, spread_3m10y_bp=s3m10, chg_3m_2s10s_bp=d2s10, chg_3m_3m10y_bp=d3m10,
        shape_2s10s=_shape(s2s10), shape_3m10y=_shape(s3m10),
        motion=("steepening" if (d2s10 or 0) > 0 else "flattening") if d2s10 is not None else "unknown",
        asof=treasury[-1].get("date") if treasury else None,
        read="Displayed, never scored here — the debt-cycle engine scores its own 30y-3m term "
             "premium on different tenors. Steepening off inversion is the classic cycle-turn tell.")

    # D7 — DXY
    dxy = s("DXUSD")
    c3, c12 = _chg(dxy, 63), _chg(dxy, 252)
    dials["dxy"] = _dial(
        "dxy", "US dollar (DXY)", src.get("DXUSD", "missing"),
        level=round(dxy[-1][1], 4) if dxy else None,
        chg_3m_pct=round(c3 * 100, 2) if c3 is not None else None,
        chg_12m_pct=round(c12 * 100, 2) if c12 is not None else None,
        pctile=_pctile(dxy[-1][1], [v for _, v in dxy]) if dxy else None,
        pctile_window="6y", insufficient_history=len(dxy) < MIN_PCTILE_OBS,
        trend=_trend(dxy, c3), series=_weekly(dxy),
        read="A falling dollar is a broad tailwind for the whole complex; a rising one is the "
             "headwind every commodity thesis has to survive.")

    # D8 — per-commodity momentum table
    rows = []
    for sym, label in MOMENTUM_TABLE:
        ser = s(sym)
        m12, m3 = _chg(ser, 252), _chg(ser, 63)
        closes = [c for _, c in ser]
        hi52 = max(closes[-252:]) if len(closes) >= 20 else None
        row = {"symbol": sym, "label": label, "is_proxy": sym in ("URA",),
               "mom_12m_pct": round(m12 * 100, 2) if m12 is not None else None,
               "mom_3m_pct": round(m3 * 100, 2) if m3 is not None else None,
               "pctile_5y": _pctile(closes[-1], closes[-1260:]) if closes else None,
               "off_52wk_high_pct": (round((closes[-1] / hi52 - 1) * 100, 2)
                                     if hi52 and closes and hi52 > 0 else None),
               "source": src.get(sym, "missing"), "series": _weekly(ser)}
        if row["is_proxy"]:
            row["proxy_note"] = "ETF proxy — carries equity beta, not uranium spot (no uranium spot on FMP)"
        rows.append(row)
    dials["momentum_table"] = _dial(
        "momentum_table", "Commodity momentum", worst(*[x for x, _ in MOMENTUM_TABLE]), rows=rows,
        read="Each commodity's 12-month move and where today's price sits in its own 5-year range.")
    return dials


# ────────────────────────────── the winner scoreboard ──────────────────────────────
def _is_monetary(chain):
    c = chain.get("commodity") or {}
    if isinstance(c.get("monetary_metal"), bool):
        return c["monetary_metal"]
    return (c.get("fmp_symbol") in ("GCUSD", "SIUSD")) or (c.get("proxy_etf") in ("GDX", "SIL"))


def build_scoreboard(data, meta, taxonomy, regime, phase):
    """0-100 per Mining chain from four legs (setup 30 / momentum 30 / confirmation 20 / tilt 20).

    Rows come from the taxonomy, never a hardcoded chain list. Every missing leg pays its exact
    neutral midpoint so an outage compresses all rows symmetrically — a data gap can never single
    out a chain (the display analog of "never tighten the book").

    MONETARY-METAL EXCLUSION (the gold seam): a chain flagged `monetary_metal` scores NEUTRAL on the
    momentum leg, and on the setup leg whenever the only available basis would be its own price
    percentile. It ranks on miners-confirmation, the Dalio tilt, and genuine cost-curve economics
    (`vs_incentive_pct`) — never on gold's price action."""
    src = meta.get("source", {})
    tilt_pts = PHASE_TILT_POINTS.get(str(phase or "UNKNOWN").upper(), PHASE_TILT_POINTS["UNKNOWN"])
    rows = []
    for ch in taxonomy.get("chains", []):
        cid = ch.get("id")
        c = ch.get("commodity") or {}
        sym = c.get("fmp_symbol") or c.get("proxy_etf")
        ser = data.get(sym) or [] if sym else []
        monetary = _is_monetary(ch)
        live_legs = 0

        # ── setup leg (30) — cost-curve economics, never price momentum
        rs = (regime or {}).get(cid) or {}
        vs_inc, as_of = rs.get("vs_incentive_pct"), rs.get("as_of")
        fresh = False
        if isinstance(vs_inc, (int, float)) and as_of:
            try:
                fresh = (date.today() - datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()).days <= 45
            except Exception:
                fresh = False
        if fresh:
            setup, setup_src = max(0.0, min(30.0, 15 - vs_inc * 0.5)), "vs_incentive"
            live_legs += 1
        elif monetary:
            # the proxy would be gold's own price percentile — forbidden. Neutral, stamped.
            setup, setup_src = NEUTRAL_SETUP, "monetary_metal_excluded"
        else:
            closes = [x for _, x in ser]
            p = _pctile(closes[-1], closes[-1260:]) if closes else None
            if p is None:
                setup, setup_src = NEUTRAL_SETUP, "missing_neutral"
            else:
                setup, setup_src = round((100 - p) * 0.30, 1), "percentile_proxy"
                live_legs += 1

        # ── momentum leg (30) — hard-excluded for monetary metals
        if monetary:
            mom, mom_src, mom_pctile = NEUTRAL_MOM, "monetary_metal_excluded", None
        else:
            cur = _chg(ser, 252)
            hist = _rolling_12m_returns(ser)
            mom_pctile = _pctile(cur, hist) if cur is not None else None
            if mom_pctile is None:
                mom, mom_src = NEUTRAL_MOM, "missing_neutral"
            else:
                mom, mom_src = round(0.30 * mom_pctile, 1), "live"
                live_legs += 1

        # ── miners-confirmation leg (20)
        metal, etf = c.get("fmp_symbol"), c.get("proxy_etf")
        if metal and etf and data.get(metal) and data.get(etf):
            ratio = []
            j = _joint(data[etf], data[metal])
            if j:
                j = j[-504:]
                b1, b2 = j[0][1], j[0][2]
                if b1 > 0 and b2 > 0:
                    ratio = [(d, (a / b1) / (b / b2)) for d, a, b in j if b > 0]
            ch3 = _chg(ratio, 63)
            if ch3 is None:
                conf, conf_src = NEUTRAL_CONF, "missing_neutral"
            else:
                conf = 20.0 if ch3 >= 0.02 else (0.0 if ch3 <= -0.02 else 10.0)
                conf_src = "live"
                live_legs += 1
        elif etf and not metal:
            conf, conf_src = NEUTRAL_CONF, "n/a_proxy_only"
        else:
            conf, conf_src = NEUTRAL_CONF, "missing_neutral"

        tilt = float(tilt_pts["monetary" if monetary else "industrial"])
        score = round(setup + mom + conf + tilt, 1)
        rows.append({
            "chain_id": cid, "chain_name": ch.get("name", cid), "symbol": sym,
            "is_proxy": not bool(c.get("fmp_symbol")), "monetary_metal": monetary,
            "score": score,
            "legs": {
                "setup": {"points": round(setup, 1), "max": 30, "source": setup_src,
                          "vs_incentive_pct": vs_inc if fresh else None, "as_of": as_of if fresh else None},
                "momentum": {"points": round(mom, 1), "max": 30, "source": mom_src,
                             "mom_pctile": mom_pctile},
                "confirmation": {"points": round(conf, 1), "max": 20, "source": conf_src},
                "tilt": {"points": tilt, "max": 20, "source": "debt_cycle_phase", "phase": phase},
            },
            "regime_state": rs.get("state"),
            "confidence": "high" if live_legs >= 3 else ("med" if live_legs == 2 else "low"),
            "data_source": src.get(sym, "missing") if sym else "missing",
        })
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


# ────────────────────────────── assembly ──────────────────────────────
def build_payload(data, meta, taxonomy, regime, snapshot, today=None):
    import _commodity_tilt as CT
    dc = (snapshot or {}).get("debt_cycle") or {}
    phase = dc.get("debt_cycle_phase") or "UNKNOWN"
    quadrant = (snapshot or {}).get("quadrant") or "UNKNOWN"
    dials = build_dials(data, meta)
    board = build_scoreboard(data, meta, taxonomy, regime, phase)
    non_live = sorted({k for k, v in meta.get("source", {}).items() if v != "live"})
    degraded = bool(non_live)
    banner = ""
    if degraded:
        cached = [k for k in non_live if meta["source"][k] == "cache"]
        missing = [k for k in non_live if meta["source"][k] == "missing"]
        parts = []
        if cached:
            parts.append(f"cached data from {meta.get('cache_asof')} for {', '.join(cached)}")
        if missing:
            parts.append(f"NO data for {', '.join(missing)} (those dials read blank)")
        banner = ("Macro dials degraded: " + "; ".join(parts)
                  + ". Readings may be stale — scores compress toward neutral by design, they are "
                    "never tightened by a data gap.")
    return {
        "version": VERSION,
        "generated_at": (today or date.today()).isoformat(),
        "taxonomy_version": taxonomy.get("version"),
        "debt_cycle_phase": phase,
        "quadrant": quadrant,
        "quadrant_basis": (snapshot or {}).get("quadrant_basis", ""),
        "risk_regime": (snapshot or {}).get("regime"),
        "risk_score": (snapshot or {}).get("score"),
        "regime_detail": (snapshot or {}).get("regime_detail") or {},
        "macro_asof": dc.get("asof") or (snapshot or {}).get("as_of"),
        # The debt-cycle detail the /commodities macro header renders (gauge strip with its live/
        # missing chips, hysteresis state, seeded/confidence honesty flags, and the gold
        # falsification chip). Carried HERE rather than published as a second GCS object: this mode
        # already reads the snapshot, so one producer and one fetch means the header can never
        # disagree with the tilt and scoreboard rendered beside it. Everything is passed through
        # verbatim — this module computes no phase and scores nothing from it.
        "debt_cycle": {
            "phase": phase,
            "phase_basis": dc.get("phase_basis", ""),
            "phase_detail": dc.get("phase_detail", ""),
            "weeks_in_phase": dc.get("weeks_in_phase"),
            "prior_phase": dc.get("prior_phase"),
            "cycle_score": dc.get("cycle_score"),
            "cycle_target": dc.get("cycle_target"),
            "pending_target": dc.get("pending_target"),
            "pending_count": dc.get("pending_count"),
            "transition_blocked": dc.get("transition_blocked"),
            "transition_implied": dc.get("transition_implied"),
            "sub_scores": dc.get("cycle_sub_scores") or {},
            "sub_sources": dc.get("cycle_sub_sources") or {},
            "confidence": dc.get("confidence"),
            "seeded": bool(dc.get("seeded")),
            "reserve_asset_check": dc.get("reserve_asset_check") or {},
            "expected_horizon_months": dc.get("expected_horizon_months"),
            "sub_score_convention": "INVERTED vs the risk regime — higher = LATER in the cycle / more stress",
        },
        "dials": dials,
        "scoreboard": board,
        "scoreboard_authority": (
            "Ranks commodity setups for display and Director citation ONLY. Never gates membership, "
            "never sizes, never touches conviction. The Mining debate pipeline selects picks."),
        "tilt": CT.tilt_payload(phase, quadrant),
        "gold_note": (
            "Gold and silver dials here are DISPLAY DATA. Gold is a falsification check only inside "
            "the debt-cycle engine, and the monetary-metal chain's momentum and price-percentile "
            "legs are neutralized in the scoreboard above — gold's own price action scores nothing."),
        "degraded": degraded,
        "stale_banner": banner,
        "sources": meta.get("source", {}),
        "cpi_basis": meta.get("cpi_basis"),
    }


def run(fmp_func, today=None, tax_path=None, regime_path=None, snapshot_path=None, out_path=None,
        cache_path=None):
    """Gather -> build -> write. Always writes a payload; returns it."""
    import sys
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    tax = json.loads(Path(tax_path or TAX_F).read_text(encoding="utf-8"))
    regime = {}
    rp = Path(regime_path or REGIME_F)
    if rp.exists():
        try:
            regime = json.loads(rp.read_text(encoding="utf-8")) or {}
        except Exception:
            regime = {}
    if not regime:
        print("WARN mining-macro: no mining/regime_state.json — the setup leg falls back to the "
              "percentile proxy (fail-open, stamped in every row)")
    snapshot = {}
    sp = Path(snapshot_path or MACRO_SNAPSHOT_F)
    if sp.exists():
        try:
            snapshot = json.loads(sp.read_text(encoding="utf-8")) or {}
        except Exception:
            snapshot = {}
    if not snapshot:
        print("WARN mining-macro: no macro_regime.json — Dalio tilt is UNKNOWN (neutral 10/10 "
              "points, fail-open)")
    etfs = sorted(set(CORE_ETFS) | {(c.get("commodity") or {}).get("proxy_etf")
                                    for c in tax.get("chains", [])} - {None})
    data, meta = gather(fmp_func, etfs=etfs, today=today, cache_path=cache_path)
    payload = build_payload(data, meta, tax, regime, snapshot, today=today)
    out = Path(out_path or OUT_F)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    board = payload["scoreboard"]
    print(f"mining-macro: {len(payload['dials'])} dials, {len(board)} chains scored "
          f"(phase {payload['debt_cycle_phase']} x quadrant {payload['quadrant']}) -> {out}")
    for r in board:
        excl = " [monetary-metal: momentum excluded]" if r["monetary_metal"] else ""
        print(f"  #{r['rank']} {r['chain_id']:<22} {r['score']:>5}/100  "
              f"setup {r['legs']['setup']['points']} · mom {r['legs']['momentum']['points']} · "
              f"conf {r['legs']['confirmation']['points']} · tilt {r['legs']['tilt']['points']}  "
              f"({r['confidence']}){excl}")
    if payload["degraded"]:
        print(f"  DEGRADED: {payload['stale_banner']}")
    return payload
