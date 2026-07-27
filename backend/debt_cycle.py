#!/usr/bin/env python3
"""
Dalio Long-Term Debt Cycle Layer — CB Screener
===============================================
Third, orthogonal macro axis beside macro_regime.py's risk label and growth x
inflation quadrant. Answers the question neither can: are positive real rates
being CHOSEN by a hot economy, or IMPOSED by the bond market on the borrower?

Phases (path-dependent state machine, NOT a stateless classifier):
  EXPANSION    — borrowing freely, real rates low, auctions bid
  DISCIPLINE   — bond market imposing positive real rates; duration punished,
                 cash flow rewarded, real assets NOT yet
  FORCING      — funding stress live (auction failures, credit spreads blowing)
  MONETIZATION — CB absorbs the debt; real rates forced negative; real assets

╔════════════════════════════════════════════════════════════════════════╗
║ CONVENTION INVERSION vs macro_regime.py:                               ║
║   here HIGHER sub-score = LATER in the debt cycle / MORE stress.       ║
║   macro_regime.py scores higher = more risk-on. Do not mix them.       ║
╚════════════════════════════════════════════════════════════════════════╝

Design rules (handover spec 2026-07-26, forks resolved by Bruno 2026-07-27):
  - FORK 1/A: separate module. Both v7 and v8 regime fetchers splice the same
    self-contained dict, so a future v8 switch cannot strip this axis the way
    it would have stripped the quadrant.
  - FORK 2/B: the phase NEVER gates eligibility. It caps aggregate duration
    exposure (see PHASE_DURATION_CAPS), modifies stance (apply_phase_to_stance)
    and stretches horizon. Enforcement lives in _regime_post; a badge is
    published on every director pick.
  - FORK 3/A (build): auction_quality is fed by the TreasuryDirect fetcher
    (CLI `fetch-auctions`), scheduled every Saturday BEFORE the weekly routine:
      gcloud scheduler jobs create http cycle-auction-fetch \
        --schedule="0 5 * * 6" --time-zone="Europe/Amsterdam" ...
    fetch_debt_cycle also self-heals: a cache staler than 8 days triggers an
    inline refetch, so a missed Saturday cannot silently zero the gauge.
  - Reserve assets (gold) are a FALSIFICATION CHECK ONLY — never a scored
    input. Scoring gold into a phase that drives buying real assets is a
    momentum loop wearing a macro costume; it would have bought the Jan top.
  - Fail-open on caps: UNKNOWN phase maps to the loosest (EXPANSION) caps and
    no stance modifier. A data outage must never silently tighten the book.

Thresholds are HAND-TUNED PRIORS, exactly like every band in macro_regime.py.
They are not fitted. The _cycle_ledger.jsonl track record is what will
eventually let them be.

Data sources:
  real_long_rate   FRED DFII30 (30y TIPS, keyless CSV); fallback = FMP nominal
                   30y minus FMP `inflationRate` (daily, ~2.3% while CPI ~4% —
                   i.e. market-implied expected inflation, verified 2026-07-27)
  term_premium     FMP treasury-rates history (30y-3m level + 3mo direction)
  auction_quality  TreasuryDirect TA_WS auction results (10y Notes, 30y Bonds)
  debt_service     FRED A091RC1Q027SBEA / W006RC1Q027SBEA (interest ÷ receipts)
  credit_stress    FRED BAMLH0A0HYM2 (HY OAS level + 3mo delta)
  cb_balance_sheet FRED WALCL (Fed total assets, 3mo direction)

All series pass through a GCS last-known-good cache
(gs://screener-signals-carbonbridge/macro/cycle_last_known_good.json) — a
silent outage defaulting every gauge to 0.50 would MANUFACTURE a phase, and a
manufactured phase now touches portfolio caps.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# GCS cache (same bucket/pattern as macro_regime.py; helpers duplicated on
# purpose so this module stays fully standalone — FORK 1/A isolation)
# ---------------------------------------------------------------------------
_GCS_BUCKET = "screener-signals-carbonbridge"
_CYCLE_CACHE_PATH = "macro/cycle_last_known_good.json"
_LOCAL_STATE_FILE = BASE_DIR / "_opus_debate" / "_cycle_state.json"
_LOCAL_AUCTION_FILE = BASE_DIR / "_opus_debate" / "_auction_cache.json"


def _gcs_token():
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def _load_cycle_cache() -> dict:
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return {}
        r = requests.get(
            f"https://storage.googleapis.com/{_GCS_BUCKET}/{_CYCLE_CACHE_PATH}",
            headers={"Authorization": f"Bearer {tok}"}, timeout=5,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"  cycle cache load skipped: {e}")
    return {}


def _save_cycle_cache(cache: dict):
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return
        requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{_GCS_BUCKET}/o",
            params={"uploadType": "media", "name": _CYCLE_CACHE_PATH},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(cache), timeout=10,
        )
    except Exception as e:
        log.debug(f"  cycle cache save skipped: {e}")


# ---------------------------------------------------------------------------
# Raw fetchers (each returns None / [] on failure — caller falls back to cache)
# ---------------------------------------------------------------------------

def _fetch_fred_csv(series_id: str, timeout: int = 15) -> list:
    """FRED keyless CSV download → [(date, value)] oldest-first. '.' rows skipped."""
    try:
        import requests
        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id}, timeout=timeout,
        )
        if r.status_code != 200:
            return []
        out = []
        for row in csv.reader(io.StringIO(r.text)):
            if len(row) != 2 or row[0].lower() in ("date", "observation_date"):
                continue
            try:
                out.append((row[0], float(row[1])))
            except ValueError:
                continue  # '.' = missing observation
        return out
    except Exception as e:
        log.debug(f"  FRED {series_id} fetch failed: {e}")
        return []


def fetch_auction_results(days: int = 370) -> list:
    """TreasuryDirect auction results for 10-Year Notes + 30-Year Bonds.
    Returns [{date, term, btc, indirect_pct}] oldest-first. FORK 3/A fetcher —
    run weekly (Saturday, before the routine) via CLI `fetch-auctions`."""
    rows = []
    try:
        import requests
        for sec_type in ("Note", "Bond"):
            r = requests.get(
                "https://www.treasurydirect.gov/TA_WS/securities/auctioned",
                params={"days": days, "type": sec_type, "format": "json"}, timeout=20,
            )
            if r.status_code != 200:
                continue
            for a in r.json() if isinstance(r.json(), list) else []:
                term = str(a.get("securityTerm") or a.get("term") or "")
                if not (term.startswith("10-") or term.startswith("30-")):
                    continue
                try:
                    btc = float(a.get("bidToCoverRatio") or 0)
                except (TypeError, ValueError):
                    btc = 0.0
                if btc <= 0:
                    continue
                ind_pct = None
                try:
                    ind = float(a.get("indirectBidderAccepted") or 0)
                    tot = float(a.get("totalAccepted") or 0)
                    if tot > 0:
                        ind_pct = ind / tot
                except (TypeError, ValueError):
                    pass
                d = str(a.get("auctionDate") or "")[:10]
                if d:
                    rows.append({"date": d, "term": term[:4].rstrip("-") + "y",
                                 "btc": btc, "indirect_pct": ind_pct})
    except Exception as e:
        log.debug(f"  TreasuryDirect fetch failed: {e}")
    rows.sort(key=lambda x: x["date"])
    return rows


def refresh_auction_cache() -> int:
    """CLI entry for the Saturday job: fetch auctions → GCS cache + local file.
    Returns row count (0 = failed; the classifier then rides last-known-good)."""
    rows = fetch_auction_results()
    if rows:
        cache = _load_cycle_cache()
        cache["AUCTIONS"] = rows
        cache["AUCTIONS_ASOF"] = datetime.now().strftime("%Y-%m-%d")
        _save_cycle_cache(cache)
        try:
            _LOCAL_AUCTION_FILE.parent.mkdir(parents=True, exist_ok=True)
            _LOCAL_AUCTION_FILE.write_text(
                json.dumps({"asof": cache["AUCTIONS_ASOF"], "rows": rows}), encoding="utf-8")
        except Exception:
            pass
    return len(rows)


# ---------------------------------------------------------------------------
# Sub-scores — REMEMBER: higher = later in the cycle / more stress
# ---------------------------------------------------------------------------

SUB_WEIGHTS_CYCLE = {
    "real_long_rate":   0.25,   # the master dial
    "term_premium":     0.20,
    "auction_quality":  0.15,   # the Dalio-specific tell (FORK 3/A)
    "debt_service":     0.15,
    "credit_stress":    0.15,   # the FORCING trigger — delta-weighted
    "cb_balance_sheet": 0.10,   # the MONETIZATION tell
}
assert abs(sum(SUB_WEIGHTS_CYCLE.values()) - 1.0) < 1e-9, \
    f"SUB_WEIGHTS_CYCLE sums to {sum(SUB_WEIGHTS_CYCLE.values())}, must be 1.0"

PHASES = ["EXPANSION", "DISCIPLINE", "FORCING", "MONETIZATION"]


def _score_real_long_rate(real_rate: Optional[float], delta_3m: Optional[float]) -> Optional[float]:
    """30y real rate level, +kicker when rising. ≤0% early-cycle, ≥2.5% = imposed."""
    if real_rate is None:
        return None
    if real_rate <= 0.0:
        s = 0.0
    elif real_rate <= 0.5:
        s = 0.15
    elif real_rate <= 1.0:
        s = 0.35
    elif real_rate <= 1.5:
        s = 0.50
    elif real_rate <= 2.0:
        s = 0.70
    elif real_rate <= 2.5:
        s = 0.85
    else:
        s = 1.00
    if isinstance(delta_3m, (int, float)) and delta_3m > 0.10:
        s += 0.10
    return max(0.0, min(1.0, s))


def _score_term_premium(rates_now: dict, rates_3mo: dict) -> Optional[float]:
    """Long end selling off while the front end is held/rising = the discipline
    signature. A steepening driven by a collapsing front end (easing) is NOT."""
    y30 = rates_now.get("year30")
    m3 = rates_now.get("month3")
    if not isinstance(y30, (int, float)) or not isinstance(m3, (int, float)):
        return None
    spread_bp = (y30 - m3) * 100
    if spread_bp < 0:
        s = 0.10
    elif spread_bp < 50:
        s = 0.30
    elif spread_bp < 100:
        s = 0.50
    elif spread_bp < 150:
        s = 0.70
    else:
        s = 0.90
    y30_p, m3_p = rates_3mo.get("year30"), rates_3mo.get("month3")
    if isinstance(y30_p, (int, float)) and isinstance(m3_p, (int, float)):
        widen_bp = ((y30 - m3) - (y30_p - m3_p)) * 100
        front_move_bp = (m3 - m3_p) * 100
        if widen_bp >= 25 and front_move_bp > -25:
            s += 0.10                       # discipline signature
        elif front_move_bp < -50:
            s -= 0.20                       # easing-driven steepening
    return max(0.0, min(1.0, s))


def _score_auction_quality(auctions: list) -> Optional[float]:
    """Deterioration of the latest 10y/30y auctions vs the trailing 4-auction
    average — bid-to-cover 60%, indirect share 40%. Needs ≥5 auctions."""
    rows = [a for a in (auctions or []) if isinstance(a.get("btc"), (int, float)) and a["btc"] > 0]
    if len(rows) < 5:
        return None
    latest, trail = rows[-1], rows[-5:-1]
    btc_avg = sum(a["btc"] for a in trail) / len(trail)
    ratio = latest["btc"] / btc_avg if btc_avg > 0 else 1.0
    # Bands calibrated on the §8 fixture: a ~5% bid-to-cover slip + ~5pp indirect
    # drift is "demand softening" (~0.6, DISCIPLINE evidence), NOT stress. The
    # FORCING gate needs ≥0.7 — reserved for ratio <0.90 / indirect collapsing.
    if ratio >= 1.02:
        s_btc = 0.20
    elif ratio >= 0.99:
        s_btc = 0.40
    elif ratio >= 0.95:
        s_btc = 0.60
    elif ratio >= 0.90:
        s_btc = 0.75
    else:
        s_btc = 0.90
    ind_trail = [a["indirect_pct"] for a in trail if isinstance(a.get("indirect_pct"), (int, float))]
    if isinstance(latest.get("indirect_pct"), (int, float)) and len(ind_trail) >= 2:
        ind_avg = sum(ind_trail) / len(ind_trail)
        d = latest["indirect_pct"] - ind_avg
        s_ind = 0.25 if d >= 0.01 else (0.45 if d >= -0.03 else (0.65 if d >= -0.07 else 0.85))
        return round(s_btc * 0.6 + s_ind * 0.4, 4)
    return s_btc


def _score_debt_service(ratio: Optional[float]) -> Optional[float]:
    """Net interest ÷ federal receipts. ~7% was the 2004-06 world; >20% is the zone
    where the borrower's arithmetic, not the Fed, sets the agenda."""
    if not isinstance(ratio, (int, float)) or ratio <= 0:
        return None
    if ratio <= 0.08:
        return 0.10
    elif ratio <= 0.12:
        return 0.30
    elif ratio <= 0.16:
        return 0.50
    elif ratio <= 0.20:
        return 0.70
    elif ratio <= 0.25:
        return 0.85
    return 1.00


def _score_credit_stress(oas_now: Optional[float], oas_3mo: Optional[float]) -> Optional[float]:
    """HY OAS — low weight on level, high on delta (spec §3.2). Tight spreads with
    a violent widening is the FORCING tell; wide-but-stable is already priced."""
    if not isinstance(oas_now, (int, float)):
        return None
    lvl = oas_now * 100 if oas_now < 50 else oas_now      # FRED serves percent
    if lvl < 300:
        s_lvl = 0.15
    elif lvl < 400:
        s_lvl = 0.30
    elif lvl < 500:
        s_lvl = 0.50
    elif lvl < 700:
        s_lvl = 0.75
    else:
        s_lvl = 0.95
    if isinstance(oas_3mo, (int, float)):
        prev = oas_3mo * 100 if oas_3mo < 50 else oas_3mo
        d = lvl - prev
        s_d = 0.10 if d <= -50 else (0.40 if d <= 50 else (0.70 if d <= 150 else 1.00))
        return round(s_lvl * 0.5 + s_d * 0.5, 4)
    return s_lvl


def _score_cb_balance_sheet(pct_3m: Optional[float]) -> Optional[float]:
    """Fed total assets, 3-month % change. Expansion into stress/hot inflation is
    the MONETIZATION tell; QT reads early/mid-cycle."""
    if not isinstance(pct_3m, (int, float)):
        return None
    if pct_3m <= -1.0:
        return 0.20
    elif pct_3m < 1.0:
        return 0.40
    elif pct_3m <= 3.0:
        return 0.70
    return 0.90


# ---------------------------------------------------------------------------
# State machine — the part that makes this not-flap
# ---------------------------------------------------------------------------
# Legal single steps. MONETIZATION -> EXPANSION is the cycle reset.
_LEGAL_NEXT = {
    "EXPANSION":    {"DISCIPLINE"},
    "DISCIPLINE":   {"FORCING", "EXPANSION"},
    "FORCING":      {"MONETIZATION", "DISCIPLINE"},
    "MONETIZATION": {"EXPANSION"},
}
HYSTERESIS_PUBLISHES = 2    # target must repeat on N consecutive advances


def _target_phase(cycle_score: float, sub: dict, real_delta_3m: Optional[float]) -> str:
    """Stateless composite → target. Two conditional gates on top of the bands:

    MONETIZATION is an override, not a band: it requires the CB absorbing
    (cb ≥ 0.7) while real rates are pushed DOWN (falling ≥ 0.25pp/3mo) into a
    still-stressed composite — a scalar alone cannot see it.

    FORCING is gated on LIVE funding stress (credit_stress ≥ 0.6 or
    auction_quality ≥ 0.7): FORCING means the market is breaking, and the
    discipline gauges (real rate, term premium, debt service) can max the
    composite past 0.70 while HY OAS sits at 310bp and auctions cover 2.3x —
    that is severe DISCIPLINE, not FORCING. Calibrated against the §8 fixture,
    which brushes 0.70 with calm credit and must read DISCIPLINE."""
    cb = sub.get("cb_balance_sheet")
    if (isinstance(cb, (int, float)) and cb >= 0.7
            and isinstance(real_delta_3m, (int, float)) and real_delta_3m < -0.25
            and cycle_score >= 0.55):
        return "MONETIZATION"
    if cycle_score < 0.35:
        return "EXPANSION"
    if cycle_score >= 0.70 and (sub.get("credit_stress", 0) >= 0.6
                                or sub.get("auction_quality", 0) >= 0.7):
        return "FORCING"
    return "DISCIPLINE"


def _step_toward(current: str, target: str) -> str:
    """One legal step from current toward target (indices; MONETIZATION wraps to
    EXPANSION). Returns current when already there or no legal step helps."""
    if target == current:
        return current
    ci, ti = PHASES.index(current), PHASES.index(target)
    # wrap case: MONETIZATION -> EXPANSION is forward, not 3 steps back
    step = "EXPANSION" if current == "MONETIZATION" else PHASES[ci + 1] if ti > ci else PHASES[ci - 1]
    return step if step in _LEGAL_NEXT[current] else current


def advance_state(state: dict, target: str, asof: str) -> dict:
    """Apply one publish tick: hysteresis (target must repeat HYSTERESIS_PUBLISHES
    consecutive ticks), then at most ONE legal step. Illegal jumps are stepped
    once along the chain and logged via transition_blocked/transition_implied."""
    state = dict(state or {})
    phase = state.get("phase") or "DISCIPLINE"
    if phase not in PHASES:
        phase = "DISCIPLINE"
    weeks = int(state.get("weeks_in_phase") or 0)
    pending, count = state.get("pending_target"), int(state.get("pending_count") or 0)

    blocked, implied = False, None
    if target == phase:
        pending, count = None, 0
        weeks += 1
    else:
        count = count + 1 if pending == target else 1
        pending = target
        if count >= HYSTERESIS_PUBLISHES:
            nxt = _step_toward(phase, target)
            if nxt != target:
                blocked, implied = True, target
            if nxt != phase:
                state["prior_phase"] = phase
                phase, weeks = nxt, 1
                pending, count = (target, count) if blocked else (None, 0)
            else:
                weeks += 1
        else:
            weeks += 1

    state.update({"phase": phase, "weeks_in_phase": weeks,
                  "pending_target": pending, "pending_count": count,
                  "transition_blocked": blocked, "transition_implied": implied,
                  "asof": asof})
    state.setdefault("prior_phase", phase)
    return state


def _load_state(cache: dict) -> dict:
    st = cache.get("STATE")
    if isinstance(st, dict) and st.get("phase") in PHASES:
        return st
    try:
        st = json.loads(_LOCAL_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(st, dict) and st.get("phase") in PHASES:
            return st
    except Exception:
        pass
    # Cold start: DISCIPLINE is a documented PRIOR (2026 tape), not a computation.
    return {"phase": "DISCIPLINE", "weeks_in_phase": 0, "pending_target": None,
            "pending_count": 0, "seeded": True}


def _save_state(cache: dict, state: dict):
    cache["STATE"] = state
    _save_cycle_cache(cache)
    try:
        _LOCAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase → authority: stance modifier + duration caps (single source of truth)
# ---------------------------------------------------------------------------
# HAND-TUNED PRIORS (spec §6.2). UNKNOWN = loosest caps — fail-open, a data
# outage must never tighten the book. real_asset_floor is ADVISORY (memo-level):
# real-asset classification is not deterministic in this codebase yet.
PHASE_DURATION_CAPS = {
    "EXPANSION":    {"story_max": 0.40},
    "DISCIPLINE":   {"story_max": 0.20, "cash_now_min": 0.35},
    "FORCING":      {"story_max": 0.10, "cash_now_min": 0.50},
    "MONETIZATION": {"story_max": 0.35, "real_asset_floor": 0.25},
    "UNKNOWN":      {"story_max": 0.40},
}

_STANCE_ORDER = ["defensive", "balanced", "aggressive"]


def apply_phase_to_stance(stance: str, phase: str) -> tuple[str, str]:
    """Phase modifies the quadrant-derived stance (spec §5.1). Returns
    (effective_stance, note). DISCIPLINE caps at balanced; FORCING floors at
    defensive; MONETIZATION unlocks aggressive even from a RISK_OFF quadrant —
    the combination today's architecture cannot express. UNKNOWN: no-op."""
    s = stance if stance in _STANCE_ORDER else "balanced"
    if phase == "DISCIPLINE" and _STANCE_ORDER.index(s) > 1:
        return "balanced", "DISCIPLINE caps stance at balanced (real rates being imposed)"
    if phase == "FORCING" and _STANCE_ORDER.index(s) > 0:
        return "defensive", "FORCING floors stance at defensive (funding stress live)"
    if phase == "MONETIZATION" and s != "aggressive":
        return "aggressive", "MONETIZATION unlocks aggressive (real assets, hard-asset re-rates)"
    return s, ""


PHASE_HORIZON_MONTHS = {"EXPANSION": 12, "DISCIPLINE": 18, "FORCING": 24,
                        "MONETIZATION": 12, "UNKNOWN": 12}


def duration_bucket(scan_rec: dict, override: Optional[str] = None,
                    override_reason: str = "") -> dict:
    """Deterministic payback-speed label (spec §5.3) — the input to the duration
    caps. Computed from scan fundamentals, NOT assigned by the Director; the
    Director may override WITH a written justification (recorded, badged).

      cash_now     positive FCF and FCF yield ≥ 4%  (p_fcf ≤ 25)
      payback_2_3y positive FCF, yield < 4%
      story        no positive FCF (deviation from spec: no consensus-estimate
                   feed for 'FCF-positive within 8q', so non-FCF-positive is
                   conservatively 'story')
    """
    p_fcf = scan_rec.get("p_fcf")
    fcf_margin = scan_rec.get("fcf_margin")
    if isinstance(p_fcf, (int, float)) and 0 < p_fcf <= 25:
        computed = "cash_now"
    elif (isinstance(p_fcf, (int, float)) and p_fcf > 25) or \
         (isinstance(fcf_margin, (int, float)) and fcf_margin > 0):
        computed = "payback_2_3y"
    else:
        computed = "story"
    out = {"duration_bucket": computed, "duration_bucket_source": "computed"}
    if override in ("cash_now", "payback_2_3y", "story") and override != computed:
        if override_reason.strip():
            out.update({"duration_bucket": override, "duration_bucket_source": "director_override",
                        "duration_bucket_computed": computed,
                        "duration_bucket_override_reason": override_reason.strip()})
        else:
            out["duration_bucket_override_rejected"] = override  # no justification, no override
    return out


# ---------------------------------------------------------------------------
# Reserve-asset falsification check — NEVER a scored input (spec §3.3)
# ---------------------------------------------------------------------------

def reserve_asset_check(phase: str, gold_now: Optional[float],
                        gold_6mo: Optional[float]) -> dict:
    if not isinstance(gold_now, (int, float)) or not isinstance(gold_6mo, (int, float)) or gold_6mo <= 0:
        return {"consistent_with_phase": None, "note": "gold data unavailable — check skipped"}
    chg = (gold_now - gold_6mo) / gold_6mo
    if phase in ("DISCIPLINE", "FORCING"):
        if chg <= 0.05:
            return {"consistent_with_phase": True,
                    "note": f"gold {chg:+.0%} over 6mo — consistent with successfully imposed positive real rates"}
        return {"consistent_with_phase": False,
                "note": f"gold {chg:+.0%} over 6mo while phase reads {phase} — phase call may be LATE; "
                        f"raise a falsifier for RegimeRead, do not change the score"}
    if phase == "MONETIZATION":
        if chg >= 0.0:
            return {"consistent_with_phase": True, "note": f"gold {chg:+.0%} over 6mo — consistent with monetization"}
        return {"consistent_with_phase": False,
                "note": f"gold {chg:+.0%} over 6mo contradicts MONETIZATION — phase call may be EARLY"}
    return {"consistent_with_phase": True, "note": f"gold {chg:+.0%} over 6mo — no strong prior in {phase}"}


# ---------------------------------------------------------------------------
# Core computation (pure — testable against the §8 fixture with no network)
# ---------------------------------------------------------------------------

def compute_debt_cycle(inputs: dict, state: dict, asof: str, advance: bool = False) -> dict:
    """inputs keys (any may be None/missing → that gauge scores neutral 0.5 and
    is flagged in sub_sources as 'missing'):
      real_rate, real_delta_3m, rates_now{}, rates_3mo{}, auctions[],
      debt_service_ratio, oas_now, oas_3mo, cb_pct_3m, gold_now, gold_6mo
    """
    raw = {
        "real_long_rate":   _score_real_long_rate(inputs.get("real_rate"), inputs.get("real_delta_3m")),
        "term_premium":     _score_term_premium(inputs.get("rates_now") or {}, inputs.get("rates_3mo") or {}),
        "auction_quality":  _score_auction_quality(inputs.get("auctions") or []),
        "debt_service":     _score_debt_service(inputs.get("debt_service_ratio")),
        "credit_stress":    _score_credit_stress(inputs.get("oas_now"), inputs.get("oas_3mo")),
        "cb_balance_sheet": _score_cb_balance_sheet(inputs.get("cb_pct_3m")),
    }
    sub_sources = {k: ("live" if v is not None else "missing") for k, v in raw.items()}
    sub = {k: (v if v is not None else 0.5) for k, v in raw.items()}
    live_n = sum(1 for s in sub_sources.values() if s == "live")
    confidence = "high" if live_n >= 5 else ("med" if live_n >= 3 else "low")

    cycle_score = sum(sub[k] * SUB_WEIGHTS_CYCLE[k] for k in SUB_WEIGHTS_CYCLE)
    target = _target_phase(cycle_score, sub, inputs.get("real_delta_3m"))

    if advance:
        state = advance_state(state, target, asof)
    phase = state.get("phase") or "UNKNOWN"

    rn = inputs.get("rates_now") or {}
    tp_bp = ((rn.get("year30") or 0) - (rn.get("month3") or 0)) * 100 if rn else None
    basis_bits = []
    if inputs.get("real_rate") is not None:
        d = inputs.get("real_delta_3m")
        basis_bits.append(f"real 30y {inputs['real_rate']:.2f}%"
                          + (f" ({'rising' if d and d > 0 else 'falling' if d and d < 0 else 'flat'})" if d is not None else ""))
    if tp_bp:
        basis_bits.append(f"30y-3m {tp_bp:+.0f}bp")
    if sub_sources["auction_quality"] == "live":
        basis_bits.append(f"auction demand score {sub['auction_quality']:.2f}")
    if sub_sources["debt_service"] == "live":
        basis_bits.append(f"interest/receipts score {sub['debt_service']:.2f}")

    detail = {
        "EXPANSION":    "Borrowing accommodated. Duration and growth carry normally.",
        "DISCIPLINE":   "Positive real long rates being imposed and holding. Duration punished, cash flow rewarded. Real assets not yet.",
        "FORCING":      "Funding stress live. Balance sheet and FCF carry only; reaches suspended.",
        "MONETIZATION": "Real rates forced down while the CB absorbs. Real assets and pricing power lead.",
    }.get(phase, "Phase unknown — no stance modifier, loosest duration caps (fail-open).")

    return {
        "debt_cycle_phase": phase,
        "prior_phase": state.get("prior_phase", phase),
        "weeks_in_phase": int(state.get("weeks_in_phase") or 0),
        "cycle_score": round(cycle_score, 4),
        "cycle_target": target,
        "transition_blocked": bool(state.get("transition_blocked")),
        "transition_implied": state.get("transition_implied"),
        "pending_target": state.get("pending_target"),
        "pending_count": int(state.get("pending_count") or 0),
        "confidence": confidence,
        "seeded": bool(state.get("seeded")),
        "phase_basis": " x ".join(basis_bits) or "insufficient live data",
        "cycle_sub_scores": {k: round(v, 4) for k, v in sub.items()},
        "cycle_sub_sources": sub_sources,
        "reserve_asset_check": reserve_asset_check(phase, inputs.get("gold_now"), inputs.get("gold_6mo")),
        "phase_detail": detail,
        "duration_caps": PHASE_DURATION_CAPS.get(phase, PHASE_DURATION_CAPS["UNKNOWN"]),
        "expected_horizon_months": PHASE_HORIZON_MONTHS.get(phase, 12),
        "asof": asof,
    }, state


_UNKNOWN_RESULT = {
    "debt_cycle_phase": "UNKNOWN", "fallback": True, "cycle_score": None,
    "confidence": "low", "cycle_sub_scores": {}, "phase_basis": "classifier failed",
    "phase_detail": "Phase unknown — no stance modifier, loosest duration caps (fail-open).",
    "duration_caps": PHASE_DURATION_CAPS["UNKNOWN"], "expected_horizon_months": 12,
    "weeks_in_phase": 0, "transition_blocked": False, "transition_implied": None,
    "reserve_asset_check": {"consistent_with_phase": None, "note": "n/a"},
}


# ---------------------------------------------------------------------------
# LIVE gather + classify
# ---------------------------------------------------------------------------

def _gather_inputs(fmp_func, cache: dict, as_of: Optional[str] = None) -> dict:
    """Collect raw series (live) with GCS last-known-good fallback per series.
    as_of set = historical mode with publication-lag guards:
      debt_service +45d · cb_balance_sheet +7d · auctions +1d · market series same-day."""
    today = datetime.now() if not as_of else datetime.strptime(as_of, "%Y-%m-%d")
    cutoff = today.strftime("%Y-%m-%d")

    def cached_series(key: str, fresh: list) -> list:
        if fresh:
            cache[key] = fresh
            return fresh
        got = cache.get(key) or []
        if got:
            log.warning(f"  cycle {key}: live fetch empty, using last-known-good ({len(got)} rows)")
        return got

    def lagged(series: list, lag_days: int) -> list:
        if not as_of:
            return series
        lim = (today - timedelta(days=lag_days)).strftime("%Y-%m-%d")
        return [x for x in series if str(x[0] if isinstance(x, (list, tuple)) else x.get("date"))[:10] <= lim]

    def latest_before(series: list, days_back: int) -> Optional[float]:
        tgt = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        prior = [v for d, v in series if d <= tgt]
        return prior[-1] if prior else None

    # FRED series (market ones same-day; slow ones lag-guarded in historical mode)
    tips = lagged(cached_series("DFII30", _fetch_fred_csv("DFII30")), 0)
    oas = lagged(cached_series("BAMLH0A0HYM2", _fetch_fred_csv("BAMLH0A0HYM2")), 0)
    walcl = lagged(cached_series("WALCL", _fetch_fred_csv("WALCL")), 7)
    interest = lagged(cached_series("FYINT_Q", _fetch_fred_csv("A091RC1Q027SBEA")), 45)
    receipts = lagged(cached_series("FYREC_Q", _fetch_fred_csv("W006RC1Q027SBEA")), 45)
    tips = [x for x in tips if x[0] <= cutoff]
    oas = [x for x in oas if x[0] <= cutoff]

    # Treasury rates now + ~3mo ago (FMP)
    rates_now, rates_3mo = {}, {}
    infl_now = infl_3mo = None
    if fmp_func:
        try:
            frm = (today - timedelta(days=110)).strftime("%Y-%m-%d")
            tr = fmp_func("treasury-rates", {"from": frm, "to": cutoff}) or []
            tr = [r for r in tr if str(r.get("date", ""))[:10] <= cutoff]
            if tr:
                tr.sort(key=lambda r: r.get("date", ""), reverse=True)
                rates_now = tr[0]
                rates_3mo = tr[-1]
            ir = fmp_func("economic-indicators", {"name": "inflationRate", "from": frm, "to": cutoff}) or []
            ivals = sorted([(str(d.get("date"))[:10], float(d["value"])) for d in ir if d.get("value")],
                           reverse=True)
            if ivals:
                infl_now = ivals[0][1]
                infl_3mo = ivals[-1][1]
        except Exception as e:
            log.debug(f"  cycle FMP fetch failed: {e}")

    # Real 30y: FRED TIPS primary, nominal-minus-expected-inflation proxy fallback
    real_rate = real_delta = None
    if tips:
        real_rate = tips[-1][1]
        p = latest_before(tips, 90)
        real_delta = (real_rate - p) if p is not None else None
    elif isinstance(rates_now.get("year30"), (int, float)) and infl_now is not None:
        real_rate = rates_now["year30"] - infl_now
        if isinstance(rates_3mo.get("year30"), (int, float)) and infl_3mo is not None:
            real_delta = real_rate - (rates_3mo["year30"] - infl_3mo)

    # Auctions: cache (Saturday job) with self-heal when stale >8d (live mode only)
    auctions = cache.get("AUCTIONS") or []
    if not as_of:
        stale = True
        try:
            stale = (datetime.now() - datetime.strptime(cache.get("AUCTIONS_ASOF", "2000-01-01"),
                                                        "%Y-%m-%d")).days > 8
        except Exception:
            pass
        if stale:
            fresh = fetch_auction_results()
            if fresh:
                auctions = fresh
                cache["AUCTIONS"] = fresh
                cache["AUCTIONS_ASOF"] = datetime.now().strftime("%Y-%m-%d")
    else:
        lim = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        auctions = [a for a in auctions if a.get("date", "") <= lim]

    # Debt service ratio: latest quarter where both series exist
    ds_ratio = None
    if interest and receipts:
        rec_by_d = dict(receipts)
        for d, v in reversed(interest):
            if d in rec_by_d and rec_by_d[d] > 0:
                ds_ratio = v / rec_by_d[d]
                break

    # OAS now + 3mo
    oas_now = oas[-1][1] if oas else None
    oas_3mo = latest_before(oas, 90) if oas else None

    # CB balance sheet 3-month % change
    cb_pct = None
    if walcl:
        now_v = walcl[-1][1]
        p = latest_before(walcl, 90)
        if p and p > 0:
            cb_pct = (now_v - p) / p * 100

    # Gold (falsification check only) — FMP GCUSD quote + 6mo-ago close
    gold_now = gold_6mo = None
    if fmp_func and not as_of:
        try:
            q = fmp_func("quote", {"symbol": "GCUSD"}) or []
            if q and isinstance(q, list):
                gold_now = float(q[0].get("price") or 0) or None
            h = fmp_func("historical-price-eod/full", {
                "symbol": "GCUSD",
                "from": (today - timedelta(days=200)).strftime("%Y-%m-%d"),
                "to": (today - timedelta(days=170)).strftime("%Y-%m-%d")}) or []
            if h and isinstance(h, list):
                gold_6mo = float(h[0].get("close") or 0) or None
        except Exception as e:
            log.debug(f"  cycle gold fetch failed: {e}")

    return {"real_rate": real_rate, "real_delta_3m": real_delta,
            "rates_now": rates_now, "rates_3mo": rates_3mo, "auctions": auctions,
            "debt_service_ratio": ds_ratio, "oas_now": oas_now, "oas_3mo": oas_3mo,
            "cb_pct_3m": cb_pct, "gold_now": gold_now, "gold_6mo": gold_6mo}


def fetch_debt_cycle(fmp_func=None, advance: bool = False) -> dict:
    """LIVE debt-cycle read. advance=True ONLY from the weekly publish
    (_write_macro_regime) — read-only callers (e.g. /macro) must not tick
    weeks_in_phase or the hysteresis counters. Fail-soft: hard failure returns
    UNKNOWN with the loosest caps and no stance modifier (fail-open, §3.7)."""
    try:
        asof = datetime.now().strftime("%Y-%m-%d")
        cache = _load_cycle_cache()
        inputs = _gather_inputs(fmp_func, cache)
        state = _load_state(cache)
        result, state = compute_debt_cycle(inputs, state, asof, advance=advance)
        if advance:
            _save_state(cache, state)      # persists cache series refreshes too
        else:
            _save_cycle_cache(cache)
        log.info(f"  Debt cycle: {result['debt_cycle_phase']} "
                 f"(score={result['cycle_score']}, target={result['cycle_target']}, "
                 f"weeks={result['weeks_in_phase']}, conf={result['confidence']})")
        return result
    except Exception as e:
        log.warning(f"  Debt cycle classifier failed (fail-open UNKNOWN): {e}")
        return dict(_UNKNOWN_RESULT, asof=datetime.now().strftime("%Y-%m-%d"))


def fetch_debt_cycle_historical(fmp_func, as_of_date: str) -> dict:
    """Backtest-safe read: publication-lag guards on the slow series, NO state
    advance (the state machine is a live-forward object; a backtest re-deriving
    phase history should replay compute_debt_cycle over its own state)."""
    try:
        cache = _load_cycle_cache()
        inputs = _gather_inputs(fmp_func, cache, as_of=as_of_date)
        state = _load_state(cache)
        result, _ = compute_debt_cycle(inputs, state, as_of_date, advance=False)
        return result
    except Exception as e:
        log.warning(f"  Debt cycle historical failed (fail-open UNKNOWN): {e}")
        return dict(_UNKNOWN_RESULT, asof=as_of_date)


# ---------------------------------------------------------------------------
# CLI:  python debt_cycle.py                → live read (no state advance)
#       python debt_cycle.py fetch-auctions → Saturday job (TreasuryDirect → GCS)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "fetch-auctions" in sys.argv:
        n = refresh_auction_cache()
        print(f"auction cache refresh: {n} rows" + ("" if n else " (FAILED — riding last-known-good)"))
        sys.exit(0 if n else 1)
    fmp = None
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import fmp  # noqa: F401
    except Exception:
        print("screener_v6.fmp unavailable — FRED-only read")
    r = fetch_debt_cycle(fmp, advance="--advance" in sys.argv)
    print(json.dumps(r, indent=2))
