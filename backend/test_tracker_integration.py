#!/usr/bin/env python3
"""
test_tracker_integration.py
===========================
Integration tests for signal_tracker.py, verifying both 30-day and 60-day
regimes, state transitions, options spread EV calculations, rolling health
computations, and offline GCS helper robustness.
"""

import os
import json
import logging
from datetime import datetime, timedelta
import signal_tracker

# Setup logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TrackerTest")

# ---------------------------------------------------------------------------
# In-Memory GCS Mock
# ---------------------------------------------------------------------------
gcs_mock_bucket = {}

def mock_gcs_read(path: str, default):
    if path in gcs_mock_bucket:
        log.info(f"[MOCK GCS READ] {path} (HIT)")
        return json.loads(json.dumps(gcs_mock_bucket[path]))
    log.info(f"[MOCK GCS READ] {path} (MISS, default returned)")
    return default

def mock_gcs_read_text(path: str, default: str = "") -> str:
    if path in gcs_mock_bucket:
        log.info(f"[MOCK GCS READ TEXT] {path} (HIT)")
        return gcs_mock_bucket[path]
    log.info(f"[MOCK GCS READ TEXT] {path} (MISS, default returned)")
    return default

def mock_gcs_write(path: str, data, content_type: str = "application/json") -> bool:
    log.info(f"[MOCK GCS WRITE] {path}")
    if isinstance(data, str):
        gcs_mock_bucket[path] = data
    else:
        gcs_mock_bucket[path] = json.loads(json.dumps(data, default=str))
    return True

# Save original methods for robustness tests
orig_read = signal_tracker._gcs_read
orig_read_text = signal_tracker._gcs_read_text
orig_write = signal_tracker._gcs_write

def apply_mocks():
    signal_tracker._gcs_read = mock_gcs_read
    signal_tracker._gcs_read_text = mock_gcs_read_text
    signal_tracker._gcs_write = mock_gcs_write

def remove_mocks():
    signal_tracker._gcs_read = orig_read
    signal_tracker._gcs_read_text = orig_read_text
    signal_tracker._gcs_write = orig_write


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------
def run_tests():
    log.info("Starting signal_tracker integration tests...")

    # Override tracking configuration to match the integration test scenario
    signal_tracker.CYCLE_LENGTH_DAYS = 30
    signal_tracker.HIT_WINDOW_DAYS = 28

    # Also override Regime parameters to match the test scenario
    signal_tracker.REGIME_60D.cycle_length_days = 30
    signal_tracker.REGIME_60D.synth_dte_days = 60
    signal_tracker.REGIME_60D.hit_window_days = 60
    signal_tracker.REGIME_60D.synth_long_offset = 0.05
    signal_tracker.REGIME_60D.synth_short_offset = 0.20

    signal_tracker.REGIME_30D_P10.cycle_length_days = 30
    signal_tracker.REGIME_30D_P10.synth_dte_days = 30
    signal_tracker.REGIME_30D_P10.hit_window_days = 28
    signal_tracker.REGIME_30D_P10.synth_long_offset = 0.025
    signal_tracker.REGIME_30D_P10.synth_short_offset = 0.10

    # =======================================================================
    # Test Phase 1: Offline GCS Helper Robustness
    # =======================================================================
    log.info("\n--- Phase 1: Testing GCS helper methods offline behavior ---")
    remove_mocks()
    
    # Set offline env vars to force local fallback
    os.environ["FMP_OFFLINE"] = "YES"
    
    # Save original _gcs_token and mock it to return None to simulate offline/no-token environment
    orig_token = signal_tracker._gcs_token
    signal_tracker._gcs_token = lambda: None
    
    try:
        # These should fail gracefully returning default/False rather than raising exceptions
        res_read = signal_tracker._gcs_read("nonexistent_path_test_123.json", {"fallback": True})
        assert res_read == {"fallback": True}, f"Expected default fallback, got {res_read}"
        
        res_read_text = signal_tracker._gcs_read_text("nonexistent_path_test_123.txt", "fallback_text")
        assert res_read_text == "fallback_text", f"Expected default fallback text, got {res_read_text}"
        
        res_write = signal_tracker._gcs_write("nonexistent_path_test_123.json", {"test": 1})
        assert res_write is False, f"Expected write to return False when offline, got {res_write}"
        
        log.info("✅ Phase 1 passed: GCS helper methods handled offline mode gracefully.")
    finally:
        # Clean up env and restore original token method
        signal_tracker._gcs_token = orig_token
        os.environ.pop("FMP_OFFLINE", None)
        apply_mocks()

    # =======================================================================
    # Test Phase 2: 30-Day Regime Prediction Cycle
    # =======================================================================
    log.info("\n--- Phase 2: Testing 30-Day Regime Prediction & Outcome (HIT) ---")
    gcs_mock_bucket.clear()

    # 1. First scan on Day 1 (2026-05-01): AAPL qualifies for 30d regime
    stocks_day1 = [
        {
            "symbol": "AAPL",
            "price": 100.0,
            "hit_prob": 0.75,  # Decile 10 (>=0.66824 under new 30d thresholds)
            "options_iv_current": 0.30,
            "options_iv_rank": 50,
            "expected_dd_30d": 5.2,
            "composite": 8.0,
            "signal": "STRONG_BUY",
            "sector": "Technology",
            "country": "US"
        }
    ]

    signal_tracker.update_from_scan(stocks_day1, region="sp500", scan_date="2026-05-01")

    # Verify cycle state
    state = gcs_mock_bucket.get(signal_tracker.REGIME_30D_P10.pointer_path)
    assert state is not None, "Cycle pointer state file not written!"
    assert state["collecting_cycle_id"] == "2026-05-01", f"Expected cycle 2026-05-01, got {state['collecting_cycle_id']}"
    assert state["collecting_ends"] == "2026-05-31", f"Expected cycle end 2026-05-31, got {state['collecting_ends']}"

    # Verify open.json contains AAPL with correct 30-day fields
    open_json_path = f"hit_rate_tracking/cycles_30d/2026-05-01/open.json"
    open_data = gcs_mock_bucket.get(open_path := open_json_path)
    assert open_data is not None, "open.json not written!"
    assert len(open_data["predictions"]) == 1, "Expected 1 active prediction"
    
    pred = open_data["predictions"][0]
    assert pred["symbol"] == "AAPL"
    assert pred["regime"] == "30d"
    assert pred["decile"] == 10
    assert pred["signal_strength"] == "STRONG"
    assert pred["hit_window_days"] == 28
    assert pred["expected_dd"] == 5.2
    assert "ev_dollars" in pred, "Spread EV calculation block missing"
    assert pred["outcome"] == "OPEN"

    # Verify predictions.jsonl
    predictions_jsonl_path = f"hit_rate_tracking/cycles_30d/2026-05-01/predictions.jsonl"
    jsonl_content = gcs_mock_bucket.get(predictions_jsonl_path, "")
    assert "AAPL" in jsonl_content
    lines = [json.loads(line) for line in jsonl_content.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["outcome"] == "OPEN"

    # 2. Second scan on Day 15 (2026-05-15): AAPL hits +20% target (target price is 110.0, spot becomes 122.0)
    stocks_day15 = [
        {
            "symbol": "AAPL",
            "price": 122.0,
            "hit_prob": 0.15,
            "options_iv_current": 0.28,
            "options_iv_rank": 40,
            "composite": 7.5,
            "signal": "BUY"
        }
    ]

    signal_tracker.update_from_scan(stocks_day15, region="sp500", scan_date="2026-05-15")

    # AAPL should be closed as HIT, open.json should be empty
    open_data = gcs_mock_bucket.get(open_json_path)
    assert len(open_data["predictions"]) == 0, "AAPL prediction should have closed"

    # Verify predictions.jsonl has the close row (HIT)
    jsonl_content = gcs_mock_bucket.get(predictions_jsonl_path, "")
    lines = [json.loads(line) for line in jsonl_content.splitlines() if line.strip()]
    assert len(lines) == 2, "Expected 2 rows in jsonl (1 open, 1 close)"
    assert lines[0]["outcome"] == "OPEN"
    assert lines[1]["outcome"] == "HIT"
    assert lines[1]["realized_return_pct"] == 22.0
    assert lines[1]["resolution_date"] == "2026-05-15"

    log.info("✅ Phase 2 passed: 30-Day Regime prediction correctly initialized, updated, and resolved (HIT).")

    # =======================================================================
    # Test Phase 3: 60-Day Regime Prediction Cycle (EXPIRED)
    # =======================================================================
    log.info("\n--- Phase 3: Testing 60-Day Regime Prediction & Outcome (EXPIRED) ---")

    # 1. Scan on Day 32 (2026-06-02): advances cycle, MSFT qualifies for 60d regime
    stocks_day32 = [
        {
            "symbol": "MSFT",
            "price": 300.0,
            "hit_prob_60d": 0.60,  # Decile 10 (>=0.57808)
            "options_iv_current": 0.25,
            "options_iv_rank": 35,
            "expected_dd_60d": 8.5,
            "composite": 9.0,
            "signal": "STRONG_BUY",
            "sector": "Technology",
            "country": "US"
        }
    ]

    # This scan should advance the cycle because 2026-06-02 >= 2026-05-31 (collecting ends)
    signal_tracker.update_from_scan(stocks_day32, region="sp500", scan_date="2026-06-02")

    # Verify cycle state advanced
    state = gcs_mock_bucket.get(signal_tracker.CYCLE_POINTER_PATH)
    assert state["collecting_cycle_id"] == "2026-06-02", f"Expected new cycle, got {state['collecting_cycle_id']}"
    assert "2026-05-01" not in state["resolving_cycle_ids"], "Old cycle should not be in resolving list since it got archived"
    
    # Verify 2026-05-01 cycle is archived because its open.json was empty
    assert "2026-05-01" in state["archived_cycle_ids"], "Old cycle should be archived"
    archive_data = gcs_mock_bucket.get(f"hit_rate_tracking/cycles/2026-05-01/archived.json")
    assert archive_data is not None, "Archive file not written"
    assert archive_data["total_predictions"] == 1
    assert archive_data["hit_rate"] == 1.0
    assert archive_data["calibration_check"]["healthy"] is False  # Under-sampled (n < 5)

    # Verify MSFT in open.json for cycle 2026-06-02
    open_json_path_60d = f"hit_rate_tracking/cycles/2026-06-02/open.json"
    open_data_60d = gcs_mock_bucket.get(open_json_path_60d)
    assert open_data_60d is not None
    assert len(open_data_60d["predictions"]) == 1
    
    pred_msft = open_data_60d["predictions"][0]
    assert pred_msft["symbol"] == "MSFT"
    assert pred_msft["regime"] == "60d"
    assert pred_msft["decile"] == 10
    assert pred_msft["signal_strength"] == "STRONG"
    assert pred_msft["hit_window_days"] == 60
    assert pred_msft["expected_dd"] == 8.5
    assert pred_msft["dte"] == 60
    assert pred_msft["short_strike"] == 375.0  # Spot 300 * 1.25 = 375 (optimizing EV via grid search)
    assert pred_msft["outcome"] == "OPEN"

    # 2. Update scan on Day 95 (2026-08-05): MSFT is now flat at 310.0 (expired after 64 days > 60 days window)
    stocks_day95 = [
        {
            "symbol": "MSFT",
            "price": 310.0,
            "hit_prob_60d": 0.50,
            "options_iv_current": 0.24,
            "options_iv_rank": 30,
            "composite": 8.0,
            "signal": "BUY"
        }
    ]

    signal_tracker.update_from_scan(stocks_day95, region="sp500", scan_date="2026-08-05")

    # MSFT should be expired and closed
    open_data_60d = gcs_mock_bucket.get(open_json_path_60d)
    assert len(open_data_60d["predictions"]) == 0, "MSFT prediction should have expired and closed"

    # Verify predictions.jsonl has the EXPIRED row
    predictions_jsonl_path_60d = f"hit_rate_tracking/cycles/2026-06-02/predictions.jsonl"
    jsonl_content_60d = gcs_mock_bucket.get(predictions_jsonl_path_60d, "")
    lines_60d = [json.loads(line) for line in jsonl_content_60d.splitlines() if line.strip()]
    assert len(lines_60d) == 2, "Expected 2 rows in 60d cycle jsonl"
    assert lines_60d[1]["outcome"] == "EXPIRED"
    assert lines_60d[1]["realized_return_pct"] == 3.3333  # (310-300)/300 * 100
    assert lines_60d[1]["resolution_date"] == "2026-08-05"

    log.info("✅ Phase 3 passed: 60-Day Regime prediction correctly advanced cycles, resolved as EXPIRED.")

    # =======================================================================
    # Test Phase 4: Rolling Health and Kill Switch Trigger
    # =======================================================================
    log.info("\n--- Phase 4: Testing Rolling Health and Kill Switch Trigger ---")
    gcs_mock_bucket.clear()

    # Reset current cycle pointer
    state = {
        "collecting_cycle_id": "2026-05-01",
        "collecting_start": "2026-05-01",
        "collecting_ends": "2026-05-31",
        "resolving_cycle_ids": [],
        "archived_cycle_ids": []
    }
    mock_gcs_write(signal_tracker.CYCLE_POINTER_PATH, state)

    # Let's write a mock predictions.jsonl with 10 predictions in Decile 10.
    # To trigger the kill-switch, we need:
    # 1. Dominant regime is 60d (so count_60d > total_in_window/2).
    # 2. Number of D10 predictions >= 10.
    # 3. D10 hit rate < 40% (for 60d regime threshold). Let's do 3 hits out of 10 (30% hit rate).
    
    mock_preds = []
    # 3 Hits
    for i in range(3):
        mock_preds.append({
            "symbol": f"S_HIT_{i}", "entry_date": "2026-05-10", "cycle_id": "2026-05-01", "regime": "60d",
            "decile": 10, "hit_window_days": 60, "outcome": "HIT", "max_high_observed_pct": 25.0
        })
    # 7 Expired
    for i in range(7):
        mock_preds.append({
            "symbol": f"S_EXP_{i}", "entry_date": "2026-05-10", "cycle_id": "2026-05-01", "regime": "60d",
            "decile": 10, "hit_window_days": 60, "outcome": "EXPIRED", "max_high_observed_pct": 5.0
        })

    jsonl_str = "\n".join(json.dumps(p) for p in mock_preds) + "\n"
    mock_gcs_write(f"hit_rate_tracking/cycles/2026-05-01/predictions.jsonl", jsonl_str)

    # Trigger a scan update to recalculate health
    stocks_dummy = [{"symbol": "TEST", "price": 10.0, "hit_prob_60d": 0.10}]
    signal_tracker.update_from_scan(stocks_dummy, region="sp500", scan_date="2026-07-20")

    # Read rolling health
    health = gcs_mock_bucket.get(signal_tracker.ROLLING_HEALTH_PATH)
    assert health is not None, "Rolling health file not written!"
    assert health["d10_n"] == 10, f"Expected 10 D10 samples, got {health['d10_n']}"
    assert health["d10_hits"] == 3, f"Expected 3 D10 hits, got {health['d10_hits']}"
    assert health["d10_hit_rate"] == 0.30, f"Expected 30% hit rate, got {health['d10_hit_rate']}"
    assert health["kill_switch_active"] is True, "Kill switch should be active"
    assert health["status"] == "DEGRADED", f"Expected DEGRADED status, got {health['status']}"

    log.info("✅ Phase 4 passed: Rolling Health correctly detected dominant regime, computed D10 stats, and activated Kill Switch.")

    print("\n" + "="*80)
    print("ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("="*80 + "\n")


if __name__ == "__main__":
    run_tests()
