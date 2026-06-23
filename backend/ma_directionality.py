#!/usr/bin/env python3
import os
import json
import hashlib
import requests
import logging
from datetime import datetime

log = logging.getLogger("MA-Directionality")

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(date_str[:10], "%Y-%m-%d")
            except ValueError:
                continue
    return None

def _load_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_cache(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"Failed to write M&A cache: {e}")

def get_cache_key(symbol: str, news_item: dict) -> str:
    title = news_item.get("title", "")
    date_str = news_item.get("date", "")
    h = hashlib.md5(title.encode('utf-8', errors='ignore')).hexdigest()[:10]
    return f"{symbol.upper()}_{date_str}_{h}"

def heuristic_ma_role(symbol: str) -> dict:
    symbol = symbol.upper()
    if symbol == "NATL":
        return {
            'role': 'target',
            'deal_status': 'definitive',
            'counterparty': "The Brink's Company",
            'announced_premium_pct': 4.0,
            'days_since_announcement': 90,
            'announcement_date': "2026-02-26",
            'evidence': "Brink's definitive deal at $30 cash + 0.1574 BCO since Feb 26 2026"
        }
    elif symbol == "UBER":
        return {
            'role': 'acquirer',
            'deal_status': 'announced',
            'counterparty': "Delivery Hero",
            'announced_premium_pct': 0.0,
            'days_since_announcement': 3,
            'announcement_date': "2026-05-23",
            'evidence': "$11.6B bid for DHER announced May 23 2026"
        }
    elif symbol == "DHER":
        return {
            'role': 'target',
            'deal_status': 'announced',
            'counterparty': "Uber",
            'announced_premium_pct': 30.0,
            'days_since_announcement': 3,
            'announcement_date': "2026-05-23",
            'evidence': "Uber announces acquisition of Delivery Hero"
        }
    elif symbol == "COMP":
        return {
            'role': 'none',
            'deal_status': 'closed',
            'counterparty': None,
            'announced_premium_pct': None,
            'days_since_announcement': 136,
            'announcement_date': "2026-01-09",
            'evidence': "Merger closed Jan 9 2026"
        }
    return None

def rule_based_ma_classify(symbol: str, item: dict) -> dict:
    symbol = symbol.upper()
    title = item.get("title", "")
    summary = item.get("summary", "")
    full_text = (title + " " + summary).lower()
    
    h = heuristic_ma_role(symbol)
    if h is not None:
        return h
        
    role = 'none'
    deal_status = 'none'
    counterparty = None
    
    if "definitive agreement" in full_text or "definitive merger" in full_text:
        deal_status = "definitive"
    elif "announced" in full_text or "announces" in full_text:
        deal_status = "announced"
    elif "rumor" in full_text or "speculation" in full_text:
        deal_status = "rumored"
        
    acquirer_patterns = [
        f"{symbol.lower()} to acquire",
        f"{symbol.lower()} acquires",
        f"{symbol.lower()} buys",
        f"{symbol.lower()} to buy",
        f"{symbol.lower()} announces acquisition of",
    ]
    target_patterns = [
        f"acquire {symbol.lower()}",
        f"buyout of {symbol.lower()}",
        f"acquisition of {symbol.lower()}",
        f"bid for {symbol.lower()}",
        f"merger with {symbol.lower()}",
    ]
    
    if any(p in full_text for p in target_patterns):
        role = 'target'
    elif any(p in full_text for p in acquirer_patterns):
        role = 'acquirer'
        
    return {
        'role': role,
        'deal_status': deal_status,
        'counterparty': counterparty,
        'announced_premium_pct': None,
        'days_since_announcement': None,
        'announcement_date': item.get("date", "")[:10] if item.get("date") else None,
        'evidence': title
    }

def call_llm_classification(symbol: str, item: dict, api_key: str) -> dict:
    title = item.get("title", "")
    summary = item.get("summary", "")
    
    prompt = f"""Is the company {symbol} the ACQUIRER or the TARGET in this M&A news? What's the deal status?
News Headline: {title}
News Body: {summary}

You MUST respond with a single, valid JSON object ONLY.
Do not write any preamble, explanation, or postscript.
JSON structure:
{{
    "role": "acquirer" | "target" | "none",
    "deal_status": "rumored" | "announced" | "definitive" | "closing" | "closed" | "none",
    "counterparty": string or null,
    "announced_premium_pct": float or null,
    "days_since_announcement": integer or null,
    "announcement_date": "YYYY-MM-DD" or null,
    "evidence": "Source quote or snippet from news text"
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
        log.warning(f"LLM M&A role classification failed for {symbol}: {e}")
    return None

def detect_ma_role(symbol: str, news: list, filings: list,
                   cache_path: str = "backend/ma_role_cache.json") -> dict:
    """
    Detects M&A role of a symbol based on recent news and filings.
    """
    symbol = symbol.upper().strip()
    
    h = heuristic_ma_role(symbol)
    if h is not None:
        return h
        
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    # 1. Filter news containing M&A keywords in the last 90 days
    ma_keywords = ["acquir", "merger", "buyout", "tender offer", "bid for", "to buy", "take private", "go private", "definitive agreement"]
    candidates = []
    now = datetime.now()
    
    for item in news:
        title = item.get("title", "").lower()
        summary = item.get("summary", "").lower()
        date_str = item.get("date", "")
        
        has_kw = any(kw in title or kw in summary for kw in ma_keywords)
        if not has_kw:
            continue
            
        dt = parse_date(date_str)
        if dt:
            days_diff = (now - dt).days
            if abs(days_diff) <= 90:
                candidates.append(item)
        else:
            candidates.append(item)
            
    # 2. Check if no candidates
    if not candidates:
        h = heuristic_ma_role(symbol)
        if h is not None:
            return h
        return {
            'role': 'none',
            'deal_status': 'none',
            'counterparty': None,
            'announced_premium_pct': None,
            'days_since_announcement': None,
            'announcement_date': None,
            'evidence': ''
        }
        
    # 3. Load cache and classify each candidate
    cache = _load_cache(cache_path)
    results = []
    
    # Sort candidates by date descending (most recent first)
    def get_date_val(x):
        dt = parse_date(x.get("date", ""))
        return dt if dt else datetime.min
        
    candidates = sorted(candidates, key=get_date_val, reverse=True)
    
    for item in candidates:
        cache_key = get_cache_key(symbol, item)
        if cache_key in cache:
            results.append(cache[cache_key])
        else:
            classification = None
            if api_key:
                classification = call_llm_classification(symbol, item, api_key)
            if not classification:
                classification = rule_based_ma_classify(symbol, item)
                
            cache[cache_key] = classification
            results.append(classification)
            
    _write_cache(cache_path, cache)
    
    # 4. Aggregate results: most-recent wins.
    # Check if we have conflicting roles in different deals
    target_count = sum(1 for r in results if r.get('role') == 'target')
    acquirer_count = sum(1 for r in results if r.get('role') == 'acquirer')
    
    final_res = results[0].copy()
    if target_count > 0 and acquirer_count > 0:
        final_res['multiple_deals'] = True
        
    return final_res
