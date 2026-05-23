#!/usr/bin/env python3
"""
Signal Tracker — CB Screener v1.2 (May 2026 — Commit 2)
=========================================================
Tracks ML model predictions over time using cohort-based cycles and validates
calibration against the baseline distribution from training.

WHAT IT DOES
  For every enriched stock (any stock with hit_prob > 0, typically ~30–50 per
  scan), store a forward-looking prediction with the calibrated decile bucket
  and a computed options-spread EV. Track each prediction's outcome over a
  28-day fate window. Roll predictions into 30-day cohorts ("cycles") for
  aggregate accuracy measurement bucketed by decile.

PRIMARY METRIC: DECILE HIT RATES
  Calibration baseline (from 21,650 OOS training samples):
    D10 hit rate: 22.3%   D1 hit rate: 1.1%   (≈20× odds ratio)
  A healthy model continues to produce that separation. If it stops, retrain.

KILL SWITCH
  Rolling 90-day window D10 hit rate. If it drops below 10%, the model has
  degraded materially and needs retraining. Surfaced in cycle archives and
  logged on every scan.

CYCLE LIFECYCLE
  A cycle is identified by the date it opened (cycle_id = YYYY-MM-DD).
  Each cycle moves through three states:

  COLLECTING  Days 0–30 from cycle open. Accepts new hit_prob>0 predictions.
              At day 30, the cycle stops accepting new entries; the next
              cycle opens immediately.
  RESOLVING   Predictions still have open 28-day fate windows. No new
              entries. Each prediction continues being marked hit/expired
              as price action unfolds.
  ARCHIVED    All predictions in the cycle have resolved. A summary
              archived.json is written with aggregate stats (hit rate by
              decile, signal strength, mean realized return, etc.) and a
              calibration check comparing to baseline.

EV METHODOLOGY (mirrors frontend TradierOptionsCard v3)
  Computed for every prediction where price + IV permit spread synthesis.
  spot, P20 from scan; spread synthesized: ATM long, +10% short, 30 DTE,
  net_debit = width × clamp(IV × 0.65, 0.15, 0.50). When options_spread is
  live, use those strikes/debits instead.

  Probability ladder (calibrated on 21,650 OOS samples, May 2026):
    P5  = min(P20 × 3.41, 0.80)   P(close ≥ +5%  in 4w)
    P10 = min(P20 × 2.29, 0.65)   P(close ≥ +10% in 4w)
    P15 = min(P20 × 1.49, 0.50)   P(close ≥ +15% in 4w)
    P20 = P20 (raw model output)  P(touch +20% daily high in 4w)

  Interpolated:
    P(BE)  = interpolate(break_even_move_pct, ladder)
    P(max) = interpolate(short_strike_move_pct, ladder)

  EV (per contract):
    EV = P(max) × max_gain − (1 − P(BE)) × max_loss

  Stored as a sub-block on every prediction row when computable; absent on
  rows where price/IV can't construct a spread. Used downstream for the
  "what would each decile have made as spreads" P&L attribution.

GCS LAYOUT
  hit_rate_tracking/
    current_cycle.json                  Pointer + state log
    cycles/{cycle_id}/
      predictions.jsonl                 Append-only: every hit_prob>0 entry
      open.json                         Predictions still tracking
      archived.json                     Written when cycle fully resolves
    rolling_health.json                 Last 90d D10 hit rate + kill-switch flag

  stock_history/{SYMBOL}.json           [date, price, composite] per scan
                                        (unchanged from prior version)

STORAGE NOTES
  predictions.jsonl is immutable and survives forever — every prediction
  the model has ever made, gsutil-fetchable for offline model validation
  and re-training. open.json and archived.json are derived state.

Invoked once per scan by run_scan_job.py after save_scan_to_gcs() completes.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GCS_BUCKET = "screener-signals-carbonbridge"

# Tracking parameters (locked May 2026)
P20_INCLUSION       = 0.0      # Track every stock with hit_prob > this
HIT_THRESHOLD_PCT   = 20.0     # +20% from entry counts as hit
HIT_WINDOW_DAYS     = 60       # 60 calendar days — tracks through spread expiration
CYCLE_LENGTH_DAYS   = 60       # New cycle every 60 calendar days
STOCK_HISTORY_KEEP_DAYS = 365  # Trim chart history beyond this

# Calibration baselines (from 21,650 OOS training samples, May 2026)
# D10 should hit ~22.3%, D1 ~1.1%. We track this every cycle to detect drift.
D10_CALIBRATION_HIT_RATE = 0.223
D1_CALIBRATION_HIT_RATE  = 0.011
KILL_SWITCH_THRESHOLD    = 0.10

# Calibration baselines: 30d/legacy (from 21,650 OOS samples, May 2026)
D10_CALIBRATION_HIT_RATE_30D = 0.223
D1_CALIBRATION_HIT_RATE_30D  = 0.011
KILL_SWITCH_THRESHOLD_30D    = 0.10

# Calibration baselines: 60d (from v3 model calibration, May 2026)
D10_CALIBRATION_HIT_RATE_60D = 0.832
D1_CALIBRATION_HIT_RATE_60D  = 0.015
KILL_SWITCH_THRESHOLD_60D    = 0.40

# Kill-switch parameters: if the rolling 90-day D10 hit rate drops below the
# threshold, the model has degraded materially and needs retraining.
KILL_SWITCH_WINDOW_DAYS     = 90

# Calibrated probability ladder multipliers (30d / legacy)
P5_MULT  = 3.41
P10_MULT = 2.29
P15_MULT = 1.49

# Calibrated probability ladder multipliers (60d regime)
P5_MULT_60D  = 2.44
P10_MULT_60D = 1.85
P15_MULT_60D = 1.35
P5_CAP_60D   = 0.98
P10_CAP_60D  = 0.95
P15_CAP_60D  = 0.90

# Synthesized spread structure (30d / legacy)
SYNTH_LONG_OFFSET  = 0.05    # Long call strike at +5% from spot
SYNTH_SHORT_OFFSET = 0.20    # Short call strike at +20% from spot
SYNTH_DTE_DAYS     = 30

# Synthesized spread structure (60d regime)
SYNTH_LONG_OFFSET_60D  = 0.05    # Long call strike at +5% from spot
SYNTH_SHORT_OFFSET_60D = 0.20 # Short call strike at +20% from spot
SYNTH_DTE_DAYS_60D     = 60

# IV estimation bounds
IV_FACTOR_MIN      = 0.15    # Floor on debit/width ratio
IV_FACTOR_MAX      = 0.50    # Ceiling on debit/width ratio
IV_FACTOR_SCALE    = 0.65    # Multiplier on annualized IV

# Canonical GCS paths
CYCLE_POINTER_PATH    = "hit_rate_tracking/current_cycle.json"
CYCLES_PREFIX         = "hit_rate_tracking/cycles"
ROLLING_HEALTH_PATH   = "hit_rate_tracking/rolling_health.json"
STOCK_HISTORY_PREFIX  = "stock_history"


# ---------------------------------------------------------------------------
# GCS I/O (unchanged from prior version)
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
            if not path.startswith(STOCK_HISTORY_PREFIX):
                try:
                    patch_url = f"https://www.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{path.replace('/', '%2F')}"
                    requests.patch(
                        patch_url,
                        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                        json={"cacheControl": "no-cache, no-store, max-age=0, must-revalidate"},
                        timeout=10
                    )
                except Exception as patch_e:
                    log.warning(f"GCS metadata patch for {path} failed: {patch_e}")
            return True
        log.warning(f"GCS write {path}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"GCS write {path} failed: {e}")
    return False


# ---------------------------------------------------------------------------
# EV calculation — Python mirror of frontend TradierOptionsCard v3
# ---------------------------------------------------------------------------

def _round_strike(spot: float) -> float:
    """Round to broker-style strike increments: $5 for spot>=$50, $2.5 for
    spot>=$10, else $1. Matches roundStrike() in TradierOptionsCard."""
    inc = 5.0 if spot >= 50 else 2.5 if spot >= 10 else 1.0
    return round(spot / inc) * inc


def _interpolate_p(move_pct: float, ladder: list) -> float:
    """Piecewise-linear interpolation across the calibrated probability ladder.
    ladder: list of (move_pct, probability) tuples in ascending order.
    Mirrors interpolateP() in TradierOptionsCard."""
    if move_pct <= 0:
        return 0.85
    if move_pct <= ladder[0][0]:
        return min(ladder[0][1] + (ladder[0][0] - move_pct) * 0.02, 0.90)
    if move_pct >= ladder[-1][0]:
        return max(ladder[-1][1] - (move_pct - ladder[-1][0]) * 0.01, 0.01)
    for i in range(len(ladder) - 1):
        x0, y0 = ladder[i]
        x1, y1 = ladder[i + 1]
        if x0 <= move_pct <= x1:
            frac = (move_pct - x0) / (x1 - x0)
            return y0 + (y1 - y0) * frac
    return ladder[-1][1]


def calculate_spread_ev(stock: dict, is_60d: bool = False) -> Optional[dict]:
    """Compute the deployable options-spread EV for a P20-qualified stock.

    Mirrors TradierOptionsCard v3 exactly: uses live tradier_spread when
    present, else synthesizes a bull call spread (ATM long, short at offset)
    with debit estimated from current IV.

    Returns a dict with all spread components and EV calculation, or None if
    not computable (no price, no P20, can't construct strikes, or spot < $1).
    """
    p20 = stock.get("hit_prob_60d") if is_60d else stock.get("hit_prob")
    if p20 is None:
        p20 = stock.get("hit_prob") or 0
    spot = stock.get("price") or 0
    if p20 <= 0 or spot <= 0:
        return None
    # Penny stocks have no meaningful options market and the rounding logic
    # produces degenerate strike pairs (e.g. long=$0). Skip below $1.
    if spot < 1.0:
        return None

    # Calibrated probability ladder
    if is_60d:
        p5  = min(p20 * P5_MULT_60D,  P5_CAP_60D)
        p10 = min(p20 * P10_MULT_60D, P10_CAP_60D)
        p15 = min(p20 * P15_MULT_60D, P15_CAP_60D)
    else:
        p5  = min(p20 * P5_MULT,  0.80)
        p10 = min(p20 * P10_MULT, 0.65)
        p15 = min(p20 * P15_MULT, 0.50)
    ladder = [(5.0, p5), (10.0, p10), (15.0, p15), (20.0, p20)]

    # Spread structure: live or synthesized
    live_sp = stock.get("options_spread")
    synth_dte = SYNTH_DTE_DAYS_60D if is_60d else SYNTH_DTE_DAYS
    synth_long_offset = SYNTH_LONG_OFFSET_60D if is_60d else SYNTH_LONG_OFFSET
    synth_short_offset = SYNTH_SHORT_OFFSET_60D if is_60d else SYNTH_SHORT_OFFSET

    if live_sp and isinstance(live_sp, dict) and live_sp.get("long_strike") is not None:
        sp = {
            "spot": float(live_sp.get("spot", spot)),
            "long_strike": float(live_sp["long_strike"]),
            "short_strike": float(live_sp["short_strike"]),
            "long_mid": float(live_sp.get("long_mid", 0)),
            "short_mid": float(live_sp.get("short_mid", 0)),
            "net_debit": float(live_sp["net_debit"]),
            "max_gain_per_contract": float(live_sp["max_gain_per_contract"]),
            "max_loss_per_contract": float(live_sp["max_loss_per_contract"]),
            "break_even_price": float(live_sp["break_even_price"]),
            "break_even_move_pct": float(live_sp["break_even_move_pct"]),
            "expiration": live_sp.get("expiration"),
            "dte": int(live_sp.get("dte", synth_dte)),
            "long_greeks": live_sp.get("long_greeks"),
            "short_greeks": live_sp.get("short_greeks"),
            "long_iv": live_sp.get("long_iv"),
            "short_iv": live_sp.get("short_iv"),
        }
        is_live = True
    else:
        long_strike = _round_strike(spot * (1.0 + synth_long_offset))
        short_strike = _round_strike(spot * (1.0 + synth_short_offset))
        if short_strike <= long_strike:
            return None
        width = short_strike - long_strike
        iv = stock.get("options_iv_current") or 0.30
        iv_factor = min(IV_FACTOR_MAX, max(IV_FACTOR_MIN, iv * IV_FACTOR_SCALE))
        net_debit = round(width * iv_factor * 100) / 100
        if net_debit <= 0 or net_debit >= width:
            return None
        max_gain = (width - net_debit) * 100
        max_loss = net_debit * 100
        be_price = long_strike + net_debit
        be_pct = ((be_price - spot) / spot) * 100
        exp = datetime.now() + timedelta(days=synth_dte)
        while exp.weekday() != 4:  # Friday
            exp += timedelta(days=1)
        sp = {
            "spot": spot,
            "long_strike": long_strike,
            "short_strike": short_strike,
            "long_mid": round(net_debit * 0.65, 2),
            "short_mid": round(net_debit * 0.35, 2),
            "net_debit": net_debit,
            "max_gain_per_contract": max_gain,
            "max_loss_per_contract": max_loss,
            "break_even_price": be_price,
            "break_even_move_pct": be_pct,
            "expiration": exp.strftime("%Y-%m-%d"),
            "dte": synth_dte,
            "long_greeks": None,
            "short_greeks": None,
            "long_iv": None,
            "short_iv": None,
        }
        is_live = False

    # Interpolated probabilities and EV
    short_pct = ((sp["short_strike"] - sp["spot"]) / sp["spot"]) * 100
    p_be = _interpolate_p(sp["break_even_move_pct"], ladder)
    p_max = _interpolate_p(short_pct, ladder)
    ev = p_max * sp["max_gain_per_contract"] - (1 - p_be) * sp["max_loss_per_contract"]
    ev_per_dollar = ev / sp["max_loss_per_contract"] if sp["max_loss_per_contract"] > 0 else 0

    # Assessment ladder (mirrors frontend buckets)
    if ev_per_dollar > 0.15:
        assessment = "STRONG_EDGE"
    elif ev_per_dollar > 0.05:
        assessment = "MODERATE_EDGE"
    elif ev_per_dollar > 0:
        assessment = "MARGINAL_EDGE"
    elif ev_per_dollar > -0.10:
        assessment = "SLIGHT_NEGATIVE"
    else:
        assessment = "NO_EDGE"

    return {
        "is_live_spread": is_live,
        "long_strike": sp["long_strike"],
        "short_strike": sp["short_strike"],
        "long_mid": sp["long_mid"],
        "short_mid": sp["short_mid"],
        "net_debit": sp["net_debit"],
        "max_gain_per_contract": round(sp["max_gain_per_contract"], 2),
        "max_loss_per_contract": round(sp["max_loss_per_contract"], 2),
        "break_even_price": round(sp["break_even_price"], 2),
        "break_even_move_pct": round(sp["break_even_move_pct"], 2),
        "expiration": sp["expiration"],
        "dte": sp["dte"],
        "p_breakeven": round(p_be, 4),
        "p_max_profit": round(p_max, 4),
        "p5": round(p5, 4),
        "p10": round(p10, 4),
        "p15": round(p15, 4),
        "ev_dollars": round(ev, 2),
        "ev_per_dollar": round(ev_per_dollar, 4),
        "assessment": assessment,
        "long_greeks": sp.get("long_greeks"),
        "short_greeks": sp.get("short_greeks"),
        "long_iv": sp.get("long_iv"),
        "short_iv": sp.get("short_iv"),
    }


# ---------------------------------------------------------------------------
# Decile / signal-strength bucketing (matches frontend)
# ---------------------------------------------------------------------------

def _decile(p20: float, is_60d: bool = False) -> int:
    """OOS-calibrated decile thresholds."""
    if is_60d:
        if p20 >= 0.57808: return 10
        if p20 >= 0.50809: return 9
        if p20 >= 0.46325: return 8
        if p20 >= 0.39994: return 7
        if p20 >= 0.33742: return 6
        if p20 >= 0.28662: return 5
        if p20 >= 0.26955: return 4
        if p20 >= 0.21729: return 3
        if p20 >= 0.21060: return 2
        return 1
    else:
        if p20 >= 0.17: return 10
        if p20 >= 0.07: return 9
        if p20 >= 0.05: return 8
        if p20 >= 0.03: return 7
        if p20 >= 0.02: return 6
        if p20 >= 0.013: return 5
        if p20 >= 0.009: return 4
        if p20 >= 0.006: return 3
        if p20 >= 0.004: return 2
        return 1


def _signal_strength(p20: float, is_60d: bool = False) -> str:
    if is_60d:
        if p20 >= 0.55: return "STRONG"
        if p20 >= 0.40: return "MODERATE"
        if p20 >= 0.25: return "MILD"
        return "WEAK"
    else:
        if p20 >= 0.15: return "STRONG"
        if p20 >= 0.08: return "MODERATE"
        if p20 >= 0.03: return "MILD"
        return "WEAK"


# ---------------------------------------------------------------------------
# Cycle management
# ---------------------------------------------------------------------------

def _load_cycle_state() -> dict:
    """Read current_cycle.json. Returns a freshly-initialized state if not yet
    written (first-run bootstrap)."""
    default = {
        "collecting_cycle_id": None,
        "collecting_start": None,
        "collecting_ends": None,
        "resolving_cycle_ids": [],
        "archived_cycle_ids": [],
    }
    state = _gcs_read(CYCLE_POINTER_PATH, default)
    if not isinstance(state, dict):
        return default
    # Defensive: backfill any missing fields from default
    for k, v in default.items():
        state.setdefault(k, v)
    return state


def _save_cycle_state(state: dict) -> None:
    _gcs_write(CYCLE_POINTER_PATH, state)


def _open_new_cycle(state: dict, today_str: str) -> dict:
    """Open a new collecting cycle starting today. Mutates and returns state."""
    new_id = today_str
    ends = (datetime.strptime(today_str, "%Y-%m-%d")
            + timedelta(days=CYCLE_LENGTH_DAYS)).strftime("%Y-%m-%d")
    state["collecting_cycle_id"] = new_id
    state["collecting_start"] = today_str
    state["collecting_ends"] = ends
    # Initialize empty open.json so downstream code doesn't 404
    _gcs_write(f"{CYCLES_PREFIX}/{new_id}/open.json", {"predictions": []})
    log.info(f"  Cycle {new_id} opened (collects until {ends})")
    return state


def _advance_cycles_if_needed(state: dict, today_str: str) -> dict:
    """Roll cycles forward when the collecting window expires.

    If today is on/after collecting_ends, the current cycle moves to RESOLVING
    and a new collecting cycle opens. Mutates and returns state.
    """
    # Bootstrap: no cycle has ever been opened.
    if state["collecting_cycle_id"] is None:
        return _open_new_cycle(state, today_str)

    if today_str >= state["collecting_ends"]:
        old_id = state["collecting_cycle_id"]
        if old_id not in state["resolving_cycle_ids"]:
            state["resolving_cycle_ids"].append(old_id)
            log.info(f"  Cycle {old_id} → RESOLVING (collected for "
                     f"{CYCLE_LENGTH_DAYS}d, predictions still tracking)")
        _open_new_cycle(state, today_str)
    return state


def _attempt_archive_resolving_cycles(state: dict, today_str: str) -> dict:
    """For each cycle in RESOLVING state, if its open.json is empty, write
    archived.json with summary stats and move to archived_cycle_ids.

    Predictions in open.json get closed independently by _process_open_predictions
    every day. Once all predictions for a cycle have resolved, this archiver
    finalizes the summary.
    """
    still_resolving = []
    for cycle_id in state["resolving_cycle_ids"]:
        open_data = _gcs_read(f"{CYCLES_PREFIX}/{cycle_id}/open.json",
                              {"predictions": []})
        open_preds = (open_data or {}).get("predictions", [])
        if open_preds:
            still_resolving.append(cycle_id)
            continue
        # All predictions resolved — compute summary and archive
        summary = _compute_cycle_summary(cycle_id, today_str)
        if _gcs_write(f"{CYCLES_PREFIX}/{cycle_id}/archived.json", summary):
            state["archived_cycle_ids"].append(cycle_id)
            log.info(f"  Cycle {cycle_id} → ARCHIVED "
                     f"(n={summary['total_predictions']}, "
                     f"hit_rate={summary['hit_rate']:.1%})")
        else:
            log.warning(f"  Cycle {cycle_id} archive write failed; will retry")
            still_resolving.append(cycle_id)
    state["resolving_cycle_ids"] = still_resolving
    return state


def _compute_cycle_summary(cycle_id: str, today_str: str) -> dict:
    """Read the immutable predictions.jsonl for the cycle and roll up stats."""
    raw = _gcs_read_text(f"{CYCLES_PREFIX}/{cycle_id}/predictions.jsonl", "")
    latest_by_key = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        key = (row.get("symbol"), row.get("entry_date"))
        existing = latest_by_key.get(key)
        if existing is None:
            latest_by_key[key] = row
        elif existing.get("outcome") == "OPEN" and row.get("outcome") != "OPEN":
            latest_by_key[key] = row

    preds = list(latest_by_key.values())

    if not preds:
        return {
            "cycle_id": cycle_id,
            "archived_date": today_str,
            "total_predictions": 0,
            "hit_count": 0,
            "hit_rate": 0.0,
            "predictions": [],
        }

    hit_count = sum(1 for p in preds if p.get("outcome") == "HIT")
    expired_count = sum(1 for p in preds if p.get("outcome") == "EXPIRED")
    n = len(preds)

    # Mean realized return (final price at resolution vs entry)
    realized_returns = [p.get("realized_return_pct", 0) for p in preds
                        if p.get("realized_return_pct") is not None]
    mean_realized = sum(realized_returns) / len(realized_returns) if realized_returns else 0

    # Excursion stats — peak run-up and deepest drawdown observed within each
    # prediction's fate window. These describe the risk shape of the strategy:
    # high mean_max_high alongside high mean_max_drawdown means choppy paths.
    max_highs = [p.get("max_high_observed_pct", 0) for p in preds
                 if p.get("max_high_observed_pct") is not None]
    max_dds = [p.get("max_drawdown_observed_pct", 0) for p in preds
               if p.get("max_drawdown_observed_pct") is not None]
    mean_max_high = sum(max_highs) / len(max_highs) if max_highs else 0
    mean_max_drawdown = sum(max_dds) / len(max_dds) if max_dds else 0
    worst_drawdown = min(max_dds) if max_dds else 0
    best_runup = max(max_highs) if max_highs else 0

    # Aggregate dollar EV vs realized P&L (assuming 1 contract per prediction)
    sum_ev = sum(p.get("ev_dollars", 0) or 0 for p in preds)
    # Realized contract P&L: hit → max_gain (price reached short strike);
    # expired w/ final price ≥ breakeven → fractional; else → -max_loss.
    sum_realized = 0
    for p in preds:
        outcome = p.get("outcome")
        if outcome == "HIT":
            sum_realized += p.get("max_gain_per_contract", 0) or 0
        elif outcome == "EXPIRED":
            sum_realized += (p.get("realized_contract_pnl", 0) or 0)

    # Hit rate by decile and signal strength
    by_decile = {}
    by_signal = {}
    for p in preds:
        d = p.get("decile", 1)
        sig = p.get("signal_strength", "WEAK")
        by_decile.setdefault(d, {"n": 0, "hits": 0})
        by_decile[d]["n"] += 1
        if p.get("outcome") == "HIT":
            by_decile[d]["hits"] += 1
        by_signal.setdefault(sig, {"n": 0, "hits": 0})
        by_signal[sig]["n"] += 1
        if p.get("outcome") == "HIT":
            by_signal[sig]["hits"] += 1
    for d in by_decile:
        by_decile[d]["hit_rate"] = round(
            by_decile[d]["hits"] / by_decile[d]["n"], 4) if by_decile[d]["n"] else 0
    for sig in by_signal:
        by_signal[sig]["hit_rate"] = round(
            by_signal[sig]["hits"] / by_signal[sig]["n"], 4) if by_signal[sig]["n"] else 0

    # Options portfolio P&L aggregates (1 contract per prediction)
    total_cost_basis = sum(p.get("entry_cost_basis") or 0 for p in preds)
    total_options_pnl = sum(p.get("options_realized_pnl") or 0 for p in preds
                           if p.get("options_realized_pnl") is not None)
    options_winners = sum(1 for p in preds if p.get("options_outcome") == "PROFIT")
    options_losers = sum(1 for p in preds if p.get("options_outcome") == "LOSS")
    options_with_outcome = options_winners + options_losers
    options_win_rate = round(options_winners / options_with_outcome, 4) if options_with_outcome > 0 else None
    options_return_pct = round(
        (total_options_pnl / total_cost_basis) * 100, 4
    ) if total_cost_basis > 0 else None

    is_60d_cycle = any(p.get("regime") == "60d" for p in preds)

    return {
        "cycle_id": cycle_id,
        "archived_date": today_str,
        "total_predictions": n,
        "hit_count": hit_count,
        "expired_count": expired_count,
        "hit_rate": round(hit_count / n, 4),
        "mean_realized_return_pct": round(mean_realized, 4),
        "mean_max_runup_pct": round(mean_max_high, 4),
        "mean_max_drawdown_pct": round(mean_max_drawdown, 4),
        "best_runup_pct": round(best_runup, 4),
        "worst_drawdown_pct": round(worst_drawdown, 4),
        "aggregate_ev_dollars": round(sum_ev, 2),
        "aggregate_realized_pnl_dollars": round(sum_realized, 2),
        "ev_realization_ratio": round(sum_realized / sum_ev, 4) if sum_ev != 0 else 0,
        # Paper-trading portfolio P&L
        "total_cost_basis": round(total_cost_basis, 2),
        "total_options_pnl": round(total_options_pnl, 2),
        "options_win_rate": options_win_rate,
        "options_return_pct": options_return_pct,
        "options_winners": options_winners,
        "options_losers": options_losers,
        "hit_rate_by_decile": by_decile,
        "hit_rate_by_signal_strength": by_signal,
        "calibration_check": _calibration_check(by_decile, is_60d=is_60d_cycle),
        "predictions": preds,
    }


def _calibration_check(by_decile: dict, is_60d: bool = False) -> dict:
    """Compare observed D10 and D1 hit rates against the training baseline.
    Healthy: D10 hit rate well above D1, ideally near baseline.
    Returns metrics suitable for a UI calibration card."""
    d10 = by_decile.get(10, {})
    d1 = by_decile.get(1, {})
    d10_hr = d10.get("hit_rate", 0)
    d1_hr = d1.get("hit_rate", 0)
    odds_ratio = (d10_hr / d1_hr) if d1_hr > 0 else None

    if is_60d:
        base_d10 = D10_CALIBRATION_HIT_RATE_60D
        base_d1 = D1_CALIBRATION_HIT_RATE_60D
        kill_threshold = KILL_SWITCH_THRESHOLD_60D
        note = "D10 must exceed kill-switch threshold (40%) and ideally track the 83.2% baseline. Sample size <5 in D10 -> unstable."
    else:
        base_d10 = D10_CALIBRATION_HIT_RATE_30D
        base_d1 = D1_CALIBRATION_HIT_RATE_30D
        kill_threshold = KILL_SWITCH_THRESHOLD_30D
        note = "D10 must exceed kill-switch threshold (10%) and ideally track the 22.3% baseline. Sample size <5 in D10 -> unstable."

    baseline_odds = base_d10 / base_d1 if base_d1 > 0 else 20.0

    # Health flag: D10 must remain well above the kill switch threshold AND
    # well above D1. If D10 < kill switch threshold, the model has degraded.
    healthy = d10.get("n", 0) >= 5 and d10_hr >= kill_threshold
    return {
        "d10_hit_rate": round(d10_hr, 4),
        "d10_n": d10.get("n", 0),
        "d1_hit_rate": round(d1_hr, 4),
        "d1_n": d1.get("n", 0),
        "d10_baseline": base_d10,
        "d1_baseline": base_d1,
        "observed_odds_ratio": round(odds_ratio, 2) if odds_ratio else None,
        "baseline_odds_ratio": round(baseline_odds, 2),
        "kill_switch_threshold": kill_threshold,
        "healthy": healthy,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Rolling 90-day D10 health monitor (kill switch)
# ---------------------------------------------------------------------------

def _compute_rolling_d10_health(state: dict, today_str: str) -> dict:
    """Compute D10 hit rate over the trailing 90-day window across all
    predictions (open + closed) and trigger kill-switch flag if below threshold.

    Reads predictions.jsonl across all known cycles (collecting + resolving +
    most-recent archived). Only counts predictions whose ENTRY date is within
    the 90-day window. For OPEN predictions, only count those whose fate window
    has closed (entry_date <= today - hit_window_days) so we don't artificially
    deflate the rate with still-unresolved setups.
    """
    today_dt = datetime.strptime(today_str, "%Y-%m-%d")
    window_start = today_dt - timedelta(days=KILL_SWITCH_WINDOW_DAYS)

    cycle_ids = []
    if state.get("collecting_cycle_id"):
        cycle_ids.append(state["collecting_cycle_id"])
    cycle_ids.extend(state.get("resolving_cycle_ids", []))
    # Most recent archived cycles too — bounded so we don't read everything.
    cycle_ids.extend(state.get("archived_cycle_ids", [])[-6:])

    # Dedupe last-known state of each (symbol, entry_date) — JSONL contains
    # both entry rows and close rows; the close row supersedes the entry.
    latest_by_key = {}
    for cycle_id in cycle_ids:
        raw = _gcs_read_text(f"{CYCLES_PREFIX}/{cycle_id}/predictions.jsonl", "")
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            key = (row.get("symbol"), row.get("entry_date"))
            # Prefer rows where outcome != OPEN (closed rows are written after entry)
            existing = latest_by_key.get(key)
            if existing is None:
                latest_by_key[key] = row
            elif existing.get("outcome") == "OPEN" and row.get("outcome") != "OPEN":
                latest_by_key[key] = row

    d10_n = 0
    d10_hits = 0
    d1_n = 0
    d1_hits = 0
    total_in_window = 0
    count_60d = 0

    # Accumulators for all deciles 1 to 10
    deciles_data = {d: {"n": 0, "hits": 0, "sum_probs": 0.0} for d in range(1, 11)}

    for row in latest_by_key.values():
        entry_date_str = row.get("entry_date")
        if not entry_date_str:
            continue
        try:
            entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d")
        except Exception:
            continue
        if entry_dt < window_start:
            continue

        total_in_window += 1
        if row.get("regime") == "60d":
            count_60d += 1

        # Skip not-yet-resolved predictions
        outcome = row.get("outcome")
        row_window_days = row.get("hit_window_days", 28)
        row_res_cutoff = today_dt - timedelta(days=row_window_days)
        if outcome == "OPEN" and entry_dt > row_res_cutoff:
            continue

        decile = row.get("decile")
        hit = outcome == "HIT" or (row.get("max_high_observed_pct", 0) >= HIT_THRESHOLD_PCT)

        # Accumulate decile stats (if decile is valid)
        if isinstance(decile, (int, float)) and 1 <= int(decile) <= 10:
            d_idx = int(decile)
            deciles_data[d_idx]["n"] += 1
            if hit:
                deciles_data[d_idx]["hits"] += 1
            # Expected rate is mean predicted probability (p20/hit_prob)
            prob = row.get("p20") or row.get("hit_prob") or row.get("hit_prob_60d") or 0.0
            deciles_data[d_idx]["sum_probs"] += prob

        if decile == 10:
            d10_n += 1
            if hit:
                d10_hits += 1
        elif decile == 1:
            d1_n += 1
            if hit:
                d1_hits += 1

    d10_hr = d10_hits / d10_n if d10_n > 0 else 0
    d1_hr = d1_hits / d1_n if d1_n > 0 else 0

    # Determine dominant regime in the trailing window
    is_60d_dominated = (count_60d > total_in_window / 2) if total_in_window > 0 else False

    if is_60d_dominated:
        baseline_d10 = D10_CALIBRATION_HIT_RATE_60D
        baseline_d1 = D1_CALIBRATION_HIT_RATE_60D
        kill_threshold = KILL_SWITCH_THRESHOLD_60D
    else:
        baseline_d10 = D10_CALIBRATION_HIT_RATE_30D
        baseline_d1 = D1_CALIBRATION_HIT_RATE_30D
        kill_threshold = KILL_SWITCH_THRESHOLD_30D

    # Format calibration dict for all deciles
    decile_calib = {}
    for d in range(1, 11):
        dn = deciles_data[d]["n"]
        dh = deciles_data[d]["hits"]
        dsum = deciles_data[d]["sum_probs"]
        decile_calib[str(d)] = {
            "n": dn,
            "hits": dh,
            "observed_rate": round(dh / dn, 4) if dn > 0 else 0.0,
            "expected_rate": round(dsum / dn, 4) if dn > 0 else 0.0,
        }

    # Check combined deciles 7-10 early so we have them precomputed
    n_top = sum(deciles_data[d]["n"] for d in range(7, 11))
    hits_top = sum(deciles_data[d]["hits"] for d in range(7, 11))
    sum_probs_top = sum(deciles_data[d]["sum_probs"] for d in range(7, 11))
    obs_top = hits_top / n_top if n_top > 0 else 0.0
    exp_top = sum_probs_top / n_top if n_top > 0 else 0.0

    # Dynamic status & kill switch determination:
    # 1. If D10 has enough samples (>=10), use it (legacy/standard behavior)
    # 2. If D10 is empty/low-sampled, check the highest active deciles (7 to 9) combined
    # 3. If combined top deciles (7-10) have >= 10 samples, check if observed hit rate < expected * 0.5
    kill_switch_active = False
    status = "UNDER_SAMPLED"

    if d10_n >= 10:
        kill_switch_active = d10_hr < kill_threshold
        status = "DEGRADED" if kill_switch_active else "HEALTHY"
    else:
        if n_top >= 10:
            # If hit rate is less than half of what the model expected, flag it
            kill_switch_active = obs_top < (exp_top * 0.5)
            status = "DEGRADED" if kill_switch_active else "HEALTHY"
        else:
            status = "UNDER_SAMPLED"

    return {
        "computed_date": today_str,
        "window_days": KILL_SWITCH_WINDOW_DAYS,
        "d10_n": d10_n,
        "d10_hits": d10_hits,
        "d10_hit_rate": round(d10_hr, 4),
        "d1_n": d1_n,
        "d1_hits": d1_hits,
        "d1_hit_rate": round(d1_hr, 4),
        "baseline_d10": baseline_d10,
        "baseline_d1": baseline_d1,
        "kill_switch_threshold": kill_threshold,
        "kill_switch_active": kill_switch_active,
        "status": status,
        "deciles": decile_calib,
        "top_cohort_n": n_top,
        "top_cohort_hits": hits_top,
        "top_cohort_observed_rate": round(obs_top, 4),
        "top_cohort_expected_rate": round(exp_top, 4),
    }


def _save_rolling_health(health: dict) -> None:
    """Persist the latest rolling health snapshot so /performance can show it
    without recomputing on every UI fetch."""
    _gcs_write(ROLLING_HEALTH_PATH, health)
    if health.get("kill_switch_active"):
        log.warning(
            f"  ⚠ KILL SWITCH ACTIVE: D10 hit rate {health['d10_hit_rate']:.1%} "
            f"over {KILL_SWITCH_WINDOW_DAYS}d window (threshold "
            f"{KILL_SWITCH_THRESHOLD:.0%}, baseline "
            f"{D10_CALIBRATION_HIT_RATE:.1%}). Model needs retraining."
        )
    else:
        log.info(
            f"  Rolling D10 health: {health['status']} — "
            f"D10 {health['d10_hit_rate']:.1%} (n={health['d10_n']}), "
            f"D1 {health['d1_hit_rate']:.1%} (n={health['d1_n']}), "
            f"baseline D10={D10_CALIBRATION_HIT_RATE:.1%}"
        )


# ---------------------------------------------------------------------------
# Prediction tracking — entries, opens, closes
# ---------------------------------------------------------------------------

def _append_predictions_jsonl_batch(cycle_id: str, rows: list[dict]) -> bool:
    """Append multiple prediction rows to predictions.jsonl for the cycle in a single write.
    Avoids sequential network operations to GCS.
    """
    if not rows:
        return True
    path = f"{CYCLES_PREFIX}/{cycle_id}/predictions.jsonl"
    existing = _gcs_read_text(path, "")
    new_lines = "\n".join(json.dumps(row, default=str) for row in rows)
    body = existing + ("\n" if existing and not existing.endswith("\n") else "") + new_lines + "\n"
    return _gcs_write(path, body, content_type="text/plain")


def _append_prediction_jsonl(cycle_id: str, row: dict) -> bool:
    """Append one prediction row to predictions.jsonl for the cycle (wrapper around batch helper)."""
    return _append_predictions_jsonl_batch(cycle_id, [row])


def _enrich_stocks_with_theta_eod(stocks: list[dict], today_str: str, is_60d: bool) -> None:
    """Fetch ThetaData EOD option quotes for new candidate stocks in parallel
    and inject the options_spread directly into the stock dictionaries.
    """
    try:
        from thetadata import ThetaClient
    except ImportError:
        log.warning("_enrich_stocks_with_theta_eod: ThetaData SDK not available, skipping EOD enrichment")
        return

    today = datetime.now()
    today_date = today.date()
    
    # Compute the EOD business day
    import datetime as _dt
    _eod_date = today_date
    while _eod_date.weekday() >= 5:
        _eod_date -= _dt.timedelta(days=1)
    if today.hour < 21:  # UTC
        _eod_date -= _dt.timedelta(days=1)
        while _eod_date.weekday() >= 5:
            _eod_date -= _dt.timedelta(days=1)

    symbols = [s["symbol"] for s in stocks if s.get("symbol") and (s.get("price") or 0) >= 1.0]
    if not symbols:
        return

    try:
        client = ThetaClient(
            email="carbonbridge.tech@gmail.com",
            password="Sccp1985r",
        )
    except Exception as e:
        log.error(f"_enrich_stocks_with_theta_eod: ThetaData client init failed: {e}")
        return

    from threading import Lock
    import concurrent.futures

    class ThreadSafeRateLimiter:
        def __init__(self, rps):
            self.interval = 1.0 / rps
            self.last_called = 0.0
            self.lock = Lock()

        def wait(self):
            with self.lock:
                import time as _time
                now = _time.time()
                elapsed = now - self.last_called
                sleep_time = self.interval - elapsed
                if sleep_time > 0:
                    _time.sleep(sleep_time)
                    self.last_called = _time.time()
                else:
                    self.last_called = now

    limiter = ThreadSafeRateLimiter(16)

    def fetch_greeks(sym):
        limiter.wait()
        try:
            df = client.option_history_greeks_eod(
                symbol=sym,
                expiration="*",
                start_date=_eod_date,
                end_date=_eod_date,
                strike="*",
                right="call",
            )
            return sym, df, None
        except Exception as e:
            return sym, None, e

    log.info(f"ThetaData: fetching EOD option chains for {len(symbols)} new candidates...")
    symbol_dfs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_greeks, sym) for sym in symbols]
        for fut in concurrent.futures.as_completed(futures):
            sym, df, err = fut.result()
            if df is not None and not (hasattr(df, 'is_empty') and df.is_empty()):
                symbol_dfs[sym] = df

    # Match long/short legs and inject spreads
    target_dte = 60 if is_60d else 30
    long_offset = 0.05
    short_offset = 0.20

    for s in stocks:
        sym = s["symbol"]
        spot = s.get("price") or 0
        df_greeks = symbol_dfs.get(sym)
        if df_greeks is None or spot <= 0:
            continue

        try:
            df = df_greeks.to_pandas() if hasattr(df_greeks, 'to_pandas') else df_greeks
        except Exception:
            continue

        if df.empty:
            continue

        if 'iv_error' in df.columns:
            df = df[df['iv_error'] < 0.1]
        if 'implied_vol' in df.columns:
            df = df[df['implied_vol'] > 0]
        if df.empty:
            continue

        # Expiration matching
        by_exp = {}
        for idx, row in df.iterrows():
            exp_val = row.get("expiration")
            if exp_val:
                by_exp.setdefault(str(exp_val), []).append(row)

        expirations = sorted(by_exp.keys())
        if not expirations:
            continue

        chosen_exp = None
        chosen_diff = 10**9
        for exp in expirations:
            try:
                date_str = exp.split()[0]
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                dte = (d - today_date).days
                diff = abs(dte - target_dte)
                if diff < chosen_diff:
                    chosen_diff = diff
                    chosen_exp = exp
            except Exception:
                continue

        if not chosen_exp:
            continue

        # Get rows for chosen expiration
        exp_df = df[df['expiration'] == chosen_exp]
        strike_col = 'strike' if 'strike' in exp_df.columns else None
        if not strike_col or exp_df.empty:
            continue

        long_k = spot * (1.0 + long_offset)
        short_k = spot * (1.0 + short_offset)

        # Match strikes
        long_sorted = exp_df.iloc[(exp_df[strike_col].astype(float) - long_k).abs().argsort()]
        short_sorted = exp_df.iloc[(exp_df[strike_col].astype(float) - short_k).abs().argsort()]

        if long_sorted.empty or short_sorted.empty:
            continue

        matched_long_k = float(long_sorted.iloc[0][strike_col])
        matched_short_k = float(short_sorted.iloc[0][strike_col])

        if matched_short_k <= matched_long_k:
            valid_shorts = short_sorted[short_sorted[strike_col].astype(float) > matched_long_k]
            if not valid_shorts.empty:
                matched_short_k = float(valid_shorts.iloc[0][strike_col])
                short_row = valid_shorts.iloc[:1]
                long_row = long_sorted.iloc[:1]
            else:
                valid_longs = long_sorted[long_sorted[strike_col].astype(float) < matched_short_k]
                if not valid_longs.empty:
                    matched_long_k = float(valid_longs.iloc[0][strike_col])
                    long_row = valid_longs.iloc[:1]
                    short_row = short_sorted.iloc[:1]
                else:
                    continue
        else:
            long_row = long_sorted.iloc[:1]
            short_row = short_sorted.iloc[:1]

        lr = long_row.iloc[0]
        sr = short_row.iloc[0]

        long_close = float(lr.get('close', 0) or 0)
        short_close = float(sr.get('close', 0) or 0)
        net_debit = round(long_close - short_close, 2)
        if net_debit <= 0 or net_debit >= (matched_short_k - matched_long_k):
            continue

        width = matched_short_k - matched_long_k
        max_gain = round((width - net_debit) * 100, 2)
        max_loss = round(net_debit * 100, 2)
        be_price = matched_long_k + net_debit
        be_pct = ((be_price - spot) / spot) * 100

        try:
            exp_date = datetime.strptime(chosen_exp.split()[0], "%Y-%m-%d").date()
            dte = (exp_date - today_date).days
        except Exception:
            dte = target_dte

        # Structure matches Polygon/Massive spread block
        s["options_spread"] = {
            "spot": spot,
            "long_strike": matched_long_k,
            "short_strike": matched_short_k,
            "long_mid": long_close,
            "short_mid": short_close,
            "net_debit": net_debit,
            "max_gain_per_contract": max_gain,
            "max_loss_per_contract": max_loss,
            "break_even_price": be_price,
            "break_even_move_pct": be_pct,
            "expiration": chosen_exp.split()[0],
            "dte": dte,
            "long_greeks": {g: round(float(lr[g]), 4) for g in ("delta", "gamma", "theta", "vega") if lr.get(g) is not None},
            "short_greeks": {g: round(float(sr[g]), 4) for g in ("delta", "gamma", "theta", "vega") if sr.get(g) is not None},
            "long_iv": lr.get('implied_vol'),
            "short_iv": sr.get('implied_vol'),
        }
        log.info(f"  ThetaData EOD Spread built for {sym}: {matched_long_k}/{matched_short_k}C @ {chosen_exp.split()[0]} (debit: ${net_debit:.2f})")


def _record_new_predictions(stocks: list, today_str: str, cycle_id: str,
                            region: str, is_60d_regime: bool = False) -> tuple[int, int]:
    """Process today's scan. For each stock with P20 > 0 that isn't already
    being tracked in the collecting cycle, compute the EV and store a new
    prediction (both in immutable JSONL and the cycle's open.json).

    Returns (new_count, skipped_no_ev_count).
    """
    open_path = f"{CYCLES_PREFIX}/{cycle_id}/open.json"
    open_data = _gcs_read(open_path, {"predictions": []})
    if not isinstance(open_data, dict):
        open_data = {"predictions": []}
    open_preds = open_data.get("predictions", [])

    # Symbols already tracked in the current cycle (any state) — don't re-enter
    already_in_cycle = {p["symbol"] for p in open_preds}

    # Also check predictions.jsonl for symbols already entered this cycle even
    # if they've since closed (so we don't double-enter same stock per cycle)
    raw = _gcs_read_text(f"{CYCLES_PREFIX}/{cycle_id}/predictions.jsonl", "")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            already_in_cycle.add(json.loads(line)["symbol"])
        except Exception:
            continue

    new_count = 0
    skipped_no_price = 0
    no_ev_count = 0
    new_preds = []

    # Filter candidate stocks to only those not already in the cycle and with P20 > 0
    candidate_stocks = []
    for s in stocks:
        p20 = s.get("hit_prob_60d") if is_60d_regime else s.get("hit_prob")
        if p20 is None:
            p20 = s.get("hit_prob") or 0.0
        if p20 <= P20_INCLUSION:
            continue
        sym = s.get("symbol")
        if not sym or sym in already_in_cycle:
            continue
        candidate_stocks.append(s)

    # Fetch EOD spreads from ThetaData in parallel and inject into candidate_stocks
    if candidate_stocks:
        _enrich_stocks_with_theta_eod(candidate_stocks, today_str, is_60d_regime)

    for s in candidate_stocks:
        p20 = s.get("hit_prob_60d") if is_60d_regime else s.get("hit_prob")
        if p20 is None:
            p20 = s.get("hit_prob") or 0.0
        sym = s.get("symbol")
        price = s.get("price") or 0
        if price <= 0:
            skipped_no_price += 1
            continue

        # EV is OPTIONAL.
        ev_block = calculate_spread_ev(s, is_60d=is_60d_regime)
        if ev_block is None:
            no_ev_count += 1

        # Build mode qualifications (which baskets this stock was in)
        modes = []
        if s.get("signal") in ("BUY", "STRONG_BUY"):
            modes.append("momentum")
        if s.get("fallen_angel_flag"):
            modes.append("fallen_angel")
        if s.get("signal_compounder_us") == "QUALIFIED":
            modes.append("compounder_us")
        if s.get("signal_compounder_global") == "QUALIFIED":
            modes.append("compounder_global")

        hit_window_days = 60 if is_60d_regime else HIT_WINDOW_DAYS
        fate_window_ends = (datetime.strptime(today_str, "%Y-%m-%d")
                             + timedelta(days=hit_window_days)).strftime("%Y-%m-%d")

        expected_dd = s.get("expected_dd_60d") if is_60d_regime else s.get("expected_dd_30d")
        if expected_dd is not None:
            expected_dd = round(float(expected_dd), 2)

        pred = {
            "symbol": sym,
            "entry_date": today_str,
            "cycle_id": cycle_id,
            "region": region,
            "entry_price": round(price, 4),
            "target_price": round(price * (1 + HIT_THRESHOLD_PCT / 100), 4),
            "fate_window_ends": fate_window_ends,
            "hit_window_days": hit_window_days,
            "regime": "60d" if is_60d_regime else "30d",
            "expected_dd": expected_dd,
            "p20": round(p20, 4),
            "decile": _decile(p20, is_60d=is_60d_regime),
            "signal_strength": _signal_strength(p20, is_60d=is_60d_regime),
            "mode_qualifications": modes,
            "composite": s.get("composite"),
            "sector": s.get("sector"),
            "country": s.get("country"),
            "market_cap": s.get("market_cap"),
            "ivr_at_entry": s.get("options_iv_rank"),
            "iv_at_entry": s.get("options_iv_current"),
            "skew_25d": s.get("options_skew_25d"),
            "pc_oi_ratio": s.get("options_pc_oi_ratio"),
            "outcome": "OPEN",
            "max_high_observed_pct": 0.0,
            "max_drawdown_observed_pct": 0.0,
            "current_price": round(price, 4),
            "last_updated": today_str,
            "days_observed": 0,
            "realized_return_pct": None,
            "realized_contract_pnl": None,
        }
        # Merge EV/spread block when present
        if ev_block is not None:
            pred.update(ev_block)
            # Paper-trading monetary fields (1 contract per prediction)
            pred["contract_size"] = 1
            pred["entry_net_debit"] = ev_block.get("net_debit")
            debit = ev_block.get("net_debit") or 0
            pred["entry_cost_basis"] = round(debit * 100, 2) if debit > 0 else None
            pred["current_spread_value"] = debit  # at entry, value = cost
            pred["current_contract_value"] = pred["entry_cost_basis"]
            pred["unrealized_pnl"] = 0.0
            pred["unrealized_pnl_pct"] = 0.0
            pred["spread_last_repriced"] = today_str
            pred["current_long_iv"] = ev_block.get("long_iv")
            pred["current_short_iv"] = ev_block.get("short_iv")
            pred["current_long_greeks"] = ev_block.get("long_greeks")
            pred["current_short_greeks"] = ev_block.get("short_greeks")
            # Net greeks for the spread
            lg = ev_block.get("long_greeks") or {}
            sg = ev_block.get("short_greeks") or {}
            pred["net_delta"] = round((lg.get("delta") or 0) - (sg.get("delta") or 0), 4) if lg.get("delta") is not None else None
            pred["net_theta"] = round((lg.get("theta") or 0) - (sg.get("theta") or 0), 4) if lg.get("theta") is not None else None
            pred["days_to_expiration"] = ev_block.get("dte")
        else:
            pred["contract_size"] = 1
            pred["entry_net_debit"] = None
            pred["entry_cost_basis"] = None
            pred["current_spread_value"] = None
            pred["current_contract_value"] = None
            pred["unrealized_pnl"] = None
            pred["unrealized_pnl_pct"] = None
            pred["spread_last_repriced"] = None
            pred["current_long_iv"] = None
            pred["current_short_iv"] = None
            pred["current_long_greeks"] = None
            pred["current_short_greeks"] = None
            pred["net_delta"] = None
            pred["net_theta"] = None
            pred["days_to_expiration"] = None
        new_preds.append(pred)
        already_in_cycle.add(sym)

    if new_preds:
        if _append_predictions_jsonl_batch(cycle_id, new_preds):
            open_preds.extend(new_preds)
            new_count = len(new_preds)
            _gcs_write(open_path, {"predictions": open_preds})
        else:
            log.warning(f"  Failed to append batch of {len(new_preds)} predictions")

    return new_count, no_ev_count


def _process_open_predictions(stocks: list, today_str: str,
                              state: dict) -> tuple[int, int]:
    """For every cycle with active predictions (collecting OR resolving), update
    each open prediction with today's price; mark HIT/EXPIRED as appropriate.

    Returns (closed_count, still_open_count).
    """
    # Build lookup: symbol → current price for fast access
    price_lookup = {s["symbol"]: s.get("price") or 0 for s in stocks if s.get("symbol")}

    cycles_to_process = []
    if state["collecting_cycle_id"]:
        cycles_to_process.append(state["collecting_cycle_id"])
    cycles_to_process.extend(state["resolving_cycle_ids"])

    closed_total = 0
    open_total = 0

    for cycle_id in cycles_to_process:
        open_path = f"{CYCLES_PREFIX}/{cycle_id}/open.json"
        open_data = _gcs_read(open_path, {"predictions": []})
        if not isinstance(open_data, dict):
            continue
        preds = open_data.get("predictions", [])
        if not preds:
            continue

        updated = []
        newly_closed = []
        for p in preds:
            sym = p["symbol"]
            entry_price = p["entry_price"]
            current_price = price_lookup.get(sym, p.get("current_price", entry_price))

            # Daily return from entry
            gain_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

            # Track peak run-up since entry (max_high)
            if gain_pct > p.get("max_high_observed_pct", 0):
                p["max_high_observed_pct"] = round(gain_pct, 4)
            # Track deepest underwater since entry (max_drawdown — most-negative
            # daily return observed). Stored as a negative percent so the field
            # is interpretable directly: -15.0 means stock touched -15% from entry.
            if gain_pct < p.get("max_drawdown_observed_pct", 0):
                p["max_drawdown_observed_pct"] = round(gain_pct, 4)

            days_in = (datetime.strptime(today_str, "%Y-%m-%d")
                       - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days
            p["days_observed"] = days_in
            p["current_price"] = round(current_price, 4)
            p["last_updated"] = today_str

            # Update DTE countdown if spread has an expiration
            exp = p.get("expiration")
            if exp:
                try:
                    exp_date = datetime.strptime(exp, "%Y-%m-%d")
                    p["days_to_expiration"] = max(0, (exp_date - datetime.strptime(today_str, "%Y-%m-%d")).days)
                except Exception:
                    pass

            # Closure: HIT if max-high ever touched +20%, else EXPIRED after window
            hit = p["max_high_observed_pct"] >= HIT_THRESHOLD_PCT
            expired = days_in >= p.get("hit_window_days", HIT_WINDOW_DAYS)

            if hit:
                p["outcome"] = "HIT"
                p["realized_return_pct"] = round(p["max_high_observed_pct"], 4)
                p["realized_contract_pnl"] = p.get("max_gain_per_contract", 0)
                p["resolution_date"] = today_str
                # Options P&L at resolution
                cost_basis = p.get("entry_cost_basis") or 0
                if cost_basis > 0:
                    p["options_outcome"] = "PROFIT"
                    p["options_realized_pnl"] = round(
                        p.get("max_gain_per_contract", 0), 2)
                newly_closed.append(p)
                closed_total += 1
                continue
            if expired:
                p["outcome"] = "EXPIRED"
                p["realized_return_pct"] = round(gain_pct, 4)
                # Spread payoff at expiration: full width payout if above short,
                # linear in (price − long_strike) between strikes, 0 below long.
                final_payoff = _spread_final_payoff(p, current_price)
                cost_basis = p.get("entry_cost_basis") or 0
                p["realized_contract_pnl"] = round(
                    final_payoff - (p.get("max_loss_per_contract", 0) or 0), 2)
                # Options P&L at resolution
                if cost_basis > 0:
                    pnl = round(final_payoff - cost_basis, 2)
                    p["options_outcome"] = "PROFIT" if pnl > 0 else "LOSS"
                    p["options_realized_pnl"] = pnl
                p["resolution_date"] = today_str
                newly_closed.append(p)
                closed_total += 1
                continue

            # Still open
            updated.append(p)
            open_total += 1

        if newly_closed:
            _append_predictions_jsonl_batch(cycle_id, newly_closed)
        _gcs_write(open_path, {"predictions": updated})

    return closed_total, open_total


def _spread_final_payoff(pred: dict, final_price: float) -> float:
    """Bull call spread final payoff per contract at expiration."""
    long_k = pred.get("long_strike", 0)
    short_k = pred.get("short_strike", 0)
    if final_price <= long_k:
        return 0.0
    if final_price >= short_k:
        return (short_k - long_k) * 100
    return (final_price - long_k) * 100


# ---------------------------------------------------------------------------
# Stock history (unchanged from v7.2)
# ---------------------------------------------------------------------------

def _update_stock_history(stocks: list, today_str: str):
    """Append today's (date, price, composite) to per-symbol history files.
    One file per symbol. Limited to stocks with composite > 0 and price > 0,
    coverage >= 6 (to avoid noise from half-evaluated scans).
    """
    cutoff_date = (datetime.strptime(today_str, "%Y-%m-%d")
                   - timedelta(days=STOCK_HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")

    written = 0
    for s in stocks:
        sym = s["symbol"]
        price = s.get("price", 0) or 0
        composite = s.get("composite", 0) or 0
        comp_fa = s.get("composite_fallen_angel", 0) or 0
        comp_cus = s.get("compounder_score_us") or 0
        comp_cgl = s.get("compounder_score_global") or 0
        sm_score = s.get("smart_money_score") or 0
        
        # Require at least a valid momentum composite or valid compounder score
        if price <= 0 or (composite <= 0 and comp_cus <= 0 and comp_cgl <= 0):
            continue

        path = f"{STOCK_HISTORY_PREFIX}/{sym}.json"
        history = _gcs_read(path, [])
        if not isinstance(history, list):
            history = []

        today_idx = next((i for i, row in enumerate(history)
                          if isinstance(row, list) and len(row) >= 1 and row[0] == today_str), -1)
        new_row = [
            today_str, 
            round(price, 4), 
            round(composite, 4),
            round(comp_fa, 4),
            round(comp_cus, 4),
            round(comp_cgl, 4),
            round(sm_score, 4)
        ]
        if today_idx >= 0:
            history[today_idx] = new_row
        else:
            history.append(new_row)

        history = [row for row in history
                   if isinstance(row, list) and len(row) >= 1 and row[0] >= cutoff_date]

        if _gcs_write(path, history):
            written += 1

    log.info(f"  Stock history: {written} symbols updated")


# ---------------------------------------------------------------------------
# Contract repricing — daily mark-to-market via ThetaData API
# ---------------------------------------------------------------------------

def reprice_open_contracts():
    """Reprice all open spread contracts using ThetaData EOD greeks.

    Called daily by monitor_prices.py after market close. For each open
    prediction with spread data (long_strike, short_strike, expiration),
    fetches EOD greeks from ThetaData and updates:
      - current_spread_value, current_contract_value
      - unrealized_pnl, unrealized_pnl_pct
      - current_long_iv, current_short_iv, current_ivr
      - current_long_greeks, current_short_greeks
      - net_delta, net_theta
      - days_to_expiration
    """
    try:
        from thetadata import ThetaClient
    except ImportError:
        log.warning("reprice_open_contracts: thetadata SDK not available, skipping")
        return {"repriced": 0, "skipped": 0, "expired_settled": 0}

    state = _load_cycle_state()
    if not state:
        return {"repriced": 0, "skipped": 0, "expired_settled": 0}

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_date = today.date()

    # ThetaData EOD data is only available after market close (~16:30 ET).
    # Use the last business day that has published EOD data.
    import datetime as _dt
    _eod_date = today_date
    # If it's a weekend, roll back to Friday
    while _eod_date.weekday() >= 5:  # 5=Sat, 6=Sun
        _eod_date -= _dt.timedelta(days=1)
    # If market hasn't closed yet (before 21:00 UTC / 17:00 ET), use previous business day
    if today.hour < 21:  # Cloud Run runs in UTC
        _eod_date -= _dt.timedelta(days=1)
        while _eod_date.weekday() >= 5:
            _eod_date -= _dt.timedelta(days=1)
    log.info(f"reprice: using EOD date {_eod_date} for ThetaData")

    # Load 52-week IV ranks from the latest scans in GCS
    iv_ranks = {}
    for region in ("global", "nasdaq", "sp500"):
        try:
            scan_data = _gcs_read(f"scans/latest_{region}.json", {})
            if scan_data:
                stocks_list = scan_data.get("stocks", [])
                for st in stocks_list:
                    s_sym = st.get("symbol")
                    s_ivr = st.get("options_iv_rank")
                    if s_sym and s_ivr is not None:
                        iv_ranks[s_sym.upper()] = s_ivr
        except Exception as e:
            log.warning(f"reprice: failed to read scans/latest_{region}.json for IVR: {e}")

    cycles_to_process = []
    if state.get("collecting_cycle_id"):
        cycles_to_process.append(state["collecting_cycle_id"])
    cycles_to_process.extend(state.get("resolving_cycle_ids", []))

    # Gather all predictions that need repricing, grouped by symbol
    # to minimize API calls (one call per symbol, not per contract)
    symbol_preds: dict[str, list[tuple[str, dict]]] = {}  # {symbol: [(cycle_path, pred), ...]}
    expired_preds: list[tuple[str, dict]] = []  # [(cycle_path, pred), ...]
    loaded_cycles: dict[str, dict] = {}  # {path: open_data}

    for cycle_id in cycles_to_process:
        open_path = f"{CYCLES_PREFIX}/{cycle_id}/open.json"
        open_data = _gcs_read(open_path, {"predictions": []})
        if not isinstance(open_data, dict):
            continue
        loaded_cycles[open_path] = open_data
        preds = open_data.get("predictions", [])
        for p in preds:
            long_k = p.get("long_strike")
            short_k = p.get("short_strike")
            exp = p.get("expiration")
            if not all([long_k, short_k, exp]):
                continue

            try:
                exp_date = datetime.strptime(exp, "%Y-%m-%d")
                dte = (exp_date - today).days
            except Exception:
                dte = -1

            if dte < 0:
                expired_preds.append((open_path, p))
            else:
                sym = p["symbol"]
                symbol_preds.setdefault(sym, []).append((open_path, p))

    repriced_total = 0
    skipped_total = 0
    expired_settled = 0

    # Handle expired contracts first (no API calls needed)
    paths_modified = set()
    for open_path, p in expired_preds:
        current_price = p.get("current_price", 0)
        final_payoff = _spread_final_payoff(p, current_price)
        cost_basis = p.get("entry_cost_basis") or 0
        p["current_spread_value"] = 0.0
        p["current_contract_value"] = round(final_payoff, 2)
        p["unrealized_pnl"] = round(final_payoff - cost_basis, 2)
        p["unrealized_pnl_pct"] = round(
            ((final_payoff - cost_basis) / cost_basis) * 100, 2
        ) if cost_basis > 0 else 0.0
        p["days_to_expiration"] = 0
        p["spread_last_repriced"] = today_str
        p["options_outcome"] = "PROFIT" if final_payoff > cost_basis else "LOSS"
        p["options_realized_pnl"] = p["unrealized_pnl"]
        expired_settled += 1
        paths_modified.add(open_path)

    # Reprice live contracts via ThetaData (one API call per symbol)
    if symbol_preds:
        try:
            client = ThetaClient(
                email="carbonbridge.tech@gmail.com",
                password="Sccp1985r",
            )
        except Exception as e:
            log.error(f"reprice: ThetaData client init failed: {e}")
            # Write back any expired changes we already made
            _flush_modified_cycles(loaded_cycles, paths_modified)
            return {"repriced": 0, "skipped": len(symbol_preds),
                    "expired_settled": expired_settled}

        from threading import Lock
        import concurrent.futures

        class ThreadSafeRateLimiter:
            def __init__(self, rps):
                self.interval = 1.0 / rps
                self.last_called = 0.0
                self.lock = Lock()

            def wait(self):
                with self.lock:
                    import time as _time
                    now = _time.time()
                    elapsed = now - self.last_called
                    sleep_time = self.interval - elapsed
                    if sleep_time > 0:
                        _time.sleep(sleep_time)
                        self.last_called = _time.time()
                    else:
                        self.last_called = now

        limiter = ThreadSafeRateLimiter(16)

        def fetch_greeks_for_symbol(sym):
            limiter.wait()
            try:
                greeks_df = client.option_history_greeks_eod(
                    symbol=sym,
                    expiration="*",
                    start_date=_eod_date,
                    end_date=_eod_date,
                    strike="*",
                    right="call",  # Bull call spread: both legs are calls
                )
                return sym, greeks_df, None
            except Exception as e:
                return sym, None, e

        log.info(f"reprice: fetching Greeks for {len(symbol_preds)} symbols using ThreadPoolExecutor...")
        symbol_dfs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_greeks_for_symbol, sym) for sym in symbol_preds.keys()]
            for fut in concurrent.futures.as_completed(futures):
                sym, greeks_df, err = fut.result()
                if err is not None:
                    err_str = str(err)
                    if "No data" in err_str or "NOT_FOUND" in err_str:
                        log.debug(f"reprice {sym}: no EOD data for {_eod_date}")
                    else:
                        log.warning(f"reprice {sym}: ThetaData fetch failed: {err}")
                symbol_dfs[sym] = greeks_df

        for sym, pred_list in symbol_preds.items():
            greeks_df = symbol_dfs.get(sym)
            if greeks_df is None or (hasattr(greeks_df, 'is_empty') and greeks_df.is_empty()):
                skipped_total += len(pred_list)
                continue

            # Convert to pandas for easier manipulation
            try:
                df = greeks_df.to_pandas() if hasattr(greeks_df, 'to_pandas') else greeks_df
            except Exception:
                skipped_total += len(pred_list)
                continue

            if df.empty:
                skipped_total += len(pred_list)
                continue

            # Filter out garbage IV
            if 'iv_error' in df.columns:
                df = df[(df['iv_error'] < 0.1)]
            if 'implied_vol' in df.columns:
                df = df[df['implied_vol'] > 0]

            for open_path, p in pred_list:
                long_k = float(p["long_strike"])
                short_k = float(p["short_strike"])
                exp = p["expiration"]

                try:
                    exp_date = datetime.strptime(exp, "%Y-%m-%d")
                    dte = (exp_date - today).days
                except Exception:
                    dte = 0

                # Find matching contracts by strike and expiration
                # ThetaData stores strike as integer (cents) or float
                # and expiration as datetime.date
                exp_filter = df.copy()
                if 'expiration' in exp_filter.columns and not exp_filter.empty:
                    import pandas as pd
                    def _to_date(val):
                        if isinstance(val, str):
                            return datetime.strptime(val.split()[0], "%Y-%m-%d").date()
                        elif hasattr(val, 'date'):
                            return val.date()
                        elif hasattr(val, 'strftime'):
                            return datetime.strptime(val.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
                        else:
                            try:
                                return pd.to_datetime(val).date()
                            except Exception:
                                return None

                    target_date_obj = datetime.strptime(exp, "%Y-%m-%d").date()
                    unique_exps = exp_filter['expiration'].dropna().unique()
                    
                    best_exp_val = None
                    min_diff = 10**9
                    for ue in unique_exps:
                        ue_date = _to_date(ue)
                        if ue_date:
                            diff = abs((ue_date - target_date_obj).days)
                            if diff < min_diff:
                                min_diff = diff
                                best_exp_val = ue
                    
                    if best_exp_val is not None:
                        exp_filter = exp_filter[exp_filter['expiration'] == best_exp_val]
                        matched_date = _to_date(best_exp_val)
                        if matched_date:
                            dte = max(0, (matched_date - today_date).days)

                if exp_filter.empty:
                    skipped_total += 1
                    continue

                # Find long and short strike rows
                strike_col = 'strike' if 'strike' in exp_filter.columns else None
                if not strike_col:
                    skipped_total += 1
                    continue

                long_sorted = exp_filter.iloc[
                    (exp_filter[strike_col].astype(float) - long_k).abs().argsort()
                ]
                short_sorted = exp_filter.iloc[
                    (exp_filter[strike_col].astype(float) - short_k).abs().argsort()
                ]

                if long_sorted.empty or short_sorted.empty:
                    skipped_total += 1
                    continue

                matched_long_k = float(long_sorted.iloc[0][strike_col])
                matched_short_k = float(short_sorted.iloc[0][strike_col])

                if matched_short_k <= matched_long_k:
                    valid_shorts = short_sorted[short_sorted[strike_col].astype(float) > matched_long_k]
                    if not valid_shorts.empty:
                        matched_short_k = float(valid_shorts.iloc[0][strike_col])
                        short_row = valid_shorts.iloc[:1]
                        long_row = long_sorted.iloc[:1]
                    else:
                        valid_longs = long_sorted[long_sorted[strike_col].astype(float) < matched_short_k]
                        if not valid_longs.empty:
                            matched_long_k = float(valid_longs.iloc[0][strike_col])
                            long_row = valid_longs.iloc[:1]
                            short_row = short_sorted.iloc[:1]
                        else:
                            skipped_total += 1
                            continue
                else:
                    long_row = long_sorted.iloc[:1]
                    short_row = short_sorted.iloc[:1]

                # Update strikes in prediction dictionary to lock them in
                p["long_strike"] = matched_long_k
                p["short_strike"] = matched_short_k

                lr = long_row.iloc[0]
                sr = short_row.iloc[0]

                # Extract close prices for mark-to-market
                long_close = float(lr.get('close', 0) or 0)
                short_close = float(sr.get('close', 0) or 0)
                spread_value = round(long_close - short_close, 4)
                contract_value = round(spread_value * 100, 2)
                cost_basis = p.get("entry_cost_basis") or 0

                # Update mark-to-market
                p["current_spread_value"] = spread_value
                p["current_contract_value"] = contract_value
                p["unrealized_pnl"] = round(contract_value - cost_basis, 2)
                p["unrealized_pnl_pct"] = round(
                    ((contract_value - cost_basis) / cost_basis) * 100, 2
                ) if cost_basis > 0 else 0.0
                p["days_to_expiration"] = dte
                p["spread_last_repriced"] = today_str

                # Update IV
                long_iv = lr.get('implied_vol')
                short_iv = sr.get('implied_vol')
                if long_iv is not None and float(long_iv) > 0:
                    p["current_long_iv"] = round(float(long_iv), 4)
                if short_iv is not None and float(short_iv) > 0:
                    p["current_short_iv"] = round(float(short_iv), 4)

                # Update IVR: use latest 52-week IV rank from daily scan if available,
                # otherwise fall back to current vs entry IV ratio.
                latest_ivr = iv_ranks.get(p["symbol"].upper())
                if latest_ivr is not None:
                    p["current_ivr"] = round(float(latest_ivr), 1)
                else:
                    entry_iv = p.get("iv_at_entry") or p.get("long_iv")
                    current_iv = p.get("current_long_iv")
                    if entry_iv and current_iv and entry_iv > 0:
                        p["current_ivr"] = round((current_iv / entry_iv) * 100, 1)

                # Update greeks
                for prefix, row in [("current_long_greeks", lr),
                                     ("current_short_greeks", sr)]:
                    greeks = {}
                    for g in ("delta", "gamma", "theta", "vega"):
                        val = row.get(g)
                        if val is not None:
                            greeks[g] = round(float(val), 4)
                    if greeks:
                        p[prefix] = greeks

                # Net greeks
                lg = p.get("current_long_greeks") or {}
                sg = p.get("current_short_greeks") or {}
                if lg.get("delta") is not None and sg.get("delta") is not None:
                    p["net_delta"] = round(lg["delta"] - sg["delta"], 4)
                if lg.get("theta") is not None and sg.get("theta") is not None:
                    p["net_theta"] = round(lg["theta"] - sg["theta"], 4)

                repriced_total += 1
                paths_modified.add(open_path)

    # Flush all modified cycle files back to GCS
    _flush_modified_cycles(loaded_cycles, paths_modified)

    log.info(f"reprice_open_contracts: repriced={repriced_total}, "
             f"skipped={skipped_total}, expired_settled={expired_settled}")
    return {
        "repriced": repriced_total,
        "skipped": skipped_total,
        "expired_settled": expired_settled,
    }


def _flush_modified_cycles(loaded_cycles: dict[str, dict], paths_modified: set) -> None:
    """Write back any cycle open.json files that were modified in-memory."""
    for path in paths_modified:
        if path in loaded_cycles:
            _gcs_write(path, loaded_cycles[path])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def update_from_scan(stocks: list, region: str, scan_date: str = None):
    """Update all tracking from a completed scan.

    Args:
        stocks: list of stock dicts as written to latest_{region}.json
        region: "sp500" | "global" | etc. (informational only on prediction row)
        scan_date: YYYY-MM-DD. Defaults to today.
    """
    if not stocks:
        log.info("signal_tracker: no stocks, skipping update")
        return

    today_str = scan_date or datetime.now().strftime("%Y-%m-%d")

    # Cycle lifecycle (open new / advance / archive)
    try:
        state = _load_cycle_state()
        state = _advance_cycles_if_needed(state, today_str)
        _save_cycle_state(state)
        log.info(f"  Cycle state: collecting={state['collecting_cycle_id']}, "
                 f"resolving={state['resolving_cycle_ids']}, "
                 f"archived={len(state['archived_cycle_ids'])}")
    except Exception as e:
        log.error(f"signal_tracker cycle advance failed: {e}", exc_info=True)
        return  # don't proceed without a valid cycle state

    # Detect 60-day model regime
    is_60d_regime = any((s.get("hit_prob_60d") or 0.0) > 0.0 for s in stocks)

    # New predictions enter the current collecting cycle. We track every stock
    # with hit_prob > 0 (the enriched ~30-50 per scan, all deciles) so we can
    # compute the full decile distribution and validate calibration.
    try:
        new_count, no_ev_count = _record_new_predictions(
            stocks, today_str, state["collecting_cycle_id"], region, is_60d_regime)
        log.info(f"  Predictions (hit_prob>0): +{new_count} new "
                 f"({no_ev_count} without spread EV — price/IV missing)")
    except Exception as e:
        log.error(f"signal_tracker record predictions failed: {e}", exc_info=True)

    # Update all open predictions (collecting + resolving cycles)
    try:
        closed, open_n = _process_open_predictions(stocks, today_str, state)
        log.info(f"  Predictions update: {closed} closed today, {open_n} still open")
    except Exception as e:
        log.error(f"signal_tracker process open failed: {e}", exc_info=True)

    # Try to archive any RESOLVING cycles whose predictions are all closed
    try:
        state = _attempt_archive_resolving_cycles(state, today_str)
        _save_cycle_state(state)
    except Exception as e:
        log.error(f"signal_tracker archive resolving failed: {e}", exc_info=True)

    # Rolling 90-day D10 health check + kill-switch alerting. Runs every scan
    # so the dashboard can show live calibration status.
    try:
        health = _compute_rolling_d10_health(state, today_str)
        _save_rolling_health(health)
    except Exception as e:
        log.error(f"signal_tracker rolling health failed: {e}", exc_info=True)

    # Stock history (unchanged)
    try:
        _update_stock_history(stocks, today_str)
    except Exception as e:
        log.error(f"stock_history update failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Reader helpers (used by run_server.py HTTP endpoints)
# ---------------------------------------------------------------------------

def read_cycle_state() -> dict:
    """Pointer + lists for /performance/cycles."""
    return _load_cycle_state()


def read_rolling_health() -> dict:
    """Latest 90-day D10 hit rate + kill-switch flag for the dashboard."""
    default = {
        "computed_date": None,
        "window_days": KILL_SWITCH_WINDOW_DAYS,
        "d10_n": 0, "d10_hits": 0, "d10_hit_rate": 0.0,
        "d1_n": 0,  "d1_hits": 0,  "d1_hit_rate": 0.0,
        "baseline_d10": D10_CALIBRATION_HIT_RATE,
        "baseline_d1": D1_CALIBRATION_HIT_RATE,
        "kill_switch_threshold": KILL_SWITCH_THRESHOLD,
        "kill_switch_active": False,
        "status": "NOT_YET_COMPUTED",
    }
    data = _gcs_read(ROLLING_HEALTH_PATH, default)
    return data if isinstance(data, dict) else default


def read_cycle_open(cycle_id: str) -> dict:
    """Return active open.json for a cycle (collecting or resolving)."""
    data = _gcs_read(f"{CYCLES_PREFIX}/{cycle_id}/open.json", {"predictions": []})
    return data if isinstance(data, dict) else {"predictions": []}


def read_cycle_archived(cycle_id: str) -> Optional[dict]:
    """Return archived.json for a fully-resolved cycle, or None if not yet."""
    data = _gcs_read(f"{CYCLES_PREFIX}/{cycle_id}/archived.json", None)
    return data if isinstance(data, dict) else None


def read_cycle_predictions_jsonl(cycle_id: str) -> list:
    """Return parsed list of all rows from predictions.jsonl. Each prediction
    may appear multiple times (entry row, plus a close row when resolved)."""
    raw = _gcs_read_text(f"{CYCLES_PREFIX}/{cycle_id}/predictions.jsonl", "")
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def read_stock_history(symbol: str) -> list:
    """Return [[date, price, composite], ...] for /stock/{SYMBOL}/history."""
    data = _gcs_read(f"{STOCK_HISTORY_PREFIX}/{symbol.upper()}.json", [])
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Legacy reader helpers — map P20 cycle data to the shapes expected by
# the Signal Performance and Legacy Hit Rate frontend tabs.
# These were removed during the v1.2 rewrite but run_server.py still
# imports them. Rather than maintaining separate GCS files, we derive
# the old data shapes from the unified P20 prediction system.
# ---------------------------------------------------------------------------

_SIGNAL_MAP = {
    "STRONG": "STRONG BUY",
    "MODERATE": "BUY",
    "MILD": "WATCH",
    "WEAK": "HOLD",
}


def _pred_to_signal_open(p: dict) -> dict:
    """Convert a P20 prediction to SignalTrackOpen shape."""
    ep = p.get("entry_price", 0) or 0
    cp = p.get("current_price", ep) or ep
    sig = _SIGNAL_MAP.get(p.get("signal_strength", ""), "HOLD")
    max_high_pct = p.get("max_high_observed_pct", 0) or 0
    max_dd_pct = p.get("max_drawdown_observed_pct", 0) or 0
    return {
        "symbol": p.get("symbol", ""),
        "region": p.get("region", "global"),
        "entry_date": p.get("entry_date", ""),
        "entry_price": ep,
        "entry_composite": p.get("composite", 0) or 0,
        "entry_signal": sig,
        "sector": p.get("sector"),
        "industry": None,
        "classification": None,
        "last_price": cp,
        "last_composite": p.get("composite", 0) or 0,
        "last_signal": sig,
        "last_updated": p.get("last_updated", ""),
        "max_price": round(ep * (1 + max_high_pct / 100), 4) if ep > 0 else 0,
        "min_price": round(ep * (1 + max_dd_pct / 100), 4) if ep > 0 else 0,
        "days_held": p.get("days_observed", 0),
    }


def _pred_to_signal_closed(p: dict) -> dict:
    """Convert a resolved P20 prediction to SignalTrackClosed shape."""
    base = _pred_to_signal_open(p)
    cp = p.get("current_price", base["entry_price"])
    pnl = p.get("realized_return_pct", 0) or 0
    max_high = p.get("max_high_observed_pct", 0) or 0
    max_dd = p.get("max_drawdown_observed_pct", 0) or 0
    base.update({
        "exit_date": p.get("resolution_date", p.get("last_updated", "")),
        "exit_price": cp,
        "exit_composite": p.get("composite", 0) or 0,
        "exit_signal": "SELL",
        "realized_pnl_pct": round(pnl, 2),
        "max_gain_pct": round(max_high, 2),
        "max_dd_pct": round(max_dd, 2),
    })
    return base


def _pred_to_hitrate_open(p: dict) -> dict:
    """Convert a P20 prediction to HitRateOpen shape."""
    ep = p.get("entry_price", 0) or 0
    cp = p.get("current_price", ep) or ep
    p20 = p.get("p20", 0) or 0
    p10_val = min(p20 * P10_MULT, 0.65)
    max_high_pct = p.get("max_high_observed_pct", 0) or 0
    sig = _SIGNAL_MAP.get(p.get("signal_strength", ""), "HOLD")
    # Determine hit_date: if max run-up touched +10%, the hit was observed
    hit_date = None
    if max_high_pct >= 10.0 and p.get("resolution_date"):
        hit_date = p["resolution_date"]
    return {
        "symbol": p.get("symbol", ""),
        "region": p.get("region", "global"),
        "entry_date": p.get("entry_date", ""),
        "entry_price": ep,
        "entry_composite": p.get("composite", 0) or 0,
        "entry_signal": sig,
        "entry_p10": round(p10_val, 4),
        "sector": p.get("sector"),
        "classification": None,
        "last_price": cp,
        "last_updated": p.get("last_updated", ""),
        "max_price": round(ep * (1 + max_high_pct / 100), 4) if ep > 0 else 0,
        "days_elapsed": p.get("days_observed", 0),
        "hit_date": hit_date,
    }


def _pred_to_hitrate_closed(p: dict) -> dict:
    """Convert a resolved P20 prediction to HitRateClosed shape."""
    base = _pred_to_hitrate_open(p)
    max_high = p.get("max_high_observed_pct", 0) or 0
    hit = max_high >= 10.0
    base.update({
        "exit_date": p.get("resolution_date", p.get("last_updated", "")),
        "exit_reason": "hit_10pct" if hit else "window_closed",
        "hit": hit,
        "max_gain_pct": round(max_high, 2),
    })
    return base


def _gather_predictions_from_cycles(state: dict, include_archived: int = 6):
    """Gather open and closed predictions from all known cycles.

    Returns (open_list, closed_list) where open_list contains OPEN predictions
    from collecting + resolving cycles, and closed_list contains HIT/EXPIRED
    predictions from resolving + archived cycles.
    """
    open_list = []
    closed_list = []
    seen_closed = set()  # (symbol, entry_date) dedup for closed

    # Active cycles: collecting + resolving → open predictions
    active_ids = []
    if state.get("collecting_cycle_id"):
        active_ids.append(state["collecting_cycle_id"])
    active_ids.extend(state.get("resolving_cycle_ids", []))

    for cid in active_ids:
        open_data = _gcs_read(f"{CYCLES_PREFIX}/{cid}/open.json",
                              {"predictions": []})
        for p in (open_data or {}).get("predictions", []):
            open_list.append(p)

    # Closed predictions from resolving cycles (via JSONL — deduplicated to
    # latest state per symbol+entry_date)
    for cid in active_ids:
        raw = _gcs_read_text(f"{CYCLES_PREFIX}/{cid}/predictions.jsonl", "")
        latest = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            key = (row.get("symbol"), row.get("entry_date"))
            existing = latest.get(key)
            if existing is None:
                latest[key] = row
            elif existing.get("outcome") == "OPEN" and row.get("outcome") != "OPEN":
                latest[key] = row
        for key, row in latest.items():
            if row.get("outcome") in ("HIT", "EXPIRED") and key not in seen_closed:
                seen_closed.add(key)
                closed_list.append(row)

    # Archived cycles — fully resolved, use archived.json's predictions list
    for cid in state.get("archived_cycle_ids", [])[-include_archived:]:
        arch = _gcs_read(f"{CYCLES_PREFIX}/{cid}/archived.json", None)
        if not arch or not isinstance(arch, dict):
            continue
        for p in arch.get("predictions", []):
            key = (p.get("symbol"), p.get("entry_date"))
            if key not in seen_closed:
                seen_closed.add(key)
                closed_list.append(p)

    return open_list, closed_list


def read_signal_tracks() -> dict:
    """Derive legacy signal-track data from P20 cycle predictions.

    Returns {open: SignalTrackOpen[], closed: SignalTrackClosed[]} matching
    the shape expected by the Signal Performance frontend tab.
    """
    state = _load_cycle_state()
    if not state or not state.get("collecting_cycle_id"):
        return {"open": [], "closed": []}

    open_preds, closed_preds = _gather_predictions_from_cycles(state)

    return {
        "open": [_pred_to_signal_open(p) for p in open_preds],
        "closed": [_pred_to_signal_closed(p) for p in closed_preds],
    }


def read_hitrate_tracks() -> dict:
    """Derive legacy hit-rate data from P20 cycle predictions.

    Returns {open: HitRateOpen[], closed: HitRateClosed[]} matching
    the shape expected by the Legacy Hit Rate frontend tab.
    """
    state = _load_cycle_state()
    if not state or not state.get("collecting_cycle_id"):
        return {"open": [], "closed": []}

    open_preds, closed_preds = _gather_predictions_from_cycles(state)

    return {
        "open": [_pred_to_hitrate_open(p) for p in open_preds],
        "closed": [_pred_to_hitrate_closed(p) for p in closed_preds],
    }
