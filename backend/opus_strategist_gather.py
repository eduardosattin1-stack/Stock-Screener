"""
opus_strategist_gather.py — step 1 of the nightly Opus option-strategy routine.

Runs on the IB Gateway host. Selects the highest-conviction ML picks (D9/D10 by the
v4 p20_60 decile thresholds), pulls a rich IBKR option chain for each (two expiries,
strike band, calls+puts with greeks) + IV-rank from the GCS history, and writes
strategy_input.json. Step 2 (claude -p, Opus) reads that and designs one best
strategy per name; step 3 (opus_strategist_publish.py) uploads to GCS.

Run:  python backend/opus_strategist_gather.py
Env:  OPUS_MIN_DECILE (9 = D9/D10) · OPUS_INPUT (strategy_input.json) · IB_GATEWAY_PORT
"""
from __future__ import annotations
import os, json, logging
from datetime import datetime, timezone

import ibkr_options
from ibkr_options import chain_snapshot
from ibkr_options_batch import _gcs_read, _map_contract   # reuse GCS read + exchange mapping

log = logging.getLogger("opus_gather")
IV_PREFIX = "options/iv_history"
MIN_SAMPLES = 20
EDGES = [0.103, 0.163, 0.229, 0.296, 0.345, 0.393, 0.445, 0.516, 0.577]  # p20_60 decile edges
MIN_DECILE = int(os.environ.get("OPUS_MIN_DECILE", "9"))   # 9 => D9+D10 only
OUT = os.environ.get("OPUS_INPUT", "strategy_input.json")


def _decile(p: float) -> int:
    d = 1
    for t in EDGES:
        if p >= t:
            d += 1
    return d


def _iv_rank(symbol: str):
    hist = _gcs_read(f"{IV_PREFIX}/{symbol.upper()}.json", [])
    ivs = ([float(r[1]) for r in hist if isinstance(r, list) and len(r) >= 2 and r[1]]
           if isinstance(hist, list) else [])
    if len(ivs) < MIN_SAMPLES:
        return None, len(ivs)
    lo, hi, cur = min(ivs), max(ivs), ivs[-1]
    return (50.0 if hi == lo else round((cur - lo) / (hi - lo) * 100, 1)), len(ivs)


def main():
    scan = _gcs_read("scans/latest_global.json", {})
    stocks = scan.get("stocks") or (scan if isinstance(scan, list) else [])
    picks = [s for s in stocks
             if isinstance(s.get("hit_prob_60d"), (int, float)) and s["hit_prob_60d"] > 0
             and _decile(s["hit_prob_60d"]) >= MIN_DECILE]
    picks.sort(key=lambda s: s["hit_prob_60d"], reverse=True)
    log.info("D%d+ picks: %d", MIN_DECILE, len(picks))

    ib = ibkr_options._connect()
    out = []
    try:
        for s in picks:
            sym = s["symbol"]
            try:
                # Recover from a dropped gateway connection (IB error 1100) so one
                # blip doesn't doom the rest of the run.
                if not ib.isConnected():
                    log.warning("IB disconnected — reconnecting before %s", sym)
                    try: ib.disconnect()
                    except Exception: pass
                    ib = ibkr_options._connect()
                m = _map_contract(sym)
                if not m:
                    log.info("skip %s (unmapped exchange)", sym); continue
                ib_sym, ex, cur = m
                snap = chain_snapshot(ib, ib_sym, ex, cur, s.get("price"))
                if not snap.get("expirations"):
                    log.info("skip %s (no chain/options)", sym); continue
                ivr, n = _iv_rank(sym)
                out.append({
                    "symbol": sym, "decile": _decile(s["hit_prob_60d"]),
                    "hit_prob_60d": round(s["hit_prob_60d"], 3),
                    "hit_prob_30d": round(s.get("hit_prob_30d") or 0, 3),
                    "expected_dd_60d": round(s.get("expected_dd_60d") or 0, 3),
                    "days_to_earnings": s.get("days_to_earnings"),
                    "sector": s.get("sector"), "price": s.get("price"), "currency": cur,
                    "iv_rank": ivr, "iv_samples": n, "chain": snap,
                })
                log.info("gathered %s (D%d, ivr=%s, exps=%d)", sym, out[-1]["decile"], ivr, len(snap["expirations"]))
            except Exception as e:
                # RequestTimeout (bad/unresolvable contract), connection error, etc.
                # Skip this name and keep going — never let one stall the batch.
                log.warning("skip %s (error: %s)", sym, type(e).__name__ + ": " + str(e))
                continue
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass

    payload = {"updated": datetime.now(timezone.utc).isoformat(), "count": len(out), "picks": out}
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("wrote %s — %d picks with chains", OUT, len(out))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    main()
