#!/usr/bin/env python3
"""Deterministic margin-torque / cost-curve metrics for the FUTURE RESOURCES Lane A book
(FUTURE_RESOURCES_SPEC.md §3, Phase 2). Shared-module extraction precedent: _moat.py.

These are HONEST PROXIES computed from the Stage-B FMP fetches (no AISC endpoint exists on FMP),
stamped into the grade input so the Director scores on them. They are Director SCORING INPUTS,
NEVER a ranking that picks members (deterministic-guards-never-pick, Do-NOT #2).

Per the taxonomy (future_resources_chains.json, versioned — Do-NOT #9): a chain with
torque_metrics != false (the four commodity/power chains) gets the TORQUE set —
  - ebitda_margin_ttm + ebitda_margin_band : TTM EBITDA / revenue; band = percentile WITHIN the
    chain cohort (cohorts < 8 names fall back to fixed bands >45% / 25-45% / <25% — percentiles are
    unstable on n=6 uranium). Highest margin at the same commodity price ~ lowest cost quartile:
    the cost-curve-position proxy.
  - fcf_torque_10pct : (0.10 x TTM revenue x commodity_revenue_share) / max(TTM EBITDA, eps). The
    % EBITDA uplift from a +10% commodity move. SYMMETRIC — the Director must read it as downside
    torque too (Do-NOT #7).
  - commodity_beta_2y : 2y weekly log-return regression vs the chain's commodity.fmp_symbol (or the
    proxy_etf when the commodity is off-FMP — beta_is_proxy=true). A "producer" with beta ~ 0 is
    hedged or mislabeled. Reuses _post_common.weekly_logrets / get_market / _beta.
  - ndebt_ebitda : reused from the Stage-B funded-leverage fetch (net_funded_debt_ebitda). Torque x
    leverage is the blow-up quadrant.
A chain with torque_metrics=false (robotics_automation, quantum) gets NO torque metrics — there is
no spot price to be leveraged to, and pretending an ETF is one would be a fabricated number. Their
set is gm_trajectory (direction + 3-yr numbers) / rev_yoy / fcf_margin / ndebt_ebitda; commodity_beta_2y
is still computed vs the proxy_etf (BOTZ/QTUM), clearly labeled a proxy factor-exposure read.

Usage:
    from _resource_metrics import compute            # fr_input stamps compute(members) into the grade input
    python _resource_metrics.py CCJ FCX MP           # standalone: metrics for named lane-A symbols (uses _candidates.json gates)
    python _resource_metrics.py --offline CCJ FCX MP # reuse the cached 2y charts (idempotent)
"""
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../backend/_opus_debate
BK = os.path.dirname(_HERE)                             # .../backend
ROOT_DIR = os.path.dirname(BK)                          # .../Stock-Screener
sys.path.insert(0, BK)
os.chdir(BK)
if hasattr(sys.stdout, "reconfigure"):                 # Windows console is cp1252 — keep prose prints safe
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# FMP key: prefer the real key from frontend/.env.local (house rule) BEFORE importing screener_v6,
# which freezes FMP_KEY at import; fall back to the shared demo key (the _value_post pattern).
if not os.environ.get("FMP_API_KEY"):
    _env = Path(ROOT_DIR) / "frontend" / ".env.local"
    if _env.exists():
        for _line in _env.read_text(encoding="utf-8").splitlines():
            if _line.strip().startswith("FMP_API_KEY=") and "=" in _line:
                os.environ["FMP_API_KEY"] = _line.split("=", 1)[1].strip().replace('"', "").replace("'", "")
                break
if not os.environ.get("FMP_API_KEY"):
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
from screener_v6 import fmp, get_chart                  # noqa: E402  FMP REST + OHLCV
sys.path.insert(0, _HERE)                              # so the sibling _post_common resolves
import _post_common as _pc                              # noqa: E402  shared weekly_logrets / get_market / _beta

ROOT = Path("_opus_debate")
FR_DIR = ROOT / "future_resources"
TAX_F = ROOT / "future_resources_chains.json"
CAND_F = FR_DIR / "_candidates.json"
CACHE_F = FR_DIR / "_resource_metrics_cache.json"

TORQUE_EPS = 1.0                                        # div-by-zero guard for fcf_torque (lane A requires EBITDA>0)


def _tax():
    return json.load(open(TAX_F, encoding="utf-8"))


def _chain_by_id(tax=None):
    tax = tax or _tax()
    return {c["id"]: c for c in tax.get("chains", [])}


def _beta_symbol(chain):
    """The commodity to regress against: the FMP spot symbol when it exists, else the proxy ETF."""
    com = chain.get("commodity") or {}
    return com.get("fmp_symbol") or com.get("proxy_etf")


def _ebitda_margin(g):
    rev, ebitda = g.get("ttm_revenue"), g.get("ttm_ebitda")
    if isinstance(rev, (int, float)) and isinstance(ebitda, (int, float)) and rev > 0:
        return ebitda / rev
    return None


def _fcf_margin(g):
    rev, fcf = g.get("ttm_revenue"), g.get("ttm_fcf")
    if isinstance(rev, (int, float)) and isinstance(fcf, (int, float)) and rev > 0:
        return round(fcf / rev, 4)
    return None


def _fcf_torque(g, crs):
    """% EBITDA uplift from a +10% commodity move — SYMMETRIC (downside too). Needs the chain-map
    commodity_revenue_share; None when it or EBITDA is missing/non-positive (a producer that fails
    the EBITDA gate is not lane A anyway)."""
    rev, ebitda = g.get("ttm_revenue"), g.get("ttm_ebitda")
    if not (isinstance(rev, (int, float)) and rev > 0 and isinstance(crs, (int, float)) and crs >= 0):
        return None
    if not isinstance(ebitda, (int, float)) or ebitda <= 0:
        return None                                    # torque is undefined on non-positive EBITDA
    return round((0.10 * rev * crs) / max(ebitda, TORQUE_EPS), 3)


def _band(em, cohort):
    """Cost-curve-position band. Cohort >= 8: quartile by percentile of the name's margin within the
    chain cohort (higher margin at the same commodity price = lower on the cost curve). Cohort < 8:
    fixed absolute bands (>45% / 25-45% / <25%) — percentiles are unstable on n=6 (uranium)."""
    if em is None:
        return None
    n = len(cohort)
    if n >= 8:
        pct = sum(1 for x in cohort if x < em) / n      # fraction of the cohort this name beats
        if pct >= 0.75:
            band = "q1_low_cost"
        elif pct >= 0.50:
            band = "q2_below_median"
        elif pct >= 0.25:
            band = "q3_above_median"
        else:
            band = "q4_high_cost"
        return {"band": band, "pct": round(pct, 2), "basis": "cohort_percentile", "n_cohort": n}
    # fixed absolute bands
    if em > 0.45:
        band = "high(>45%)"
    elif em >= 0.25:
        band = "mid(25-45%)"
    else:
        band = "low(<25%)"
    return {"band": band, "pct": None, "basis": "fixed_bands", "n_cohort": n}


def _gm_trajectory(sym, offline):
    """Non-commodity chains' pricing-power lie detector: 3-4y annual gross-margin direction + numbers.
    Deterministic FMP annual income-statement fetch; offline / on failure -> None (never fabricated)."""
    if offline:
        return None
    try:
        ann = fmp("income-statement", {"symbol": sym, "period": "annual", "limit": 4}) or []
    except Exception:
        return None
    gms = []
    for row in ann:                                     # FMP returns newest-first
        rev, gp = row.get("revenue"), row.get("grossProfit")
        if isinstance(rev, (int, float)) and rev > 0 and isinstance(gp, (int, float)):
            gms.append(round(gp / rev, 4))
    if len(gms) < 2:
        return None
    latest, oldest = gms[0], gms[-1]                    # gms[0]=newest
    delta = round(latest - oldest, 4)
    direction = "expanding" if delta > 0.01 else ("compressing" if delta < -0.01 else "flat")
    return {"direction": direction, "gm_recent_to_old": list(reversed(gms)), "delta_3y": delta}


def compute(members, offline=False):
    """members: list of dicts each with symbol, chains(list), commodity_revenue_share(float|None),
    business_model(str), gates(dict incl. ttm_revenue/ttm_ebitda/ttm_fcf/rev_yoy/net_funded_debt_ebitda).
    Returns {symbol: metrics_dict}. Deterministic + offline-tolerant (a chart fetch that fails leaves
    commodity_beta_2y=None, never a fabricated value)."""
    chains = _chain_by_id()
    prim = {}                                           # symbol -> primary chain id (chains[0])
    bench = set()
    quote_syms = []
    for m in members:
        sym = m.get("symbol")
        if not sym:
            continue
        cid = (m.get("chains") or [None])[0]
        prim[sym] = cid
        quote_syms.append(sym)
        ch = chains.get(cid)
        if ch:
            bs = _beta_symbol(ch)
            if bs:
                bench.add(bs)
    corr_syms = sorted(set(quote_syms) | bench)         # member charts + benchmark charts for the regression
    # quotes are unused here (metrics are fundamentals-based) — pass [] to skip the batch-quote call.
    _q, weekly, asof = _pc.get_market([], corr_syms, offline, CACHE_F,
                                      quotes_fn=lambda ss: {}, chart_fn=lambda s: get_chart(s, days=760))
    # per-chain cohort of EBITDA margins (torque chains only) for the band percentile
    cohort = {}
    for m in members:
        cid = prim.get(m.get("symbol"))
        ch = chains.get(cid) or {}
        if not bool(ch.get("torque_metrics", True)):
            continue
        em = _ebitda_margin(m.get("gates") or {})
        if em is not None:
            cohort.setdefault(cid, []).append(em)
    out = {}
    for m in members:
        sym = m.get("symbol")
        if not sym:
            continue
        cid = prim.get(sym)
        ch = chains.get(cid) or {}
        torque_on = bool(ch.get("torque_metrics", True))
        g = m.get("gates") or {}
        crs = m.get("commodity_revenue_share")
        bsym = _beta_symbol(ch)
        beta = _pc._beta(weekly.get(sym), weekly.get(bsym)) if bsym else None
        ndebt = g.get("net_funded_debt_ebitda")
        beta_is_proxy = ((ch.get("commodity") or {}).get("fmp_symbol") is None)
        mt = {"chain": cid, "torque_metrics": torque_on,
              "commodity_beta_2y": round(beta, 2) if isinstance(beta, (int, float)) else None,
              "beta_benchmark": bsym, "beta_is_proxy": beta_is_proxy,
              "ndebt_ebitda": round(ndebt, 2) if isinstance(ndebt, (int, float)) else None,
              "commodity_revenue_share": crs, "as_of": asof}
        if torque_on:
            em = _ebitda_margin(g)
            mt["ebitda_margin_ttm"] = round(em, 4) if em is not None else None
            mt["ebitda_margin_band"] = _band(em, cohort.get(cid, []))
            mt["fcf_torque_10pct"] = _fcf_torque(g, crs)
            mt["torque_note"] = ("SYMMETRIC: fcf_torque_10pct is the +/-10% commodity move's % EBITDA swing "
                                 "(read the downside too). beta_is_proxy=" + str(beta_is_proxy)
                                 + " (proxy ETF regression where the spot is off-FMP).")
        else:
            mt["gm_trajectory"] = _gm_trajectory(sym, offline)
            mt["rev_yoy"] = g.get("rev_yoy")
            mt["fcf_margin"] = _fcf_margin(g)
            mt["torque_note"] = ("NON-COMMODITY chain (no spot to lever to): no torque metric. "
                                 "commodity_beta_2y is a PROXY factor-exposure read vs " + str(bsym)
                                 + ", not a commodity torque.")
        out[sym] = mt
    return out


def _members_from_candidates(symbols):
    """Standalone helper: build member rows for named symbols from _candidates.json (Stage-B gates +
    chains_hint). commodity_revenue_share is not known pre-chain-map, so it defaults to 1.0 (pure
    producer) — flagged in the printout as an assumption for the standalone test only."""
    if not CAND_F.exists():
        print(f"GUARD: {CAND_F} not found — run fr-universe first (standalone test needs the gates). STOP")
        raise SystemExit(1)
    cand = {c["symbol"]: c for c in json.load(open(CAND_F, encoding="utf-8")).get("candidates", [])}
    members = []
    for s in symbols:
        c = cand.get(s)
        if not c:
            print(f"  WARN: {s} not in _candidates.json — skipped")
            continue
        members.append({"symbol": s, "chains": c.get("chains_hint") or [], "business_model": "",
                        "commodity_revenue_share": 1.0, "gates": c.get("gates") or {}})
    return members


def main():
    offline = "--offline" in sys.argv
    symbols = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not symbols:
        print("usage: python _resource_metrics.py [--offline] SYM [SYM ...]")
        raise SystemExit(1)
    members = _members_from_candidates(symbols)
    if not members:
        print("no valid symbols found in _candidates.json")
        raise SystemExit(1)
    print(f"_resource_metrics: {len(members)} symbol(s) | commodity_revenue_share defaulted to 1.0 "
          f"(standalone — the chain map supplies the real share in fr-input) | offline={offline}")
    res = compute(members, offline=offline)
    for sym in symbols:
        m = res.get(sym)
        if m:
            print(f"\n=== {sym} [{m.get('chain')}] torque_metrics={m.get('torque_metrics')} ===")
            print(json.dumps(m, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
