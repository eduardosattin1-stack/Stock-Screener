#!/usr/bin/env python3
"""_ledger.py — shared Director decision-history ledger (2026-07-10 extraction).

Single source of truth for `_decision_history.json`, replacing two prior copies that had drifted
apart: the canonical implementation in weekly_opus_refresh.py and an inline copy in
publish_to_frontend.py (which existed only to dodge weekly_opus_refresh.py's module-level
os.chdir() side-effect). This module has NO side effects on import (no chdir, no network) so both
callers can import it directly — weekly_opus_refresh.py picks it up from its own directory
(backend/); publish_to_frontend.py already puts backend/ on sys.path (see its BACKEND constant).

DECISION_HISTORY path is self-located (Path(__file__).parent), independent of either caller's CWD.
"""
import json
from pathlib import Path

LEDGER_YEAR = "2026"
DECISION_HISTORY = Path(__file__).resolve().parent / "_opus_debate" / "_decision_history.json"


def _book_apex(d):
    return (d.get("apex_basket") or d.get("apex") or []) if isinstance(d, dict) else (d if isinstance(d, list) else [])


def load_decision_history():
    try:
        return json.load(open(DECISION_HISTORY, encoding="utf-8")) or {}
    except Exception:
        return {}


def append_decision_history(book, basket):
    """Record this run's per-name Director decisions into the persistent year ledger (for next run +
    the UI rotation trail). Best-effort; never raises."""
    try:
        import datetime as _dt
        today = _dt.date.today().isoformat()
        hist = load_decision_history()
        bh = hist.setdefault(book, {})
        for p in _book_apex(basket):
            if not isinstance(p, dict) or not p.get("symbol"):
                continue
            s = p["symbol"]
            ev = {"date": today,
                  "decision": str(p.get("decision") or "KEEP").upper(),
                  "conviction": p.get("director_conviction") or p.get("value_score") or p.get("conviction"),
                  "rationale": (p.get("decision_rationale") or p.get("whats_changed") or p.get("thesis")
                                or p.get("director_rationale") or "")[:200]}
            # 2026-07-11 (pipeline-v3 Weeks 3-4, Director anchoring): the ledger now carries the
            # NUMBERS, not just the verbs — next week's Director is anchored against its own prior
            # conviction/size/ER, and the deterministic clamp in _regime_post reads conviction here.
            # All best-effort: absent fields are simply omitted (older baskets lack them).
            for src_key, dst_key in (("size_units", "size_units"), ("expected_return_pct", "expected_return_pct"),
                                     ("sop_fair_value", "sop_fair_value"), ("entry_price", "live_price"),
                                     ("conviction_delta", "conviction_delta")):
                v = p.get(src_key)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    ev[dst_key] = v
            comp = p.get("computed") or {}
            if isinstance(comp.get("rr_ratio"), (int, float)):
                ev["rr_ratio"] = comp["rr_ratio"]
            if p.get("numeric_gate") and p.get("numeric_gate") != "PASS":
                ev["numeric_gate"] = p.get("numeric_gate")
            lst = bh.setdefault(s, [])
            if not (lst and lst[-1].get("date") == today):
                lst.append(ev)
            bh[s] = lst[-24:]
        json.dump(hist, open(DECISION_HISTORY, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"WARN: append_decision_history({book}) failed ({e})")
