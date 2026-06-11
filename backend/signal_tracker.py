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

class Regime:
    def __init__(self, name, pointer_path, cycles_prefix, health_path, prob_key,
                 hit_threshold_pct, hit_window_days, synth_dte_days,
                 synth_long_offset, synth_short_offset,
                 p5_mult, p10_mult, p15_mult, p5_cap, p10_cap, p15_cap,
                 d10_calib, d1_calib, kill_threshold, is_60d):
        self.name = name
        self.pointer_path = pointer_path
        self.cycles_prefix = cycles_prefix
        self.health_path = health_path
        self.prob_key = prob_key
        self.hit_threshold_pct = hit_threshold_pct
        self.hit_window_days = hit_window_days
        self.synth_dte_days = synth_dte_days
        self.synth_long_offset = synth_long_offset
        self.synth_short_offset = synth_short_offset
        self.p5_mult = p5_mult
        self.p10_mult = p10_mult
        self.p15_mult = p15_mult
        self.p5_cap = p5_cap
        self.p10_cap = p10_cap
        self.p15_cap = p15_cap
        self.d10_calib = d10_calib
        self.d1_calib = d1_calib
        self.kill_threshold = kill_threshold
        self.is_60d = is_60d
        self.cycle_length_days = synth_dte_days

REGIME_60D = Regime(
    name="60d",
    pointer_path="hit_rate_tracking/current_cycle.json",
    cycles_prefix="hit_rate_tracking/cycles",
    health_path="hit_rate_tracking/rolling_health.json",
    prob_key="hit_prob_60d",
    hit_threshold_pct=20.0,
    hit_window_days=60,
    synth_dte_days=60,
    synth_long_offset=0.05,
    synth_short_offset=0.20,
    p5_mult=2.44,
    p10_mult=1.85,
    p15_mult=1.35,
    p5_cap=0.98,
    p10_cap=0.95,
    p15_cap=0.90,
    d10_calib=0.832,
    d1_calib=0.015,
    kill_threshold=0.40,
    is_60d=True
)

REGIME_30D_P10 = Regime(
    name="30d_p10",
    pointer_path="hit_rate_tracking/current_cycle_30d.json",
    cycles_prefix="hit_rate_tracking/cycles_30d",
    health_path="hit_rate_tracking/rolling_health_30d.json",
    prob_key="hit_prob_10pct_30d",
    hit_threshold_pct=10.0,
    hit_window_days=30,
    synth_dte_days=30,
    synth_long_offset=0.025,
    synth_short_offset=0.10,  # "short leg be within 10%"
    p5_mult=3.41,
    p10_mult=2.29,
    p15_mult=1.49,
    p5_cap=0.80,
    p10_cap=0.65,
    p15_cap=0.50,
    d10_calib=0.7045,
    d1_calib=0.2924,
    kill_threshold=0.35,
    is_60d=False
)


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

def _get_option_price(row) -> float:
    close = float(row.get('close', 0) or 0)
    if close > 0:
        return close
    bid = float(row.get('bid', 0) or 0)
    ask = float(row.get('ask', 0) or 0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if bid > 0:
        return bid
    if ask > 0:
        return ask
    return 0.0


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


def calculate_spread_ev(stock: dict, is_60d: bool = False, regime: Regime = None, today_str: Optional[str] = None) -> Optional[dict]:
    """Compute the deployable options-spread EV for a P20-qualified stock.

    Mirrors TradierOptionsCard v3 exactly: uses live tradier_spread when
    present, else synthesizes a bull call spread (ATM long, short at offset)
    with debit estimated from current IV.

    Returns a dict with all spread components and EV calculation, or None if
    not computable (no price, no P20, can't construct strikes, or spot < $1).
    """
    if regime is None:
        regime = REGIME_60D if is_60d else REGIME_30D_P10
    
    p20 = stock.get(regime.prob_key)
    if p20 is None:
        p20 = stock.get("hit_prob_60d") if regime.is_60d else stock.get("hit_prob")
    if p20 is None:
        p20 = stock.get("hit_prob") or 0.0

    spot = stock.get("price") or 0
    if p20 <= 0 or spot <= 0:
        return None
    # Penny stocks have no meaningful options market and the rounding logic
    # produces degenerate strike pairs (e.g. long=$0). Skip below $1.
    if spot < 1.0:
        return None

    # Calibrated probability ladder
    p5  = min(p20 * regime.p5_mult,  regime.p5_cap)
    p10 = min(p20 * regime.p10_mult, regime.p10_cap)
    p15 = min(p20 * regime.p15_mult, regime.p15_cap)
    ladder = [(5.0, p5), (10.0, p10), (15.0, p15), (20.0, p20)]

    # Spread structure: live or synthesized
    live_sp = stock.get("options_spread")
    synth_dte = regime.synth_dte_days
    synth_long_offset = regime.synth_long_offset
    synth_short_offset = regime.synth_short_offset

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
        # Search the best EV combination of long and short strikes
        best_ev = -999999.0
        best_sp = None

        # Test candidate offsets
        for lo in [0.005 * i for i in range(16)]:  # Long offsets: 0% to 7.5% from spot
            long_strike = _round_strike(spot * (1.0 + lo))
            for so in [0.01 * i for i in range(3, 26)]:  # Short offsets: 3% to 25% from spot
                short_strike = _round_strike(spot * (1.0 + so))
                if short_strike <= long_strike:
                    continue

                width = short_strike - long_strike
                iv = stock.get("options_iv_current") or 0.30
                iv_factor = min(IV_FACTOR_MAX, max(IV_FACTOR_MIN, iv * IV_FACTOR_SCALE))
                net_debit = round(width * iv_factor * 100) / 100
                if net_debit <= 0 or net_debit >= width:
                    continue

                max_gain = (width - net_debit) * 100
                max_loss = net_debit * 100
                be_price = long_strike + net_debit
                be_pct = ((be_price - spot) / spot) * 100

                # Expiration calculation
                if today_str:
                    base_dt = datetime.strptime(today_str, "%Y-%m-%d")
                else:
                    base_dt = datetime.now()
                exp = base_dt + timedelta(days=synth_dte)
                while exp.weekday() != 4:  # Friday
                    exp += timedelta(days=1)

                sp_candidate = {
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

                # Calculate EV for this candidate
                short_pct = ((sp_candidate["short_strike"] - sp_candidate["spot"]) / sp_candidate["spot"]) * 100
                p_be = _interpolate_p(sp_candidate["break_even_move_pct"], ladder)
                p_max = _interpolate_p(short_pct, ladder)
                cand_ev = p_max * sp_candidate["max_gain_per_contract"] - (1 - p_be) * sp_candidate["max_loss_per_contract"]

                if cand_ev > best_ev:
                    best_ev = cand_ev
                    best_sp = sp_candidate

        if best_sp is None:
            return None

        sp = best_sp
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

def _decile(p20: float, is_60d: bool = False, regime: Regime = None) -> int:
    """OOS-calibrated decile thresholds."""
    if regime is None:
        regime = REGIME_60D if is_60d else REGIME_30D_P10
    if regime.is_60d:
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
        if p20 >= 0.66824: return 10
        if p20 >= 0.61036: return 9
        if p20 >= 0.53112: return 8
        if p20 >= 0.49112: return 7
        if p20 >= 0.45668: return 6
        if p20 >= 0.40472: return 5
        if p20 >= 0.39495: return 4
        if p20 >= 0.36167: return 3
        if p20 >= 0.30328: return 2
        return 1


def _signal_strength(p20: float, is_60d: bool = False, regime: Regime = None) -> str:
    if regime is None:
        regime = REGIME_60D if is_60d else REGIME_30D_P10
    if regime.is_60d:
        if p20 >= 0.55: return "STRONG"
        if p20 >= 0.40: return "MODERATE"
        if p20 >= 0.25: return "MILD"
        return "WEAK"
    else:
        if p20 >= 0.61: return "STRONG"
        if p20 >= 0.49: return "MODERATE"
        if p20 >= 0.36: return "MILD"
        return "WEAK"


# ---------------------------------------------------------------------------
# Cycle management
# ---------------------------------------------------------------------------

def _load_cycle_state(regime: Regime = REGIME_60D) -> dict:
    """Read pointer_path. Returns a freshly-initialized state if not yet
    written (first-run bootstrap)."""
    default = {
        "collecting_cycle_id": None,
        "collecting_start": None,
        "collecting_ends": None,
        "resolving_cycle_ids": [],
        "archived_cycle_ids": [],
    }
    state = _gcs_read(regime.pointer_path, default)
    if not isinstance(state, dict):
        return default
    # Defensive: backfill any missing fields from default
    for k, v in default.items():
        state.setdefault(k, v)
    return state


def _save_cycle_state(state: dict, regime: Regime = REGIME_60D) -> None:
    _gcs_write(regime.pointer_path, state)


def _open_new_cycle(state: dict, today_str: str, regime: Regime = REGIME_60D) -> dict:
    """Open a new collecting cycle starting today. Mutates and returns state."""
    new_id = today_str
    ends = (datetime.strptime(today_str, "%Y-%m-%d")
            + timedelta(days=regime.cycle_length_days)).strftime("%Y-%m-%d")
    state["collecting_cycle_id"] = new_id
    state["collecting_start"] = today_str
    state["collecting_ends"] = ends
    # Initialize empty open.json so downstream code doesn't 404
    _gcs_write(f"{regime.cycles_prefix}/{new_id}/open.json", {"predictions": []})
    log.info(f"  Cycle {new_id} ({regime.name}) opened (collects until {ends})")
    return state


def _advance_cycles_if_needed(state: dict, today_str: str, regime: Regime = REGIME_60D) -> dict:
    """Roll cycles forward when the collecting window expires.

    If today is on/after collecting_ends, the current cycle moves to RESOLVING
    and a new collecting cycle opens. Mutates and returns state.
    """
    # Bootstrap: no cycle has ever been opened.
    if state["collecting_cycle_id"] is None:
        return _open_new_cycle(state, today_str, regime)

    if today_str >= state["collecting_ends"]:
        old_id = state["collecting_cycle_id"]
        if old_id not in state["resolving_cycle_ids"]:
            state["resolving_cycle_ids"].append(old_id)
            log.info(f"  Cycle {old_id} ({regime.name}) → RESOLVING (collected for "
                     f"{regime.synth_dte_days}d, predictions still tracking)")
        _open_new_cycle(state, today_str, regime)
    return state


def _attempt_archive_resolving_cycles(state: dict, today_str: str, regime: Regime = REGIME_60D) -> dict:
    """For each cycle in RESOLVING state, if its open.json is empty, write
    archived.json with summary stats and move to archived_cycle_ids.

    Predictions in open.json get closed independently by _process_open_predictions
    every day. Once all predictions for a cycle have resolved, this archiver
    finalizes the summary.
    """
    still_resolving = []
    for cycle_id in state["resolving_cycle_ids"]:
        open_data = _gcs_read(f"{regime.cycles_prefix}/{cycle_id}/open.json",
                              {"predictions": []})
        open_preds = (open_data or {}).get("predictions", [])
        if open_preds:
            still_resolving.append(cycle_id)
            continue
        # All predictions resolved — compute summary and archive
        summary = _compute_cycle_summary(cycle_id, today_str, regime)
        if _gcs_write(f"{regime.cycles_prefix}/{cycle_id}/archived.json", summary):
            state["archived_cycle_ids"].append(cycle_id)
            stock_n = summary["by_method"]["stock"].get("n", 0)
            call_n = summary["by_method"]["long_call"].get("n", 0)
            stock_hr = summary["by_method"]["stock"].get("barrier_hit_rate", 0)
            call_hr = summary["by_method"]["long_call"].get("barrier_hit_rate", 0)
            d10_hr = summary["calibration"].get("d10_hit_rate", 0)
            log.info(f"  Cycle {cycle_id} ({regime.name}) → ARCHIVED "
                     f"(picks={summary['n_picks']}, "
                     f"stock hit={stock_hr:.1%} n={stock_n}, "
                     f"call hit={call_hr:.1%} n={call_n}, "
                     f"D10={d10_hr:.1%})")
        else:
            log.warning(f"  Cycle {cycle_id} ({regime.name}) archive write failed; will retry")
    state["resolving_cycle_ids"] = still_resolving
    return state


UNDERPOWERED_N = 20  # n < this in a single method × cycle → flag as underpowered


def _empty_method_stats() -> dict:
    return {
        "n": 0, "barrier_hit_count": 0, "stopped_count": 0, "terminal_count": 0,
        "barrier_hit_rate": 0.0, "winning_trade_rate": None,
        "mean_realized_return_pct": 0.0, "median_realized_return_pct": 0.0,
        "tail_p5_return_pct": 0.0, "tail_p95_return_pct": 0.0,
        "mean_max_runup_pct": 0.0, "mean_max_drawdown_pct": 0.0,
        "worst_drawdown_pct": 0.0, "best_runup_pct": 0.0,
        "total_cost_basis": 0.0, "total_realized_pnl_dollars": 0.0,
        "portfolio_return_pct": None,
        "underpowered": True,
        "by_decile": {}, "by_signal_strength": {},
    }


def _empty_calibration(regime: Regime) -> dict:
    base_odds = regime.d10_calib / regime.d1_calib if regime.d1_calib > 0 else 20.0
    return {
        "d10_hit_rate": 0.0, "d10_n": 0, "d1_hit_rate": 0.0, "d1_n": 0,
        "d10_baseline": regime.d10_calib, "d1_baseline": regime.d1_calib,
        "observed_odds_ratio": None,
        "baseline_odds_ratio": round(base_odds, 2),
        "kill_switch_threshold": regime.kill_threshold,
        "healthy": False,
        "by_decile": {},
        "note": "no data",
    }


def _method_stats(preds: list, regime: Regime, method: str) -> dict:
    """Aggregate trade-quality stats for one method's prediction rows within
    a single cycle. Returns the per-method block of _compute_cycle_summary.
    """
    if not preds:
        return _empty_method_stats()

    n = len(preds)
    barrier_hits = sum(1 for p in preds if p.get("outcome_tag") == "SOLD_AT_TOUCH")
    stopped = sum(1 for p in preds if p.get("outcome_tag") == "STOPPED")
    terminal = sum(1 for p in preds if p.get("outcome_tag") == "TERMINAL")

    returns = [p.get("realized_return_pct") for p in preds
               if p.get("realized_return_pct") is not None]
    winners = sum(1 for r in returns if r > 0)
    win_rate = round(winners / len(returns), 4) if returns else None

    if returns:
        mean_ret = sum(returns) / len(returns)
        sorted_ret = sorted(returns)
        median_ret = sorted_ret[len(sorted_ret) // 2]
        p5_idx = max(0, int(0.05 * (len(sorted_ret) - 1)))
        p95_idx = min(len(sorted_ret) - 1, int(0.95 * (len(sorted_ret) - 1)))
        tail_p5 = sorted_ret[p5_idx]
        tail_p95 = sorted_ret[p95_idx]
    else:
        mean_ret = median_ret = tail_p5 = tail_p95 = 0.0

    max_highs = [p.get("max_high_observed_pct", 0) for p in preds]
    max_dds = [p.get("max_drawdown_observed_pct", 0) for p in preds]
    mean_max_high = sum(max_highs) / len(max_highs) if max_highs else 0
    mean_max_dd = sum(max_dds) / len(max_dds) if max_dds else 0
    worst_dd = min(max_dds) if max_dds else 0
    best_runup = max(max_highs) if max_highs else 0

    # Decile and signal-strength bucketing — barrier-hit-based, so D10 should
    # touch the baseline rate from training (P-ladder calibration), regardless
    # of method (both arms see the same spot path).
    by_decile: dict = {}
    by_signal: dict = {}
    for p in preds:
        d = p.get("decile", 1)
        sig = p.get("signal_strength", "WEAK")
        by_decile.setdefault(d, {"n": 0, "hits": 0})
        by_decile[d]["n"] += 1
        if p.get("outcome_tag") == "SOLD_AT_TOUCH":
            by_decile[d]["hits"] += 1
        by_signal.setdefault(sig, {"n": 0, "hits": 0})
        by_signal[sig]["n"] += 1
        if p.get("outcome_tag") == "SOLD_AT_TOUCH":
            by_signal[sig]["hits"] += 1
    for d in by_decile:
        by_decile[d]["hit_rate"] = round(by_decile[d]["hits"] / by_decile[d]["n"], 4) if by_decile[d]["n"] else 0
    for sig in by_signal:
        by_signal[sig]["hit_rate"] = round(by_signal[sig]["hits"] / by_signal[sig]["n"], 4) if by_signal[sig]["n"] else 0

    # Portfolio dollar tracking — method-specific cost basis. Stock arm uses
    # entry_price × 1 share notional. Call arm uses entry_quote_ask × 100.
    if method == "long_call":
        total_cost_basis = sum((p.get("entry_quote_ask") or 0) * 100 for p in preds)
        total_realized = sum((p.get("realized_pnl_at_resolve") or 0) for p in preds
                              if p.get("realized_pnl_at_resolve") is not None)
        portfolio_return_pct = round(total_realized / total_cost_basis * 100, 4) if total_cost_basis > 0 else None
    else:
        total_cost_basis = sum((p.get("entry_price") or 0) for p in preds)
        total_realized = sum(((p.get("realized_return_pct") or 0) / 100) * (p.get("entry_price") or 0)
                              for p in preds if p.get("realized_return_pct") is not None)
        portfolio_return_pct = round(total_realized / total_cost_basis * 100, 4) if total_cost_basis > 0 else None

    return {
        "n": n,
        "barrier_hit_count": barrier_hits,
        "stopped_count": stopped,
        "terminal_count": terminal,
        "barrier_hit_rate": round(barrier_hits / n, 4),
        "winning_trade_rate": win_rate,
        "mean_realized_return_pct": round(mean_ret, 4),
        "median_realized_return_pct": round(median_ret, 4),
        "tail_p5_return_pct": round(tail_p5, 4),
        "tail_p95_return_pct": round(tail_p95, 4),
        "mean_max_runup_pct": round(mean_max_high, 4),
        "mean_max_drawdown_pct": round(mean_max_dd, 4),
        "worst_drawdown_pct": round(worst_dd, 4),
        "best_runup_pct": round(best_runup, 4),
        "total_cost_basis": round(total_cost_basis, 2),
        "total_realized_pnl_dollars": round(total_realized, 2),
        "portfolio_return_pct": portfolio_return_pct,
        "underpowered": n < UNDERPOWERED_N,
        "by_decile": by_decile,
        "by_signal_strength": by_signal,
    }


def _calibration_check_picks(pick_rows: list, regime: Regime) -> dict:
    """Compare pick-level barrier-touch hit rates against the P-ladder
    baseline. Pick-level (not row-level) dedup avoids double-counting the
    same spot event when both the stock arm and long-call arm of a pick
    touch on the same day — they reference the same physical price path.
    """
    if not pick_rows:
        return _empty_calibration(regime)

    by_decile: dict = {}
    for p in pick_rows:
        d = p.get("decile", 1)
        by_decile.setdefault(d, {"n": 0, "hits": 0})
        by_decile[d]["n"] += 1
        if p.get("outcome_tag") == "SOLD_AT_TOUCH":
            by_decile[d]["hits"] += 1
    for d in by_decile:
        by_decile[d]["hit_rate"] = round(by_decile[d]["hits"] / by_decile[d]["n"], 4) if by_decile[d]["n"] else 0

    d10 = by_decile.get(10, {})
    d1 = by_decile.get(1, {})
    d10_hr = d10.get("hit_rate", 0)
    d1_hr = d1.get("hit_rate", 0)
    odds_ratio = (d10_hr / d1_hr) if d1_hr > 0 else None

    base_d10 = regime.d10_calib
    base_d1 = regime.d1_calib
    kill = regime.kill_threshold
    base_odds = base_d10 / base_d1 if base_d1 > 0 else 20.0
    healthy = d10.get("n", 0) >= 5 and d10_hr >= kill

    return {
        "d10_hit_rate": round(d10_hr, 4),
        "d10_n": d10.get("n", 0),
        "d1_hit_rate": round(d1_hr, 4),
        "d1_n": d1.get("n", 0),
        "d10_baseline": base_d10,
        "d1_baseline": base_d1,
        "observed_odds_ratio": round(odds_ratio, 2) if odds_ratio else None,
        "baseline_odds_ratio": round(base_odds, 2),
        "kill_switch_threshold": kill,
        "healthy": healthy,
        "by_decile": by_decile,
        "note": (f"D10 must stay above kill-switch ({int(kill*100)}%) and ideally "
                 f"track the {base_d10:.1%} baseline. Sample size <5 in D10 -> unstable."),
    }


def _compute_cycle_summary(cycle_id: str, today_str: str, regime: Regime = REGIME_60D) -> dict:
    """Roll up cycle stats — method-aware. Reads the immutable
    predictions.jsonl, dedupes to latest row per (symbol, entry_date, method),
    then splits by method (stock vs long_call) for trade-quality decomposition.
    Calibration is computed once at the pick level (barrier touch is the same
    physical event for both arms — pick-level dedup is the honest unit).

    Per-method block includes the risk-surfacing fields the desktop thread
    added to the backtest (tail p5, max DD, UNDERPOWERED flag) so the same
    sanity check applies to forward live data: a method with 80% win and
    +8% mean ROI that hides a -40% tail will not pass the same eye test.
    """
    raw = _gcs_read_text(f"{regime.cycles_prefix}/{cycle_id}/predictions.jsonl", "")
    latest_by_key = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        # Method is part of the dedup key now — same symbol + entry_date
        # produces two rows (stock + long_call) per regime.
        key = (row.get("symbol"), row.get("entry_date"), row.get("method"))
        existing = latest_by_key.get(key)
        if existing is None:
            latest_by_key[key] = row
        elif existing.get("outcome") == "OPEN" and row.get("outcome") != "OPEN":
            latest_by_key[key] = row

    # Open picks get their daily Max+/Max-/days_observed updates written to the
    # cycle's open.json by _process_open_predictions, but those running updates are
    # NOT re-appended to the immutable predictions.jsonl (only resolutions are). So
    # overlay the live open.json snapshot for still-open picks — otherwise the UI
    # shows them frozen at the day-0 entry row (max_high=0, max_dd=0, days=0) until
    # they resolve. Closed picks are absent from open.json, so they keep the
    # resolved row deduped from the jsonl above.
    open_snapshot = _gcs_read(f"{regime.cycles_prefix}/{cycle_id}/open.json", {"predictions": []})
    if isinstance(open_snapshot, dict):
        for row in open_snapshot.get("predictions", []):
            okey = (row.get("symbol"), row.get("entry_date"), row.get("method"))
            latest_by_key[okey] = row

    preds = list(latest_by_key.values())

    if not preds:
        return {
            "cycle_id": cycle_id,
            "archived_date": today_str,
            "regime": regime.name,
            "total_predictions": 0,
            "n_picks": 0,
            "by_method": {"stock": _empty_method_stats(), "long_call": _empty_method_stats()},
            "calibration": _empty_calibration(regime),
            "predictions": [],
        }

    stock_preds = [p for p in preds if p.get("method") == "stock"]
    call_preds = [p for p in preds if p.get("method") == "long_call"]

    # Pick-level dedup for calibration. Either arm of the same pick records
    # the same max_high (spot path) — taking whichever resolved (or whichever
    # row exists) is fine. We pick the stock arm when present for stability.
    pick_dedup: dict = {}
    for p in preds:
        pk = (p.get("symbol"), p.get("entry_date"))
        if pk not in pick_dedup or p.get("method") == "stock":
            pick_dedup[pk] = p
    pick_rows = list(pick_dedup.values())

    return {
        "cycle_id": cycle_id,
        "archived_date": today_str,
        "regime": regime.name,
        "total_predictions": len(preds),
        "n_picks": len(pick_rows),
        "by_method": {
            "stock": _method_stats(stock_preds, regime, "stock"),
            "long_call": _method_stats(call_preds, regime, "long_call"),
        },
        "calibration": _calibration_check_picks(pick_rows, regime),
        "predictions": preds,
    }


def _calibration_check(by_decile: dict, is_60d: bool = False, regime: Regime = None) -> dict:
    """Legacy decile-dict signature, retained for callers passing a precomputed
    decile map (e.g. _compute_rolling_d10_health). Prefer _calibration_check_picks
    for new code — it accepts raw pick rows and dedupes correctly.
    """
    if regime is None:
        regime = REGIME_60D if is_60d else REGIME_30D_P10
    d10 = by_decile.get(10, {})
    d1 = by_decile.get(1, {})
    d10_hr = d10.get("hit_rate", 0)
    d1_hr = d1.get("hit_rate", 0)
    odds_ratio = (d10_hr / d1_hr) if d1_hr > 0 else None
    base_odds = regime.d10_calib / regime.d1_calib if regime.d1_calib > 0 else 20.0
    healthy = d10.get("n", 0) >= 5 and d10_hr >= regime.kill_threshold
    return {
        "d10_hit_rate": round(d10_hr, 4),
        "d10_n": d10.get("n", 0),
        "d1_hit_rate": round(d1_hr, 4),
        "d1_n": d1.get("n", 0),
        "d10_baseline": regime.d10_calib,
        "d1_baseline": regime.d1_calib,
        "observed_odds_ratio": round(odds_ratio, 2) if odds_ratio else None,
        "baseline_odds_ratio": round(base_odds, 2),
        "kill_switch_threshold": regime.kill_threshold,
        "healthy": healthy,
        "note": (f"D10 must stay above kill-switch ({int(regime.kill_threshold*100)}%) and "
                 f"ideally track the {regime.d10_calib:.1%} baseline. n<5 in D10 -> unstable."),
    }


# ---------------------------------------------------------------------------
# Rolling 90-day D10 health monitor (kill switch)
# ---------------------------------------------------------------------------

def _compute_rolling_d10_health(state: dict, today_str: str, regime: Regime = REGIME_60D) -> dict:
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
        raw = _gcs_read_text(f"{regime.cycles_prefix}/{cycle_id}/predictions.jsonl", "")
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

        # Skip not-yet-resolved predictions
        outcome = row.get("outcome")
        row_window_days = row.get("hit_window_days", regime.hit_window_days)
        row_res_cutoff = today_dt - timedelta(days=row_window_days)
        if outcome == "OPEN" and entry_dt > row_res_cutoff:
            continue

        decile = row.get("decile")
        hit = outcome == "HIT" or (row.get("max_high_observed_pct", 0) >= regime.hit_threshold_pct)

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

    baseline_d10 = regime.d10_calib
    baseline_d1 = regime.d1_calib
    kill_threshold = regime.kill_threshold

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


def _save_rolling_health(health: dict, regime: Regime = REGIME_60D) -> None:
    """Persist the latest rolling health snapshot so /performance can show it
    without recomputing on every UI fetch."""
    _gcs_write(regime.health_path, health)
    if health.get("kill_switch_active"):
        log.warning(
            f"  ⚠ KILL SWITCH ACTIVE ({regime.name}): D10 hit rate {health['d10_hit_rate']:.1%} "
            f"over {KILL_SWITCH_WINDOW_DAYS}d window (threshold "
            f"{regime.kill_threshold:.0%}, baseline "
            f"{regime.d10_calib:.1%}). Model needs retraining."
        )
    else:
        log.info(
            f"  Rolling D10 health ({regime.name}): {health['status']} — "
            f"D10 {health['d10_hit_rate']:.1%} (n={health['d10_n']}), "
            f"D1 {health['d1_hit_rate']:.1%} (n={health['d1_n']}), "
            f"baseline D10={regime.d10_calib:.1%}"
        )


# ---------------------------------------------------------------------------
# Prediction tracking — entries, opens, closes
# ---------------------------------------------------------------------------

def _append_predictions_jsonl_batch(cycle_id: str, rows: list[dict], regime: Regime = REGIME_60D) -> bool:
    """Append multiple prediction rows to predictions.jsonl for the cycle in a single write.
    Avoids sequential network operations to GCS.
    """
    if not rows:
        return True
    path = f"{regime.cycles_prefix}/{cycle_id}/predictions.jsonl"
    existing = _gcs_read_text(path, "")
    new_lines = "\n".join(json.dumps(row, default=str) for row in rows)
    body = existing + ("\n" if existing and not existing.endswith("\n") else "") + new_lines + "\n"
    return _gcs_write(path, body, content_type="text/plain")


def _append_prediction_jsonl(cycle_id: str, row: dict, regime: Regime = REGIME_60D) -> bool:
    """Append one prediction row to predictions.jsonl for the cycle (wrapper around batch helper)."""
    return _append_predictions_jsonl_batch(cycle_id, [row], regime=regime)


def _enrich_stocks_with_theta_eod(stocks: list[dict], today_str: str, is_60d: bool = False, regime: Regime = None) -> None:
    """Fetch ThetaData EOD option quotes for new candidate stocks in parallel
    and inject the options_spread directly into the stock dictionaries.
    """
    if regime is None:
        regime = REGIME_60D if is_60d else REGIME_30D_P10

    try:
        from thetadata import ThetaClient
    except ImportError:
        log.warning("_enrich_stocks_with_theta_eod: ThetaData SDK not available, skipping EOD enrichment")
        return

    target_dt = datetime.strptime(today_str, "%Y-%m-%d")
    _eod_date = target_dt.date()
    
    # Compute the EOD business day
    import datetime as _dt
    while _eod_date.weekday() >= 5:
        _eod_date -= _dt.timedelta(days=1)
        
    # If today_str is today, check if current time is before EOD release (21:00 UTC)
    # to roll back to the prior business day.
    if today_str == datetime.utcnow().strftime("%Y-%m-%d"):
        if datetime.utcnow().hour < 21:
            _eod_date -= _dt.timedelta(days=1)
            while _eod_date.weekday() >= 5:
                _eod_date -= _dt.timedelta(days=1)

    symbols = [s["symbol"] for s in stocks if s.get("symbol") and (s.get("price") or 0) >= 1.0]
    if not symbols:
        return

    try:
        client = ThetaClient(
            email=os.environ["THETA_EMAIL"],
            password=os.environ["THETA_PASSWORD"],
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
    target_dte = regime.synth_dte_days
    long_offset = regime.synth_long_offset
    short_offset = regime.synth_short_offset

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
                dte = (d - target_dt.date()).days
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

        long_close = _get_option_price(lr)
        short_close = _get_option_price(sr)
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


# ---------------------------------------------------------------------------
# Long-call arm: leg picking and single-leg refetch (Python ThetaData only)
# ---------------------------------------------------------------------------
# Touch-payoff model (v2, Jun 2026): the long-call leg is bought and held until the
# underlying TOUCHES barrier_price, then sold. Conditional on that touch the leg is
# worth at least its intrinsic value max(0, barrier_price - strike) * 100 (residual
# time value ignored - a conservative floor). Net touch P&L = intrinsic - ask * 100.
# We select the cheapest strike (most leverage) that still clears a non-negative net
# touch P&L - i.e. the leg profits when the thesis (the touch) plays out.

def _model_fair_value_long_call(strike: float, barrier_price: float) -> float:
    """Gross value of the leg AT the barrier touch = intrinsic * 100 (residual time
    value ignored - conservative). Net touch P&L = this - ask * 100."""
    return max(0.0, barrier_price - strike) * 100.0


def _pick_best_long_leg(exp_df, spot: float, barrier_price: float,
                         p_barrier: float, strike_col: str = 'strike') -> Optional[dict]:
    """From an expiration's option rows, pick the single long call to track: the
    CHEAPEST strike (highest strike = lowest premium = most leverage) that is still
    profitable when sold at the barrier touch (net touch P&L >= 0), else the least-bad.

    Strike range: [spot × 0.70, barrier_price]. Above the barrier, intrinsic at
    touch is 0 — can't win. The floor is 0.70×spot (was 0.95): for high-IV names
    the cheapest profitable-at-touch strike sits deep ITM, below 0.95×spot, so the
    old floor forced a guaranteed-loss near-money leg. The objective still prefers
    the highest (cheapest / most leverage) profitable strike within the window.

    Returns a dict with strike, ask, bid, mid, iv, greeks, model_fair_value,
    edge_dollars, edge_pct, or None if no leg qualifies.
    """
    if exp_df is None or exp_df.empty:
        return None
    lo = spot * 0.70   # was 0.95: for high-IV names no near-money strike is profitable
    hi = barrier_price # at touch (all time value), so the profitable leg sits deeper ITM
    candidates = exp_df[(exp_df[strike_col].astype(float) >= lo) &
                         (exp_df[strike_col].astype(float) <= hi)]
    if candidates.empty:
        return None

    best_profitable = None    # cheapest leg (highest strike) with net touch P&L >= 0
    best_fallback = None       # least-bad leg (max net touch P&L) if none clear zero
    best_fallback_edge = -1e18
    for _, row in candidates.iterrows():
        strike = float(row[strike_col])
        ask = float(row.get('ask', 0) or 0)
        bid = float(row.get('bid', 0) or 0)
        # EOD greeks endpoint sometimes returns close-only; fall back gracefully
        if ask <= 0:
            close = float(row.get('close', 0) or 0)
            if close <= 0:
                continue
            ask = close
            if bid <= 0:
                bid = close * 0.97
        mid = (ask + bid) / 2.0 if bid > 0 else ask
        fair_value = _model_fair_value_long_call(strike, barrier_price)   # gross touch value
        edge_dollars = fair_value - ask * 100.0                           # net touch P&L
        leg = {
            "strike": strike,
            "ask": round(ask, 2),
            "bid": round(bid, 2),
            "mid": round(mid, 2),
            "iv": round(float(row.get('implied_vol', 0) or 0), 4),
            "delta": round(float(row.get('delta', 0) or 0), 4),
            "gamma": round(float(row.get('gamma', 0) or 0), 4),
            "theta": round(float(row.get('theta', 0) or 0), 4),
            "vega": round(float(row.get('vega', 0) or 0), 4),
            "model_fair_value": round(fair_value, 2),
            "edge_dollars": round(edge_dollars, 2),
            "edge_pct": round(edge_dollars / (ask * 100.0), 4) if ask > 0 else None,
        }
        # Objective: cheapest strike that still profits at the touch = the HIGHEST
        # strike whose net touch P&L is non-negative (lowest premium, most leverage).
        if edge_dollars >= 0 and (best_profitable is None or strike > best_profitable["strike"]):
            best_profitable = leg
        if edge_dollars > best_fallback_edge:
            best_fallback_edge = edge_dollars
            best_fallback = leg
    return best_profitable or best_fallback


def _enrich_stocks_with_long_call_legs(stocks: list[dict], today_str: str, regime: Regime) -> None:
    """For each candidate stock, fetch EOD call chain and pick the single long
    leg that maximizes edge_dollars under the touch-payoff model.

    Injects s["long_call_pick_<regime.name>"] = {strike, ask, bid, mid, iv,
    delta, gamma, theta, vega, model_fair_value, edge_dollars, edge_pct,
    expiration, dte_at_entry}, or leaves it absent if no leg qualifies.

    Uses the Python ThetaData SDK — same client/limiter pattern as
    _enrich_stocks_with_theta_eod, single-leg pick instead of a spread.
    """
    try:
        from thetadata import ThetaClient
    except ImportError:
        log.warning("_enrich_stocks_with_long_call_legs: ThetaData SDK not available, skipping")
        return

    target_dt = datetime.strptime(today_str, "%Y-%m-%d")
    _eod_date = target_dt.date()
    import datetime as _dt
    while _eod_date.weekday() >= 5:
        _eod_date -= _dt.timedelta(days=1)
    if today_str == datetime.utcnow().strftime("%Y-%m-%d"):
        if datetime.utcnow().hour < 21:
            _eod_date -= _dt.timedelta(days=1)
            while _eod_date.weekday() >= 5:
                _eod_date -= _dt.timedelta(days=1)

    symbols = [s["symbol"] for s in stocks if s.get("symbol") and (s.get("price") or 0) >= 1.0]
    if not symbols:
        return

    try:
        client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"])
    except Exception as e:
        log.error(f"_enrich_stocks_with_long_call_legs: ThetaData client init failed: {e}")
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

    def fetch_chain(sym):
        limiter.wait()
        try:
            df = client.option_history_greeks_eod(
                symbol=sym, expiration="*", start_date=_eod_date, end_date=_eod_date,
                strike="*", right="call")
            return sym, df, None
        except Exception as e:
            return sym, None, e

    log.info(f"ThetaData (long-call leg pick, {regime.name}): fetching chains for {len(symbols)} symbols...")
    chains: dict[str, object] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_chain, sym) for sym in symbols]
        for fut in concurrent.futures.as_completed(futures):
            sym, df, err = fut.result()
            if df is not None and not (hasattr(df, 'is_empty') and df.is_empty()):
                chains[sym] = df

    target_dte = regime.hit_window_days
    pick_key = f"long_call_pick_{regime.name}"
    picked_count = 0

    for s in stocks:
        sym = s["symbol"]
        spot = s.get("price") or 0
        if spot <= 0:
            continue
        df_raw = chains.get(sym)
        if df_raw is None:
            continue
        try:
            df = df_raw.to_pandas() if hasattr(df_raw, 'to_pandas') else df_raw
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

        # Group by expiration; prefer the soonest expiration that is at or past
        # the window. Below-window expirations would mature before the barrier
        # window closes — unacceptable for forward truth on this method.
        by_exp = {}
        for idx, row in df.iterrows():
            exp_val = row.get("expiration")
            if exp_val:
                by_exp.setdefault(str(exp_val), []).append(row)
        if not by_exp:
            continue

        chosen_exp = None
        chosen_dte = None
        chosen_diff = 10**9
        for exp in sorted(by_exp.keys()):
            try:
                date_str = exp.split()[0]
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                dte = (d - target_dt.date()).days
                if dte < target_dte:
                    continue
                diff = dte - target_dte
                if diff < chosen_diff:
                    chosen_diff = diff
                    chosen_exp = exp
                    chosen_dte = dte
            except Exception:
                continue
        if not chosen_exp:
            continue

        p20 = s.get(regime.prob_key)
        if p20 is None:
            p20 = s.get("hit_prob_60d") if regime.is_60d else s.get("hit_prob")
        if p20 is None:
            p20 = s.get("hit_prob") or 0.0
        if p20 <= 0:
            continue

        barrier_price = spot * (1.0 + regime.hit_threshold_pct / 100.0)
        exp_df = df[df['expiration'] == chosen_exp]
        strike_col = 'strike' if 'strike' in exp_df.columns else None
        if not strike_col or exp_df.empty:
            continue

        best_leg = _pick_best_long_leg(exp_df, spot, barrier_price, p20, strike_col=strike_col)
        if best_leg is None:
            continue

        best_leg["expiration"] = chosen_exp.split()[0] if " " in str(chosen_exp) else str(chosen_exp)
        best_leg["dte_at_entry"] = chosen_dte
        s[pick_key] = best_leg
        picked_count += 1
        log.info(f"  Long-call leg ({regime.name}) {sym}: "
                 f"K=${best_leg['strike']:.2f} @ {best_leg['expiration']} "
                 f"ask=${best_leg['ask']:.2f} edge=${best_leg['edge_dollars']:.0f} "
                 f"({best_leg['edge_pct']*100:.1f}%)" if best_leg.get('edge_pct') is not None
                 else f"  Long-call leg ({regime.name}) {sym}: K=${best_leg['strike']:.2f}")
    log.info(f"  Long-call legs picked: {picked_count}/{len(symbols)} ({regime.name})")


def _refetch_long_call_quote(df_chain, strike: float, expiration: str) -> Optional[dict]:
    """Look up a single long-call leg's row in a pre-fetched chain dataframe.

    Used by the resolver: the existing per-symbol chain fetch is reused across
    all open call-arm rows for the same symbol — no extra API calls.

    Returns {ask, bid, mid, iv, delta, gamma, theta, vega} or None if the
    strike/expiration combo isn't in the chain (delisted, illiquid, missing).
    """
    if df_chain is None or (hasattr(df_chain, 'empty') and df_chain.empty):
        return None
    try:
        df = df_chain.to_pandas() if hasattr(df_chain, 'to_pandas') else df_chain
    except Exception:
        return None
    if df.empty:
        return None
    if 'expiration' not in df.columns or 'strike' not in df.columns:
        return None
    exp_norm = expiration.split()[0] if " " in str(expiration) else str(expiration)
    matched = df[(df['expiration'].astype(str).str.startswith(exp_norm)) &
                 (df['strike'].astype(float).round(2) == round(float(strike), 2))]
    if matched.empty:
        return None
    row = matched.iloc[0]
    ask = float(row.get('ask', 0) or 0)
    bid = float(row.get('bid', 0) or 0)
    if ask <= 0:
        close = float(row.get('close', 0) or 0)
        if close <= 0:
            return None
        ask = close
        if bid <= 0:
            bid = close * 0.97
    mid = (ask + bid) / 2.0 if bid > 0 else ask
    return {
        "ask": round(ask, 2),
        "bid": round(bid, 2),
        "mid": round(mid, 2),
        "iv": round(float(row.get('implied_vol', 0) or 0), 4),
        "delta": round(float(row.get('delta', 0) or 0), 4),
        "gamma": round(float(row.get('gamma', 0) or 0), 4),
        "theta": round(float(row.get('theta', 0) or 0), 4),
        "vega": round(float(row.get('vega', 0) or 0), 4),
    }


def _record_new_predictions(stocks: list, today_str: str, cycle_id: str,
                            region: str, is_60d_regime: bool = False, regime: Regime = None) -> tuple[int, int]:
    """For each P20>0 stock not already in this cycle, emit TWO prediction
    rows — one stock arm (sell-at-touch with regime stop), one long-call arm
    (single leg picked via touch-payoff edge). Combined across the two
    regimes in update_from_scan, each pick produces 4 rows total:
      stock × 30dd/+10% (20% stop) | stock × 60dd/+20% (no-stop shadow)
      long_call × 30dd/+10%        | long_call × 60dd/+20%

    Both arms ship the same common entry context (price, P20, decile, IVR,
    IV, skew, etc.) so cross-method analysis pivots on consistent fields.

    Returns (new_row_count, no_call_leg_count). new_row_count = 2 × picks.
    no_call_leg_count = picks where the call arm shipped with null leg
    (Theta SDK missing, no expiration past window, no positive-edge strike).
    """
    if regime is None:
        regime = REGIME_60D if is_60d_regime else REGIME_30D_P10

    open_path = f"{regime.cycles_prefix}/{cycle_id}/open.json"
    open_data = _gcs_read(open_path, {"predictions": []})
    if not isinstance(open_data, dict):
        open_data = {"predictions": []}
    open_preds = open_data.get("predictions", [])

    # Symbols already tracked in the current cycle (any state) — don't re-enter
    already_in_cycle = {p["symbol"] for p in open_preds}

    # Also check predictions.jsonl for symbols already entered this cycle even
    # if they've since closed (so we don't double-enter same stock per cycle)
    raw = _gcs_read_text(f"{regime.cycles_prefix}/{cycle_id}/predictions.jsonl", "")
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
        p20 = s.get(regime.prob_key)
        if p20 is None:
            p20 = s.get("hit_prob_60d") if regime.is_60d else s.get("hit_prob")
        if p20 is None:
            p20 = s.get("hit_prob") or 0.0
        if p20 <= P20_INCLUSION:
            continue
        sym = s.get("symbol")
        if not sym or sym in already_in_cycle:
            continue
        candidate_stocks.append(s)

    # Theta enrichment: fetch full call chain per candidate, pick best single
    # long leg (max edge_dollars under touch-payoff model). Skips silently
    # when ThetaData SDK unavailable — call arms simply ship with null leg
    # fields and tag no_ev for accounting.
    if candidate_stocks:
        _enrich_stocks_with_long_call_legs(candidate_stocks, today_str, regime)

    for s in candidate_stocks:
        p20 = s.get(regime.prob_key)
        if p20 is None:
            p20 = s.get("hit_prob_60d") if regime.is_60d else s.get("hit_prob")
        if p20 is None:
            p20 = s.get("hit_prob") or 0.0
        sym = s.get("symbol")
        price = s.get("price") or 0
        if price <= 0:
            skipped_no_price += 1
            continue

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

        hit_window_days = regime.hit_window_days
        fate_window_ends = (datetime.strptime(today_str, "%Y-%m-%d")
                             + timedelta(days=hit_window_days)).strftime("%Y-%m-%d")

        expected_dd = s.get("expected_dd_60d") if regime.is_60d else s.get("expected_dd_30d")
        if expected_dd is not None:
            expected_dd = round(float(expected_dd), 2)

        # Common entry context — identical across both method rows for this
        # symbol/regime so cross-method comparison pivots on consistent
        # entry-time fields. ATM IV / IVR / skew / pc_oi land on the stock arm
        # too (even though unused by stock payoff) so downstream filtering can
        # slice stock outcomes by IV regime same as call outcomes.
        common = {
            "symbol": sym,
            "entry_date": today_str,
            "cycle_id": cycle_id,
            "region": region,
            "regime": regime.name,
            "entry_price": round(price, 4),
            "p20": round(p20, 4),
            "decile": _decile(p20, regime=regime),
            "signal_strength": _signal_strength(p20, regime=regime),
            "mode_qualifications": modes,
            "composite": s.get("composite"),
            "company_name": s.get("company_name"),
            "sector": s.get("sector"),
            "country": s.get("country"),
            "market_cap": s.get("market_cap"),
            "expected_dd": expected_dd,
            "ivr_at_entry": s.get("options_iv_rank"),
            "iv_at_entry": s.get("options_iv_current"),
            "skew_25d": s.get("options_skew_25d"),
            "pc_oi_ratio": s.get("options_pc_oi_ratio"),
            "fate_window_ends": fate_window_ends,
            "hit_window_days": hit_window_days,
            "barrier_target_pct": regime.hit_threshold_pct,
            "barrier_price": round(price * (1.0 + regime.hit_threshold_pct / 100.0), 4),
            "outcome": "OPEN",
            "outcome_tag": "OPEN",
            "current_price": round(price, 4),
            "last_updated": today_str,
            "days_observed": 0,
            "max_high_observed_pct": 0.0,
            "max_drawdown_observed_pct": 0.0,
            "realized_return_pct": None,
            "resolution_date": None,
        }

        # Stock arm — locked 20% stop for 30dd/+10%, no-stop shadow for
        # 60dd/+20%. Sweep showed no-stop wins on CAGR but with worst tail;
        # both run live so the trade-off is visible forward.
        if regime.is_60d:
            stop_loss_pct = None
            stop_price = None
        else:
            stop_loss_pct = 20.0
            stop_price = round(price * (1.0 - 20.0 / 100.0), 4)

        stock_row = {
            **common,
            "method": "stock",
            "stop_loss_pct": stop_loss_pct,
            "stop_price": stop_price,
        }
        new_preds.append(stock_row)

        # Long-call arm — single leg picked by Theta enrichment above. When
        # Theta returns no viable leg (SDK missing, no liquid expiration past
        # window, all strikes have negative edge), the row still ships with
        # null leg fields so the symbol's method coverage stays consistent.
        leg = s.get(f"long_call_pick_{regime.name}")
        if leg is None:
            no_ev_count += 1
        call_row = {
            **common,
            "method": "long_call",
            "chosen_leg_strike": leg.get("strike") if leg else None,
            "chosen_leg_expiration": leg.get("expiration") if leg else None,
            "chosen_leg_dte_at_entry": leg.get("dte_at_entry") if leg else None,
            # Crossed entry — pay the ask.
            "entry_quote_ask": leg.get("ask") if leg else None,
            "entry_quote_bid": leg.get("bid") if leg else None,
            "entry_quote_mid": leg.get("mid") if leg else None,
            "entry_iv_at_strike": leg.get("iv") if leg else None,
            "entry_delta": leg.get("delta") if leg else None,
            "entry_gamma": leg.get("gamma") if leg else None,
            "entry_theta": leg.get("theta") if leg else None,
            "entry_vega": leg.get("vega") if leg else None,
            # Touch-payoff model edge.
            "model_fair_value_at_entry": leg.get("model_fair_value") if leg else None,
            "edge_dollars_at_entry": leg.get("edge_dollars") if leg else None,
            "edge_pct_at_entry": leg.get("edge_pct") if leg else None,
            # Forward marks — initialized to entry quote, refreshed by resolver.
            "current_quote_ask": leg.get("ask") if leg else None,
            "current_quote_bid": leg.get("bid") if leg else None,
            "current_quote_mid": leg.get("mid") if leg else None,
            "current_iv_at_strike": leg.get("iv") if leg else None,
            "current_delta": leg.get("delta") if leg else None,
            "current_theta": leg.get("theta") if leg else None,
            "unrealized_pnl": 0.0 if leg else None,
            "unrealized_pnl_pct": 0.0 if leg else None,
            "realized_pnl_at_resolve": None,
            "quote_last_repriced": today_str if leg else None,
        }
        new_preds.append(call_row)
        already_in_cycle.add(sym)

    if new_preds:
        if _append_predictions_jsonl_batch(cycle_id, new_preds, regime=regime):
            open_preds.extend(new_preds)
            new_count = len(new_preds)
            _gcs_write(open_path, {"predictions": open_preds})
        else:
            log.warning(f"  Failed to append batch of {len(new_preds)} predictions")

    return new_count, no_ev_count


def _refresh_call_chains(symbols: set, today_str: str) -> dict:
    """Fetch EOD call chains for a set of symbols (used by resolver to
    refresh long-call arm marks). Returns {symbol: df_chain}. Empty dict on
    Theta failure — caller falls back to intrinsic-only marks.
    """
    if not symbols:
        return {}
    try:
        from thetadata import ThetaClient
    except ImportError:
        log.warning("_refresh_call_chains: ThetaData SDK not available, skipping leg refresh")
        return {}

    target_dt = datetime.strptime(today_str, "%Y-%m-%d")
    _eod_date = target_dt.date()
    import datetime as _dt
    while _eod_date.weekday() >= 5:
        _eod_date -= _dt.timedelta(days=1)
    if today_str == datetime.utcnow().strftime("%Y-%m-%d"):
        if datetime.utcnow().hour < 21:
            _eod_date -= _dt.timedelta(days=1)
            while _eod_date.weekday() >= 5:
                _eod_date -= _dt.timedelta(days=1)

    try:
        client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"])
    except Exception as e:
        log.error(f"_refresh_call_chains: client init failed: {e}")
        return {}

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

    def fetch_chain(sym):
        limiter.wait()
        try:
            df = client.option_history_greeks_eod(
                symbol=sym, expiration="*", start_date=_eod_date, end_date=_eod_date,
                strike="*", right="call")
            return sym, df, None
        except Exception as e:
            return sym, None, e

    log.info(f"ThetaData (call-arm resolver): fetching chains for {len(symbols)} symbols...")
    chains: dict[str, object] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_chain, sym) for sym in symbols]
        for fut in concurrent.futures.as_completed(futures):
            sym, df, err = fut.result()
            if df is not None and not (hasattr(df, 'is_empty') and df.is_empty()):
                chains[sym] = df
    return chains


def _refresh_underlying_eod(symbol_entry: dict, today_str: str) -> dict:
    """For each symbol, fetch daily OHLC over [entry_date, today] from ThetaData
    and return {symbol: (max_high_price, min_low_price)} — the intraday extremes
    over the holding window. Lets the resolver count a +X% intraday spike that
    reverts by the nightly close as a real touch (and capture the true trough).
    Empty dict on Theta failure → caller falls back to the close-based extremes.
    """
    if not symbol_entry:
        return {}
    try:
        from thetadata import ThetaClient
        import datetime as _dt
    except ImportError:
        log.warning("_refresh_underlying_eod: ThetaData SDK unavailable, using close-based extremes")
        return {}
    try:
        client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"])
    except Exception as e:
        log.error(f"_refresh_underlying_eod: client init failed: {e}")
        return {}

    end_date = datetime.strptime(today_str, "%Y-%m-%d").date()
    while end_date.weekday() >= 5:
        end_date -= _dt.timedelta(days=1)

    from threading import Lock
    import concurrent.futures

    class _RL:
        def __init__(self, rps): self.interval = 1.0 / rps; self.last = 0.0; self.lock = Lock()
        def wait(self):
            with self.lock:
                import time as _t
                now = _t.time(); s = self.interval - (now - self.last)
                if s > 0: _t.sleep(s); self.last = _t.time()
                else: self.last = now
    limiter = _RL(16)

    def fetch_hl(item):
        sym, entry = item
        try:
            start = datetime.strptime(entry, "%Y-%m-%d").date()
        except Exception:
            return sym, None
        if start > end_date:
            return sym, None
        hi = lo = None
        cur = start
        while cur <= end_date:  # ThetaData caps multi-day EOD at ~1 month → chunk
            chunk_end = min(cur + _dt.timedelta(days=28), end_date)
            limiter.wait()
            try:
                df = client.stock_history_eod(sym, cur, chunk_end)
                if df is not None and hasattr(df, "height") and df.height > 0:
                    ch = df.get_column("high").max(); cl = df.get_column("low").min()
                    if ch is not None: hi = ch if hi is None else max(hi, ch)
                    if cl is not None: lo = cl if lo is None else min(lo, cl)
            except Exception as e:
                log.debug(f"_refresh_underlying_eod {sym} [{cur}..{chunk_end}]: {e}")
            cur = chunk_end + _dt.timedelta(days=1)
        if hi is None or lo is None:
            return sym, None
        return sym, (float(hi), float(lo))

    out: dict[str, tuple] = {}
    log.info(f"ThetaData (underlying EOD high/low): fetching for {len(symbol_entry)} symbols...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for sym, hl in executor.map(fetch_hl, list(symbol_entry.items())):
            if hl is not None:
                out[sym] = hl
    return out


def _process_open_predictions(stocks: list, today_str: str,
                              state: dict, regime: Regime = REGIME_60D) -> tuple[int, int]:
    """For every cycle with active predictions, update each open prediction
    with today's price and resolve per-method exit conditions.

    Stock arms (method == "stock"):
      SOLD_AT_TOUCH  max_high_observed_pct >= barrier_target_pct
      STOPPED        stop_loss_pct set AND current_price <= stop_price
      TERMINAL       days_observed >= hit_window_days (close at day-N price)
      Order of checks: barrier first (intraday high wins ties with stop),
      then stop, then window. realized_return_pct = max_high on SOLD_AT_TOUCH,
      -stop_loss_pct on STOPPED, day-N gain_pct on TERMINAL.

    Long-call arms (method == "long_call"):
      Single-leg quote refreshed from a pooled ThetaData chain refetch (one
      call per symbol covers both regime's arms).
      SOLD_AT_TOUCH  max_high_observed_pct >= barrier_target_pct
      TERMINAL       days_observed >= hit_window_days
      Exit value at resolve = current_quote_mid × 100 (when chain quote
      available) else intrinsic = max(0, current_price - strike) × 100.
      realized_pnl = exit_value - entry_quote_ask × 100 (crossed entry).
      No stop on long calls (entry_ask is the max loss bound).

    Returns (closed_count, still_open_count).
    """
    price_lookup = {s["symbol"]: s.get("price") or 0 for s in stocks if s.get("symbol")}

    cycles_to_process = []
    if state["collecting_cycle_id"]:
        cycles_to_process.append(state["collecting_cycle_id"])
    cycles_to_process.extend(state["resolving_cycle_ids"])

    # Load all open predictions across cycles first so we can pool the
    # call-arm chain refetch into one Theta sweep (one call per unique symbol
    # regardless of how many cycles or arms reference it).
    cycles_data: dict[str, tuple] = {}
    call_arm_symbols: set = set()
    for cycle_id in cycles_to_process:
        open_path = f"{regime.cycles_prefix}/{cycle_id}/open.json"
        open_data = _gcs_read(open_path, {"predictions": []})
        if not isinstance(open_data, dict):
            continue
        preds = open_data.get("predictions", [])
        if not preds:
            continue
        cycles_data[cycle_id] = (open_path, preds)
        for p in preds:
            if p.get("method") == "long_call" and p.get("chosen_leg_strike") is not None:
                call_arm_symbols.add(p["symbol"])

    chain_lookup = _refresh_call_chains(call_arm_symbols, today_str)

    # Underlying intraday high/low over each pick's window — so a +X% spike that
    # reverts by the nightly snapshot still counts as a touch, and the drawdown is
    # the true trough. Falls back to the scan close if Theta is unavailable.
    underlying_windows: dict[str, str] = {}
    for _cid, (_op, _preds) in cycles_data.items():
        for _p in _preds:
            _e = _p.get("entry_date")
            if _e:
                _cur = underlying_windows.get(_p["symbol"])
                if _cur is None or _e < _cur:
                    underlying_windows[_p["symbol"]] = _e
    high_low_lookup = _refresh_underlying_eod(underlying_windows, today_str)

    closed_total = 0
    open_total = 0

    for cycle_id, (open_path, preds) in cycles_data.items():
        updated = []
        newly_closed = []
        for p in preds:
            sym = p["symbol"]
            entry_price = p["entry_price"]
            current_price = price_lookup.get(sym, p.get("current_price", entry_price))
            gain_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

            # Spot-path peak / trough (used by both arms — call arm reads
            # max_high to detect barrier touch, even though its P&L is on the
            # option leg).
            hl = high_low_lookup.get(sym)
            if hl and entry_price > 0:
                hi_gain = ((hl[0] - entry_price) / entry_price) * 100   # intraday high over window
                lo_gain = ((hl[1] - entry_price) / entry_price) * 100   # intraday low over window
            else:
                hi_gain = lo_gain = gain_pct                            # fallback: nightly close only
            if hi_gain > p.get("max_high_observed_pct", 0):
                p["max_high_observed_pct"] = round(hi_gain, 4)
            if lo_gain < p.get("max_drawdown_observed_pct", 0):
                p["max_drawdown_observed_pct"] = round(lo_gain, 4)

            days_in = (datetime.strptime(today_str, "%Y-%m-%d")
                       - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days
            p["days_observed"] = days_in
            p["current_price"] = round(current_price, 4)
            p["last_updated"] = today_str

            method = p.get("method", "stock")
            barrier_pct = p.get("barrier_target_pct", regime.hit_threshold_pct)
            window_days = p.get("hit_window_days", regime.hit_window_days)
            barrier_touched = p["max_high_observed_pct"] >= barrier_pct
            window_terminal = days_in >= window_days

            if method == "stock":
                stop_price = p.get("stop_price")
                stopped = stop_price is not None and current_price <= stop_price

                if barrier_touched:
                    p["outcome"] = "CLOSED"
                    p["outcome_tag"] = "SOLD_AT_TOUCH"
                    p["realized_return_pct"] = round(p["max_high_observed_pct"], 4)
                    p["resolution_date"] = today_str
                    newly_closed.append(p)
                    closed_total += 1
                    continue
                if stopped:
                    p["outcome"] = "CLOSED"
                    p["outcome_tag"] = "STOPPED"
                    p["realized_return_pct"] = round(-(p.get("stop_loss_pct") or 0), 4)
                    p["resolution_date"] = today_str
                    newly_closed.append(p)
                    closed_total += 1
                    continue
                if window_terminal:
                    p["outcome"] = "CLOSED"
                    p["outcome_tag"] = "TERMINAL"
                    p["realized_return_pct"] = round(gain_pct, 4)
                    p["resolution_date"] = today_str
                    newly_closed.append(p)
                    closed_total += 1
                    continue
                updated.append(p)
                open_total += 1
                continue

            if method == "long_call":
                strike = p.get("chosen_leg_strike")
                expiration = p.get("chosen_leg_expiration")
                entry_ask = p.get("entry_quote_ask")
                cost_basis = entry_ask * 100.0 if entry_ask is not None else None

                # Refresh leg quote if chain was fetched
                df_chain = chain_lookup.get(sym) if (strike is not None and expiration) else None
                if df_chain is not None:
                    leg_quote = _refetch_long_call_quote(df_chain, strike, expiration)
                    if leg_quote is not None:
                        p["current_quote_ask"] = leg_quote["ask"]
                        p["current_quote_bid"] = leg_quote["bid"]
                        p["current_quote_mid"] = leg_quote["mid"]
                        p["current_iv_at_strike"] = leg_quote["iv"]
                        p["current_delta"] = leg_quote["delta"]
                        p["current_theta"] = leg_quote["theta"]
                        p["quote_last_repriced"] = today_str
                        if cost_basis is not None and cost_basis > 0:
                            current_value = leg_quote["mid"] * 100.0
                            p["unrealized_pnl"] = round(current_value - cost_basis, 2)
                            p["unrealized_pnl_pct"] = round(
                                (current_value - cost_basis) / cost_basis * 100, 2)

                if barrier_touched or window_terminal:
                    p["outcome"] = "CLOSED"
                    p["outcome_tag"] = "SOLD_AT_TOUCH" if barrier_touched else "TERMINAL"
                    p["resolution_date"] = today_str
                    # Exit value: current mid (only if refreshed TODAY) else
                    # spot intrinsic. The stale entry mid persists in
                    # current_quote_mid when Theta is unavailable — preferring
                    # it over intrinsic would silently anchor realized P&L to
                    # the entry quote forever.
                    quote_fresh_today = p.get("quote_last_repriced") == today_str
                    if quote_fresh_today and p.get("current_quote_mid") is not None:
                        exit_value = p["current_quote_mid"] * 100.0
                    elif strike is not None:
                        exit_value = max(0.0, current_price - strike) * 100.0
                    else:
                        exit_value = 0.0
                    if cost_basis is not None and cost_basis > 0:
                        p["realized_pnl_at_resolve"] = round(exit_value - cost_basis, 2)
                        p["realized_return_pct"] = round(
                            (exit_value - cost_basis) / cost_basis * 100, 2)
                    else:
                        p["realized_pnl_at_resolve"] = None
                        p["realized_return_pct"] = None
                    newly_closed.append(p)
                    closed_total += 1
                    continue
                updated.append(p)
                open_total += 1
                continue

            # Unknown method (shouldn't happen post-wipe). Keep open and log once.
            updated.append(p)
            open_total += 1

        if newly_closed:
            _append_predictions_jsonl_batch(cycle_id, newly_closed, regime=regime)
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
    """Reprice all open spread contracts using ThetaData EOD greeks for all regimes.

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

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_date = today.date()

    # ThetaData EOD data is only available after market close (~16:30 ET).
    # Use the last business day that has published EOD data.
    import datetime as _dt
    _eod_date = today_date
    # If market hasn't closed yet on a weekday, use previous business day
    if today_date.weekday() < 5 and today.hour < 21:  # Cloud Run runs in UTC
        _eod_date -= _dt.timedelta(days=1)
    # If it's a weekend, roll back to Friday
    while _eod_date.weekday() >= 5:  # 5=Sat, 6=Sun
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

    try:
        client = ThetaClient(
            email=os.environ["THETA_EMAIL"],
            password=os.environ["THETA_PASSWORD"],
        )
    except Exception as e:
        log.error(f"reprice: ThetaData client init failed: {e}")
        return {"repriced": 0, "skipped": 0, "expired_settled": 0}

    results = []
    for regime in (REGIME_60D, REGIME_30D_P10):
        log.info(f"reprice: running for regime {regime.name}...")
        res = _reprice_open_contracts_for_regime(regime, client, today, today_str, today_date, _eod_date, iv_ranks)
        results.append(res)
        log.info(f"reprice [{regime.name}] result: {res}")

    return {
        "repriced": sum(r["repriced"] for r in results),
        "skipped": sum(r["skipped"] for r in results),
        "expired_settled": sum(r["expired_settled"] for r in results),
    }


def _reprice_open_contracts_for_regime(regime: Regime, client, today, today_str, today_date, _eod_date, iv_ranks) -> dict:
    state = _load_cycle_state(regime)
    if not state:
        return {"repriced": 0, "skipped": 0, "expired_settled": 0}

    cycles_to_process = []
    if state.get("collecting_cycle_id"):
        cycles_to_process.append(state["collecting_cycle_id"])
    cycles_to_process.extend(state.get("resolving_cycle_ids", []))

    symbol_preds: dict[str, list[tuple[str, dict]]] = {}
    expired_preds: list[tuple[str, dict]] = []
    loaded_cycles: dict[str, dict] = {}

    for cycle_id in cycles_to_process:
        open_path = f"{regime.cycles_prefix}/{cycle_id}/open.json"
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

        log.info(f"[{regime.name}] reprice: fetching Greeks for {len(symbol_preds)} symbols...")
        symbol_dfs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_greeks_for_symbol, sym) for sym in symbol_preds.keys()]
            for fut in concurrent.futures.as_completed(futures):
                sym, greeks_df, err = fut.result()
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
                long_close = _get_option_price(lr)
                short_close = _get_option_price(sr)
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

    # Run for both regimes!
    for regime in (REGIME_60D, REGIME_30D_P10):
        log.info(f"signal_tracker: running update for regime {regime.name}...")
        try:
            state = _load_cycle_state(regime)
            state = _advance_cycles_if_needed(state, today_str, regime)
            _save_cycle_state(state, regime)
            log.info(f"  [{regime.name}] Cycle state: collecting={state['collecting_cycle_id']}, "
                     f"resolving={state['resolving_cycle_ids']}, "
                     f"archived={len(state['archived_cycle_ids'])}")
        except Exception as e:
            log.error(f"  [{regime.name}] signal_tracker cycle advance failed: {e}", exc_info=True)
            continue  # don't proceed for this regime without a valid cycle state

        # New predictions enter the current collecting cycle. We track every stock
        # with hit_prob > 0 (the enriched ~30-50 per scan, all deciles) so we can
        # compute the full decile distribution and validate calibration.
        try:
            new_count, no_call_leg = _record_new_predictions(
                stocks, today_str, state["collecting_cycle_id"], region, regime=regime)
            log.info(f"  [{regime.name}] Predictions: +{new_count} rows "
                     f"(~{new_count // 2} picks × 2 method arms; "
                     f"{no_call_leg} call arms with null leg)")
        except Exception as e:
            log.error(f"  [{regime.name}] signal_tracker record predictions failed: {e}", exc_info=True)

        # Update all open predictions (collecting + resolving cycles)
        try:
            closed, open_n = _process_open_predictions(stocks, today_str, state, regime=regime)
            log.info(f"  [{regime.name}] Predictions update: {closed} closed today, {open_n} still open")
        except Exception as e:
            log.error(f"  [{regime.name}] signal_tracker process open failed: {e}", exc_info=True)

        # Try to archive any RESOLVING cycles whose predictions are all closed
        try:
            state = _attempt_archive_resolving_cycles(state, today_str, regime=regime)
            _save_cycle_state(state, regime)
        except Exception as e:
            log.error(f"  [{regime.name}] signal_tracker archive resolving failed: {e}", exc_info=True)

        # Rolling 90-day D10 health check + kill-switch alerting. Runs every scan
        # so the dashboard can show live calibration status.
        try:
            health = _compute_rolling_d10_health(state, today_str, regime=regime)
            _save_rolling_health(health, regime=regime)
        except Exception as e:
            log.error(f"  [{regime.name}] signal_tracker rolling health failed: {e}", exc_info=True)

    # Stock history (unchanged, regime-independent)
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
    """Convert a prediction row to SignalTrackOpen shape. Carries
    method + regime + outcome_tag so the UI can split by arm."""
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
        # New schema additions — let the UI pivot per method/regime
        "method": p.get("method"),
        "regime": p.get("regime"),
        "outcome_tag": p.get("outcome_tag", "OPEN"),
        "barrier_target_pct": p.get("barrier_target_pct"),
        "barrier_price": p.get("barrier_price"),
    }


def _pred_to_signal_closed(p: dict) -> dict:
    """Convert a resolved prediction row to SignalTrackClosed shape."""
    base = _pred_to_signal_open(p)
    cp = p.get("current_price", base["entry_price"])
    pnl = p.get("realized_return_pct", 0) or 0
    max_high = p.get("max_high_observed_pct", 0) or 0
    max_dd = p.get("max_drawdown_observed_pct", 0) or 0
    exit_signal_map = {
        "SOLD_AT_TOUCH": "SELL_TOUCH",
        "STOPPED": "SELL_STOP",
        "TERMINAL": "SELL_WINDOW",
    }
    base.update({
        "exit_date": p.get("resolution_date", p.get("last_updated", "")),
        "exit_price": cp,
        "exit_composite": p.get("composite", 0) or 0,
        "exit_signal": exit_signal_map.get(p.get("outcome_tag"), "SELL"),
        "realized_pnl_pct": round(pnl, 2),
        "max_gain_pct": round(max_high, 2),
        "max_dd_pct": round(max_dd, 2),
    })
    return base


def _pred_to_hitrate_open(p: dict) -> dict:
    """Convert a prediction row to HitRateOpen shape. Barrier is read off
    the row (10% for 30d arm, 20% for 60d arm) — no hardcoded threshold."""
    ep = p.get("entry_price", 0) or 0
    cp = p.get("current_price", ep) or ep
    p20 = p.get("p20", 0) or 0
    # p10_val approximates the row's P(barrier) for UI display. For the 30d
    # regime this IS P10; for 60d it's P20 — name kept for frontend compat.
    p10_val = min(p20 * P10_MULT, 0.65)
    max_high_pct = p.get("max_high_observed_pct", 0) or 0
    barrier_pct = p.get("barrier_target_pct") or 10.0
    sig = _SIGNAL_MAP.get(p.get("signal_strength", ""), "HOLD")
    # hit_date: barrier touched within window AND resolution recorded
    hit_date = None
    if max_high_pct >= barrier_pct and p.get("resolution_date"):
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
        "method": p.get("method"),
        "regime": p.get("regime"),
        "barrier_target_pct": barrier_pct,
    }


def _pred_to_hitrate_closed(p: dict) -> dict:
    """Convert a resolved prediction row to HitRateClosed shape."""
    base = _pred_to_hitrate_open(p)
    max_high = p.get("max_high_observed_pct", 0) or 0
    barrier_pct = p.get("barrier_target_pct") or 10.0
    hit = p.get("outcome_tag") == "SOLD_AT_TOUCH" or max_high >= barrier_pct
    tag = p.get("outcome_tag", "")
    exit_reason_map = {
        "SOLD_AT_TOUCH": f"hit_{int(barrier_pct)}pct",
        "STOPPED": "stopped",
        "TERMINAL": "window_closed",
    }
    base.update({
        "exit_date": p.get("resolution_date", p.get("last_updated", "")),
        "exit_reason": exit_reason_map.get(tag, "window_closed"),
        "hit": hit,
        "max_gain_pct": round(max_high, 2),
    })
    return base


def _gather_predictions_from_cycles(state: dict, include_archived: int = 6,
                                      regime: Regime = None):
    """Gather open and closed prediction rows from all known cycles in a
    single regime tree. Caller iterates regimes if cross-regime data is needed.

    New schema: open list = rows still tracking (outcome == "OPEN"), closed
    list = rows finalized (outcome == "CLOSED"). Dedup key includes method
    and regime so the 4 rows per pick (stock×30d, call×30d, stock×60d,
    call×60d) all survive the dedup pass.
    """
    if regime is None:
        regime = REGIME_60D

    open_list: list = []
    closed_list: list = []
    seen_closed: set = set()

    active_ids = []
    if state.get("collecting_cycle_id"):
        active_ids.append(state["collecting_cycle_id"])
    active_ids.extend(state.get("resolving_cycle_ids", []))

    for cid in active_ids:
        open_data = _gcs_read(f"{regime.cycles_prefix}/{cid}/open.json",
                              {"predictions": []})
        for p in (open_data or {}).get("predictions", []):
            open_list.append(p)

    for cid in active_ids:
        raw = _gcs_read_text(f"{regime.cycles_prefix}/{cid}/predictions.jsonl", "")
        latest: dict = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            key = (row.get("symbol"), row.get("entry_date"),
                   row.get("method"), row.get("regime"))
            existing = latest.get(key)
            if existing is None:
                latest[key] = row
            elif existing.get("outcome") == "OPEN" and row.get("outcome") != "OPEN":
                latest[key] = row
        for key, row in latest.items():
            if row.get("outcome") == "CLOSED" and key not in seen_closed:
                seen_closed.add(key)
                closed_list.append(row)

    for cid in state.get("archived_cycle_ids", [])[-include_archived:]:
        arch = _gcs_read(f"{regime.cycles_prefix}/{cid}/archived.json", None)
        if not arch or not isinstance(arch, dict):
            continue
        for p in arch.get("predictions", []):
            key = (p.get("symbol"), p.get("entry_date"),
                   p.get("method"), p.get("regime"))
            if key not in seen_closed:
                seen_closed.add(key)
                closed_list.append(p)

    return open_list, closed_list


def _gather_predictions_all_regimes(include_archived: int = 6):
    """Walk both regime trees and return one flat (open, closed) pair.
    Rows already carry their `method` and `regime` tags so the consumer can
    pivot however it wants.
    """
    all_open: list = []
    all_closed: list = []
    for regime in (REGIME_30D_P10, REGIME_60D):
        state = _load_cycle_state(regime)
        if not state or not state.get("collecting_cycle_id"):
            continue
        o, c = _gather_predictions_from_cycles(state, include_archived, regime)
        all_open.extend(o)
        all_closed.extend(c)
    return all_open, all_closed


def read_signal_tracks() -> dict:
    """Derive signal-track data from cycle predictions across BOTH regimes.

    Each row carries `method` and `regime` so the UI can pivot or filter
    per method/regime.
    """
    open_preds, closed_preds = _gather_predictions_all_regimes()
    return {
        "open": [_pred_to_signal_open(p) for p in open_preds],
        "closed": [_pred_to_signal_closed(p) for p in closed_preds],
    }


def read_hitrate_tracks() -> dict:
    """Derive hit-rate data from cycle predictions across BOTH regimes.

    Each row carries `method`, `regime`, and `barrier_target_pct` so the UI
    can compute per-arm hit rates.
    """
    open_preds, closed_preds = _gather_predictions_all_regimes()

    return {
        "open": [_pred_to_hitrate_open(p) for p in open_preds],
        "closed": [_pred_to_hitrate_closed(p) for p in closed_preds],
    }


def read_method_tracks(include_archived: int = 6) -> dict:
    """Method-aware reader: returns per-regime, per-method aggregate stats
    plus the recent archived cycle summaries. Designed for the new
    four-method comparison UI.

    Shape:
      {
        "regimes": {
          "30d_p10": {
            "regime": "30d_p10",
            "barrier_target_pct": 10.0,
            "hit_window_days": 30,
            "current_cycle": <method-aware summary, in-progress>,
            "archived_cycles": [<last N archived summaries, newest first>]
          },
          "60d": {...}
        },
        "as_of": "YYYY-MM-DD"
      }
    """
    out: dict = {"regimes": {}, "as_of": datetime.now().strftime("%Y-%m-%d")}
    for regime in (REGIME_30D_P10, REGIME_60D):
        state = _load_cycle_state(regime)
        if not state:
            continue
        block: dict = {
            "regime": regime.name,
            "barrier_target_pct": regime.hit_threshold_pct,
            "hit_window_days": regime.hit_window_days,
            "current_cycle": None,
            "archived_cycles": [],
        }
        # Current (collecting) cycle: compute live summary so the UI can show
        # in-progress stock vs call performance before the cycle archives.
        collecting = state.get("collecting_cycle_id")
        if collecting:
            try:
                block["current_cycle"] = _compute_cycle_summary(
                    collecting, datetime.now().strftime("%Y-%m-%d"), regime)
            except Exception as e:
                log.warning(f"read_method_tracks: current cycle summary failed for {regime.name}: {e}")
        # Recent archived cycles (newest first)
        for cid in reversed(state.get("archived_cycle_ids", [])[-include_archived:]):
            arch = _gcs_read(f"{regime.cycles_prefix}/{cid}/archived.json", None)
            if arch and isinstance(arch, dict):
                block["archived_cycles"].append(arch)
        out["regimes"][regime.name] = block
    return out
