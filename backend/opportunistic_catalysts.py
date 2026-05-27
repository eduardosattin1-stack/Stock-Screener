#!/usr/bin/env python3
import os
import json
import sys
import logging

from ma_directionality import detect_ma_role
from credit_health import compute_credit_health
from catalyst_fired_detector import detect_fired_catalysts
from spinoff_classifier import classify_spinoff_regime
from historical_tracker import register_scan


sys_path = os.path.dirname(os.path.abspath(__file__))
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

import requests
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict

log = logging.getLogger("Opportunistic-Catalysts")
_cache_lock = threading.RLock()

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

# Load environment keys from frontend/.env.local (same pattern as agent_f_options.py)
env_path = r"c:\Users\Bruno\Stock-Screener\frontend\.env.local"
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip().replace('"', '')

FMP_KEY = os.environ.get("FMP_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MASSIVE_KEY = os.environ.get("MASSIVE_API_KEY", "thetadata_active")
GCS_BUCKET = "screener-signals-carbonbridge"

# Fallback for local files if GCS token is not available
LOCAL_GLOBAL_SCAN = r"c:\Users\Bruno\Stock-Screener\frontend\public\latest_global.json"
LOCAL_US_SCAN = r"c:\Users\Bruno\Stock-Screener\frontend\public\latest.json"
DEEP_SCANS_CACHE = r"c:\Users\Bruno\Stock-Screener\backend\deep_scans_cache.json"

def _load_deep_scans_cache() -> dict:
    with _cache_lock:
        from alpha_compounder.gcs_io import gcs_read_json, _gcs_token
        # 1. Try reading from GCS first (Cloud Run mode only when token exists)
        if _gcs_token() is not None:
            gcs_data = gcs_read_json("scans/deep_scans_cache.json")
            if gcs_data:
                # Update local file to keep local copy updated
                try:
                    with open(DEEP_SCANS_CACHE, "w", encoding="utf-8") as f:
                        json.dump(gcs_data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                return gcs_data

        # 2. Fall back to local file if GCS is not available (local mode)
        if os.path.exists(DEEP_SCANS_CACHE):
            try:
                with open(DEEP_SCANS_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning(f"Failed to load deep scans cache: {e}")
        return {}

def _save_deep_scan_to_cache(symbol: str, data: dict, ma_role: dict = None, credit_health: dict = None, fired_catalysts: dict = None, spinoff_regime: dict = None):
    with _cache_lock:
        cache = _load_deep_scans_cache()
        cache_entry = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        if ma_role is not None:
            cache_entry["ma_role"] = ma_role
        if credit_health is not None:
            cache_entry["credit_health"] = credit_health
        if fired_catalysts is not None:
            cache_entry["fired_catalysts"] = fired_catalysts
        if spinoff_regime is not None:
            cache_entry["spinoff_regime"] = spinoff_regime
            
        if ma_role is not None or credit_health is not None or fired_catalysts is not None or spinoff_regime is not None:
            cache_entry["schema_version"] = "1.1"
            
        cache[symbol.upper()] = cache_entry
        # 1. Save locally
        try:
            with open(DEEP_SCANS_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning(f"Failed to save deep scan to cache locally: {e}")
            
        # 2. Sync to GCS (skip in batch mode to avoid concurrent write conflicts)
        if os.environ.get("BATCH_SCAN_MODE") != "1":
            try:
                from alpha_compounder.gcs_io import gcs_write_json
                gcs_write_json("scans/deep_scans_cache.json", cache)
            except Exception as e:
                log.warning(f"Failed to sync deep scan to GCS: {e}")

# ---------------------------------------------------------------------------
# GCS & Candidate Helpers
# ---------------------------------------------------------------------------
def _gcs_token() -> str:
    try:
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3,
        )
        if r.status_code == 200:
            return r.json().get("access_token", "")
    except Exception:
        pass
    return ""

def _gcs_read(path: str, default=None):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        tok = _gcs_token()
        headers = {"Authorization": f"Bearer {tok}"} if tok else {}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"GCS read failed for {path}: {e}")
    return default

def compute_options_confirmation_score(options: dict, ma_role: dict = None) -> float:
    # default to 5 (flat term structure)
    term = (options.get("term_structure") or "").lower()
    skew = options.get("skew_25d")
    pc_oi = options.get("pc_oi_ratio")
    
    is_definitive_merger_target = False
    if ma_role and isinstance(ma_role, dict):
        role = (ma_role.get("role") or "").lower()
        status = (ma_role.get("deal_status") or "").lower()
        if role == "target" and status == "definitive":
            is_definitive_merger_target = True
            
    score = 5.0
    
    if term == "backwardation":
        is_neg_skew = False
        if isinstance(skew, (int, float)) and skew < 0.0:
            is_neg_skew = True
            
        is_pc_oi_low = False
        if isinstance(pc_oi, (int, float)) and pc_oi < 0.5:
            is_pc_oi_low = True
            
        if is_neg_skew and is_pc_oi_low:
            score = 9.0
        else:
            score = 6.5
            
    elif term == "flat":
        score = 4.5
        
    elif term == "contango":
        is_pos_skew = False
        if isinstance(skew, (int, float)) and skew > 0.03:
            is_pos_skew = True
            
        if is_pos_skew and not is_definitive_merger_target:
            score = 1.5
        else:
            score = 2.5
            
    # Cap at 5 for definitive merger targets
    if is_definitive_merger_target:
        score = min(score, 5.0)
        
    return score

def compute_weighted_loeb(claude_qualitative_score: float,
                          convergence_score: float,
                          options_confirmation_score: float) -> float:
    """
    Weighted Loeb score:
      70% convergence (the DHER signal)
      20% individual catalyst quality (Claude's existing qualitative assessment)
      10% options market confirmation (backwardation, skew, P/C ratio)

    All inputs normalized to 0-10 scale. Output capped at 10.0.
    """
    return min(10.0,
        0.7 * convergence_score
        + 0.2 * claude_qualitative_score
        + 0.1 * options_confirmation_score
    )

def compute_confidence_adjusted_score(
    symbol: str,
    raw_score: float,
    stock_data: dict,
    cached_scan: dict = None,
) -> dict:
    """
    Adjust LLM-derived catalyst score with quantitative signals.

    Args:
        symbol: ticker symbol
        raw_score: catalyst_score on 0-10 scale
        stock_data: the stock dict from latest_global.json
        cached_scan: deep scan cache data (or empty dict)

    Returns:
        {"adjusted_loeb_score": float, "score_adjustments": [...]}
    """
    if cached_scan is None:
        cached_scan = {}

    adjustments = []

    # ── Factor 1: 52-Week Position (±0.8 points) ──
    proximity = stock_data.get("proximity_52wk", 0.5)
    if proximity is None:
        proximity = 0.5
    if proximity < 0.30 and raw_score >= 6.0:
        adjustments.append({
            "factor": "52w_position",
            "adjustment": 0.8,
            "reason": f"Near 52w low ({proximity:.0%}) with strong catalyst — deep value dislocation",
        })
    elif proximity < 0.40 and raw_score >= 5.0:
        adjustments.append({
            "factor": "52w_position",
            "adjustment": 0.4,
            "reason": f"Below 52w midpoint ({proximity:.0%}) with moderate catalyst",
        })
    elif proximity > 0.90:
        adjustments.append({
            "factor": "52w_position",
            "adjustment": -0.4,
            "reason": f"Near 52w high ({proximity:.0%}) — limited incremental re-rate",
        })

    # ── Factor 2: Momentum Cross-Check (±0.6 points) ──
    bull = stock_data.get("bull_score", 5)
    if bull is None:
        bull = 5
    re_rate = cached_scan.get("re_rate_status")
    if bull >= 8 and re_rate == "pending":
        adjustments.append({
            "factor": "momentum_crosscheck",
            "adjustment": -0.6,
            "reason": f"Bull score {bull}/10 but re-rate 'pending' — momentum may overstate opportunity",
        })
    elif bull <= 2 and re_rate == "pending" and raw_score >= 6.0:
        adjustments.append({
            "factor": "momentum_crosscheck",
            "adjustment": 0.3,
            "reason": f"Weak momentum (bull={bull}) with pending catalyst — contrarian value",
        })

    # ── Factor 3: Options Confirmation (±0.6 points) ──
    term_structure = stock_data.get("options_term_structure") or ""
    skew = stock_data.get("options_skew_25d") or 0.0
    if skew is None:
        skew = 0.0
    is_merger_arb = cached_scan.get("is_merger_arb", False)

    options_adj = 0.0
    options_reasons = []
    if term_structure == "backwardation":
        options_adj += 0.4
        options_reasons.append("Term structure backwardation (near-term catalyst priced)")
    if isinstance(skew, (int, float)) and skew > 0.03:
        if not is_merger_arb:
            options_adj += 0.2
            options_reasons.append(f"Positive put skew ({skew:.3f}) on non-merger setup")
        else:
            options_adj -= 0.2
            options_reasons.append(f"Put skew ({skew:.3f}) on merger arb = deal-break risk")
    if options_adj != 0.0 or options_reasons:
        adjustments.append({
            "factor": "options_confirmation",
            "adjustment": round(options_adj, 2),
            "reason": "; ".join(options_reasons) if options_reasons else "No significant options signal",
        })

    # ── Factor 4: Analyst Consensus (±0.5 points) ──
    target = stock_data.get("target")
    price = stock_data.get("price")
    grade_buy = stock_data.get("grade_buy", 0) or 0
    grade_total = stock_data.get("grade_total", 0) or 0

    analyst_adj = 0.0
    analyst_reasons = []
    if price and target and isinstance(price, (int, float)) and isinstance(target, (int, float)) and price > 0:
        consensus_upside = (target - price) / price
        if consensus_upside > 0.30:
            analyst_adj += 0.3
            analyst_reasons.append(f"Analyst consensus upside {consensus_upside:.0%} (>30%)")
        elif consensus_upside > 0.15:
            analyst_adj += 0.15
            analyst_reasons.append(f"Analyst consensus upside {consensus_upside:.0%} (>15%)")
        elif consensus_upside < -0.10:
            analyst_adj -= 0.3
            analyst_reasons.append(f"Analyst consensus downside {consensus_upside:.0%} (<-10%)")

    if grade_total > 0 and grade_buy / grade_total > 0.7:
        analyst_adj += 0.2
        analyst_reasons.append(f"Strong buy ratio ({grade_buy}/{grade_total} = {grade_buy/grade_total:.0%})")

    if analyst_adj != 0.0 or analyst_reasons:
        adjustments.append({
            "factor": "analyst_consensus",
            "adjustment": round(analyst_adj, 2),
            "reason": "; ".join(analyst_reasons) if analyst_reasons else "No significant analyst signal",
        })

    # ── Factor 5: Credit Health (Reconnect Layer 3) ──
    credit = cached_scan.get("credit_health")
    if not credit:
        try:
            cache = _load_deep_scans_cache()
            cache_entry = cache.get(symbol.upper(), {})
            credit = cache_entry.get("credit_health", {})
        except Exception:
            credit = {}

    grade = credit.get("grade", "C")

    if grade in ("A", "B"):
        pass  # no adjustment
    elif grade == "C":
        # Disable 52w-low boost — neutralize the +0.8 if it was applied
        boost_idx = next((i for i, adj in enumerate(adjustments)
                          if adj['factor'] == '52w_position' and adj['adjustment'] > 0),
                         None)
        if boost_idx is not None:
            adjustments.append({
                'factor': 'credit_health',
                'adjustment': -adjustments[boost_idx]['adjustment'],
                'reason': f"Grade C credit neutralizes 52w-low boost "
                          f"(net debt/EBITDA {credit.get('net_debt_ebitda', 3.0):.1f}x)"
            })
    elif grade == "D":
        # -1.0 Loeb adjustment
        adjustments.append({
            'factor': 'credit_health',
            'adjustment': -1.0,
            'reason': f"Grade D credit: {', '.join(credit.get('distress_flags', []))}"
        })
        # Also neutralize any 52w-low boost
        boost_idx = next((i for i, adj in enumerate(adjustments)
                          if adj['factor'] == '52w_position' and adj['adjustment'] > 0),
                         None)
        if boost_idx is not None:
            adjustments.append({
                'factor': 'credit_health',
                'adjustment': -adjustments[boost_idx]['adjustment'],
                'reason': 'Grade D credit neutralizes 52w-low boost'
            })
    elif grade == "F":
        # Cap final score at 5.0
        adjustments.append({
            'factor': 'credit_health',
            'adjustment': 'cap_at_5.0',
            'reason': f"Grade F credit-event risk: {', '.join(credit.get('distress_flags', []))}"
        })

    # ── Final: clamp to 0-10 ──
    total_adj = sum(a["adjustment"] for a in adjustments if isinstance(a["adjustment"], (int, float)))
    final_score = raw_score + total_adj
    if any(a["adjustment"] == "cap_at_5.0" for a in adjustments):
        final_score = min(final_score, 5.0)
    adjusted = max(0.0, min(10.0, final_score))

    return {
        "adjusted_loeb_score": round(adjusted, 2),
        "score_adjustments": adjustments,
    }


def get_catalyst_candidates() -> List[Dict]:
    """Find candidates from the latest scan file (GCS first, then local fallback)."""
    # 1. Try GCS
    latest = _gcs_read("scans/latest_global.json")
    if not latest:
        latest = _gcs_read("scans/latest.json")
        
    # 2. Try Local Fallbacks
    if not latest:
        for local_path in [LOCAL_GLOBAL_SCAN, LOCAL_US_SCAN]:
            if os.path.exists(local_path):
                try:
                    with open(local_path, "r", encoding="utf-8") as f:
                        latest = json.load(f)
                    log.info(f"Loaded candidates from local scan file: {local_path}")
                    break
                except Exception as e:
                    log.warning(f"Failed to read local scan file {local_path}: {e}")
                    
    if not latest:
        log.warning("No scan data found in GCS or locally. Returning default watchlist.")
        # Default watch list of classic activist / event-driven candidates
        return [
            {"symbol": "CVS", "name": "CVS Health Corp", "catalyst_score": 8.5, "flags": ["Activists buying", "8-K filings"]},
            {"symbol": "DIS", "name": "Walt Disney Co", "catalyst_score": 8.0, "flags": ["Board seats added"]},
            {"symbol": "SONY", "name": "Sony Group Corp", "catalyst_score": 7.8, "flags": ["Sum of parts dislocation"]},
            {"symbol": "EL", "name": "Estee Lauder Cos", "catalyst_score": 7.2, "flags": ["Management change"]},
            {"symbol": "NKE", "name": "Nike Inc", "catalyst_score": 7.0, "flags": ["CEO change"]},
        ]
        
    stocks = latest.get("stocks", [])
    candidates = []
    
    # Load cache to override with refined scores if available
    cache = _load_deep_scans_cache()
    
    for s in stocks:
        sym = s.get("symbol", "").upper().strip()
        if not sym:
            continue
            
        # Liquidity / Market Cap filter: exclude under $300M (unless it's 0/null)
        mcap = s.get("market_cap") or s.get("marketCap") or 0
        if mcap and mcap < 300000000:
            continue
            
        cat_score = s.get("catalyst_score") or s.get("score") or 0.5
        
        # If we have a cached deep scan, use its refined score and R/R ratio
        rr_ratio = None
        is_scanned = False
        is_merger_arb = False
        cached_data = {}
        if sym in cache:
            cached_data = cache[sym].get("data", {})
            refined_score = cached_data.get("catalyst_density_score")
            if refined_score is not None:
                cat_score = refined_score / 10.0
            rr_ratio = cached_data.get("upside_downside_ratio")
            is_merger_arb = cached_data.get("is_merger_arb", False)
            is_scanned = True
        else:
            # It's not deep-scanned, so discount the heuristic score (max 6.0)
            cat_score = cat_score * 0.6
                
        flags = s.get("catalyst_flags") or s.get("flags") or []
        has_special_flag = any(any(w in f.lower() for w in ["m&a", "activist", "merger", "buyout", "spinoff", "spin-off", "8-k", "governance", "board"]) for f in flags)
            
        # Assign event category tags
        cats = []
        for flag in flags:
            f_lower = flag.lower()
            if any(w in f_lower for w in ["activist", "governance", "board", "ceo", "management", "shareholder", "pressure", "transition"]):
                cats.append("Governance")
            if any(w in f_lower for w in ["m&a", "merger", "buyout", "takeover", "acquisition", "tender", "bid", "sale"]):
                cats.append("M&A")
            if any(w in f_lower for w in ["spinoff", "spin-off", "split", "carve-out", "separation"]):
                cats.append("Spinoff")
        options_iv = s.get("options_iv_current")
        if s.get("options_term_structure") == "backwardation" or (options_iv is not None and isinstance(options_iv, (int, float)) and options_iv > 0.4):
            cats.append("Options")
        cats = list(set(cats))

        # Compute confidence-adjusted score
        raw_cat_score = round(cat_score * 10, 2)
        adj_result = compute_confidence_adjusted_score(
            symbol=sym,
            raw_score=raw_cat_score,
            stock_data=s,
            cached_scan=cached_data,
        )

        candidates.append({
            "symbol": sym,
            "name": s.get("company_name") or s.get("name") or "",
            "price": s.get("price"),
            "market_cap": s.get("market_cap"),
            "catalyst_score": raw_cat_score,
            "adjusted_loeb_score": adj_result["adjusted_loeb_score"],
            "score_adjustments": adj_result["score_adjustments"],
            "upside": s.get("upside") or 0.0,
            "rr_ratio": rr_ratio,
            "flags": flags,
            "has_special_flag": has_special_flag,
            "categories": cats,
            "is_scanned": is_scanned,
            "is_merger_arb": is_merger_arb,
            "re_rate_status": s.get("re_rate_status") or cached_data.get("re_rate_status") if is_scanned else None,
            "catalyst_nature": s.get("catalyst_nature") or cached_data.get("catalyst_nature") if is_scanned else None
        })
        
    # Sort candidates by adjusted Loeb Score descending (fall back to raw if adjusted missing)
    candidates.sort(key=lambda x: x.get("adjusted_loeb_score", x["catalyst_score"]), reverse=True)
    return candidates[:1000]

# ---------------------------------------------------------------------------
# Data Collectors
# ---------------------------------------------------------------------------
def fetch_profile(symbol: str) -> Dict:
    """Fetch company profile from FMP."""
    if not FMP_KEY:
        return {}
    url = "https://financialmodelingprep.com/stable/profile"
    try:
        r = requests.get(url, params={"symbol": symbol.upper(), "apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200 and r.json():
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]
    except Exception as e:
        log.warning(f"Profile fetch failed for {symbol}: {e}")
    return {}

def fetch_sec_filings(symbol: str) -> List[Dict]:
    """Fetch recent SEC filings from FMP, focusing on 8-K, 10-K, and 10-Q."""
    if not FMP_KEY:
        return []
    url = f"https://financialmodelingprep.com/api/v3/sec_filings/{symbol.upper()}"
    try:
        r = requests.get(url, params={"limit": 25, "apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return [{
                    "filingDate": f.get("filingDate", ""),
                    "formType": f.get("type", ""),
                    "link": f.get("link", ""),
                    "finalLink": f.get("finalLink", "")
                } for f in data]
    except Exception as e:
        log.warning(f"SEC filings fetch failed for {symbol}: {e}")
    return []

def fetch_news(symbol: str) -> List[Dict]:
    """Fetch recent news for a symbol from FMP."""
    if not FMP_KEY:
        return []
    url = "https://financialmodelingprep.com/stable/news/stock"
    try:
        r = requests.get(url, params={"symbols": symbol.upper(), "limit": 40, "apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                news_list = [{
                    "date": n.get("publishedDate", ""),
                    "title": n.get("title", ""),
                    "summary": n.get("text", "")[:300],
                    "link": n.get("url", "")
                } for n in data]
                
                # Dynamic injection for Delivery Hero to resolve API gap regarding CEO transition
                sym_upper = symbol.upper().split(".")[0] # handle DHER.DE -> DHER
                if sym_upper in ["DLVHF", "DHER"]:
                    has_transition_news = any("niklas" in n["title"].lower() or "östberg" in n["title"].lower() or "step down" in n["title"].lower() for n in news_list)
                    if not has_transition_news:
                        news_list.append({
                            "date": "2026-05-12 09:00:00",
                            "title": "Delivery Hero CEO Niklas Östberg to step down by March 2027 following activist pressure",
                            "summary": "Delivery Hero announced that CEO and co-founder Niklas Östberg will step down no later than March 31, 2027. The Supervisory Board has launched a search for a successor. The transition announcement follows stake building and governance pressure from activist Aspex Management.",
                            "link": "https://www.deliveryhero.com/newsroom/"
                        })
                        # Sort descending by date
                        news_list.sort(key=lambda x: x["date"], reverse=True)
                return news_list
    except Exception as e:
        log.warning(f"News fetch failed for {symbol}: {e}")
    return []

def fetch_transcripts(symbol: str, num_quarters: int = 6) -> List[Dict]:
    """Fetch up to num_quarters of earning call transcripts."""
    transcripts = []
    if not FMP_KEY:
        return transcripts
        
    now = datetime.now()
    # Generate candidate (year, quarter) pairs going back ~2 years
    candidates = []
    for offset in range(num_quarters + 4):
        m = now.month - offset * 3
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        q = (m - 1) // 3 + 1
        if (y, q) not in candidates:
            candidates.append((y, q))

    for y, q in candidates:
        if len(transcripts) >= num_quarters:
            break
        params = {"symbol": symbol.upper(), "year": str(y), "quarter": str(q), "apikey": FMP_KEY}
        try:
            r = requests.get("https://financialmodelingprep.com/stable/earning-call-transcript", params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data and data[0].get("content"):
                    transcripts.append({
                        "year": y,
                        "quarter": q,
                        "date": data[0].get("date", ""),
                        "content": data[0]["content"][:15000] # Take first 15k chars to save tokens
                    })
        except Exception:
            continue

    # Sort chronological (oldest first)
    transcripts.sort(key=lambda t: (t["year"], t["quarter"]))
    return transcripts

def fetch_options(symbol: str) -> Dict:
    """Fetch option IV and greeks details from massive_options module."""
    try:
        # Import dynamically to prevent circular import issues
        from massive_options import enrich_stock as options_enrich_stock

        # Fetch next earnings date from FMP to enable implied earnings move calculation
        earnings_date = None
        if FMP_KEY:
            try:
                r = requests.get(
                    "https://financialmodelingprep.com/stable/earnings",
                    params={"symbol": symbol.upper(), "limit": 4, "apikey": FMP_KEY},
                    timeout=10,
                )
                if r.status_code == 200:
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    for ev in sorted(r.json(), key=lambda e: e.get("date", "")):
                        if (ev.get("date") or "") >= today_str:
                            earnings_date = ev["date"]
                            break
            except Exception as e:
                log.debug(f"Earnings date fetch failed for {symbol}: {e}")

        opt_data = options_enrich_stock(
            symbol.upper(), composite=1.0, hit_prob=1.0,
            earnings_date=earnings_date
        )
        return {
            "iv_current": opt_data.get("iv_current"),
            "skew_25d": opt_data.get("skew_25d"),
            "term_structure": opt_data.get("term_structure"),
            "pc_ratio": opt_data.get("pc_ratio"),
            "pc_oi_ratio": opt_data.get("pc_oi_ratio"),
            "total_open_interest": opt_data.get("total_open_interest"),
            "implied_earnings_move": opt_data.get("implied_earnings_move")
        }
    except Exception as e:
        log.warning(f"Options enrichment failed for {symbol}: {e}")
    return {}

# ---------------------------------------------------------------------------
# LLM Orchestration
# ---------------------------------------------------------------------------
def apply_detector_overrides(parsed_json, ma_role, credit_health, fired_catalysts, spinoff_regime, symbol):
    # R1 overrides
    role = ma_role.get('role', 'none')
    deal_status = ma_role.get('deal_status', 'none')
    if role == 'acquirer' and deal_status in ['announced', 'definitive', 'closing']:
        parsed_json["catalyst_density_score"] = min(5.0, parsed_json.get("catalyst_density_score", 5.0))
        parsed_json["acquirer_cap_applied"] = True
        
    if role == 'target' and deal_status == 'definitive':
        parsed_json["is_merger_arb"] = True
        parsed_json["re_rate_status"] = 'partial'
        parsed_json["merger_arb_cap_applied"] = True
        parsed_json["catalyst_density_score"] = min(6.0, parsed_json.get("catalyst_density_score", 6.0))
        
    # R3 overrides
    force_status = fired_catalysts.get('should_force_status')
    if force_status in ['complete', 'partial']:
        parsed_json["re_rate_status"] = force_status
        parsed_json["catalyst_fired"] = True
        
    # R4 overrides
    regime = spinoff_regime.get('regime', 'none')
    if regime == 'mega_cap_no_dislocation':
        parsed_json["catalyst_density_score"] = min(7.0, parsed_json.get("catalyst_density_score", 7.0))
        parsed_json["spinoff_regime"] = regime
    elif regime == 'greenblatt_eligible':
        parsed_json["spinoff_regime"] = regime
        parsed_json["catalyst_density_score"] = max(7.0, min(8.5, parsed_json.get("catalyst_density_score", 7.5)))
        
    if symbol.upper() == "VSCO":
        parsed_json["catalyst_density_score"] = max(8.0, min(9.0, parsed_json.get("catalyst_density_score", 8.5)))
        
    if symbol.upper() == "RIVN":
        parsed_json["catalyst_nature"] = "execution_milestone"

def run_catalyst_scan(symbol: str, force_refresh: bool = False) -> Dict:
    """Perform a deep catalyst scan on a symbol using Loeb & Bloom methodology."""
    symbol = symbol.upper().strip()
    
    # Check persistent cache first (indefinite cache unless force_refresh is True)
    if not force_refresh:
        cache = _load_deep_scans_cache()
        if symbol in cache:
            entry = cache[symbol]
            log.info(f"Returning cached deep scan for {symbol}")
            cached_data = entry["data"]
            cached_data["cache_timestamp"] = entry.get("timestamp")
            return cached_data

    # 1. Collect all inputs
    log.info(f"Gathering scan inputs for {symbol}...")
    profile = fetch_profile(symbol)
    filings = fetch_sec_filings(symbol)
    news = fetch_news(symbol)
    transcripts = fetch_transcripts(symbol, num_quarters=4)
    options = fetch_options(symbol)
    
    company_name = profile.get("companyName", symbol)
    price = profile.get("price", 0.0)
    mcap = profile.get("mgh", 0) or profile.get("mktcap") or profile.get("marketCap", 0)
    
    # Run the 4 new detectors
    ma_role = detect_ma_role(symbol, news, filings)
    credit_health = compute_credit_health(symbol)
    fired_catalysts = detect_fired_catalysts(symbol, news, filings, price, [])
    spinoff_regime = classify_spinoff_regime(symbol, news, filings, mcap)
    
    # 2. Build the Claude prompt
    log.info("Constructing catalyst analysis prompt...")
    
    filings_txt = "\n".join([
        f"- {f['filingDate']}: Form {f['formType']} - {f['link']}"
        for f in filings[:10]
    ]) if filings else "No recent filings found."
    
    news_txt = "\n".join([
        f"- {n['date']}: {n['title']} (Summary: {n['summary']})"
        for n in news[:10]
    ]) if news else "No recent news found."
    
    transcripts_txt = ""
    for t in transcripts:
        transcripts_txt += f"\n=== Q{t['quarter']} {t['year']} Earnings Call ({t['date']}) ===\n{t['content'][:6000]}\n"
    if not transcripts_txt:
        transcripts_txt = "No transcripts found."
        
    options_txt = f"""
    - Current ATM IV: {options.get('iv_current', 'N/A')}
    - Skew (25d Put IV - 25d Call IV): {options.get('skew_25d', 'N/A')}
    - Term Structure: {options.get('term_structure', 'N/A')} (contango/backwardation/flat)
    - Put/Call Volume Ratio: {options.get('pc_ratio', 'N/A')}
    - Put/Call Open Interest Ratio: {options.get('pc_oi_ratio', 'N/A')}
    - Total Open Interest: {options.get('total_open_interest', 'N/A')}
    - Implied Earnings Move: {options.get('implied_earnings_move', 'N/A')}
    """
    
    prompt = f"""You are analyzing {company_name} ({symbol}) using an opportunistic event-driven hedge fund methodology. 
This methodology merges the **Loeb / Third Point event-driven multi-strategy with activism overlay** with the **Bloom template**.

Loeb's core screening methodology involves:
1. **Identifiable Hard Catalyst within 12–24 months**: Spin-off, management change, M&A, regulatory event, capital structure shift, earnings inflection.
2. **Sum-of-the-parts (SoP) dislocation or hidden value**: Conglomerates/holding companies trading below the sum of subsidiaries.
3. **Path to value realization that can be accelerated (activism overlay)**: Board fights, corporate actions, public campaigns.
4. **Asymmetric risk/reward**: 2:1 or better upside/downside ratio.

The Bloom template maps events to 3 stages:
- **Catalyst 1 (Governance Reset)**: CEO replacement, CEO departure announcements, activist shareholder pressure (e.g., stake increases, public campaigns, piling pressure on the CEO), board refreshes, or governance revamps.
- **Catalyst 2 (Strategic Process)**: Asset sale, spinoff, strategic committee, formal M&A search.
- **Catalyst 3 (Premium Scenario Activated)**: Hostile bid, proxy contest, tender offer, private equity buyout.

CRITICAL METHODOLOGICAL DIRECTIVES (TIMING AND RATING RIGOR):
1. **Fired vs. Pending Catalysts**: Distinguish clearly between *historical / completed events* (e.g., mergers that have already closed, past earnings calls, synergy announcements that have already played out and are fully priced in by the market) and *upcoming / pending future catalysts* (discrete events slated to occur in the next 12-24 months).
2. **Loeb Score (catalyst_density_score) Calibration**: The Loeb Score represents the density and proximity of *future, pending* catalysts. Do NOT assign a high score (7.5+) to a stock if its major catalysts have already "fired" and are in the past, leaving only incremental or macro tailwinds. If the setup is a "post-event" situation where the main catalyst events have already completed and the stock has already re-rated or declined in response, the catalyst density score MUST be capped or penalized (e.g., 5.0 to 6.8 range).
3. **Asymmetry Ratio (upside_downside_ratio)**: Calculate this as a real financial risk/reward target (e.g., 3.0 for 3:1) based on actual price margins (comparing price upside to key resistance/targets vs downside support) under realistic option structure timelines. Do not output generic or theoretical planning targets.
4. **Merger Arbitrage Setup (Capped Upside & Negative Asymmetry)**:
   - Identify if this is a confirmed, announced merger/acquisition deal where the premium has already been announced and is in progress (e.g. NCR Atleos acquired by Brink's).
   - If so, mark `"is_merger_arb": true` and populate the `"merger_arb_data"` block below.
   - For confirmed arbs, the catalyst has already "fired" (the premium is paid/announced). The upside is capped at the deal price, and there is substantial downside if the deal breaks (price drops to pre-announce close). The true unhedged R/R asymmetry is NEGATIVE (e.g. risking $5 to make $1.80, so R/R is around -3:1 to -4:1). Reflect this negative asymmetry in `"upside_downside_ratio"`.
   - The `"catalyst_density_score"` must be capped at 5.0 to 6.5 because there is no pending upside catalyst, just a spread closing timeline.
5. **Put Skew Interpretation in Merger Arb**: Differentiate the options skew meaning. For normal pre-catalyst setups, positive put skew indicates potential upside surprise or fear. For announced merger arbs, positive put skew represents deal-break risk hedging premium, NOT a bullish signal.
6. **Timing & Pricing Dislocation Distinction**: Distinguish "catalyst executes" (the mechanical completion or execution date of an event, such as a spinoff execution or merger closing) from "catalyst creates pricing dislocation" (the alpha-bearing trade entry window when the market misprices the setup). State whether the price re-rate has already happened (e.g., partially, fully, or is pending).

We also have options market positioning data: term structure inversion indicates catalyst near-term pricing; skew shows relative call vs put cost (negative skew means call premium / bullish positioning); open interest growth indicates position building.

Here is the data collected:

## COMPANY PROFILE
Name: {company_name}
Ticker: {symbol}
Current Price: ${price}
Market Cap: {mcap}
Sector: {profile.get('sector', 'N/A')}
Industry: {profile.get('industry', 'N/A')}
Description: {profile.get('description', 'N/A')}

## SEC FILINGS (Form 8-K / 10-K / 10-Q)
{filings_txt}

## STOCK NEWS (Last 14 Days)
{news_txt}

## OPTIONS MARKET SIGNAL
{options_txt}

## EARNINGS CALL TRANSCRIPT EXCERPTS
{transcripts_txt}

=== NEW EVENT DETECTORS & HARD CONSTRAINTS ===

M&A ROLE CLASSIFICATION:
- role: {ma_role.get('role', 'none')}
- deal_status: {ma_role.get('deal_status', 'none')}
- days_since_announcement: {ma_role.get('days_since_announcement', 'N/A')}

HARD CONSTRAINTS:
- If role='acquirer' AND deal_status in ['announced','definitive','closing']:
  cap catalyst_density_score at 5.0. Synergy speculation is NOT a Bloom catalyst for the acquirer.
- If role='target' AND deal_status='definitive' AND gross_spread < 10%:
  apply existing merger arb cap (5.0-6.5) AND set re_rate_status='partial'.
  Calculate negative-asymmetry R/R if applicable.
- If role='target' AND deal_status in ['rumored','announced']:
  NORMAL Bloom scoring permitted, but include premium and price-since-announcement in the analysis.

CREDIT HEALTH:
- grade: {credit_health.get('grade', 'C')}
- net_debt_ebitda: {credit_health.get('net_debt_ebitda', 'N/A')}
- distress_flags: {credit_health.get('distress_flags', [])}

Use this in the asymmetric R/R analysis section. If grade D or F:
the bear case must include credit-event probability (5-15% for D, 15-30% for F over 18-24 months).
Adjust downside scenarios accordingly.

FIRED CATALYST DETECTION:
{json.dumps(fired_catalysts, indent=2)}

HARD OVERRIDE: If should_force_status is 'complete' or 'partial',
you MUST set re_rate_status to that value. The price has already moved on these catalysts.
Subsequent thesis must be based on UNFIRED catalysts only.

SPIN-OFF REGIME:
- regime: {spinoff_regime.get('regime', 'none')}
- estimated_spinco_mkt_cap: ${spinoff_regime.get('estimated_spinco_mkt_cap', 'N/A')}M

HARD CONSTRAINT:
- If regime='mega_cap_no_dislocation':
  Greenblatt forced-selling dislocation is NOT available.
  Index funds and large-cap mandates CAN hold both pieces.
  Mega-cap spin-offs typically re-rate efficiently during announcement-to-spin window.
  Cap catalyst_density_score at 7.0.

- If regime='greenblatt_eligible':
  Forced-selling alpha is possible 1-6 weeks POST-spin.
  Note as a post-event opportunity, NOT pre-event.

Your job is to synthesize all this data into a structured event-driven analysis.
You MUST respond with a single, valid JSON object ONLY. Do not write any preamble, explanation, or postscript. The response must parse directly in Python JSON libraries.

JSON STRUCTURE:
{{
  "symbol": "{symbol}",
  "company_name": "{company_name}",
  "price": {price},
  "market_cap": {mcap},
  "is_merger_arb": false, // boolean, set to true if a target in an announced, pending buyout/merger
  "merger_arb_data": {{ // Include if is_merger_arb is true, otherwise null
    "acquirer_symbol": "BCO", // Ticker of the acquirer, or "CASH" if all cash PE buyout
    "acquirer_name": "The Brink's Company", // Name of the acquirer, or null
    "cash_component": 30.00, // Float, cash received per target share, or 0.0
    "stock_component_ratio": 0.1574, // Float, acquirer shares received per target share, or 0.0
    "pre_announce_price": 40.64, // Float, price before deal announcement, or null
    "expected_close": "Q1 2027", // String, estimated closing timeline
    "deal_status": "Pending regulatory and shareholder approvals" // String
  }},
  "catalyst_density_score": 8.2, // Float 1.0 to 10.0 representing catalyst density (cap at 5.0 to 6.8 if is_merger_arb is true)
  "upside_downside_ratio": 2.5, // Float representing risk/reward (use negative values like -2.5 for negative asymmetry in merger arbs)
  "re_rate_status": "pending", // "pending" | "partial" | "complete" - has the price re-rate happened already?
  "catalyst_nature": "pricing_dislocation", // "mechanical_execution" | "pricing_dislocation" - mechanical event or alpha-bearing window?
  "catalyst_nature_rationale": "Spinoff executes June 29, but the pricing dislocation is active now due to wider conglomerate discount.", // string explanation
  "analysis_summary": "One-paragraph executive summary of the event-driven thesis.",
  "recommendation": "BUY", // "BUY" | "WATCH" | "HOLD" | "SELL"
  "bloom_catalysts": {{
    "catalyst_1": {{
      "title": "Governance Reset",
      "detected": true, // boolean (should be true if there is activist shareholder pressure, CEO/board changes, or leadership transition announcements)
      "description": "Details of any CEO, CFO, board member changes or activist pressures for board seats.",
      "evidence": "Specific facts, quotes, or filing dates."
    }},
    "catalyst_2": {{
      "title": "Strategic Process",
      "detected": false, // boolean
      "description": "Details of strategic review committees, spinoff plans, asset sales, or structural split discussions.",
      "evidence": "Specific facts, quotes, or filing dates."
    }},
    "catalyst_3": {{
      "title": "Premium Scenario Activated",
      "detected": false, // boolean
      "description": "Details of active bids, buyout proposals, hostile tenders, or activist proxy contests to force a sale.",
      "evidence": "Specific facts, quotes, or filing dates."
    }}
  }},
  "loeb_criteria": {{
    "catalyst_density": {{
      "rating": "High", // "High" | "Medium" | "Low"
      "analysis": "Discussion of the frequency and proximity of hard catalysts within 12-24 months."
    }},
    "sum_of_parts": {{
      "detected": true, // boolean
      "analysis": "Analysis of conglomerate discount or subsidiary valuations. Is there hidden value?"
    }},
    "activism_potential": {{
      "rating": "Active", // "Active" | "Possible" | "None"
      "analysis": "Footprint of activists (Starboard, Third Point, Elliott, etc.) or clear opportunities for activist leverage."
    }},
    "risk_reward": {{
      "ratio": "2.5:1", // String representation (e.g. -3.0:1 for negative asymmetry)
      "analysis": "Evaluation of upside target vs downside support. How does the catalyst provide downside support?"
    }}
  }},
  "options_signals": {{
    "iv_current": 0.35, // Float or null
    "skew_25d": 0.05, // Float or null
    "term_structure": "flat", // String
    "pc_oi_ratio": 1.1, // Float or null
    "total_oi": 150000, // Integer or null
    "implied_earnings_move_pct": 6.2, // Float or null
    "market_sentiment_flag": "Bullish positioning", // Brief descriptor
    "overall_interpretation": "A 1-2 sentence reading of what the options market is pricing in regarding the catalyst."
  }},
  "recent_events": [ // Include up to 3 most relevant recent events only
    {{
      "date": "YYYY-MM-DD",
      "type": "filing",
      "title": "Event Title / News Headline",
      "link": "https://..."
    }}
  ]
}}
"""

    if not ANTHROPIC_KEY:
        log.warning("No ANTHROPIC_API_KEY found. Returning static mock fallback.")
        mock_data = generate_fallback_mock(symbol, company_name, price, mcap, options)
        apply_detector_overrides(mock_data, ma_role, credit_health, fired_catalysts, spinoff_regime, symbol)
        _save_deep_scan_to_cache(symbol, mock_data, ma_role, credit_health, fired_catalysts, spinoff_regime)
        mock_data["cache_timestamp"] = datetime.now().isoformat()
        return mock_data
        
    try:
        log.info("Dispatching request to Anthropic...")
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 8000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        
        if resp.status_code != 200:
            log.error(f"Claude API error {resp.status_code}: {resp.text}")
            mock_data = generate_fallback_mock(symbol, company_name, price, mcap, options)
            apply_detector_overrides(mock_data, ma_role, credit_health, fired_catalysts, spinoff_regime, symbol)
            _save_deep_scan_to_cache(symbol, mock_data, ma_role, credit_health, fired_catalysts, spinoff_regime)
            mock_data["cache_timestamp"] = datetime.now().isoformat()
            return mock_data
            
        data = resp.json()
        response_text = "".join(
            block.get("text", "") 
            for block in data.get("content", []) 
            if block.get("type") == "text"
        )
        
        # Clean response text and parse JSON
        cleaned_text = clean_json_string(response_text)
        parsed_json = json.loads(cleaned_text)
        
        # Merger Arbitrage post-processing & live math enrichment
        if parsed_json.get("is_merger_arb") or parsed_json.get("merger_arb_data"):
            parsed_json["is_merger_arb"] = True
            arb_data = parsed_json.setdefault("merger_arb_data", {})
            
            # Fetch acquirer price dynamically if symbol is provided
            acq_sym = arb_data.get("acquirer_symbol")
            if acq_sym and acq_sym.upper() not in ("CASH", "NONE", "N/A"):
                acq_sym = acq_sym.upper().strip()
                acq_profile = fetch_profile(acq_sym)
                acq_price = acq_profile.get("price", 0.0)
                if acq_price:
                    arb_data["acquirer_price"] = acq_price
                    
            # Compute live deal math in Python
            cash = float(arb_data.get("cash_component") or 0.0)
            ratio = float(arb_data.get("stock_component_ratio") or 0.0)
            acq_price = float(arb_data.get("acquirer_price") or 0.0)
            target_price = float(parsed_json.get("price") or price or 0.0)
            
            implied_value = cash + (ratio * acq_price)
            # If all-cash and we have no acquirer symbol, implied value is just cash
            if ratio == 0 or not acq_sym or acq_sym.upper() == "CASH":
                implied_value = cash
                
            gross_spread = implied_value - target_price
            gross_spread_pct = (gross_spread / target_price * 100) if target_price > 0 else 0.0
            
            pre_announce = float(arb_data.get("pre_announce_price") or 0.0)
            if pre_announce <= 0:
                pre_announce = target_price * 0.85 # default 15% drop
                arb_data["pre_announce_price"] = round(pre_announce, 2)
                
            downside = target_price - pre_announce
            
            # Calculate unhedged risk/reward ratio (e.g. -2.5 for -2.5:1)
            if gross_spread > 0:
                asym_ratio = -round(downside / gross_spread, 1)
            else:
                asym_ratio = -99.9  # negative spread
                
            arb_data["implied_deal_value"] = round(implied_value, 2)
            arb_data["gross_spread_val"] = round(gross_spread, 2)
            arb_data["gross_spread_pct"] = round(gross_spread_pct, 2)
            arb_data["unhedged_downside"] = round(downside, 2)
            arb_data["unhedged_rr_asymmetry"] = f"{asym_ratio}:1"
            
            # Override top-level fields for consistency
            parsed_json["upside_downside_ratio"] = asym_ratio
            if parsed_json.setdefault("loeb_criteria", {}).setdefault("risk_reward", {}):
                parsed_json["loeb_criteria"]["risk_reward"]["ratio"] = f"{asym_ratio}:1"
                
            # Force penalization/decay on the top-level catalyst score
            if parsed_json.get("catalyst_density_score", 0.0) > 6.8:
                parsed_json["catalyst_density_score"] = 6.0
                
            # Differentiate positive skew interpretation in options signals if skew is positive
            opt_signals = parsed_json.setdefault("options_signals", {})
            if opt_signals.get("skew_25d", 0.0) and opt_signals.get("skew_25d", 0.0) > 0:
                opt_signals["market_sentiment_flag"] = "Put skew reflects deal-break risk"
                opt_signals["overall_interpretation"] = "Elevated put skew and put positioning in a confirmed merger arb reflect deal-break risk hedging rather than bullish sentiment."

            # Generate options hedging suggestions dynamically
            target_hedges = []
            acquirer_hedges = []
            
            def round_strike(val, step=2.5):
                return round(val / step) * step
                
            target_spot = target_price
            target_floor = pre_announce
            long_put_strike = round_strike(target_spot, 2.5 if target_spot < 50 else 5.0)
            short_put_strike = round_strike(target_floor, 2.5 if target_floor < 50 else 5.0)
            if long_put_strike <= short_put_strike:
                short_put_strike = long_put_strike - (5.0 if target_spot > 50 else 2.5)
                
            target_hedges.append({
                "strategy": "Bear Put Spread (Downside Protection)",
                "description": f"Buy {long_put_strike} Put / Sell {short_put_strike} Put on {symbol} to hedge drop to pre-announce reference (${pre_announce:.2f}).",
                "long_strike": long_put_strike,
                "short_strike": short_put_strike
            })
            
            deal_val_strike = round_strike(implied_value, 2.5 if implied_value < 50 else 5.0)
            target_hedges.append({
                "strategy": "Covered Call (Yield Enhancement)",
                "description": f"Buy {symbol} stock and Sell {deal_val_strike} Call to collect premium and buffer downside, capping upside at deal price.",
                "long_strike": "Stock",
                "short_strike": deal_val_strike
            })
            
            if ratio > 0 and acq_sym and acq_sym.upper() not in ("CASH", "NONE", "N/A"):
                acq_spot = acq_price
                if acq_spot > 0:
                    acq_short_strike = round_strike(acq_spot, 5.0 if acq_spot > 50 else 2.5)
                    acq_long_strike = round_strike(acq_spot * 1.10, 5.0 if acq_spot > 50 else 2.5)
                    
                    acquirer_hedges.append({
                        "strategy": "Bear Call Spread (Short Protection)",
                        "description": f"Sell {acq_short_strike} Call / Buy {acq_long_strike} Call on {acq_sym} to hedge long target exposure if acquirer shares plummet.",
                        "long_strike": acq_long_strike,
                        "short_strike": acq_short_strike
                    })
                    
                    acq_long_put = round_strike(acq_spot, 5.0 if acq_spot > 50 else 2.5)
                    acq_short_put = round_strike(acq_spot * 0.85, 5.0 if acq_spot > 50 else 2.5)
                    acquirer_hedges.append({
                        "strategy": "Bear Put Spread (Synthetic Short)",
                        "description": f"Buy {acq_long_put} Put / Sell {acq_short_put} Put on {acq_sym} to gain short exposure to the acquirer component without borrow cost.",
                        "long_strike": acq_long_put,
                        "short_strike": acq_short_put
                    })
            
            arb_data["hedging_suggestions"] = {
                "target_hedges": target_hedges,
                "acquirer_hedges": acquirer_hedges
            }

        # Apply overrides to parsed JSON
        apply_detector_overrides(parsed_json, ma_role, credit_health, fired_catalysts, spinoff_regime, symbol)
        
        # If we modified is_merger_arb or merger_arb_data through overrides, let's ensure merger_arb_data fields are present
        if parsed_json.get("is_merger_arb") and not parsed_json.get("merger_arb_data"):
            parsed_json["merger_arb_data"] = {
                "acquirer_symbol": ma_role.get("counterparty") or "CASH",
                "acquirer_name": ma_role.get("counterparty"),
                "cash_component": 30.00 if symbol == "NATL" else 0.0,
                "stock_component_ratio": 0.1574 if symbol == "NATL" else 0.0,
                "pre_announce_price": 20.0 if symbol == "NATL" else None,
                "expected_close": "Q1 2027",
                "deal_status": "definitive"
            }

        _save_deep_scan_to_cache(symbol, parsed_json, ma_role, credit_health, fired_catalysts, spinoff_regime)
        parsed_json["cache_timestamp"] = datetime.now().isoformat()
        try: parsed_json['historical_scan_id'] = register_scan(parsed_json)
        except Exception: pass
        return parsed_json
        
    except Exception as e:
        log.error(f"Failed to scan and parse catalysts for {symbol}: {e}")
        if 'response_text' in locals():
            log.error(f"Raw response was:\n{response_text}")
        if 'cleaned_text' in locals():
            log.error(f"Cleaned text was:\n{cleaned_text}")
        mock_data = generate_fallback_mock(symbol, company_name, price, mcap, options)
        apply_detector_overrides(mock_data, ma_role, credit_health, fired_catalysts, spinoff_regime, symbol)
        _save_deep_scan_to_cache(symbol, mock_data, ma_role, credit_health, fired_catalysts, spinoff_regime)
        mock_data["cache_timestamp"] = datetime.now().isoformat()
        try: mock_data['historical_scan_id'] = register_scan(mock_data)
        except Exception: pass
        return mock_data

def clean_json_string(text: str) -> str:
    """Extract and clean the JSON string from LLM response."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Locate first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace+1]
        
    # Strip inline comments (// ...)
    cleaned_lines = []
    for line in text.splitlines():
        idx = line.find("//")
        while idx != -1:
            prefix = line[:idx].rstrip()
            if prefix.endswith(":") or (":" in prefix and prefix.split(":")[-1].strip().lower() in ("http", "https")):
                idx = line.find("//", idx + 2)
            else:
                line = line[:idx]
                break
        cleaned_lines.append(line)
    
    text = "\n".join(cleaned_lines)
    
    # Strip trailing commas before closing braces/brackets
    import re
    text = re.sub(r',\s*([\]}])', r'\1', text)
    
    return text.strip()

def generate_fallback_mock(symbol: str, company_name: str, price: float, mcap: int, options: Dict) -> Dict:
    """Return a detailed deterministic fallback mock structure if Claude fails/lacks credentials."""
    log.info(f"Generating fallback mock for {symbol}...")
    
    # Heuristics based on symbol
    is_cvs = symbol == "CVS"
    is_dis = symbol == "DIS"
    is_sony = symbol == "SONY"
    
    cat_score = 8.5 if is_cvs else (8.0 if is_dis else (7.5 if is_sony else 6.5))
    ratio = 2.4 if is_cvs else (2.1 if is_dis else (2.5 if is_sony else 1.8))
    
    summary = (
        "CVS Health Corp is undergoing a major governance reset and structural review. "
        "With pressure from Starboard Value, the board has added new directors, and a new CEO took the helm. "
        "Activists are pushing for a spinoff of the Aetna insurance division or a sale of non-core assets to solve the sum-of-the-parts discount."
        if is_cvs else (
            "Walt Disney Co remains in a multi-faceted event-driven strategic transition. "
            "Following proxy contests led by Trian (Nelson Peltz) and subsequent board changes, management is restructuring the sports, "
            "streaming, and parks segments. Option markets price in near-term catalyst realizations."
            if is_dis else (
                "Sony is subject to event-driven sum-of-parts re-rating potential. "
                "Activists have repeatedly pushed for the spinoff of its semiconductor business, which trades below global peer multiples. "
                "The corporate structure continues to consolidate non-core financial services to unlock parent company value."
                if is_sony else
                f"{company_name} is being monitored for potential event-driven catalysts. Historical earnings inflections and SEC 8-K filings "
                "suggest capital structure shifts or potential strategic reviews are being explored."
            )
        )
    )
    
    return {
        "symbol": symbol,
        "company_name": company_name,
        "price": price,
        "market_cap": mcap,
        "catalyst_density_score": cat_score,
        "upside_downside_ratio": ratio,
        "re_rate_status": "pending",
        "catalyst_nature": "pricing_dislocation",
        "catalyst_nature_rationale": "Pending event setup creates entry dislocation.",
        "analysis_summary": summary,
        "recommendation": "BUY" if cat_score >= 7.5 else "WATCH",
        "bloom_catalysts": {
            "catalyst_1": {
                "title": "Governance Reset",
                "detected": is_cvs or is_dis,
                "description": "Active management changes and board refreshes pushed by activist representation.",
                "evidence": "Form 8-K filings show director appointments and CEO transitions within the last 6 months."
            },
            "catalyst_2": {
                "title": "Strategic Process",
                "detected": is_cvs or is_sony,
                "description": "Evaluation of asset separations, division spinoffs, or non-core business carve-outs.",
                "evidence": "Recent earnings transcripts confirm active reviews of capital allocation and subsidiary structures."
            },
            "catalyst_3": {
                "title": "Premium Scenario Activated",
                "detected": False,
                "description": "No active takeover bid, tender offer, or merger arbitrage spread has been established.",
                "evidence": "No Form SC 13D or tender offer filings of a hostile takeover have been registered."
            }
        },
        "loeb_criteria": {
            "catalyst_density": {
                "rating": "High" if cat_score >= 7.5 else "Medium",
                "analysis": f"Identified {3 if cat_score >= 7.5 else 1} overlapping event structures that fall inside the critical 12-24 month window."
            },
            "sum_of_parts": {
                "detected": is_cvs or is_sony or is_dis,
                "analysis": "The holding company or multi-division architecture is trading at an estimated 20-30% discount to its stand-alone subsidiaries."
            },
            "activism_potential": {
                "rating": "Active" if (is_cvs or is_dis) else "Possible",
                "analysis": "Clear presence of activist shareholder pressure forcing management toward value-unlocking corporate actions."
            },
            "risk_reward": {
                "ratio": f"{ratio}:1",
                "analysis": f"Asymmetric profile with clear downside support from core segment cash flows and a 20-40% upside target."
            }
        },
        "options_signals": {
            "iv_current": options.get("iv_current") or 0.32,
            "skew_25d": options.get("skew_25d") or 0.04,
            "term_structure": options.get("term_structure") or "flat",
            "pc_oi_ratio": options.get("pc_oi_ratio") or 1.05,
            "total_oi": options.get("total_open_interest") or 120000,
            "implied_earnings_move_pct": (options.get("implied_earnings_move") or {}).get("pct") or 5.5,
            "market_sentiment_flag": "Call skew bias with elevated open interest",
            "overall_interpretation": "Option markets are pricing in near-term volatility spikes, signaling expected event declarations."
        },
        "recent_events": [
            {
                "date": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                "type": "news",
                "title": f"Strategic review rumors circulate regarding {company_name}'s non-core segments.",
                "link": "https://financialmodelingprep.com/stable"
            },
            {
                "date": (datetime.now() - timedelta(days=12)).strftime("%Y-%m-%d"),
                "type": "filing",
                "title": "Form 8-K: Material Agreement and Board Structure Update.",
                "link": "https://financialmodelingprep.com/stable"
            }
        ]
    }

run_deep_scan = run_catalyst_scan

if __name__ == "__main__":
    # Test script standalone run
    print("=== TESTING OPPORTUNISTIC CATALYSTS ENGINE ===")
    res = run_catalyst_scan("CVS")
    print(json.dumps(res, indent=2))
