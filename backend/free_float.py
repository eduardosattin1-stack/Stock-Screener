#!/usr/bin/env python3
"""
Free-float floor (2026-10-13, Bruno: "add a minimum free-float to avoid companies like KARE")
===============================================================================================
A seat needs a tradable float. Karelia Tobacco (KARE.AT) sat in both books with a 4.2% free
float (~116k shares, ~EUR 48m): a controlling family, no buybacks in five years, and an exit
that would move the price. A discount you cannot realise is not a margin of safety.

Rule: free float below MIN_FREE_FLOAT_PCT is INELIGIBLE for a seat in the regime and value books.
  - The Directors see it in their prompts (do not seat such names).
  - The post layers enforce it deterministically: float_demote() moves any seat below the floor to
    the front of runner_ups, stamped with the reason (the same "a gate that cannot demote is
    decoration" pattern as the skeptic and numeric gates).
  - Fail-open: no float figure (FMP gap) = no demotion. A data outage never removes a name.

Data: FMP /stable/shares-float (freeFloat %, floatShares, outstandingShares). Cached 30 days in
_opus_debate/_free_float_cache.json; this run's labels in _opus_debate/free_float.json.
CLI:  python backend/free_float.py KARE.AT DUE.DE
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
CACHE_F = HERE / "_opus_debate" / "_free_float_cache.json"
OUT_F = HERE / "_opus_debate" / "free_float.json"
MIN_FREE_FLOAT_PCT = 15.0      # common index-inclusion threshold; KARE.AT (4.2%) is the case it exists for
CACHE_MAX_AGE_DAYS = 30


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


def fetch(sym: str, key: str) -> Optional[dict]:
    import requests
    try:
        r = requests.get("https://financialmodelingprep.com/stable/shares-float",
                         params={"symbol": sym, "apikey": key}, timeout=30)
        j = r.json() if r.status_code == 200 else None
    except Exception:
        return None
    if not isinstance(j, list):
        return None
    if not j:
        return {}
    x = j[0]
    return {"free_float_pct": x.get("freeFloat"), "float_shares": x.get("floatShares"),
            "outstanding_shares": x.get("outstandingShares"), "asof": str(x.get("date") or "")[:10]}


def build(symbols, out_path: Path = OUT_F, cache_path: Path = CACHE_F, verbose: bool = True) -> dict:
    today = datetime.now()
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8")) or {}
    except Exception:
        cache = {}

    def stale(e):
        try:
            return (today - datetime.strptime(e["fetched"], "%Y-%m-%d")).days > CACHE_MAX_AGE_DAYS
        except Exception:
            return True

    todo = [s for s in symbols if s not in cache or stale(cache[s])]
    failed = []
    if todo:
        key = _fmp_key()
        if key:
            with ThreadPoolExecutor(max_workers=8) as ex:
                for s, rec in zip(todo, ex.map(lambda s: fetch(s, key), todo)):
                    if rec is None:
                        failed.append(s)
                        continue
                    cache[s] = dict(rec, fetched=today.strftime("%Y-%m-%d"))
            try:
                cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"WARN free-float: cache write failed ({e})")
    by = {}
    for s in symbols:
        pct = (cache.get(s) or {}).get("free_float_pct")
        pct = float(pct) if isinstance(pct, (int, float)) else None
        by[s] = {"free_float_pct": round(pct, 1) if pct is not None else None,
                 "below_min": pct is not None and pct < MIN_FREE_FLOAT_PCT}
    below = sorted(s for s, v in by.items() if v["below_min"])
    doc = {"asof": today.strftime("%Y-%m-%d"), "min_free_float_pct": MIN_FREE_FLOAT_PCT,
           "rule": "free float below the minimum is ineligible for a seat; unknown float never blocks",
           "below_min": below, "by_symbol": by}
    for s, v in by.items():
        doc.setdefault(s, v)          # top-level keys too: agents look up doc[SYM]
    try:
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"WARN free-float: write failed ({e})")
    if verbose:
        unknown = sum(1 for v in by.values() if v["free_float_pct"] is None)
        print(f"free-float: {len(by)} names | below {MIN_FREE_FLOAT_PCT:.0f}%: {len(below)} {below} | "
              f"unknown {unknown} (never blocks) | fetched {len(todo) - len(failed)}, failed {len(failed)} -> {out_path.name}")
    return doc


def float_demote(apx: dict, path: Path = OUT_F) -> list:
    """Deterministic teeth: move every apex seat whose free float is below the floor to the front of
    runner_ups (stamped free_float_pct + free_float_demoted). Unknown float passes. Returns the
    demoted symbols. Shared by the regime and value post layers."""
    try:
        by = (json.loads(Path(path).read_text(encoding="utf-8")) or {}).get("by_symbol") or {}
    except Exception:
        by = {}
    keep, demoted = [], []
    for p in apx.get("apex_basket", []) or []:
        rec = by.get(p.get("symbol")) or {}
        pct = rec.get("free_float_pct")
        if pct is not None:
            p["free_float_pct"] = pct
        if rec.get("below_min"):
            p["free_float_demoted"] = True
            p["free_float_reason"] = (f"free float {pct}% is below the {MIN_FREE_FLOAT_PCT:.0f}% minimum - "
                                      f"too few tradable shares to realise the discount or exit cleanly")
            demoted.append(p)
            print(f"WARN free-float: {p['symbol']} free float {pct}% < {MIN_FREE_FLOAT_PCT:.0f}% -> DEMOTED to runner_ups")
        else:
            keep.append(p)
    if demoted:
        ds = {d["symbol"] for d in demoted}
        apx["apex_basket"] = keep
        apx["runner_ups"] = demoted + [r for r in (apx.get("runner_ups") or [])
                                       if (r.get("symbol") if isinstance(r, dict) else r) not in ds]
    return [d["symbol"] for d in demoted]


if __name__ == "__main__":
    syms = [a for a in sys.argv[1:] if not a.startswith("-")]
    if syms:
        d = build(syms, out_path=Path(os.devnull) if os.name != "nt" else HERE / "_opus_debate" / "_free_float_cli.json")
        for s in syms:
            print(s, d["by_symbol"][s])
    else:
        print(__doc__)
