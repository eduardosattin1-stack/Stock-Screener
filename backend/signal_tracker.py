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
HIT_WINDOW_DAYS     = 28       # 4 weeks ≈ 20 trading days (legacy default)
CYCLE_LENGTH_DAYS   = 30       # New cycle every 30 calendar days
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
SYNTH_SHORT_OFFSET = 0.10    # Short call strike at +10% from spot
SYNTH_DTE_DAYS     = 30

# Synthesized spread structure (60d regime)
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
            f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded_path}?alt=media",
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
            f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{encoded_path}?alt=media",
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
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": content_type},
            data=body, timeout=15,
        )
        if r.status_code in (200, 201):
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
        long_strike = _round_strike(spot)
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

    # Kill-switch fires when D10 sample is ≥10 (statistical floor) AND hit
    # rate is below threshold. Below 10 D10 samples we don't have signal yet.
    kill_switch_active = d10_n >= 10 and d10_hr < kill_threshold

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
        "status": "DEGRADED" if kill_switch_active
                  else "UNDER_SAMPLED" if d10_n < 10
                  else "HEALTHY",
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

def _append_prediction_jsonl(cycle_id: str, row: dict) -> bool:
    """Append one prediction row to predictions.jsonl for the cycle.

    GCS doesn't support native append, so we read-modify-write. The file is
    small (≤30 rows per cycle in practice given P20≥25% gate), so cost is
    negligible.
    """
    path = f"{CYCLES_PREFIX}/{cycle_id}/predictions.jsonl"
    existing = _gcs_read_text(path, "")
    new_line = json.dumps(row, default=str)
    body = existing + ("\n" if existing and not existing.endswith("\n") else "") + new_line + "\n"
    return _gcs_write(path, body, content_type="text/plain")


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

    for s in stocks:
        p20 = s.get("hit_prob_60d") if is_60d_regime else s.get("hit_prob")
        if p20 is None:
            p20 = s.get("hit_prob") or 0.0
        # Gate: any enriched stock (hit_prob > 0).
        if p20 <= P20_INCLUSION:
            continue
        sym = s.get("symbol")
        if not sym or sym in already_in_cycle:
            continue
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

        # Append to immutable JSONL (audit trail) and to open.json (active state)
        if _append_prediction_jsonl(cycle_id, pred):
            open_preds.append(pred)
            new_count += 1
            already_in_cycle.add(sym)
        else:
            log.warning(f"  Failed to append prediction for {sym}")

    if new_count > 0:
        _gcs_write(open_path, {"predictions": open_preds})

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

            # Closure: HIT if max-high ever touched +20%, else EXPIRED after window
            hit = p["max_high_observed_pct"] >= HIT_THRESHOLD_PCT
            expired = days_in >= p.get("hit_window_days", 28)

            if hit:
                p["outcome"] = "HIT"
                p["realized_return_pct"] = round(p["max_high_observed_pct"], 4)
                p["realized_contract_pnl"] = p.get("max_gain_per_contract", 0)
                p["resolution_date"] = today_str
                # Re-append final state to JSONL so the audit trail has the close
                _append_prediction_jsonl(cycle_id, p)
                closed_total += 1
                continue
            if expired:
                p["outcome"] = "EXPIRED"
                p["realized_return_pct"] = round(gain_pct, 4)
                # Spread payoff at expiration: full width payout if above short,
                # linear in (price − long_strike) between strikes, 0 below long.
                final_payoff = _spread_final_payoff(p, current_price)
                p["realized_contract_pnl"] = round(
                    final_payoff - (p.get("max_loss_per_contract", 0) or 0), 2)
                p["resolution_date"] = today_str
                _append_prediction_jsonl(cycle_id, p)
                closed_total += 1
                continue

            # Still open
            updated.append(p)
            open_total += 1

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
    is_60d_regime = any("hit_prob_60d" in s for s in stocks)

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
