#!/usr/bin/env python3
"""
ETF Passive Flow Velocity — Track B.5 (Backtest Redesign, v8 candidate)
========================================================================

LIVE-ONLY FACTOR — NOT BACKTESTABLE (yet).

WHY
---
Index / thematic / active ETFs rebalance continuously. A stock that's
being ADDED to more ETFs receives passive inflows independent of any
fundamental change. Tracking the *velocity* of ETF-holder count and
aggregate weight-sum provides a leading indicator for price pressure.

WHY LIVE-ONLY
-------------
FMP exposes ETF holdings as a CURRENT snapshot only — there is no
`historical-etf-holdings` endpoint. A backtest on 2023-06-15 cannot know
"how many ETFs held NVDA on 2023-06-15 vs 2023-05-15". Same problem as
price-target-consensus: the 2026 snapshot would leak forward information
into 2023 simulation.

DESIGN
------
This module does two things:

    1.  SNAPSHOT PERSISTENCE — weekly, write a full snapshot of ETF
        holder count + aggregate weight for every scanned symbol to
        GCS. Over time this BECOMES the historical dataset that future
        backtests can use (after ~6 months of weekly snapshots, Track
        A's next quarterly review can include this factor).

    2.  LIVE SCORING — compute a score from the delta between the
        current snapshot and the snapshot N weeks ago (if available).
        Falls back to a neutral score (0.5) when no prior snapshot
        exists.

STORAGE
-------
Snapshots are stored as JSON on GCS at:
    gs://screener-signals-carbonbridge/factors/etf_flow/{YYYY-MM-DD}.json

Format:
    {
      "snapshot_date": "2026-04-21",
      "fetched_at": "2026-04-21T15:02:13Z",
      "symbols": {
        "NVDA": {"etf_count": 542, "weight_sum_pct": 12.47},
        "AAPL": {"etf_count": 618, "weight_sum_pct": 14.83},
        ...
      }
    }

INTEGRATION
-----------
See INTEGRATION_GUIDE.md for the one-liner hook into screener_v6.py.
Short version:

    from factor_etf_flow_velocity import (
        fetch_etf_snapshot,            # per-symbol call (pass-2 enrichment)
        write_snapshot_to_gcs,         # weekly snapshot persistence
        load_prior_snapshot_from_gcs,  # lookup for delta scoring
        compute_etf_flow_score,        # the factor-shaped return dict
    )

    # Pass 2 (top 30 stocks):
    prior = load_prior_snapshot_from_gcs(weeks_ago=4)   # cached once/scan
    snap = fetch_etf_snapshot(fmp, sym)
    score = compute_etf_flow_score(sym, snap, prior)
    stock.factor_scores["etf_flow"] = score["score"]

    # Once per week (at scan end):
    write_snapshot_to_gcs(weekly_snapshot_dict)

WEIGHT IN COMPOSITE
-------------------
Until 6+ months of snapshots exist, the factor is emitted with
`_evaluated=False` so its weight redistributes. Target weight for
when historical data matures: ~3% (similar to sector_momentum).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

_GCS_BUCKET = "screener-signals-carbonbridge"
_GCS_PREFIX = "factors/etf_flow"

# ---------------------------------------------------------------------------
# Per-symbol ETF snapshot (FMP etf-asset-exposure)
# ---------------------------------------------------------------------------

def fetch_etf_snapshot(fmp_func, sym: str) -> dict:
    """
    Query FMP `etf-asset-exposure?symbol=SYM` and return a compact
    summary:
        {"etf_count": int, "weight_sum_pct": float, "_evaluated": bool}

    Notes:
      * Endpoint returns ALL ETFs holding the symbol with fields:
          etfSymbol, etfName, weightPercentage, sharesNumber,
          marketValue, ...
      * Response can be very large (500+ ETFs for mega-caps). We only
        extract the aggregate count and weight sum — the raw payload is
        discarded immediately.
    """
    result = {"etf_count": 0, "weight_sum_pct": 0.0, "_evaluated": False}

    rows = fmp_func("etf-asset-exposure", {"symbol": sym})
    if not rows or not isinstance(rows, list):
        return result

    count = 0
    wsum = 0.0
    for r in rows:
        # weightPercentage is a float like 0.1234 (percent already)
        try:
            w = float(r.get("weightPercentage") or 0)
        except (TypeError, ValueError):
            w = 0.0
        count += 1
        wsum += w

    result["etf_count"] = count
    result["weight_sum_pct"] = round(wsum, 4)
    result["_evaluated"] = count > 0
    return result


# ---------------------------------------------------------------------------
# GCS snapshot persistence
# ---------------------------------------------------------------------------

def _gcs_token() -> Optional[str]:
    """GCP metadata-server token. Returns None off-GCP (local dev)."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            "service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:
        pass
    return None


def write_snapshot_to_gcs(snapshot: dict) -> bool:
    """
    Persist one full snapshot to GCS. Called once per week at the end
    of the scan.

    `snapshot` shape:
        {
          "snapshot_date": "YYYY-MM-DD",
          "fetched_at":    "YYYY-MM-DDTHH:MM:SSZ",
          "symbols":       {"NVDA": {"etf_count":..., "weight_sum_pct":...}, ...}
        }
    """
    import requests
    tok = _gcs_token()
    if not tok:
        log.info("  etf_flow snapshot: no GCS token (local mode), skip")
        return False
    date = snapshot.get("snapshot_date") or datetime.now().strftime("%Y-%m-%d")
    obj = f"{_GCS_PREFIX}/{date}.json"
    try:
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{_GCS_BUCKET}/o",
            params={"uploadType": "media", "name": obj},
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/json"},
            data=json.dumps(snapshot), timeout=20,
        )
        if r.status_code in (200, 201):
            log.info(f"  etf_flow snapshot → gs://{_GCS_BUCKET}/{obj} "
                     f"({len(snapshot.get('symbols', {}))} symbols)")
            return True
        log.warning(f"  etf_flow snapshot upload failed: {r.status_code}")
    except Exception as e:
        log.warning(f"  etf_flow snapshot upload exception: {e}")
    return False


def load_prior_snapshot_from_gcs(weeks_ago: int = 4) -> Optional[dict]:
    """
    Look up a snapshot from `weeks_ago` weeks back. Tolerates
    ±3-day slack to cover holiday weeks. Returns None if not found.

    Used once per scan (caller should cache it in a module-level var
    for the duration of the scan).
    """
    import requests
    tok = _gcs_token()
    if not tok:
        return None

    today = datetime.now()
    target = today - timedelta(weeks=weeks_ago)

    for delta in range(-3, 4):
        try_date = (target + timedelta(days=delta)).strftime("%Y-%m-%d")
        obj = f"{_GCS_PREFIX}/{try_date}.json"
        try:
            r = requests.get(
                f"https://storage.googleapis.com/{_GCS_BUCKET}/{obj}",
                headers={"Authorization": f"Bearer {tok}"}, timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Factor scoring
# ---------------------------------------------------------------------------

def compute_etf_flow_score(
    sym: str, current: dict, prior: Optional[dict]
) -> dict:
    """
    Score ETF flow velocity for a symbol.

    Args:
        current: Result of fetch_etf_snapshot(fmp, sym).
        prior:   Snapshot dict loaded via load_prior_snapshot_from_gcs,
                 or None if no history yet.

    Returns:
        Factor-shaped dict:
            {"score": float 0-1, "delta_count": int, "delta_weight": float,
             "flags": [...], "_evaluated": bool}

    Scoring rules:
        * If no current data               → _evaluated=False (skip factor)
        * If no prior snapshot             → _evaluated=False (factor disabled
                                             until enough weekly history)
        * delta_weight (pp) ≥ +0.5         → score 0.85
        * delta_weight (pp) between 0-0.5  → score 0.60
        * delta_weight ≈ 0                 → score 0.50 (neutral)
        * delta_weight between -0.5 and 0  → score 0.40
        * delta_weight (pp) ≤ -0.5         → score 0.15 (passive outflow)
    """
    result = {
        "score": 0.5, "delta_count": 0, "delta_weight": 0.0,
        "flags": [], "_evaluated": False,
    }
    if not current or not current.get("_evaluated"):
        return result
    if not prior or "symbols" not in prior:
        return result

    prior_sym = prior["symbols"].get(sym.upper())
    if not prior_sym:
        return result

    d_count = current["etf_count"] - prior_sym.get("etf_count", 0)
    d_weight = current["weight_sum_pct"] - prior_sym.get("weight_sum_pct", 0.0)

    result["delta_count"] = d_count
    result["delta_weight"] = round(d_weight, 4)
    result["_evaluated"] = True

    # Scoring: weight delta dominates count delta
    if d_weight >= 0.5:
        score = 0.85
        result["flags"].append(
            f"ETF weight +{d_weight:.2f}pp, +{d_count} new holders"
        )
    elif d_weight > 0:
        score = 0.60
        result["flags"].append(f"ETF weight +{d_weight:.2f}pp")
    elif d_weight == 0:
        score = 0.50
    elif d_weight > -0.5:
        score = 0.40
        result["flags"].append(f"ETF weight {d_weight:.2f}pp")
    else:
        score = 0.15
        result["flags"].append(
            f"⚠ ETF passive OUTFLOW: {d_weight:.2f}pp, "
            f"{d_count} fewer holders"
        )

    result["score"] = score
    return result


# ---------------------------------------------------------------------------
# Scan-end helper: build full snapshot dict from per-symbol results
# ---------------------------------------------------------------------------

def build_scan_snapshot(
    per_symbol_results: dict, snapshot_date: Optional[str] = None,
) -> dict:
    """
    Assemble the scan-end snapshot payload.

    `per_symbol_results`: {sym: {"etf_count":..., "weight_sum_pct":...}, ...}
    """
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")
    return {
        "snapshot_date": snapshot_date,
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols": {
            sym.upper(): {
                "etf_count": int(r.get("etf_count", 0)),
                "weight_sum_pct": float(r.get("weight_sum_pct", 0.0)),
            }
            for sym, r in per_symbol_results.items()
            if isinstance(r, dict)
        },
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Unit test the scoring logic end-to-end
    prior = {
        "snapshot_date": "2026-03-24",
        "symbols": {
            "NVDA": {"etf_count": 500, "weight_sum_pct": 11.50},
            "AAPL": {"etf_count": 615, "weight_sum_pct": 14.90},
            "WIX":  {"etf_count": 45,  "weight_sum_pct": 0.30},
        },
    }

    # Current snapshots representing passive INFLOW, FLAT, OUTFLOW
    cases = [
        ("NVDA", {"etf_count": 542, "weight_sum_pct": 12.47, "_evaluated": True}),
        ("AAPL", {"etf_count": 618, "weight_sum_pct": 14.85, "_evaluated": True}),
        ("WIX",  {"etf_count": 39,  "weight_sum_pct": -0.15 + 0.30 - 0.80,
                  "_evaluated": True}),    # big drop
        ("NEW",  {"etf_count": 10,  "weight_sum_pct": 0.05,  "_evaluated": True}),
        ("EMPTY", {"etf_count": 0,  "weight_sum_pct": 0.0,   "_evaluated": False}),
    ]

    print("=== compute_etf_flow_score ===")
    for sym, cur in cases:
        r = compute_etf_flow_score(sym, cur, prior)
        print(f"  {sym:6s} → score={r['score']:.2f} d_count={r['delta_count']} "
              f"d_weight={r['delta_weight']:+.2f}pp _evaluated={r['_evaluated']}")
        if r["flags"]:
            print(f"           flags={r['flags']}")

    print("\n=== build_scan_snapshot ===")
    snap = build_scan_snapshot(
        {"NVDA": {"etf_count": 542, "weight_sum_pct": 12.47}},
        snapshot_date="2026-04-21",
    )
    print(" ", json.dumps(snap, indent=2))
