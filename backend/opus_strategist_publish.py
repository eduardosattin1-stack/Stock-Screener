"""
opus_strategist_publish.py — step 3 of the nightly Opus option-strategy routine.

Reads the Opus output (strategy_output.json — a JSON object keyed by symbol, possibly
wrapped in markdown fences), and uploads it to GCS scans/options_strategies.json for
the frontend stock card to read.

Run:  python backend/opus_strategist_publish.py [strategy_output.json]
"""
from __future__ import annotations
import os, sys, json, re, logging
from datetime import datetime, timezone

from ibkr_options_batch import _gcs_write   # reuse the gcloud-token GCS write

log = logging.getLogger("opus_publish")


def _parse(text: str):
    t = text.lstrip("﻿").strip()   # tolerate a UTF-8 BOM
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```$", "", t.strip())
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)   # outermost object fallback
        if m:
            return json.loads(m.group(0))
        raise


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "strategy_output.json"
    with open(path, encoding="utf-8-sig") as f:   # utf-8-sig strips any BOM
        strategies = _parse(f.read())
    if isinstance(strategies, dict) and isinstance(strategies.get("strategies"), dict):
        strategies = strategies["strategies"]   # tolerate {"strategies": {...}}
    if not isinstance(strategies, dict):
        raise SystemExit("expected a JSON object keyed by symbol")

    # Enrich each strategy from the gather's strategy_input.json: decile/iv_rank/
    # price/sector for the card chips, AND a fill-aware, probability-grounded EV
    # (opus_ev) that replaces the conviction*mid heuristic. Best-effort.
    in_path = os.path.join(os.path.dirname(os.path.abspath(path)), "strategy_input.json")
    try:
        from opus_ev import compute_ev
        with open(in_path, encoding="utf-8-sig") as f:
            picks = {p["symbol"]: p for p in (json.load(f).get("picks") or [])}
        for sym, strat in strategies.items():
            p = picks.get(sym)
            if isinstance(strat, dict) and p:
                strat.setdefault("decile", p.get("decile"))
                strat.setdefault("iv_rank", p.get("iv_rank"))
                strat.setdefault("price", p.get("price"))
                strat.setdefault("sector", p.get("sector"))
                ev = compute_ev(strat, p)
                if ev:
                    strat["ev"] = ev["ev"]                    # per contract, fill-aware
                    strat["pop"] = ev["pop"]
                    strat["net_fill"] = ev["net_fill"]
                    strat["max_gain_fill"] = ev["max_gain_fill"]
                    strat["max_loss_fill"] = ev["max_loss_fill"]
                    strat["breakeven_fill"] = ev["breakeven_fill"]
                    strat["ev_method"] = ev["method"]
    except Exception as e:
        log.warning("could not enrich from strategy_input.json: %s", e)

    payload = {"updated": datetime.now(timezone.utc).isoformat(),
               "count": len(strategies), "strategies": strategies}
    if _gcs_write("scans/options_strategies.json", payload):
        log.info("uploaded scans/options_strategies.json — %d names", len(strategies))
    else:
        raise SystemExit("upload failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
