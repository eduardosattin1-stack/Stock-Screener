"""Apply layer-2 financial gates to the 357-stock structural allowlist.

Run locally with the FMP API key. Approx. wall time: 5-8 minutes (357 calls,
sequential, polite pacing).

USAGE:
    cd /home/claude/Stock-Screener/backend
    export FMP_API_KEY=<your_key>
    python apply_financial_gates.py

OUTPUT:
    backend/strategy_allowlists/sp500.txt          (refreshed with layer-2 survivors)
    backend/strategy_allowlists/_sp500_audit.json  (per-symbol scores + drop reasons)

GATES:
    1. Piotroski score >= 5  (median; allows mature buyback-heavy names like HD/MCD)
    2. Altman-Z >= 1.81       (Altman's safe zone; catches KHC, VTRS, DD, T, VZ, BA)
    3. Revenue >= $1B         (almost always redundant given SP500, but defends
                              against zero-revenue dev-stage names)
"""
import os, json, time
import requests
from datetime import datetime, timezone
from pathlib import Path

KEY = os.environ.get("FMP_API_KEY") or "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
BASE = "https://financialmodelingprep.com/stable"

# Threshold knobs - set these once and forget
PIOTROSKI_MIN = 5
ALTMAN_Z_MIN = 1.81
REVENUE_MIN = 1_000_000_000

ALLOWLIST_DIR = Path(__file__).parent / "strategy_allowlists"
INPUT_PATH = ALLOWLIST_DIR / "sp500.txt"          # the 357-name structural list
OUTPUT_PATH = ALLOWLIST_DIR / "sp500.txt"         # overwrite with layer-2 survivors
AUDIT_PATH = ALLOWLIST_DIR / "_sp500_audit.json"  # human-readable drop log

session = requests.Session()

def fetch_scores(symbol):
    try:
        r = session.get(f"{BASE}/financial-scores",
                        params={"symbol": symbol, "apikey": KEY}, timeout=15)
        if not r.ok:
            return None, f"http_{r.status_code}"
        data = r.json()
        if not data:
            return None, "empty_response"
        return data[0], None
    except Exception as e:
        return None, f"exception_{type(e).__name__}"


def evaluate(scores):
    """Return (kept: bool, reason: str)."""
    pio = scores.get("piotroskiScore")
    z = scores.get("altmanZScore")
    rev = scores.get("revenue") or 0

    if pio is None:
        return False, "missing_piotroski"
    if pio < PIOTROSKI_MIN:
        return False, f"piotroski_{pio}_below_{PIOTROSKI_MIN}"
    if z is None:
        return False, "missing_altman_z"
    if z < ALTMAN_Z_MIN:
        return False, f"altman_z_{z:.2f}_below_{ALTMAN_Z_MIN}"
    if rev < REVENUE_MIN:
        return False, f"revenue_${rev/1e6:.0f}M_below_$1B"
    return True, "kept"


# 2026-05-05: explicit force-keep list. These are SP500 mainstays whose
# balance sheets fail the Altman-Z gate (telco/aerospace debt loads) but
# whose cash flows and market position justify keeping them in the
# momentum universe. Per Bruno's call.
FORCE_KEEP = {"T", "VZ", "BA"}


def main():
    if not INPUT_PATH.exists():
        raise SystemExit(f"Input not found: {INPUT_PATH}")
    symbols = [s.strip() for s in INPUT_PATH.read_text().splitlines() if s.strip() and not s.startswith("#")]
    print(f"Input: {len(symbols)} symbols from {INPUT_PATH}")
    print(f"Gate: Piotroski >= {PIOTROSKI_MIN}, Altman-Z >= {ALTMAN_Z_MIN}, Revenue >= ${REVENUE_MIN/1e9:.0f}B")
    print()

    keep, drops, scored = [], [], []
    for i, sym in enumerate(symbols, 1):
        scores, err = fetch_scores(sym)
        if err:
            drops.append({"symbol": sym, "reason": f"fetch_failed_{err}"})
            print(f"  [{i:3d}/{len(symbols)}] {sym:6s}  FETCH_FAILED ({err})")
            continue
        scored.append({"symbol": sym, **{k: scores.get(k) for k in
            ["piotroskiScore", "altmanZScore", "revenue", "ebit", "marketCap"]}})
        kept, reason = evaluate(scores)
        if not kept and sym in FORCE_KEEP:
            kept = True
            reason = f"force_kept_overriding_{reason}"
        if kept:
            keep.append(sym)
            if reason.startswith("force_kept"):
                print(f"  [{i:3d}/{len(symbols)}] {sym:6s}  KEEP  ({reason})")
        else:
            drops.append({"symbol": sym, "reason": reason,
                          "piotroski": scores.get("piotroskiScore"),
                          "altman_z": round(scores.get("altmanZScore", 0), 2),
                          "revenue_m": round((scores.get("revenue") or 0)/1e6)})
            print(f"  [{i:3d}/{len(symbols)}] {sym:6s}  DROP  ({reason})")
        time.sleep(0.05)  # polite pacing on FMP

    # Write outputs
    OUTPUT_PATH.write_text("\n".join(sorted(keep)) + "\n")
    AUDIT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_count": len(symbols),
        "kept": len(keep),
        "dropped": len(drops),
        "thresholds": {"piotroski_min": PIOTROSKI_MIN, "altman_z_min": ALTMAN_Z_MIN,
                       "revenue_min": REVENUE_MIN},
        "kept_symbols": sorted(keep),
        "drops_detail": sorted(drops, key=lambda x: x["symbol"]),
        "scored_detail": sorted(scored, key=lambda x: x["symbol"]),
    }, indent=2))

    print()
    print(f"Result: {len(keep)} kept, {len(drops)} dropped")
    print(f"  → {OUTPUT_PATH}")
    print(f"  → {AUDIT_PATH}")


if __name__ == "__main__":
    main()
