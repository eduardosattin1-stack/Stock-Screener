#!/usr/bin/env python3
"""Quick validation: test Massive options snapshot for a symbol.
Usage: MASSIVE_API_KEY=xxx python backend/_test_massive.py AAPL
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("MASSIVE_API_KEY", "")

from massive_options import get_options_snapshot, enrich_stock, get_spot_price

sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
key = os.environ.get("MASSIVE_API_KEY", "")

print(f"=== Massive Options Validation for {sym} ===")
print(f"API Key set: {'YES (' + key[:8] + '...)' if key else 'NO — set MASSIVE_API_KEY'}")
if not key:
    sys.exit(1)

# Test 1: Spot price
print(f"\n--- Test 1: Spot Price ---")
spot = get_spot_price(sym)
print(f"  Spot: ${spot}" if spot else "  [X] No spot price")

# Test 2: Raw snapshot (first 3 contracts)
print(f"\n--- Test 2: Options Snapshot (sample) ---")
contracts = get_options_snapshot(sym, limit=10)
print(f"  Contracts returned: {len(contracts)}")
if contracts:
    c = contracts[0]
    print(f"  Sample contract:")
    print(f"    Type:       {c.get('details', {}).get('contract_type')}")
    print(f"    Strike:     {c.get('details', {}).get('strike_price')}")
    print(f"    Expiration: {c.get('details', {}).get('expiration_date')}")
    print(f"    IV:         {c.get('implied_volatility')}")
    print(f"    OI:         {c.get('open_interest')}")
    greeks = c.get("greeks", {})
    print(f"    Greeks:     Delta={greeks.get('delta')} Gamma={greeks.get('gamma')} "
          f"Theta={greeks.get('theta')} Vega={greeks.get('vega')}")
    q = c.get("last_quote", {})
    print(f"    Bid/Ask:    {q.get('bid')} / {q.get('ask')} (mid {q.get('midpoint')})")
    ua = c.get("underlying_asset", {})
    print(f"    Underlying: ${ua.get('price')}")
else:
    print("  [X] No contracts returned")

# Test 3: Full enrichment
print(f"\n--- Test 3: Full enrich_stock() ---")
data = enrich_stock(sym, composite=0.75, hit_prob=0.70)
print(f"  IV Current:   {data.get('iv_current')}")
print(f"  IV Rank:      {data.get('iv_rank')}")
print(f"  IV Samples:   {data.get('iv_samples')}")
print(f"  P/C (volume): {data.get('pc_ratio')}")
print(f"  P/C (OI):     {data.get('pc_oi_ratio')}  <- NEW (not available from Tradier)")
print(f"  Total OI:     {data.get('total_open_interest')}  <- NEW")
print(f"  IV 30d:       {data.get('iv_30d')}")
print(f"  IV 60d:       {data.get('iv_60d')}")
print(f"  IV 90d:       {data.get('iv_90d')}")
print(f"  Term Struct:  {data.get('term_structure')}")
print(f"  Earnings Move:{data.get('implied_earnings_move')}")

sp = data.get("spread")
if sp:
    print(f"\n  SPREAD:")
    print(f"    Strategy:  {sp.get('strategy')}")
    print(f"    Legs:      {sp.get('long_strike')}C / {sp.get('short_strike')}C")
    print(f"    Exp:       {sp.get('expiration')} ({sp.get('dte')}d)")
    print(f"    Debit:     ${sp.get('net_debit')}")
    print(f"    Max Gain:  ${sp.get('max_gain_per_contract')}/contract")
    print(f"    Max Loss:  ${sp.get('max_loss_per_contract')}/contract")
    print(f"    R/R:       {sp.get('risk_reward')}:1")
    print(f"    Break-even:${sp.get('break_even_price')} (+{sp.get('break_even_move_pct')}%)")
else:
    print(f"\n  [X] No spread built")

print(f"\n=== Done ===")
