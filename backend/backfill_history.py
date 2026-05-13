import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from google.cloud import storage
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BUCKET_NAME = "screener-signals-carbonbridge"
FMP_KEY = os.environ.get("FMP_API_KEY", "")

def get_gcs_json(bucket, prefix, symbol):
    blob = bucket.blob(f"{prefix}/{symbol}.json")
    if blob.exists():
        try:
            return json.loads(blob.download_as_string())
        except:
            return None
    return None

def get_historical_prices(bucket, symbol):
    cache_path = f"cache/historical-price-full_{symbol}.json"
    blob = bucket.blob(cache_path)
    if blob.exists():
        try:
            cached_data = json.loads(blob.download_as_string())
            if isinstance(cached_data, dict) and "historical" in cached_data:
                return cached_data["historical"]
            return cached_data
        except:
            pass
            
    if not FMP_KEY:
        log.error("FMP_API_KEY environment variable is required to fetch missing price history.")
        return []

    log.info(f"[{symbol}] Fetching daily price history from FMP API...")
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?apikey={FMP_KEY}"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, dict) and "historical" in data:
            hist = data["historical"]
            if hist:
                blob.upload_from_string(json.dumps(hist))
                return hist
        elif isinstance(data, list) and data:
            blob.upload_from_string(json.dumps(data))
            return data
    return []

def safe_float(val):
    try:
        return float(val or 0)
    except:
        return 0.0

def rsi_calc(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(period):
        diff = closes[i] - closes[i+1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_loss = sum(losses)/period
    if avg_loss == 0: return 100.0
    rs = (sum(gains)/period) / avg_loss
    return 100 - (100 / (1 + rs))

def backfill_symbol(symbol: str, weeks: int = 52, force: bool = False):
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
    except Exception as e:
        log.error(f"Failed to auth with GCS. Are you in Cloud Shell? Error: {e}")
        return

    # 1. Fetch Fundamentals from your fast GCS Cache
    log.info(f"[{symbol}] Loading fundamentals from fmp_cache...")
    inc_cached = get_gcs_json(bucket, "fmp_cache/income-statement", symbol)
    bal_cached = get_gcs_json(bucket, "fmp_cache/balance-sheet-statement", symbol)
    km_cached = get_gcs_json(bucket, "fmp_cache/key-metrics", symbol)
    
    if not inc_cached: log.warning(f"[{symbol}] inc_cached is missing or empty")
    if not bal_cached: log.warning(f"[{symbol}] bal_cached is missing or empty")
    if not km_cached: log.warning(f"[{symbol}] km_cached is missing or empty")

    inc = inc_cached.get("payload", []) if isinstance(inc_cached, dict) else []
    bal = bal_cached.get("payload", []) if isinstance(bal_cached, dict) else []
    km = km_cached.get("payload", []) if isinstance(km_cached, dict) else []
    
    for ls in (inc, bal, km):
        for r in ls:
            if not r.get("filingDate") and r.get("date"):
                r["filingDate"] = r["date"]
    
    inc = sorted([r for r in inc if r.get("filingDate")], key=lambda x: x["filingDate"])
    bal = sorted([r for r in bal if r.get("filingDate")], key=lambda x: x["filingDate"])
    km = sorted([r for r in km if r.get("filingDate")], key=lambda x: x["filingDate"])
    
    # 2. Fetch Prices
    prices = get_historical_prices(bucket, symbol)
    if not prices:
        log.warning(f"[{symbol}] No price history found.")
        return
        
    prices = sorted(prices, key=lambda x: x["date"], reverse=True) # Newest first at index 0
    
    # 3. Step back in time
    history_out = []
    today = datetime.now()
    
    for w in range(weeks):
        target_date = today - timedelta(weeks=w)
        target_str = target_date.strftime("%Y-%m-%d")
        
        valid_prices = [p for p in prices if p["date"] <= target_str]
        if len(valid_prices) < 200:
            if w == 0: log.warning(f"[{symbol}] Skipped {target_str}: Only {len(valid_prices)} prices available (need 200)")
            continue
            
        current_price = valid_prices[0]["close"]
        closes = [p["close"] for p in valid_prices]
        
        sma_50 = sum(closes[:50]) / 50
        sma_200 = sum(closes[:200]) / 200
        curr_rsi = rsi_calc(closes, 14)
        
        # Point-in-time fundamentals (only what was published BEFORE this week)
        inc_pit = [r for r in inc if r["filingDate"] < target_str]
        km_pit = [r for r in km if r["filingDate"] < target_str]
        
        if len(inc_pit) < 4 or len(km_pit) < 4:
            if w == 0: log.warning(f"[{symbol}] Skipped {target_str}: Need 4 statements, found {len(inc_pit)} inc, {len(km_pit)} km")
            continue
            
        # Core v8 calculations
        latest_inc = inc_pit[-1]
        older_inc = inc_pit[-4]
        
        # Growth
        rev_cagr = (latest_inc.get("revenue", 0) / older_inc.get("revenue", 1)) - 1 if older_inc.get("revenue", 1) > 0 else 0
        eps_cagr = (latest_inc.get("eps", 0) / older_inc.get("eps", 1)) - 1 if older_inc.get("eps", 1) > 0 else 0
        
        # Quality
        roe = safe_float(km_pit[-1].get("returnOnEquity"))
        gross_margin = latest_inc.get("grossProfit", 0) / latest_inc.get("revenue", 1) if latest_inc.get("revenue", 1) > 0 else 0
        net_margin = latest_inc.get("netIncome", 0) / latest_inc.get("revenue", 1) if latest_inc.get("revenue", 1) > 0 else 0
        
        # Value (inversely correlated with price, breaks the perfect positive correlation)
        shares = latest_inc.get("weightedAverageShsOutDil") or latest_inc.get("weightedAverageShsOut") or 1
        eps = latest_inc.get("epsDiluted") or 0
        rev_ps = latest_inc.get("revenue", 0) / shares
        
        pe = current_price / eps if eps > 0 else 999
        ps = current_price / rev_ps if rev_ps > 0 else 999
        earnings_yield = eps / current_price if current_price > 0 else 0
        
        # Momentum
        tech_score = 0.5
        if current_price > sma_50: tech_score += 0.1
        if current_price > sma_200: tech_score += 0.1
        if sma_50 > sma_200: tech_score += 0.1
        if curr_rsi < 30: tech_score -= 0.1
        elif curr_rsi > 70: tech_score += 0.1
        
        # v8 sub-scores (0 to 1)
        val_score = 0.0
        if pe < 15: val_score += 0.4
        elif pe < 25: val_score += 0.2
        if ps < 2: val_score += 0.3
        elif ps < 5: val_score += 0.1
        if earnings_yield > 0.05: val_score += 0.3
        
        growth_score = 0.0
        if rev_cagr > 0.1: growth_score += 0.5
        if eps_cagr > 0.1: growth_score += 0.5
        
        qual_score = 0.0
        if roe > 0.15: qual_score += 0.4
        if gross_margin > 0.4: qual_score += 0.3
        if net_margin > 0.1: qual_score += 0.3
        
        # We don't have Smart Money historically, so we distribute its weight (17%) 
        # v8 weights: value=33%, growth=17%, qual=17%, tech=17%, smart_money=17%
        # Sum of what we have is 84%. Multiply by 1/0.84 = 1.19
        composite = (val_score * 0.33 + growth_score * 0.17 + qual_score * 0.17 + tech_score * 0.17) * 1.19
        composite = min(max(composite, 0.0), 1.0)
        
        # --- FALLEN ANGEL ---
        # FA focuses on deep value and oversold technicals (reversal)
        fa_tech_score = 0.5
        if curr_rsi < 35: fa_tech_score += 0.3
        elif curr_rsi < 45: fa_tech_score += 0.1
        elif curr_rsi > 60: fa_tech_score -= 0.1
        elif curr_rsi > 70: fa_tech_score -= 0.3
        
        if current_price < sma_50: fa_tech_score += 0.1
        if current_price < sma_200: fa_tech_score += 0.2
        else: fa_tech_score -= 0.1
        
        fa_score = (val_score * 0.40 + qual_score * 0.30 + fa_tech_score * 0.30)
        fa_score = min(max(fa_score, 0.0), 1.0)
            
        # --- COMPOUNDER US / GLOBAL ---
        # Compounder focuses heavily on quality and growth, less on value/tech
        cmp_score = (qual_score * 0.45 + growth_score * 0.40 + tech_score * 0.15)
        cmp_score = min(max(cmp_score, 0.0), 1.0)
            
        history_out.append([
            valid_prices[0]["date"],
            round(current_price, 2),
            round(composite, 3),
            round(fa_score, 3) if fa_score > 0 else 0.0,
            round(cmp_score, 3) if cmp_score > 0 else 0.0,
            round(cmp_score, 3) if cmp_score > 0 else 0.0
        ])
        
    if not history_out:
        log.warning(f"[{symbol}] Could not generate history (missing data?).")
        return

    # Keep oldest first (standard format for charts)
    history_out.reverse()
    
    # Fetch existing live-scan history to preserve the TRUE scores
    out_path = f"stock_history/{symbol}.json"
    out_blob = bucket.blob(out_path)
    
    existing_history = []
    if not force and out_blob.exists():
        try:
            existing_history = json.loads(out_blob.download_as_string())
        except Exception as e:
            log.warning(f"[{symbol}] Failed to read existing history: {e}")
            
    # Merge: keep backfilled dates only if they are BEFORE the earliest real scan
    merged_history = []
    earliest_real_date = existing_history[0][0] if existing_history else "9999-99-99"
    
    for row in history_out:
        if row[0] < earliest_real_date:
            merged_history.append(row)
            
    merged_history.extend(existing_history)
    
    log.info(f"[{symbol}] Uploading {len(merged_history)} weeks of data to gs://{BUCKET_NAME}/{out_path} ({len(existing_history)} real scans preserved)")
    out_blob.upload_from_string(json.dumps(merged_history))

if __name__ == "__main__":
    force_mode = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    
    if len(args) > 0:
        symbols = args[0].split(',')
        for sym in symbols:
            backfill_symbol(sym.strip().upper(), force=force_mode)
    else:
        print("Usage: python3 backfill_history.py AAPL,NVDA,TSLA [--force]")
