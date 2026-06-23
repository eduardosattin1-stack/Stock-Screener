import json
from backfill_history import BUCKET_NAME, get_gcs_json, get_historical_prices, safe_float, rsi_calc
from google.cloud import storage
from datetime import datetime, timedelta

def test_aapl():
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    
    inc_cached = get_gcs_json(bucket, "fmp_cache/income-statement", "AAPL")
    km_cached = get_gcs_json(bucket, "fmp_cache/key-metrics", "AAPL")
    inc = inc_cached.get("payload", [])
    km = km_cached.get("payload", [])
    for ls in (inc, km):
        for r in ls:
            if not r.get("filingDate") and r.get("date"):
                r["filingDate"] = r["date"]
    inc = sorted([r for r in inc if r.get("filingDate")], key=lambda x: x["filingDate"])
    km = sorted([r for r in km if r.get("filingDate")], key=lambda x: x["filingDate"])
    
    prices = get_historical_prices(bucket, "AAPL")
    prices = sorted(prices, key=lambda x: x["date"], reverse=True)
    
    today = datetime.now()
    target_date = today - timedelta(weeks=0) # last week
    target_str = target_date.strftime("%Y-%m-%d")
    
    valid_prices = [p for p in prices if p["date"] <= target_str]
    current_price = valid_prices[0]["close"]
    closes = [p["close"] for p in valid_prices]
    sma_50 = sum(closes[:50]) / 50
    sma_200 = sum(closes[:200]) / 200
    curr_rsi = rsi_calc(closes, 14)
    
    inc_pit = [r for r in inc if r["filingDate"] < target_str]
    km_pit = [r for r in km if r["filingDate"] < target_str]
    
    latest_inc = inc_pit[-1]
    older_inc = inc_pit[-4]
    
    rev_cagr = (latest_inc.get("revenue", 0) / older_inc.get("revenue", 1)) - 1 if older_inc.get("revenue", 1) > 0 else 0
    eps_cagr = (latest_inc.get("eps", 0) / older_inc.get("eps", 1)) - 1 if older_inc.get("eps", 1) > 0 else 0
    
    roe = safe_float(km_pit[-1].get("returnOnEquity"))
    gross_margin = latest_inc.get("grossProfit", 0) / latest_inc.get("revenue", 1) if latest_inc.get("revenue", 1) > 0 else 0
    net_margin = latest_inc.get("netIncome", 0) / latest_inc.get("revenue", 1) if latest_inc.get("revenue", 1) > 0 else 0
    
    shares = latest_inc.get("weightedAverageShsOutDil") or latest_inc.get("weightedAverageShsOut") or 1
    eps = latest_inc.get("epsDiluted") or 0
    rev_ps = latest_inc.get("revenue", 0) / shares
    
    pe = current_price / eps if eps > 0 else 999
    ps = current_price / rev_ps if rev_ps > 0 else 999
    earnings_yield = eps / current_price if current_price > 0 else 0
    
    tech_score = 0.5
    if current_price > sma_50: tech_score += 0.1
    if current_price > sma_200: tech_score += 0.1
    if sma_50 > sma_200: tech_score += 0.1
    if curr_rsi < 30: tech_score -= 0.1
    elif curr_rsi > 70: tech_score += 0.1
    
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
    
    composite = (val_score * 0.33 + growth_score * 0.17 + qual_score * 0.17 + tech_score * 0.17) * 1.19
    composite = min(max(composite, 0.0), 1.0)
    
    fa_tech_score = 0.5
    if curr_rsi < 35: fa_tech_score += 0.3
    elif curr_rsi < 45: fa_tech_score += 0.1
    elif curr_rsi > 70: fa_tech_score -= 0.3
    if current_price < sma_200: fa_tech_score += 0.2
    else: fa_tech_score -= 0.1
    
    fa_score = (val_score * 0.33 + growth_score * 0.17 + qual_score * 0.17 + fa_tech_score * 0.17) * 1.19
    fa_score = min(max(fa_score, 0.0), 1.0)
    
    print(f"val: {val_score}, growth: {growth_score}, qual: {qual_score}")
    print(f"tech: {tech_score}, fa_tech: {fa_tech_score}")
    print(f"composite: {composite}, fa_score: {fa_score}")

if __name__ == "__main__":
    test_aapl()
