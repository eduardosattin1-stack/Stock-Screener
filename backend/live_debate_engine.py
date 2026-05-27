#!/usr/bin/env python3
"""
live_debate_engine.py — Speculair Two-Tier Multi-Agent Debate Pipeline
=====================================================================
Tier 1: Per-methodology 4-Agent Barbell Debate
  Radar (gemini-3.5-flash, two-mode) → Interrogator (gemini-3.1-pro-preview) →
  Architect (gpt-5.4) → Moderator (gpt-5.5 via OpenAI)

Tier 2: Apex PM Director cross-sectional basket allocation
  (Delegated to live_director_agent.py — claude-opus-4-7 via Anthropic SDK)

Radar operates in two modes selected by methodology:
  • growth_catalyst  (methodologies 1-3, 5, 7, 8)
  • value_trap_audit (methodologies 4, 6, 9)
Radar is a CLASSIFIER / TAGGER, not a gate — all candidates proceed.

Usage:
  python backend/live_debate_engine.py --run-full
  python backend/live_debate_engine.py --dry-run  # no LLM calls, loads cached
"""
from __future__ import annotations

import argparse
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DebateEngine] %(message)s")
log = logging.getLogger("live_debate")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
CACHE_DIR = BASE_DIR / "debate_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEBATE_CACHE_FILE = CACHE_DIR / "live_debate_convictions.json"
TRANSCRIPT_CACHE_DIR = BASE_DIR / "fmp_cache" / "earning-call-transcript"

GCS_BUCKET = "screener-signals-carbonbridge"

# Methodology keys matching screener_v6.py
METHODOLOGY_KEYS = [
    "dcf_fcff", "rd_capitalized_dcf", "owner_earnings", "epv",
    "graham_revised", "iv15_deep_value", "ev_gross_profit",
    "earnings_yield_gap", "acquirers_multiple"
]

# ── Radar Mode Router ────────────────────────────────────────────────────
# Value-oriented methodologies get the value_trap_audit prompt;
# growth/catalyst methodologies get the growth_catalyst prompt.
VALUE_METHODOLOGIES = {"epv", "iv15_deep_value", "acquirers_multiple"}

def radar_mode_for_methodology(meth_key: str) -> str:
    """Return 'value_trap_audit' or 'growth_catalyst' based on methodology."""
    return "value_trap_audit" if meth_key in VALUE_METHODOLOGIES else "growth_catalyst"

# ── API Key Loading ──────────────────────────────────────────────────────
def load_api_keys():
    """Load API keys from frontend/.env.local into os.environ."""
    env_path = FRONTEND_DIR / ".env.local"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().replace('"', '').replace("'", "")

def get_key(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        load_api_keys()
        val = os.environ.get(name, "")
    return val


# ── Transcript Resolution ────────────────────────────────────────────────
def resolve_transcript(symbol: str, before_date: str = None) -> Optional[dict]:
    """Resolve latest earnings call transcript for symbol.
    
    Returns dict with keys: date, content, filename, source
    First checks local cache, then fetches from FMP API.
    If before_date is given, only transcripts dated <= before_date qualify.
    """
    # 1. Check local cache
    cached = _resolve_from_cache(symbol, before_date)
    if cached:
        return cached
    
    # 2. Fetch from FMP
    return _fetch_from_fmp(symbol, before_date)


def _resolve_from_cache(symbol: str, before_date: str = None) -> Optional[dict]:
    """Find latest cached transcript for symbol, optionally before a date."""
    if not TRANSCRIPT_CACHE_DIR.exists():
        return None
    
    transcripts = []
    for f in TRANSCRIPT_CACHE_DIR.glob(f"{symbol}_*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                payload = data.get("payload", [])
                if isinstance(payload, list) and payload:
                    t_date = payload[0].get("date", "")
                    t_content = payload[0].get("content", "")
                    if t_date and t_content and len(t_content) > 100:
                        if before_date is None or t_date <= before_date:
                            transcripts.append({
                                "date": t_date,
                                "content": t_content,
                                "filename": f.name,
                                "source": "cache"
                            })
        except Exception:
            pass
    
    if transcripts:
        transcripts.sort(key=lambda x: x["date"], reverse=True)
        return transcripts[0]
    return None


def _fetch_from_fmp(symbol: str, before_date: str = None) -> Optional[dict]:
    """Fetch latest transcript from FMP API and cache it."""
    fmp_key = get_key("FMP_API_KEY")
    if not fmp_key:
        log.warning(f"FMP_API_KEY not set — cannot fetch transcript for {symbol}")
        return None
    
    try:
        url = f"https://financialmodelingprep.com/stable/earning-call-transcript"
        r = requests.get(url, params={"symbol": symbol, "limit": 4, "apikey": fmp_key}, timeout=20)
        if r.status_code != 200:
            log.warning(f"FMP transcript fetch for {symbol}: HTTP {r.status_code}")
            return None
        
        data = r.json()
        if not isinstance(data, list) or not data:
            return None
        
        # Find latest transcript (optionally before_date)
        for entry in data:
            t_date = entry.get("date", "")
            t_content = entry.get("content", "")
            if t_date and t_content and len(t_content) > 100:
                if before_date is None or t_date[:10] <= before_date:
                    # Cache it
                    quarter = entry.get("quarter", "")
                    year = entry.get("year", "")
                    cache_name = f"{symbol}_{year}Q{quarter}.json"
                    cache_path = TRANSCRIPT_CACHE_DIR / cache_name
                    if not cache_path.exists():
                        TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                        with open(cache_path, "w", encoding="utf-8") as fh:
                            json.dump({"payload": [entry]}, fh)
                    
                    return {
                        "date": t_date[:10],
                        "content": t_content,
                        "filename": cache_name,
                        "source": "fmp_api"
                    }
        return None
    except Exception as e:
        log.warning(f"FMP transcript fetch for {symbol} failed: {e}")
        return None


# ── Debate Cache ─────────────────────────────────────────────────────────
def load_debate_cache() -> dict:
    if DEBATE_CACHE_FILE.exists():
        try:
            with open(DEBATE_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error reading debate cache: {e}")
    return {}

def save_debate_cache(cache: dict):
    try:
        tmp = DEBATE_CACHE_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        tmp.replace(DEBATE_CACHE_FILE)
    except Exception as e:
        log.error(f"Error saving debate cache: {e}")


# ── LLM Calling Helpers ─────────────────────────────────────────────────
def query_gemini(model_name: str, system_prompt: str, user_prompt: str,
                 response_schema=None, max_attempts: int = 4) -> Optional[dict]:
    """Call Gemini API with structured JSON output."""
    api_key = get_key("GEMINI_API_KEY") or get_key("GOOGLE_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY not found")
        return None
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
    except ImportError:
        log.error("google-generativeai not installed")
        return None
    
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    safety = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    gen_config = {"temperature": 0.1, "response_mime_type": "application/json"}
    if response_schema:
        gen_config["response_schema"] = response_schema
    
    for attempt in range(max_attempts):
        try:
            model = genai.GenerativeModel(
                model_name=f"models/{model_name}",
                system_instruction=system_prompt,
                safety_settings=safety
            )
            response = model.generate_content(user_prompt, generation_config=gen_config)
            try:
                text = response.text.strip()
            except Exception:
                if response.candidates and response.candidates[0].content.parts:
                    text = response.candidates[0].content.parts[0].text.strip()
                else:
                    text = "{}"
            
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            return json.loads(text.strip())
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "quota" in err or "overloaded" in err:
                sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                log.warning(f"Gemini rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                time.sleep(sleep)
            else:
                log.error(f"Gemini {model_name} error: {e}")
                time.sleep(3.0)
    return None


def query_openai(model: str, system_prompt: str, user_prompt: str,
                 max_attempts: int = 4) -> Optional[dict]:
    """Call OpenAI API with JSON output."""
    api_key = get_key("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY not found")
        return None
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_completion_tokens": 600,
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    
    for attempt in range(max_attempts):
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                              headers=headers, json=payload, timeout=60)
            rj = r.json()
            if "choices" in rj and rj["choices"]:
                text = rj["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
                return json.loads(text.strip())
            else:
                log.error(f"OpenAI error: {rj}")
                time.sleep(3.0)
        except Exception as e:
            log.error(f"OpenAI {model} error: {e}")
            time.sleep(3.0 * (attempt + 1))
    return None


# ── Agent System Prompts ─────────────────────────────────────────────────
import typing_extensions as typing

class RadarOutput(typing.TypedDict):
    alert: bool
    signal_type: str
    rationale: str

class InterrogatorOutput(typing.TypedDict):
    credibility_score: int
    findings: str

class ModeratorOutput(typing.TypedDict):
    verdict: str
    conviction: int
    consensus_delta: str
    valley_of_death: str
    positioning_washout: str
    forcing_function: str
    moderator_conclusion: str

RADAR_GROWTH_CATALYST_PROMPT = """You are the Radar Agent, a real-time market scanner for a financial investment committee.
Your job is to read the earnings call transcript and determine if the company has under-appreciated R&D tailwinds, technological breakthroughs, or structural innovation-driven growth catalysts, OR if it exhibits any of the following event-driven/restructuring setups:
1. The "Capital Cycle" & Supply Destruction (Marathon Playbook): Sector-wide vocabulary shift from market expansion to capacity discipline, footprint rationalization, or asset scrapping.
2. The "Outsider" Capital Allocation Inflection (The Thorndike Hook): Vocab shift from top-line TAM expansion/synergies to per-share metrics like ROIC, hurdle rates, share cannibalization, or non-core divestitures.
3. "Acoustic Sandbagging" & The Kitchen Sink (Behavioral Arbitrage): Catastrophic forward guidance paired with massive goodwill impairments and strategic option strike price alignments.
4. The "Shadow Pivot" (Narrative vs. CapEx Divergence): Stealth transition into high-margin verticals (e.g. AI infrastructure, software) while publicly maintaining legacy hardware/dividend narratives.
5. Activist & Governance Reset (Loeb/Bloom Catalysts): Board reconstitution, strategic review process, spin-off or IPO of undervalued divisions, shareholder activism campaigns.

Filter out all defensive financial noise, cost-cutting narratives, or generic management optimism.
Focus only on whether the transcript shows clear indicators of innovation-driven future growth, R&D momentum, or new event-driven value-unlock catalysts.

You must output a JSON object:
{
  "alert": boolean (true if any of the above moats, pivots, or catalysts are present, false otherwise),
  "signal_type": "innovation" | "catalyst" | "none",
  "rationale": "A concise single sentence (max 25 words) explaining your decision."
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.
"""

RADAR_VALUE_TRAP_PROMPT = """You are the Radar Agent (Value-Trap Audit mode), a real-time scanner for a financial investment committee.
You are reviewing a company selected by a deep-value / no-growth valuation methodology. These stocks are EXPECTED to look narratively dead.

Your job is NOT to check for innovation or growth catalysts. Instead, determine whether the company is a genuine deep-value opportunity or a terminal value trap.

Check for:
1. Capital Return Discipline: Is the company returning cash via buybacks, dividends, or debt paydown, or is it hoarding cash while destroying value?
2. Asset Floor Integrity: Is tangible book value, liquidation value, or replacement cost holding, or is it evaporating through write-downs, goodwill impairments, or hidden liabilities?
3. Earnings Power Sustainability: Are normalized earnings stable or declining? Is there a structural decline in the core business that MOS cannot compensate for?
4. Governance / Insider Alignment: Are insiders buying, or dumping? Is there shareholder activism or a strategic review?
5. Secular Obsolescence Risk: Is this a melting ice cube (newspapers, legacy retail) or a stable cash generator in a boring but durable industry?

You must output a JSON object:
{
  "alert": boolean (true if the stock passes the value-trap audit — i.e., it is a genuine deep-value opportunity, false if it is a likely value trap),
  "signal_type": "deep_value" | "trap" | "none",
  "rationale": "A concise single sentence (max 25 words) explaining your decision."
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.
"""

INTERROGATOR_SYSTEM_PROMPT = """You are the Interrogator Agent for a financial investment committee.
Your job is to critically analyze the company's structural technological/R&D claims and event-driven narratives in the earnings call transcript.
Cross-reference these claims against the financial metrics provided (such as R&D expense, capex, margins, revenue growth).

Perform forensic analysis:
- Verify whether management's stated strategic priorities are consistent with the actual capital expenditure and R&D spend trajectory.
- Check for disconnect between narrative claims (e.g., "AI transformation", "platform pivot") and measurable financial evidence.
- Assess whether revenue growth, margin trends, and cash flow patterns corroborate or contradict the earnings call narrative.
- Flag any signs of earnings evasiveness, non-answers during Q&A, or defensive deflection.

You must output a JSON object:
{
  "credibility_score": integer (1 to 5, where 5 is highly credible and 1 is evasive/unsupported),
  "findings": "A concise paragraph (max 100 words) summarizing your forensic analysis of transcript claims versus financial reality."
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.
"""

ARCHITECT_SYSTEM_PROMPT = """You are the Architect Agent, a System-2 reasoning engine for a financial investment committee.
Your job is to take the Interrogator's findings, the financial metrics, and the transcript to construct a rigorous, probabilistically weighted Bull and Bear case.
Map exactly how the macro environment impacts the company's R&D moat or event-driven catalyst logistically.
Do NOT include any specific numbers (percentages, dollar figures, or statistics) in the arguments.

You must output a JSON object:
{
  "bull_thesis": "A concise paragraph of at most 100 words presenting the bullish argument.",
  "bear_thesis": "A concise paragraph of at most 100 words presenting the bearish argument."
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.
"""

MODERATOR_SYSTEM_PROMPT = """You are the Chief Risk Officer & Expectations Arbitrageur for a financial investment committee.
Your task is to review the earnings call transcript, along with the Interrogator's findings, the Architect's Bull/Bear cases, and financial metrics.
Your sole responsibility is to evaluate TIMING, NARRATIVE SATURATION, and MARGIN OF SAFETY to measure the delta between fundamental reality and market perception.

Analyze the subtext, narrative history, and simulated positioning data to answer these four questions:
1. The Consensus Delta: Is Wall Street still looking the wrong way? Quote or explain the exact analyst assumptions that are factually incorrect based on our hidden thesis.
2. The Valley of Death: Detail exactly what will go wrong in the next 3 to 9 months. Is there a cash burn hump, debt maturity wall, or macro headwind that will temporarily decimate Free Cash Flow or punish the stock before the catalyst is realized?
3. The Positioning Washout: Will the pivot/dividend cut force the current yield-focused/passive shareholder base to liquidate mechanically?
4. The Forcing Function: What is the exact hard date, proxy window, or corporate event that will shatter the current consensus and force a re-rating?

You must also perform Activist & Catalyst Detection by merging:
- Loeb's Third Point criteria (catalyst density, sum-of-parts discount, activism potential, asymmetric risk/reward).
- The Bloom template (governance reset, strategic process, premium scenario).

Your final execution verdict MUST be one of:
- "A": AGGRESSIVE ENTRY (Catalyst imminent, market offside, pain trade is primed).
- "B": WATCHLIST FOR CAPITULATION (The thesis is real, but wait for a specific flush/headwind to clear the decks—specify the exact event to wait for).
- "C": PASS (The narrative is saturated, multiple expanded, or alpha is dead).

The conviction score MUST be an integer between 1 and 5 matching the verdict:
- 5: Strong Buy (Aggressive Entry, high conviction catalysts, activism/governance resets)
- 4: Buy (Watchlist for Capitulation with clear timing/catalysts)
- 3: Hold / Neutral (Moderate watchlist / stable profile)
- 2: Sell (Pass, challenged fundamentals, lack of catalysts, or priced in)
- 1: Strong Sell (Pass, value trap, or capital destruction risk)

You must return a valid JSON object:
{
  "verdict": "A" | "B" | "C",
  "conviction": integer (1 to 5),
  "consensus_delta": "string (max 100 words)",
  "valley_of_death": "string (max 100 words)",
  "positioning_washout": "string (max 100 words)",
  "forcing_function": "string (max 100 words)",
  "moderator_conclusion": "string (your detailed synthesis, timing analysis, and narrative summary, max 250 words)"
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.

IMPORTANT — Signal-Type Branching:
The Radar Agent has classified this candidate with a signal_type:
- If signal_type is "innovation" or "catalyst": evaluate through the growth/catalyst lens above.
- If signal_type is "deep_value": shift your framework. The Consensus Delta becomes "Is the street pricing terminal decline into a company with stable/growing earnings power?" The Valley of Death becomes "Is there a liquidation event, debt maturity, or forced selling that could kill the thesis before MOS converges?" The Forcing Function becomes "What event (buyback authorization, activist, asset sale, dividend initiation) will force the market to re-rate?"
- If signal_type is "trap" or "none": assign conviction ≤ 2 and verdict C unless extraordinary override evidence exists.
"""


# ── Single-Candidate Debate ─────────────────────────────────────────────
def debate_candidate(symbol: str, transcript: dict, financials: dict = None,
                     cache: dict = None, methodology_key: str = "") -> dict:
    """Run 4-agent debate on a single candidate.
    
    Returns a debate result dict with conviction, theses, moderator synthesis.
    Uses cache keyed by {symbol}|{transcript_date} to avoid re-debating.
    """
    t_date = transcript["date"]
    cache_key = f"{symbol}|{t_date}"
    
    # Check cache
    if cache and cache_key in cache:
        cached = cache[cache_key]
        if cached.get("bull_thesis") not in (None, "API Timeout/Failure"):
            log.info(f"  [Cache Hit] {symbol} (transcript {t_date})")
            return cached
    
    t_content = transcript["content"][:8000]
    if len(transcript["content"]) > 8000:
        t_content += "\n[Transcript truncated for length...]"
    
    # Build financial metrics string
    metrics_str = "No financial metrics available."
    if financials:
        metrics_fields = ["price", "sector", "market_cap", "mos", "fair_value",
                          "entry_metric", "weight"]
        m = {k: financials.get(k, "N/A") for k in metrics_fields if financials.get(k) is not None}
        if m:
            metrics_str = json.dumps(m, indent=2, default=str)
    
    result = {
        "symbol": symbol,
        "transcript_date": t_date,
        "transcript_filename": transcript.get("filename", ""),
        "radar_alert": False,
        "radar_rationale": "",
        "signal_type": "none",
        "methodology_key": methodology_key,
        "interrogator_score": 3,
        "interrogator_findings": "",
        "bull_thesis": "",
        "bear_thesis": "",
        "conviction": 2,
        "verdict": "C",
        "consensus_delta": "",
        "valley_of_death": "",
        "positioning_washout": "",
        "forcing_function": "",
        "moderator_conclusion": "",
        "debated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # ── 1. RADAR (gemini-3.5-flash, methodology-aware) ───────────────────
    radar_mode = radar_mode_for_methodology(methodology_key)
    radar_prompt = RADAR_VALUE_TRAP_PROMPT if radar_mode == "value_trap_audit" else RADAR_GROWTH_CATALYST_PROMPT
    log.info(f"  [Radar:{radar_mode}] {symbol} ...")
    radar_out = query_gemini(
        "gemini-3.5-flash",
        radar_prompt,
        f"Transcript content:\n{t_content}",
        response_schema=RadarOutput
    )
    
    if radar_out:
        result["radar_alert"] = radar_out.get("alert", False)
        result["signal_type"] = radar_out.get("signal_type", "none")
        result["radar_rationale"] = radar_out.get("rationale", "")
    else:
        # On error, assume alert=True to avoid filtering real candidates
        result["radar_alert"] = True
        result["signal_type"] = "catalyst" if radar_mode == "growth_catalyst" else "deep_value"
        result["radar_rationale"] = "Radar API error — defaulting to alert"
    
    # Radar is a TAGGER, not a gate — all candidates proceed regardless of alert
    log.info(f"  [Radar:{radar_mode}] {symbol}: alert={result['radar_alert']}, "
             f"signal_type={result['signal_type']}, rationale={result['radar_rationale']}")
    time.sleep(1.0)  # Rate limiting
    
    # ── 2. INTERROGATOR (gemini-3.1-pro-preview) ─────────────────────────
    log.info(f"  [Interrogator] {symbol} ...")
    interr_out = query_gemini(
        "gemini-3.1-pro-preview",
        INTERROGATOR_SYSTEM_PROMPT,
        f"Financial Metrics:\n{metrics_str}\n\nTranscript content:\n{t_content}",
        response_schema=InterrogatorOutput
    )
    
    if interr_out:
        result["interrogator_score"] = int(interr_out.get("credibility_score", 3))
        result["interrogator_findings"] = interr_out.get("findings", "")
    
    time.sleep(1.5)
    
    # ── 3. ARCHITECT (gpt-5.4) ────────────────────────────────────────────
    log.info(f"  [Architect] {symbol} ...")
    arch_prompt = (
        f"Financial Metrics:\n{metrics_str}\n\n"
        f"Interrogator Findings:\n{result['interrogator_findings']}\n\n"
        f"Transcript content:\n{t_content}"
    )
    arch_out = query_openai("gpt-5.4", ARCHITECT_SYSTEM_PROMPT, arch_prompt)
    
    if arch_out:
        result["bull_thesis"] = arch_out.get("bull_thesis", "")
        result["bear_thesis"] = arch_out.get("bear_thesis", "")
    
    time.sleep(1.0)
    
    # ── 4. MODERATOR (gpt-5.5 via OpenAI) ─────────────────────────────────
    log.info(f"  [Moderator] {symbol} ...")
    mod_prompt = (
        f"Company: {symbol}\n"
        f"Earnings Call Date: {t_date}\n"
        f"Radar Signal Type: {result['signal_type']}\n\n"
        f"=== FINANCIAL METRICS ===\n{metrics_str}\n\n"
        f"=== INTERROGATOR FINDINGS ===\n"
        f"Credibility Score: {result['interrogator_score']}/5\n"
        f"{result['interrogator_findings']}\n\n"
        f"=== ARCHITECT BULL THESIS ===\n{result['bull_thesis']}\n\n"
        f"=== ARCHITECT BEAR THESIS ===\n{result['bear_thesis']}\n\n"
        f"=== EARNINGS CALL TRANSCRIPT ===\n{t_content}\n\n"
        f"Please run your final moderation synthesis and output the JSON result."
    )
    mod_out = query_openai(
        "gpt-5.5",
        MODERATOR_SYSTEM_PROMPT,
        mod_prompt,
    )
    
    if mod_out:
        result["conviction"] = max(1, min(5, int(mod_out.get("conviction", 3))))
        result["verdict"] = mod_out.get("verdict", "B")
        result["consensus_delta"] = mod_out.get("consensus_delta", "")
        result["valley_of_death"] = mod_out.get("valley_of_death", "")
        result["positioning_washout"] = mod_out.get("positioning_washout", "")
        result["forcing_function"] = mod_out.get("forcing_function", "")
        result["moderator_conclusion"] = mod_out.get("moderator_conclusion", "")
    
    log.info(f"  [Result] {symbol}: verdict={result['verdict']} conviction={result['conviction']}")
    return result


# ── Per-Methodology Basket Selection ─────────────────────────────────────
def select_methodology_basket(methodology: str, debate_results: list[dict],
                              target_size: int = 7) -> dict:
    """From debate results for a methodology, select top picks.
    
    Selection criteria (Expectations Arbitrage & Temporal Vetoes):
    1. Only candidates with conviction >= 3 (verdict A or B)
    2. Sorted by conviction DESC, then by interrogator score
    3. Take top target_size
    
    Note: Under-debated baskets (< 5 qualified candidates from 20 inputs)
    are flagged with 'under_debated': True for Director-level review.
    """
    # Filter to debated candidates with conviction >= 3
    qualified = [r for r in debate_results if r.get("conviction", 0) >= 3]
    
    # Sort by conviction DESC
    qualified.sort(key=lambda x: (-x.get("conviction", 0), -x.get("interrogator_score", 0)))
    
    # Take top picks
    picks = qualified[:target_size]
    
    under_debated = len(qualified) < 5
    
    # Build moderator memo summarizing selections
    if picks:
        pick_syms = [p["symbol"] for p in picks]
        memo = (f"[{methodology}] Selected {len(picks)} picks: {', '.join(pick_syms)}. "
                f"Filtered {len(debate_results) - len(qualified)} candidates "
                f"(conviction < 3 or radar filtered). "
                f"Top conviction: {picks[0]['symbol']} ({picks[0].get('conviction', '?')}/5).")
    else:
        memo = f"[{methodology}] No candidates survived the debate pipeline."
    
    return {
        "methodology": methodology,
        "picks": picks,
        "moderator_memo": memo,
        "total_candidates": len(debate_results),
        "radar_filtered": sum(1 for r in debate_results if not r.get("radar_alert", True)),
        "qualified": len(qualified),
        "under_debated": under_debated,
    }


# ── Tier 1: Full Per-Methodology Pipeline ────────────────────────────────
def run_tier1(methodology_picks: dict, before_date: str = None,
              dry_run: bool = False) -> dict:
    """Run Tier 1 debate pipeline across all 9 methodologies.
    
    Args:
        methodology_picks: dict from methodology_picks.json
        before_date: for backfill — only use transcripts before this date
        dry_run: if True, only use cached results
    
    Returns dict of per-methodology baskets.
    """
    cache = load_debate_cache()
    methodologies = methodology_picks.get("methodologies", {})
    
    tier1_results = {}
    stats = {
        # 3-bucket disjoint funnel (sum == unique_symbols)
        "total_picks": 0,            # non-deduped across all methodologies
        "unique_symbols": 0,          # deduped
        "cache_hits": 0,              # cache served, no LLM calls
        "no_transcript": 0,           # skipped, no earnings call available
        "fully_debated": 0,           # full 4-agent debate ran

        # Orthogonal Radar tag distribution (sum == fully_debated)
        "radar_alerted": 0,
        "radar_filtered": 0,
        "radar_filtered_names": [],
    }
    seen_symbols = set()
    
    for meth_key in METHODOLOGY_KEYS:
        meth_data = methodologies.get(meth_key)
        if not meth_data:
            log.warning(f"No data for methodology {meth_key}")
            continue
        
        picks = meth_data.get("picks", [])
        if not picks:
            log.warning(f"No picks for {meth_key}")
            continue
        
        # Take up to 20 candidates per methodology
        candidates = picks[:20]
        log.info(f"\n{'='*60}")
        log.info(f"METHODOLOGY: {meth_key} — {len(candidates)} candidates")
        log.info(f"{'='*60}")
        
        debate_results = []
        for cand in candidates:
            symbol = cand.get("symbol", "")
            if not symbol:
                continue
            
            stats["total_picks"] += 1
            if symbol not in seen_symbols:
                stats["unique_symbols"] += 1
                seen_symbols.add(symbol)
            
            # Resolve transcript
            transcript = resolve_transcript(symbol, before_date)
            if not transcript:
                log.warning(f"  No transcript for {symbol} — skipping")
                stats["no_transcript"] += 1
                debate_results.append({
                    "symbol": symbol,
                    "conviction": 2,
                    "verdict": "C",
                    "radar_alert": False,
                    "radar_rationale": "No transcript available",
                    "moderator_conclusion": "No transcript available — quality penalty",
                    "methodology_key": meth_key,
                })
                continue
            
            # Check cache
            cache_key = f"{symbol}|{transcript['date']}"
            if cache_key in cache and cache[cache_key].get("bull_thesis") not in (None, "API Timeout/Failure"):
                log.info(f"  [Cache Hit] {symbol} (transcript {transcript['date']})")
                debate_results.append(cache[cache_key])
                stats["cache_hits"] += 1
                continue
            
            if dry_run:
                log.info(f"  [Dry Run] {symbol} — would debate")
                debate_results.append({
                    "symbol": symbol,
                    "conviction": 3,
                    "verdict": "B",
                    "radar_alert": True,
                    "radar_rationale": "Dry run — skipped",
                    "moderator_conclusion": "Dry run — no LLM calls made",
                })
                continue
            
            # Run debate
            result = debate_candidate(symbol, transcript, cand, cache, methodology_key=meth_key)
            debate_results.append(result)
            
            # Update cache
            cache[cache_key] = result
            save_debate_cache(cache)
            
            stats["fully_debated"] += 1
            if result.get("radar_alert"):
                stats["radar_alerted"] += 1
            else:
                stats["radar_filtered"] += 1
                stats["radar_filtered_names"].append(
                    f"{symbol} ({meth_key}): {result.get('radar_rationale', 'N/A')}"
                )
            
            # Rate limiting between full debates
            time.sleep(2.0)
        
        # Select methodology basket
        basket = select_methodology_basket(meth_key, debate_results)
        tier1_results[meth_key] = basket
        
        log.info(f"\n[{meth_key}] Basket: {len(basket['picks'])} picks selected "
                 f"from {basket['total_candidates']} candidates "
                 f"({basket['radar_filtered']} radar-filtered)")
    
    # ── Funnel integrity assertion ─────────────────────────────────────────
    expected = stats["cache_hits"] + stats["no_transcript"] + stats["fully_debated"]
    if expected != stats["unique_symbols"]:
        log.warning(f"Funnel mismatch: {expected} != {stats['unique_symbols']} unique_symbols")
    
    return {"baskets": tier1_results, "stats": stats, "cache": cache}


# ── Full Pipeline Orchestrator ───────────────────────────────────────────
def debate_and_allocate(before_date: str = None, dry_run: bool = False) -> dict:
    """Full Tier 1 + Tier 2 pipeline.
    
    Loads methodology_picks.json → runs per-methodology debates →
    runs Director allocation → writes speculair_baskets.json.
    """
    log.info("=" * 70)
    log.info("SPECULAIR DEBATE PIPELINE — STARTING")
    log.info("=" * 70)
    
    # 1. Load methodology picks from GCS (primary) or local (fallback)
    picks_data = _load_methodology_picks()
    if not picks_data:
        log.error("Could not load methodology_picks.json — aborting")
        return {}
    
    last_updated = picks_data.get("last_updated", "")
    log.info(f"Loaded methodology picks (last_updated: {last_updated})")
    
    # 2. Run Tier 1 — per-methodology debates
    tier1 = run_tier1(picks_data, before_date=before_date, dry_run=dry_run)
    tier1_baskets = tier1["baskets"]
    tier1_stats = tier1["stats"]
    
    log.info(f"\n{'='*60}")
    log.info(f"TIER 1 COMPLETE — {len(tier1_baskets)} methodology baskets")
    log.info(f"Stats: {tier1_stats}")
    log.info(f"{'='*60}")
    
    # 3. Run Tier 2 — Director allocation
    try:
        from live_director_agent import run_director_allocation
        director_result = run_director_allocation(tier1_baskets, dry_run=dry_run)
    except ImportError:
        log.warning("live_director_agent.py not found — using Tier 1 results only")
        director_result = _fallback_director(tier1_baskets)
    except Exception as e:
        log.error(f"Director allocation failed: {e}")
        director_result = _fallback_director(tier1_baskets)
    
    # 4. Assemble output
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rebalance_date = before_date or today
    
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rebalance_date": rebalance_date,
        "apex_basket": director_result.get("apex_basket", []),
        "capitulation_watchlist": director_result.get("capitulation_watchlist", []),
        "per_methodology_baskets": {},
        "director_memo": director_result.get("director_memo", ""),
        "debate_stats": {
            "total_picks": tier1_stats["total_picks"],
            "unique_symbols": tier1_stats["unique_symbols"],
            "cache_hits": tier1_stats["cache_hits"],
            "no_transcript": tier1_stats["no_transcript"],
            "fully_debated": tier1_stats["fully_debated"],
            "radar_alerted": tier1_stats["radar_alerted"],
            "radar_filtered": tier1_stats["radar_filtered"],
            "radar_filtered_names": tier1_stats["radar_filtered_names"],
            "auto_vetoed": director_result.get("auto_vetoed", 0),
            "apex_selected": len(director_result.get("apex_basket", [])),
        }
    }
    
    # Per-methodology baskets
    for meth_key, basket in tier1_baskets.items():
        output["per_methodology_baskets"][meth_key] = {
            "picks": [
                {
                    "symbol": p.get("symbol", ""),
                    "conviction": p.get("conviction", 0),
                    "verdict": p.get("verdict", ""),
                    "bull_thesis": p.get("bull_thesis", ""),
                    "bear_thesis": p.get("bear_thesis", ""),
                    "forcing_function": p.get("forcing_function", ""),
                    "consensus_delta": p.get("consensus_delta", ""),
                }
                for p in basket.get("picks", [])
            ],
            "moderator_memo": basket.get("moderator_memo", ""),
            "total_candidates": basket.get("total_candidates", 0),
            "radar_filtered": basket.get("radar_filtered", 0),
        }
    
    # 5. Write output
    _write_output(output, dry_run=dry_run)
    
    log.info("=" * 70)
    log.info("SPECULAIR DEBATE PIPELINE — COMPLETE")
    log.info(f"Apex Basket: {[p.get('symbol') for p in output['apex_basket']]}")
    log.info(f"Capitulation WL: {[p.get('symbol') for p in output['capitulation_watchlist']]}")
    log.info("=" * 70)
    
    return output


def _load_methodology_picks() -> Optional[dict]:
    """Load methodology picks from GCS or local file."""
    # Try GCS first
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        data = gcs_download("scans/methodology_picks.json")
        if data and data.get("methodologies"):
            return data
    except Exception as e:
        log.debug(f"GCS download failed: {e}")
    
    # Fallback to local
    local = FRONTEND_DIR / "public" / "methodology_picks.json"
    if local.exists():
        try:
            with open(local, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("methodologies"):
                return data
        except Exception as e:
            log.error(f"Local picks load failed: {e}")
    
    return None


def _fallback_director(tier1_baskets: dict) -> dict:
    """Simple fallback when Director agent is unavailable.
    Takes top picks across all methodologies by conviction."""
    all_picks = []
    seen = set()
    
    for meth_key, basket in tier1_baskets.items():
        for p in basket.get("picks", []):
            sym = p.get("symbol", "")
            if sym and sym not in seen:
                seen.add(sym)
                pick = dict(p)
                pick["source_methodologies"] = [meth_key]
                all_picks.append(pick)
            elif sym in seen:
                # Add methodology attribution
                for ap in all_picks:
                    if ap.get("symbol") == sym:
                        ap.setdefault("source_methodologies", []).append(meth_key)
                        break
    
    # Sort by conviction, take top 7
    all_picks.sort(key=lambda x: (-x.get("conviction", 0), -x.get("interrogator_score", 0)))
    
    apex = all_picks[:7]
    capitul = [p for p in all_picks[7:12] if p.get("conviction", 0) >= 3]
    
    for p in apex:
        p["entry_price"] = p.get("price", 0)
        p["entry_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        p["director_rationale"] = "Fallback allocation — Director unavailable"
    
    return {
        "apex_basket": apex,
        "capitulation_watchlist": capitul,
        "director_memo": "Fallback allocation — Director agent not available. "
                         "Picks selected by raw conviction score from Tier 1 debates.",
        "auto_vetoed": 0,
    }


def _write_output(output: dict, dry_run: bool = False):
    """Write speculair_baskets.json to GCS and local."""
    if dry_run:
        log.info("[Dry Run] Would write speculair_baskets.json")
        # Still write local for inspection
        local = FRONTEND_DIR / "public" / "speculair_baskets.json"
        with open(local, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        log.info(f"Wrote local: {local}")
        return
    
    # Local
    local = FRONTEND_DIR / "public" / "speculair_baskets.json"
    try:
        with open(local, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        log.info(f"Wrote local: {local}")
    except Exception as e:
        log.error(f"Local write failed: {e}")
    
    # GCS
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_upload
        if gcs_upload("scans/speculair_baskets.json", output):
            log.info("Wrote GCS: scans/speculair_baskets.json")
        else:
            log.warning("GCS upload of speculair_baskets.json returned False")
    except Exception as e:
        log.warning(f"GCS upload failed: {e}")


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Speculair Multi-Agent Debate Pipeline")
    ap.add_argument("--run-full", action="store_true",
                    help="Run full Tier 1 + Tier 2 pipeline")
    ap.add_argument("--dry-run", action="store_true",
                    help="No LLM calls — use cached results only")
    ap.add_argument("--before-date", type=str, default=None,
                    help="Only use transcripts before this date (for backfill)")
    ap.add_argument("--single", type=str, default=None,
                    help="Debug: debate a single symbol")
    args = ap.parse_args()
    
    if args.single:
        # Debug mode: debate a single symbol
        load_api_keys()
        transcript = resolve_transcript(args.single)
        if transcript:
            result = debate_candidate(args.single, transcript)
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"No transcript found for {args.single}")
    elif args.run_full or args.dry_run:
        load_api_keys()
        debate_and_allocate(before_date=args.before_date, dry_run=args.dry_run)
    else:
        ap.print_help()
