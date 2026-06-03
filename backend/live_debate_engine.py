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
import re
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
    "earnings_yield_gap", "acquirers_multiple",
    "convergence",            # 10th: cross-method valuation agreement (screener_v6)
    "fundamental_momentum",   # 11th: physical hard-tech momentum, growth lens (screener_v6)
]

# ── Radar Mode Router ────────────────────────────────────────────────────
# Value-oriented methodologies get the value_trap_audit prompt;
# growth/catalyst methodologies get the growth_catalyst prompt.
VALUE_METHODOLOGIES = {"epv", "iv15_deep_value", "acquirers_multiple", "convergence"}

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


def resolve_transcripts(symbol: str, before_date: str = None,
                        max_transcripts: int = 8) -> dict:
    """Resolve up to *max_transcripts* earnings-call transcripts for symbol.

    Returns a dict with contract fields:
        transcript_count  (int)  : number of transcripts available (0..8)
        transcript_dates  (list) : e.g. ["2025-Q3", "2025-Q2", ...]
        all_transcripts   (list) : list of transcript dicts (date, content,
                                   filename, source), sorted descending by date

    Strategy:
        1. Read ALL matching files from local cache.
        2. Determine which (year, quarter) pairs we already have.
        3. Fetch missing quarters from FMP until we reach *max_transcripts*.
        4. Sort descending by date, trim to *max_transcripts*.
    """
    # ── 1. Gather everything already in the local cache ─────────────────
    cached = _resolve_all_from_cache(symbol, before_date)
    cached_keys: set[str] = set()
    for t in cached:
        # Derive a "YYYY-QN" key from filename (e.g. AAPL_2025Q3.json)
        fn = t.get("filename", "")
        if "Q" in fn:
            key_part = fn.replace(".json", "").split("_", 1)[-1]  # "2025Q3"
            cached_keys.add(key_part)

    all_transcripts: list[dict] = list(cached)

    # ── 2. Fetch missing quarters from FMP ──────────────────────────────
    if len(all_transcripts) < max_transcripts:
        fmp_key = get_key("FMP_API_KEY")
        if fmp_key:
            now = datetime.now()
            url = "https://financialmodelingprep.com/stable/earning-call-transcript"
            # Scan current year back to (current-2), all 4 quarters
            for y in range(now.year, now.year - 3, -1):
                for q in [4, 3, 2, 1]:
                    yq_key = f"{y}Q{q}"
                    if yq_key in cached_keys:
                        continue  # already have this quarter
                    if len(all_transcripts) >= max_transcripts:
                        break
                    try:
                        r = requests.get(
                            url,
                            params={"symbol": symbol, "year": y,
                                    "quarter": q, "apikey": fmp_key},
                            timeout=20,
                        )
                        if r.status_code != 200:
                            continue
                        data = r.json()
                        if not isinstance(data, list) or not data:
                            continue
                        entry = data[0]
                        t_date = entry.get("date", "")
                        t_content = entry.get("content", "")
                        if not (t_date and t_content and len(t_content) > 100):
                            continue
                        if before_date and t_date[:10] > before_date:
                            continue
                        # Cache the fetched transcript
                        cache_name = f"{symbol}_{y}Q{q}.json"
                        cache_path = TRANSCRIPT_CACHE_DIR / cache_name
                        if not cache_path.exists():
                            TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                            with open(cache_path, "w", encoding="utf-8") as fh:
                                json.dump({"payload": [entry]}, fh)
                        all_transcripts.append({
                            "date": t_date[:10],
                            "content": t_content,
                            "filename": cache_name,
                            "source": "fmp_api",
                        })
                    except Exception:
                        pass  # best-effort; skip failed quarters
                if len(all_transcripts) >= max_transcripts:
                    break

    # ── 3. Sort descending by date and trim ─────────────────────────────
    all_transcripts.sort(key=lambda x: x["date"], reverse=True)
    all_transcripts = all_transcripts[:max_transcripts]

    # ── 4. Build contract fields ────────────────────────────────────────
    transcript_dates: list[str] = []
    for t in all_transcripts:
        fn = t.get("filename", "")
        if "Q" in fn:
            raw = fn.replace(".json", "").split("_", 1)[-1]  # "2025Q3"
            yr, qr = raw.split("Q", 1)
            transcript_dates.append(f"{yr}-Q{qr}")
        else:
            transcript_dates.append(t["date"][:7])  # fallback YYYY-MM

    return {
        "transcript_count": len(all_transcripts),
        "transcript_dates": transcript_dates,
        "all_transcripts": all_transcripts,
    }


def _resolve_all_from_cache(symbol: str,
                            before_date: str = None) -> list[dict]:
    """Return ALL cached transcripts for *symbol* (not just the latest)."""
    if not TRANSCRIPT_CACHE_DIR.exists():
        return []
    results: list[dict] = []
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
                            results.append({
                                "date": t_date[:10],
                                "content": t_content,
                                "filename": f.name,
                                "source": "cache",
                            })
        except Exception:
            pass
    return results


def _resolve_from_cache(symbol: str, before_date: str = None) -> Optional[dict]:
    """Find latest cached transcript for symbol, optionally before a date."""
    all_cached = _resolve_all_from_cache(symbol, before_date)
    if all_cached:
        all_cached.sort(key=lambda x: x["date"], reverse=True)
        return all_cached[0]
    return None


def _fetch_from_fmp(symbol: str, before_date: str = None) -> Optional[dict]:
    """Fetch latest transcript from FMP API and cache it."""
    fmp_key = get_key("FMP_API_KEY")
    if not fmp_key:
        log.warning(f"FMP_API_KEY not set — cannot fetch transcript for {symbol}")
        return None
    
    try:
        now = datetime.now()
        year = now.year
        url = f"https://financialmodelingprep.com/stable/earning-call-transcript"
        
        # Try current year and previous year quarters
        for q in [4, 3, 2, 1]:
            for y in [year, year - 1]:
                r = requests.get(url, params={"symbol": symbol, "year": y, "quarter": q, "apikey": fmp_key}, timeout=20)
                if r.status_code != 200:
                    continue
                data = r.json()
                if not isinstance(data, list) or not data:
                    continue
                
                entry = data[0]
                t_date = entry.get("date", "")
                t_content = entry.get("content", "")
                if t_date and t_content and len(t_content) > 100:
                    if before_date is None or t_date[:10] <= before_date:
                        # Cache it
                        quarter = entry.get("quarter", "")
                        year_val = entry.get("year", "")
                        cache_name = f"{symbol}_{year_val}Q{quarter}.json"
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
    # 1. Try local first (fast path)
    if DEBATE_CACHE_FILE.exists():
        try:
            with open(DEBATE_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache:
                log.info(f"Loaded debate cache from local ({len(cache)} entries)")
                return cache
        except Exception as e:
            log.error(f"Error reading local debate cache: {e}")
    
    # 2. Fallback to GCS (Cloud Run cold start recovery)
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        gcs_cache = gcs_download("scans/debate_cache.json")
        if gcs_cache and isinstance(gcs_cache, dict):
            log.info(f"Loaded debate cache from GCS ({len(gcs_cache)} entries)")
            # Write to local for subsequent fast reads
            try:
                tmp = DEBATE_CACHE_FILE.with_suffix(".json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(gcs_cache, f, indent=2)
                tmp.replace(DEBATE_CACHE_FILE)
            except Exception as le:
                log.error(f"Error saving cached GCS to local debate cache: {le}")
            return gcs_cache
    except Exception as e:
        log.debug(f"GCS debate cache download failed: {e}")
    
    log.info("No debate cache found — starting fresh")
    return {}

def save_debate_cache(cache: dict):
    # Local write (atomic)
    try:
        tmp = DEBATE_CACHE_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        tmp.replace(DEBATE_CACHE_FILE)
    except Exception as e:
        log.error(f"Error saving local debate cache: {e}")
    
    # GCS write on every save (user request: every debate is stored in GCS)
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_upload
        gcs_upload("scans/debate_cache.json", cache)
        log.info(f"Synced debate cache to GCS ({len(cache)} entries)")
    except Exception as e:
        log.debug(f"GCS debate cache upload failed: {e}")


def save_dossier(symbol: str, transcript_date: str, result: dict):
    """Persist a single completed dossier to its OWN object the instant the agents finish —
    so an expensive run's spend is never lost even if a later step crashes. Writes a LOCAL
    file always (works without cloud creds) AND uploads to GCS when credentials exist.
    Best-effort: failures are logged, never raised."""
    safe = f"{symbol}__{transcript_date}".replace("/", "_")
    try:
        ddir = BASE_DIR / "dossiers"
        ddir.mkdir(exist_ok=True)
        with open(ddir / f"{safe}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
    except Exception as e:
        log.debug(f"Local dossier write failed for {symbol}: {e}")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_upload
        gcs_upload(f"dossiers/{safe}.json", result)
    except Exception as e:
        log.debug(f"Dossier GCS upload failed for {symbol}: {e}")


def _is_fresh_cache(entry: dict) -> bool:
    """A debate-cache entry is valid only if it carries a real bull thesis AND the new opus
    interrogator_dossier — so pre-rebuild (gemini-era) entries miss the cache and get
    re-debated with the upgraded pipeline."""
    if not isinstance(entry, dict):
        return False
    return (entry.get("bull_thesis") not in (None, "", "API Timeout/Failure")
            and bool(entry.get("interrogator_dossier")))


def _load_existing_speculair() -> dict:
    """Best-effort load of the current speculair_baskets.json — for portfolio continuity
    (held positions) and the director cost-guard. Returns {} if unavailable."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        d = gcs_download("scans/speculair_baskets.json")
        if isinstance(d, dict):
            return d
    except Exception as e:
        log.debug(f"existing speculair load failed: {e}")
    return {}


def run_macro_strategist(candidate_sectors: dict, before_date: str = None) -> str:
    """Once-per-scan macro regime brief for the director (opus). Tilts toward the sectors
    where the debated opportunities cluster. Returns markdown, or '' on failure (the
    director still runs without it). NOTE: reflects the model's macro knowledge; wiring a
    live rates/inflation/breadth data feed is a planned enhancement."""
    sectors = ", ".join(f"{s} ({n})" for s, n in sorted(candidate_sectors.items(), key=lambda x: -x[1])) or "n/a"
    day = before_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system = (
        "You are the Macro Strategist for a high-conviction equity committee. Write a concise, "
        "decision-useful MACRO REGIME BRIEF for the portfolio director: the rates / inflation / growth "
        "backdrop and its trajectory, the dominant risk-on vs risk-off posture, and explicit "
        "tailwind/headwind calls for the sectors where this cycle's opportunities cluster. Be specific "
        "about what would flip the regime. No hedging filler."
    )
    user = (
        f"Today is {day}. The debated opportunity set clusters in these sectors (name + count): {sectors}.\n"
        "Provide: (1) the macro regime in 3-5 sentences; (2) a per-sector tailwind/headwind line for the "
        "clustered sectors; (3) the single macro risk the director should most avoid clustering the basket around."
    )
    return query_claude(MACRO_MODEL, system, user, max_tokens=3000) or ""


# ── LLM Calling Helpers ─────────────────────────────────────────────────
def query_gemini(model_name: str, system_prompt: str, user_prompt: str,
                 response_schema=None, max_attempts: int = 4) -> Optional[dict]:
    """Call Gemini API via REST with structured JSON output."""
    api_key = get_key("GEMINI_API_KEY") or get_key("GOOGLE_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY not found")
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }
    
    for attempt in range(max_attempts):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code == 200:
                rj = r.json()
                text = rj["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
                    first_line = lines[0].strip()
                    if first_line.startswith("```json") or text.startswith("json"):
                        if text.startswith("json"):
                            text = text[4:].strip()
                res = json.loads(text.strip())
                if isinstance(res, list) and res:
                    res = res[0]
                return res
            else:
                log.error(f"Gemini API REST error: {r.status_code} - {r.text}")
                time.sleep(3.0)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "quota" in err or "overloaded" in err:
                sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                log.warning(f"Gemini rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                time.sleep(sleep)
            else:
                log.error(f"Gemini {model_name} REST error: {e}")
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
    is_reasoning = (model.startswith("o1-") or model.startswith("o3-") or model.startswith("gpt-5"))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_completion_tokens": 12000 if is_reasoning else 1500,
        "response_format": {"type": "json_object"}
    }
    if not is_reasoning:
        payload["temperature"] = 0.1

    
    for attempt in range(max_attempts):
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                              headers=headers, json=payload, timeout=300)  # gpt-5.x reasoning runs 100-180s
            rj = r.json()
            if "choices" in rj and rj["choices"]:
                text = rj["choices"][0]["message"]["content"].strip()
                try:
                    cleaned_text = text
                    if cleaned_text.startswith("```"):
                        lines = cleaned_text.split("\n")
                        # Remove first line (the ``` or ```json) and last line (```)
                        first_line = lines[0].strip()
                        cleaned_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
                        # If first line had "json", make sure we don't have stray characters
                        if first_line.startswith("```json") or cleaned_text.startswith("json"):
                            if cleaned_text.startswith("json"):
                                cleaned_text = cleaned_text[4:].strip()
                    res = json.loads(cleaned_text.strip())
                    if isinstance(res, list) and res:
                        res = res[0]
                    return res
                except Exception as je:
                    log.error(f"Failed to parse OpenAI JSON response: {je}. Raw response: {text!r}")
                    time.sleep(3.0)
            else:
                log.error(f"OpenAI error: {rj}")
                time.sleep(3.0)
        except Exception as e:
            log.error(f"OpenAI {model} error: {e}")
            time.sleep(3.0 * (attempt + 1))

    return None


# ── Model assignment (capital-allocation rebuild) ────────────────────────
# Each step runs on the model best suited to it; no token caps on the output.
INTERROGATOR_MODEL = "claude-opus-4-8"   # forensic transcript dossier (also user-facing)
ARCHITECT_MODEL    = "gpt-5.5"           # probabilistic bull/bear
MODERATOR_MODEL    = "gpt-5.5"           # risk / timing / expectations
MACRO_MODEL        = "claude-opus-4-8"   # once-per-scan macro regime brief
ANTHROPIC_1M_BETA  = "context-1m-2025-08-07"
DIRECTOR_CADENCE_DAYS = 30   # director re-reviews the basket at most ~monthly (plus on held-name earnings)


def query_claude(model: str, system_prompt: str, user_prompt: str,
                 max_tokens: int = 8000, max_attempts: int = 4,
                 expect_json: bool = False, beta_1m: bool = False):
    """Call Anthropic Claude. Returns response TEXT (markdown) by default, or a parsed
    dict when expect_json=True. Used for the Interrogator dossier, the Macro Strategist,
    and any Claude-backed step. Loads ANTHROPIC_API_KEY via get_key (overrides the empty
    shadow some runtimes inject). Returns None on persistent failure."""
    api_key = get_key("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found")
        return None
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if beta_1m:
        headers["anthropic-beta"] = ANTHROPIC_1M_BETA
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    for attempt in range(max_attempts):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=payload, timeout=600)
            if r.status_code != 200:
                log.error(f"Claude {model} HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(3.0 * (attempt + 1))
                continue
            d = r.json()
            text = "".join(b.get("text", "") for b in d.get("content", [])
                           if b.get("type") == "text").strip()
            if not text:
                log.error(f"Claude {model} empty response: {str(d)[:200]}")
                time.sleep(3.0)
                continue
            if not expect_json:
                return text
            t = text
            if t.startswith("```"):
                lines = t.split("\n")
                t = "\n".join(lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:])
                if t.strip().startswith("json"):
                    t = t.strip()[4:]
            try:
                return json.loads(t.strip())
            except Exception:
                m = re.search(r"\{.*\}", t, re.DOTALL)
                if m:
                    return json.loads(m.group(0))
                raise
        except Exception as e:
            log.error(f"Claude {model} error: {e}")
            time.sleep(3.0 * (attempt + 1))
    return None


def _openai_health_check() -> bool:
    """Quick connectivity/auth check before the main debate loop.
    Sends a minimal prompt to gpt-5.5 to verify the API key works.
    Returns True if healthy, False otherwise.
    """
    api_key = get_key("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY not set — OpenAI agents will fail")
        return False
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-5.5",
                "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
                "max_completion_tokens": 5,
            },
            timeout=15,
        )
        rj = r.json()
        if "choices" in rj:
            log.info("OpenAI health check: OK")
            return True
        err = rj.get("error", {}).get("message", str(rj))
        log.error(f"OpenAI health check FAILED: {err}")
        return False
    except Exception as e:
        log.error(f"OpenAI health check FAILED: {e}")
        return False


# ── Agent System Prompts ─────────────────────────────────────────────────
import typing_extensions as typing

class RadarOutput(typing.TypedDict):
    alert: bool
    signal_type: str
    rationale: str

class InterrogatorOutput(typing.TypedDict):
    credibility_score: int
    findings: str
    narrative_arc: str
    tone_shift: str
    guidance_credibility: int

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

INTERROGATOR_SYSTEM_PROMPT = """You are the Interrogator — a forensic equity analyst on an investment committee allocating REAL capital. You receive multiple consecutive quarterly earnings-call transcripts for a company (up to 8 quarters) AND its actual financial trajectory from our screener.

Management's words are the hypothesis; the financials are the evidence. Extract what ONLY the transcripts reveal — the evolution of management's thinking, tone, and credibility over time — and rigorously CROSS-REFERENCE every major narrative claim against the hard numbers provided. This dossier is read by a portfolio director deciding whether to commit capital, AND it is shown to investors on the stock page, so be specific, quote brief phrases with exact quarter references, write clear well-structured prose, and do not hedge. There is no length limit — be as thorough as the evidence warrants.

Produce a markdown dossier with these sections:

## 1. NARRATIVE ARC
How the core story evolved across the quarters: what was emphasized at the start vs now, thesis shifts / expansion / contraction, growth drivers introduced or quietly dropped.

## 2. CLAIMS vs FINANCIALS (forensic)
Take management's biggest claims (growth, margins, demand, capital allocation) and test each against the ACTUAL FINANCIALS block. Where does the narrative match the numbers? Where does it diverge? Call out where the story is richer or poorer than the trajectory justifies. Use a table where it helps.

## 3. TONE & CONFIDENCE TRAJECTORY
Rate the trajectory (Rising / Stable / Declining) with quoted evidence per quarter. More or less specific with guidance over time? Any shift from offensive (growth / investment) to defensive (efficiency / cost / macro) language?

## 4. GUIDANCE CREDIBILITY
Track guidance given in earlier calls vs results delivered in later calls. Did they deliver, over-deliver, or miss? Reconcile with the earnings-beat rate in the financials. Any sandbagging pattern? Score reliability High / Medium / Low.

## 5. ANALYST PRESSURE POINTS
Recurring questions management deflects or non-answers; topics analysts pushed on that later turned into bad news; what analysts worry about that management isn't addressing.

## 6. RED FLAGS / GREEN FLAGS
🔴 concerning shifts and 🟢 positive evolution — each with specific quarter references.

## 7. HIDDEN SIGNALS
Subtle terminology shifts, changes in how they discuss competition or capital allocation, management changes and what new voices say differently.

## 8. CAPITAL-ALLOCATION VERDICT (for the director)
Classify the trajectory: STRENGTHENING / STABLE / DETERIORATING / PIVOTING. State the single most important thing the director must weigh before sizing a position.

After the dossier, output one final line in EXACTLY this format for machine parsing (nothing after it):
CREDIBILITY_SCORE: <integer 1-5> | TRAJECTORY: <STRENGTHENING|STABLE|DETERIORATING|PIVOTING>
where credibility_score is 1 (evasive / unsupported by financials) to 5 (highly credible, corroborated by financials).
"""

ARCHITECT_SYSTEM_PROMPT = """You are the Architect — a System-2 reasoning engine on an investment committee allocating REAL capital. Using the Interrogator's forensic dossier, the financial metrics, and the transcript, construct a rigorous, probabilistically-weighted Bull case and Bear case. Map how the macro and competitive environment impacts the company's moat or event-driven catalyst. Ground every argument in the specific evidence provided — cite the real financials (revenue/margin/EPS/FCF trajectory, returns, leverage, valuation) and quote transcript phrases with quarter references. State the key conditions each case depends on. Be thorough; there is no length limit.

You must output a JSON object:
{
  "bull_thesis": "The full bullish argument — the strongest evidence-grounded case for why this works, the catalysts, and the specific conditions that must hold.",
  "bear_thesis": "The full bearish argument — the strongest evidence-grounded case for why this fails, the specific risks, and what would confirm them."
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
  "consensus_delta": "string — the full expectations-arbitrage analysis; quote the exact street assumptions that are wrong and why. No length limit.",
  "valley_of_death": "string — the full near-term (3-9 month) risk analysis: cash-burn humps, maturities, macro headwinds that hit before the catalyst. No length limit.",
  "positioning_washout": "string — the full analysis of forced/mechanical selling dynamics in the shareholder base. No length limit.",
  "forcing_function": "string — the exact hard date(s), proxy window, or corporate event that forces a re-rating, and why. No length limit.",
  "moderator_conclusion": "string — your full synthesis, timing call, and narrative summary. No length limit."
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.

IMPORTANT — Signal-Type Branching:
The Radar Agent has classified this candidate with a signal_type:
- If signal_type is "innovation" or "catalyst": evaluate through the growth/catalyst lens above.
- If signal_type is "deep_value": shift your framework. The Consensus Delta becomes "Is the street pricing terminal decline into a company with stable/growing earnings power?" The Valley of Death becomes "Is there a liquidation event, debt maturity, or forced selling that could kill the thesis before MOS converges?" The Forcing Function becomes "What event (buyback authorization, activist, asset sale, dividend initiation) will force the market to re-rate?"
- If signal_type is "trap" or "none": assign conviction ≤ 2 and verdict C unless extraordinary override evidence exists.
"""


# ── Single-Candidate Debate ─────────────────────────────────────────────
MAX_CHARS_PER_TRANSCRIPT = 18_000  # hard cap per individual transcript block

# Scan fields threaded into the debate metrics block (Caveat 1 forensic grounding).
_SCAN_FIN_FIELDS = [
    "revenue_yoy", "revenue_cagr_3y", "gross_margin", "gross_margin_trend",
    "net_margin", "fcf_margin", "eps_latest", "eps_yoy", "eps_cagr_3y",
    "eps_beats", "eps_total", "fcf_yoy", "fcf_cagr_3y", "p_fcf", "roe_avg",
    "roic_avg", "net_debt", "forward_eps_growth", "peak_margin_sigma",
    "insider_buy_ratio", "margin_of_safety", "buffett_fair_value", "sector",
]


def _slice_transcript(content: str, cap: int = MAX_CHARS_PER_TRANSCRIPT) -> str:
    """Truncate a transcript to *cap* chars while preserving BOTH ends.

    Earnings calls run prepared-remarks-first, analyst-Q&A-last. A naive head slice
    (content[:cap]) keeps the scripted narrative but drops the Q&A — exactly where
    management evasiveness, non-answers, and guidance-delivery signal live. So when
    truncation is needed, keep ~55% head + ~45% tail so both survive (Caveat 2 fix).
    """
    if not content:
        return ""
    if len(content) <= cap:
        return content
    head = int(cap * 0.55)
    tail = cap - head
    return (content[:head]
            + "\n\n[... mid-call omitted for length — prepared remarks above, analyst Q&A below ...]\n\n"
            + content[-tail:])


def _fmt_pct(v, scale: float = 100.0, signed: bool = True):
    """Format a fraction (0.035) as a percent string ('+3.5%'). None if not numeric."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return f"{v * scale:+.1f}%" if signed else f"{v * scale:.1f}%"


def _fmt_amt(v):
    """Format an absolute currency amount with B/M suffix. None if not numeric."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e6:
        return f"{v / 1e6:.0f}M"
    return f"{v:.0f}"


def _build_debate_metrics(financials: dict = None, scan_fin: dict = None) -> str:
    """Forensic-grounding metrics block for Interrogator/Architect/Moderator.

    Combines the methodology candidate's valuation fields with the screener scan's
    already-computed fundamentals (growth, margins, returns, leverage) plus a
    multi-year revenue/earnings series, so agents can cross-reference transcript
    claims against real financial trajectory instead of the bare 7-field stub
    (Caveat 1 fix). Degrades to the compact stub when scan data is absent.
    """
    financials = financials or {}
    scan_fin = scan_fin or {}

    # No scan grounding available — preserve the legacy compact behaviour.
    if not scan_fin:
        fields = ["price", "sector", "market_cap", "mos", "fair_value", "entry_metric", "weight"]
        m = {k: financials.get(k) for k in fields if financials.get(k) is not None}
        return json.dumps(m, indent=2, default=str) if m else "No financial metrics available."

    g = scan_fin.get
    lines = []
    sector = financials.get("sector") or g("sector")
    if sector:
        lines.append(f"Sector: {sector}")

    val = []
    if financials.get("price") is not None:
        val.append(f"Price {financials['price']}")
    fv = financials.get("fair_value") if financials.get("fair_value") is not None else g("buffett_fair_value")
    if fv is not None:
        val.append(f"Fair Value {fv}")
    mos = financials.get("mos") if financials.get("mos") is not None else g("margin_of_safety")
    if isinstance(mos, (int, float)) and not isinstance(mos, bool):
        val.append(f"Margin of Safety {mos * 100:.0f}%" if abs(mos) < 5 else f"Margin of Safety {mos:.0f}%")
    if isinstance(g("p_fcf"), (int, float)):
        val.append(f"P/FCF {g('p_fcf'):.1f}x")
    if val:
        lines.append("Valuation: " + " | ".join(val))

    rev = []
    if _fmt_pct(g("revenue_yoy")):
        rev.append(f"{_fmt_pct(g('revenue_yoy'))} YoY")
    if _fmt_pct(g("revenue_cagr_3y")):
        rev.append(f"3-yr CAGR {_fmt_pct(g('revenue_cagr_3y'))}")
    if rev:
        lines.append("Revenue growth: " + " | ".join(rev))

    mg = []
    gm = _fmt_pct(g("gross_margin"), signed=False)
    if gm:
        trend = g("gross_margin_trend")
        mg.append(f"Gross {gm}" + (f" ({trend})" if trend else ""))
    if _fmt_pct(g("net_margin"), signed=False):
        mg.append(f"Net {_fmt_pct(g('net_margin'), signed=False)}")
    if _fmt_pct(g("fcf_margin"), signed=False):
        mg.append(f"FCF {_fmt_pct(g('fcf_margin'), signed=False)}")
    if mg:
        lines.append("Margins: " + " | ".join(mg))

    eps = []
    if g("eps_latest") is not None:
        eps.append(f"{g('eps_latest')} latest")
    if _fmt_pct(g("eps_yoy")):
        eps.append(f"{_fmt_pct(g('eps_yoy'))} YoY")
    if _fmt_pct(g("eps_cagr_3y")):
        eps.append(f"3-yr CAGR {_fmt_pct(g('eps_cagr_3y'))}")
    beats, total = g("eps_beats"), g("eps_total")
    if isinstance(beats, (int, float)) and isinstance(total, (int, float)) and total:
        eps.append(f"beat {int(beats)}/{int(total)} qtrs ({beats / total * 100:.0f}%)")
    if eps:
        lines.append("EPS / guidance delivery: " + " | ".join(eps))

    fcf = []
    if _fmt_pct(g("fcf_yoy")):
        fcf.append(f"{_fmt_pct(g('fcf_yoy'))} YoY")
    if _fmt_pct(g("fcf_cagr_3y")):
        fcf.append(f"3-yr CAGR {_fmt_pct(g('fcf_cagr_3y'))}")
    if fcf:
        lines.append("FCF growth: " + " | ".join(fcf))

    ret = []
    if _fmt_pct(g("roe_avg"), signed=False):
        ret.append(f"ROE {_fmt_pct(g('roe_avg'), signed=False)}")
    if _fmt_pct(g("roic_avg"), signed=False):
        ret.append(f"ROIC {_fmt_pct(g('roic_avg'), signed=False)}")
    if _fmt_amt(g("net_debt")) is not None:
        ret.append(f"Net debt {_fmt_amt(g('net_debt'))}")
    if ret:
        lines.append("Returns / leverage: " + " | ".join(ret))

    fwd = []
    if _fmt_pct(g("forward_eps_growth")):
        fwd.append(f"Consensus fwd EPS growth {_fmt_pct(g('forward_eps_growth'))}")
    if isinstance(g("peak_margin_sigma"), (int, float)):
        fwd.append(f"Margin {g('peak_margin_sigma'):.2f}sigma vs hist. peak")
    if isinstance(g("insider_buy_ratio"), (int, float)):
        fwd.append(f"Insider buy ratio {g('insider_buy_ratio'):.2f}")
    if fwd:
        lines.append("Forward / signals: " + " | ".join(fwd))

    rows = (scan_fin.get("history_rows") or [])[-5:]
    if rows:
        traj = ["Multi-year trajectory (fiscal yr - revenue / net income / EPS):"]
        for r in rows:
            rv = _fmt_amt((r.get("revenue_mm") or 0) * 1e6) if r.get("revenue_mm") is not None else "N/A"
            ni = _fmt_amt((r.get("net_income_mm") or 0) * 1e6) if r.get("net_income_mm") is not None else "N/A"
            traj.append(f"  {r.get('year')}: rev {rv}, NI {ni}, EPS {r.get('eps')}")
        cagrs = scan_fin.get("history_cagrs") or {}
        cg = ", ".join(f"{k} {_fmt_pct(v)}" for k, v in cagrs.items() if isinstance(v, (int, float)))
        if cg:
            traj.append(f"  CAGRs: {cg}")
        lines.append("\n".join(traj))

    return "=== FUNDAMENTALS (screener scan, latest fiscal year unless noted) ===\n" + "\n".join(lines)


def debate_candidate(symbol: str, transcript: dict, financials: dict = None,
                     cache: dict = None, methodology_key: str = "",
                     multi_transcript_info: dict = None,
                     scan_financials: dict = None) -> dict:
    """Run 4-agent debate on a single candidate.
    
    Returns a debate result dict with conviction, theses, moderator synthesis,
    plus multi-transcript qualitative fields:
        transcript_count, transcript_dates, narrative_arc, tone_shift,
        guidance_credibility.
    Uses cache keyed by {symbol}|{transcript_date} to avoid re-debating.

    Args:
        multi_transcript_info: optional dict from resolve_transcripts() with
            transcript_count, transcript_dates, all_transcripts.
    """
    t_date = transcript["date"]
    cache_key = f"{symbol}|{t_date}"
    
    # Check cache
    if cache and cache_key in cache:
        cached = cache[cache_key]
        if _is_fresh_cache(cached):
            log.info(f"  [Cache Hit] {symbol} (transcript {t_date})")
            return cached
    
    t_content = _slice_transcript(transcript.get("content", ""), MAX_CHARS_PER_TRANSCRIPT)
    
    # ── Assemble multi-quarter transcript blocks ─────────────────────────
    # Each transcript is capped at MAX_CHARS_PER_TRANSCRIPT chars.
    transcript_blocks: list[str] = []
    mt_info = multi_transcript_info or {}
    all_tx = mt_info.get("all_transcripts", [transcript])
    tx_dates = mt_info.get("transcript_dates", [])
    tx_count = mt_info.get("transcript_count", 1)

    for idx, tx in enumerate(all_tx):
        label = tx_dates[idx] if idx < len(tx_dates) else tx.get("date", "unknown")
        content = _slice_transcript(tx.get("content", ""), MAX_CHARS_PER_TRANSCRIPT)
        transcript_blocks.append(
            f"--- Earnings Call: {label} (date: {tx.get('date', 'N/A')}) ---\n{content}"
        )

    multi_transcript_text = "\n\n".join(transcript_blocks)
    
    # Build financial metrics string — rich scan-grounded block when available
    # (Caveat 1 forensic grounding), else the compact stub.
    metrics_str = _build_debate_metrics(financials, scan_financials)
    
    result = {
        "symbol": symbol,
        "transcript_date": t_date,
        "transcript_filename": transcript.get("filename", ""),
        "transcript_count": tx_count,
        "transcript_dates": tx_dates,
        "radar_alert": False,
        "radar_rationale": "",
        "signal_type": "none",
        "methodology_key": methodology_key,
        "interrogator_score": 3,
        "interrogator_dossier": "",     # full markdown forensic dossier (opus) — director fuel + stock-page UI
        "trajectory": "",               # STRENGTHENING|STABLE|DETERIORATING|PIVOTING (parsed from dossier)
        "interrogator_findings": "",    # legacy/back-compat (mirrors dossier)
        "narrative_arc": "",
        "tone_shift": "stable",
        "guidance_credibility": 50,
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
    
    # ── 2. INTERROGATOR (opus-4-8) — multi-quarter forensic dossier ──────
    log.info(f"  [Interrogator:{INTERROGATOR_MODEL}] {symbol} ({tx_count} transcripts) ...")
    interr_user_prompt = (
        f"=== ACTUAL FINANCIALS (screener scan) ===\n{metrics_str}\n\n"
        f"Number of earnings-call transcripts provided: {tx_count}\n"
        f"Quarters covered: {', '.join(tx_dates) if tx_dates else t_date}\n\n"
        f"=== EARNINGS-CALL TRANSCRIPTS ({tx_count} quarters, chronological) ===\n{multi_transcript_text}"
    )
    interr_dossier = query_claude(
        INTERROGATOR_MODEL,
        INTERROGATOR_SYSTEM_PROMPT,
        interr_user_prompt,
        max_tokens=12000,
    )

    if interr_dossier:
        result["interrogator_dossier"] = interr_dossier
        result["interrogator_findings"] = interr_dossier  # back-compat: rich content
        m = re.search(r"CREDIBILITY_SCORE:\s*(\d+)", interr_dossier)
        result["interrogator_score"] = max(1, min(5, int(m.group(1)))) if m else 3
        mt = re.search(r"TRAJECTORY:\s*([A-Z]+)", interr_dossier)
        result["trajectory"] = mt.group(1) if mt else ""
        # Map trajectory -> legacy tone_shift for any consumer still reading it
        result["tone_shift"] = {"STRENGTHENING": "improving", "DETERIORATING": "deteriorating"}.get(
            result["trajectory"], "stable")
    else:
        log.warning(f"  [Interrogator] {symbol}: no dossier returned")

    time.sleep(1.0)
    
    # ── 3. ARCHITECT (gpt-5.5) — bull/bear, grounded in the dossier ──────
    log.info(f"  [Architect:{ARCHITECT_MODEL}] {symbol} ...")
    arch_prompt = (
        f"=== FINANCIAL METRICS ===\n{metrics_str}\n\n"
        f"=== INTERROGATOR FORENSIC DOSSIER ===\n{result['interrogator_dossier']}\n\n"
        f"=== MOST RECENT EARNINGS CALL ===\n{t_content}"
    )
    arch_out = query_openai(ARCHITECT_MODEL, ARCHITECT_SYSTEM_PROMPT, arch_prompt)

    if arch_out:
        result["bull_thesis"] = arch_out.get("bull_thesis", "")
        result["bear_thesis"] = arch_out.get("bear_thesis", "")

    time.sleep(1.0)
    
    # ── 4. MODERATOR (gpt-5.5 via OpenAI) ─────────────────────────────────
    log.info(f"  [Moderator] {symbol} ...")
    mod_prompt = (
        f"Company: {symbol}\n"
        f"Earnings Call Date: {t_date}\n"
        f"Radar Signal Type: {result['signal_type']}\n"
        f"Transcripts Available: {tx_count} ({', '.join(tx_dates) if tx_dates else t_date})\n\n"
        f"=== FINANCIAL METRICS ===\n{metrics_str}\n\n"
        f"=== INTERROGATOR FORENSIC DOSSIER ===\n"
        f"Credibility Score: {result['interrogator_score']}/5 | Trajectory: {result['trajectory']}\n"
        f"{result['interrogator_dossier']}\n\n"
        f"=== ARCHITECT BULL THESIS ===\n{result['bull_thesis']}\n\n"
        f"=== ARCHITECT BEAR THESIS ===\n{result['bear_thesis']}\n\n"
        f"=== MOST RECENT EARNINGS CALL ===\n{t_content}\n\n"
        f"Please run your final moderation synthesis and output the JSON result."
    )
    mod_out = query_openai(
        MODERATOR_MODEL,
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
    
    log.info(f"  [Result] {symbol}: verdict={result['verdict']} conviction={result['conviction']} "
             f"tone_shift={result['tone_shift']} guidance_cred={result['guidance_credibility']}")
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
              dry_run: bool = False, scan_enrich: dict = None) -> dict:
    """Run Tier 1 debate pipeline across all 9 methodologies.

    Args:
        methodology_picks: dict from methodology_picks.json
        before_date: for backfill — only use transcripts before this date
        dry_run: if True, only use cached results
        scan_enrich: optional symbol->{sector, years_history, financials} map from
            the screener scan (Caveat 1 grounding). Loaded here if not supplied.

    Returns dict of per-methodology baskets.
    """
    cache = load_debate_cache()
    if scan_enrich is None:
        scan_enrich = _load_scan_enrichment()
    methodologies = methodology_picks.get("methodologies", {})
    
    tier1_results = {}
    full_results = {}   # unfiltered debate results per methodology (for the free-universe director)
    stats = {
        # 3-bucket disjoint funnel (sum == unique_symbols)
        "total_picks": 0,            # non-deduped across all methodologies
        "unique_symbols": 0,          # deduped
        "cache_hits": 0,              # cache served, no LLM calls
        "no_transcript": 0,           # skipped, no earnings call available
        "fully_debated": 0,           # full 4-agent debate ran
        "fresh_symbols": [],          # names freshly (re-)debated this cycle — triggers the director

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
            is_new = symbol not in seen_symbols
            if is_new:
                stats["unique_symbols"] += 1
                seen_symbols.add(symbol)
            
            # Resolve transcripts (multi-quarter)
            multi_tx = resolve_transcripts(symbol, before_date)
            transcript = None
            if multi_tx["all_transcripts"]:
                transcript = multi_tx["all_transcripts"][0]  # latest as primary
            
            if not transcript:
                log.warning(f"  No transcript for {symbol} — skipping")
                if is_new:
                    stats["no_transcript"] += 1
                result = {
                    "symbol": symbol,
                    "conviction": 2,
                    "verdict": "C",
                    "radar_alert": False,
                    "radar_rationale": "No transcript available",
                    "moderator_conclusion": "No transcript available — quality penalty",
                    "methodology_key": meth_key,
                    "transcript_count": 0,
                    "transcript_dates": [],
                    "narrative_arc": "",
                    "tone_shift": "stable",
                    "guidance_credibility": 50,
                }
            else:
                # Check cache
                cache_key = f"{symbol}|{transcript['date']}"
                if cache_key in cache and _is_fresh_cache(cache[cache_key]):
                    log.info(f"  [Cache Hit] {symbol} (transcript {transcript['date']})")
                    result = dict(cache[cache_key])
                    if is_new:
                        stats["cache_hits"] += 1
                elif dry_run:
                    log.info(f"  [Dry Run] {symbol} — would debate")
                    result = {
                        "symbol": symbol,
                        "conviction": 3,
                        "verdict": "B",
                        "radar_alert": True,
                        "radar_rationale": "Dry run — skipped",
                        "moderator_conclusion": "Dry run — no LLM calls made",
                    }
                    if is_new:
                        stats["fully_debated"] += 1
                        stats["radar_alerted"] += 1
                else:
                    # Run debate (pass multi-transcript info + scan financials)
                    sym_fin = (scan_enrich.get(symbol) or {}).get("financials") if scan_enrich else None
                    result = debate_candidate(symbol, transcript, cand, cache,
                                              methodology_key=meth_key,
                                              multi_transcript_info=multi_tx,
                                              scan_financials=sym_fin)
                    # Update cache
                    cache[cache_key] = result
                    save_dossier(symbol, transcript["date"], result)  # durable per-dossier GCS write
                    save_debate_cache(cache)
                    
                    if is_new:
                        stats["fully_debated"] += 1
                        stats["fresh_symbols"].append(symbol)
                        if result.get("radar_alert"):
                            stats["radar_alerted"] += 1
                        else:
                            stats["radar_filtered"] += 1
                            stats["radar_filtered_names"].append(
                                f"{symbol} ({meth_key}): {result.get('radar_rationale', 'N/A')}"
                            )
                    # Rate limiting between full debates
                    time.sleep(2.0)
            
            # Carry G1-G4 + price/mos quant fields from methodology_picks.json
            g_fields = [
                "cycle_flag", "peak_margin_sigma", "norm_scale", "mos_source",
                "years_history", "structural_break", "structural_break_reason",
                "forward_eps_growth", "iv15_nogrowth_agreement", "iv15_saturated",
                "sector_class", "methodology_applicable", "mos", "fair_value",
                "price", "entry_price", "entry_date", "entry_metric", "weight"
            ]
            for f in g_fields:
                if f in cand:
                    result[f] = cand[f]
            
            debate_results.append(result)
        
        # Select methodology basket (filtered, for the per-methodology UI view)
        basket = select_methodology_basket(meth_key, debate_results)
        tier1_results[meth_key] = basket
        # Keep the FULL unfiltered debate set for the free-universe director (§2)
        full_results[meth_key] = debate_results
        
        log.info(f"\n[{meth_key}] Basket: {len(basket['picks'])} picks selected "
                 f"from {basket['total_candidates']} candidates "
                 f"({basket['radar_filtered']} radar-filtered)")
    
    # ── Funnel integrity assertion ─────────────────────────────────────────
    expected = stats["cache_hits"] + stats["no_transcript"] + stats["fully_debated"]
    if expected != stats["unique_symbols"]:
        log.warning(f"Funnel mismatch: {expected} != {stats['unique_symbols']} unique_symbols")
    
    return {"baskets": tier1_results, "full": full_results, "stats": stats, "cache": cache}


# ── Full Pipeline Orchestrator ───────────────────────────────────────────
def debate_and_allocate(before_date: str = None, dry_run: bool = False,
                        push_gcs: bool = True) -> dict:
    """Full Tier 1 + Tier 2 pipeline.

    Loads methodology_picks.json → runs per-methodology debates →
    runs Director allocation → writes speculair_baskets.json.

    push_gcs=False writes the output locally only (frontend/public) and skips the
    GCS upload — used for local review runs before promoting to production.
    """
    log.info("=" * 70)
    log.info("SPECULAIR DEBATE PIPELINE — STARTING")
    log.info("=" * 70)
    
    # Pre-flight health checks
    openai_ok = _openai_health_check()
    if not openai_ok:
        log.warning("⚠ OpenAI health check failed — Architect/Moderator agents will fail. "
                    "Pipeline will continue but debate quality will be degraded.")
    
    # 1. Load methodology picks from GCS (primary) or local (fallback)
    picks_data = _load_methodology_picks()
    if not picks_data:
        log.error("Could not load methodology_picks.json — aborting")
        return {}
    
    last_updated = picks_data.get("last_updated", "")
    log.info(f"Loaded methodology picks (last_updated: {last_updated})")
    
    # 2. Run Tier 1 — per-methodology debates.
    # Load the scan enrichment ONCE (sector + years_history + rich financials) and
    # reuse it for both the debate metrics grounding (Caveat 1) and the director floor.
    enrich = _load_scan_enrichment()
    tier1 = run_tier1(picks_data, before_date=before_date, dry_run=dry_run,
                      scan_enrich=enrich)
    tier1_baskets = tier1["baskets"]
    tier1_full = tier1.get("full", {})
    tier1_stats = tier1["stats"]
    
    # Persist debate cache to GCS after all debates complete
    save_debate_cache(tier1.get("cache", {}))
    
    # ── Empty thesis detection & Live check (Stage Gate 0) ─────────────────
    all_picks_across_baskets = []
    for basket in tier1_baskets.values():
        all_picks_across_baskets.extend(basket.get("picks", []))
    
    empty_thesis_count = sum(
        1 for p in all_picks_across_baskets
        if not p.get("bull_thesis") and not p.get("bear_thesis")
    )
    total_picks = len(all_picks_across_baskets)
    
    if not dry_run and total_picks > 0 and empty_thesis_count == total_picks:
        raise RuntimeError(
            f"FAIL: All {total_picks} picks have empty theses in a LIVE run! "
            f"This indicates a systemic LLM failure in Tier 1. Aborting."
        )
        
    if total_picks > 0 and empty_thesis_count == total_picks:
        log.error(
            f"🚨 ALERT: ALL {total_picks} picks have empty theses! "
            f"This indicates a systemic LLM failure (likely OpenAI API). "
            f"Output will be written but quality is severely degraded."
        )
        # Tag the output so downstream consumers (frontend/email) can detect this
        tier1_stats["_empty_thesis_alert"] = True
        tier1_stats["_empty_thesis_count"] = empty_thesis_count
    elif empty_thesis_count > 0:
        pct = empty_thesis_count / total_picks * 100
        log.warning(
            f"⚠ {empty_thesis_count}/{total_picks} picks ({pct:.0f}%) have empty theses"
        )
    
    log.info(f"\n{'='*60}")
    log.info(f"TIER 1 COMPLETE — {len(tier1_baskets)} methodology baskets")
    log.info(f"Stats: {tier1_stats}")
    log.info(f"{'='*60}")
    
    # 3. Run Tier 2 — Director allocation
    director_last_run = None   # set in the director block; persisted for the next run's cost-guard
    try:
        from live_director_agent import run_director_allocation
        # §2: the director chooses 2-20 freely from the FULL debated, gate-passing
        # universe — every name carrying a real debate thesis, not just the
        # per-methodology basket winners. Drop no-transcript stubs (empty theses).
        director_pool = {}
        for meth_key, picks in tier1_full.items():
            debated = [p for p in picks if (p.get("bull_thesis") or p.get("bear_thesis"))]
            if debated:
                director_pool[meth_key] = {"picks": debated}
        pool_syms = {p.get("symbol") for v in director_pool.values() for p in v["picks"]}
        log.info(f"Director universe (pre-floor): {len(pool_syms)} unique debated gate-passing names")
        # Enrich sector + years_history from the screener scan. methodology_picks picks
        # carry a blank sector and (older vintages) no history; sector makes the
        # concentration cap meaningful, years_history (count of annual buffett_history
        # rows) feeds the minimum-history floor below.
        from live_director_agent import MIN_YEARS_HISTORY
        # enrich already loaded above (reused — avoids re-fetching the full scan).
        if enrich:
            n_sec = n_hist = 0
            for v in director_pool.values():
                for p in v["picks"]:
                    e = enrich.get(p.get("symbol", ""))
                    if not e:
                        continue
                    if not (p.get("sector") or "").strip() and e.get("sector"):
                        p["sector"] = e["sector"]; n_sec += 1
                    if p.get("years_history") is None and e.get("years_history") is not None:
                        p["years_history"] = e["years_history"]; n_hist += 1
            log.info(f"Enriched {n_sec} sectors, {n_hist} years_history from scan ({len(enrich)} symbols mapped)")
        # History floor (G2a, upstream of the director): drop names with < MIN years of
        # fundamental history — or unknown history — BEFORE the director sees them, so a
        # recent-IPO / de-SPAC name (one noisy annual statement) can't be picked or ranked.
        floored, dropped = {}, []
        for meth_key, v in director_pool.items():
            keep = []
            for p in v["picks"]:
                yh = p.get("years_history")
                if yh is None or yh < MIN_YEARS_HISTORY:
                    dropped.append((p.get("symbol"), yh))
                else:
                    keep.append(p)
            if keep:
                floored[meth_key] = {"picks": keep}
        if dropped:
            uniq = sorted(set(dropped))
            log.info(f"History floor (>= {MIN_YEARS_HISTORY}y) dropped {len(uniq)} thin/unknown-history names: {uniq}")
        director_pool = floored
        pool_syms = {p.get("symbol") for v in director_pool.values() for p in v["picks"]}
        log.info(f"Director universe (post-floor): {len(pool_syms)} names")
        if not director_pool:
            # Cold cache / dry-run with no real theses — fall back to the baskets
            log.warning("No debated names with theses — director falling back to per-methodology baskets")
            director_pool = tier1_baskets
        # ── Portfolio continuity + director cost-guard ─────────────────────
        # Load the live basket (held positions) so the director does HOLD/ROTATE, and a
        # pool signature so we pay for the (expensive ~€20) director ONLY when the debated
        # universe actually changed since the last run. Unchanged pool → keep the basket.
        existing_spec = _load_existing_speculair()
        current_basket = {}
        for p in (existing_spec.get("apex_basket", []) + existing_spec.get("capitulation_watchlist", [])):
            sym = p.get("symbol")
            if sym:
                current_basket[sym] = {"entry_date": p.get("entry_date"),
                                       "entry_price": p.get("entry_price"),
                                       "conviction": p.get("conviction")}
        # Director cost-guard: the (~EUR20) director re-runs only when it could change the book —
        # a HELD name reported new earnings (must reassess), or the periodic review is due. A
        # marginal MoS-driven entrant does NOT trigger it (it waits for the next review), so daily
        # methodology-basket churn never incurs the director cost.
        held_apex = {p.get("symbol") for p in existing_spec.get("apex_basket", [])}
        held_reported = bool(held_apex & set(tier1_stats.get("fresh_symbols", [])))
        last_run = existing_spec.get("director_last_run")
        try:
            days_since = (datetime.now(timezone.utc).date() - datetime.fromisoformat(last_run).date()).days if last_run else 9999
        except Exception:
            days_since = 9999
        if (not dry_run) and held_apex and (not held_reported) and days_since < DIRECTOR_CADENCE_DAYS:
            log.info(f"Director cost-guard: no held name reported + review not due ({days_since}d < "
                     f"{DIRECTOR_CADENCE_DAYS}d) — holding existing basket, skipping the director.")
            director_result = {
                "apex_basket": existing_spec.get("apex_basket", []),
                "capitulation_watchlist": existing_spec.get("capitulation_watchlist", []),
                "director_memo": existing_spec.get("director_memo", "")
                                 + f"\n\n[Basket held — no held-name earnings + {days_since}d since last review "
                                   f"(< {DIRECTOR_CADENCE_DAYS}d). Director not re-run.]",
                "auto_vetoed": 0,
            }
            director_last_run = last_run
        else:
            why = ("first run / empty basket" if not held_apex
                   else "held name reported earnings" if held_reported
                   else f"periodic review due ({days_since}d >= {DIRECTOR_CADENCE_DAYS}d)")
            log.info(f"Director running — trigger: {why}.")
            # Once-per-scan macro regime brief, tilted to where the opportunities cluster.
            macro_brief = ""
            if not dry_run:
                sec_counts = {}
                for v in director_pool.values():
                    for p in v.get("picks", []):
                        s = (p.get("sector") or "Unknown")
                        sec_counts[s] = sec_counts.get(s, 0) + 1
                macro_brief = run_macro_strategist(sec_counts, before_date)
                log.info(f"Macro Strategist brief: {len(macro_brief)} chars")
            director_result = run_director_allocation(director_pool, dry_run=dry_run,
                                                      macro_brief=macro_brief, current_basket=current_basket)
            director_last_run = datetime.now(timezone.utc).date().isoformat()
        
        # If it's a live run and we used the fallback because the Director LLM failed:
        if not dry_run and "Fallback" in director_result.get("director_memo", ""):
            raise RuntimeError("FAIL: Director LLM returned zero successful responses in a LIVE run — aborting.")
            
    except ImportError:
        if not dry_run:
            raise RuntimeError("FAIL: live_director_agent.py not found in a LIVE run.")
        log.warning("live_director_agent.py not found — using Tier 1 results only")
        director_result = _fallback_director(tier1_baskets)
    except Exception as e:
        if not dry_run:
            raise RuntimeError(f"FAIL: Director allocation failed in a LIVE run: {e}")
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
        "director_last_run": director_last_run,
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
            "empty_thesis_alert": tier1_stats.get("_empty_thesis_alert", False),
            "empty_thesis_count": tier1_stats.get("_empty_thesis_count", 0),
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
                    "valley_of_death": p.get("valley_of_death", ""),
                    "moderator_conclusion": p.get("moderator_conclusion", ""),
                    "interrogator_dossier": p.get("interrogator_dossier", ""),
                    "interrogator_score": p.get("interrogator_score", 3),
                    "trajectory": p.get("trajectory", ""),
                    "transcript_count": p.get("transcript_count", 0),
                    "transcript_dates": p.get("transcript_dates", []),
                    "narrative_arc": p.get("narrative_arc", ""),
                    "tone_shift": p.get("tone_shift", "stable"),
                    "guidance_credibility": p.get("guidance_credibility", 50),
                    # Carry G1-G4 + BUG1 + price/mos details:
                    "cycle_flag": p.get("cycle_flag", "NORMAL"),
                    "peak_margin_sigma": p.get("peak_margin_sigma", 0.0),
                    "norm_scale": p.get("norm_scale", 1.0),
                    "mos_source": p.get("mos_source", ""),
                    "years_history": p.get("years_history", 99),
                    "structural_break": p.get("structural_break", False),
                    "structural_break_reason": p.get("structural_break_reason", ""),
                    "forward_eps_growth": p.get("forward_eps_growth", 0.0),
                    "iv15_nogrowth_agreement": p.get("iv15_nogrowth_agreement", True),
                    "iv15_saturated": p.get("iv15_saturated", False),
                    "sector_class": p.get("sector_class", "operating"),
                    "methodology_applicable": p.get("methodology_applicable", True),
                    "mos": p.get("mos", 0.0),
                    "fair_value": p.get("fair_value", 0.0),
                    "price": p.get("price", 0.0),
                    "entry_price": p.get("entry_price", 0.0),
                    "entry_date": p.get("entry_date", ""),
                    "entry_metric": p.get("entry_metric", 0.0),
                    "weight": p.get("weight", 0.0),
                }
                for p in basket.get("picks", [])
            ],
            "moderator_memo": basket.get("moderator_memo", ""),
            "total_candidates": basket.get("total_candidates", 0),
            "radar_filtered": basket.get("radar_filtered", 0),
        }
    
    # 4b. Apex Basket live-forward track record (chained NAV + closed-position log)
    if not dry_run:
        try:
            output["apex_tracking"] = _update_apex_tracking(output["apex_basket"], push_gcs=push_gcs)
        except Exception as e:
            log.warning(f"apex tracking update failed: {e}")
            output["apex_tracking"] = {}

    # 5. Write output
    _write_output(output, dry_run=dry_run, push_gcs=push_gcs)
    
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


def _load_scan_enrichment() -> dict:
    """symbol -> {sector, years_history} from the latest screener scan (best-effort).

    Enriches Speculair director candidates: methodology_picks picks carry a blank
    sector and (older vintages) no years_history. Sector makes the concentration cap
    meaningful; years_history is derived from the count of annual buffett_history rows
    and feeds the minimum-history floor so thin / recent-IPO names cannot reach the
    director.
    """
    import urllib.request

    def build(scan: dict) -> dict:
        out = {}
        for s in scan.get("stocks", []):
            sym = s.get("symbol")
            if not sym:
                continue
            bh = s.get("buffett_history") or {}
            rows = bh.get("rows")
            yrs = len(rows) if isinstance(rows, list) else None
            # Rich fundamentals for debate metrics grounding (Caveat 1).
            fin = {k: s.get(k) for k in _SCAN_FIN_FIELDS if s.get(k) is not None}
            if isinstance(rows, list) and rows:
                fin["history_rows"] = [
                    {"year": r.get("year"), "revenue_mm": r.get("revenue_mm"),
                     "net_income_mm": r.get("net_income_mm"), "eps": r.get("eps")}
                    for r in rows[-6:]
                ]
                if isinstance(bh.get("cagrs"), dict):
                    fin["history_cagrs"] = bh["cagrs"]
            out[sym] = {"sector": s.get("sector") or "", "years_history": yrs, "financials": fin}
        return out

    # 1. Authenticated GCS (production / Cloud Run)
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        scan = gcs_download("scans/latest_global.json")
        if scan and scan.get("stocks"):
            return build(scan)
    except Exception as e:
        log.debug(f"scan enrichment via gcs_download failed: {e}")
    # 2. Public bucket URL (local dev without ADC)
    try:
        url = f"https://storage.googleapis.com/{GCS_BUCKET}/scans/latest_global.json"
        with urllib.request.urlopen(url, timeout=90) as r:
            scan = json.load(r)
        if scan and scan.get("stocks"):
            return build(scan)
    except Exception as e:
        log.debug(f"scan enrichment via public URL failed: {e}")
    return {}


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


APEX_TRACKING_PATH = "scans/speculair_apex_tracking.json"


def _load_apex_tracking() -> dict:
    """Load the persistent apex-basket track record (chained NAV + closed-position log)."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        d = gcs_download(APEX_TRACKING_PATH)
        if isinstance(d, dict) and d.get("nav"):
            return d
    except Exception as e:
        log.debug(f"apex tracking GCS load failed: {e}")
    try:
        local = FRONTEND_DIR / "public" / "speculair_apex_tracking.json"
        if local.exists():
            return json.loads(local.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _current_prices(symbols: set) -> dict:
    """Current prices for `symbols` from the latest scan. Tries authenticated GCS
    (Cloud Run), then the public bucket URL, then the local file (dev without ADC)."""
    scan = None
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        scan = gcs_download("scans/latest_global.json")
    except Exception:
        scan = None
    if not (scan and scan.get("stocks")):
        try:
            import urllib.request
            url = f"https://storage.googleapis.com/{GCS_BUCKET}/scans/latest_global.json"
            with urllib.request.urlopen(url, timeout=20) as r:
                scan = json.loads(r.read().decode("utf-8"))
        except Exception:
            scan = None
    if not (scan and scan.get("stocks")):
        try:
            local = FRONTEND_DIR / "public" / "latest_global.json"
            if local.exists():
                scan = json.loads(local.read_text(encoding="utf-8"))
        except Exception:
            scan = None
    out = {}
    for s in (scan or {}).get("stocks", []):
        sym, px = s.get("symbol"), s.get("price")
        if sym in symbols and isinstance(px, (int, float)) and px > 0:
            out[sym] = float(px)
    return out


def _update_apex_tracking(apex_basket: list, push_gcs: bool = True) -> dict:
    """Persistent live-forward track record for the Apex Basket.

    Chains an equal-weight NAV across rebalances (anchored to entry prices at inception,
    so it measures performance from when the basket was established — not from go-live of
    the tracking code), logs a realized return whenever a name rotates out, and appends
    one history point per day. Returns a compact summary embedded in speculair_baskets.json
    for the frontend. Best-effort — callers wrap in try/except so it never breaks the run.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    apex = [p for p in (apex_basket or []) if p.get("symbol")]
    syms = {p["symbol"] for p in apex}
    if not syms:
        return {}

    tr = _load_apex_tracking()
    nav = float(tr.get("nav") or 100.0)
    last_prices = dict(tr.get("last_prices") or {})
    positions = dict(tr.get("positions") or {})
    history = list(tr.get("history") or [])
    closed = list(tr.get("closed") or [])
    prices = _current_prices(syms | set(last_prices.keys()))
    period_ret = 0.0

    if not tr:
        # INCEPTION — anchor NAV to entry prices so it reflects performance since the
        # basket was established (entry_date), not since the tracker first ran.
        rets = [prices[p["symbol"]] / p["entry_price"] - 1 for p in apex
                if (p.get("entry_price") or 0) > 0 and prices.get(p["symbol"], 0) > 0]
        period_ret = (sum(rets) / len(rets)) if rets else 0.0
        nav = 100.0 * (1 + period_ret)
        inception = min((p.get("entry_date") for p in apex if p.get("entry_date")), default=today)
        history = [{"date": inception, "nav": 100.0, "ret": 0.0, "n": len(apex)}]
    else:
        inception = tr.get("inception_date") or today
        prior = [s for s in last_prices if s in prices and last_prices[s] > 0]
        if prior and tr.get("last_date") != today:
            period_ret = sum(prices[s] / last_prices[s] - 1 for s in prior) / len(prior)
            nav *= (1 + period_ret)
        for s in list(last_prices.keys()):          # rotations → realized exits
            if s not in syms:
                pos = positions.get(s, {})
                ep = pos.get("entry_price") or last_prices[s]
                xp = prices.get(s, last_prices[s])
                closed.append({"symbol": s, "entry_date": pos.get("entry_date", ""), "exit_date": today,
                               "entry_price": round(ep, 4), "exit_price": round(xp, 4),
                               "return_pct": round((xp / ep - 1) * 100, 2) if ep else 0.0,
                               "conviction": pos.get("conviction", 0)})
                positions.pop(s, None)

    new_last = {}
    for p in apex:
        s = p["symbol"]
        cp = prices.get(s) or p.get("price") or last_prices.get(s) or 0.0
        new_last[s] = cp
        if s not in positions:
            positions[s] = {"entry_price": p.get("entry_price") or cp,
                            "entry_date": p.get("entry_date") or today,
                            "conviction": p.get("conviction", 0)}
        else:
            positions[s]["conviction"] = p.get("conviction", positions[s].get("conviction", 0))

    point = {"date": today, "nav": round(nav, 4), "ret": round(period_ret, 6), "n": len(apex)}
    if history and history[-1].get("date") == today:
        history[-1] = point
    else:
        history.append(point)
    history = history[-400:]

    state = {"inception_date": inception, "nav": round(nav, 4), "last_date": today,
             "last_prices": new_last, "positions": positions,
             "history": history, "closed": closed[-80:]}
    try:
        (FRONTEND_DIR / "public" / "speculair_apex_tracking.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log.debug(f"apex tracking local write failed: {e}")
    if push_gcs:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from screener_v6 import gcs_upload
            gcs_upload(APEX_TRACKING_PATH, state)
        except Exception as e:
            log.warning(f"apex tracking GCS upload failed: {e}")
    log.info(f"Apex tracking: NAV {nav:.2f} ({(nav / 100 - 1) * 100:+.1f}% since {inception}) | "
             f"{len(apex)} open, {len(closed)} closed")

    wins = [c for c in closed if c.get("return_pct", 0) > 0]
    return {"inception_date": inception, "since_inception_pct": round((nav / 100.0 - 1) * 100, 2),
            "nav": round(nav, 2), "n_open": len(apex), "n_closed": len(closed),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
            "history": history, "closed": closed[-20:]}


def _write_output(output: dict, dry_run: bool = False, push_gcs: bool = True):
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
    if not push_gcs:
        log.info("[--no-gcs] Local-only write — skipping GCS upload of speculair_baskets.json")
        return
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
    ap.add_argument("--no-gcs", action="store_true",
                    help="Write speculair_baskets.json locally only; skip the GCS upload (local review run)")
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
        debate_and_allocate(before_date=args.before_date, dry_run=args.dry_run,
                            push_gcs=not args.no_gcs)
    else:
        ap.print_help()
