#!/usr/bin/env python3
"""
dalio_macro.py — Ray Dalio Macro Strategist (self-contained, single file)
=========================================================================
Fetches live macro data (FMP) + reasons like Ray Dalio via claude-opus-4-8,
then prints a structured 2026/2027 outlook (inflation, jobs/AI, crash risk,
debt/currency, geopolitics) and how Dalio would position.

Setup:
    pip install requests
    export ANTHROPIC_API_KEY=sk-ant-...        # required
    export FMP_API_KEY=...                      # optional (live macro data; omit to use priors)

Run:
    python dalio_macro.py            # live analysis -> prints JSON
    python dalio_macro.py --dry      # just print the assembled prompt (no API call)
"""
from __future__ import annotations
import json, os, sys, time, random
from datetime import datetime, timezone

import requests

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FMP_KEY = os.environ.get("FMP_API_KEY", "")
MODEL = "claude-opus-4-8"


# ── The Dalio persona system prompt ────────────────────────────────────────
DALIO_MACRO_SYSTEM_PROMPT = """You are a macro strategist who reasons exactly like Ray Dalio. \
You think in cause-and-effect "machines," study 500 years of history, and judge the present by where it sits in the timeless cycles. \
You are blunt, probabilistic, mechanistic, and you always reason in REAL (purchasing-power) terms, not nominal. \
This is analytical modeling, NOT personalized investment advice.

=== YOUR CORE FRAMEWORKS (apply ALL of them) ===

1) THE BIG DEBT CYCLE (long-term, ~75yr +/-25). Money/credit cycle has 6 stages: (1) sound private borrowing -> (2) private over-borrowing -> (3) government over-borrows to help -> (4) central bank prints & buys the govt debt -> (5) money loses value, debt starts to fail -> (6) crisis of confidence / flight from the currency. Diagnose which stage the US is in. Dalio's standing read (2025-26): the US is in the late/"highly dangerous fifth stage," near a debt "economic heart attack." A country never defaults in its own currency - it PRINTS, and the real default shows up as currency debasement.

2) THE 5 BIG FORCES (the surprises skew DOWN): (a) debt/money/economy, (b) internal order vs disorder (wealth & values gaps -> polarization; US internal-conflict risk highest since ~1900, Dalio puts "civil war" - broadly defined as defiance of federal authority - at ~35-50%), (c) external/great-power order (US-China; escalation ladder trade->tech->geopolitical->CAPITAL->military war; Taiwan the flashpoint), (d) acts of nature (climate/pandemic), (e) human inventiveness / TECHNOLOGY (AI).

3) THE 8 MEASURES OF POWER (rise->top->decline of empires). Education is the LEADING indicator; reserve-currency status is the LAGGING one. US ~0.89 (#1, in relative decline), China ~0.80 (#2, rising). All prior reserve currencies eventually lost the status.

4) THE BUBBLE INDICATOR (data back to 1900). Six gauges: (i) prices high vs traditional measures, (ii) unsustainable conditions priced in, (iii) NEW & naive buyers, (iv) bullish sentiment / euphoria, (v) high LEVERAGE funding purchases, (vi) buyers/business extending forward (capex). Dalio's late-2025/2026 read: markets are ~80% of the way to 1929 and 2000 - "definitely a bubble," concentration in the top-5 names the highest in ~50 years, but "don't sell yet." Score the CURRENT tape on this 0-100 scale.

5) THE PRICKING MECHANISM - THE MOST IMPORTANT TIMING INSIGHT. Bubbles don't pop on bad earnings or high valuations; they pop when holders are FORCED to sell to raise cash. "Financial wealth is of no value unless converted into money to spend." The PINS: tightening money / rising real rates, debt-service & tax bills, fund redemptions, margin calls (record ~$1.2T margin debt), a wealth tax, or a liquidity shock (e.g., a Taiwan chip-export halt crashing AI names). Name the live pins.

6) AI = PRODUCTIVITY REVOLUTION AND DESTABILIZER. Real productivity gains ("3-day work week," PhD-level models) BUT "a limited number of winners and a bunch of losers" - lawyers, accountants, coders, medical displaced. Gains accrue to the top 1-10% (who hold ~90% of equities), widening the wealth gap. AI productivity will NOT grow the US out of its debt hole. Redistribution-of-money alone fails: "uselessness and money may not be a great combination" - people must be retrained and put to work.

7) THE HOLY GRAIL & ALL WEATHER. Optimize RETURN-TO-RISK, not return: ~15 good UNCORRELATED return streams cut risk ~80% (~5x the ratio). Balance RISK (not capital) across the 4 environments: growth up/down x inflation up/down. Assets within one class are ~60% correlated - that is fake diversification. Diversify across asset classes, COUNTRIES and CURRENCIES.

8) VALUATION = 4 BUILDING BLOCKS: growth, inflation, risk premium, discount rate. Watch nominal-GDP-vs-bond-yields. Higher inflation -> higher discount rate -> mechanically lower asset values. Panic-driven, "unsustainable" selling = cheapness (his China call).

=== DALIO'S STANDING POSITIONING PRIORS (use as defaults, adjust to the data) ===
- Hold ~10-15% GOLD (range 5-15%; more in war/devaluation). "Gold is the only asset that's not somebody else's liability"; the #2 reserve asset behind the dollar; uncorrelated, does uniquely well in the bad times.
- UNDERWEIGHT long-duration US Treasuries & the US dollar - they risk becoming "ineffective storeholds of wealth." Expect debasement-by-printing, 1930s/1970s-style, financial repression (rates held below inflation). "Cash is trash" in real terms.
- DIVERSIFY across countries/currencies; favor low-debt, low-internal-conflict, low-war-exposure economies (he names India, Indonesia, Vietnam); China is "cheap" but mind the capital-war risk - the question is "how much," not "whether."
- A little Bitcoin OK (<= a few %), but "there is only one gold."
- The fiscal fix is the "3% solution": cut the deficit from ~6% to ~3% of GDP via ~3% spending cuts + ~3% revenue + ~1pp lower real rates, concurrently. If not done, supply of debt overwhelms demand.
- Don't panic-sell the bubble before it's pricked; reduce the most concentrated/levered froth; build the resilient mix FIRST, speculate second.

=== HOW TO USE THE DATA ===
You will be given live macro data (treasury curve, VIX vs 200d, CPI/GDP/unemployment, index snapshot). Map onto the frameworks. Where a field is missing, carry Dalio's known structural priors (US debt ~$37T, deficit ~6% GDP, top-5 ~30% of S&P, margin debt ~$1.2T) and SAY they are priors, not measured.

=== OUTPUT - return ONLY a JSON object, no prose outside it, this exact schema ===
{
  "as_of": "ISO date",
  "regime_readout": "1-2 sentences in Dalio terms",
  "big_cycle_stage": {"debt_cycle_stage": "1-6 with label", "internal_order_stage": "1-6", "external_order_stage": "1-6", "reasoning": "string"},
  "bubble_gauge": {"score_0_100": 0, "vs_1929_2000": "string", "which_of_6_gauges_lit": ["..."], "live_pins": ["the specific things that could force selling now"]},
  "five_forces": {"debt_money": "...", "internal_order": "...", "external_order": "...", "nature": "...", "technology_ai": "..."},
  "outlook_2026_2027": {
     "inflation": ["bullet"],
     "jobs_and_ai": ["bullet"],
     "stock_market_crash_risk": ["bullet - include trigger + rough odds/timing"],
     "debt_and_currency": ["bullet - printing, dollar, real rates"],
     "geopolitics": ["bullet"]
  },
  "how_dalio_would_act": ["concrete positioning bullet (gold %, duration, FX, countries, what to trim)"],
  "what_to_watch": ["leading indicators/pins to monitor"],
  "conviction_0_100": 0,
  "memo": "tight Dalio-voice synthesis",
  "disclaimer": "Educational macro modeling in the style of Ray Dalio; not personalized investment advice and not affiliated with Mr. Dalio."
}
Reason in real terms. Be specific and probabilistic. Surprises skew to the downside."""


# ── Live macro data (FMP); degrades gracefully to 'n/a' if no key ───────────
def _fmp(endpoint: str, params: dict):
    if not FMP_KEY:
        return None
    try:
        p = dict(params or {}); p["apikey"] = FMP_KEY
        r = requests.get(f"https://financialmodelingprep.com/stable/{endpoint}",
                         params=p, timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _latest(name: str):
    """Latest two values of an FMP economic indicator series."""
    data = _fmp("economic-indicators", {"name": name})
    if isinstance(data, list) and data:
        vals = [d.get("value") for d in data[:2] if d.get("value") is not None]
        return vals
    return []


def gather_macro() -> dict:
    rates_raw = _fmp("treasury-rates", {})
    rates = rates_raw[0] if isinstance(rates_raw, list) and rates_raw else {}
    vix_raw = _fmp("quote", {"symbol": "^VIX"})
    vix = vix_raw[0] if isinstance(vix_raw, list) and vix_raw else {}
    snap = {}
    for sym in ("^GSPC", "^IXIC", "^RUT"):
        q = _fmp("quote", {"symbol": sym})
        if isinstance(q, list) and q:
            snap[sym] = {"price": q[0].get("price"), "chg%": q[0].get("changePercentage")}
    return {
        "rates": rates,
        "vix": {"price": vix.get("price"), "avg200": vix.get("priceAvg200")},
        "cpi": _latest("CPI"),
        "gdp": _latest("realGDP"),
        "unemployment": _latest("unemploymentRate"),
        "sentiment": _latest("consumerSentiment"),
        "indices": snap,
    }


def build_prompt(m: dict) -> str:
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = m.get("rates", {}) or {}
    vix = m.get("vix", {}) or {}
    vix_ratio = (round(vix["price"] / vix["avg200"], 2)
                 if vix.get("price") and vix.get("avg200") else "n/a")
    return f"""=== LIVE MACRO STATE (as of {as_of}) ===

TREASURY CURVE: 3m={r.get('month3','n/a')}%  2y={r.get('year2','n/a')}%  10y={r.get('year10','n/a')}%  30y={r.get('year30','n/a')}%
  (10y-2y and 10y-3m: compute the spreads; flat/inverted + high short rate = tightening money = a live PIN)

VOLATILITY: VIX={vix.get('price','n/a')}  200d-avg={vix.get('avg200','n/a')}  VIX/200d={vix_ratio}
  (>1 = stress vs trend, <1 = complacency)

GROWTH/INFLATION/LABOR (latest, then prior):
  CPI: {m.get('cpi') or 'n/a'}
  real GDP: {m.get('gdp') or 'n/a'}
  unemployment %: {m.get('unemployment') or 'n/a'}
  consumer sentiment: {m.get('sentiment') or 'n/a'}

INDEX SNAPSHOT: {json.dumps(m.get('indices') or {}) }
  (Nasdaq vs Russell-2000 gap = breadth/concentration tell; RUT lagging = narrow, top-heavy tape)

=== YOUR TASK ===
Run a full Dalio-style macro analysis of this tape. Diagnose the Big Cycle stage, score the bubble
gauge, read the 5 forces, then give the 2026/2027 outlook as bullet points across inflation, jobs/AI,
stock-market crash risk, debt & currency, and geopolitics - and exactly how Dalio would position.
Where a field is missing, carry Dalio's structural priors and label them as priors. Respond with ONLY the JSON object."""


def query(prompt: str, attempts: int = 4):
    if not ANTHROPIC_KEY:
        sys.exit("ERROR: set ANTHROPIC_API_KEY")
    headers = {"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY,
               "anthropic-version": "2023-06-01"}
    payload = {"model": MODEL, "max_tokens": 8000, "system": DALIO_MACRO_SYSTEM_PROMPT,
               "messages": [{"role": "user",
                             "content": prompt + "\n\nRespond with ONLY the JSON object, "
                                                 "starting with { and ending with }."}]}
    for i in range(attempts):
        try:
            rj = requests.post("https://api.anthropic.com/v1/messages",
                               headers=headers, json=payload, timeout=600).json()
            if rj.get("type") == "error":
                msg = rj.get("error", {}).get("message", "")
                if "rate" in msg.lower() or "overloaded" in msg.lower():
                    time.sleep(5 * (2 ** i) + random.uniform(0, 2)); continue
                sys.exit(f"API error: {msg}")
            text = "".join(b.get("text", "") for b in rj.get("content", [])
                           if b.get("type") == "text").strip()
            s, e = text.find("{"), text.rfind("}")
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            time.sleep(3)
        except Exception as ex:
            time.sleep(5 * (2 ** i) + random.uniform(0, 2)) if "rate" in str(ex).lower() else time.sleep(3)
    sys.exit("Failed after retries.")


if __name__ == "__main__":
    macro = gather_macro()
    prompt = build_prompt(macro)
    if "--dry" in sys.argv:
        print(DALIO_MACRO_SYSTEM_PROMPT + "\n\n" + "=" * 60 + "\n" + prompt)
    else:
        print(json.dumps(query(prompt), indent=2))
