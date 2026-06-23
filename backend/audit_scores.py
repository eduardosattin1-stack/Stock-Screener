#!/usr/bin/env python3
"""
Loeb Scoring Audit — Programmatic audit of cached deep scan scores.

Reads deep_scans_cache.json and latest_global.json (from GCS if local is empty),
cross-references scores with market data, and flags anomalies.

Usage:  python audit_scores.py
"""

import json
import os
import sys

# Add backend to path for importing compute_confidence_adjusted_score
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from opportunistic_catalysts import compute_confidence_adjusted_score


def load_deep_scans_cache():
    path = os.path.join(BACKEND_DIR, "deep_scans_cache.json")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_latest_global():
    """Load stock data from local or GCS."""
    # Try local files first
    for filename in ["latest_global.json", "latest.json"]:
        path = os.path.join(BACKEND_DIR, "..", "frontend", "public", filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            stocks = data.get("stocks", [])
            if stocks:
                return {s["symbol"]: s for s in stocks if s.get("symbol")}
    
    # Try GCS
    try:
        import requests
        for gcs_path in ["scans/latest_global.json", "scans/latest.json"]:
            url = f"https://storage.googleapis.com/screener-signals-carbonbridge/{gcs_path}"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                stocks = data.get("stocks", [])
                if stocks:
                    print(f"  Loaded {len(stocks)} stocks from GCS: {gcs_path}")
                    return {s["symbol"]: s for s in stocks if s.get("symbol")}
    except Exception as e:
        print(f"  GCS fetch failed: {e}")
    
    return {}


def run_audit():
    print("=" * 72)
    print("  LOEB SCORING AUDIT — Confidence-Adjusted Score Analysis")
    print("=" * 72)
    print()

    # Load data
    print("[1/3] Loading deep scans cache...")
    cache = load_deep_scans_cache()
    print(f"  {len(cache)} stocks in cache")

    print("[2/3] Loading latest global scan data...")
    global_data = load_latest_global()
    print(f"  {len(global_data)} stocks in global scan")

    print("[3/3] Running audit...\n")

    # Audit results
    results = []
    false_positives = []
    hidden_gems = []
    re_rate_mismatches = []
    matched = 0
    unmatched = 0

    for sym, entry in cache.items():
        cached_data = entry.get("data", {})
        raw_score = cached_data.get("catalyst_density_score")
        if raw_score is None:
            continue

        # Get market data from global scan
        stock_data = global_data.get(sym, {})
        if not stock_data:
            unmatched += 1
            # Still compute with empty stock_data (adjustments will be minimal)
            stock_data = {}

        matched += 1

        # Compute adjusted score
        adj = compute_confidence_adjusted_score(
            symbol=sym,
            raw_score=raw_score,
            stock_data=stock_data,
            cached_scan=cached_data,
        )

        adjusted = adj["adjusted_loeb_score"]
        adjustments = adj["score_adjustments"]
        divergence = adjusted - raw_score

        result = {
            "symbol": sym,
            "raw_score": raw_score,
            "adjusted_score": adjusted,
            "divergence": round(divergence, 2),
            "adjustments": adjustments,
            "re_rate_status": cached_data.get("re_rate_status"),
            "catalyst_nature": cached_data.get("catalyst_nature"),
            "is_merger_arb": cached_data.get("is_merger_arb", False),
            "proximity_52wk": stock_data.get("proximity_52wk"),
            "price": stock_data.get("price"),
            "year_high": stock_data.get("year_high"),
            "year_low": stock_data.get("year_low"),
            "bull_score": stock_data.get("bull_score"),
            "upside": stock_data.get("upside"),
            "company_name": cached_data.get("company_name", ""),
        }
        results.append(result)

        # Flag categories
        if raw_score >= 7.5 and adjusted < 6.0:
            false_positives.append(result)
        if raw_score < 6.0 and adjusted >= 7.0:
            hidden_gems.append(result)
        proximity = stock_data.get("proximity_52wk")
        if (cached_data.get("re_rate_status") == "pending"
                and proximity is not None
                and proximity > 0.85):
            re_rate_mismatches.append(result)

    # Sort results
    results.sort(key=lambda r: r["adjusted_score"], reverse=True)
    false_positives.sort(key=lambda r: r["divergence"])
    hidden_gems.sort(key=lambda r: r["adjusted_score"], reverse=True)

    # ── Print Report ──
    print("─" * 72)
    print("  SUMMARY STATISTICS")
    print("─" * 72)
    scores = [r["raw_score"] for r in results]
    adj_scores = [r["adjusted_score"] for r in results]
    divergences = [r["divergence"] for r in results]
    print(f"  Total cached scans:     {len(results)}")
    print(f"  Matched with global:    {matched} ({unmatched} unmatched)")
    print(f"  Average raw score:      {sum(scores)/len(scores):.2f}")
    print(f"  Average adjusted score: {sum(adj_scores)/len(adj_scores):.2f}")
    print(f"  Average divergence:     {sum(divergences)/len(divergences):+.2f}")
    print(f"  Max positive adj:       {max(divergences):+.2f}")
    print(f"  Max negative adj:       {min(divergences):+.2f}")
    print(f"  False Positives:        {len(false_positives)}")
    print(f"  Hidden Gems:            {len(hidden_gems)}")
    print(f"  Re-Rate Mismatches:     {len(re_rate_mismatches)}")
    print()

    # ── FALSE POSITIVES ──
    print("─" * 72)
    print(f"  FALSE POSITIVES (raw ≥ 7.5 but adjusted < 6.0): {len(false_positives)}")
    print("─" * 72)
    if false_positives:
        print(f"  {'Symbol':<8} {'Raw':>5} {'Adj':>5} {'Δ':>6}  {'Prox':>5}  Reason")
        print(f"  {'─'*8} {'─'*5} {'─'*5} {'─'*6}  {'─'*5}  {'─'*40}")
        for r in false_positives[:15]:
            prox = f"{r['proximity_52wk']:.0%}" if r.get("proximity_52wk") is not None else "N/A"
            reasons = "; ".join(a["factor"] for a in r["adjustments"]) or "None"
            print(f"  {r['symbol']:<8} {r['raw_score']:>5.1f} {r['adjusted_score']:>5.1f} {r['divergence']:>+6.1f}  {prox:>5}  {reasons[:50]}")
    else:
        print("  None found — scoring appears well-calibrated at the high end.")
    print()

    # ── HIDDEN GEMS ──
    print("─" * 72)
    print(f"  HIDDEN GEMS (raw < 6.0 but adjusted ≥ 7.0): {len(hidden_gems)}")
    print("─" * 72)
    if hidden_gems:
        print(f"  {'Symbol':<8} {'Raw':>5} {'Adj':>5} {'Δ':>6}  {'Prox':>5}  Reason")
        print(f"  {'─'*8} {'─'*5} {'─'*5} {'─'*6}  {'─'*5}  {'─'*40}")
        for r in hidden_gems[:15]:
            prox = f"{r['proximity_52wk']:.0%}" if r.get("proximity_52wk") is not None else "N/A"
            reasons = "; ".join(a["factor"] for a in r["adjustments"]) or "None"
            print(f"  {r['symbol']:<8} {r['raw_score']:>5.1f} {r['adjusted_score']:>5.1f} {r['divergence']:>+6.1f}  {prox:>5}  {reasons[:50]}")
    else:
        print("  None found — no significantly underrated stocks detected.")
    print()

    # ── RE-RATE MISMATCHES ──
    print("─" * 72)
    print(f"  RE-RATE MISMATCHES (status='pending' but price near 52w high): {len(re_rate_mismatches)}")
    print("─" * 72)
    if re_rate_mismatches:
        print(f"  {'Symbol':<8} {'Raw':>5} {'Adj':>5} {'Prox':>5}  {'Re-Rate':<10}  Company")
        print(f"  {'─'*8} {'─'*5} {'─'*5} {'─'*5}  {'─'*10}  {'─'*30}")
        for r in sorted(re_rate_mismatches, key=lambda x: x.get("proximity_52wk", 0), reverse=True)[:20]:
            prox = f"{r['proximity_52wk']:.0%}" if r.get("proximity_52wk") is not None else "N/A"
            print(f"  {r['symbol']:<8} {r['raw_score']:>5.1f} {r['adjusted_score']:>5.1f} {prox:>5}  {r['re_rate_status'] or 'N/A':<10}  {r['company_name'][:30]}")
    else:
        print("  None found.")
    print()

    # ── TOP 20 ACTIONABLE ──
    actionable = [r for r in results if not r["is_merger_arb"] and r["re_rate_status"] == "pending"]
    actionable.sort(key=lambda r: r["adjusted_score"], reverse=True)
    print("─" * 72)
    print(f"  TOP 20 MOST ACTIONABLE (non-merger, pending re-rate, by adj score)")
    print("─" * 72)
    print(f"  {'#':>3} {'Symbol':<8} {'Raw':>5} {'Adj':>5} {'Δ':>6}  {'Prox':>5}  {'Nature':<20}  Company")
    print(f"  {'─'*3} {'─'*8} {'─'*5} {'─'*5} {'─'*6}  {'─'*5}  {'─'*20}  {'─'*25}")
    for i, r in enumerate(actionable[:20], 1):
        prox = f"{r['proximity_52wk']:.0%}" if r.get("proximity_52wk") is not None else "N/A"
        nature = (r.get("catalyst_nature") or "unknown")[:20]
        print(f"  {i:>3} {r['symbol']:<8} {r['raw_score']:>5.1f} {r['adjusted_score']:>5.1f} {r['divergence']:>+6.1f}  {prox:>5}  {nature:<20}  {r['company_name'][:25]}")
    print()

    # ── Save JSON results ──
    output_path = os.path.join(BACKEND_DIR, "audit_results.json")
    output = {
        "total_scanned": len(results),
        "avg_raw_score": round(sum(scores)/len(scores), 2),
        "avg_adjusted_score": round(sum(adj_scores)/len(adj_scores), 2),
        "false_positives": false_positives,
        "hidden_gems": hidden_gems,
        "re_rate_mismatches": re_rate_mismatches,
        "top_20_actionable": actionable[:20],
        "all_results": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Full results saved to: {output_path}")
    print("=" * 72)


if __name__ == "__main__":
    run_audit()
