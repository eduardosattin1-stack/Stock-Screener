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
DIRECTOR_SYSTEM_PROMPT = """You are the Apex Portfolio Manager & Chief Risk Officer for the Speculair high-performance, alpha-seeking stock selection system.
Your mandate is pure Relative Capital Allocation, Opportunity Cost, and Temporal Arbitrage. Capital is strictly finite. You must pit the provided equities against one another in a zero-sum competition.

You are provided with a batch of candidate equities that have already survived per-methodology debate pipelines (Radar, Interrogator, Architect, Moderator). Each candidate contains:
- "symbol": Ticker symbol
- "conviction": The debate conviction score (1 to 5)
- "source_methodologies": Which of the 9 valuation methodologies selected this stock
- "bull_thesis": The structural bull macro probability case
- "bear_thesis": The structural bear macro probability case
- "moderator_conclusion": The Expectations Arbitrage CRO synthesis
- "consensus_delta": The gap between street assumptions and reality
- "forcing_function": The imminent catalyst
- "red_flags": Active financial warning flags

Your execution workflow:

Step 1: The Ruthless Cull (Internal Filter)
Internally interrogate every stock. Instantly eliminate any stock that triggers temporal traps:
- The "Priced In" Veto: Kill any trade where Wall Street is already modeling the thesis and the multiple has expanded.
- The "Valley of Death" Veto: Kill any trade facing a massive cash-burn hump, debt maturity wall, or forced institutional liquidation before the primary catalyst triggers.
- The "Dead Money" Veto: Kill any trade where the forcing function is legally or practically more than 6 to 9 months away.

Step 2: Relative Ranking & Basket Optimization
Take the surviving candidates and rank them strictly on Maximum Immediate Asymmetry. Optimize for the widest gap between management's structural reality and Wall Street's legacy assumptions, paired with the most imminent catalyst. Ensure the final basket is idiosyncratic (do not cluster risks on the same macro catalyst).

Step 3: The Output Format
You must return a valid JSON object matching the following schema:
{
  "memo": "string (The Final Execution Memo formatted exactly as requested below)",
  "allocations": {
    "TICKER": integer (conviction score: 5 for Apex Basket, 3 for Capitulation Watchlist, 2 for Graveyard/Rejected)
  }
}

The "memo" string must be formatted exactly as follows:
1. THE SPECULAIR APEX BASKET (Select strictly 5 to 7 tickers):
These are the immediate "Aggressive Entry" allocations. For each selected equity, provide:
- The Consensus Delta: The exact street assumption that is factually incorrect today.
- The Forcing Function: The exact imminent event that will force the re-rating.
- Relative Conviction: One sentence explaining why this stock beat out discarded peers.

2. THE CAPITULATION WATCHLIST (Select Top 3 to 5 "Good but Early" Setups):
Fundamentally generational setups with terrible near-term timing. Specify the exact capitulation event or price point that will activate our buy order.

3. THE GRAVEYARD (Brief Summary):
Do not list individual tickers. Provide a rapid-fire, two-sentence post-mortem.

Output ONLY the raw JSON object. Do not write any markdown formatting or code blocks outside the JSON.

Note: Some baskets may be flagged as 'under_debated' (< 5 qualified candidates from 20 inputs).
Treat under-debated baskets with extra scrutiny — their conviction scores are statistically less reliable.
Prefer candidates from well-populated baskets when conviction scores are tied.
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
    }
    payload = {
        "model": "claude-opus-4-7-20250219",
        "max_tokens": 4096,
        "temperature": 0.1,
        "system": DIRECTOR_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "{"},
        ],
    }
    
    for attempt in range(max_attempts):
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers, json=payload, timeout=120
            )
            rj = r.json()
            if rj.get("type") == "error":
                err_msg = rj.get("error", {}).get("message", str(rj))
                if "rate" in err_msg.lower() or "overloaded" in err_msg.lower():
                    sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                    log.warning(f"Director rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                    time.sleep(sleep)
                    continue
                log.error(f"Director API error: {err_msg}")
                time.sleep(3.0)
                continue
            
            # Extract text from Anthropic response
            content_blocks = rj.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text += block.get("text", "")
            
            # Prepend the '{' we used for pre-filling
            text = "{" + text.strip()
            
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
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


# ── Main Director Allocation ─────────────────────────────────────────────
def run_director_allocation(tier1_baskets: dict, dry_run: bool = False) -> dict:
    """Run Tier 2 Director allocation across all methodology baskets.
    
    Args:
        tier1_baskets: dict of methodology_key → basket from Tier 1
        dry_run: if True, skip LLM call and use conviction-based fallback
    
    Returns dict with apex_basket, capitulation_watchlist, director_memo
    """
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
                    "bull_thesis": pick.get("bull_thesis", ""),
                    "bear_thesis": pick.get("bear_thesis", ""),
                    "moderator_conclusion": pick.get("moderator_conclusion", ""),
                    "consensus_delta": pick.get("consensus_delta", ""),
                    "forcing_function": pick.get("forcing_function", ""),
                    "verdict": pick.get("verdict", ""),
                    "interrogator_score": pick.get("interrogator_score", 3),
                    "price": pick.get("price", 0),
                    "sector": pick.get("sector", ""),
                    "signal_type": pick.get("signal_type", "none"),
                    "mos": {meth_key: pick.get("mos", "N/A")},
                }
            else:
                # Merge methodology attribution, take highest conviction, merge MOS
                all_candidates[sym]["source_methodologies"].append(meth_key)
                all_candidates[sym].setdefault("mos", {})[meth_key] = pick.get("mos", "N/A")
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
    
    # Build Director prompt
    prompt_candidates = []
    for c in director_candidates:
        prompt_candidates.append({
            "symbol": c["symbol"],
            "conviction": c["conviction"],
            "source_methodologies": c["source_methodologies"],
            "bull_thesis": c.get("bull_thesis", "N/A")[:300],
            "bear_thesis": c.get("bear_thesis", "N/A")[:300],
            "moderator_conclusion": c.get("moderator_conclusion", "N/A")[:400],
            "consensus_delta": c.get("consensus_delta", "N/A")[:200],
            "forcing_function": c.get("forcing_function", "N/A")[:200],
            "financial_warnings": c.get("financial_warnings", "None"),
            "signal_type": c.get("signal_type", "none"),
            "mos": c.get("mos", {}),
        })
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    director_prompt = (
        f"Date: {today}\n"
        f"Candidates for cross-sectional triaging ({len(prompt_candidates)} stocks "
        f"surviving from 9 methodology debate pipelines):\n"
        f"{json.dumps(prompt_candidates, indent=2)}"
    )
    
    log.info(f"Querying Director PM with {len(prompt_candidates)} candidates...")
    director_response = _query_director(director_prompt)
    
    if not director_response:
        log.warning("Director LLM call failed — using fallback")
        return _build_fallback_result(director_candidates, auto_vetoed, auto_veto_count)
    
    # 4. Parse Director response
    memo = director_response.get("memo", "")
    allocations = director_response.get("allocations", {})
    
    log.info(f"Director memo length: {len(memo)} chars")
    log.info(f"Director allocations: {allocations}")
    
    # 5. Build output baskets
    apex_basket = []
    capitulation_watchlist = []
    
    for sym, conv in allocations.items():
        conv = int(conv)
        cand = all_candidates.get(sym, {})
        
        entry = {
            "symbol": sym,
            "conviction": conv,
            "debate_conviction": cand.get("conviction", 0),
            "entry_price": cand.get("price", 0),
            "entry_date": today,
            "source_methodologies": cand.get("source_methodologies", []),
            "director_rationale": "",
            "consensus_delta": cand.get("consensus_delta", ""),
            "forcing_function": cand.get("forcing_function", ""),
            "bull_thesis": cand.get("bull_thesis", ""),
            "bear_thesis": cand.get("bear_thesis", ""),
            "sector": cand.get("sector", ""),
            "mos": cand.get("mos", {}),
        }
        
        if conv >= 5:
            apex_basket.append(entry)
        elif conv >= 3:
            entry["trigger_event"] = cand.get("valley_of_death", "Monitor for capitulation event")
            capitulation_watchlist.append(entry)
    
    # Apply sector cap
    apex_basket, capitulation_watchlist, cap_warnings = apply_sector_cap(
        apex_basket, capitulation_watchlist
    )
    if cap_warnings:
        memo += "\n\n--- SECTOR CAP ADJUSTMENTS ---\n" + "\n".join(cap_warnings)

    # Sort apex by conviction desc
    apex_basket.sort(key=lambda x: -x["conviction"])
    
    log.info(f"Apex Basket: {[p['symbol'] for p in apex_basket]}")
    log.info(f"Capitulation WL: {[p['symbol'] for p in capitulation_watchlist]}")
    
    # Cache Director decisions
    _cache_decisions(allocations, memo, today)
    
    return {
        "apex_basket": apex_basket,
        "capitulation_watchlist": capitulation_watchlist,
        "director_memo": memo,
        "auto_vetoed": auto_veto_count,
    }


def apply_sector_cap(apex: list, watchlist: list, max_per_sector: int = 3) -> tuple[list, list, list[str]]:
    """Enforce sector concentration cap on Apex basket.
    
    If a sector has > max_per_sector picks in Apex, demote the lowest
    debate_conviction pick to Watchlist and promote the highest conviction
    watchlist pick from a different sector.
    
    Cross-reference: DIRECTOR_SYSTEM_PROMPT Step 2 (idiosyncratic basket).
    
    Returns: (apex, watchlist, warnings)
    """
    warnings = []
    from collections import Counter
    sector_counts = Counter(p.get("sector", "Unknown") for p in apex)
    
    # Soft warning at 2+
    for sector, count in sector_counts.items():
        if count >= 2:
            warnings.append(f"Sector concentration: {count} picks in {sector}")
    
    # Hard cap: demote/promote if > max_per_sector
    changed = True
    while changed:
        changed = False
        sector_counts = Counter(p.get("sector", "Unknown") for p in apex)
        for sector, count in sector_counts.items():
            if count > max_per_sector:
                # Find lowest debate_conviction in this sector
                sector_picks = [p for p in apex if p.get("sector", "Unknown") == sector]
                sector_picks.sort(key=lambda x: x.get("debate_conviction", 0))
                demoted = sector_picks[0]
                apex.remove(demoted)
                demoted["conviction"] = 3  # Demote to watchlist conviction
                watchlist.append(demoted)
                warnings.append(f"Demoted {demoted['symbol']} from Apex (sector cap: {sector})")
                
                # Promote highest conviction watchlist pick from a DIFFERENT sector
                other_wl = [p for p in watchlist if p.get("sector", "Unknown") != sector]
                if other_wl:
                    other_wl.sort(key=lambda x: -x.get("debate_conviction", 0))
                    promoted = other_wl[0]
                    watchlist.remove(promoted)
                    promoted["conviction"] = 5  # Promote to apex conviction
                    apex.append(promoted)
                    warnings.append(f"Promoted {promoted['symbol']} to Apex (replacing sector-capped pick)")
                
                changed = True
                break
    
    return apex, watchlist, warnings


def _build_fallback_result(candidates: list, auto_vetoed: dict, veto_count: int) -> dict:
    """Conviction-based fallback when Director LLM unavailable."""
    candidates.sort(key=lambda x: (
        -x.get("conviction", 0),
        -len(x.get("source_methodologies", [])),
        -x.get("interrogator_score", 0)
    ))
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    apex = []
    capitul = []
    
    for c in candidates[:7]:
        apex.append({
            "symbol": c["symbol"],
            "conviction": c.get("conviction", 3),
            "entry_price": c.get("price", 0),
            "entry_date": today,
            "source_methodologies": c.get("source_methodologies", []),
            "director_rationale": "Fallback allocation — Director LLM unavailable",
            "consensus_delta": c.get("consensus_delta", ""),
            "forcing_function": c.get("forcing_function", ""),
            "bull_thesis": c.get("bull_thesis", ""),
            "bear_thesis": c.get("bear_thesis", ""),
            "sector": c.get("sector", ""),
        })
    
    for c in candidates[7:12]:
        if c.get("conviction", 0) >= 3:
            capitul.append({
                "symbol": c["symbol"],
                "conviction": c.get("conviction", 3),
                "trigger_event": "Monitor for capitulation event",
                "source_methodologies": c.get("source_methodologies", []),
            })
    
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
