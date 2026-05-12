#!/usr/bin/env python3
"""Diagnostic: trace why tradier_spread is always None.
Run: python backend/_diag_tradier_spread.py AAPL
Requires TRADIER_TOKEN in environment."""
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

from tradier_options import (
    TRADIER_TOKEN, DTE_TARGET, DTE_TOLERANCE,
    get_quote, get_expirations, get_chain,
    _pick_expiration, _pick_strikes, _spread_economics, _extract_atm_iv,
    enrich_stock,
)
from datetime import datetime

sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

print(f"=== Tradier spread diagnostic for {sym} ===")
print(f"TRADIER_TOKEN set: {'YES (' + TRADIER_TOKEN[:6] + '...)' if TRADIER_TOKEN else 'NO'}")
print(f"DTE_TARGET={DTE_TARGET}, DTE_TOLERANCE={DTE_TOLERANCE}")
print(f"Acceptable DTE range: {DTE_TARGET - DTE_TOLERANCE}–{DTE_TARGET + DTE_TOLERANCE}")
print()

if not TRADIER_TOKEN:
    print("ERROR: TRADIER_TOKEN not set. Set it and retry.")
    sys.exit(1)

# Step 1: Quote
print("--- Step 1: Quote ---")
q = get_quote(sym)
if not q:
    print("  FAIL: no quote")
    sys.exit(1)
spot = float(q.get("last", 0))
print(f"  spot = ${spot:.2f}")

# Step 2: Expirations
print("\n--- Step 2: Expirations ---")
exps = get_expirations(sym)
print(f"  {len(exps)} expirations available")
today = datetime.now().date()
for e in exps[:12]:
    try:
        d = datetime.strptime(e, "%Y-%m-%d").date()
        dte = (d - today).days
        in_window = abs(dte - DTE_TARGET) <= DTE_TOLERANCE
        marker = " <<<< IN WINDOW" if in_window else ""
        print(f"  {e}  (DTE {dte:3d}, diff from target={abs(dte - DTE_TARGET):2d}){marker}")
    except Exception:
        print(f"  {e}  (parse error)")

# Step 3: Pick expiration
print("\n--- Step 3: _pick_expiration ---")
chosen_exp = _pick_expiration(exps)
print(f"  chosen_exp = {chosen_exp}")
if not chosen_exp:
    print("  FAIL: No expiration in window! This is why spread is None.")
    print(f"  Fix: widen DTE_TOLERANCE or adjust DTE_TARGET")
    sys.exit(1)

# Step 4: Chain
print(f"\n--- Step 4: Chain for {chosen_exp} ---")
chain = get_chain(sym, chosen_exp)
print(f"  chain has {len(chain)} contracts")
calls = [o for o in chain if o.get("option_type") == "call"]
puts = [o for o in chain if o.get("option_type") == "put"]
print(f"  calls: {len(calls)}, puts: {len(puts)}")

calls_with_strike = [o for o in chain if o.get("option_type") == "call" and o.get("strike")]
print(f"  calls with 'strike' field: {len(calls_with_strike)}")

if calls:
    strikes_list = sorted([float(c["strike"]) for c in calls if c.get("strike")])
    print(f"  call strike range: ${min(strikes_list):.0f} – ${max(strikes_list):.0f}")
    print(f"  ATM target: ${spot:.2f}")
    print(f"  Short target (+10%): ${spot * 1.10:.2f}")

# Step 5: IV extraction
print(f"\n--- Step 5: IV extraction ---")
iv = _extract_atm_iv(chain, spot)
print(f"  ATM IV = {iv}")

# Step 6: Pick strikes
print(f"\n--- Step 6: _pick_strikes ---")
strikes = _pick_strikes(chain, spot)
if not strikes:
    print("  FAIL: _pick_strikes returned None!")
    # Debug why
    if len(calls_with_strike) < 2:
        print(f"  Reason: fewer than 2 calls with strike ({len(calls_with_strike)})")
    else:
        long_target = spot
        short_target = spot * 1.10
        long_call = min(calls_with_strike, key=lambda o: abs(float(o["strike"]) - long_target))
        short_call = min(calls_with_strike, key=lambda o: abs(float(o["strike"]) - short_target))
        print(f"  long_call strike: {long_call['strike']} (target: {long_target:.2f})")
        print(f"  short_call strike: {short_call['strike']} (target: {short_target:.2f})")
        if float(long_call["strike"]) >= float(short_call["strike"]):
            print(f"  Reason: long >= short ({long_call['strike']} >= {short_call['strike']})")
            print(f"  Both selectors picked the same contract or long is higher")
    sys.exit(1)

print(f"  long: ${strikes['long']['strike']} call")
print(f"  short: ${strikes['short']['strike']} call")

# Step 7: Economics
print(f"\n--- Step 7: Spread economics ---")
econ = _spread_economics(strikes["long"], strikes["short"], spot)
for k, v in econ.items():
    print(f"  {k}: {v}")

# Step 8: Full enrich_stock
print(f"\n--- Step 8: Full enrich_stock ---")
result = enrich_stock(sym, 0.70, 0.05)
if result.get("spread"):
    print("  SUCCESS: spread is populated!")
    for k, v in result["spread"].items():
        print(f"    {k}: {v}")
else:
    print("  FAIL: spread is still None after full enrich_stock")
    print(f"  iv_current: {result.get('iv_current')}")
    print(f"  iv_rank: {result.get('iv_rank')}")
    print(f"  iv_samples: {result.get('iv_samples')}")

print("\n=== Done ===")
