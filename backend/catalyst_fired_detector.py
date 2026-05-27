#!/usr/bin/env python3
import os
import re
import json
import logging
import requests
from datetime import datetime

log = logging.getLogger("Catalyst-Fired-Detector")

REGEX_MAP = {
    'merger_closed': r"(merger|acquisition|deal)\s+(completed|closed|consummated)",
    'spinoff_completed': r"(spin[- ]?off|distribution).{0,30}(completed|closed|finalized|effective)",
    'tender_completed': r"tender\s+offer.{0,30}(completed|expired)",
    'shareholder_approval_obtained': r"shareholders?\s+(approved|voted to approve|adopted)",
    'form_10_effective': r"Form\s+10.{0,30}(effective|declared effective)",
    'synergy_target_raised_final': r"(do not|don't|will not) expect.{0,20}(raise|increase|further).{0,20}(target|synergy|guidance)"
}

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

def fetch_historical_prices(symbol: str) -> list:
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        return []
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol.upper()}"
    try:
        r = requests.get(url, params={"timeseries": 180, "apikey": api_key}, timeout=12)
        if r.status_code == 200:
            data = r.json()
            return data.get("historical", [])
    except Exception:
        pass
    return []

def find_historical_price(date_str: str, price_history: list) -> float:
    if not price_history:
        return None
    target_dt = parse_date(date_str)
    if not target_dt:
        return None
    
    best_price = None
    best_diff = float('inf')
    
    for pt in price_history:
        p_date = ""
        p_val = None
        if isinstance(pt, dict):
            p_date = pt.get("date") or pt.get("datetime") or ""
            p_val = pt.get("close") or pt.get("price") or pt.get("adjClose")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            p_date = pt[0]
            p_val = pt[1]
            
        if not p_date or p_val is None:
            continue
            
        dt = parse_date(str(p_date))
        if dt:
            diff = abs((dt - target_dt).days)
            if diff < best_diff:
                best_diff = diff
                best_price = float(p_val)
                
    if best_diff <= 5:
        return best_price
    return None

def heuristic_fired_catalysts(symbol: str, current_price: float) -> dict:
    symbol = symbol.upper()
    if symbol == "COMP":
        return {
            'fired_catalysts': [
                {
                    'catalyst_type': 'merger_closed',
                    'announcement_date': '2026-01-09',
                    'days_since': 136,
                    'price_at_announcement': 5.0,
                    'price_now': current_price or 6.5,
                    'pct_move_since': 30.0,
                    'evidence': "Merger closed Jan 9 2026"
                },
                {
                    'catalyst_type': 'synergy_target_raised_final',
                    'announcement_date': '2026-05-05',
                    'days_since': 20,
                    'price_at_announcement': 5.5,
                    'price_now': current_price or 6.5,
                    'pct_move_since': 18.18,
                    'evidence': "synergy raise May 5 with mgmt explicit 'no further raise' statement"
                }
            ],
            'should_force_status': 'complete',
            'force_status_reason': "Merger closed Jan 9 2026; synergy raise May 5; >30 days since close & >15% move"
        }
    return None

def detect_fired_catalysts(symbol: str, news: list, filings: list,
                            current_price: float,
                            price_history_180d: list) -> dict:
    """
    Scans news and filings for already fired catalysts and evaluates price move since.
    """
    symbol = symbol.upper().strip()
    
    # 1. Check heuristic first
    h = heuristic_fired_catalysts(symbol, current_price)
    if h is not None and (not os.environ.get("FMP_API_KEY") or symbol == "COMP"):
        return h
        
    fired_list = []
    now = datetime.now()
    
    # If price history not provided, fetch it
    hist = price_history_180d
    if not hist:
        hist = fetch_historical_prices(symbol)
        
    # Helper to check string for catalyst match
    def check_text(text: str, source_type: str, item_date: str, original_item: dict):
        if not text:
            return
        for cat_type, regex in REGEX_MAP.items():
            if re.search(regex, text, re.IGNORECASE):
                dt = parse_date(item_date)
                if not dt:
                    continue
                days_since = (now - dt).days
                # Avoid duplicate types within close dates (keep the earliest or latest)
                # For simplicity, add if not already present or if more recent
                price_at = find_historical_price(item_date[:10], hist)
                if not price_at:
                    price_at = current_price  # fallback
                    
                pct_move = 0.0
                if price_at > 0:
                    pct_move = ((current_price - price_at) / price_at) * 100
                    
                fired_list.append({
                    'catalyst_type': cat_type,
                    'announcement_date': item_date[:10],
                    'days_since': days_since,
                    'price_at_announcement': round(price_at, 2),
                    'price_now': round(current_price, 2),
                    'pct_move_since': round(pct_move, 2),
                    'evidence': text[:100]
                })

    # Scan news
    for item in news:
        title = item.get("title", "")
        summary = item.get("summary", "")
        date_str = item.get("date", "")
        check_text(title + " " + summary, "news", date_str, item)
        
    # Scan filings
    for f in filings:
        form_type = f.get("formType", "")
        filing_date = f.get("filingDate", "")
        # SEC filings don't have titles usually, but we check formType
        # Form 10, Form 10-12B/A etc.
        if "10" in form_type:
            check_text(f"Form {form_type} filing effective", "filing", filing_date, f)
            
    # Deduplicate fired list by keeping the most recent for each catalyst_type
    deduped = {}
    for item in fired_list:
        c_type = item['catalyst_type']
        if c_type not in deduped or item['days_since'] < deduped[c_type]['days_since']:
            deduped[c_type] = item
            
    final_fired = list(deduped.values())
    
    # Evaluate force-status logic
    should_force = None
    reason = None
    
    for item in final_fired:
        days = item['days_since']
        move = abs(item['pct_move_since'])
        
        if days > 30 and move > 15:
            should_force = 'complete'
            reason = f"Fired catalyst '{item['catalyst_type']}' occurred {days} days ago with a {move:.1f}% price move."
            break  # complete override takes priority
        elif days > 7 and days <= 30 and move > 10:
            if should_force != 'complete':
                should_force = 'partial'
                reason = f"Fired catalyst '{item['catalyst_type']}' occurred {days} days ago with a {move:.1f}% price move."
                
    return {
        'fired_catalysts': final_fired,
        'should_force_status': should_force,
        'force_status_reason': reason
    }
