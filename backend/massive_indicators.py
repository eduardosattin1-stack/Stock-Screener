import os
import requests
import logging

log = logging.getLogger(__name__)

MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "").strip()
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

def get_index_temperature() -> dict:
    """
    Fetch a snapshot of major indices for the UI thermometer.
    Returns a dict like:
    {
      "SPX": {"price": 5240.2, "change_pct": 0.5, "change": 26.2},
      "NDX": {"price": 18230.1, "change_pct": 0.8, "change": 145.8},
      "RUT": {"price": 2040.5, "change_pct": -0.2, "change": -4.1},
      "VIX": {"price": 13.5, "change_pct": -2.1, "change": -0.3}
    }
    """
    if not MASSIVE_API_KEY:
        # Return mock data for local testing when key is not present
        return {
            "SPX": {"price": 5267.84, "change_pct": 0.35, "change": 18.2},
            "NDX": {"price": 18452.10, "change_pct": 0.62, "change": 114.5},
            "RUT": {"price": 2084.21, "change_pct": -0.15, "change": -3.2},
            "VIX": {"price": 13.45, "change_pct": -4.2, "change": -0.5}
        }
        
    url = f"{MASSIVE_BASE}/v3/snapshot/indices"
    params = {
        "ticker.any_of": "I:SPX,I:NDX,I:RUT,I:VIX",
        "apiKey": MASSIVE_API_KEY
    }
    
    result = {}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            for res in results:
                ticker = res.get("ticker", "").replace("I:", "")
                val = res.get("value", 0)
                # Todays change:
                session = res.get("session", {})
                change = session.get("change", 0)
                change_pct = session.get("change_percent", 0)
                result[ticker] = {
                    "price": val,
                    "change": change,
                    "change_pct": change_pct
                }
            return result
    except Exception as e:
        log.warning(f"Massive snapshot fetch failed: {e}")
        
    # Return mock data if fetch fails
    return {
        "SPX": {"price": 5267.84, "change_pct": 0.35, "change": 18.2},
        "NDX": {"price": 18452.10, "change_pct": 0.62, "change": 114.5},
        "RUT": {"price": 2084.21, "change_pct": -0.15, "change": -3.2},
        "VIX": {"price": 13.45, "change_pct": -4.2, "change": -0.5}
    }

