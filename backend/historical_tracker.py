import os
import json
import logging
import uuid
from datetime import datetime, timedelta
from google.cloud import storage

log = logging.getLogger("Historical-Tracker")

# Automatically set credentials if not present in the environment
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    adc_path = os.path.expandvars(r"%APPDATA%\gcloud\legacy_credentials\carbonbridge.tech@gmail.com\adc.json")
    if os.path.exists(adc_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = adc_path
if "GOOGLE_CLOUD_PROJECT" not in os.environ:
    os.environ["GOOGLE_CLOUD_PROJECT"] = "screener-signals-carbonbridge"

GCS_BUCKET = "screener-signals-carbonbridge"
GCS_BLOB_PATH = "historical/score_outcomes.json"
LOCAL_FALLBACK_PATH = "backend/Cache_Data/historical_score_outcomes.json"

def _load_outcomes(gcs_client=None):
    """
    Downloads historical/score_outcomes.json from GCS.
    Returns (outcomes_dict, generation).
    If GCS fails or is not authenticated, falls back to local file.
    """
    if gcs_client is None:
        try:
            gcs_client = storage.Client()
        except Exception:
            pass
    if gcs_client is not None:
        try:
            bucket = gcs_client.bucket(GCS_BUCKET)
            blob = bucket.blob(GCS_BLOB_PATH)
            if blob.exists():
                blob.reload()
                text = blob.download_as_text()
                return json.loads(text), blob.generation
            else:
                return {}, 0
        except Exception as e:
            log.debug(f"GCS load failed: {e}")
            
    # Local fallback
    if os.path.exists(LOCAL_FALLBACK_PATH):
        try:
            with open(LOCAL_FALLBACK_PATH, "r", encoding="utf-8") as f:
                return json.load(f), None
        except Exception as e:
            log.warning(f"Failed to read local fallback outcomes: {e}")
    return {}, None

def _save_outcomes(outcomes, generation=None, gcs_client=None) -> bool:
    """
    Saves historical/score_outcomes.json.
    If generation is not None, performs atomic write using if_generation_match.
    Returns True on success, False on conflict/error.
    """
    if gcs_client is None:
        try:
            gcs_client = storage.Client()
        except Exception:
            pass
    if gcs_client is not None and generation is not None:
        try:
            bucket = gcs_client.bucket(GCS_BUCKET)
            blob = bucket.blob(GCS_BLOB_PATH)
            payload = json.dumps(outcomes, indent=2, ensure_ascii=False)
            blob.upload_from_string(
                payload,
                content_type="application/json",
                if_generation_match=generation
            )
            return True
        except Exception as e:
            log.debug(f"GCS atomic save failed: {e}")
            return False
            
    # Local fallback or non-atomic write
    try:
        os.makedirs(os.path.dirname(LOCAL_FALLBACK_PATH), exist_ok=True)
        tmp_path = LOCAL_FALLBACK_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(outcomes, f, indent=2, ensure_ascii=False)
        if os.path.exists(LOCAL_FALLBACK_PATH):
            os.remove(LOCAL_FALLBACK_PATH)
        os.rename(tmp_path, LOCAL_FALLBACK_PATH)
        return True
    except Exception as e:
        log.warning(f"Failed to write outcomes locally: {e}")
        return False

def register_scan(scan_result: dict, gcs_client=None) -> str:
    """
    Persists a scan to gs://screener-signals-carbonbridge/historical/score_outcomes.json
    """
    scan_id = str(uuid.uuid4())
    symbol = scan_result.get("symbol", "").upper().strip()
    
    # Gather dates
    scan_date_str = scan_result.get("scan_date")
    if not scan_date_str:
        ts = scan_result.get("cache_timestamp") or datetime.now().isoformat()
        scan_date_str = ts.split("T")[0]
        
    try:
        scan_date = datetime.strptime(scan_date_str, "%Y-%m-%d")
    except ValueError:
        scan_date = datetime.now()
        scan_date_str = scan_date.strftime("%Y-%m-%d")
        
    forecast_end = scan_date + timedelta(days=180)
    outcome_end = scan_date + timedelta(days=270)
    
    # Load cache entry for metadata
    try:
        from opportunistic_catalysts import _load_deep_scans_cache
        cache = _load_deep_scans_cache()
        cache_entry = cache.get(symbol, {})
    except Exception:
        cache_entry = {}
        
    ma_role = cache_entry.get("ma_role", {})
    credit_health = cache_entry.get("credit_health", {})
    spinoff_regime = cache_entry.get("spinoff_regime", {})
    
    # Extract expected catalyst summary
    expected_catalyst_summary = "General catalyst event"
    bloom_catalysts = scan_result.get("bloom_catalysts", {})
    if isinstance(bloom_catalysts, dict):
        for cat_val in bloom_catalysts.values():
            if isinstance(cat_val, dict) and cat_val.get("detected"):
                desc = cat_val.get("description")
                if desc:
                    expected_catalyst_summary = desc
                    break
    if expected_catalyst_summary == "General catalyst event":
        expected_catalyst_summary = (
            scan_result.get("catalyst_nature_rationale") or
            scan_result.get("analysis_summary", "")[:100] or
            "General event-driven catalyst"
        )
        
    expected_direction = "bear" if scan_result.get("recommendation") == "SELL" else "bull"
    
    entry = {
      "scan_id": scan_id,
      "symbol": symbol,
      "scan_date": scan_date_str,
      "raw_loeb_score": scan_result.get("catalyst_density_score", 0.0),
      "adjusted_loeb_score": scan_result.get("adjusted_loeb_score", scan_result.get("catalyst_density_score", 0.0)),
      "re_rate_status": scan_result.get("re_rate_status", "pending"),
      "ma_role": ma_role.get("role", "none") if ma_role else "none",
      "ma_deal_status": ma_role.get("deal_status", "none") if ma_role else "none",
      "credit_grade": credit_health.get("grade", "C") if credit_health else "C",
      "spinoff_regime": spinoff_regime.get("regime", "none") if spinoff_regime else "none",
      "catalyst_density_score": scan_result.get("catalyst_density_score", 0.0),
      "expected_catalyst_summary": expected_catalyst_summary,
      "expected_direction": expected_direction,
      "price_at_scan": scan_result.get("price", 0.0),
      "stock_currency": "USD",
      "forecast_window_end": forecast_end.strftime("%Y-%m-%d"),
      "outcome_window_end": outcome_end.strftime("%Y-%m-%d"),
      "outcome_recorded": False,
      "outcome_data": None,
      "schema_version": "1.0"
    }
    
    # Perform atomic read-modify-write
    for attempt in range(5):
        outcomes, generation = _load_outcomes(gcs_client)
        outcomes[scan_id] = entry
        if _save_outcomes(outcomes, generation, gcs_client):
            break
        import time
        time.sleep(0.1)
        
    return scan_id

def record_outcome(scan_id: str, outcome_data: dict, gcs_client=None) -> None:
    """
    Updates outcome fields for a scan that has reached its outcome_window_end.
    """
    for attempt in range(5):
        outcomes, generation = _load_outcomes(gcs_client)
        if scan_id in outcomes:
            outcomes[scan_id]["outcome_recorded"] = True
            outcomes[scan_id]["outcome_data"] = outcome_data
            if _save_outcomes(outcomes, generation, gcs_client):
                break
        else:
            log.warning(f"scan_id {scan_id} not found in outcomes.")
            break
        import time
        time.sleep(0.1)

def _calculate_stats(entries: list) -> dict:
    total_scans = len(entries)
    hits = 0
    misses = 0
    false_positives = 0
    noise_hits = 0
    pending = 0
    
    for entry in entries:
        if not entry.get("outcome_recorded"):
            pending += 1
            continue
            
        out_data = entry.get("outcome_data") or {}
        out_class = out_data.get("outcome_class")
        
        if out_class == "hit":
            hits += 1
        elif out_class == "miss":
            misses += 1
        elif out_class == "false_positive":
            false_positives += 1
        elif out_class == "noise_hit":
            noise_hits += 1
        else:
            pending += 1
            
    valid_count = hits + misses + false_positives
    if valid_count > 0:
        hit_rate_pct = (hits / valid_count) * 100.0
    else:
        hit_rate_pct = 0.0
        
    precision_denom = hits + noise_hits + false_positives
    if precision_denom > 0:
        precision_pct = (hits / precision_denom) * 100.0
    else:
        precision_pct = 0.0
        
    return {
        'total_scans': total_scans,
        'hits': hits,
        'misses': misses,
        'false_positives': false_positives,
        'noise_hits': noise_hits,
        'pending': pending,
        'hit_rate_pct': round(hit_rate_pct, 2),
        'precision_pct': round(precision_pct, 2)
    }

def compute_hit_rate_by_band(min_score: float, max_score: float, date_range: tuple, gcs_client=None) -> dict:
    outcomes, _ = _load_outcomes(gcs_client)
    iso_start, iso_end = date_range
    
    filtered_entries = []
    for entry in outcomes.values():
        score = entry.get("catalyst_density_score", 0.0)
        scan_date = entry.get("scan_date", "")
        if min_score <= score < max_score:
            if iso_start <= scan_date <= iso_end:
                filtered_entries.append(entry)
                
    return _calculate_stats(filtered_entries)

def compute_hit_rate_by_setup(filters: dict, gcs_client=None) -> dict:
    outcomes, _ = _load_outcomes(gcs_client)
    filtered_entries = []
    
    for entry in outcomes.values():
        match = True
        for key, val in filters.items():
            actual_val = entry.get(key)
            if actual_val != val:
                match = False
                break
        if match:
            filtered_entries.append(entry)
            
    return _calculate_stats(filtered_entries)
