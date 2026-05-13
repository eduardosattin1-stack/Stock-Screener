import os
import requests
import logging

log = logging.getLogger(__name__)

MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
MASSIVE_BASE = "https://api.polygon.io"

def get_index_sma(symbol: str, window: int = 200, timespan: str = "day") -> float | None:
    """Fetch SMA for an index (e.g., I:VIX) using Massive Technical Indicators API."""
    if not MASSIVE_API_KEY:
        log.warning("MASSIVE_API_KEY not set - Massive indicators disabled")
        return None
    
    url = f"{MASSIVE_BASE}/v1/indicators/sma/{symbol}"
    params = {
        "timespan": timespan,
        "adjusted": "true",
        "window": window,
        "series_type": "close",
        "order": "desc",
        "limit": 1,
        "apiKey": MASSIVE_API_KEY
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("results") and data["results"].get("values"):
                return float(data["results"]["values"][0]["value"])
    except Exception as e:
        log.warning(f"Massive SMA fetch failed for {symbol}: {e}")
        
    return None

def get_index_price(symbol: str) -> float | None:
    """Fetch the previous day's close price for an index (e.g., I:VIX)."""
    if not MASSIVE_API_KEY:
        return None
        
    url = f"{MASSIVE_BASE}/v2/aggs/ticker/{symbol}/prev"
    params = {
        "adjusted": "true",
        "apiKey": MASSIVE_API_KEY
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("results") and len(data["results"]) > 0:
                return float(data["results"][0].get("c"))
    except Exception as e:
        log.warning(f"Massive Prev Close fetch failed for {symbol}: {e}")
        
    return None
