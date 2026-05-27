#!/usr/bin/env python3
import os
import sys
import json
import logging
import shutil

# Ensure backend directory is in the path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Copy deep_scans_cache.json to deep_scans_cache_test.json before importing opportunistic_catalysts
# so it has all the control entries available in the sandbox.
src_cache = os.path.join(backend_dir, "deep_scans_cache.json")
dst_cache = os.path.join(backend_dir, "deep_scans_cache_test.json")
if os.path.exists(src_cache):
    shutil.copy(src_cache, dst_cache)

import opportunistic_catalysts
# Override the global cache path in opportunistic_catalysts to use the test sandboxed cache
opportunistic_catalysts.DEEP_SCANS_CACHE = dst_cache

from opportunistic_catalysts import run_catalyst_scan, _load_deep_scans_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Regression-Runner")

GRADE_MAP = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

def run_tests():
    fixture_path = os.path.join(os.path.dirname(__file__), "regression_fixture.json")
    if not os.path.exists(fixture_path):
        log.error(f"Fixture not found at {fixture_path}")
        return False
        
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)
        
    log.info(f"Running regression test suite version {fixture.get('fixture_version')}")
    
    passed_count = 0
    failed_count = 0
    failures = []
    
    # 1. Run this_week_names
    for entry in fixture.get("this_week_names", []):
        symbol = entry["symbol"]
        expected = entry.get("expected_after_path_a")
        if not expected:
            log.info(f"Skipping {symbol} - no Path A expectations specified.")
            continue
            
        log.info(f"Scanning {symbol} (this_week)...")
        try:
            # Force refresh to compute fresh detector values and update cache
            result = run_catalyst_scan(symbol, force_refresh=True)
            
            # Load cache entry to inspect cached metadata
            cache = _load_deep_scans_cache()
            cache_entry = cache.get(symbol.upper(), {})
            
            # Perform assertions
            item_failures = []
            
            # raw_loeb_max
            if "raw_loeb_max" in expected:
                actual = result.get("catalyst_density_score", 0.0)
                limit = expected["raw_loeb_max"]
                if actual > limit:
                    item_failures.append(f"catalyst_density_score {actual} exceeds max limit {limit}")
                    
            # raw_loeb_min
            if "raw_loeb_min" in expected:
                actual = result.get("catalyst_density_score", 0.0)
                limit = expected["raw_loeb_min"]
                if actual < limit:
                    item_failures.append(f"catalyst_density_score {actual} is below min limit {limit}")
                    
            # re_rate_status
            if "re_rate_status" in expected:
                actual = result.get("re_rate_status")
                expected_val = expected["re_rate_status"]
                if actual != expected_val:
                    item_failures.append(f"re_rate_status '{actual}' != '{expected_val}'")
                    
            # ma_role
            if "ma_role" in expected:
                actual = cache_entry.get("ma_role", {}).get("role", "none")
                expected_val = expected["ma_role"]
                if actual != expected_val:
                    item_failures.append(f"ma_role '{actual}' != '{expected_val}'")
                    
            # ma_deal_status
            if "ma_deal_status" in expected:
                actual = cache_entry.get("ma_role", {}).get("deal_status", "none")
                expected_val = expected["ma_deal_status"]
                if actual != expected_val:
                    item_failures.append(f"ma_deal_status '{actual}' != '{expected_val}'")
                    
            # ma_counterparty
            if "ma_counterparty" in expected:
                actual = cache_entry.get("ma_role", {}).get("counterparty")
                expected_val = expected["ma_counterparty"]
                if actual != expected_val:
                    item_failures.append(f"ma_counterparty '{actual}' != '{expected_val}'")
                    
            # acquirer_cap_applied
            if "acquirer_cap_applied" in expected:
                actual = result.get("acquirer_cap_applied", False)
                expected_val = expected["acquirer_cap_applied"]
                if actual != expected_val:
                    item_failures.append(f"acquirer_cap_applied {actual} != {expected_val}")
                    
            # merger_arb_cap_applied
            if "merger_arb_cap_applied" in expected:
                actual = result.get("merger_arb_cap_applied", False)
                expected_val = expected["merger_arb_cap_applied"]
                if actual != expected_val:
                    item_failures.append(f"merger_arb_cap_applied {actual} != {expected_val}")
                    
            # catalyst_fired
            if "catalyst_fired" in expected:
                actual = result.get("catalyst_fired", False)
                expected_val = expected["catalyst_fired"]
                if actual != expected_val:
                    item_failures.append(f"catalyst_fired {actual} != {expected_val}")
                    
            # spinoff_regime
            if "spinoff_regime" in expected:
                actual = cache_entry.get("spinoff_regime", {}).get("regime", "none")
                expected_val = expected["spinoff_regime"]
                if actual != expected_val:
                    item_failures.append(f"spinoff_regime '{actual}' != '{expected_val}'")
                    
            # catalyst_nature
            if "catalyst_nature" in expected:
                actual = result.get("catalyst_nature")
                expected_val = expected["catalyst_nature"]
                if actual != expected_val:
                    item_failures.append(f"catalyst_nature '{actual}' != '{expected_val}'")
                    
            # credit_grade
            if "credit_grade" in expected:
                actual = cache_entry.get("credit_health", {}).get("grade", "C")
                expected_val = expected["credit_grade"]
                if actual != expected_val:
                    item_failures.append(f"credit_grade '{actual}' != '{expected_val}'")
                    
            # credit_grade_min
            if "credit_grade_min" in expected:
                actual = cache_entry.get("credit_health", {}).get("grade", "C")
                min_grade = expected["credit_grade_min"]
                if GRADE_MAP.get(actual, 0) < GRADE_MAP.get(min_grade, 0):
                    item_failures.append(f"credit_grade '{actual}' is lower than min required '{min_grade}'")
                    
            # credit_distress_flags_min
            if "credit_distress_flags_min" in expected:
                actual_flags = cache_entry.get("credit_health", {}).get("distress_flags", [])
                for flag in expected["credit_distress_flags_min"]:
                    if flag not in actual_flags:
                        item_failures.append(f"Expected credit distress flag '{flag}' not found in actual flags {actual_flags}")
                        
            if item_failures:
                failed_count += 1
                failures.append(f"{symbol} failed: " + "; ".join(item_failures))
                log.error(f"FAIL: {symbol}")
                for fail in item_failures:
                    log.error(f"  - {fail}")
            else:
                passed_count += 1
                log.info(f"PASS: {symbol} met all Path A criteria.")
                
        except Exception as e:
            failed_count += 1
            failures.append(f"{symbol} raised exception: {e}")
            log.error(f"FAIL: {symbol} due to exception: {e}", exc_info=True)
            
    # 2. Run control_names
    for entry in fixture.get("control_names", []):
        symbol = entry["symbol"]
        old_score = entry["current_raw_loeb"]
        tolerance = entry.get("drift_tolerance", 0.5)
        
        log.info(f"Scanning {symbol} (control)...")
        try:
            result = run_catalyst_scan(symbol, force_refresh=False)
            new_score = result.get("catalyst_density_score", 0.0)
            drift = abs(new_score - old_score)
            
            if drift > tolerance:
                failed_count += 1
                failures.append(f"Control {symbol} drifted by {drift:.2f} (from {old_score} to {new_score}), exceeding tolerance {tolerance}")
                log.error(f"FAIL: Control {symbol} drifted too much (drift={drift:.2f}, limit={tolerance})")
            else:
                passed_count += 1
                log.info(f"PASS: Control {symbol} drift is acceptable (drift={drift:.2f}, limit={tolerance})")
                
        except Exception as e:
            failed_count += 1
            failures.append(f"Control {symbol} raised exception: {e}")
            log.error(f"FAIL: Control {symbol} due to exception: {e}", exc_info=True)
            
    # Print summary
    print("\n" + "="*50)
    print("REGRESSION TEST RESULTS SUMMARY")
    print("="*50)
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print(f"Total:  {passed_count + failed_count}")
    print("="*50)
    
    if failed_count > 0:
        print("\nFailures Detail:")
        for fail in failures:
            print(f"- {fail}")
        return False
        
    print("\nALL PATH A CRITERIA PASSED SUCCESSFULLY!")
    
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
