#!/usr/bin/env python3
"""Read-only smoke test of the calibration-v2 activation path.

Exercises exactly what the nightly job does for activation, with NO GCS writes:
  1. get_theta_client() from env THETA_EMAIL/THETA_PASSWORD (the path that
     failed on 2026-06-11 because THETA_PASSWORD was unset in the job).
  2. _fetch_eod_bars(sym, scan_date, scan_date) for a few real pending symbols.
  3. The same bar-matching predicate _activate_pending_entries uses
     (bar["date"] == scan_date) -> prints the would-be entry price.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration_tracker as ct

SCAN_DATE = "2026-06-11"
SYMBOLS = ["ACAD", "ACHR", "NVDA"]

print(f"env THETA_EMAIL set:    {bool(os.environ.get('THETA_EMAIL'))}")
print(f"env THETA_PASSWORD set: {bool(os.environ.get('THETA_PASSWORD'))}")

print("\n[1/2] get_theta_client() ...")
theta = ct.get_theta_client()
print(f"      OK -> {type(theta).__name__}")

print(f"\n[2/2] EOD bar for scan_date {SCAN_DATE} (activation predicate: bar.date == scan_date)")
failures = 0
for sym in SYMBOLS:
    bars = ct._fetch_eod_bars(theta, sym, SCAN_DATE, SCAN_DATE)
    bar = next((b for b in bars if b.get("date") == SCAN_DATE), None)
    if bar:
        print(f"      {sym:6s} OK   close={bar['close']:.2f}  high={bar['high']:.2f}  low={bar['low']:.2f}  -> would activate at {bar['close']:.2f}")
    else:
        failures += 1
        print(f"      {sym:6s} FAIL no {SCAN_DATE} bar (got {len(bars)} bars: {[b['date'] for b in bars]})")

print()
if failures:
    print(f"SMOKE TEST FAILED: {failures}/{len(SYMBOLS)} symbols missing the scan-date bar")
    sys.exit(1)
print("SMOKE TEST PASSED: credentials valid, scan-date EOD bars available, activation will fire tonight")
