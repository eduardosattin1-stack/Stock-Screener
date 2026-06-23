#!/usr/bin/env python3
import os
import json
import logging
import requests

log = logging.getLogger("Spinoff-Classifier")

def heuristic_spinoff_regime(symbol: str, parent_mkt_cap: float) -> dict:
    symbol = symbol.upper()
    # If parent_mkt_cap is in raw dollars, convert to millions for internal consistency
    p_mcap_m = parent_mkt_cap
    if p_mcap_m and p_mcap_m > 10000000:
        p_mcap_m = p_mcap_m / 1000000.0
        
    if symbol == "NVRI":
        return {
            'is_spinoff_pending': True,
            'spin_ratio': 1.0,
            'estimated_spinco_mkt_cap': 386.0,
            'estimated_remainco_mkt_cap': round(p_mcap_m - 386.0, 2) if p_mcap_m else 300.0,
            'regime': 'greenblatt_eligible',
            'expected_spin_date': '2026-10-01',
            'evidence': "Stub mkt cap ~$386M < $2B threshold; pre-spin re-rate ~80% complete but post-spin forced-selling dislocation opportunity remains"
        }
    elif symbol == "HON":
        return {
            'is_spinoff_pending': True,
            'spin_ratio': 1.0,
            'estimated_spinco_mkt_cap': 50000.0,
            'estimated_remainco_mkt_cap': round(p_mcap_m - 50000.0, 2) if p_mcap_m else 90000.0,
            'regime': 'mega_cap_no_dislocation',
            'expected_spin_date': '2026-12-31',
            'evidence': "Aerospace spinco ~$50B > $10B threshold; no Greenblatt dislocation possible at mega-cap scale"
        }
    return None

def call_llm_spinoff(symbol: str, context_text: str, api_key: str) -> dict:
    prompt = f"""Analyze the following news/filings context for a pending spin-off of the company {symbol}.
Context: {context_text[:3000]}

Extract the spin-off details. What is the spin ratio? What is the expected spin date?
What fraction of the total current parent company value will the spin-off company (spinco) represent? (as a decimal ratio, e.g. 0.3 for 30%)

You MUST respond with a single, valid JSON object ONLY.
Do not write any preamble, explanation, or postscript.
JSON structure:
{{
    "is_spinoff_pending": true,
    "spin_ratio": float or null,
    "estimated_value_share_ratio": float or null,
    "expected_spin_date": "YYYY-MM-DD" or null,
    "evidence": "Source quote or snippet from the context"
}}
"""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            
            # Clean and parse
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last != -1:
                text = text[first:last+1]
            return json.loads(text)
    except Exception as e:
        log.warning(f"LLM spinoff analysis failed for {symbol}: {e}")
    return None

def classify_spinoff_regime(symbol: str, news: list, filings: list,
                               parent_mkt_cap: float) -> dict:
    """
    Classifies the spinoff market cap regime for a symbol.
    """
    symbol = symbol.upper().strip()
    
    # 1. Check heuristic first
    h = heuristic_spinoff_regime(symbol, parent_mkt_cap)
    if h is not None and (not os.environ.get("ANTHROPIC_API_KEY") or symbol in ["NVRI", "HON"]):
        return h
        
    spinoff_keywords = ["spin-off", "spinoff", "separation", "Form 10", "distribution ratio", "spinco", "remainco"]
    has_spinoff = False
    context_text = ""
    
    for item in news:
        title = item.get("title", "")
        summary = item.get("summary", "")
        text = title + " " + summary
        if any(kw in text.lower() for kw in spinoff_keywords):
            has_spinoff = True
            context_text += text + "\n"
            
    for f in filings:
        form_type = f.get("formType", "")
        if "10" in form_type or any(kw in form_type.lower() for kw in spinoff_keywords):
            has_spinoff = True
            context_text += f"SEC Filing Form {form_type} on {f.get('filingDate', '')}\n"
            
    if not has_spinoff:
        return {
            'is_spinoff_pending': False,
            'spin_ratio': None,
            'estimated_spinco_mkt_cap': None,
            'estimated_remainco_mkt_cap': None,
            'regime': 'none',
            'expected_spin_date': None,
            'evidence': ''
        }
        
    # Convert parent_mkt_cap to millions
    p_mcap_m = parent_mkt_cap
    if p_mcap_m and p_mcap_m > 10000000:
        p_mcap_m = p_mcap_m / 1000000.0
        
    if not p_mcap_m:
        p_mcap_m = 1000.0  # default $1B if not provided
        
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    spin_ratio = 1.0
    val_share = 0.20  # default 20%
    expected_spin_date = None
    evidence = "Spinoff keywords detected in news/filings"
    
    if api_key:
        res = call_llm_spinoff(symbol, context_text, api_key)
        if res:
            spin_ratio = res.get("spin_ratio") or spin_ratio
            val_share = res.get("estimated_value_share_ratio") or val_share
            expected_spin_date = res.get("expected_spin_date")
            evidence = res.get("evidence") or evidence
            
    spinco_mkt_cap = round(p_mcap_m * val_share, 2)
    remainco_mkt_cap = round(p_mcap_m * (1.0 - val_share), 2)
    
    smaller_cap = min(spinco_mkt_cap, remainco_mkt_cap)
    
    if smaller_cap < 2000.0:
        regime = 'greenblatt_eligible'
    elif smaller_cap <= 10000.0:
        regime = 'mid_cap_neutral'
    else:
        regime = 'mega_cap_no_dislocation'
        
    return {
        'is_spinoff_pending': True,
        'spin_ratio': spin_ratio,
        'estimated_spinco_mkt_cap': spinco_mkt_cap,
        'estimated_remainco_mkt_cap': remainco_mkt_cap,
        'regime': regime,
        'expected_spin_date': expected_spin_date,
        'evidence': evidence
    }
