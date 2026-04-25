#!/usr/bin/env python3
"""
strategy_basket.py
===================
Generates the winning strategy basket from the latest scan output.

Strategy (v1.0):
    Universe:    allowlist (clean, $100M+ revenue, no biotech, no financials/REITs/utilities)
    Bucket:      Piotroski <= 3
    Rank:        composite_raw descending
    Basket:      top 10, equal-weight
    Rebalance:   weekly

Run modes:
    (a) Invoked from screener_v6 after a scan completes:
            from strategy_basket import generate
            generate("midcap", scan_results, gcs_bucket)

    (b) Standalone from CLI (e.g. Cloud Run job or local debug):
            python3 strategy_basket.py --region midcap

Input:  GCS `latest_{region}.json` (the existing scan output)
Output: GCS `strategy_basket_{region}.json` (new)

The allowlist is shipped in the repo at backend/strategy_allowlists/{region}.txt
so it's version-controlled. Regenerate quarterly via build_universe_allowlist.py.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import os
import sys
from typing import Dict, List, Optional

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
# Allowlist loader
# ---------------------------------------------------------------------------

def load_allowlist(region: str) -> set:
    path = os.path.join(ALLOWLIST_DIR, f"{region}.txt")
    if not os.path.exists(path):
        log.warning(f"[basket] allowlist not found at {path}, using empty set")
        return set()
    with open(path) as f:
        return {line.strip().upper() for line in f if line.strip() and not line.startswith("#")}


# ---------------------------------------------------------------------------
# Basket selection
# ---------------------------------------------------------------------------

def select_basket(
    scan_results: List[dict],
    allowlist: set,
    max_piotroski: int = MAX_PIOTROSKI,
    n_picks: int = N_PICKS,
) -> dict:
    """Apply universe filter, Piotroski bucket filter, rank by composite_raw."""

    # Step 1: allowlist filter
    allowed = [r for r in scan_results if r.get("symbol", "").upper() in allowlist]

    # Step 2: Piotroski bucket
    bucket = []
    for r in allowed:
        factors = r.get("factors") or {}
        pio = factors.get("piotroski")
        if pio is None:
            continue
        if pio > max_piotroski:
            continue
        if r.get("composite_raw") is None:
            continue
        bucket.append(r)

    # Step 3: rank + cap
    bucket.sort(key=lambda r: r["composite_raw"], reverse=True)
    basket = bucket[:n_picks]

    # Project to output shape
    picks = []
    for rank, r in enumerate(basket, 1):
        f = r.get("factors") or {}
        picks.append({
            "rank": rank,
            "symbol": r["symbol"],
            "price": r.get("price"),
            "composite_raw": r.get("composite_raw"),
            "piotroski": f.get("piotroski"),
            "altman_z": f.get("altman_z"),
            "rsi": f.get("rsi"),
            "momentum_20d": f.get("momentum_20d"),
            "prox_raw": f.get("prox_raw"),
        })

    return {
        "strategy": f"{STRATEGY_VERSION}__pio_le_{max_piotroski}__top_{n_picks}",
        "strategy_version": STRATEGY_VERSION,
        "max_piotroski": max_piotroski,
        "n_picks": n_picks,
        "universe_size": len(scan_results),
        "allowlist_size": len(allowlist),
        "allowed_count": len(allowed),
        "bucket_size": len(bucket),
        "basket": picks,
    }


# ---------------------------------------------------------------------------
# GCS I/O (uses existing bucket)
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
    # latest_{region}.json is typically {"scan_date": "...", "results": [...]} or just a list
    return data.get("results") if isinstance(data, dict) else data


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
    # Public-read is already bucket-wide, no need to set per-blob
    return f"gs://{BUCKET_NAME}/scans/strategy_basket_{region}.json"


# ---------------------------------------------------------------------------
# Main entry point — called from screener_v6 after scan completes
# ---------------------------------------------------------------------------

def generate(
    region: str,
    scan_results: Optional[List[dict]] = None,
    scan_date: Optional[str] = None,
) -> dict:
    """Generate and upload strategy_basket_{region}.json.

    Can be called two ways:
      1. Inline from screener_v6 after scan: pass scan_results directly
      2. Standalone: pass None to auto-read from GCS
    """
    allowlist = load_allowlist(region)
    log.info(f"[basket] {region}: allowlist={len(allowlist)} symbols")

    if scan_results is None:
        scan_results = read_scan_from_gcs(region)
    log.info(f"[basket] {region}: scan_results={len(scan_results)} symbols")

    if scan_date is None:
        scan_date = dt.date.today().isoformat()

    result = select_basket(scan_results, allowlist)
    result["region"] = region
    result["scan_date"] = scan_date
    result["generated_at"] = dt.datetime.utcnow().isoformat() + "Z"

    url = write_basket_to_gcs(region, result)
    log.info(f"[basket] {region}: wrote {len(result['basket'])} names -> {url}")
    return result


# ---------------------------------------------------------------------------
# CLI (standalone)
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, choices=["midcap", "sp500"])
    ap.add_argument("--dry-run", action="store_true",
                    help="print basket without writing to GCS")
    ap.add_argument("--scan-file", default=None,
                    help="read scan from local file instead of GCS")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.scan_file:
        with open(args.scan_file) as f:
            data = json.load(f)
        scan_results = data.get("results") if isinstance(data, dict) else data
    else:
        scan_results = read_scan_from_gcs(args.region)

    allowlist = load_allowlist(args.region)
    result = select_basket(scan_results, allowlist)
    result["region"] = args.region
    result["scan_date"] = dt.date.today().isoformat()
    result["generated_at"] = dt.datetime.utcnow().isoformat() + "Z"

    print(json.dumps(result, indent=2))

    if not args.dry_run:
        url = write_basket_to_gcs(args.region, result)
        print(f"\nwrote -> {url}", file=sys.stderr)


if __name__ == "__main__":
    main()
