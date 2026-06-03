#!/usr/bin/env python3
"""
live_director_agent.py — Speculair Apex PM & Basket Allocator (Tier 2)
=====================================================================
Receives 9 per-methodology baskets from Tier 1 debates.
Runs a single cross-sectional Director LLM call to select the
ultimate Speculair Apex Basket (5-7 tickers).

Includes:
  - Red flag computation from live FMP financials
  - Auto-veto gate (≥3 red flags → conviction 2.0, bypass LLM)
  - Director PM cross-sectional triage (claude-opus-4-7 via Anthropic SDK)
  - Sector concentration cap (hard ≤3 per sector, soft warning at 2+)
  - Execution memo generation
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DirectorAgent] %(message)s")
log = logging.getLogger("live_director")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
CACHE_DIR = BASE_DIR / "debate_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DIRECTOR_CACHE_FILE = CACHE_DIR / "director_decisions.json"

# ── API Key Loading ──────────────────────────────────────────────────────
def _load_keys():
    env_path = FRONTEND_DIR / ".env.local"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().replace('"', '').replace("'", "")

def _key(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        _load_keys()
        val = os.environ.get(name, "")
    return val


# ── Red Flag Computation ─────────────────────────────────────────────────
def compute_red_flags(symbol: str) -> dict:
    """Compute 5 red flags from live FMP financial data.
    
    Flags:
    1. Revenue Decline: revenue YoY < 0
    2. Debt Acceleration: LT debt growth > 20% YoY
    3. Margin Compression: net margin dropped > 5pp YoY
    4. Capital Destruction: ROIC < 5%
    5. Earnings Evasiveness: (qualitative — from debate results)
    """
    fmp_key = _key("FMP_API_KEY")
    if not fmp_key:
        return {"flags": {}, "total_active": 0}
    
    flags = {
        "revenue_decline": False,
        "debt_acceleration": False,
        "margin_compression": False,
        "capital_destruction": False,
        "earnings_evasiveness": False,
    }
    
    try:
        # Fetch key metrics (TTM)
        url = "https://financialmodelingprep.com/stable/key-metrics"
        r = requests.get(url, params={"symbol": symbol, "period": "annual",
                                      "limit": 2, "apikey": fmp_key}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) >= 1:
                latest = data[0]
                roic = latest.get("roic") or latest.get("returnOnCapitalEmployed")
                if roic is not None and roic < 0.05:
                    flags["capital_destruction"] = True
        
        # Fetch income statement for revenue/margin checks
        url = "https://financialmodelingprep.com/stable/income-statement"
        r = requests.get(url, params={"symbol": symbol, "period": "annual",
                                      "limit": 2, "apikey": fmp_key}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) >= 2:
                curr = data[0]
                prev = data[1]
                
                # Revenue decline
                curr_rev = curr.get("revenue", 0) or 0
                prev_rev = prev.get("revenue", 0) or 0
                if prev_rev > 0 and curr_rev < prev_rev:
                    flags["revenue_decline"] = True
                
                # Margin compression (>5pp drop)
                curr_margin = (curr.get("netIncome", 0) or 0) / curr_rev if curr_rev > 0 else 0
                prev_margin = (prev.get("netIncome", 0) or 0) / prev_rev if prev_rev > 0 else 0
                if (prev_margin - curr_margin) > 0.05:
                    flags["margin_compression"] = True
        
        # Fetch balance sheet for debt check
        url = "https://financialmodelingprep.com/stable/balance-sheet-statement"
        r = requests.get(url, params={"symbol": symbol, "period": "annual",
                                      "limit": 2, "apikey": fmp_key}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) >= 2:
                curr_debt = data[0].get("longTermDebt", 0) or 0
                prev_debt = data[1].get("longTermDebt", 0) or 0
                if prev_debt > 0 and curr_debt > 0:
                    debt_growth = (curr_debt - prev_debt) / prev_debt
                    if debt_growth > 0.20:
                        flags["debt_acceleration"] = True
    
    except Exception as e:
        log.warning(f"Red flag computation for {symbol} failed: {e}")
    
    # Sleep to respect FMP rate limits
    time.sleep(0.15)
    
    return {
        "flags": flags,
        "total_active": sum(flags.values()),
    }


def add_evasiveness_flag(red_flags: dict, debate_result: dict) -> dict:
    """Check debate results for earnings evasiveness indicators."""
    conclusion = str(debate_result.get("moderator_conclusion", "")).lower()
    bear = str(debate_result.get("bear_thesis", "")).lower()
    findings = str(debate_result.get("interrogator_findings", "")).lower()
    
    evasive_words = ["defensive", "evasive", "deflect", "obfuscate", "vague",
                     "non-answer", "redirect", "avoid"]
    if any(w in conclusion or w in bear or w in findings for w in evasive_words):
        red_flags["flags"]["earnings_evasiveness"] = True
        red_flags["total_active"] = sum(red_flags["flags"].values())
    
    return red_flags


# ── Director System Prompt ───────────────────────────────────────────────
DIRECTOR_SYSTEM_PROMPT = """You are the Apex Portfolio Manager & Chief Risk Officer for the Speculair high-performance, alpha-seeking stock selection system. You allocate REAL capital. Your mandate is pure Relative Capital Allocation, Opportunity Cost, and Temporal Arbitrage. Capital is strictly finite — you pit the provided equities against one another in a zero-sum competition.

You are given the FULL scored & gated candidate universe: every name that passed the screener's quantitative gates AND survived the multi-agent debate pipeline. For EACH name your analyst team has produced a complete dossier:
- A forensic INTERROGATOR DOSSIER — an 8-quarter transcript analysis cross-referenced against the actual financials (narrative arc, claims-vs-financials, tone trajectory, guidance credibility, red/green flags, a capital-allocation verdict). This is deep work — trust and USE it.
- The ARCHITECT's full Bull and Bear theses.
- The MODERATOR's (CRO) consensus delta, valley of death, positioning washout, and forcing function.
- The VALUATION MATRIX: the fair-value and margin-of-safety that each of the 9 methodologies assigns the name.
- The hard FINANCIALS (growth, margins, returns, leverage, earnings-beat rate, multi-year trajectory) and ANALYST consensus where available.
- A MACRO regime brief and the name's SECTOR MOMENTUM.

DO NOT re-derive the per-stock forensic work — your team already did it. Your unique job is the work only a portfolio manager can do:

1. CROSS-SECTIONAL COMPETITION. Rank every name against every other. Capital given to one name is denied to all others, so a "good" name must lose to a "great" one. Explicitly reason about why each chosen name beat the names you discarded.

2. VALUATION REALISM. For each name, look across the 9 methods' fair-value estimates. Is the implied upside REALISTIC, or an artifact of one aggressive method? Triangulate: a name cheap on 6 of 9 methods is far more robust than one cheap on 1. Compare the methods' fair value to the current price AND to analyst consensus where provided — where the screener and the street disagree, decide who is right using the dossier evidence.

3. TIMING. Weigh the forcing function (the catalyst's hard date) against the valley of death (what breaks in the next 3-9 months). A real thesis with a catalyst >6-9 months out, or a lethal near-term air-pocket, is "dead money" — push it to the watchlist, not the basket.

4. MACRO & SECTOR FIT. Use the macro brief and sector momentum as a tailwind/headwind overlay; do not cluster the basket on a single macro bet.

5. PORTFOLIO CONTINUITY & ROTATION. You manage a LIVE, tracked basket — its performance is measured from each position's entry date. You are NOT building from scratch each cycle. Your CURRENT LIVE BASKET (existing holdings with entry date/price and P&L) is provided below when it exists. Each cycle:
   - HOLD by default. A current holding stays unless its thesis is now broken (the latest dossier shows deterioration that invalidates the original case) OR a candidate is clearly superior and you are at your conviction-justified capacity.
   - ROTATE with discipline. Only drop a holding for a new name when that name is MEANINGFULLY better than your weakest holding — never on marginal differences. Churn destroys the track record and incurs cost. When you rotate, name the holding you dropped and why, and the name you added and why it won the seat.
   - ADD a genuinely new high-conviction name even without a drop, if the basket has room within your conviction-driven size.
   - Re-score held names with the latest dossier, but you are deciding HOLD vs SELL — they keep their original entry.
   Bias toward LOW turnover: a great business you already own beats a marginally-better new one.

6. FUNDAMENTAL-MOMENTUM SLEEVE (distinct lens). Some candidates are surfaced by the FUNDAMENTAL_MOMENTUM basket (check source_methodologies) — physical hard-tech growth leaders (AI/semiconductors, nuclear/SMR, robotics, rare-earth, defence, electrification) screened on growth + acceleration + analyst-revision velocity + quality (ROIC), NOT margin of safety. The intrinsic models CANNOT price their growth, so they will show little or NEGATIVE MoS in the valuation matrix — DO NOT penalise them for that; the value lens does not apply. Judge them instead on: (a) is the growth real, accelerating, and durable; (b) is the priced-in expectation BEATABLE — reverse-DCF: what CAGR does the multiple imply, and is it conservative versus the trajectory; (c) is the analyst-revision trend up. They are a distinct growth sleeve competing on growth-asymmetry, not cheapness. Apply the same TIMING/MACRO discipline.

Hard vetoes to apply during your internal cull:
- "Priced In": kill trades the street already models with an expanded multiple — EXCEPT for FUNDAMENTAL_MOMENTUM names, where an expanded multiple is expected: kill only if growth is NOT accelerating ahead of that multiple.
- "Valley of Death": kill trades facing a cash-burn hump, maturity wall, or forced liquidation before the catalyst.
- "Dead Money": kill trades whose forcing function is >6-9 months away.

Then build the Speculair Apex Basket: choose **BETWEEN 2 AND 20 names — your own count, driven purely by conviction**. Concentrate in 2 if only 2 are genuinely worthy; spread to 20 if that many are genuinely asymmetric. DO NOT pad to a quota, DO NOT pick one-per-methodology, DO NOT force a fixed size. Hold no more than 3 names in any one sector.

Score EVERY apex pick with a CONTINUOUS conviction 0-100:
  90-100 = table-pounding, maximal asymmetry, catalyst imminent
  70-89  = high-conviction aggressive entry
  50-69  = solid, included but sized smaller
  below 50 = do NOT place in the apex basket (use the watchlist instead)
Your conviction drives position sizing downstream — rank honestly.

Return a valid JSON object matching this schema EXACTLY:
{
  "memo": "string — the Final Execution Memo (format below)",
  "basket": [
    {"symbol": "TICKER", "conviction": <integer 0-100>, "rationale": "your full reasoning: the consensus delta, the forcing function, why the cross-method valuation is realistic, and why this beat the discarded peers"}
  ],
  "watchlist": [
    {"symbol": "TICKER", "conviction": <integer 0-100>, "trigger": "the exact capitulation event or price point that activates the buy order"}
  ]
}
- "basket" MUST contain between 2 and 20 entries — the Speculair Apex Basket.
- "watchlist" contains 0 to 8 generational-but-bad-near-term-timing setups.
- rationale and memo have NO length limit — this is a real capital-allocation decision; be as thorough as it deserves.

The "memo" must contain:
1. THE SPECULAIR APEX BASKET: per apex name — its Consensus Delta + Forcing Function + why its cross-method valuation is realistic + why it beat discarded peers.
2. THE CAPITULATION WATCHLIST: the exact capitulation event/price for each.
3. THE GRAVEYARD: no tickers — a sharp post-mortem on why the discarded majority lost the competition.
4. MACRO & PORTFOLIO POSTURE: how the macro regime shaped the basket and how you avoided clustering risk.

Output ONLY the raw JSON object. No markdown or code fences outside the JSON.
"""


# ── Director LLM Call ────────────────────────────────────────────────────
def _query_director(prompt: str, max_attempts: int = 4) -> Optional[dict]:
    """Run Director LLM call via Anthropic claude-opus-4-7.
    
    Uses JSON pre-filling (assistant message starts with '{') to ensure
    structured JSON output without markdown wrapping.
    """
    api_key = _key("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found for Director")
        return None
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        # 1M context: the director ingests the full per-name dossiers for the whole
        # debated universe (can run 500K-900K input tokens) for true cross-sectional ranking.
        "anthropic-beta": "context-1m-2025-08-07",
    }
    payload = {
        "model": "claude-opus-4-8",
        "max_tokens": 24000,            # uncapped memo + per-pick rationale across up to 20 names
        # NOTE: temperature omitted (deprecated on opus-4-x; deterministic enough here).
        "system": DIRECTOR_SYSTEM_PROMPT,
        "messages": [
            # opus does not support assistant-message prefill — end on a user message and
            # extract the JSON object defensively below.
            {"role": "user", "content": prompt + "\n\nRespond with ONLY the JSON object, "
                                                 "starting with { and ending with }. No prose, no code fences."},
        ],
    }

    for attempt in range(max_attempts):
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers, json=payload, timeout=600
            )
            rj = r.json()
            if rj.get("type") == "error":
                err_msg = rj.get("error", {}).get("message", str(rj))
                err_type = rj.get("error", {}).get("type", "unknown")
                if "rate" in err_msg.lower() or "overloaded" in err_msg.lower():
                    sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                    log.warning(f"Director rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                    time.sleep(sleep)
                    continue
                log.error(f"Director API error (type={err_type}): {err_msg}")
                time.sleep(3.0)
                continue
            
            # Extract text from Anthropic response
            content_blocks = rj.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text += block.get("text", "")
            
            # Defensive parse: strip code fences, then extract the outermost {...}
            text = text.strip()
            if text.startswith("```"):
                blocks = text.split("```")
                text = max(blocks, key=len)               # largest fenced block
                if text.lstrip().lower().startswith("json"):
                    text = text.lstrip()[4:]
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end + 1]
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            log.error(f"Director JSON parse error: {e}")
            time.sleep(3.0)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                log.warning(f"Director rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                time.sleep(sleep)
            else:
                log.error(f"Director error: {e}")
                time.sleep(3.0)
    return None


# ── Deterministic G1-G4 Contract Rules ────────────────────────────────────
# Apex inclusion threshold on the 0-100 continuous conviction scale.
# Director picks scoring below this are demoted to the Capitulation Watchlist.
APEX_CONVICTION_FLOOR = 50

# Minimum years of fundamental history to enter the director pool / apex. Matches the
# earnings-methods G2a gate. Unknown history is treated as INSUFFICIENT — a recent-IPO /
# de-SPAC name (one noisy annual statement) must not default through as long-history.
MIN_YEARS_HISTORY = 5

# Deep-value / no-growth methodologies. The G3b iv15-no-growth-IV agreement check is only
# meaningful for names THESE surfaced ("is it cheap assuming no growth?"). For growth-sourced
# names, iv15_nogrowth_agreement=False is the expected/normal case and must NOT veto them
# (otherwise every growth/turnaround pick — DXC, WKL.AS, VOW3.DE — is excluded from the apex).
_NO_GROWTH_METHODS = {"epv", "iv15_deep_value"}

def apply_contract_rules(cand: dict, conviction: int) -> Optional[int]:
    """Apply deterministic G1-G4 contract rules on a 0-100 conviction score.

    G2/G3/G4 are HARD EXCLUSIONS → return None (drop the name from any basket).
    G1 (Peak Cycle) is a soft cap → conviction capped just below the apex floor
    so the name is demoted to the Capitulation Watchlist rather than excluded.

    Returns the (possibly capped) 0-100 conviction, or None to exclude entirely.
    """
    symbol = cand.get("symbol", "")
    cycle = cand.get("cycle_flag", "NORMAL")
    sb = cand.get("structural_break", False)
    yrs = cand.get("years_history")
    if yrs is None:
        yrs = 0  # unknown history → treat as insufficient (never a free pass via a 99 default)
    feg = cand.get("forward_eps_growth", 0.0)
    iv_agree = cand.get("iv15_nogrowth_agreement", True)

    # G4 check: all source methodologies must be applicable
    source_meths = cand.get("source_methodologies", [])
    meth_app_dict = cand.get("methodology_applicable", {})
    all_inapplicable = len(source_meths) > 0 and all(not meth_app_dict.get(m, True) for m in source_meths)

    # G2, G3, G4 are hard exclusions (G2a = minimum fundamental history)
    if sb or yrs < MIN_YEARS_HISTORY:
        log.info(f"  [Contract Gate] {symbol} EXCLUDED (G2: structural_break={sb}, years={yrs} < {MIN_YEARS_HISTORY})")
        return None
    # G3a: forward-declining earnings is always a hard veto.
    if feg <= -0.10:
        log.info(f"  [Contract Gate] {symbol} EXCLUDED (G3a: forward_eps_growth={feg} <= -0.10)")
        return None
    # G3b: iv15 no-growth-IV disagreement. Originally vetoed ANY name a no-growth method
    # surfaced — but that nuked growing, cross-method-supported names (HRMY, DXC) whose
    # iv15_nogrowth_agreement=False is the expected/normal case. Tightened (June 2026):
    # veto only when the no-growth disagreement is the WHOLE story — the name is PURELY
    # no-growth-sourced (no growth/convergence cross-support) OR is actually declining
    # (forward growth < 0). A growing name with support from a growth or convergence
    # method is trusted — the same cross-method principle as the convergence basket.
    if (not iv_agree) and any(m in _NO_GROWTH_METHODS for m in source_meths):
        has_growth_support = any(m not in _NO_GROWTH_METHODS for m in source_meths)
        if (not has_growth_support) or (feg < 0.0):
            log.info(f"  [Contract Gate] {symbol} EXCLUDED (G3b: no-growth-sourced + iv15 disagreement; growth_support={has_growth_support}, feg={feg})")
            return None
        log.info(f"  [Contract Gate] {symbol} G3b softened — kept (growth/cross-method support, feg={feg}); iv15 disagreement not disqualifying")
    if all_inapplicable:
        log.info(f"  [Contract Gate] {symbol} EXCLUDED (G4: all source methodologies inapplicable: {meth_app_dict})")
        return None

    final_conv = max(0, min(100, int(conviction)))

    # G1: Peak Cycle → demote below the apex floor (lands on Watchlist, not excluded)
    if cycle == "PEAK_CYCLE" and final_conv >= APEX_CONVICTION_FLOOR:
        log.info(f"  [Contract Gate] {symbol} capped below apex floor (G1: PEAK_CYCLE)")
        final_conv = APEX_CONVICTION_FLOOR - 1

    return final_conv


# ── Main Director Allocation ─────────────────────────────────────────────
def run_director_allocation(tier1_baskets: dict, dry_run: bool = False,
                            macro_brief: str = "", current_basket: dict = None) -> dict:
    """Run Tier 2 Director allocation across all methodology baskets.

    Args:
        tier1_baskets: dict of methodology_key → basket from Tier 1
        dry_run: if True, skip LLM call and use conviction-based fallback
        macro_brief: optional once-per-scan macro regime brief prepended to the prompt
        current_basket: optional {symbol: {entry_date, entry_price, conviction}} of the
            LIVE held positions — fed to the director for hold/rotate decisions, and used
            to preserve entry date/price for held names so the track record continues.

    Returns dict with apex_basket, capitulation_watchlist, director_memo
    """
    current_basket = current_basket or {}
    log.info("=" * 60)
    log.info("TIER 2: APEX PM & BASKET ALLOCATOR")
    log.info("=" * 60)
    
    # 1. Collect all unique candidates across methodologies
    all_candidates = {}  # symbol → merged candidate dict
    for meth_key, basket in tier1_baskets.items():
        for pick in basket.get("picks", []):
            sym = pick.get("symbol", "")
            if not sym:
                continue
            if sym not in all_candidates:
                all_candidates[sym] = {
                    "symbol": sym,
                    "conviction": pick.get("conviction", 0),
                    "source_methodologies": [meth_key],
                    "interrogator_dossier": pick.get("interrogator_dossier", "") or pick.get("interrogator_findings", ""),
                    "trajectory": pick.get("trajectory", ""),
                    "bull_thesis": pick.get("bull_thesis", ""),
                    "bear_thesis": pick.get("bear_thesis", ""),
                    "moderator_conclusion": pick.get("moderator_conclusion", ""),
                    "consensus_delta": pick.get("consensus_delta", ""),
                    "valley_of_death": pick.get("valley_of_death", ""),
                    "positioning_washout": pick.get("positioning_washout", ""),
                    "forcing_function": pick.get("forcing_function", ""),
                    "verdict": pick.get("verdict", ""),
                    "interrogator_score": pick.get("interrogator_score", 3),
                    "price": pick.get("price", 0),
                    "sector": pick.get("sector", ""),
                    "signal_type": pick.get("signal_type", "none"),
                    "mos": {meth_key: pick.get("mos", "N/A")},
                    "fair_value": {meth_key: pick.get("fair_value", "N/A")},
                    # convergence (10th basket) cross-method agreement — symbol-constant,
                    # so first-seen capture is correct (no per-basket merge needed):
                    "consensus_agreement": pick.get("consensus_agreement"),
                    "consensus_votes": pick.get("consensus_votes"),
                    # CONTRACT fields from screener:
                    "cycle_flag": pick.get("cycle_flag", "NORMAL"),
                    "peak_margin_sigma": pick.get("peak_margin_sigma", 0.0),
                    "norm_scale": pick.get("norm_scale", 1.0),
                    "mos_source": pick.get("mos_source", ""),
                    "years_history": pick.get("years_history", 99),
                    "structural_break": pick.get("structural_break", False),
                    "structural_break_reason": pick.get("structural_break_reason", ""),
                    "forward_eps_growth": pick.get("forward_eps_growth", 0.0),
                    "iv15_nogrowth_agreement": pick.get("iv15_nogrowth_agreement", True),
                    "iv15_saturated": pick.get("iv15_saturated", False),
                    "sector_class": pick.get("sector_class", "operating"),
                    "methodology_applicable": {meth_key: pick.get("methodology_applicable", True)},
                }
            else:
                # Merge methodology attribution + valuation matrix (dossier/theses are
                # symbol-constant — same cached debate — so no need to re-copy them).
                all_candidates[sym]["source_methodologies"].append(meth_key)
                all_candidates[sym].setdefault("mos", {})[meth_key] = pick.get("mos", "N/A")
                all_candidates[sym].setdefault("fair_value", {})[meth_key] = pick.get("fair_value", "N/A")
                all_candidates[sym].setdefault("methodology_applicable", {})[meth_key] = pick.get("methodology_applicable", True)
                if pick.get("conviction", 0) > all_candidates[sym]["conviction"]:
                    all_candidates[sym]["conviction"] = pick["conviction"]
                    all_candidates[sym]["bull_thesis"] = pick.get("bull_thesis", "")
                    all_candidates[sym]["bear_thesis"] = pick.get("bear_thesis", "")
                    all_candidates[sym]["moderator_conclusion"] = pick.get("moderator_conclusion", "")
    
    log.info(f"Collected {len(all_candidates)} unique candidates from {len(tier1_baskets)} methodologies")
    
    # 2. Compute red flags + auto-veto
    auto_vetoed = {}
    director_candidates = []
    auto_veto_count = 0
    
    for sym, cand in all_candidates.items():
        red_flags = compute_red_flags(sym)
        red_flags = add_evasiveness_flag(red_flags, cand)
        cand["red_flags"] = red_flags
        
        if red_flags["total_active"] >= 3:
            log.info(f"  [Auto-Veto] {sym}: {red_flags['total_active']} red flags — conviction 2.0")
            auto_vetoed[sym] = {
                "conviction": 2,
                "rationale": f"Auto-veto: {red_flags['total_active']} severe financial red flags",
                "red_flags": red_flags["flags"],
            }
            auto_veto_count += 1
        else:
            active_flags = [k.replace("_", " ").title() for k, v in red_flags["flags"].items() if v]
            cand["financial_warnings"] = ", ".join(active_flags) if active_flags else "None"
            director_candidates.append(cand)
    
    log.info(f"Auto-vetoed: {auto_veto_count}, Remaining for Director: {len(director_candidates)}")
    
    # 3. Run Director LLM (or fallback)
    if dry_run or not director_candidates:
        log.info("[Dry Run / No Candidates] Using conviction-based fallback")
        return _build_fallback_result(director_candidates, auto_vetoed, auto_veto_count)
    
    # Build the Director prompt — full readable dossier per name (NO truncation), so the
    # PM consumes the team's complete work and ranks cross-sectionally.
    def _dirtrim(s, cap, head=0.55):
        # Trim a field for the director PROMPT, keeping head + tail so a dossier's opening
        # narrative AND its closing capital-allocation verdict both survive. The full,
        # untrimmed dossier is still stored in the speculair output for the stock page.
        if not s:
            return "N/A"
        if len(s) <= cap:
            return s
        h = int(cap * head)
        return s[:h] + "\n...[trimmed for director context — full dossier on stock page]...\n" + s[-(cap - h):]

    def _fmt_valuation(c):
        mos = c.get("mos", {}) or {}
        fv = c.get("fair_value", {}) or {}
        rows = [f"    - {m}: MoS {mos.get(m, 'N/A')}, Fair Value {fv.get(m, 'N/A')}"
                for m in sorted(set(list(mos.keys()) + list(fv.keys())))]
        return "\n".join(rows) if rows else "    (none)"

    def _format_candidate(c):
        return (
            f"═══════════ CANDIDATE: {c['symbol']} ═══════════\n"
            f"Sector: {c.get('sector','?')} | Signal: {c.get('signal_type','none')} | "
            f"Prior debate conviction: {c.get('conviction','?')}/5 | "
            f"Trajectory: {c.get('trajectory') or '?'} | Price: {c.get('price','?')}\n"
            f"Surfaced by {len(c.get('source_methodologies',[]))} of 10 methodologies "
            f"(cross-method consensus: {(c.get('consensus_agreement') or 0):.0%} of "
            f"{c.get('consensus_votes') or 0} valuation estimates cluster on fair value) — VALUATION MATRIX "
            f"(judge whether these fair values are realistic vs price & analysts):\n"
            f"{_fmt_valuation(c)}\n"
            f"Risk context: cycle_flag={c.get('cycle_flag','NORMAL')}, structural_break={c.get('structural_break',False)}, "
            f"years_history={c.get('years_history','?')}, forward_eps_growth={c.get('forward_eps_growth','?')}, "
            f"sector_class={c.get('sector_class','operating')}\n"
            f"Financial warnings: {c.get('financial_warnings','None')}\n\n"
            f"--- INTERROGATOR FORENSIC DOSSIER (trimmed for context; full version on the stock page) ---\n{_dirtrim(c.get('interrogator_dossier'), 6000)}\n\n"
            f"--- ARCHITECT BULL THESIS ---\n{_dirtrim(c.get('bull_thesis'), 2500)}\n\n"
            f"--- ARCHITECT BEAR THESIS ---\n{_dirtrim(c.get('bear_thesis'), 2500)}\n\n"
            f"--- MODERATOR / CRO ---\n"
            f"Consensus Delta: {_dirtrim(c.get('consensus_delta'), 1500)}\n"
            f"Valley of Death: {_dirtrim(c.get('valley_of_death'), 1500)}\n"
            f"Positioning Washout: {_dirtrim(c.get('positioning_washout'), 1000)}\n"
            f"Forcing Function: {_dirtrim(c.get('forcing_function'), 1500)}\n"
            f"CRO Synthesis: {_dirtrim(c.get('moderator_conclusion'), 2500)}\n"
        )

    candidate_blocks = "\n\n".join(_format_candidate(c) for c in director_candidates)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    macro_section = f"=== MACRO REGIME BRIEF ===\n{macro_brief}\n\n" if macro_brief else ""

    # Current live basket (held positions) for hold/rotate decisions.
    basket_section = ""
    if current_basket:
        cand_by_sym = {c["symbol"]: c for c in director_candidates}
        lines = ["=== CURRENT LIVE BASKET — your existing holdings; decide HOLD vs ROTATE (bias to hold) ==="]
        for sym, h in current_basket.items():
            ep = h.get("entry_price")
            cur = (cand_by_sym.get(sym) or {}).get("price")
            pnl = f", now {cur} ({(cur - ep) / ep * 100:+.1f}%)" if isinstance(ep, (int, float)) and isinstance(cur, (int, float)) and ep else ""
            tag = " [re-debated this cycle — full dossier above]" if sym in cand_by_sym else " [no fresh debate this cycle — hold unless clearly broken]"
            lines.append(f"  - {sym}: held since {h.get('entry_date','?')} @ {ep}{pnl}, prior conviction {h.get('conviction','?')}{tag}")
        basket_section = "\n".join(lines) + "\n\n"

    director_prompt = (
        f"Date: {today}\n\n"
        f"{macro_section}"
        f"{basket_section}"
        f"This is the FULL scored & gated candidate universe ({len(director_candidates)} names) "
        f"that survived the 9 methodology debate pipelines. Each name's complete dossier follows. "
        f"Consume the dossiers (do NOT re-derive them), rank the names cross-sectionally, judge each "
        f"name's cross-method valuation realism, weigh timing, then build your Speculair Apex Basket "
        f"FREELY: between 2 and 20 names, your own count, each scored 0-100 by conviction.\n\n"
        f"{candidate_blocks}"
    )

    log.info(f"Querying Director PM with {len(director_candidates)} candidates (free 2-20 selection)...")
    director_response = _query_director(director_prompt)

    if not director_response:
        log.warning("Director LLM call failed — using fallback")
        return _build_fallback_result(director_candidates, auto_vetoed, auto_veto_count)

    # 4. Parse Director response (contract: basket[] + watchlist[], 0-100 conviction)
    memo = director_response.get("memo", "")
    basket_picks = director_response.get("basket") or []
    watchlist_picks = director_response.get("watchlist") or []

    # Backward-compat: adapt the legacy {allocations: {TICKER: 1-5}} shape if emitted
    if not basket_picks and isinstance(director_response.get("allocations"), dict):
        log.warning("Director used legacy 'allocations' shape — adapting to basket/watchlist")
        for sym, c in director_response["allocations"].items():
            try:
                c = int(c)
            except (ValueError, TypeError):
                continue
            score = c * 20 if c <= 5 else c            # 5→100, 4→80, 3→60
            (basket_picks if score >= APEX_CONVICTION_FLOOR else watchlist_picks).append(
                {"symbol": sym, "conviction": score, "rationale": ""}
            )

    log.info(f"Director memo length: {len(memo)} chars")
    log.info(f"Director basket: {[(p.get('symbol'), p.get('conviction')) for p in basket_picks]}")

    def _make_entry(sym: str, raw_conv, rationale: str = "") -> Optional[dict]:
        """Build an output pick dict, applying deterministic G1-G4 gates.
        Returns None if the name is unknown or hard-excluded by a contract gate."""
        cand = all_candidates.get(sym)
        if not cand:
            log.warning(f"  Director named {sym} which is not in the candidate universe — skipping")
            return None
        try:
            raw_conv = int(raw_conv)
        except (ValueError, TypeError):
            raw_conv = 0
        conv = apply_contract_rules(cand, raw_conv)
        if conv is None:
            return None
        return {
            "symbol": sym,
            "conviction": conv,                              # 0-100 (director)
            "debate_conviction": cand.get("conviction", 0),  # 1-5 (moderator)
            # Preserve original entry for HELD names (track record continues); new names enter today.
            "entry_price": (current_basket.get(sym, {}).get("entry_price") or cand.get("price", 0)),
            "entry_date": (current_basket.get(sym, {}).get("entry_date") or today),
            "held_since_prior": sym in current_basket,
            "source_methodologies": cand.get("source_methodologies", []),
            "director_rationale": rationale or "Director selected portfolio allocation",
            "consensus_delta": cand.get("consensus_delta", ""),
            "forcing_function": cand.get("forcing_function", ""),
            "valley_of_death": cand.get("valley_of_death", ""),
            "positioning_washout": cand.get("positioning_washout", ""),
            "moderator_conclusion": cand.get("moderator_conclusion", ""),
            "bull_thesis": cand.get("bull_thesis", ""),
            "bear_thesis": cand.get("bear_thesis", ""),
            # Full opus forensic dossier — rendered on the stock page (Speculair + Transcript tabs)
            "interrogator_dossier": cand.get("interrogator_dossier", ""),
            "interrogator_score": cand.get("interrogator_score", 3),
            "trajectory": cand.get("trajectory", ""),
            "sector": cand.get("sector", ""),
            "mos": cand.get("mos", {}),
            "fair_value": cand.get("fair_value", {}),
            # Carry G1-G4 fields!
            "cycle_flag": cand.get("cycle_flag", "NORMAL"),
            "peak_margin_sigma": cand.get("peak_margin_sigma", 0.0),
            "norm_scale": cand.get("norm_scale", 1.0),
            "mos_source": cand.get("mos_source", ""),
            "years_history": cand.get("years_history", 99),
            "structural_break": cand.get("structural_break", False),
            "structural_break_reason": cand.get("structural_break_reason", ""),
            "forward_eps_growth": cand.get("forward_eps_growth", 0.0),
            "iv15_nogrowth_agreement": cand.get("iv15_nogrowth_agreement", True),
            "iv15_saturated": cand.get("iv15_saturated", False),
            "sector_class": cand.get("sector_class", "operating"),
            "methodology_applicable": cand.get("methodology_applicable", {}),
        }

    # 5. Build output baskets (free 2-20 apex, variable-size watchlist)
    apex_basket = []
    capitulation_watchlist = []
    seen = set()

    for p in basket_picks[:20]:                 # honor the 20-name ceiling
        sym = (p.get("symbol") or "").strip()
        if not sym or sym in seen:
            continue
        entry = _make_entry(sym, p.get("conviction", 0), p.get("rationale", ""))
        if entry is None:
            continue
        seen.add(sym)
        if entry["conviction"] >= APEX_CONVICTION_FLOOR:
            apex_basket.append(entry)
        else:
            # A risk gate (e.g. peak-cycle) demoted it below the apex floor
            entry["trigger_event"] = "Demoted below apex conviction floor by a risk gate (e.g. peak-cycle)"
            capitulation_watchlist.append(entry)

    for p in watchlist_picks[:8]:
        sym = (p.get("symbol") or "").strip()
        if not sym or sym in seen:
            continue
        entry = _make_entry(sym, p.get("conviction", 0), "")
        if entry is None:
            continue
        seen.add(sym)
        entry["trigger_event"] = p.get("trigger") or "Monitor for capitulation event"
        capitulation_watchlist.append(entry)

    # Apply sector cap (idiosyncratic-basket guardrail)
    apex_basket, capitulation_watchlist, cap_warnings = apply_sector_cap(
        apex_basket, capitulation_watchlist
    )
    if cap_warnings:
        memo += "\n\n--- SECTOR CAP ADJUSTMENTS ---\n" + "\n".join(cap_warnings)

    # Sort apex by conviction desc
    apex_basket.sort(key=lambda x: -x["conviction"])

    if len(apex_basket) < 2:
        log.warning(f"Director returned only {len(apex_basket)} apex names (<2) — below the 2-20 mandate.")

    log.info(f"Apex Basket ({len(apex_basket)}): {[(p['symbol'], p['conviction']) for p in apex_basket]}")
    log.info(f"Capitulation WL ({len(capitulation_watchlist)}): {[p['symbol'] for p in capitulation_watchlist]}")

    # Cache Director decisions
    _cache_decisions({p["symbol"]: p["conviction"] for p in apex_basket}, memo, today)

    return {
        "apex_basket": apex_basket,
        "capitulation_watchlist": capitulation_watchlist,
        "director_memo": memo,
        "auto_vetoed": auto_veto_count,
    }
 
 
def apply_sector_cap(apex: list, watchlist: list, max_per_sector: int = 3) -> tuple[list, list, list[str]]:
    """Enforce the idiosyncratic-basket guardrail: at most max_per_sector apex
    picks in any one sector.

    Over-cap picks are demoted (LOWEST director conviction first) to the
    Capitulation Watchlist. Because basket size is now the director's own free
    choice (2-20), this guardrail only ever REMOVES from apex — it never pads
    the basket by promoting watchlist names.

    Cross-reference: DIRECTOR_SYSTEM_PROMPT Step 2 (idiosyncratic basket).
    Returns: (apex, watchlist, warnings)
    """
    from collections import Counter
    warnings = []

    def sec_of(p):
        """Known sector or None. Blank/'Unknown' sectors are NOT capped — without
        sector data we cannot prove concentration, and capping them would collapse
        the whole basket into one phantom 'Unknown' bucket."""
        s = (p.get("sector") or "").strip()
        return s if s and s.lower() != "unknown" else None

    sector_counts = Counter(s for s in (sec_of(p) for p in apex) if s)

    # Soft warning at 2+
    for sector, count in sector_counts.items():
        if count >= 2:
            warnings.append(f"Sector concentration: {count} picks in {sector}")

    # Hard cap: demote lowest-conviction over-cap picks (known sectors only)
    changed = True
    while changed:
        changed = False
        sector_counts = Counter(s for s in (sec_of(p) for p in apex) if s)
        for sector, count in sector_counts.items():
            if count > max_per_sector:
                sector_picks = [p for p in apex if sec_of(p) == sector]
                sector_picks.sort(key=lambda x: x.get("conviction", 0))  # lowest 0-100 first
                demoted = sector_picks[0]
                apex.remove(demoted)
                demoted["trigger_event"] = f"Demoted from Apex by sector cap (>{max_per_sector} in {sector})"
                watchlist.append(demoted)
                warnings.append(f"Demoted {demoted['symbol']} from Apex (sector cap: {sector})")
                changed = True
                break

    return apex, watchlist, warnings
 
 
def _build_fallback_result(candidates: list, auto_vetoed: dict, veto_count: int) -> dict:
    """Conviction-based fallback when the Director LLM is unavailable.

    Only reached on a dry-run or a hard LLM failure — a LIVE run aborts upstream
    when the memo contains 'Fallback' (live_debate_engine stage gate). Maps the
    1-5 debate conviction onto the 0-100 director scale (5->100, 4->80, 3->60)
    and applies the G1-G4 gates (which now return None to hard-exclude).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    scored = []
    for c in candidates:
        gated = apply_contract_rules(c, int(c.get("conviction", 3)) * 20)  # 1-5 → 0-100
        if gated is None:
            continue
        scored.append((gated, c))

    scored.sort(key=lambda t: (
        -t[0],
        -len(t[1].get("source_methodologies", [])),
        -t[1].get("interrogator_score", 0),
    ))

    apex = []
    capitul = []
    for gated, c in scored:
        entry = {
            "symbol": c["symbol"],
            "conviction": gated,
            "debate_conviction": c.get("conviction", 0),
            "entry_price": c.get("price", 0),
            "entry_date": today,
            "source_methodologies": c.get("source_methodologies", []),
            "director_rationale": "Fallback allocation — Director LLM unavailable",
            "consensus_delta": c.get("consensus_delta", ""),
            "forcing_function": c.get("forcing_function", ""),
            "bull_thesis": c.get("bull_thesis", ""),
            "bear_thesis": c.get("bear_thesis", ""),
            "sector": c.get("sector", ""),
            # Carry G1-G4 fields!
            "cycle_flag": c.get("cycle_flag", "NORMAL"),
            "peak_margin_sigma": c.get("peak_margin_sigma", 0.0),
            "norm_scale": c.get("norm_scale", 1.0),
            "mos_source": c.get("mos_source", ""),
            "years_history": c.get("years_history", 99),
            "structural_break": c.get("structural_break", False),
            "structural_break_reason": c.get("structural_break_reason", ""),
            "forward_eps_growth": c.get("forward_eps_growth", 0.0),
            "iv15_nogrowth_agreement": c.get("iv15_nogrowth_agreement", True),
            "iv15_saturated": c.get("iv15_saturated", False),
            "sector_class": c.get("sector_class", "operating"),
            "methodology_applicable": c.get("methodology_applicable", {}),
            "mos": c.get("mos", {}),
        }
        if gated >= APEX_CONVICTION_FLOOR and len(apex) < 7:
            apex.append(entry)
        elif len(capitul) < 5:
            entry["trigger_event"] = "Monitor for capitulation event"
            capitul.append(entry)

    return {
        "apex_basket": apex,
        "capitulation_watchlist": capitul,
        "director_memo": "Fallback allocation — Director agent used conviction-based sorting. "
                         f"{veto_count} candidates auto-vetoed for ≥3 red flags.",
        "auto_vetoed": veto_count,
    }
 
 
def _cache_decisions(allocations: dict, memo: str, date: str):
    """Cache Director decisions to local file."""
    cache = {}
    if DIRECTOR_CACHE_FILE.exists():
        try:
            with open(DIRECTOR_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
    
    cache[date] = {
        "allocations": allocations,
        "memo": memo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    try:
        with open(DIRECTOR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        log.info(f"Cached Director decisions for {date}")
    except Exception as e:
        log.error(f"Failed to cache Director decisions: {e}")
    
    # Also push to GCS
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_upload
        gcs_upload("scans/director_decisions.json", cache)
    except Exception as e:
        log.debug(f"GCS upload of director decisions failed: {e}")
