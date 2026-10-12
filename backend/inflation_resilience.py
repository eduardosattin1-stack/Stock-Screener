#!/usr/bin/env python3
"""
Inflation resilience — deterministic per-name label (2026-10-12, Bruno-approved)
================================================================================
The question: when input and wage costs ran hot in 2021-22, did this business keep its
margins (it could pass the costs on) or did they get squeezed? That is the MEASURED half
of "pricing power". The other half — a dated sign in the latest transcript that price
increases are sticking — stays with the underwriters, as prose in macro_fit_note.

Label = gross-margin change from the last pre-COVID fiscal year to the WORST fiscal year
of the 2021-22 inflation shock:
  resilient   change >= -1.0pp
  mixed       -4.0pp <= change < -1.0pp
  exposed     change < -4.0pp
  unknown     not measurable: financials (no cost-of-sales line), no pre-2020 or no
              2021-22 annual statement, a zero/negative cost-of-sales line, or a gross
              margin that jumps > 12pp while operating margin barely moves (a cost
              reclassification, not pricing)

Years are picked by fiscal PERIOD-END date, never the fiscalYear label, so January
(retail) and September (UK) year-ends land in the right window:
  baseline = the latest year ending 2019-01-01 .. 2020-02-29
  shock    = every year ending 2021-07-01 .. 2023-06-30 (the worst gross margin counts)

AUTHORITY: none over weights, seats, eligibility or conviction (CLAUDE.md FORK 2/B — the
macro gives direction, it does not weigh on the picks). It is a judgement input for the
Director and context for the underwriter's macro_fit, exactly like phase_fit. 'unknown' is
never a penalty. The thresholds are hand-tuned priors: score them against realized returns
before giving this label any teeth.

Statement history is immutable, so it is cached in _opus_debate/_inflation_resilience_cache.json
(re-fetched only when missing or older than 180 days).

CLI:  python backend/inflation_resilience.py KO JPM ADBE      (spot-check; prints labels)
"""

import json
import logging
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
CACHE_F = HERE / "_opus_debate" / "_inflation_resilience_cache.json"
OUT_F = HERE / "_opus_debate" / "inflation_resilience.json"

BASE_WINDOW = ("2019-01-01", "2020-02-29")
SHOCK_WINDOW = ("2021-07-01", "2023-06-30")
RESILIENT_MIN_PP = -1.0
EXPOSED_BELOW_PP = -4.0
RECLASS_GM_PP = 12.0       # a gross-margin move bigger than this ...
RECLASS_OM_PP = 3.0        # ... with operating margin moving less than this = reclassification
CACHE_MAX_AGE_DAYS = 180
ROYALTY_GM_PCT = 95.0      # base gross margin at/above this = royalty/licensing P&L (ZEAL.CO 99% -> 59%)
FINANCIAL_SECTORS = {"financial services", "financials", "financial", "banks", "insurance"}
METHOD = ("gross-margin change, worst fiscal year ending 2021-07..2023-06 vs the last "
          "fiscal year ending 2019-01..2020-02")

PLAIN = {
    "resilient": "kept its margins through the 2021-22 inflation",
    "mixed": "its margins dipped in the 2021-22 inflation",
    "exposed": "its margins were squeezed by the 2021-22 inflation",
    "unknown": "inflation resilience not measurable from its accounts",
}


def _num(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _margins(row: dict):
    """(gross margin %, operating margin %) for one annual statement. Gross margin is None
    when there is no positive cost-of-sales line (banks book interest expense there and it
    goes negative - JPM FY2021)."""
    rev = _num(row.get("revenue"))
    if not rev or rev <= 0:
        return None, None
    cogs, gp, oi = _num(row.get("costOfRevenue")), _num(row.get("grossProfit")), _num(row.get("operatingIncome"))
    gm = 100.0 * gp / rev if (cogs is not None and cogs > 0 and gp is not None) else None
    om = 100.0 * oi / rev if oi is not None else None
    return gm, om


def _unknown(source: str, basis: str) -> dict:
    return {"inflation_resilience": "unknown", "inflation_resilience_source": source,
            "inflation_resilience_basis": basis, "inflation_resilience_plain": PLAIN["unknown"],
            "inflation_resilience_method": METHOD}


def classify(statements: list, sector: Optional[str] = None) -> dict:
    """PURE: annual income statements (any order, FMP field names) + sector -> label dict."""
    if sector and str(sector).strip().lower() in FINANCIAL_SECTORS:
        return _unknown("financials", f"{sector}: no cost-of-sales line, so margin pass-through "
                                      f"is not measurable")
    rows = [(str(r.get("date") or "")[:10], r) for r in (statements or []) if isinstance(r, dict)]
    rows = [(d, r) for d, r in rows if len(d) == 10]
    base = [(d, r) for d, r in rows if BASE_WINDOW[0] <= d <= BASE_WINDOW[1]]
    shock = [(d, r) for d, r in rows if SHOCK_WINDOW[0] <= d <= SHOCK_WINDOW[1]]
    if not base:
        return _unknown("no_history", "no annual statement ending 2019-01..2020-02 (listed later "
                                      "or no filings that far back)")
    if not shock:
        return _unknown("no_history", "no annual statement ending 2021-07..2023-06")
    bd, br = max(base, key=lambda x: x[0])
    gm0, om0 = _margins(br)
    shock_m = [(d,) + _margins(r) for d, r in shock]
    if gm0 is None or any(gm is None for _, gm, _ in shock_m):
        return _unknown("no_cogs", "no positive cost-of-sales line in the 2019 or 2021-22 filings "
                                   "(bank/insurer-style accounts) - gross margin not measurable")
    if gm0 >= ROYALTY_GM_PCT:
        return _unknown("no_cogs", f"gross margin {gm0:.1f}% in the base year - a royalty/licensing-style "
                                   f"P&L with no meaningful cost of sales, so a later drop reflects a "
                                   f"revenue-mix change, not pricing")
    wd, gm1, om1 = min(shock_m, key=lambda x: x[1])
    d_gm = gm1 - gm0
    d_om = (om1 - om0) if (om0 is not None and om1 is not None) else None
    nums = {"gm_base_pct": round(gm0, 1), "gm_shock_pct": round(gm1, 1), "gm_change_pp": round(d_gm, 1),
            "om_change_pp": round(d_om, 1) if d_om is not None else None,
            "base_fy_end": bd, "shock_fy_end": wd}
    if abs(d_gm) > RECLASS_GM_PP and (d_om is None or abs(d_om) < RECLASS_OM_PP):
        om_txt = "n/a" if d_om is None else f"{d_om:+.1f}pp"
        out = _unknown("reclassified", f"gross margin moved {d_gm:+.1f}pp ({bd[:7]} -> {wd[:7]}) while "
                                       f"operating margin moved {om_txt} - looks like a cost "
                                       f"reclassification, not pricing")
        out.update(nums)
        return out
    label = "resilient" if d_gm >= RESILIENT_MIN_PP else ("mixed" if d_gm >= EXPOSED_BELOW_PP else "exposed")
    om_txt = f", operating margin {d_om:+.1f}pp" if d_om is not None else ""
    out = {"inflation_resilience": label, "inflation_resilience_source": "computed",
           "inflation_resilience_basis": (f"gross margin {gm0:.1f}% (year to {bd[:7]}) -> {gm1:.1f}% in the "
                                          f"worst inflation year (year to {wd[:7]}) = {d_gm:+.1f}pp{om_txt}"),
           "inflation_resilience_plain": PLAIN[label], "inflation_resilience_method": METHOD}
    out.update(nums)
    return out


# ---------------------------------------------------------------------------
# Fetch + cache
# ---------------------------------------------------------------------------

_KEEP = ("date", "fiscalYear", "period", "reportedCurrency", "revenue", "costOfRevenue",
         "grossProfit", "operatingIncome")


def _fmp_key() -> str:
    k = os.environ.get("FMP_API_KEY", "")
    if k:
        return k
    try:
        sys.path.insert(0, str(HERE))
        import live_debate_engine as E
        E.load_api_keys()
        return E.get_key("FMP_API_KEY") or ""
    except Exception:
        return ""


def fetch_statements(sym: str, key: str) -> Optional[list]:
    """Annual income statements (10y) from FMP stable, trimmed to the fields classify uses.
    None on any error (the caller does not cache a failure)."""
    import requests
    try:
        r = requests.get("https://financialmodelingprep.com/stable/income-statement",
                         params={"symbol": sym, "period": "annual", "limit": 10, "apikey": key},
                         timeout=30)
        if r.status_code != 200:
            return None
        j = r.json()
    except Exception:
        return None
    if not isinstance(j, list):
        return None
    return [{k: x.get(k) for k in _KEEP} for x in j if isinstance(x, dict)]


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _stale(entry: Optional[dict], today: datetime) -> bool:
    if not entry or not entry.get("fetched"):
        return True
    try:
        return (today - datetime.strptime(entry["fetched"][:10], "%Y-%m-%d")).days > CACHE_MAX_AGE_DAYS
    except ValueError:
        return True


def build(sym_sector: dict, out_path: Path = OUT_F, cache_path: Path = CACHE_F,
          max_workers: int = 8, verbose: bool = True) -> dict:
    """Label every symbol in {symbol: sector}, write out_path, return the document.
    Fail-open: a name whose statements cannot be fetched is 'unknown', never dropped."""
    today = datetime.now()
    cache = _load_cache(cache_path)
    todo = [s for s in sym_sector if _stale(cache.get(s), today)]
    failed = []
    if todo:
        key = _fmp_key()
        if not key:
            print("WARN inflation-resilience: no FMP key - every un-cached name reads unknown")
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                for sym, rows in zip(todo, ex.map(lambda s: fetch_statements(s, key), todo)):
                    if rows is None:
                        failed.append(sym)
                        continue
                    cache[sym] = {"fetched": today.strftime("%Y-%m-%d"), "statements": rows}
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"WARN inflation-resilience: cache write failed ({e})")
    by_symbol = {}
    for sym, sector in sym_sector.items():
        entry = cache.get(sym)
        if not entry:
            by_symbol[sym] = _unknown("fetch_failed", "annual statements could not be fetched this run")
            continue
        by_symbol[sym] = classify(entry.get("statements") or [], sector)
    counts = Counter(v["inflation_resilience"] for v in by_symbol.values())
    doc = {
        "asof": today.strftime("%Y-%m-%d"),
        "method": METHOD,
        "thresholds_pp": {"resilient_min": RESILIENT_MIN_PP, "exposed_below": EXPOSED_BELOW_PP},
        "authority": ("judgement input only - never a weight, a seat gate or a conviction fact; "
                      "'unknown' is never a penalty"),
        "counts": dict(counts),
        "by_symbol": by_symbol,
    }
    # Also key each symbol at the TOP level: debate agents told to read "this symbol's entry"
    # looked for doc[SYM] and reported "no entry" for names that were present (2026-10-12).
    for sym, rec in by_symbol.items():
        doc.setdefault(sym, rec)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"WARN inflation-resilience: write failed ({e})")
    if verbose:
        print(f"inflation-resilience: {len(by_symbol)} names -> resilient {counts.get('resilient', 0)} | "
              f"mixed {counts.get('mixed', 0)} | exposed {counts.get('exposed', 0)} | "
              f"unknown {counts.get('unknown', 0)} (fetched {len(todo) - len(failed)}, "
              f"failed {len(failed)}) -> {out_path.name}")
    return doc


def stamp(picks: list, path: Path = OUT_F) -> int:
    """Copy each pick's label (+ basis + plain caption) onto the pick dict in place, for the
    published book. A name missing from this run's file is stamped unknown. Returns the
    number of picks stamped with a measured (non-unknown) label."""
    try:
        by = (json.loads(Path(path).read_text(encoding="utf-8")) or {}).get("by_symbol") or {}
    except Exception:
        by = {}
    n = 0
    for p in picks or []:
        if not isinstance(p, dict) or not p.get("symbol"):
            continue
        rec = by.get(p["symbol"]) or _unknown("not_computed", "not in this run's inflation-resilience file")
        for k in ("inflation_resilience", "inflation_resilience_basis", "inflation_resilience_plain"):
            p[k] = rec.get(k)
        n += rec.get("inflation_resilience") != "unknown"
    return n


if __name__ == "__main__":
    syms = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not syms:
        print(__doc__)
        sys.exit(0)
    key = _fmp_key()
    for s in syms:
        rows = fetch_statements(s, key) if key else None
        r = classify(rows or [], None)
        print(f"{s:10s} {r['inflation_resilience']:9s} {r['inflation_resilience_basis']}")
