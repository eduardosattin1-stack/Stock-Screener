#!/usr/bin/env python3
"""
strategy_basket.py — v1.2
==========================
Generates the winning strategy basket from the latest scan output.

Strategy (v1.0):
    Universe:    allowlist (clean, $100M+ revenue, no biotech, no
                 financials/REITs/utilities)
    Bucket:      Piotroski <= 3
    Rank:        composite_raw descending
    Basket:      top 10, equal-weight
    Rebalance:   weekly

v1.2 changes from v1.1:
  - Robust input shape handling. Accepts both:
    (a) Live-scan shape from screener_v6 asdict():
        {symbol, composite, piotroski, altman_z, factor_scores: {...}}
    (b) Cache shape from backtest_full.py:
        {symbol, composite_raw, factors: {piotroski, altman_z, ...}}
  - Single normalized record format passed to selection logic
  - --from-cache flag for regions without scheduled scans

Run modes:
    Inline from screener_v6 after a scan completes:
        from strategy_basket import generate
        generate("midcap", scan_results=scan_dicts, scan_date="2026-04-25")

    CLI reading latest_{region}.json from GCS:
        python3 strategy_basket.py --region sp500

    CLI reading from a JSONL cache:
        python3 strategy_basket.py --region midcap \\
            --from-cache ~/data/midcap_merged.jsonl
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

try:
    from google.cloud import storage  # type: ignore
    HAS_GCS = True
except Exception:
    HAS_GCS = False

log = logging.getLogger(__name__)


STRATEGY_VERSION = "1.0"
MAX_PIOTROSKI = 3
N_PICKS = 10

BUCKET_NAME = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
ALLOWLIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_allowlists")


# ---------------------------------------------------------------------------
# Input shape normalization (v1.2)
# ---------------------------------------------------------------------------

def _normalize_record(r: dict) -> Optional[dict]:
    """
    Normalize a record from either live-scan or cache shape into a canonical
    form. Returns None if the record can't be used (missing required fields).

    Canonical fields:
      symbol, price, composite, piotroski, altman_z, rsi, momentum_20d, prox_raw
    """
    if not isinstance(r, dict):
        return None

    sym = r.get("symbol")
    if not sym:
        return None

    # Composite: live-scan uses 'composite', cache uses 'composite_raw'
    composite = r.get("composite_raw")
    if composite is None:
        composite = r.get("composite")
    if composite is None:
        return None

    # Factors: cache nests them under 'factors', live-scan puts them top-level
    factors = r.get("factors")
    if not isinstance(factors, dict):
        factors = {}

    def _pull(field: str):
        """Try nested factors first, then top-level."""
        v = factors.get(field)
        if v is not None:
            return v
        return r.get(field)

    pio = _pull("piotroski")
    if pio is None:
        return None

    return {
        "symbol": sym.upper(),
        "price": r.get("price"),
        "composite": composite,
        "piotroski": pio,
        "altman_z": _pull("altman_z"),
        "rsi": _pull("rsi"),
        "momentum_20d": _pull("momentum_20d"),
        "prox_raw": _pull("prox_raw"),
    }


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

def load_allowlist(region: str) -> set:
    path = os.path.join(ALLOWLIST_DIR, f"{region}.txt")
    if not os.path.exists(path):
        log.warning(f"[basket] allowlist not found at {path}")
        return set()
    with open(path) as f:
        syms = {line.strip().upper() for line in f
                if line.strip() and not line.startswith("#")}
    log.info(f"[basket] loaded {len(syms)} symbols from {path}")
    return syms


# ---------------------------------------------------------------------------
# Basket selection
# ---------------------------------------------------------------------------

def select_basket(
    scan_results: List[dict],
    allowlist: set,
    max_piotroski: int = MAX_PIOTROSKI,
    n_picks: int = N_PICKS,
) -> dict:
    """
    Universe filter -> Piotroski bucket -> rank by composite -> top N.
    Accepts records in EITHER live-scan or cache shape.
    """
    if scan_results is None:
        scan_results = []

    # Step 0: normalize every record to canonical shape
    norm = []
    for r in scan_results:
        n = _normalize_record(r)
        if n:
            norm.append(n)

    log.info(f"[basket] normalized {len(norm)}/{len(scan_results)} records")

    # Step 1: allowlist filter (skip if empty allowlist for safety)
    if allowlist:
        allowed = [n for n in norm if n["symbol"] in allowlist]
    else:
        log.warning("[basket] allowlist empty — using full normalized universe")
        allowed = list(norm)

    # Step 2: Piotroski bucket
    bucket = [n for n in allowed if n["piotroski"] <= max_piotroski]

    # Step 3: rank + cap
    bucket.sort(key=lambda n: n["composite"], reverse=True)
    basket = bucket[:n_picks]

    picks = []
    for rank, n in enumerate(basket, 1):
        picks.append({
            "rank": rank,
            "symbol": n["symbol"],
            "price": n["price"],
            "composite_raw": n["composite"],
            "piotroski": n["piotroski"],
            "altman_z": n["altman_z"],
            "rsi": n["rsi"],
            "momentum_20d": n["momentum_20d"],
            "prox_raw": n["prox_raw"],
        })

    return {
        "strategy": f"v{STRATEGY_VERSION}__pio_le_{max_piotroski}__top_{n_picks}",
        "strategy_version": STRATEGY_VERSION,
        "max_piotroski": max_piotroski,
        "n_picks": n_picks,
        "universe_size": len(scan_results),
        "normalized_count": len(norm),
        "allowlist_size": len(allowlist),
        "allowed_count": len(allowed),
        "bucket_size": len(bucket),
        "basket": picks,
    }


# ---------------------------------------------------------------------------
# Input sources
# ---------------------------------------------------------------------------

def read_scan_from_gcs(region: str) -> List[dict]:
    if not HAS_GCS:
        raise RuntimeError("google-cloud-storage not installed")
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"scans/latest_{region}.json")
    if not blob.exists():
        raise RuntimeError(f"scans/latest_{region}.json not found in {BUCKET_NAME}")
    data = json.loads(blob.download_as_text())
    if isinstance(data, dict):
        return data.get("results") or data.get("stocks") or []
    return data


def read_scan_from_cache(cache_path: str, scan_date: Optional[str] = None) -> Tuple[List[dict], str]:
    """Read latest scan from JSONL cache. Returns (records, scan_date)."""
    cache_path = os.path.expanduser(cache_path)
    if not os.path.exists(cache_path):
        raise RuntimeError(f"cache file not found: {cache_path}")

    by_date: Dict[str, List[dict]] = defaultdict(list)
    with open(cache_path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            d = rec.get("scan_date")
            if d:
                by_date[d].append(rec)

    if not by_date:
        raise RuntimeError(f"no records with scan_date in {cache_path}")

    if scan_date is None:
        scan_date = max(by_date.keys())

    if scan_date not in by_date:
        raise RuntimeError(
            f"scan_date {scan_date} not in cache "
            f"(recent: {sorted(by_date.keys())[-5:]})"
        )

    return by_date[scan_date], scan_date


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_basket_to_gcs(region: str, payload: dict) -> str:
    if not HAS_GCS:
        raise RuntimeError("google-cloud-storage not installed")
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"scans/strategy_basket_{region}.json")
    blob.upload_from_string(
        json.dumps(payload, indent=2),
        content_type="application/json",
    )
    return f"gs://{BUCKET_NAME}/scans/strategy_basket_{region}.json"


# ---------------------------------------------------------------------------
# Entry point — called from screener_v6 after each scan
# ---------------------------------------------------------------------------

def generate(
    region: str,
    scan_results: Optional[List[dict]] = None,
    scan_date: Optional[str] = None,
) -> dict:
    """Generate and upload strategy_basket_{region}.json."""
    allowlist = load_allowlist(region)

    if scan_results is None:
        scan_results = read_scan_from_gcs(region)

    if scan_date is None:
        scan_date = dt.date.today().isoformat()

    result = select_basket(scan_results, allowlist)
    result["region"] = region
    result["scan_date"] = scan_date
    result["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    if len(result["basket"]) == 0:
        log.warning(
            f"[basket] {region}: produced EMPTY basket "
            f"(universe={result['universe_size']}, normalized={result['normalized_count']}, "
            f"allowed={result['allowed_count']}, bucket={result['bucket_size']})"
        )
    else:
        url = write_basket_to_gcs(region, result)
        log.info(f"[basket] {region}: wrote {len(result['basket'])} names -> {url}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, choices=["midcap", "sp500"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scan-file", default=None)
    ap.add_argument("--from-cache", default=None,
                    help="read scan from JSONL cache; picks latest scan_date")
    ap.add_argument("--scan-date", default=None,
                    help="specific scan_date from --from-cache (default: latest)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    scan_date_used: Optional[str] = None

    if args.from_cache:
        scan_results, scan_date_used = read_scan_from_cache(args.from_cache, args.scan_date)
        log.info(f"[basket] cache: scan_date={scan_date_used}, records={len(scan_results)}")
    elif args.scan_file:
        with open(args.scan_file) as f:
            data = json.load(f)
        scan_results = (data.get("results") or data.get("stocks") or []) if isinstance(data, dict) else data
    else:
        scan_results = read_scan_from_gcs(args.region)

    allowlist = load_allowlist(args.region)
    result = select_basket(scan_results, allowlist)
    result["region"] = args.region
    result["scan_date"] = scan_date_used or dt.date.today().isoformat()
    result["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    print(json.dumps(result, indent=2))

    if not args.dry_run and len(result["basket"]) > 0:
        url = write_basket_to_gcs(args.region, result)
        print(f"\nwrote -> {url}", file=sys.stderr)
    elif len(result["basket"]) == 0:
        print("\n[!] basket is empty; nothing written", file=sys.stderr)


if __name__ == "__main__":
    main()
