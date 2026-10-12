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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DebateEngine] %(message)s")
log = logging.getLogger("live_debate")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# House voice — shared style contract prepended to every agent system prompt below.
# Governs the PROSE the agents write; JSON keys / enum values are exempt (see agent_voice.py).
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from agent_voice import AGENT_VOICE
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
    Listing-driven like resolve_transcripts (the old cache-first path returned whatever stale
    call was cached and never asked FMP for a newer one).
    If before_date is given, only transcripts dated <= before_date qualify.
    """
    got = resolve_transcripts(symbol, before_date, max_transcripts=1)["all_transcripts"]
    return got[0] if got else None


def resolve_transcripts(symbol: str, before_date: str = None,
                        max_transcripts: int = 8) -> dict:
    """Resolve up to *max_transcripts* earnings-call transcripts for symbol.

    Returns a dict with contract fields:
        transcript_count  (int)  : number of transcripts available (0..8)
        transcript_dates  (list) : e.g. ["2025-Q3", "2025-Q2", ...]
        all_transcripts   (list) : list of transcript dicts (date, content,
                                   filename, source), sorted descending by date

    Strategy (2026-10-06 - listing-driven; the old version stopped asking FMP once 8 calls were
    cached and only probed fiscal years now..now-2, so 43 universe names sat on May transcripts
    while FMP held their August calls, and FY2027 reporters (8725.T, NKE, JD.L...) were missed):
        1. Ask FMP which calls exist (earning-call-transcript-dates: fiscalYear/quarter/date).
        2. Take the newest *max_transcripts* (respecting before_date); serve each from the cache
           when a VALID file exists, else fetch it - overwriting an empty placeholder.
        3. Listing unavailable (no key / HTTP error) -> fail open to the cache as before.
        4. Sort descending by date, trim to *max_transcripts*.
    """
    # ── 1. Gather everything already in the local cache ─────────────────
    cached = _resolve_all_from_cache(symbol, before_date)
    by_key = {_transcript_cache_key(t.get("filename", "")): t for t in cached}

    all_transcripts: list[dict] = []
    fmp_key = get_key("FMP_API_KEY")
    listing = _transcript_listing(symbol, fmp_key) if fmp_key else None

    # ── 2. Newest calls per FMP's own listing; fetch what the cache lacks ─
    TRANSCRIPT_LISTING_STATS["calls"] += 1
    if listing is not None:
        # one row per CALL DATE: FMP sometimes lists the same call under two fiscal years
        # (BBWI/CHWY 2026: FY2027 Q2 and FY2026 Q2) - prefer the label we already hold
        by_date: dict = {}
        for d, fy, q in listing:
            if before_date and d > before_date:
                continue
            by_date.setdefault(d, []).append((fy, q))
        wanted = []
        for d in sorted(by_date, reverse=True):
            keys = by_date[d]
            fy, q = next(((f, qq) for f, qq in keys if f"{f}Q{qq}" in by_key), keys[0])
            wanted.append((d, fy, q))
        for d, fy, q in wanted[:max_transcripts]:
            hit = by_key.get(f"{fy}Q{q}")
            # a cache hit counts only when it holds THIS call: older blind probes saved FMP's
            # year-echoed answers under future keys (CHWY_2026Q4 = the March-2026 call)
            if hit and _days_apart(hit["date"], d) <= 10:
                all_transcripts.append(hit)
                continue
            fetched = _fetch_transcript_quarter(symbol, fy, q, fmp_key, before_date)
            if fetched:
                all_transcripts.append(fetched)
        # FMP listings can omit old calls we still hold - top up from the cache (by date, so a
        # mis-keyed duplicate of a call already included never sneaks back in)
        have = {t["date"] for t in all_transcripts}
        for t in sorted(cached, key=lambda x: x["date"], reverse=True):
            if len(all_transcripts) >= max_transcripts:
                break
            if t["date"] not in have:
                all_transcripts.append(t)
                have.add(t["date"])
    else:
        if fmp_key:
            TRANSCRIPT_LISTING_STATS["failed"] += 1
            TRANSCRIPT_LISTING_STATS["failed_syms"].append(symbol)
            log.warning(f"transcript listing unavailable for {symbol} - serving the cache "
                        f"(new calls cannot be detected for this name this run)")
        else:
            TRANSCRIPT_LISTING_STATS["no_key"] += 1
        # same backstop as above: never hand a debate the same call twice
        seen = set()
        for t in sorted(cached, key=lambda x: x["date"], reverse=True):
            if t["date"] not in seen:
                all_transcripts.append(t)
                seen.add(t["date"])

    # ── 3. Sort descending by date and trim (one entry per call date) ──
    _seen_dates: set = set()
    all_transcripts = [t for t in all_transcripts
                       if not (t["date"] in _seen_dates or _seen_dates.add(t["date"]))]
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


# Per-process counters for resolve_transcripts - prep prints them, so a listing outage (e.g. a key
# that 401s after rotation) is visible instead of silently serving stale transcripts to every name.
TRANSCRIPT_LISTING_STATS = {"calls": 0, "failed": 0, "no_key": 0, "failed_syms": []}


def _days_apart(a: str, b: str) -> int:
    try:
        return abs((datetime.fromisoformat(a[:10]) - datetime.fromisoformat(b[:10])).days)
    except Exception:
        return 10**6


def _transcript_cache_key(filename: str) -> str:
    """'MMS_2026Q3.json' -> '2026Q3' (the FMP fiscalYear + quarter the file was fetched under)."""
    return filename.replace(".json", "").rsplit("_", 1)[-1] if "Q" in filename else ""


def _transcript_listing(symbol: str, fmp_key: str) -> Optional[list]:
    """FMP's own list of available calls as [(date, fiscalYear, quarter)], newest first.
    [] = FMP has none for this symbol; None = the listing call itself failed (caller fails open)."""
    try:
        r = requests.get("https://financialmodelingprep.com/stable/earning-call-transcript-dates",
                         params={"symbol": symbol, "apikey": fmp_key}, timeout=20)
        if r.status_code != 200:
            return None
        rows = r.json()
        if not isinstance(rows, list):
            return None
        out = []
        for row in rows:
            d = str(row.get("date") or "")[:10]
            fy, q = row.get("fiscalYear"), row.get("quarter")
            if d and fy and q:
                out.append((d, int(fy), int(q)))
        out.sort(reverse=True)
        return out
    except Exception:
        return None


def _fetch_transcript_quarter(symbol: str, fy: int, q: int, fmp_key: str,
                              before_date: str = None) -> Optional[dict]:
    """Fetch one listed call and cache it. Overwrites an EMPTY placeholder file (written when a
    quarter was probed before its call happened) - the old code never replaced those."""
    try:
        r = requests.get("https://financialmodelingprep.com/stable/earning-call-transcript",
                         params={"symbol": symbol, "year": fy, "quarter": q, "apikey": fmp_key},
                         timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list) or not data:
            return None
        entry = data[0]
        t_date, t_content = entry.get("date", ""), entry.get("content", "")
        if not (t_date and t_content and len(t_content) > 100):
            return None
        if before_date and t_date[:10] > before_date:
            return None
        cache_name = f"{symbol}_{fy}Q{q}.json"
        TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(TRANSCRIPT_CACHE_DIR / cache_name, "w", encoding="utf-8") as fh:
            json.dump({"payload": [entry]}, fh)
        return {"date": t_date[:10], "content": t_content,
                "filename": cache_name, "source": "fmp_api"}
    except Exception:
        return None


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


def _load_macro_snapshot() -> dict:
    """The structured classifier snapshot (backend/_opus_debate/macro_regime.json):
    regime + quadrant + Dalio debt_cycle block. Written by the weekly Opus pipeline
    (_write_macro_regime). Returns {} if missing/stale-unreadable."""
    try:
        p = BASE_DIR / "_opus_debate" / "macro_regime.json"
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.debug(f"macro snapshot load failed: {e}")
        return {}


def _phase_transition_check(existing_spec: dict) -> tuple[bool, str]:
    """Fork 4 (2026-07-27): compare the snapshot's current debt-cycle phase against the
    phase stamped at the LAST director run. A transition (e.g. DISCIPLINE -> FORCING)
    forces a director re-run regardless of the 30-day cost-guard — 'the bond market is
    cracking' is exactly the alert that must not sit unread. UNKNOWN never triggers
    (fail-open: a data outage must not burn a ~EUR20 director run)."""
    now = ((_load_macro_snapshot().get("debt_cycle") or {}).get("debt_cycle_phase")) or "UNKNOWN"
    prior = existing_spec.get("director_last_phase") or ""
    transitioned = bool(prior and now not in ("UNKNOWN", "") and now != prior)
    if transitioned:
        log.info(f"Debt-cycle phase transition detected: {prior} -> {now} — overriding director cost-guard.")
    return transitioned, now


def run_macro_strategist(candidate_sectors: dict, before_date: str = None) -> str:
    """Once-per-scan macro regime brief for the director (opus). Tilts toward the sectors
    where the debated opportunities cluster. Returns markdown, or '' on failure (the
    director still runs without it).

    2026-07-27: now GROUNDED in the classifier snapshot (macro_regime.json — regime,
    growth x inflation quadrant, Dalio debt-cycle phase + falsifiers) instead of model
    recall. The 'planned enhancement' note from the original docstring is done: the same
    dials the weekly Apex Director reads now anchor the live brief, closing the gap
    where one Director family flew on data and the other on vibes."""
    sectors = ", ".join(f"{s} ({n})" for s, n in sorted(candidate_sectors.items(), key=lambda x: -x[1])) or "n/a"
    day = before_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    snap = _load_macro_snapshot()
    cyc = snap.get("debt_cycle") or {}
    dial_lines = []
    if snap.get("regime"):
        dial_lines.append(f"- Risk regime (deterministic classifier): {snap['regime']} "
                          f"(score {snap.get('score')}) — detail {json.dumps(snap.get('regime_detail', {}))}")
    if snap.get("quadrant") and snap.get("quadrant") != "UNKNOWN":
        dial_lines.append(f"- Growth x inflation quadrant: {snap['quadrant']} ({snap.get('quadrant_basis', '')})")
    if cyc.get("debt_cycle_phase") and cyc.get("debt_cycle_phase") != "UNKNOWN":
        dial_lines.append(
            f"- Dalio debt-cycle phase: {cyc['debt_cycle_phase']} ({cyc.get('weeks_in_phase', '?')} weeks in; "
            f"basis: {cyc.get('phase_basis', '')}). Implication: {cyc.get('phase_detail', '')} "
            f"Stance rule: DISCIPLINE caps at balanced, FORCING floors at defensive, "
            f"MONETIZATION unlocks aggressive real-asset positioning.")
        rac = cyc.get("reserve_asset_check") or {}
        if rac.get("note"):
            dial_lines.append(f"- Reserve-asset cross-check: {rac['note']}")
    dials = ("\n\nDETERMINISTIC DIALS (weekly classifier snapshot, asof "
             f"{snap.get('asof', '?')}) — these are AUTHORITATIVE; your prose interprets them, "
             "it does not override them:\n" + "\n".join(dial_lines)) if dial_lines else \
            "\n\n(No classifier snapshot available — flag to the director that this brief is UNGROUNDED model recall.)"

    system = (
        "You are the Macro Strategist for a high-conviction equity committee. Write a concise, "
        "decision-useful MACRO REGIME BRIEF for the portfolio director: the rates / inflation / growth "
        "backdrop and its trajectory, the dominant risk-on vs risk-off posture, and explicit "
        "tailwind/headwind calls for the sectors where this cycle's opportunities cluster. Be specific "
        "about what would flip the regime. No hedging filler. When deterministic dials are supplied, "
        "anchor every posture call to them — including the debt-cycle phase's duration discipline "
        "(in DISCIPLINE, long-duration story names are headwind regardless of sector)."
    )
    user = (
        f"Today is {day}. The debated opportunity set clusters in these sectors (name + count): {sectors}."
        f"{dials}\n\n"
        "Provide: (1) the macro regime in 3-5 sentences, reconciling the dials; (2) a per-sector "
        "tailwind/headwind line for the clustered sectors; (3) the single macro risk the director should "
        "most avoid clustering the basket around; (4) one line on what the debt-cycle phase means for "
        "duration appetite in THIS basket."
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
INTERROGATOR_MODEL = "claude-opus-5"     # forensic transcript dossier (also user-facing)
ARCHITECT_MODEL    = "gpt-5.5"           # probabilistic bull/bear (cross-model by design)
MODERATOR_MODEL    = "gpt-5.5"           # risk / timing / expectations (cross-model by design)
MACRO_MODEL        = "claude-opus-5"     # once-per-scan macro regime brief
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

RADAR_GROWTH_CATALYST_PROMPT = AGENT_VOICE + """You are the Radar Agent, a real-time market scanner for a financial investment committee.
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

RADAR_VALUE_TRAP_PROMPT = AGENT_VOICE + """You are the Radar Agent (Value-Trap Audit mode), a real-time scanner for a financial investment committee.
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

INTERROGATOR_SYSTEM_PROMPT = AGENT_VOICE + """You are the Interrogator — a forensic equity analyst on an investment committee allocating REAL capital. You receive multiple consecutive quarterly earnings-call transcripts for a company (up to 8 quarters) AND its actual financial trajectory from our screener.

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
Then assess the ECONOMIC MOAT and whether a SECULAR force threatens its TERMINAL value (distinct from a cyclical dip): name the moat type (switching-costs / network / scale-cost / intangible-brand / regulatory-license / none), judge its WIDTH using the returns + margin EVIDENCE in the financials — a high-but-FALLING ROIC or eroding gross margin is an ERODING moat, NOT a wide one; a rising ROIC with expanding margins is widening. Then judge whether a structural threat (AI-displacement, fintech/stablecoin disintermediation, cord-cutting/broadband overbuild, autonomous-vehicle, labor-arbitrage deflation, reimbursement compression, retail channel-shift, energy-transition) could impair the TERMINAL value, and whether the cheapness is therefore a fear-print (mispricing) or a structurally-shrinking base (value trap).

After the dossier, output one final line in EXACTLY this format for machine parsing (nothing after it):
CREDIBILITY_SCORE: <integer 1-5> | TRAJECTORY: <STRENGTHENING|STABLE|DETERIORATING|PIVOTING> | MOAT: <WIDE|NARROW|ERODING|NONE> | MOAT_TREND: <WIDENING|STABLE|ERODING> | SECULAR_THREAT: <terminal|material|manageable|none>
where credibility_score is 1 (evasive / unsupported by financials) to 5 (highly credible, corroborated by financials); MOAT/MOAT_TREND capture whether the durable earnings base is wide and widening or narrow and being structurally eroded; SECULAR_THREAT is the terminal-value impairment risk from a structural (not cyclical) force.
"""

ARCHITECT_SYSTEM_PROMPT = AGENT_VOICE + """You are the Architect — a System-2 reasoning engine on an investment committee allocating REAL capital. Using the Interrogator's forensic dossier, the financial metrics, and the transcript, construct a rigorous, probabilistically-weighted Bull case and Bear case.

EVIDENCE DISCIPLINE (mandatory): Reason ONLY from data actually present in your input — the financial metrics block, the transcript, and the dossier IF one is provided. If the Interrogator dossier is empty or absent, do NOT invent, quote, or cite "the dossier", and do NOT fabricate specific figures (beat-rates, buyback prices, credibility scores, transcript quotes) that are not in your input; instead reason from the metrics + transcript and state that no dossier was available. Never present a number you were not given as if it were sourced. Map how the macro and competitive environment impacts the company's moat or event-driven catalyst. Ground every argument in the specific evidence provided — cite the real financials (revenue/margin/EPS/FCF trajectory, returns, leverage, valuation) and quote transcript phrases with quarter references. State the key conditions each case depends on. Be thorough; there is no length limit.

SUM-OF-PARTS (mandatory): in BOTH cases value the business by its PARTS — a true segment SoP when a "SEGMENT REVENUE" block is present (value each segment by an appropriate peer multiple, then sum), else a whole-company intrinsic via the methodology metric / peer multiple — then apply special-situation OVERLAYS where relevant (net cash, pending distributions [verify whether already paid], announced asset-sale proceeds, tender/deal terms minus liabilities). Lean on any peer-comps lever you are given for the multiples. The goal is the company's ACTUAL intrinsic value by its parts, catalyst or not (e.g. a conglomerate whose segments sum to more than the whole).

You must output a JSON object:
{
  "bull_thesis": "The full bullish argument — the strongest evidence-grounded case for why this works, the catalysts, and the specific conditions that must hold.",
  "bear_thesis": "The full bearish argument — the strongest evidence-grounded case for why this fails, the specific risks, and what would confirm them.",
  "sop_bull": "The favorable Sum-of-Parts: the parts breakdown + the per-share value they imply.",
  "sop_bear": "The adverse Sum-of-Parts: the conservative parts breakdown + the per-share value."
}
Output ONLY the raw JSON object, without any markdown formatting or code blocks.
"""

MODERATOR_SYSTEM_PROMPT = AGENT_VOICE + """You are the Chief Risk Officer & Expectations Arbitrageur for a financial investment committee.
Your task is to review the earnings call transcript, along with the Interrogator's findings, the Architect's Bull/Bear cases, and financial metrics.

EVIDENCE DISCIPLINE (mandatory): Cite ONLY data actually present in your input. Do NOT reference, quote, or invent a "dossier" that was not provided to you, and do NOT manufacture specific figures (beat-rates, insider buy ratios, multiples, prices) that are not in the metrics/inputs you were given. When the metrics block carries a "TTM / LATEST QUARTER" section, treat THOSE figures as the current state and the fiscal-year-annual figures above them as historical context.
Your sole responsibility is to evaluate TIMING, NARRATIVE SATURATION, and MARGIN OF SAFETY to measure the delta between fundamental reality and market perception.

Analyze the subtext, narrative history, and simulated positioning data to answer these four questions:
1. The Consensus Delta: Is Wall Street still looking the wrong way? Quote or explain the exact analyst assumptions that are factually incorrect based on our hidden thesis.
2. The Valley of Death: Detail exactly what will go wrong in the next 3 to 9 months. Is there a cash burn hump, debt maturity wall, or macro headwind that will temporarily decimate Free Cash Flow or punish the stock before the catalyst is realized?
3. The Positioning Washout: Will the pivot/dividend cut force the current yield-focused/passive shareholder base to liquidate mechanically?
4. The Forcing Function: What is the exact hard date, proxy window, or corporate event that will shatter the current consensus and force a re-rating?

You must also perform Activist & Catalyst Detection by merging:
- Loeb's Third Point criteria (catalyst density, sum-of-parts discount, activism potential, asymmetric risk/reward).
- The Bloom template (governance reset, strategic process, premium scenario).

SUM-OF-PARTS RECONCILIATION + CATALYST STATUS (mandatory): reconcile the Architect's sop_bull and sop_bear into ONE base-case sop_fair_value (with the parts breakdown) and a risk_reward (downside-to-break vs upside-to-fair-value). Judge the load-bearing catalyst's status FROM THE PROVIDED MATERIALS ONLY — FIRED (already happened, re-rate spent) / ARB (deal terms fixed, capped at the offer) / PENDING_HARD (dated, binding, real asymmetry) / SOFT_EXTENDED (non-binding, serially-extended, third-party, single-binary) / UNVERIFIABLE. If the materials cannot establish the CURRENT status (e.g. they predate the catalyst window), output catalyst_status=UNVERIFIABLE — NEVER assert a live status you cannot source from the inputs. CATALYST NEUTRALITY (2026-07-21 apex-reassessment): the status is DESCRIPTIVE, not a conviction lever — the dated-event asymmetry book is Basket-13, so in THIS lane a FIRED or SOFT_EXTENDED catalyst on a clean-forensic franchise is NEITHER a plus NOR a penalty. Judge the RESIDUAL value case (upside to sop_fair_value, risk_reward, forensic quality); do NOT down-rate merely because the event is spent or undated (the 2026-07 study: that clause discarded the basket winners — post-catalyst re-rates keep running), and do NOT up-rate for event heat. An ARB is still sized to the spread. Apply this UNIFORMLY (do not exempt a name just because it had a bundled transcript). Sanity-check the implied multiple against any peer comps you are given.

Your final execution verdict MUST be one of:
- "A": ENTER (the value case is live NOW — an imminent catalyst qualifies, but so does a clean-forensic franchise at a real discount whose re-rate is already underway or needs no event; do NOT withhold an A solely because no dated event exists).
- "B": WATCHLIST (the thesis is real but the price/setup is not there yet — name the SPECIFIC level or development you are waiting for; "wait for a flush" is only valid if you name the flush).
- "C": PASS (The narrative is saturated, multiple expanded, or alpha is dead).

The conviction score MUST be an integer between 1 and 5 matching the verdict:
- 5: Strong Buy (Enter, exceptional asymmetry — catalyst-driven OR a deep clean-franchise discount with a credible re-rate path)
- 4: Buy (Enter or near-trigger Watchlist with clear timing/level)
- 3: Hold / Neutral (Moderate watchlist / stable profile)
- 2: Sell (Pass, challenged fundamentals, or priced in — "no catalyst" alone is NOT a reason to score 2)
- 1: Strong Sell (Pass, value trap, or capital destruction risk)

You must return a valid JSON object:
{
  "verdict": "A" | "B" | "C",
  "conviction": integer (1 to 5),
  "value_conviction": integer (1 to 5) — rate the VALUE case as if NO catalyst overlay existed: valuation vs your reconciled SoP fair value + forensic quality ONLY, explicitly IGNORING catalyst_status and any regime tilt. This score MUST be allowed to diverge from `conviction` (a FIRED-catalyst name can be value_conviction 5; a hot-catalyst story at full price can be value_conviction 1) — do not default them to the same number. MOAT-AWARE CAP: an ERODING moat (high-but-falling returns/margins) or a TERMINAL secular threat CAPS value_conviction at 3 — a low multiple on a structurally-shrinking base is a value trap, not value; do NOT credit optical cheapness over a melting terminal value.,
  "value_conviction_blocker": "string — REQUIRED whenever value_conviction == 4: name the SINGLE ingredient that withheld the 5, one of DISCOUNT_TOO_SMALL (the business qualifies, the price does not) | MOAT (the discount is real but durability is unproven) | FORENSICS (the numbers/credibility are not clean enough) | PEAK_ARTIFACT (the cheapness may be a peak-earnings illusion) | OTHER: <one line>. Empty string for any other score. This is instrumentation, not a grade — it lets the ledger show which ingredient is structurally scarce.",
  "moat": "string — WIDE | NARROW | ERODING | NONE: the Interrogator's moat read reconciled with the returns/margin evidence (a high-but-FALLING ROIC is ERODING, not WIDE).",
  "moat_trend": "string — WIDENING | STABLE | ERODING.",
  "secular_threat": "string — terminal | material | manageable | none, naming the structural force if any.",
  "secular_theme": "string — the SINGLE dominant secular-decline theme id from backend/_opus_debate/secular_themes.json (ai-displacement | payments-disintermediation | linear-media-decline | autonomous-mobility | labor-arbitrage-deflation | reimbursement-compression | retail-channel-shift | energy-transition-loser), or \"\" if none applies. Used by the Director to avoid concentrating the book in one secular tail.",
  "sop_fair_value": "string/number — the reconciled base-case Sum-of-Parts per-share fair value (a number or tight range).",
  "sop_breakdown": "string — the parts and what each contributes to the value.",
  "risk_reward": "string — downside-to-break vs upside-to-fair-value, as a ratio or a clear statement.",
  "catalyst_status": "string — EXACTLY ONE bare enum token: FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE. NO prose, NO explanation in this field (downstream code does exact-match on it).",
  "catalyst_status_note": "string — the dated evidence for catalyst_status: WHICH event, WHEN, and how verified. All catalyst prose goes HERE, never in catalyst_status.",
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

# -- REGIME-LANE CRO RUBRIC (2026-10-06, Bruno) ---------------------------------------------------
# The regime lane's CRO answers FOUR decision questions in order (thesis -> valuation -> entry ->
# fit) and the A/B/C letter is DERIVED BY CODE from thesis_state x entry_mode (+ the quadrant entry
# floor). Deliberately a SEPARATE constant, exported by prep() to backend/_opus_debate/
# cro_regime_rubric.txt: MODERATOR_SYSTEM_PROMPT is shared with the B13 catalyst lane (same
# moderator_system.txt), FR, mining and FDT, which are out of scope and must not change. No
# AGENT_VOICE prefix - the CRO has already read it in moderator_system.txt. ASCII only.
REGIME_CRO_RUBRIC = """=== REGIME-LANE CRO RUBRIC (2026-10-06) - this lane only; where it conflicts with moderator_system.txt, THIS WINS ===
This replaces the base mandate ("Your sole responsibility is to evaluate TIMING, NARRATIVE SATURATION, and MARGIN OF SAFETY") and the base A/B/C verdict definitions. The base analysis fields (consensus_delta, valley_of_death, positioning_washout, forcing_function) stay as the supporting analysis, and every base JSON field is still required. Answer FOUR decision questions, separately and IN ORDER, and do not let one answer leak into the next.

Q1 THESIS - is the business case still true? (Not the price, not the macro.)
  thesis_state = INTACT (the load-bearing claims are corroborated by the latest dated numbers) | IMPAIRED (a load-bearing claim is in doubt but not disproven, and a specific, checkable, dated test can restore it) | BROKEN (a load-bearing claim is disproven by a dated fact).
  thesis_evidence = the dated evidence for that state (YYYY-MM-DD, the quarter or the filing).
  thesis_test = REQUIRED when IMPAIRED, else null: {metric, pass_level (restores INTACT), fail_level (makes it BROKEN), resolves_on (the dated event that settles it)}. If you cannot date or measure the test, the state is INTACT or BROKEN, not IMPAIRED.

Q2 VALUATION - the typed valuation block (step 6b of your prompt). Unchanged.

Q3 ENTRY - entry_mode = NOW (buy at today's price) | AT_LEVEL (buy only at entry_level_px) | ON_EVENT (buy only after entry_event) | NONE (no entry).
  entry_level_px = a number in the same listing and currency as the valuation block; AT_LEVEL only, else null.
  washout_type = AT_LEVEL only - WHO sells the stock down to your level: MECHANICAL (forced, non-fundamental sellers: an index deletion, fund redemptions, a lock-up expiry, spin-off dumping, yield holders after a dividend cut) | FACTOR (a sector, style or macro de-rating that is not specific to the company). NONE for every other mode. An AT_LEVEL with no named seller is the banned "wait for a flush".
  entry_event = ON_EVENT only (when IMPAIRED it is normally thesis_test.resolves_on), else "".

Q4 FIT - context, never a lever.
  peer_position = cheap_vs_peers | in_line | rich_vs_peers | no_peers (peer_groups/<SYM>.json plus your own check; explain it in peer_comps_note).
  macro_fit = TAILWIND | NEUTRAL | HEADWIND | UNKNOWN, with macro_fit_note (one or two sentences). Read backend/_opus_debate/macro_regime.json: quadrant, quadrant_basis, regime, debt_cycle.debt_cycle_phase, debt_cycle.phase_detail, debt_cycle.expected_horizon_months. Judge whether this business's payback profile (cash now versus a long-dated story; p_fcf and fcf_margin in the metrics) is helped or hurt by that backdrop.
  Inflation: also read this symbol's entry in backend/_opus_debate/inflation_resilience.json (resilient | mixed | exposed | unknown - its gross margin through the 2021-22 inflation, with the numbers in inflation_resilience_basis). When the quadrant is REFLATION or STAGFLATION, weigh it in macro_fit and add ONE pass-through sentence to macro_fit_note: either a dated quote or figure from the latest transcript showing price increases sticking / costs being passed on (or margins being squeezed by input or wage costs), or "no pass-through evidence in the transcript". A missing entry or unknown is no penalty.
  macro_fit NEVER changes thesis_state, entry_mode, the verdict or conviction, and a macro or debt-cycle citation is never the dated fact behind a change. File missing, quadrant UNKNOWN or phase UNKNOWN -> macro_fit UNKNOWN (no penalty). Do not read regime_read.json (it is last week's).

THE LETTER IS DERIVED BY CODE from Q1 x Q3. The pipeline re-derives it after the gates, keeps your letter as verdict_agent_orig and logs any mismatch as a defect - so write verdict = the mapped letter:
  A = INTACT + NOW                                -> "buy now"
  B = INTACT + AT_LEVEL   (wait_kind price)       -> "wait for a better price"
  B = IMPAIRED + ON_EVENT (wait_kind proof)       -> "wait for proof"
  B = INTACT + ON_EVENT   (wait_kind event)       -> "wait for the event"
  C = BROKEN (with any entry), or entry_mode NONE -> "pass for now"
  IMPAIRED + NOW and IMPAIRED + AT_LEVEL are not valid answers: an impaired thesis waits for its proof. The code coerces either one to ON_EVENT on thesis_test.resolves_on (wait for proof), or to C when there is no thesis_test, and flags it.
CONVICTION keeps its 1-5 scale. A C that is YOUR answer (BROKEN, entry_mode NONE, or IMPAIRED with no thesis_test) caps it at 2: a pass must never clear the Director's eligibility bar (conviction >= 3); the code clamps a higher number and keeps yours as conviction_agent_orig. A C that comes only from the price or the quadrant entry floor (no buyable price between the exit and the bar, or the wash-out pass below) leaves your conviction untouched: the letter says "not a buy at this price", the conviction still says how good the business case is, and the macro quadrant never moves conviction. So when only the price fails the floor, answer NOW or AT_LEVEL and let the code decide - write NONE only for a reason of your own (the wash-out pass below is the one price NONE the code reads as a price answer).

HARD RULES (the code enforces each one and stamps a grade flag when it has to):
 (1) BROKEN is never B: BROKEN means entry_mode NONE.
 (2) NOW only if base_fv_px / live_price - 1 >= the entry floor for the macro_regime.json quadrant: 20% for GOLDILOCKS, REFLATION, UNKNOWN or a missing file; 25% for STAGFLATION; 30% for RISK_OFF. This is the same bar the Director applies at STEP 3a - a bar to clear, not a weight. Below it, answer AT_LEVEL at the price where the discount clears the floor; when no such price sits above the exit level, still answer NOW - the code grades it a price pass and keeps your conviction. Never write NONE for a price reason. A NOW below the floor is re-derived by code to a price-wait at base_fv_px / (1 + floor), or to C when that price is at or below the exit level.
 (3) entry_level_px must sit strictly above the exit level (valuation.bear_px and downside_floor_px), strictly below live_price, and base_fv_px / entry_level_px - 1 must clear the same floor. A level at or below the exit, or one whose own discount fails the floor, is a defect: the code replaces it with base_fv_px / (1 + floor) when that price is above the exit, else grades C. A level at or above live_price means the price you wait for is already here: the code reads it as NOW, and rule (2) decides.
 (4) AT_LEVEL requires washout_type MECHANICAL or FACTOR.
 (5) IMPAIRED requires all four thesis_test parts; ON_EVENT requires entry_event.
 (6) signal_type trap or none -> entry_mode NONE unless extraordinary override evidence exists.

WASH-OUT RESOLUTION - only when inputs/<SYM>.json carries a non-null "washout" block. Read washout.level_source - there are two triggers:
  LEVEL REACHED (level_source entry_level_px or cro_add_px): the price has reached the entry level this committee named last time. The market has answered the wait you set: RESOLVE it, do not extend it. AT_LEVEL is forbidden - a second price-wait is a defect the code coerces.
  FELL 10% (level_source fall_10pct): a wait-graded name has fallen 10% or more since its last debate and it had no level you named (an older B, a proof wait or an event wait). Re-check the wait; you may keep it.
  INTACT, waiting for a price -> NOW (buy now). After LEVEL REACHED, if even this price fails rule (2), the answer is NONE (pass for now) - never another level; that pass comes from the price, so the code leaves your conviction alone. After FELL 10% you may instead answer AT_LEVEL at a level that obeys rules (3) and (4).
  INTACT, waiting for a dated event -> keep ON_EVENT with the same (or a re-dated) entry_event until the event has happened (wait for the event): you are never forced to buy ahead of the event the committee gated on.
  IMPAIRED -> ON_EVENT with a full thesis_test, the same or a re-dated test (wait for proof).
  BROKEN   -> NONE (pass for now).
  Say in thesis_evidence whether the fall came from forced sellers (mechanical), a sector or style sell-off (factor) or company news, with the date; the arrival of the price is the dated fact behind any change of letter. Write washout_resolution = {trigger (FELL_10PCT when washout.level_source is fall_10pct, else LEVEL_REACHED), prior_level_px (washout.level, or null), resolved_to (BUY | WAIT_FOR_PRICE | WAIT_FOR_PROOF | WAIT_FOR_EVENT | PASS), note (one dated sentence)}. With no washout block, washout_resolution is null.

HOUSE VOICE: the enums stay bare tokens in their own fields; the prose says them plainly. Open moderator_conclusion with the plain answer:
  "Buy now." | "Wait for a better price: we buy near <level>, which <the forced sellers, or the sector sell-off> could deliver." | "Wait for proof: we buy once <the test> passes, due <date>." | "Wait for the event: we buy once <the event> confirms." | "Pass for now."
In prose write "the thesis holds", "the thesis is in doubt until <the test>" or "the thesis has broken" - never INTACT, IMPAIRED, BROKEN, AT_LEVEL, ON_EVENT, MECHANICAL or FACTOR. Define a wash-out the first time you use the word ("a wash-out, a sharp sell-off by forced or non-fundamental sellers").
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
    # Stock-page models & scores (Jun 2026 enrichment): surface the multi-model valuation spread +
    # current stock-page scores so the debate reasons off model AGREEMENT/divergence. ONLY fields the
    # stock page actually renders today — hit_prob (ML) and factor_scores (13-factor radar) are RETIRED
    # and deliberately excluded so they cannot bias the agents.
    "dcf_value", "dcf_fcff_mos", "epv_mos", "graham_revised_mos", "owner_earnings_mos",
    "iv15_deep_value_mos", "bull_score", "catalyst_score", "altman_z", "piotroski",
    "days_to_earnings", "cycle_flag", "classification", "target", "upside",
    "smart_money_score", "inst_score", "pt_velocity_60d", "proximity_52wk", "sma200",
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


def _ttm_block(sym: str) -> str:
    """FIX (2026-06, AUDIT_PIPELINE_REPORT.md A1): the scan feeds FISCAL-YEAR-ANNUAL FCF/EPS
    labelled 'latest' — stale in 97% of audited names, and direction-inverting on inflecting
    names. Append a live TTM / latest-quarter block (FMP quarterly statements) flagged as
    overriding the annual figures, so the debate reasons off current cash/earnings. '' on failure."""
    if not sym:
        return ""
    key = get_key("FMP_API_KEY")
    if not key:
        return ""
    base = "https://financialmodelingprep.com/stable"
    try:
        cf = requests.get(base + "/cash-flow-statement",
                          params={"symbol": sym, "period": "quarter", "limit": 5, "apikey": key}, timeout=20).json()
        inc = requests.get(base + "/income-statement",
                           params={"symbol": sym, "period": "quarter", "limit": 8, "apikey": key}, timeout=20).json()
    except Exception:
        return ""
    if not (isinstance(cf, list) and isinstance(inc, list) and len(cf) >= 4 and len(inc) >= 4):
        return ""

    def _n(d, *ks):
        for k in ks:
            v = d.get(k) if isinstance(d, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
        return None

    fcfs = [_n(q, "freeCashFlow") for q in cf[:4]]
    if any(v is None for v in fcfs):
        fcfs = [(_n(q, "operatingCashFlow") or 0) + (_n(q, "capitalExpenditure") or 0) for q in cf[:4]]
    ttm_fcf = sum(v for v in fcfs if isinstance(v, (int, float))) if fcfs else None
    epss = [_n(q, "epsDiluted", "epsdiluted", "eps") for q in inc[:4]]
    ttm_eps = sum(epss) if all(isinstance(v, (int, float)) for v in epss) else None
    q0 = _n(inc[0], "epsDiluted", "epsdiluted", "eps")
    q4 = _n(inc[4], "epsDiluted", "epsdiluted", "eps") if len(inc) >= 5 else None
    yoy = ((q0 - q4) / abs(q4) * 100) if (isinstance(q0, (int, float)) and isinstance(q4, (int, float)) and q4) else None

    def _a(v):
        a = abs(v)
        return f"{v/1e9:.2f}B" if a >= 1e9 else (f"{v/1e6:.0f}M" if a >= 1e6 else f"{v:.0f}")

    parts = []
    if isinstance(ttm_fcf, (int, float)):
        parts.append(f"TTM FCF {_a(ttm_fcf)}")
    if isinstance(ttm_eps, (int, float)):
        parts.append(f"TTM diluted EPS {ttm_eps:.2f}")
    if isinstance(yoy, (int, float)):
        parts.append(f"latest-Q EPS YoY {yoy:+.0f}%")
    if not parts:
        return ""
    asof = (cf[0].get("date") if isinstance(cf[0], dict) else "") or ""
    return ("\n\n=== TTM / LATEST QUARTER (FMP, as of " + asof + " — USE THESE OVER THE "
            "FISCAL-YEAR-ANNUAL FCF/EPS ABOVE WHEN THEY DIFFER) ===\n" + " | ".join(parts))


def _live_corrections(sym: str) -> str:
    """FIX/path-A (2026-06): override the two scan fields the audit found most often wrong — net
    debt (sign-flips) and the insider 'buy ratio' (comp grants counted as buys) — with live
    recomputed values, so the debate is correct IMMEDIATELY (before the next scan propagates the
    screener_v6 root fixes). '' on any failure."""
    if not sym:
        return ""
    key = get_key("FMP_API_KEY")
    if not key:
        return ""
    base = "https://financialmodelingprep.com/stable"
    out = []
    try:
        bs = requests.get(base + "/balance-sheet-statement",
                          params={"symbol": sym, "period": "quarter", "limit": 1, "apikey": key}, timeout=20).json()
        if isinstance(bs, list) and bs:
            b = bs[0]

            def _n(*ks):
                for kk in ks:
                    v = b.get(kk)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        return v
                return 0

            td = _n("totalDebt") or (_n("longTermDebt") + _n("shortTermDebt"))
            cash = _n("cashAndShortTermInvestments") or (_n("cashAndCashEquivalents") + _n("shortTermInvestments"))
            nd = td - cash
            # 2026-07-08 (KBR incident): FMP totalDebt INCLUDES capitalized leases, but company 8-Ks
            # usually present borrowings-only — an agent (or skeptic) comparing the two sees a phantom
            # "overstatement" (~$228M of leases read as a $270M error). State the composition so both
            # definitions are visible and the record says which one its SoP uses.
            leases = _n("capitalLeaseObligations")
            nd_exlease = nd - leases

            def _amt(x):
                return f"{x/1e9:.2f}B" if abs(x) >= 1e9 else f"{x/1e6:.0f}M"

            if nd >= 0:
                lab = (f"NET DEBT {_amt(nd)} (borrowings {_amt(td - leases)} + capitalized leases {_amt(leases)}, "
                       f"minus cash {_amt(cash)}; ex-lease net debt ≈ {_amt(nd_exlease)} — filings often quote the "
                       f"ex-lease figure; STATE which definition your SoP uses) — this is a LIABILITY; "
                       f"in any Sum-of-Parts SUBTRACT it from enterprise value, NEVER add it back as 'net cash'")
            else:
                lab = (f"NET CASH {_amt(-nd)} (cash {_amt(cash)} exceeds total debt {_amt(td)}, "
                       f"incl. capitalized leases {_amt(leases)}) — a genuine SoP add-back")
            out.append(f"Net debt/cash (recomputed from the balance sheet, {b.get('date','latest Q')}): {lab}; "
                       f"use this, not the scan's net_debt above")
    except Exception:
        pass
    try:
        import screener_v6 as _sv
        if not getattr(_sv, "FMP_KEY", ""):
            _sv.FMP_KEY = key
        a = _sv.get_insider_activity(sym)
        if a.get("_evaluated"):
            b_, s_ = a.get("open_market_buys", 0), a.get("open_market_sells", 0)
            if b_ == 0 and s_ == 0:
                out.append("Insider (open-market, last ~100 filings): ZERO open-market purchases or sales "
                           "— IGNORE any 'insider buy ratio' above (it counts grants/options/gifts, not real buys)")
            else:
                out.append(f"Insider (open-market only): {b_} buys ({a.get('buy_shares',0):,}sh) vs "
                           f"{s_} sells ({a.get('sell_shares',0):,}sh) — this is the REAL conviction signal, "
                           f"NOT the grant-inflated buy_ratio above")
    except Exception:
        pass
    if not out:
        return ""
    return "\n\n=== LIVE CORRECTIONS (override the scan's net-debt and insider fields above) ===\n" + "\n".join(out)


def _analyst_targets_block(sym: str) -> str:
    """Analyst price targets, as-of dated (2026-07-15). The scan hands the debate a single
    consensus number (`target`) whose breadth/freshness the agents can't judge — the KBR
    incident showed an n=1 'consensus' arming a fake bear case. Give them the dated tape:
    price-target-consensus (levels), price-target-summary (counts + period averages, the
    thin-consensus fuse's source), price-target-news (newest individual PTs with analyst,
    date, and price-when-posted — the only FRESH per-analyst source; never previously used
    in this codebase). FMP PT coverage is US-centric: every endpoint returns empty for
    non-US listings, so in that case emit an explicit WebSearch instruction instead of
    silence (debate agents run with WebSearch + FMP MCP tools). '' only when sym/key
    missing or the request layer itself fails."""
    if not sym:
        return ""
    key = get_key("FMP_API_KEY")
    if not key:
        return ""
    base = "https://financialmodelingprep.com/stable"

    def _get(ep: str, **params):
        try:
            r = requests.get(base + "/" + ep,
                             params={**params, "symbol": sym, "apikey": key}, timeout=20).json()
            return r if isinstance(r, (list, dict)) else None
        except Exception:
            return None

    def _n(d, *ks):
        for k in ks:
            v = d.get(k) if isinstance(d, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
        return None

    cons = _get("price-target-consensus")
    summ = _get("price-target-summary")
    news = _get("price-target-news", limit=10)
    cons = cons[0] if isinstance(cons, list) and cons else (cons if isinstance(cons, dict) else None)
    summ = summ[0] if isinstance(summ, list) and summ else (summ if isinstance(summ, dict) else None)
    news = [r for r in news if isinstance(r, dict)] if isinstance(news, list) else []

    lines = []
    bits = []
    for lbl, k in (("consensus", "targetConsensus"), ("median", "targetMedian"),
                   ("high", "targetHigh"), ("low", "targetLow")):
        v = _n(cons, k)
        if v:
            bits.append(f"{lbl} {v:.2f}")
    if bits:
        lines.append("Street targets: " + " | ".join(bits))

    q_n = _n(summ, "lastQuarterCount")
    if summ:
        cnt = []
        for lbl, ck, ak in (("last month", "lastMonthCount", "lastMonthAvgPriceTarget"),
                            ("last quarter", "lastQuarterCount", "lastQuarterAvgPriceTarget"),
                            ("last year", "lastYearCount", "lastYearAvgPriceTarget")):
            c, a = _n(summ, ck), _n(summ, ak)
            if c is not None:
                cnt.append(f"{lbl}: {int(c)} PTs" + (f" avg {a:.2f}" if a else ""))
        if cnt:
            lines.append("Breadth: " + " | ".join(cnt))
        if q_n is not None and q_n < 3:
            lines.append(f"[THIN CONSENSUS: only {int(q_n)} price target(s) printed last quarter — "
                         f"this is NOT a street-wide view; weigh individual PTs below accordingly]")

    fresh = []
    newest_days = None
    for r in news[:5]:
        pt = _n(r, "priceTarget", "adjPriceTarget")
        d = str(r.get("publishedDate") or "")[:10]
        who = r.get("analystName") or r.get("analystCompany") or r.get("newsPublisher") or "unnamed"
        pw = _n(r, "priceWhenPosted")
        if pt and d:
            fresh.append(f"  {d} {who}: {pt:.2f}" + (f" (stock was {pw:.2f})" if pw else ""))
            try:
                age = (datetime.now(timezone.utc).date() - datetime.strptime(d, "%Y-%m-%d").date()).days
                newest_days = age if newest_days is None else min(newest_days, age)
            except Exception:
                pass
    if fresh:
        lines.append("Newest individual targets (dated — judge freshness yourself):")
        lines.extend(fresh)
    if newest_days is not None:
        lines.append(f"Newest PT is {newest_days} day(s) old"
                     + (" — STALE (>120d): the 'consensus' above predates current fundamentals; "
                        "verify before citing" if newest_days > 120 else ""))

    if not lines:
        # Non-US listing (or zero coverage): every FMP PT endpoint is empty. Instruct
        # rather than stay silent — the agents have WebSearch and must anchor on dated
        # sources, not invent a consensus.
        return ("\n\n=== ANALYST PRICE TARGETS ===\n"
                "No FMP analyst price-target coverage for this listing (FMP PT data is "
                "US-centric). WebSearch the current analyst consensus / recent price "
                "targets and cite dated sources before using ANY target figure; if none "
                "can be found, say so explicitly rather than assuming one.")
    return ("\n\n=== ANALYST PRICE TARGETS (FMP, as-of dated — an anchor to BEAT or FADE, "
            "not to defer to) ===\n" + "\n".join(lines))


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
        _sym0 = (financials or {}).get("symbol")
        return (json.dumps(m, indent=2, default=str) if m else "No financial metrics available.") \
            + _ttm_block(_sym0) + _live_corrections(_sym0)

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

    # ── Stock-page models & scores (Jun 2026 enrichment) — the multi-model valuation spread the
    # frontend shows, so the committee reasons off model AGREEMENT/divergence, not a single number.
    # ONLY current stock-page fields: hit_prob (ML) and the 13-factor radar are RETIRED and excluded.
    models = []
    if isinstance(g("dcf_value"), (int, float)) and g("dcf_value") > 0:
        models.append(f"DCF fair value {g('dcf_value'):.1f}")
    bfv = g("buffett_fair_value")
    if isinstance(bfv, (int, float)) and bfv > 0:
        models.append(f"Buffett fair value {bfv:.1f}")
    if models:
        lines.append("Valuation models (stock page): " + " | ".join(models))
    mos_spread = []
    for label, fld in [("DCF", "dcf_fcff_mos"), ("EPV", "epv_mos"), ("Graham", "graham_revised_mos"),
                       ("OwnerErn", "owner_earnings_mos"), ("IV15", "iv15_deep_value_mos")]:
        v = g(fld)
        if isinstance(v, (int, float)) and -2.0 < v < 2.0:   # suppress null/defect extremes
            mos_spread.append(f"{label} {v*100:+.0f}%")
    if mos_spread:
        lines.append("Per-method margin-of-safety (where models agree = higher-confidence): " + " | ".join(mos_spread))
    scores = []
    if isinstance(g("bull_score"), (int, float)):
        scores.append(f"Bull score {g('bull_score')}")
    if isinstance(g("catalyst_score"), (int, float)):
        scores.append(f"Catalyst score {g('catalyst_score')}")
    if isinstance(g("piotroski"), (int, float)) and g("piotroski") > 0:
        scores.append(f"Piotroski {int(g('piotroski'))}/9")
    if isinstance(g("altman_z"), (int, float)) and g("altman_z") != 0:
        scores.append(f"Altman-Z (solvency) {g('altman_z'):.1f}")
    if isinstance(g("days_to_earnings"), (int, float)):
        scores.append(f"Days to next earnings {int(g('days_to_earnings'))}")
    if scores:
        lines.append("Quality / scores: " + " | ".join(scores))

    # Analyst consensus (stock page) — target is the crowd's 1-yr anchor; the debate's job is to
    # judge whether the thesis BEATS or FADES that anchor, not to defer to it.
    tgt = g("target")
    if isinstance(tgt, (int, float)) and tgt > 0:
        ups = g("upside")
        ups_s = f" ({ups:+.0f}% upside)" if isinstance(ups, (int, float)) and not isinstance(ups, bool) else ""
        # thin-consensus disclosure (2026-07-08, KBR incident): FMP "consensus" can collapse to ONE
        # analyst (consensus=median=high=low) — the debate must not read n=1 as "the Street".
        n = g("target_analyst_count")
        yavg = g("target_year_avg")
        note = ""
        if isinstance(n, (int, float)) and not isinstance(n, bool) and n < 3:
            note = (f" [THIN CONSENSUS: only {int(n)} price target(s) in the last quarter — this is "
                    f"NOT a street-wide view"
                    + (f"; trailing-12mo avg {yavg:.2f} across more analysts" if isinstance(yavg, (int, float)) and not isinstance(yavg, bool) and yavg > 0 else "")
                    + "; verify the wider consensus before citing it]")
        lines.append(f"Analyst consensus target: {tgt:.2f}{ups_s}{note}")

    # Positioning / smart-money (stock page) — who's already in and which way the PT is revising.
    # NOT a thesis on its own; context for whether the committee is early or late.
    pos = []
    sm = g("smart_money_score")
    if isinstance(sm, (int, float)) and not isinstance(sm, bool):
        pos.append(f"Smart-money score {sm * 100:.0f}/100")
    ins = g("inst_score")
    if isinstance(ins, (int, float)) and not isinstance(ins, bool):
        pos.append(f"Institutional flow {ins * 100:.0f}/100")
    ptv = g("pt_velocity_60d")
    if isinstance(ptv, (int, float)) and not isinstance(ptv, bool):
        pos.append(f"Analyst-target velocity {ptv * 100:+.0f}% (vs yr-ago avg PT)")
    if pos:
        lines.append("Positioning / smart money: " + " | ".join(pos))

    # Technical posture — TIMING context only, explicitly NOT the thesis (the stock page shows it,
    # but the committee must not let chart position override fundamental judgement).
    tech = []
    price = financials.get("price")
    sma200 = g("sma200")
    if (isinstance(price, (int, float)) and price > 0
            and isinstance(sma200, (int, float)) and sma200 > 0):
        tech.append(f"price {((price - sma200) / sma200) * 100:+.0f}% vs 200d SMA")
    prox = g("proximity_52wk")
    if isinstance(prox, (int, float)) and not isinstance(prox, bool):
        tech.append(f"{prox * 100:.0f}% up the 52-wk range")
    if tech:
        lines.append("Technical posture (timing context, not thesis): " + " | ".join(tech))

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

    _sym = (financials or {}).get("symbol")
    return ("=== FUNDAMENTALS (screener scan, latest fiscal year unless noted) ===\n"
            + "\n".join(lines)) + _ttm_block(_sym) + _live_corrections(_sym) + _analyst_targets_block(_sym)


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
        if not m:
            # 8f: never fail OPEN to a neutral 3 (a malformed dossier would silently land
            # above the EXCLUDE gate). Retry once with a re-output nudge; else None, which
            # value_input() gates as CAP (fail toward caution).
            nudge = query_claude(
                INTERROGATOR_MODEL, INTERROGATOR_SYSTEM_PROMPT,
                interr_user_prompt + "\n\nYour previous dossier omitted the mandatory final line. "
                "Re-output ONLY the final line in the exact format: CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...>",
                max_tokens=200)
            m = re.search(r"CREDIBILITY_SCORE:\s*(\d+)", nudge or "")
            if m:
                interr_dossier += "\n" + (nudge or "").strip()
        result["interrogator_score"] = max(1, min(5, int(m.group(1)))) if m else None
        if m is None:
            log.warning(f"  [Interrogator] {symbol}: CREDIBILITY_SCORE unparseable after retry -> None (fail-closed)")
        mt = re.search(r"TRAJECTORY:\s*([A-Z]+)", interr_dossier)
        result["trajectory"] = mt.group(1) if mt else ""
        # Map trajectory -> legacy tone_shift for any consumer still reading it
        result["tone_shift"] = {"STRENGTHENING": "improving", "DETERIORATING": "deteriorating"}.get(
            result["trajectory"], "stable")
    else:
        log.warning(f"  [Interrogator] {symbol}: no dossier returned")
        result["interrogator_score"] = None   # 8f: fail-closed, not a neutral 3

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
        # 8d: the prompts demand a Sum-of-Parts — stop generating-and-dropping it
        result["sop_bull"] = arch_out.get("sop_bull", "")
        result["sop_bear"] = arch_out.get("sop_bear", "")

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
        # 8a: catalyst-blind value score (decoupled from the regime-tilted conviction)
        try:
            result["value_conviction"] = max(1, min(5, int(mod_out.get("value_conviction"))))
        except (TypeError, ValueError):
            result["value_conviction"] = None
        # 8d: reconciled SoP + catalyst status were demanded by the prompt and then dropped
        result["sop_fair_value"] = mod_out.get("sop_fair_value", "")
        result["sop_breakdown"] = mod_out.get("sop_breakdown", "")
        result["risk_reward"] = mod_out.get("risk_reward", "")
        result["catalyst_status"] = mod_out.get("catalyst_status", "")
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
    # Filter to debated candidates with conviction >= 3. None-safe: a fail-closed debate leaves
    # conviction/interrogator_score as EXPLICIT None (the .get default never applies), which made
    # both the filter comparison and the -x sort key crash on the first malformed dossier.
    qualified = [r for r in debate_results if (r.get("conviction") or 0) >= 3]

    # Sort by conviction DESC
    qualified.sort(key=lambda x: (-(x.get("conviction") or 0), -(x.get("interrogator_score") or 0)))
    
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
    director_last_phase = ""            # stamped below; safe default for exception paths
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
        # Debt-cycle phase-transition trigger (2026-07-27, Fork 4 = yes): a phase change —
        # e.g. DISCIPLINE -> FORCING — is exactly the event that must NOT sit unread for up
        # to 30 days, so it overrides the cost-guard and forces a director re-run.
        phase_transitioned, _phase_now = _phase_transition_check(existing_spec)
        if (not dry_run) and held_apex and (not held_reported) and (not phase_transitioned) \
                and days_since < DIRECTOR_CADENCE_DAYS:
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
            # carry the last-run phase forward (seed with current on first-ever stamp) so a
            # future transition is still detected against the phase the director LAST saw
            director_last_phase = existing_spec.get("director_last_phase") or _phase_now
        else:
            why = ("first run / empty basket" if not held_apex
                   else "held name reported earnings" if held_reported
                   else f"debt-cycle phase transition -> {_phase_now}" if phase_transitioned
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
            director_last_phase = _phase_now    # the phase this director run actually saw
        
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
        # Fork 4: the debt-cycle phase as of the last director run — the transition
        # trigger compares the live snapshot against this stamp.
        "director_last_phase": director_last_phase,
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


def _load_apex_tracking(gcs_path: str = APEX_TRACKING_PATH, local_name: str = "speculair_apex_tracking.json") -> dict:
    """Load a persistent basket track record (chained NAV + closed-position log).
    GENERATION-PINNED first: this is the RMW base of a TWO-WRITER file (nightly Cloud Run NAV mark +
    weekly publish) — a stale plain read here silently rewinds the NAV chain (the exact bug class
    that corrupted the calibration tracker). See gcs_io.gcs_read_json_fresh's invariant."""
    try:
        sys.path.insert(0, str(BASE_DIR / "alpha_compounder"))
        import gcs_io as _gio
        d = _gio.gcs_read_json_fresh(gcs_path)
        if isinstance(d, dict) and d.get("nav"):
            return d
    except Exception as e:
        log.debug(f"tracking fresh GCS load failed: {e}")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from screener_v6 import gcs_download
        d = gcs_download(gcs_path)
        if isinstance(d, dict) and d.get("nav"):
            return d
    except Exception as e:
        log.debug(f"tracking GCS load failed: {e}")
    try:
        local = FRONTEND_DIR / "public" / local_name
        if local.exists():
            return json.loads(local.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _current_prices_asof(symbols: set):
    """Current prices for `symbols` from the latest scan. Tries authenticated GCS
    (Cloud Run), then the public bucket URL, then the local file (dev without ADC).
    Returns (prices, asof): asof[sym] = the ISO day the price is dated (the scan's scan_date for
    scan names, the quote timestamp's UTC day for the FMP fallback, "" when unknown - an unknown
    date never satisfies the pending-entry tracker's "dated after the decision" test)."""
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
    out, asof = {}, {}
    scan_day = str((scan or {}).get("scan_date") or "")[:10]
    for s in (scan or {}).get("stocks", []):
        sym, px = s.get("symbol"), s.get("price")
        if sym in symbols and isinstance(px, (int, float)) and px > 0:
            out[sym] = float(px)
            asof[sym] = scan_day
    # FMP-quote fallback for OFF-SCAN members — mega-caps not in the screened universe (e.g. Visa "V",
    # TSM, CCJ in the disruptor book). Without this they stamp entry_price + NAV-mark to 0 (showed as a
    # blank/stale card). Best-effort; the scan stays the primary source.
    missing = [s for s in symbols if s not in out]
    if missing:
        try:
            key = get_key("FMP_API_KEY")
            if key:
                base = "https://financialmodelingprep.com/stable"
                for i in range(0, len(missing), 50):
                    csv = ",".join(missing[i:i + 50])
                    r = requests.get(base + "/batch-quote", params={"symbols": csv, "apikey": key}, timeout=20)
                    if r.ok:
                        for q in (r.json() or []):
                            sym, px = q.get("symbol"), q.get("price")
                            if sym in symbols and isinstance(px, (int, float)) and px > 0:
                                out[sym] = float(px)
                                ts = q.get("timestamp")
                                asof[sym] = (datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
                                             if isinstance(ts, (int, float)) and ts > 0 else "")
        except Exception:
            pass
    return out, asof


def _current_prices(symbols: set) -> dict:
    """Prices only (the weekly book publishers' price-coverage checks); see _current_prices_asof."""
    return _current_prices_asof(symbols)[0]


# ── PENDING ENTRY (2026-10-06, Bruno: "a seat is bought at the first close AFTER the decision, or at
# its gate") ───────────────────────────────────────────────────────────────────────────────────────
# A NEW seat in a gated book (regime + value publishers pass entry_rules="gated") opens PENDING: no
# entry price, outside the NAV, n_open and the win rate. It fills at the first daily close strictly
# after the decision (enter now), at the first close at or below its add level (a price wait), or not
# at all while it waits on an event / a blocked gate (a later debate ungates or drops it). Every piece
# of pending state lives INSIDE positions[sym]: main's older Saturday writer rebuilds the top-level
# state dict from a fixed key list and would silently drop a new top-level key. The pass below is
# state-driven, so a legacy caller (FR / mining / FDT / recovery / the Saturday mark) still fills or
# strips an existing pending seat - it just never opens or re-gates one. Legacy = bit-identical.
# Order of the pass (CRO review 2026-10-06): the fill on the STORED gate is resolved FIRST, so this
# run's decision never cancels or re-gates an order whose gate was already met; such a seat is held,
# or - when the Director dropped it - exits through the rotation with a real closed leg.
_ENTRY_RULES = ("legacy", "defer", "gated")
_WASHOUT_DD = 0.10            # informational wash-out stamp on a pending seat (the next debate reads it)
_FILL_CACHE: dict = {}        # one EOD lookup per (sym, since, kind, level) per process: EW + weighted fill alike
_GATE_LEDGER = BASE_DIR / "_opus_debate" / "_entry_gate_ledger.jsonl"
_GATE_MODES = ("NOW", "AT_LEVEL", "ON_EVENT", "NONE")


def _posnum(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def _tf(p, key, *nested):
    """Flat typed field first, then a nested {"entry": {...}} / {"cro": {...}} copy (cro_scorecard
    reads both shapes)."""
    v = p.get(key)
    if v not in (None, ""):
        return v
    for blk, k in nested:
        b = p.get(blk)
        if isinstance(b, dict) and b.get(k) not in (None, ""):
            return b.get(k)
    return None


def _entry_gate(p, entry_rules, today):
    """The gate a pending seat rests on: {"kind": next_close | price | event | blocked, ...}.
    Source order: "defer" -> next_close; the post layer's effective order p["entry_gate"]
    (_post_common.entry_gate: {letter, mode, level, event} - a dated Director override and a floor /
    trim-line re-derived A are already applied there); else the same rule on the reconciled posture
    (cro_verdict / entry_posture / cro_add_px / cro_add_event - a KEEP'd pending seat carries no
    entry_gate); else the typed record fields (entry_mode / entry_level_px / entry_event); else
    next_close (fail-open: nothing known never blocks). A price level at or below the exit
    (thesis_break_px / exit_level_px / downside_floor) is blocked (Bruno's rule)."""
    if entry_rules == "defer":
        return {"kind": "next_close", "since": today, "source": "defer"}
    exit_px = max([x for x in (_posnum(p.get("thesis_break_px")),
                               _posnum(_tf(p, "exit_level_px", ("entry", "exit_level_px"))),
                               _posnum(p.get("downside_floor"))) if x] or [0]) or None
    posture = str(p.get("entry_posture") or "")
    key = posture.split(":")[0].strip()
    detail = posture.split(":", 1)[1].strip() if ":" in posture else ""
    verdict = str(p.get("cro_verdict") or "").strip().upper()[:1]
    eg = p.get("entry_gate") if isinstance(p.get("entry_gate"), dict) else {}
    mode, lvl, event, src = None, None, "", ""
    if str(eg.get("mode") or "").strip().upper() in _GATE_MODES:
        mode, src = str(eg["mode"]).strip().upper(), "entry_gate"
        lvl, event = _posnum(eg.get("level")), str(eg.get("event") or "")
    elif key or verdict in ("A", "B", "C"):
        # mirror of _post_common.entry_gate on the reconciled pick (held seats get no entry_gate there)
        lvl = _posnum(p.get("cro_add_px"))
        event = str(p.get("cro_add_event") or "").strip() or detail
        src = "entry_posture"
        if key in ("enter_now_carry", "scale_in"):
            mode = "NOW"
        elif verdict == "C":
            mode = "NONE"
        elif key == "wait_for_weakness":
            mode = "AT_LEVEL"
        elif key == "on_confirmation":
            mode = "ON_EVENT"
        elif verdict == "A":
            mode = "NOW"
        elif verdict == "B":
            mode = "AT_LEVEL" if lvl else ("ON_EVENT" if event else "NONE")
        else:
            mode = "NOW"                     # an unknown posture with no debate grade: nothing says wait
    else:
        m = str(_tf(p, "entry_mode", ("entry", "mode"), ("entry", "entry_mode")) or "").strip().upper()
        if m in _GATE_MODES:
            mode, src = m, "entry_mode"
            lvl = _posnum(_tf(p, "entry_level_px", ("entry", "entry_level_px"), ("entry", "level_px")))
            event = str(_tf(p, "entry_event", ("entry", "event")) or "")
    if mode is None or mode == "NOW":
        g = {"kind": "next_close"}
    elif mode == "AT_LEVEL" and lvl:
        g = {"kind": "price", "level_px": lvl,
             "washout_type": _tf(p, "washout_type", ("entry", "washout_type"))}
    elif mode == "ON_EVENT":
        g = {"kind": "event", "event": event[:160]}
    else:
        g = {"kind": "blocked", "reason": f"entry_mode={mode}" + (" without an add level" if mode == "AT_LEVEL" else "")}
    g["source"] = src or "default"
    if posture:
        g["posture"] = posture[:200]
    if g["kind"] == "price" and exit_px and g["level_px"] <= exit_px:
        g = {"kind": "blocked", "reason": f"add level {g['level_px']} at/below exit {exit_px}",
             "source": g.get("source")}
    g["since"] = today
    return g


def _gate_sig(g):
    """What re-dates a resting order: the gate kind and its level (an event reworded is not a new gate)."""
    g = g or {}
    lv = g.get("level_px")
    return (g.get("kind"), round(lv, 4) if isinstance(lv, (int, float)) else None)


def _first_close_after(sym, after, level=None):
    """(date, close) of the first daily close strictly after `after` (and at or below `level` when
    given), from FMP stable historical-price-eod/full (unadjusted close - the scan marks' basis).
    Today's row is never used (it can be a live, in-session bar); it is read on the next run.
    None when no qualifying close exists yet; the string "ERR" on any failure / no key."""
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        frm = (datetime.strptime(after, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if frm >= today:
            return None
        key = get_key("FMP_API_KEY")
        if not key:
            return "ERR"
        r = requests.get("https://financialmodelingprep.com/stable/historical-price-eod/full",
                         params={"symbol": sym, "from": frm, "to": today, "apikey": key}, timeout=20)
        if not r.ok:
            return "ERR"
        data = r.json()
        rows = data.get("historical") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return "ERR"
        best = None
        for row in rows:
            d = str((row or {}).get("date") or "")[:10]
            c = (row or {}).get("close")
            if not (d and after < d < today) or not _posnum(c):
                continue
            if level is not None and float(c) > level:
                continue
            if best is None or d < best[0]:
                best = (d, float(c))
        return best
    except Exception:
        return "ERR"


def _resolve_fill(s, pos, prices, asof, last_prices, prev_mark):
    """(fill_date, fill_px, source) for a pending seat whose gate is met, else None. Only next_close /
    price gates fill. EOD first; when the EOD lookup fails, an older writer's mark dated after the
    decision (prior_mark), else this run's mark dated after it (mark) - never a quote seen before."""
    g = pos.get("gate") or {"kind": "next_close", "since": pos.get("pending_since") or ""}
    kind = g.get("kind")
    if kind not in ("next_close", "price"):
        return None
    after = g.get("since") or pos.get("pending_since") or ""
    if not after:
        return None
    level = g.get("level_px") if kind == "price" else None
    k = (s, after, kind, level)
    if k not in _FILL_CACHE:
        _FILL_CACHE[k] = _first_close_after(s, after, level)
    r = _FILL_CACHE[k]
    if isinstance(r, tuple):
        return r[0], float(r[1]), ("level_close_eod" if level else "next_close_eod")
    if r == "ERR":
        lp = last_prices.get(s)
        if lp and prev_mark and prev_mark > after and (level is None or lp <= level):
            return prev_mark, float(lp), "prior_mark"
        cp, ad = prices.get(s), (asof.get(s) or "")
        if cp and ad > after and (level is None or cp <= level):
            return ad, float(cp), "mark"
    return None


def _gate_log(local_name, row):
    """Append one pending-entry event to the local gate ledger (best-effort; on Cloud Run the file is
    ephemeral - fills stay durable via positions[].filled_from_pending / closed[].filled_from_pending)."""
    try:
        with open(_GATE_LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"book": local_name, **row}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _update_apex_tracking(apex_basket: list, push_gcs: bool = True,
                          gcs_path: str = APEX_TRACKING_PATH,
                          local_name: str = "speculair_apex_tracking.json",
                          weights: dict = None, entry_rules: str = "legacy") -> dict:
    """Persistent live-forward track record for a basket (apex by default; pass gcs_path/local_name
    for a separate book e.g. the Value Lens).

    Chains an equal-weight NAV across rebalances (anchored to entry prices at inception,
    so it measures performance from when the basket was established — not from go-live of
    the tracking code), logs a realized return whenever a name rotates out, and appends
    one history point per day. Returns a compact summary embedded in speculair_baskets.json
    for the frontend. Best-effort — callers wrap in try/except so it never breaks the run.

    entry_rules (2026-10-06): "legacy" (default - a new seat is booked at this run's mark, exactly as
    before), "defer" (a new seat opens PENDING and fills at the first close after this run) or
    "gated" (PENDING on its entry gate: next close / add level / event / blocked). Pending seats
    already in the state are filled / stripped / cancelled under every mode (see PENDING ENTRY above).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    apex = [p for p in (apex_basket or []) if p.get("symbol")]
    syms = {p["symbol"] for p in apex}
    if not syms:
        return {}

    tr = _load_apex_tracking(gcs_path, local_name)
    nav = float(tr.get("nav") or 100.0)
    last_prices = dict(tr.get("last_prices") or {})
    positions = dict(tr.get("positions") or {})
    history = list(tr.get("history") or [])
    closed = list(tr.get("closed") or [])
    # SURVIVE THE RE-CUT (2026-10-06): the Saturday Cloud Run scan job marks NAV with main's older
    # copy of this function, which still writes closed[-80:] into the same GCS state. The local file
    # is written only by local runs (full list), so union its legs back in on every local run.
    # Dedup on (symbol, entry_date, exit_date); order stays chronological by exit date.
    try:
        _lp = FRONTEND_DIR / "public" / local_name
        if _lp.exists():
            _lc = (json.loads(_lp.read_text(encoding="utf-8")) or {}).get("closed") or []
            _k = lambda c: (c.get("symbol"), c.get("entry_date"), c.get("exit_date"))
            _have = {_k(c) for c in closed}
            _extra = [c for c in _lc if isinstance(c, dict) and _k(c) not in _have]
            if _extra:
                closed = sorted(_extra + closed, key=lambda c: (c.get("exit_date") or "", c.get("symbol") or ""))
                log.info(f"tracking {local_name}: restored {len(_extra)} closed leg(s) a truncating writer dropped")
    except Exception as e:
        log.debug(f"tracking local closed-merge skipped: {e}")
    # a pending seat the Director dropped still needs a mark: its order may have filled before this run,
    # and then it exits with a real closed leg (empty set when nothing is pending - legacy unchanged)
    _pend_syms = {s for s, v in positions.items() if isinstance(v, dict) and v.get("entry_pending")}
    prices, asof = _current_prices_asof(syms | set(last_prices.keys()) | _pend_syms)
    period_ret = 0.0

    def _wmean(rets_by_sym):                        # weighted mean over names that have a return; equal-weight fallback
        if not rets_by_sym:
            return 0.0
        if not weights:
            return sum(rets_by_sym.values()) / len(rets_by_sym)
        ws = {s: weights.get(s, 0) for s in rets_by_sym}
        tot = sum(ws.values())
        if tot <= 0:
            return sum(rets_by_sym.values()) / len(rets_by_sym)
        return sum(rets_by_sym[s] * ws[s] / tot for s in rets_by_sym)

    # ── PENDING ENTRY pass (state-driven: runs for every caller, incl. the Saturday mark) ──
    if entry_rules not in _ENTRY_RULES:
        entry_rules = "legacy"
    pick_by = {p["symbol"]: p for p in apex}
    prev_mark = tr.get("last_date")
    ev = (lambda row: _gate_log(local_name, row)) if weights is None else (lambda row: None)  # EW call logs once
    # an older writer that dropped a never-filled seat wrote a closed leg with entry_date null - not a trade
    _ph = [c for c in closed if isinstance(c, dict) and "entry_date" in c and c["entry_date"] is None]
    if _ph:
        closed = [c for c in closed if not (isinstance(c, dict) and "entry_date" in c and c["entry_date"] is None)]
        log.warning(f"tracking {local_name}: dropped {len(_ph)} phantom closed leg(s) of never-filled seats")
    for s, pos in list(positions.items()):
        if not (isinstance(pos, dict) and pos.get("entry_pending")):
            continue
        if not pos.get("pending_since"):      # hand-migrated seat with no decision date: rests from this run
            pos["pending_since"] = (pos.get("gate") or {}).get("since") or today
        # older-writer marks since this seat was last checked (main's Saturday writer has no pending pass)
        seen = pos.get("pending_checked") or pos.get("pending_since") or ""
        k_marks = sum(1 for h in history if seen < str((h or {}).get("date") or "") < today)
        # FILL FIRST (CRO review 2026-10-06, findings 1+4): the order resting on its STORED gate (with its
        # own since) is checked against closes that printed BEFORE this run, before this run's decision may
        # cancel or re-gate it - a later decision must never erase a fill that already happened. A filled
        # seat is HELD (keep != buy) and never re-gated; a filled seat the Director dropped exits through
        # the rotation loop below with a real closed leg.
        fill = _resolve_fill(s, pos, prices, asof, last_prices, prev_mark)
        if fill:
            fd, fpx, src = fill
            since = pos.get("pending_since") or fd
            try:
                waited = (datetime.strptime(fd, "%Y-%m-%d") - datetime.strptime(since, "%Y-%m-%d")).days
            except Exception:
                waited = None
            pos.update(entry_price=round(fpx, 4), entry_date=fd, entry_price_source=src,
                       filled_from_pending={"pending_since": since, "gate": pos.get("gate"), "fill_date": fd,
                                            "fill_px": round(fpx, 4), "decision_px": pos.get("decision_px"),
                                            "waited_days": waited})
            lp = _posnum(last_prices.get(s))
            if lp and k_marks >= 2 and prev_mark and fd < prev_mark:
                # finding 2: main's writer already chained this seat from its first mark through a mark dated
                # after the fill. Stepping from the fill would count those legs twice, so the chained mark
                # stays the base; the move from the fill to the first mark is not in the NAV.
                pos["filled_from_pending"]["nav_base"] = {"kind": "older_writer_chain", "px": round(lp, 4),
                                                          "date": prev_mark}
                pos["nav_from"] = prev_mark       # the base is that mark: never step it on an older quote
                log.warning(f"tracking {local_name}: {s} filled {fd} at {round(fpx, 4)} but {k_marks - 1} "
                            f"older-writer NAV step(s) had already chained it - kept the chained base {round(lp, 4)} "
                            f"(the move from the fill to the first mark is not in the NAV)")
            else:
                if lp and k_marks >= 2:
                    log.warning(f"tracking {local_name}: {s} chained by {k_marks - 1} older-writer NAV step(s) "
                                f"before its fill on {fd} - the base is the fill")
                pos["nav_from"] = fd
                last_prices[s] = fpx              # NAV base = the fill, never a pre-fill mark
            pos.pop("entry_pending", None)
            pos.pop("pending_checked", None)
            ev({"date": today, "symbol": s, "event": "filled", "fill_date": fd, "fill_px": round(fpx, 4),
                "source": src, **({} if s in syms else {"dropped": True})})
            continue
        if s not in syms:                     # dropped before its gate was met: no trade, no closed leg
            positions.pop(s, None)
            last_prices.pop(s, None)
            ev({"date": today, "symbol": s, "event": "cancelled", "pending_since": pos.get("pending_since"),
                "gate": pos.get("gate")})
            continue
        if entry_rules != "legacy":
            # the new gate rests from today (since=today), so it can only fill on a later run
            g_new, g_old = _entry_gate(pick_by[s], entry_rules, today), (pos.get("gate") or {})
            if _gate_sig(g_new) != _gate_sig(g_old):
                if g_new["kind"] == "next_close":
                    pos["pending_since"] = today          # ungated by THIS decision -> the order is re-dated
                pos["gate_history"] = (pos.get("gate_history") or [])[-9:] + [{"date": today, "from": g_old, "to": g_new}]
                pos["gate"] = g_new
                ev({"date": today, "symbol": s, "event": "regated", "from": g_old, "to": g_new})
            elif g_new.get("kind") == "event" and g_new.get("event") != g_old.get("event"):
                pos["gate"] = {**g_old, "event": g_new.get("event")}
        if s in last_prices:                      # an older writer marked an unfilled seat: strip it before the step
            if k_marks >= 2:
                log.warning(f"tracking {local_name}: {s} unfilled but chained by {k_marks - 1} older-writer NAV step(s)")
            last_prices.pop(s, None)
        cp, dpx = prices.get(s), _posnum(pos.get("decision_px"))
        if (not pos.get("washout_hit") and cp and dpx and (asof.get(s) or "") > (pos.get("pending_since") or "")
                and cp <= dpx * (1 - _WASHOUT_DD)):
            # informational for the next debate - never a fill (a price-gate fill IS the "level reached" event)
            pos["washout_hit"] = {"date": today, "px": round(cp, 4), "kind": "drawdown_10pct"}
            ev({"date": today, "symbol": s, "event": "washout", "px": round(cp, 4)})
        pos["pending_checked"] = today

    stepped = set()
    if not tr:
        # INCEPTION — anchor NAV to entry prices so it reflects performance since the
        # basket was established (entry_date), not since the tracker first ran.
        rets = {p["symbol"]: prices[p["symbol"]] / p["entry_price"] - 1 for p in apex
                if (p.get("entry_price") or 0) > 0 and prices.get(p["symbol"], 0) > 0}
        period_ret = _wmean(rets)
        nav = 100.0 * (1 + period_ret)
        inception = min((p.get("entry_date") for p in apex if p.get("entry_date")), default=today)
        history = [{"date": inception, "nav": 100.0, "ret": 0.0, "n": len(apex)}]
    else:
        inception = tr.get("inception_date") or today
        # a just-filled name joins the step only once its mark is dated on/after the fill (nav_from)
        prior = [s for s in last_prices if s in prices and last_prices[s] > 0
                 and (asof.get(s) or "") >= ((positions.get(s) or {}).get("nav_from") or "")]
        if prior and tr.get("last_date") != today:
            period_ret = _wmean({s: prices[s] / last_prices[s] - 1 for s in prior})
            nav *= (1 + period_ret)
            stepped = set(prior)
        for s in list(last_prices.keys()):          # rotations → realized exits
            if s not in syms:
                pos = positions.get(s, {})
                ep = pos.get("entry_price") or last_prices[s]
                # finding 3: a fill whose mark predates it (nav_from set, not stepped) exits at the fill base
                # (0%, as the NAV booked it), never at a quote older than the fill
                xp = (last_prices[s] if (pos.get("nav_from") and s not in stepped)
                      else prices.get(s, last_prices[s]))
                leg = {"symbol": s, "entry_date": pos.get("entry_date", ""), "exit_date": today,
                       "entry_price": round(ep, 4), "exit_price": round(xp, 4),
                       "return_pct": round((xp / ep - 1) * 100, 2) if ep else 0.0,
                       "conviction": pos.get("conviction", 0)}
                if pos.get("filled_from_pending"):
                    leg["filled_from_pending"] = pos["filled_from_pending"]
                closed.append(leg)
                positions.pop(s, None)

    new_last = {}
    for p in apex:
        s = p["symbol"]
        cp = prices.get(s) or p.get("price") or last_prices.get(s) or 0.0
        pos = positions.get(s)
        if pos is None:
            carried = (p.get("entry_price") or 0) > 0 and str(p.get("entry_date") or today) < today
            if entry_rules == "legacy" or carried:
                positions[s] = {"entry_price": p.get("entry_price") or cp,
                                "entry_date": p.get("entry_date") or today,
                                "conviction": p.get("conviction", 0)}
            else:
                # NEW seat in a gated book: PENDING - no entry price, no last price (outside NAV / n_open)
                g = _entry_gate(p, entry_rules, today)
                dpx = _posnum(p.get("live_price")) or (cp or None)
                positions[s] = {"entry_price": None, "entry_date": None, "conviction": p.get("conviction", 0),
                                "entry_pending": True, "pending_since": today, "gate": g,
                                "decision_px": dpx, "pending_checked": today}
                ev({"date": today, "symbol": s, "event": "opened", "gate": g, "decision_px": dpx})
                if g["kind"] == "blocked":
                    log.warning(f"tracking {local_name}: {s} opened PENDING on a BLOCKED gate ({g.get('reason')})")
                elif g["kind"] == "price" and dpx and not (0.2 < g["level_px"] / dpx < 5):
                    log.warning(f"tracking {local_name}: {s} add level {g['level_px']} vs decision price {dpx} "
                                f"looks like a unit slip (GBp vs GBP?) - check the record")
                continue
        else:
            pos["conviction"] = p.get("conviction", pos.get("conviction", 0))
            if pos.get("entry_pending"):
                continue
        nf = positions[s].get("nav_from")
        if nf:
            if s in stepped:
                positions[s].pop("nav_from", None)
            else:                                   # hold the fill as the base until a mark dated after it
                new_last[s] = last_prices.get(s) or positions[s].get("entry_price") or cp
                continue
        new_last[s] = cp

    # pending seats sit outside n_open / the history n (counted per pick, so a no-pending run is unchanged)
    n_open = sum(1 for p in apex if not (positions.get(p["symbol"]) or {}).get("entry_pending"))
    pend = {s: positions[s] for s in sorted(syms) if (positions.get(s) or {}).get("entry_pending")}
    point = {"date": today, "nav": round(nav, 4), "ret": round(period_ret, 6), "n": n_open}
    if history and history[-1].get("date") == today:
        history[-1] = point
    else:
        history.append(point)
    history = history[-400:]

    # closed: the FULL realized-trade list (2026-10-06). It used to be cut to the last 80 here, so
    # the regime book permanently lost its oldest legs (25 had to be recovered from git for the
    # 2026-10 audit) - a track record must not forget trades. ~150 bytes/leg, so size is a non-issue.
    state = {"inception_date": inception, "nav": round(nav, 4), "last_date": today,
             "last_prices": new_last, "positions": positions,
             "history": history, "closed": closed}
    try:
        (FRONTEND_DIR / "public" / local_name).write_text(
            json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log.debug(f"tracking local write failed: {e}")
    if push_gcs:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from screener_v6 import gcs_upload
            gcs_upload(gcs_path, state)
        except Exception as e:
            log.warning(f"apex tracking GCS upload failed: {e}")
    log.info(f"Apex tracking: NAV {nav:.2f} ({(nav / 100 - 1) * 100:+.1f}% since {inception}) | "
             f"{n_open} open, {len(pend)} pending, {len(closed)} closed")

    wins = [c for c in closed if c.get("return_pct", 0) > 0]
    return {"inception_date": inception, "since_inception_pct": round((nav / 100.0 - 1) * 100, 2),
            "nav": round(nav, 2), "n_open": n_open, "n_pending": len(pend),
            # seated but NOT bought: no entry price, outside the NAV / n_open / win rate until the gate fills
            "pending": [{"symbol": s, "pending_since": v.get("pending_since"), "gate": v.get("gate"),
                         "washout_hit": v.get("washout_hit")} for s, v in pend.items()],
            "n_closed": len(closed),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
            # closed list matches the PERSISTED state (full since 2026-10-06), not a tighter -20.
            # The value card embeds this return value in speculair_value_apex.json and renders its
            # length as "N rotated"; at -20 it under-reported 34 legs as 20 and silently dropped
            # the 14 oldest (all pre-2026-06-30), including HRB's first, LOSING leg while keeping
            # its +52.65% winner - a truncation that flatters a name. n_closed above is the
            # authoritative count either way.
            "history": history, "closed": closed}


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
