"""
opus_strategist_publish.py — step 3 of the nightly Opus option-strategy routine.

Reads the Opus output (strategy_output.json — a JSON object keyed by symbol, possibly
wrapped in markdown fences), and uploads it to GCS scans/options_strategies.json for
the frontend stock card to read.

Run:  python backend/opus_strategist_publish.py [strategy_output.json]
"""
from __future__ import annotations
import sys, json, re, logging
from datetime import datetime, timezone

from ibkr_options_batch import _gcs_write   # reuse the gcloud-token GCS write

log = logging.getLogger("opus_publish")


def _parse(text: str):
    t = text.strip()
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
    with open(path) as f:
        strategies = _parse(f.read())
    if isinstance(strategies, dict) and isinstance(strategies.get("strategies"), dict):
        strategies = strategies["strategies"]   # tolerate {"strategies": {...}}
    if not isinstance(strategies, dict):
        raise SystemExit("expected a JSON object keyed by symbol")
    payload = {"updated": datetime.now(timezone.utc).isoformat(),
               "count": len(strategies), "strategies": strategies}
    if _gcs_write("scans/options_strategies.json", payload):
        log.info("uploaded scans/options_strategies.json — %d names", len(strategies))
    else:
        raise SystemExit("upload failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
