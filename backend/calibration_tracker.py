#!/usr/bin/env python3
"""
calibration_tracker.py — v2 model-calibration tracker (calibration_tracking/v2/)
=================================================================================
Tracks whether the time-model's predicted touch probabilities match observed
touch frequencies, with the methodology fixes the v1 signal_tracker lacked:

  - T+1 two-phase entry: stage on scan night (NO price), activate next run at
    the official ThetaData EOD close of the scan date. Entry bar EXCLUDED from
    the window (bars_elapsed starts at 0, excursion fields start at 0.0).
  - Windows counted in TRADING BARS from ThetaData history, never calendar days.
  - TOUCH fills AT the barrier price (final_return_pct == barrier_pct), never
    the window max-high. TERMINAL at bar K fills at that bar's close.
  - NO stop-loss anywhere in calibration records (the training label has none).
  - Deciles come from config decile_thresholds (v4 OOS holdout), never from
    live-model relative ranks or the v1 in-sample constants.
  - Censoring-aware expected-vs-observed touch math (per-decile time-to-touch
    CDFs from the v4 holdout): q_i = p_i * F[min(bars,K)-1] / F[K-1].

GCS namespace (bucket screener-signals-carbonbridge):
  calibration_tracking/v2/config.json            (one-off: scratch/build_v2_config.py)
  calibration_tracking/v2/pending_entries.json   (staged, not yet activated)
  calibration_tracking/v2/{regime}/entries/{YYYY-MM}.jsonl    (append-only)
  calibration_tracking/v2/{regime}/open_state.json            (rewritten nightly)
  calibration_tracking/v2/{regime}/resolved/{YYYY-MM}.jsonl   (append-only)
  calibration_tracking/v2/{regime}/daily_curve.jsonl          (one point/scan night)
  calibration_tracking/v2/{regime}/decile_stats.json          (rewritten nightly)
  calibration_tracking/v2/health.json
  calibration_tracking/v2/summary.json           (served verbatim by
                                                  GET /performance/calibration-v2)

Regimes:
  p10_30 — prob_key hit_prob_10pct_30d, barrier +10%, window 30 trading bars
  p20_60 — prob_key hit_prob_60d,       barrier +20%, window 60 trading bars

ThetaData credentials: env THETA_EMAIL / THETA_PASSWORD first, then the shared
massive_options.get_theta_client factory (RuntimeError only when both routes
fail — no credential literals in this module, ever).

Zero imports from signal_tracker (GCS helpers copied + parameterized).
The GCS layer (_gcs_impl) and the bar fetcher (_fetch_impl) are injectable so
test_calibration_tracker.py runs without network.
"""

import json
import logging
import math
import os
import requests
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Optional

log = logging.getLogger("calibration_tracker")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GCS_BUCKET = "screener-signals-carbonbridge"
CAL_PREFIX = "calibration_tracking/v2"

MAX_ACTIVATION_ATTEMPTS = 3       # pendings without an EOD bar after 3 runs -> DROPPED
RECORDS_TRAILING_DAYS = 120       # summary.json records[] cap (entry/scan date)
CI_Z = 1.96                       # 95% normal band on expected touches
WILSON_Z = 1.96                   # 95% Wilson CI on per-decile matured rates
THETA_RPS = 16.0                  # ThetaData rate limit (matches v1 tracker)
THETA_WORKERS = 10                # ThetaData thread pool size
THETA_CHUNK_DAYS = 28             # ThetaData caps multi-day EOD at ~1 month


@dataclass
class RegimeCfg:
    name: str            # GCS subfolder + regime key
    prob_key: str        # stock-dict probability field
    barrier_pct: float   # touch barrier in percent
    window_bars: int     # window length in trading bars (entry bar excluded)
    horizon_label: str   # summary.json horizons key
    dd_key: str          # stock-dict predicted-max-drawdown field for this horizon
    edge_key: str        # stock-dict vol-adjusted-edge field for this horizon


REGIMES = {
    "p10_30": RegimeCfg("p10_30", "hit_prob_10pct_30d", 10.0, 30, "30d", "expected_dd_30d", "vol_adj_edge_30d"),
    "p20_60": RegimeCfg("p20_60", "hit_prob_60d", 20.0, 60, "60d", "expected_dd_60d", "vol_adj_edge_60d"),
}


# ---------------------------------------------------------------------------
# GCS I/O (copied from signal_tracker.py, parameterized by CAL_PREFIX usage;
# JSONL appends gain ifGenerationMatch preconditions)
# ---------------------------------------------------------------------------

def _gcs_token() -> Optional[str]:
    """GCE/Cloud Run metadata token, with fallback to gcloud auth for local execution."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:
        pass

    try:
        import subprocess, platform
        cmd = "gcloud.cmd" if platform.system() == "Windows" else "gcloud"
        proc = subprocess.run([cmd, "auth", "print-access-token"], capture_output=True, text=True, check=True)
        return proc.stdout.strip()
    except Exception:
        return None


def _gcs_read(path: str, default):
    """Read JSON from GCS. Returns default on any failure."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return default
        encoded_path = path.replace("/", "%2F")
        r = requests.get(
            f"https://www.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded_path}?alt=media",
            headers={"Authorization": f"Bearer {tok}"}, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return default
        log.warning(f"GCS read {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS read {path} failed: {e}")
    return default


def _gcs_read_text(path: str, default: str = "") -> str:
    """Read raw text (for JSONL files) from GCS. Returns default on failure."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return default
        encoded_path = path.replace("/", "%2F")
        r = requests.get(
            f"https://www.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded_path}?alt=media",
            headers={"Authorization": f"Bearer {tok}"}, timeout=10,
        )
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            return default
        log.warning(f"GCS read-text {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS read-text {path} failed: {e}")
    return default


def _gcs_write(path: str, data, content_type: str = "application/json") -> bool:
    """Write JSON (or raw text if data is str) to GCS. Returns True on success."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            log.debug(f"GCS write {path}: no token (local mode)")
            return False
        if isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = json.dumps(data, default=str).encode("utf-8")
        r = requests.post(
            f"https://www.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": content_type},
            data=body, timeout=15,
        )
        if r.status_code in (200, 201):
            try:
                patch_url = f"https://www.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{path.replace('/', '%2F')}"
                requests.patch(
                    patch_url,
                    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                    json={"cacheControl": "no-cache, no-store, max-age=0, must-revalidate"},
                    timeout=10,
                )
            except Exception as patch_e:
                log.warning(f"GCS metadata patch for {path} failed: {patch_e}")
            return True
        log.warning(f"GCS write {path}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"GCS write {path} failed: {e}")
    return False


def _gcs_generation(path: str) -> Optional[int]:
    """Object generation for ifGenerationMatch preconditions.
    Returns 0 if the object does not exist, None on error/no-token."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return None
        encoded_path = path.replace("/", "%2F")
        r = requests.get(
            f"https://www.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded_path}",
            params={"fields": "generation"},
            headers={"Authorization": f"Bearer {tok}"}, timeout=10,
        )
        if r.status_code == 200:
            return int(r.json().get("generation", 0))
        if r.status_code == 404:
            return 0
        log.warning(f"GCS stat {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS stat {path} failed: {e}")
    return None


def _gcs_write_precond(path: str, text: str, generation: int) -> int:
    """Upload text iff the object's generation still matches (0 = must not exist).
    Returns the HTTP status code (412 on precondition failure), or -1 on error."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return -1
        r = requests.post(
            f"https://www.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path, "ifGenerationMatch": str(generation)},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=text.encode("utf-8"), timeout=15,
        )
        return r.status_code
    except Exception as e:
        log.warning(f"GCS precond write {path} failed: {e}")
        return -1


def _gcs_append_jsonl(path: str, rows: list) -> bool:
    """Append rows (dicts) to a JSONL object using an ifGenerationMatch
    precondition (read-modify-write that cannot silently drop lines if the
    screener-sp500 and screener-global jobs ever overlap). One re-read retry
    on 412."""
    if not rows:
        return True
    payload = "".join(json.dumps(r, default=str) + "\n" for r in rows)
    for attempt in range(2):
        gen = _gcs_generation(path)
        if gen is None:
            log.warning(f"GCS append {path}: could not stat generation")
            return False
        existing = _gcs_read_text(path, "") if gen else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        status = _gcs_write_precond(path, existing + payload, gen)
        if status in (200, 201):
            return True
        if status != 412:
            log.warning(f"GCS append {path}: HTTP {status}")
            return False
        log.info(f"GCS append {path}: generation conflict (412), retry {attempt + 1}")
    log.warning(f"GCS append {path}: gave up after precondition retry")
    return False


def _gcs_list(prefix: str) -> list:
    """List object names under a prefix."""
    names = []
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return names
        page_token = None
        while True:
            params = {"prefix": prefix, "fields": "items(name),nextPageToken"}
            if page_token:
                params["pageToken"] = page_token
            r = requests.get(
                f"https://www.googleapis.com/storage/v1/b/{GCS_BUCKET}/o",
                params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=15,
            )
            if r.status_code != 200:
                log.warning(f"GCS list {prefix}: {r.status_code}")
                break
            payload = r.json()
            names.extend(item["name"] for item in payload.get("items", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        log.warning(f"GCS list {prefix} failed: {e}")
    return names


# Injectable GCS layer: tests swap this dict for a FakeGCS-backed one.
_gcs_impl = {
    "read": _gcs_read,
    "read_text": _gcs_read_text,
    "write": _gcs_write,
    "append_jsonl": _gcs_append_jsonl,
    "list": _gcs_list,
}

# Injectable bar fetcher: when set, _fetch_impl(symbol, start_iso, end_iso)
# replaces all ThetaData access (tests). Default None = real ThetaClient.
_fetch_impl = None


# ---------------------------------------------------------------------------
# ThetaData
# ---------------------------------------------------------------------------

class ThetaUnavailable(RuntimeError):
    """ThetaData credentials missing/blank or the client cannot authenticate. A DISTINCT type (vs a
    generic RuntimeError) so run_scan_job can mark the job FAILED + alert instead of swallowing it."""


def get_theta_client():
    """ThetaClient credentials: env THETA_EMAIL / THETA_PASSWORD first; if
    unset, the shared massive_options.get_theta_client factory. NO credential
    literals in this module — raises only when both routes fail."""
    email = (os.environ.get("THETA_EMAIL") or "").strip()
    password = (os.environ.get("THETA_PASSWORD") or "").strip()
    if email and password:
        from thetadata import ThetaClient
        return ThetaClient(email=email, password=password)
    try:
        from massive_options import get_theta_client as _shared_theta_client
        return _shared_theta_client()
    except Exception as e:
        raise ThetaUnavailable(
            "THETA creds missing/blank — set THETA_EMAIL/THETA_PASSWORD (Secret Manager) "
            f"(shared factory fallback failed: {e})"
        )


def assert_theta_ready():
    """LOUD preflight: prove ThetaData is actually usable (creds non-blank AND the client constructs AND
    one tiny call authenticates) BEFORE the tracker attempts any fills — so a missing/blank credential
    fails visibly instead of silently resolving zero touches. Raises ThetaUnavailable with the greppable
    'CALIBRATION_THETA_DOWN' token. Skipped under the _fetch_impl test injection (no real ThetaData)."""
    if _fetch_impl is not None:
        return None
    try:
        client = get_theta_client()
    except Exception as e:
        raise ThetaUnavailable(f"🚨 CALIBRATION_THETA_DOWN: ThetaData credentials unusable — {e}")
    try:
        end = datetime.now().date()
        start = end - timedelta(days=7)
        client.stock_history_eod("AAPL", start, end)   # cheap smoke call; raises on auth failure
    except ThetaUnavailable:
        raise
    except Exception as e:
        raise ThetaUnavailable(f"🚨 CALIBRATION_THETA_DOWN: ThetaData connected but a smoke call failed — {e}")
    return client


class _RateLimiter:
    def __init__(self, rps: float):
        from threading import Lock
        self.interval = 1.0 / rps
        self.last = 0.0
        self.lock = Lock()

    def wait(self):
        import time as _t
        with self.lock:
            now = _t.time()
            s = self.interval - (now - self.last)
            if s > 0:
                _t.sleep(s)
                self.last = _t.time()
            else:
                self.last = now


FMP_BASE = "https://financialmodelingprep.com/stable"
FMP_KEY = os.environ.get("FMP_API_KEY") or "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"


def _fetch_eod_bars(theta, symbol: str, start: str, end: str, limiter=None) -> list:
    """Daily OHLC bars for [start, end] (ISO dates, inclusive) from FMP
    (stable historical-price-eod/full). Returns sorted
    [{"date","open","high","low","close"}].

    Migrated off ThetaData 2026-06-19 (ThetaData dropped — options now come from
    IBKR on-demand). FMP is Cloud-Run-native (no gateway), already used
    screener-wide, and covers US + EU. `theta` is unused (kept for the pooled-fetch
    signature). Routed through _fetch_impl when injected (tests)."""
    if _fetch_impl is not None:
        return _fetch_impl(symbol, start, end) or []
    if limiter:
        limiter.wait()
    try:
        r = requests.get(f"{FMP_BASE}/historical-price-eod/full",
                         params={"symbol": symbol, "from": start, "to": end, "apikey": FMP_KEY},
                         timeout=30)
        if not r.ok:
            log.debug(f"_fetch_eod_bars FMP {symbol} HTTP {r.status_code}")
            return []
        data = r.json()
        rows = data.get("historical") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        bars = []
        for row in rows:
            try:
                bars.append({
                    "date": str(row.get("date"))[:10],
                    "open": float(row.get("open") or 0.0),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        bars.sort(key=lambda b: b["date"])
        return bars
    except Exception as e:
        log.debug(f"_fetch_eod_bars FMP {symbol} [{start}..{end}]: {e}")
        return []


def _fetch_bars_pooled(theta, requests_list: list) -> dict:
    """Pooled bar fetch: requests_list = [(symbol, start_iso, end_iso)],
    returns {(symbol, start_iso, end_iso): [bars]}. 16 rps / 10 workers,
    matching the v1 tracker's ThetaData etiquette."""
    out = {}
    if not requests_list:
        return out
    if _fetch_impl is not None:
        for req in requests_list:
            sym, s, e = req
            out[req] = _fetch_impl(sym, s, e) or []
        return out
    if theta is None:
        return out
    import concurrent.futures
    limiter = _RateLimiter(THETA_RPS)

    def work(req):
        sym, s, e = req
        return req, _fetch_eod_bars(theta, sym, s, e, limiter=limiter)

    with concurrent.futures.ThreadPoolExecutor(max_workers=THETA_WORKERS) as ex:
        for req, bars in ex.map(work, requests_list):
            out[req] = bars
    return out


# ---------------------------------------------------------------------------
# Config + pure math helpers
# ---------------------------------------------------------------------------

def _load_config() -> Optional[dict]:
    """config.json, loaded once per update_from_scan call. None when missing."""
    cfg = _gcs_impl["read"](f"{CAL_PREFIX}/config.json", None)
    if not isinstance(cfg, dict):
        return None
    return cfg


def _decile_from_edges(p: float, edges: list) -> int:
    """Decile 1..10 from 9 ascending edge values (v4 OOS holdout cut points)."""
    import bisect
    if not edges:
        return 1
    return min(10, bisect.bisect_right(edges, float(p)) + 1)


def _cdf_for_decile(config: dict, regime_name: str, decile) -> list:
    """Per-decile touch CDF from config; falls back to pooled when the decile
    array is absent or empty."""
    tc = (config.get("touch_cdf") or {}).get(regime_name) or {}
    F = (tc.get("by_decile") or {}).get(str(decile))
    if not F:
        F = tc.get("pooled")
    return F or []


def _q_for_record(record: dict, F: list, K: int) -> tuple:
    """(q_i, frac_i) per C6: q_i = p_i * F[min(bars,K)-1] / F[K-1]
    (arrays 0-indexed = bar 1..K); bars_elapsed == 0 -> q_i = 0.
    frac_i = F[min(bars,K)-1]/F[K-1] is the n_effective contribution."""
    p = float(record.get("p") or 0.0)
    bars = int(record.get("bars_elapsed") or 0)
    k = min(bars, K)
    if k <= 0 or not F or len(F) < K or F[K - 1] <= 0:
        return 0.0, 0.0
    frac = F[k - 1] / F[K - 1]
    return p * frac, frac


def _curve_stats(records: list, config: dict, regime_name: str, K: int) -> dict:
    """Censoring-aware expected-vs-observed stats over non-dropped records.
    E = sum q_i; O = #TOUCH; V = sum q_i(1-q_i); ci = E -/+ 1.96*sqrt(V);
    n_effective = sum frac_i; z = (O-E)/sqrt(V) when V>0 else None."""
    E = 0.0
    V = 0.0
    n_eff = 0.0
    O = 0
    for r in records:
        F = _cdf_for_decile(config, regime_name, r.get("decile"))
        q, frac = _q_for_record(r, F, K)
        E += q
        V += q * (1.0 - q)
        n_eff += frac
        if r.get("resolution") == "TOUCH":
            O += 1
    sd = math.sqrt(V) if V > 0 else 0.0
    z = ((O - E) / sd) if V > 0 else None
    return {
        "expected": E,
        "observed": O,
        "variance": V,
        "n_effective": n_eff,
        "z": z,
        "ci_low": E - CI_Z * sd,
        "ci_high": E + CI_Z * sd,
    }


def _wilson_ci(p_hat: float, n: int, z: float = WILSON_Z) -> tuple:
    """Wilson 95% score interval on an observed rate."""
    if n <= 0:
        return 0.0, 1.0
    denom = 1.0 + z * z / n
    center = (p_hat + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p_hat * (1.0 - p_hat) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _health_block(point: dict, config: dict, as_of: str, prev_consecutive: int) -> dict:
    """Health per C6: UNDER_SAMPLED if n_effective < 30; DEGRADED if z < -3
    (kill switch); DRIFTING if -3 <= z < -2; else HEALTHY."""
    ks = config.get("kill_switch") or {}
    z_degraded = float(ks.get("z_degraded", -3))
    z_drifting = float(ks.get("z_drifting", -2))
    min_n_eff = float(ks.get("min_n_eff", 30))
    z = point.get("z")
    n_eff = float(point.get("n_effective") or 0.0)
    below_band = point.get("observed", 0) < point.get("ci_low", 0.0)
    consecutive = (prev_consecutive + 1) if below_band else 0
    if n_eff < min_n_eff:
        status = "UNDER_SAMPLED"
    elif z is not None and z < z_degraded:
        status = "DEGRADED"
    elif z is not None and z < z_drifting:
        status = "DRIFTING"
    else:
        status = "HEALTHY"
    return {
        "status": status,
        "kill_switch_active": status == "DEGRADED",
        "z_score": round(z, 4) if z is not None else None,
        "n_effective": round(n_eff, 4),
        "consecutive_below_band": consecutive,
        "rule": (f"UNDER_SAMPLED if n_eff < {min_n_eff:g}; DEGRADED (kill switch) if z < {z_degraded:g}; "
                 f"DRIFTING if {z_degraded:g} <= z < {z_drifting:g}; else HEALTHY; "
                 f"band = E +/- 1.96*sqrt(V), independent-record approximation"),
        "computed_date": as_of,
    }


# ---------------------------------------------------------------------------
# Phase A — staging (scan night, no price)
# ---------------------------------------------------------------------------

def _stage_pending_entries(stocks: list, scan_date: str, cfg: RegimeCfg,
                           config: dict, pending: list, open_symbols: set) -> int:
    """Stage every stock with cfg.prob_key > 0 that has no PENDING/OPEN record
    in this regime. Weekday gate; symbols containing '.' skipped (non-US
    listings ThetaData doesn't cover). NO entry_price at staging — the scan
    runs before ThetaData EOD finalizes."""
    try:
        d = datetime.strptime(scan_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        log.warning(f"[{cfg.name}] staging skipped: bad scan_date {scan_date!r}")
        return 0
    if d.weekday() >= 5:
        log.info(f"[{cfg.name}] staging skipped: {scan_date} is a weekend")
        return 0
    pending_keys = {(p.get("regime"), p.get("symbol")) for p in pending}
    edges = (config.get("decile_thresholds") or {}).get(cfg.name) or []
    staged = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for s in stocks:
        sym = (s.get("symbol") or "").strip()
        if not sym or "." in sym:
            continue
        try:
            p = float(s.get(cfg.prob_key) or 0.0)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        if (cfg.name, sym) in pending_keys or sym in open_symbols:
            continue
        # Scan payload emits these under the options_ prefix (screener_v6
        # output schema); fall back to the bare names for any in-memory caller.
        iv_raw = s.get("options_iv_current")
        if iv_raw is None:
            iv_raw = s.get("iv_current")
        ivr_raw = s.get("options_iv_rank")
        if ivr_raw is None:
            ivr_raw = s.get("iv_rank")
        # Model-predicted max drawdown over this regime's horizon (absolute %,
        # negative). Validated against observed max_drawdown_pct at maturity.
        dd_raw = s.get(cfg.dd_key)
        # Vol-adjusted edge: model prob minus the vol-only touch baseline at this
        # stock's realized vol (>0 => beats vol, driven by non-vol setup quality).
        edge_raw = s.get(cfg.edge_key)
        pending.append({
            "record_id": f"{cfg.name}:{sym}:{scan_date}",
            "regime": cfg.name,
            "symbol": sym,
            "scan_date": scan_date,
            "p": round(p, 4),
            "decile": _decile_from_edges(p, edges),
            "sector": s.get("sector"),
            "iv_entry": round(float(iv_raw), 4) if iv_raw is not None else None,
            "ivr_entry": round(float(ivr_raw), 1) if ivr_raw is not None else None,
            "dd_pred": round(float(dd_raw), 2) if dd_raw is not None else None,
            "edge": round(float(edge_raw), 4) if edge_raw is not None else None,
            "attempts": 0,
            "staged_at": now_iso,
        })
        pending_keys.add((cfg.name, sym))
        staged += 1
    return staged


# ---------------------------------------------------------------------------
# Phase B — activation (next runs, official EOD close)
# ---------------------------------------------------------------------------

def _activate_pending_entries(cfg: RegimeCfg, as_of: str, pending: list,
                              open_state: dict, act_bars: dict, config: dict) -> tuple:
    """Activate pendings whose scan-date EOD bar now exists: entry_price = that
    bar's close, entry bar EXCLUDED from the window. attempts >= 3 without a
    bar -> DROPPED (resolution DROPPED_NO_BAR). Returns (activated, dropped).
    Consumed pendings are flagged '_consumed' (caller filters the shared list)."""
    activated = 0
    dropped = 0
    entry_rows_by_month = {}
    dropped_rows_by_month = {}
    for pend in pending:
        if pend.get("regime") != cfg.name or pend.get("_consumed"):
            continue
        sym = pend["symbol"]
        scan_date = pend["scan_date"]
        bars = act_bars.get((sym, scan_date, scan_date)) or []
        bar = next((b for b in bars if b.get("date") == scan_date), None)
        if bar is not None:
            entry_price = float(bar["close"])
            record = {
                "record_id": pend["record_id"],
                "regime": cfg.name,
                "symbol": sym,
                "scan_date": scan_date,
                "entry_bar_date": scan_date,
                "entry_price": entry_price,
                "p": pend["p"],
                "decile": pend["decile"],
                "sector": pend.get("sector"),
                "barrier_pct": cfg.barrier_pct,
                "barrier_price": round(entry_price * (1.0 + cfg.barrier_pct / 100.0), 6),
                "window_bars": cfg.window_bars,
                "model_version": config.get("model_version"),
                "iv_entry": pend.get("iv_entry"),
                "ivr_entry": pend.get("ivr_entry"),
                "dd_pred": pend.get("dd_pred"),
                "edge": pend.get("edge"),
                "status": "OPEN",
                "bars_elapsed": 0,
                "last_bar_date": scan_date,
                "max_high": float(bar["high"]),
                "max_high_pct": 0.0,
                "min_low": float(bar["low"]),
                "max_drawdown_pct": 0.0,
                "touch_bar": None,
                "resolved_date": None,
                "resolution": None,
                "fill_price": None,
                "final_return_pct": None,
                "activated_at": as_of,
            }
            open_state.setdefault("records", []).append(record)
            entry_rows_by_month.setdefault(scan_date[:7], []).append(dict(record))
            pend["_consumed"] = True
            activated += 1
        else:
            pend["attempts"] = int(pend.get("attempts") or 0) + 1
            if pend["attempts"] >= MAX_ACTIVATION_ATTEMPTS:
                drop_row = {
                    "record_id": pend["record_id"],
                    "regime": cfg.name,
                    "symbol": sym,
                    "scan_date": scan_date,
                    "entry_bar_date": None,
                    "entry_price": None,
                    "p": pend["p"],
                    "decile": pend["decile"],
                    "sector": pend.get("sector"),
                    "barrier_pct": cfg.barrier_pct,
                    "barrier_price": None,
                    "window_bars": cfg.window_bars,
                    "model_version": config.get("model_version"),
                    "status": "DROPPED",
                    "bars_elapsed": 0,
                    "last_bar_date": None,
                    "max_high": None,
                    "max_high_pct": 0.0,
                    "min_low": None,
                    "max_drawdown_pct": 0.0,
                    "touch_bar": None,
                    "resolved_date": as_of,
                    "resolution": "DROPPED_NO_BAR",
                    "fill_price": None,
                    "final_return_pct": None,
                    "attempts": pend["attempts"],
                }
                dropped_rows_by_month.setdefault(as_of[:7], []).append(drop_row)
                pend["_consumed"] = True
                dropped += 1
    for month, rows in entry_rows_by_month.items():
        _gcs_impl["append_jsonl"](f"{CAL_PREFIX}/{cfg.name}/entries/{month}.jsonl", rows)
    for month, rows in dropped_rows_by_month.items():
        _gcs_impl["append_jsonl"](f"{CAL_PREFIX}/{cfg.name}/resolved/{month}.jsonl", rows)
    return activated, dropped


# ---------------------------------------------------------------------------
# Refresh + resolution (trading bars, barrier fills, no stop-loss)
# ---------------------------------------------------------------------------

def _refresh_open_records(cfg: RegimeCfg, as_of: str, open_state: dict,
                          bars_by_symbol: dict) -> dict:
    """Advance every OPEN record bar by bar (date order, bars strictly after
    last_bar_date). Per bar: bars_elapsed += 1; mark-to-market max_high_pct /
    max_drawdown_pct (drawdown from bar lows, floored at 0); then
    (a) TOUCH if bar.high >= barrier_price -> fill AT barrier_price,
        final_return_pct = barrier_pct, touch_bar = bars_elapsed;
    (b) else TERMINAL when bars_elapsed == window_bars -> fill at bar close.
    NO stop-loss. Resolved rows appended to resolved/{YYYY-MM}.jsonl and
    removed from open_state."""
    records = open_state.get("records", [])
    still_open = []
    resolved_by_month = {}
    touched = 0
    terminal = 0
    for r in records:
        bars = [b for b in bars_by_symbol.get(r["symbol"], [])
                if b.get("date") and b["date"] > (r.get("last_bar_date") or "")]
        bars.sort(key=lambda b: b["date"])
        entry_price = float(r["entry_price"])
        resolved = False
        for bar in bars:
            r["bars_elapsed"] = int(r.get("bars_elapsed") or 0) + 1
            r["last_bar_date"] = bar["date"]
            hi = float(bar["high"])
            lo = float(bar["low"])
            r["max_high"] = max(float(r.get("max_high") or hi), hi)
            r["max_high_pct"] = max(float(r.get("max_high_pct") or 0.0),
                                    (hi / entry_price - 1.0) * 100.0)
            r["min_low"] = min(float(r.get("min_low") or lo), lo)
            r["max_drawdown_pct"] = min(float(r.get("max_drawdown_pct") or 0.0),
                                        (lo / entry_price - 1.0) * 100.0, 0.0)
            if hi >= float(r["barrier_price"]):
                r["status"] = "RESOLVED"
                r["resolution"] = "TOUCH"
                r["touch_bar"] = r["bars_elapsed"]
                r["fill_price"] = float(r["barrier_price"])
                r["final_return_pct"] = float(r["barrier_pct"])
                r["resolved_date"] = bar["date"]
                resolved = True
                break
            if r["bars_elapsed"] >= int(r["window_bars"]):
                r["status"] = "RESOLVED"
                r["resolution"] = "TERMINAL"
                r["fill_price"] = float(bar["close"])
                r["final_return_pct"] = (float(bar["close"]) / entry_price - 1.0) * 100.0
                r["resolved_date"] = bar["date"]
                resolved = True
                break
        if resolved:
            month = (r["resolved_date"] or as_of)[:7]
            resolved_by_month.setdefault(month, []).append(r)
            if r["resolution"] == "TOUCH":
                touched += 1
            else:
                terminal += 1
        else:
            still_open.append(r)
    open_state["records"] = still_open
    for month, rows in resolved_by_month.items():
        _gcs_impl["append_jsonl"](f"{CAL_PREFIX}/{cfg.name}/resolved/{month}.jsonl", rows)
    return {"touched": touched, "terminal": terminal, "open": len(still_open)}


# ---------------------------------------------------------------------------
# Nightly stats: curve point, decile rows, health, summary
# ---------------------------------------------------------------------------

def _load_resolved_records(cfg: RegimeCfg) -> list:
    """All resolved rows (incl. DROPPED) across monthly JSONL files, deduped
    by record_id keeping the LAST occurrence — a crash between the resolved
    append and the open_state write (or overlapping jobs) can double-append
    a row, and the stats must be immune to that."""
    by_id = {}
    no_id = []
    for path in sorted(_gcs_impl["list"](f"{CAL_PREFIX}/{cfg.name}/resolved/")):
        text = _gcs_impl["read_text"](path, "")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = row.get("record_id")
            if rid:
                by_id[rid] = row              # last occurrence wins
            else:
                no_id.append(row)
    return list(by_id.values()) + no_id


def _load_entry_scan_dates(cfg: RegimeCfg) -> set:
    """Distinct scan_date values across the regime's entries files."""
    dates = set()
    for path in _gcs_impl["list"](f"{CAL_PREFIX}/{cfg.name}/entries/"):
        text = _gcs_impl["read_text"](path, "")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                sd = json.loads(line).get("scan_date")
                if sd:
                    dates.add(sd)
            except json.JSONDecodeError:
                continue
    return dates


def _curve_point_full(records: list, config: dict, cfg: RegimeCfg, as_of: str) -> tuple:
    """(daily_curve.jsonl line, raw pooled stats). The line embeds per-decile
    CurvePoints so summary curves rebuild without re-reading record history."""
    pooled = _curve_stats(records, config, cfg.name, cfg.window_bars)
    by_decile = {}
    for d in range(1, 11):
        recs = [r for r in records if int(r.get("decile") or 0) == d]
        st = _curve_stats(recs, config, cfg.name, cfg.window_bars)
        by_decile[str(d)] = {
            "scan_date": as_of,
            "expected": round(st["expected"], 4),
            "observed": st["observed"],
            "ci_low": round(st["ci_low"], 4),
            "ci_high": round(st["ci_high"], 4),
        }
    line = {
        "scan_date": as_of,
        "expected": round(pooled["expected"], 4),
        "observed": pooled["observed"],
        "ci_low": round(pooled["ci_low"], 4),
        "ci_high": round(pooled["ci_high"], 4),
        "variance": round(pooled["variance"], 6),
        "n_effective": round(pooled["n_effective"], 4),
        "z": round(pooled["z"], 4) if pooled["z"] is not None else None,
        "by_decile": by_decile,
    }
    return line, pooled


def _upsert_curve_point(cfg: RegimeCfg, line: dict) -> list:
    """Append tonight's point to daily_curve.jsonl, replacing any same-date
    point (re-run safety). Returns the full parsed history, date-ascending."""
    path = f"{CAL_PREFIX}/{cfg.name}/daily_curve.jsonl"
    text = _gcs_impl["read_text"](path, "")
    history = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("scan_date") != line["scan_date"]:
            history.append(obj)
    history.append(line)
    history.sort(key=lambda o: o.get("scan_date") or "")
    body = "".join(json.dumps(o, default=str) + "\n" for o in history)
    _gcs_impl["write"](path, body)
    return history


def _compute_decile_rows(records: list, config: dict, cfg: RegimeCfg) -> list:
    """Always-length-10 DecileRow list (decile asc). matured = TOUCH/TERMINAL.
    ci_low/ci_high = Wilson 95% CI on matured_observed_rate per C6
    ((0.0, 1.0) when no matured rows yet)."""
    rows = []
    for d in range(1, 11):
        recs = [r for r in records if int(r.get("decile") or 0) == d]
        n_total = len(recs)
        n_touched = sum(1 for r in recs if r.get("resolution") == "TOUCH")
        n_matured = sum(1 for r in recs if r.get("resolution") in ("TOUCH", "TERMINAL"))
        n_open = sum(1 for r in recs if r.get("status") == "OPEN")
        rate = (n_touched / n_matured) if n_matured > 0 else None
        mean_p = (sum(float(r.get("p") or 0.0) for r in recs) / n_total) if n_total else None
        st = _curve_stats(recs, config, cfg.name, cfg.window_bars)
        if n_matured > 0:
            ci_low, ci_high = _wilson_ci(rate, n_matured)
        else:
            ci_low, ci_high = 0.0, 1.0
        rows.append({
            "decile": d,
            "n_total": n_total,
            "n_matured": n_matured,
            "n_open": n_open,
            "n_touched": n_touched,
            "matured_observed_rate": round(rate, 4) if rate is not None else None,
            "predicted_mean_p": round(mean_p, 4) if mean_p is not None else None,
            "expected_touches_to_date": round(st["expected"], 4),
            "observed_touches_to_date": n_touched,
            "ci_low": round(ci_low, 4),
            "ci_high": round(ci_high, 4),
        })
    return rows


def _build_calib_records(records_by_regime: dict, as_of: str) -> list:
    """One CalibRecord row per pick: join both regimes on (symbol, scan_date);
    a regime with no record -> null fields. DROPPED excluded. Capped to entries
    from the trailing RECORDS_TRAILING_DAYS days. Sorted entry_date desc,
    symbol asc."""
    try:
        cutoff = (datetime.strptime(as_of, "%Y-%m-%d").date()
                  - timedelta(days=RECORDS_TRAILING_DAYS)).isoformat()
    except (TypeError, ValueError):
        cutoff = ""
    joined = {}
    for regime_name, recs in records_by_regime.items():
        for r in recs:
            if r.get("status") == "DROPPED":
                continue
            sd = r.get("scan_date") or ""
            if sd < cutoff:
                continue
            joined.setdefault((r["symbol"], sd), {})[regime_name] = r

    def _state(r):
        if r is None:
            return None
        if r.get("status") == "OPEN":
            return "OPEN"
        return "TOUCHED" if r.get("resolution") == "TOUCH" else "NO_TOUCH"

    keys = sorted(joined.keys())                      # symbol asc
    keys.sort(key=lambda k: k[1], reverse=True)       # then entry_date desc (stable)
    out = []
    for sym, sd in keys:
        pair = joined[(sym, sd)]
        r30 = pair.get("p10_30")
        r60 = pair.get("p20_60")
        base = r60 or r30
        out.append({
            "symbol": sym,
            "entry_date": sd,
            "entry_price": base.get("entry_price"),
            "sector": base.get("sector"),
            "p10": r30.get("p") if r30 else None,
            "p20": r60.get("p") if r60 else None,
            "decile_30d": r30.get("decile") if r30 else None,
            "decile_60d": r60.get("decile") if r60 else None,
            "bars_elapsed_30d": r30.get("bars_elapsed") if r30 else None,
            "bars_elapsed_60d": r60.get("bars_elapsed") if r60 else None,
            "iv_entry": base.get("iv_entry"),
            "ivr_entry": base.get("ivr_entry"),
            "dd_pred_30d": r30.get("dd_pred") if r30 else None,
            "dd_pred_60d": r60.get("dd_pred") if r60 else None,
            "edge_30d": r30.get("edge") if r30 else None,
            "edge_60d": r60.get("edge") if r60 else None,
            "max_high_pct": round(max(float(r.get("max_high_pct") or 0.0)
                                      for r in (r30, r60) if r), 4),
            "max_dd_pct": round(min(float(r.get("max_drawdown_pct") or 0.0)
                                    for r in (r30, r60) if r), 4),
            "state_30d": _state(r30),
            "state_60d": _state(r60),
            "touch_bar_30d": r30.get("touch_bar") if r30 else None,
            "touch_bar_60d": r60.get("touch_bar") if r60 else None,
        })
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_from_scan(stocks: list, scan_date: str = None) -> dict:
    """Nightly orchestrator (called from run_scan_job after the screener):
    stage -> activate -> refresh/resolve -> curve point -> decile stats ->
    health -> summary.json. Returns per-regime counters. No-ops (with an
    ERROR log) when calibration_tracking/v2/config.json is missing."""
    config = _load_config()
    if config is None:
        log.error(f"{CAL_PREFIX}/config.json missing — calibration tracker is a no-op "
                  f"(run backend/scratch/build_v2_config.py after the v4 model ships)")
        return {}
    # bar source migrated to FMP 2026-06-19 (ThetaData dropped) — no theta preflight
    as_of = (scan_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]

    pending_doc = _gcs_impl["read"](f"{CAL_PREFIX}/pending_entries.json", {"pending": []})
    pending = pending_doc.get("pending", []) if isinstance(pending_doc, dict) else []
    open_states = {name: _gcs_impl["read"](f"{CAL_PREFIX}/{name}/open_state.json", {"records": []})
                   for name in REGIMES}

    counters = {name: {"staged": 0, "activated": 0, "dropped": 0,
                       "touched": 0, "terminal": 0, "open": 0, "pending": 0}
                for name in REGIMES}

    # ── Phase A: stage tonight's qualifying picks (no price) ──
    for name, cfg in REGIMES.items():
        open_syms = {r["symbol"] for r in open_states[name].get("records", [])}
        counters[name]["staged"] = _stage_pending_entries(
            stocks or [], as_of, cfg, config, pending, open_syms)

    # ── Phase B: activate pendings at the official EOD close of their scan date ──
    # C8: pendings staged TONIGHT (scan_date == as_of) are excluded — the scan
    # fires ~16:16 ET, before ThetaData finalizes the EOD bar (~16:30 ET), so
    # activation happens strictly on subsequent runs and the staging night must
    # not consume an activation attempt.
    act_candidates = [p for p in pending
                      if not p.get("_consumed") and p.get("scan_date") != as_of]

    # ── bars come from FMP (_fetch_eod_bars); `theta` stays None for the pooled signature ──
    theta = None

    act_reqs = sorted({(p["symbol"], p["scan_date"], p["scan_date"])
                       for p in act_candidates})
    act_bars = _fetch_bars_pooled(theta, act_reqs)
    for name, cfg in REGIMES.items():
        activated, dropped = _activate_pending_entries(
            cfg, as_of, act_candidates, open_states[name], act_bars, config)
        counters[name]["activated"] = activated
        counters[name]["dropped"] = dropped
    pending = [p for p in pending if not p.get("_consumed")]
    _gcs_impl["write"](f"{CAL_PREFIX}/pending_entries.json", {"pending": pending})
    for name in REGIMES:
        counters[name]["pending"] = sum(1 for p in pending if p.get("regime") == name)

    # ── Refresh + resolve (incremental bars, pooled once per symbol) ──
    starts = {}
    for st in open_states.values():
        for r in st.get("records", []):
            lbd = r.get("last_bar_date")
            if not lbd:
                continue
            nxt = (datetime.strptime(lbd, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
            cur = starts.get(r["symbol"])
            starts[r["symbol"]] = min(cur, nxt) if cur else nxt
    refresh_reqs = sorted((sym, start, as_of) for sym, start in starts.items() if start <= as_of)
    refresh_bars = _fetch_bars_pooled(theta, refresh_reqs)
    bars_by_symbol = {req[0]: bars for req, bars in refresh_bars.items()}
    for name, cfg in REGIMES.items():
        res = _refresh_open_records(cfg, as_of, open_states[name], bars_by_symbol)
        counters[name].update(res)
        _gcs_impl["write"](f"{CAL_PREFIX}/{name}/open_state.json", open_states[name])

    # ── Stats: curve point, decile rows, health, summary ──
    prev_health = _gcs_impl["read"](f"{CAL_PREFIX}/health.json", {}) or {}
    health_doc = {"computed_date": as_of, "model_version": config.get("model_version"),
                  "regimes": {}}
    per_regime = {}
    records_by_regime = {}
    for name, cfg in REGIMES.items():
        resolved = _load_resolved_records(cfg)
        live = list(open_states[name].get("records", []))
        nondropped = live + [r for r in resolved if r.get("status") != "DROPPED"]
        n_dropped = sum(1 for r in resolved if r.get("status") == "DROPPED")
        records_by_regime[name] = nondropped

        line, pooled = _curve_point_full(nondropped, config, cfg, as_of)
        curve_history = _upsert_curve_point(cfg, line)
        decile_rows = _compute_decile_rows(nondropped, config, cfg)

        n_pending = counters[name]["pending"]
        _gcs_impl["write"](f"{CAL_PREFIX}/{name}/decile_stats.json", {
            "computed_date": as_of,
            "regime": name,
            "model_version": config.get("model_version"),
            "deciles": decile_rows,
            "censoring_curve": line,
            "decile_thresholds": (config.get("decile_thresholds") or {}).get(name),
            "n_open": counters[name]["open"],
            "n_pending": n_pending,
            "n_dropped": n_dropped,
        })

        prev_cb = ((prev_health.get("regimes") or {}).get(name) or {}).get("consecutive_below_band", 0)
        hb = _health_block(pooled, config, as_of, int(prev_cb or 0))
        health_doc["regimes"][name] = hb
        counters[name]["health"] = hb["status"]
        if hb["kill_switch_active"]:
            log.warning(f"[{name}] calibration KILL SWITCH active: z={hb['z_score']} "
                        f"(O={pooled['observed']}, E={pooled['expected']:.2f})")

        per_regime[name] = {
            "nondropped": nondropped,
            "n_dropped": n_dropped,
            "n_pending": n_pending,
            "curve_history": curve_history,
            "decile_rows": decile_rows,
            "pooled": pooled,
            "health": hb,
        }
    _gcs_impl["write"](f"{CAL_PREFIX}/health.json", health_doc)

    summary = _assemble_summary(config, as_of, per_regime, records_by_regime)
    _gcs_impl["write"](f"{CAL_PREFIX}/summary.json", summary)

    for name in REGIMES:
        c = counters[name]
        log.info(f"[{name}] staged={c['staged']} activated={c['activated']} dropped={c['dropped']} "
                 f"touched={c['touched']} terminal={c['terminal']} open={c['open']} "
                 f"pending={c['pending']} health={c.get('health')}")
    return counters


def _assemble_summary(config: dict, as_of: str, per_regime: dict,
                      records_by_regime: dict) -> dict:
    """summary.json exactly per the calibration-v2 contract (C5)."""
    horizons = {}
    for name, cfg in REGIMES.items():
        d = per_regime[name]
        recs = d["nondropped"]
        n_total = len(recs)
        n_matured = sum(1 for r in recs if r.get("resolution") in ("TOUCH", "TERMINAL"))
        n_open = sum(1 for r in recs if r.get("status") == "OPEN")
        n_touched = sum(1 for r in recs if r.get("resolution") == "TOUCH")

        scan_dates = _load_entry_scan_dates(cfg)
        scan_dates |= {pt.get("scan_date") for pt in d["curve_history"] if pt.get("scan_date")}
        tracking_since = min(scan_dates) if scan_dates else as_of
        latest_scan = max(scan_dates) if scan_dates else as_of

        curve_pooled = [{
            "scan_date": pt.get("scan_date"),
            "expected": pt.get("expected"),
            "observed": pt.get("observed"),
            "ci_low": pt.get("ci_low"),
            "ci_high": pt.get("ci_high"),
        } for pt in d["curve_history"]]
        curve_by_decile = {}
        for dec in range(1, 11):
            key = str(dec)
            curve_by_decile[key] = [pt["by_decile"][key]
                                    for pt in d["curve_history"]
                                    if isinstance(pt.get("by_decile"), dict)
                                    and key in pt["by_decile"]]

        pooled = d["pooled"]
        horizons[cfg.horizon_label] = {
            "horizon_bars": cfg.window_bars,
            "barrier_pct": int(cfg.barrier_pct),
            "cycle": {
                "tracking_since": tracking_since,
                "n_scan_dates": len(scan_dates),
                "latest_scan_date": latest_scan,
                "n_total": n_total,
                "n_matured": n_matured,
                "n_open": n_open,
                "n_touched": n_touched,
                "n_pending": d["n_pending"],
                "n_dropped": d["n_dropped"],
            },
            "headline": {
                "expected_touches_to_date": round(pooled["expected"], 4),
                "observed_touches_to_date": pooled["observed"],
                "ci_low": round(pooled["ci_low"], 4),
                "ci_high": round(pooled["ci_high"], 4),
                "z": round(pooled["z"], 4) if pooled["z"] is not None else None,
            },
            "health": d["health"],
            "deciles": d["decile_rows"],
            "curve": {
                "pooled": curve_pooled,
                "by_decile": curve_by_decile,
            },
        }
    return {
        "schema_version": "calibration-v2",
        "as_of": as_of,
        "model": {
            "version": config.get("model_version"),
            "trained_through": config.get("trained_through"),
            "decile_threshold_source": config.get("decile_threshold_source"),
        },
        "horizons": horizons,
        "records": _build_calib_records(records_by_regime, as_of),
    }


def read_summary() -> Optional[dict]:
    """Precomputed summary.json for GET /performance/calibration-v2
    (single GCS read, no recompute). None when not yet written."""
    return _gcs_impl["read"](f"{CAL_PREFIX}/summary.json", None)


def read_health() -> Optional[dict]:
    """health.json (informational; the endpoint serves summary.json)."""
    return _gcs_impl["read"](f"{CAL_PREFIX}/health.json", None)
