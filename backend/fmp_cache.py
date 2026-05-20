"""FMP cache — read-through GCS cache for slow-cadence fundamentals.

v1.3.0: financial-scores + key-metrics
v1.3.1: + statements (income/balance/cashflow), ratios, transcripts
v1.3.2: + 13F, grades, price-targets, senate/house trading

Design contract:
  - Cache wrapper returns the same shape as the underlying fmp() helper.
  - Cache failures degrade silently to live FMP calls.
  - FORCE_CACHE_REFRESH=1 env var skips cache-read and always calls the fetcher.
  - Each cached file wraps the FMP payload with a cached_at timestamp.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Any

log = logging.getLogger(__name__)

GCS_BUCKET = "screener-signals-carbonbridge"
CACHE_PREFIX = "fmp_cache"

# Per-endpoint TTL in days. Endpoints not listed here default to 5 days.
# NOTE: endpoint strings must match the first arg to fmp() in screener_v6.py
# exactly — including sub-paths like "institutional-ownership/symbol-positions-summary".
CACHE_TTL_DAYS = {
    # Quarterly fundamentals — refresh weekly (5d covers Mon-Fri from Saturday refresh)
    "financial-scores":         5,
    "key-metrics":              5,
    "ratios":                   5,
    "income-statement":         5,
    "balance-sheet-statement":  5,
    "cash-flow-statement":      5,

    # 13F institutional ownership (quarterly filings, ~45d lag)
    "institutional-ownership/symbol-positions-summary": 5,

    # Per-quarter immutable — long TTL, busted by suffix when new quarter drops
    "earning-call-transcript":  90,

    # Weekly-cadence data — refresh every 3 days so Mon scan picks up weekend updates
    "grades":                   3,
    "price-target-consensus":   3,

    # Event-driven but low-frequency (actual FMP endpoints are senate-trades/house-trades)
    "senate-trades":            5,
    "house-trades":             5,
}


# ───────────────────────── Hit/miss telemetry ─────────────────────────

_stats = {"hits": 0, "misses": 0, "force_refresh": 0, "stale_fallback": 0}


def reset_stats():
    """Reset cache stats at the start of each scan."""
    _stats.update({"hits": 0, "misses": 0, "force_refresh": 0, "stale_fallback": 0})


def log_stats():
    """Log a summary line of cache hits/misses at scan end."""
    total = _stats["hits"] + _stats["misses"]
    if total == 0:
        return
    hit_rate = _stats["hits"] / total
    log.info(f"  FMP cache: {_stats['hits']}/{total} hits ({hit_rate:.0%}), "
             f"{_stats['force_refresh']} forced refreshes, "
             f"{_stats['stale_fallback']} stale fallbacks")


# ───────────────────────── Config helpers ─────────────────────────────

def _force_refresh() -> bool:
    """Check if force-refresh is enabled via env var."""
    return os.environ.get("FORCE_CACHE_REFRESH", "").lower() in ("1", "true", "yes")


def _cache_path(endpoint: str, symbol: str, suffix: str = "") -> str:
    """Build the GCS object path for a cache entry."""
    safe_sym = symbol.replace("/", "_").replace(" ", "_").upper()
    name = f"{safe_sym}{('_' + suffix) if suffix else ''}.json"
    return f"{CACHE_PREFIX}/{endpoint}/{name}"


# ───────────────────────── GCS I/O ────────────────────────────────────
# Mirrors signal_tracker.py's lightweight approach: raw requests with
# GCE metadata token. Zero external deps beyond `requests`.

def _gcs_token() -> Optional[str]:
    """GCE/Cloud Run metadata token. None when running locally."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def _gcs_read(path: str) -> Optional[dict]:
    """Read JSON from GCS or local filesystem."""
    # Try local filesystem first
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Failed to read local cache file {local_path}: {e}")

    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return None
        r = requests.get(
            f"https://storage.googleapis.com/{GCS_BUCKET}/{path}",
            headers={"Authorization": f"Bearer {tok}"}, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        log.warning(f"FMP cache GCS read {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"FMP cache GCS read {path} failed: {e}")
    return None


def _gcs_write(path: str, data: dict) -> bool:
    """Write JSON to GCS and local filesystem."""
    # Write to local filesystem
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        log.warning(f"Failed to write local cache file {local_path}: {e}")

    try:
        import requests
        tok = _gcs_token()
        if not tok:
            log.debug(f"FMP cache GCS write {path}: no token (local mode)")
            return True  # Return True since we successfully wrote locally
        body = json.dumps(data, default=str).encode("utf-8")
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=body, timeout=15,
        )
        if r.status_code in (200, 201):
            return True
        log.warning(f"FMP cache GCS write {path}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"FMP cache GCS write {path} failed: {e}")
    return False


# ───────────────────────── Freshness check ────────────────────────────

def _is_fresh(cached_at_iso: str, ttl_days: int) -> bool:
    """Check if a cached entry is still within its TTL window."""
    try:
        cached_at = datetime.fromisoformat(cached_at_iso.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - cached_at
        return age < timedelta(days=ttl_days)
    except Exception:
        return False


# ───────────────────────── Main cache function ────────────────────────

def cached_fmp(endpoint: str, symbol: str, fetcher: Callable[[], Any],
               ttl_days: Optional[int] = None,
               cache_key_suffix: str = "") -> Optional[Any]:
    """Read-through GCS cache for FMP endpoint calls.

    Args:
        endpoint:           FMP endpoint name (e.g. "financial-scores").
        symbol:             Stock ticker.
        fetcher:            Zero-arg callable that performs the live FMP call.
                            Must return the same shape as fmp() — list or None.
        ttl_days:           Cache freshness window in days. Defaults to the
                            per-endpoint value in CACHE_TTL_DAYS, or 5.
        cache_key_suffix:   Optional suffix for cache keys that need finer
                            granularity (e.g. transcripts keyed by quarter).

    Returns:
        The cached or freshly-fetched payload (same return contract as fmp()),
        or None on unrecoverable failure.
    """
    if ttl_days is None:
        ttl_days = CACHE_TTL_DAYS.get(endpoint, 5)

    path = _cache_path(endpoint, symbol, cache_key_suffix)

    # 1. Try cache (unless force-refresh)
    cached = None
    if not _force_refresh():
        try:
            cached = _gcs_read(path)
        except Exception as e:
            log.warning(f"cached_fmp read failed for {endpoint}/{symbol}: {e}")
            # GCS read failed — treat as cache-miss, fall through to fetcher

        if cached and _is_fresh(cached.get("cached_at", ""), ttl_days):
            _stats["hits"] += 1
            return cached.get("payload")
    else:
        _stats["force_refresh"] += 1

    # 2. Fetch live
    _stats["misses"] += 1
    try:
        fresh = fetcher()
    except Exception as e:
        log.warning(f"cached_fmp fetcher failed for {endpoint}/{symbol}: {e}")
        if cached:
            log.info(f"  falling back to stale cache ({path})")
            _stats["stale_fallback"] += 1
            return cached.get("payload")
        return None

    if fresh is None:
        # Fetcher succeeded but returned nothing — don't overwrite a good
        # cache with empty data. Return stale if we have it.
        if cached:
            _stats["stale_fallback"] += 1
            return cached.get("payload")
        return None

    # 3. Write cache (best effort)
    try:
        _gcs_write(path, {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "symbol": symbol,
            "payload": fresh,
        })
    except Exception as e:
        log.warning(f"cached_fmp write failed for {endpoint}/{symbol}: {e}")

    return fresh
