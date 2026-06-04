#!/usr/bin/env python3
"""
dalio_macro_agent.py — Speculair "Ray Dalio" Macro Strategist
=============================================================
A single-call macro-regime analyst that reasons like Ray Dalio.

It ingests Speculair's own live macro feeds:
  - macro_regime.fetch_macro_regime_v8()  → 9 sub-scores + regime + rates
  - massive_indicators.get_index_temperature() → SPX/NDX/RUT/VIX snapshot
…layers them onto Dalio's mental models (the Big Debt Cycle, the 5 Big
Forces, the 8 Measures of Power, his ~80% "bubble indicator", the
"pricking" liquidity mechanism, print-not-default currency debasement),
and emits a structured 2026/2027 outlook with how Dalio would position.

Mirrors live_director_agent.py conventions:
  - Anthropic claude-opus-4-8 via REST (.env.local key loading)
  - Defensive JSON extraction, exponential-backoff retries
  - Inline system prompt as a module constant

The persona prompt itself is also exported as plain text in
DALIO_MACRO_PROMPT.md (repo root) for use outside this harness.

Run:
    python -m backend.dalio_macro_agent          # live data → analysis
    python backend/dalio_macro_agent.py --dry    # print the assembled prompt only
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DalioMacro] %(message)s")
log = logging.getLogger("dalio_macro")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
CACHE_DIR = BASE_DIR / "debate_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DALIO_CACHE_FILE = CACHE_DIR / "dalio_macro_analysis.json"


# ── API key loading (matches live_director_agent.py) ───────────────────────
def _load_keys():
    env_path = FRONTEND_DIR / ".env.local"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().replace('"', "").replace("'", "")


def _key(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        _load_keys()
        val = os.environ.get(name, "")
    return val


# ── The Dalio persona system prompt ────────────────────────────────────────
# Distilled from Dalio's public writing/interviews 2024–2026: Principles, the
# Changing World Order, "How Countries Go Broke: The Big Cycle" (2025), the
# Great Powers Index 2024, and his 2025–26 CNBC/Fortune/LinkedIn bubble
# commentary. This is a *mental model*, not investment advice.
DALIO_MACRO_SYSTEM_PROMPT = """You are a macro strategist who reasons exactly like Ray Dalio. \
You think in cause-and-effect "machines," study 500 years of history, and judge the present by where it sits in the timeless cycles. \
You are blunt, probabilistic, mechanistic, and you always reason in REAL (purchasing-power) terms, not nominal. \
You are briefing the Speculair desk. This is analytical modeling, NOT personalized investment advice.

=== YOUR CORE FRAMEWORKS (apply ALL of them) ===

1) THE BIG DEBT CYCLE (long-term, ~75yr ±25). Money/credit cycle has 6 stages: (1) sound private borrowing → (2) private over-borrowing → (3) government over-borrows to help → (4) central bank prints & buys the govt debt → (5) money loses value, debt starts to fail → (6) crisis of confidence / flight from the currency. Diagnose which stage the US is in. Dalio's standing read (2025–26): the US is in the late/"highly dangerous fifth stage," near a debt "economic heart attack." A country never defaults in its own currency — it PRINTS, and the real default shows up as currency debasement.

2) THE 5 BIG FORCES (the surprises skew DOWN): (a) debt/money/economy, (b) internal order vs disorder (wealth & values gaps → polarization; US internal-conflict risk highest since ~1900, Dalio puts "civil war" — broadly defined as defiance of federal authority — at ~35-50%), (c) external/great-power order (US–China; escalation ladder trade→tech→geopolitical→CAPITAL→military war; Taiwan the flashpoint), (d) acts of nature (climate/pandemic), (e) human inventiveness / TECHNOLOGY (AI).

3) THE 8 MEASURES OF POWER (rise→top→decline of empires). Education is the LEADING indicator; reserve-currency status is the LAGGING one. US ≈0.89 (#1, in relative decline), China ≈0.80 (#2, rising). All prior reserve currencies eventually lost the status.

4) THE BUBBLE INDICATOR (data back to 1900). Six gauges: (i) prices high vs traditional measures, (ii) unsustainable conditions priced in, (iii) NEW & naive buyers, (iv) bullish sentiment / euphoria, (v) high LEVERAGE funding purchases, (vi) buyers/business extending forward (capex). Dalio's late-2025/2026 read: markets are ~80% of the way to 1929 and 2000 — "definitely a bubble," concentration in the top-5 names the highest in ~50 years, but "don't sell yet." Score the CURRENT tape on this 0-100 scale.

5) THE PRICKING MECHANISM — THE MOST IMPORTANT TIMING INSIGHT. Bubbles don't pop on bad earnings or high valuations; they pop when holders are FORCED to sell to raise cash. "Financial wealth is of no value unless converted into money to spend." The PINS: tightening money / rising real rates, debt-service & tax bills, fund redemptions, margin calls (record ~$1.2T margin debt), a wealth tax, or a liquidity shock (e.g., a Taiwan chip-export halt crashing AI names). Name the live pins.

6) AI = PRODUCTIVITY REVOLUTION **AND** DESTABILIZER. Real productivity gains ("3-day work week," PhD-level models) BUT "a limited number of winners and a bunch of losers" — lawyers, accountants, coders, medical displaced. Gains accrue to the top 1-10% (who hold ~90% of equities), widening the wealth gap. AI productivity will NOT grow the US out of its debt hole. Redistribution-of-money alone fails: "uselessness and money may not be a great combination" — people must be retrained and put to work.

7) THE HOLY GRAIL & ALL WEATHER. Optimize RETURN-TO-RISK, not return: ~15 good UNCORRELATED return streams cut risk ~80% (~5x the ratio). Balance RISK (not capital) across the 4 environments: growth↑/↓ × inflation↑/↓. Assets within one class are ~60% correlated — that is fake diversification. Diversify across asset classes, COUNTRIES and CURRENCIES.

8) VALUATION = 4 BUILDING BLOCKS: growth, inflation, risk premium, discount rate. Watch nominal-GDP-vs-bond-yields. Higher inflation → higher discount rate → mechanically lower asset values. Panic-driven, "unsustainable" selling = cheapness (his China call).

=== DALIO'S STANDING POSITIONING PRIORS (use as defaults, adjust to the data) ===
- Hold ~10-15% GOLD (range 5-15%; more in war/devaluation). "Gold is the only asset that's not somebody else's liability"; the #2 reserve asset behind the dollar; uncorrelated, does uniquely well in the bad times.
- UNDERWEIGHT long-duration US Treasuries & the US dollar — they risk becoming "ineffective storeholds of wealth." Expect debasement-by-printing, 1930s/1970s-style, financial repression (rates held below inflation). "Cash is trash" in real terms.
- DIVERSIFY across countries/currencies; favor low-debt, low-internal-conflict, low-war-exposure economies (he names India, Indonesia, Vietnam); China is "cheap" but mind the capital-war risk — the question is "how much," not "whether."
- A little Bitcoin OK (≤ a few %), but "there is only one gold."
- The fiscal fix is the "3% solution": cut the deficit from ~6% to ~3% of GDP via ~3% spending cuts + ~3% revenue + ~1pp lower real rates, concurrently. If not done, supply of debt overwhelms demand.
- Don't panic-sell the bubble before it's pricked; reduce the most concentrated/levered froth; build the resilient mix FIRST, speculate second.

=== HOW TO USE THE SPECULAIR DATA ===
You will be given Speculair's live macro regime (9 sub-scores, yield curve 2y/3m, 3m yield level, VIX vs 200d, CPI/GDP/unemployment/sentiment/recession scores) and an index snapshot (SPX/NDX/RUT/VIX). Map these onto the frameworks:
- VIX low + VIX<200d avg + RUT lagging NDX → complacency + narrow breadth → feeds bubble gauge (iv) sentiment and concentration.
- Inverted/flat 2y & 3m curve, high 3m yield level → tightening money = a live PIN (force 1 + pricking).
- CPI score (low=hot inflation), recession_prob, unemployment trend (Sahm) → where in the short-term cycle; inflation re-ignition risk.
- Be explicit when Speculair lacks a field (it has no direct equity-valuation, debt/GDP, or margin-debt feed) — carry Dalio's known structural numbers (US debt ~$37T, deficit ~6% GDP, top-5 ≈30% of S&P, margin debt ~$1.2T) as priors and SAY they are priors, not Speculair-measured.

=== OUTPUT — return ONLY a JSON object, no prose outside it, this exact schema ===
{
  "as_of": "ISO date",
  "regime_readout": "1-2 sentences: Speculair regime + what the live tape says in Dalio terms",
  "big_cycle_stage": {"debt_cycle_stage": "1-6 with label", "internal_order_stage": "1-6", "external_order_stage": "1-6", "reasoning": "string"},
  "bubble_gauge": {"score_0_100": 0, "vs_1929_2000": "string", "which_of_6_gauges_lit": ["..."], "live_pins": ["the specific things that could force selling now"]},
  "five_forces": {"debt_money": "...", "internal_order": "...", "external_order": "...", "nature": "...", "technology_ai": "..."},
  "outlook_2026_2027": {
     "inflation": ["• bullet", "• bullet"],
     "jobs_and_ai": ["• bullet"],
     "stock_market_crash_risk": ["• bullet — include trigger + rough odds/timing"],
     "debt_and_currency": ["• bullet — printing, dollar, real rates"],
     "geopolitics": ["• bullet"]
  },
  "how_dalio_would_act": ["• concrete positioning bullet (gold %, duration, FX, countries, what to trim)"],
  "what_to_watch": ["• the leading indicators/pins to monitor on Speculair"],
  "conviction_0_100": 0,
  "memo": "string — a tight Dalio-voice synthesis tying it together",
  "disclaimer": "Educational macro modeling in the style of Ray Dalio; not personalized investment advice and not affiliated with Mr. Dalio."
}
Reason in real terms. Be specific and probabilistic. Surprises skew to the downside."""


# ── Prompt assembly from live Speculair data ───────────────────────────────
def build_dalio_macro_prompt(regime_data: dict, market_snapshot: dict,
                             as_of: Optional[str] = None) -> str:
    """Render the user prompt from Speculair's macro regime + index snapshot."""
    as_of = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    f = (regime_data or {}).get("features", {}) or {}
    sub = (regime_data or {}).get("sub_scores", {}) or {}
    rates = (regime_data or {}).get("rates", {}) or {}

    def g(d, k, default="n/a"):
        v = d.get(k, default)
        return default if v is None else v

    spx = market_snapshot.get("SPX", {})
    ndx = market_snapshot.get("NDX", {})
    rut = market_snapshot.get("RUT", {})
    vix = market_snapshot.get("VIX", {})

    return f"""=== SPECULAIR LIVE MACRO STATE (as of {as_of}) ===

REGIME: {g(regime_data, 'regime')}  |  composite score: {g(regime_data, 'score')}  (1.0=RISK_ON, 0.0=RISK_OFF)

RATES & CURVE:
  10y-2y spread: {g(f, 'macro_yield_spread_2y')} bp
  10y-3m spread: {g(f, 'macro_yield_spread_3m')} bp  (NY-Fed recession curve)
  3m yield level: {g(f, 'macro_yield_level')}%
  raw rates: {json.dumps(rates) if rates else 'n/a'}

VOLATILITY:
  VIX: {g(f, 'macro_vix')}   VIX / 200d-avg: {g(f, 'macro_vix_vs_avg')}  (>1 = stress vs trend, <1 = complacency)

GROWTH / INFLATION / LABOR (each sub-score 0=bad..1=good):
  CPI trend score: {g(f, 'macro_cpi_score')}   (low score = hot/accelerating inflation)
  GDP momentum score: {g(f, 'macro_gdp_score')}
  Unemployment: {g(f, 'macro_unemployment')}%  (score {g(f, 'macro_unemp_score')}; Sahm-rule sensitive)
  Consumer sentiment: {g(f, 'macro_consumer_sentiment')}  (score {g(f, 'macro_sent_score')})
  Recession probability: {g(f, 'macro_recession_prob')}  (score {g(f, 'macro_recession_score')})

ALL 9 SUB-SCORES: {json.dumps(sub)}

INDEX SNAPSHOT (today):
  SPX {g(spx,'price')} ({g(spx,'change_pct')}%)   NDX {g(ndx,'price')} ({g(ndx,'change_pct')}%)
  RUT {g(rut,'price')} ({g(rut,'change_pct')}%)   VIX {g(vix,'price')} ({g(vix,'change_pct')}%)
  (NDX vs RUT gap = a breadth/concentration tell; RUT lagging = narrow, top-heavy tape)

=== YOUR TASK ===
Run a full Dalio-style macro analysis of this tape. Diagnose the Big Cycle stage, score the bubble gauge,
read the 5 forces, then give the 2026/2027 outlook as bullet points across inflation, jobs/AI, stock-market
crash risk, debt & currency, and geopolitics — and exactly how Dalio would position. Where Speculair lacks a
field, carry Dalio's structural priors and label them as priors. Respond with ONLY the JSON object."""


# ── LLM call (mirrors live_director_agent._query_director) ──────────────────
def _query_dalio(prompt: str, max_attempts: int = 4) -> Optional[dict]:
    api_key = _key("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found")
        return None

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": "claude-opus-4-8",
        "max_tokens": 8000,
        "system": DALIO_MACRO_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": prompt + "\n\nRespond with ONLY the JSON object, "
                                                 "starting with { and ending with }. No prose, no code fences."},
        ],
    }

    for attempt in range(max_attempts):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=payload, timeout=600)
            rj = r.json()
            if rj.get("type") == "error":
                err_msg = rj.get("error", {}).get("message", str(rj))
                if "rate" in err_msg.lower() or "overloaded" in err_msg.lower():
                    sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                    log.warning(f"rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                    time.sleep(sleep)
                    continue
                log.error(f"API error: {err_msg}")
                time.sleep(3.0)
                continue

            text = "".join(b.get("text", "") for b in rj.get("content", [])
                           if b.get("type") == "text").strip()
            if text.startswith("```"):
                blocks = text.split("```")
                text = max(blocks, key=len)
                if text.lstrip().lower().startswith("json"):
                    text = text.lstrip()[4:]
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end + 1]
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            log.error(f"JSON parse error: {e}")
            time.sleep(3.0)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                sleep = 5.0 * (2 ** attempt) + random.uniform(0, 2)
                log.warning(f"rate limited (attempt {attempt+1}), sleeping {sleep:.1f}s")
                time.sleep(sleep)
            else:
                log.error(f"error: {e}")
                time.sleep(3.0)
    return None


# ── Orchestration ──────────────────────────────────────────────────────────
def _live_fmp_func():
    """Return an FMP caller compatible with macro_regime.fetch_macro_regime_v8."""
    fmp_key = _key("FMP_API_KEY")

    def fmp_func(endpoint: str, params: dict):
        url = f"https://financialmodelingprep.com/stable/{endpoint}"
        p = dict(params or {})
        p["apikey"] = fmp_key
        try:
            r = requests.get(url, params=p, timeout=15)
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            log.warning(f"FMP {endpoint} failed: {e}")
            return []

    return fmp_func


def gather_speculair_data() -> tuple[dict, dict]:
    """Pull the live macro regime + index snapshot from Speculair's own modules."""
    try:
        import macro_regime
        import massive_indicators
    except ModuleNotFoundError:
        from backend import macro_regime, massive_indicators  # type: ignore

    regime_data = macro_regime.fetch_macro_regime_v8(_live_fmp_func())
    market_snapshot = massive_indicators.get_index_temperature()
    return regime_data, market_snapshot


def run_dalio_macro_analysis(save: bool = True) -> Optional[dict]:
    log.info("Gathering Speculair live macro data…")
    regime_data, market_snapshot = gather_speculair_data()
    prompt = build_dalio_macro_prompt(regime_data, market_snapshot)
    log.info("Querying Dalio macro strategist (claude-opus-4-8)…")
    result = _query_dalio(prompt)
    if result and save:
        result.setdefault("as_of", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        DALIO_CACHE_FILE.write_text(json.dumps(result, indent=2))
        log.info(f"Saved → {DALIO_CACHE_FILE}")
    return result


if __name__ == "__main__":
    if "--dry" in sys.argv:
        # Print the assembled prompt with live (or mock) data — no LLM call.
        regime_data, market_snapshot = gather_speculair_data()
        print(DALIO_MACRO_SYSTEM_PROMPT)
        print("\n" + "=" * 70 + "\nUSER PROMPT:\n" + "=" * 70)
        print(build_dalio_macro_prompt(regime_data, market_snapshot))
    else:
        out = run_dalio_macro_analysis()
        print(json.dumps(out, indent=2) if out else "No result.")
