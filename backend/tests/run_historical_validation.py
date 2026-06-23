#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timedelta

# Ensure backend directory is in the path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from historical_backfill import backfill_outcomes
from historical_tracker import compute_hit_rate_by_band, compute_hit_rate_by_setup

def run_validation():
    # 1. First, trigger the backfill to ensure we have data populated
    log_status = backfill_outcomes(cutoff_days=90)
    
    # 2. Compute date range (last 6 months)
    today = datetime.now()
    six_months_ago = today - timedelta(days=180)
    date_range = (six_months_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    
    # 3. Compute stats by band
    bands = [
        ("9.0-10.0", 9.0, 10.0),
        ("8.0-9.0", 8.0, 9.0),
        ("7.0-8.0", 7.0, 8.0),
        ("6.0-7.0", 6.0, 7.0),
        ("5.0-6.0", 5.0, 6.0),
    ]
    
    band_results = {}
    for name, low, high in bands:
        stats = compute_hit_rate_by_band(low, high, date_range)
        band_results[name] = stats
        
    # 4. Compute stats by re_rate_status
    statuses = ["pending", "partial", "complete"]
    status_results = {}
    for status in statuses:
        stats = compute_hit_rate_by_setup({"re_rate_status": status})
        status_results[status] = stats
        
    # 5. Compute stats by M&A Role (Path A data only)
    roles = ["target", "acquirer", "none"]
    role_results = {}
    for role in roles:
        stats = compute_hit_rate_by_setup({"ma_role": role})
        role_results[role] = stats
        
    # 6. Compute stats by Credit Grade (Path A data only)
    grades = ["A", "B", "C", "D", "F"]
    grade_results = {}
    for grade in grades:
        stats = compute_hit_rate_by_setup({"credit_grade": grade})
        grade_results[grade] = stats
        
    # 7. Print markdown report
    print("## Historical Hit Rate by Loeb Score Band (last 6 months)\n")
    print("| Score Band | Total | Hits | Misses | FPs | Noise | Hit Rate | Precision |")
    print("|---|---|---|---|---|---|---|---|")
    for name, _, _ in bands:
        res = band_results[name]
        print(f"| {name} | {res['total_scans']} | {res['hits']} | {res['misses']} | {res['false_positives']} | {res['noise_hits']} | {res['hit_rate_pct']:.1f}% | {res['precision_pct']:.1f}% |")
        
    print("\n## Hit Rate by re_rate_status\n")
    print("| Status | Total | Hit Rate |")
    print("|---|---|---|")
    for status in statuses:
        res = status_results[status]
        print(f"| {status} | {res['total_scans']} | {res['hit_rate_pct']:.1f}% |")
        
    print("\n## Hit Rate by M&A Role (Path A data only — limited sample)\n")
    print("| Role | Total | Hit Rate |")
    print("|---|---|---|")
    for role in roles:
        res = role_results[role]
        print(f"| {role} | {res['total_scans']} | {res['hit_rate_pct']:.1f}% |")
        
    print("\n## Hit Rate by Credit Grade (Path A data only — limited sample)\n")
    print("| Grade | Total | Hit Rate |")
    print("|---|---|---|")
    for grade in grades:
        res = grade_results[grade]
        print(f"| {grade} | {res['total_scans']} | {res['hit_rate_pct']:.1f}% |")
        
    # 8. Detect anomalies
    anomalies = []
    # Compare each band with the one below it
    for idx in range(len(bands) - 1):
        upper_name, _, _ = bands[idx]
        lower_name, _, _ = bands[idx+1]
        
        upper_hr = band_results[upper_name]["hit_rate_pct"]
        lower_hr = band_results[lower_name]["hit_rate_pct"]
        
        # Only flag if there are valid scans to make comparison meaningful
        if band_results[upper_name]["total_scans"] - band_results[upper_name]["pending"] > 0 and band_results[lower_name]["total_scans"] - band_results[lower_name]["pending"] > 0:
            if upper_hr < lower_hr:
                anomalies.append(
                    f"*{upper_name}* band shows {upper_hr:.1f}% hit rate but *{lower_name}* band shows {lower_hr:.1f}% — overconfidence at top scores"
                )
                
    print("\n## [!] Anomalies / Calibration Flags\n")
    if anomalies:
        for anomaly in anomalies:
            print(f"- {anomaly}")
        print("\n*This is exactly the miscalibration Path C is designed to fix.*")
    else:
        print("No score-band inversion detected in current data.")

if __name__ == "__main__":
    run_validation()
