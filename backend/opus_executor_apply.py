"""
opus_executor_apply.py — step 7: apply Opus's close/hold decisions to the paper book.

Reads execution_output.json (Opus's per-position {id, action, reason}), and for every
OPEN position Opus marked CLOSE, realizes it at the realistic exit fill the tracker
already computed (entry_cash + exit_cash, crossing the bid/ask), stamps
status=closed_opus / exit_date / days_held / close_reason, recomputes the book stats,
and writes the ledger back to GCS. HOLDs are left to keep marking nightly.

Run:  python opus_executor_apply.py [execution_output.json]
"""
from __future__ import annotations
import sys, json, re, logging
from datetime import datetime, timezone, date

from ibkr_options_batch import _gcs_read, _gcs_write
from opus_paper_tracker import _stats, LEDGER, _today

log = logging.getLogger("opus_exec_apply")


def _parse(text: str):
    t = text.lstrip("﻿").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t); t = re.sub(r"\n```$", "", t.strip())
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _decisions(obj) -> dict:
    """Normalize to {id: {action, reason}}. Tolerates a list, {decisions:[...]}, or a map."""
    if isinstance(obj, dict) and isinstance(obj.get("decisions"), list):
        obj = obj["decisions"]
    out = {}
    if isinstance(obj, list):
        for d in obj:
            if isinstance(d, dict) and d.get("id"):
                out[d["id"]] = d
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                out[k] = v
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "execution_output.json"
    with open(path, encoding="utf-8-sig") as f:
        decisions = _decisions(_parse(f.read()))
    if not decisions:
        log.info("no decisions parsed — nothing to apply"); return

    ledger = _gcs_read(LEDGER, None, fresh=True)
    if not isinstance(ledger, dict) or "positions" not in ledger:
        raise SystemExit("no paper ledger to apply to")

    today = date.fromisoformat(_today())
    closed = 0
    for p in ledger["positions"]:
        if p["status"] != "open":
            continue
        d = decisions.get(p["id"])
        if not d or str(d.get("action", "")).upper() != "CLOSE":
            continue
        if p.get("exit_cash") is None:
            log.warning("skip close %s — no exit fill (untradeable mark)", p["id"]); continue
        realized = round((p["entry_cash"] + p["exit_cash"]) * 100, 2)
        held = (today - date.fromisoformat(p["entry_date"])).days
        p.update(status="closed_opus", exit_date=_today(), realized_pnl=realized,
                 pnl=realized, days_held=held, closed_by="opus",
                 close_reason=str(d.get("reason", ""))[:240],
                 pnl_pct=round(realized / (abs(p["max_loss"]) * 100) * 100, 1) if p.get("max_loss") else None)
        closed += 1

    ledger["stats"] = _stats(ledger)
    ledger["updated"] = datetime.now(timezone.utc).isoformat()
    if not _gcs_write(LEDGER, ledger):
        raise SystemExit("ledger upload failed")
    s = ledger["stats"]
    log.info("applied: %d closed by Opus · realized $%s (PF %s, win %s%%) · %d still open",
             closed, s["realized_pnl"], s["profit_factor"], s["win_rate"], s["n_open"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
