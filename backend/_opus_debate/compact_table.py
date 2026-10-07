#!/usr/bin/env python3
"""Print a compact, conviction-sorted table of every Opus debate result for the Director."""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

root = Path(__file__).resolve().parent / (sys.argv[1] if len(sys.argv) > 1 else "results")


# Regime-CRO four-question columns (2026-10-06). Every read is a .get with a blank default: older
# records and the other lanes' results carry none of these fields, and the table must still print.
def _grade(d):
    """The letter on the record (code-derived when the record carries thesis_state), with a trailing
    * when the code re-derived it - from the CRO's own letter, or from an A below the entry floor."""
    v = str(d.get("verdict") or "")
    orig = str(d.get("verdict_agent_orig") or "")
    moved = bool(d.get("grade_rederived")) or (bool(orig) and orig[:1].upper() != v[:1].upper())
    return v + ("*" if moved else "")


def _entry(d):
    mode = str(d.get("entry_mode") or "").strip().upper()
    if mode == "AT_LEVEL":
        lvl = d.get("entry_level_px")
        return f"AT {lvl if lvl is not None else '?'} {d.get('washout_type') or ''}".strip()
    if mode == "ON_EVENT":
        return ("ON " + str(d.get("entry_event") or "").replace("\n", " ")[:60]).strip()
    return mode if mode in ("NOW", "NONE") else ""


def _er(d):
    comp = d.get("computed") if isinstance(d.get("computed"), dict) else {}
    er = comp.get("expected_return_pct")
    return f"{er:.1f}%" if isinstance(er, (int, float)) and not isinstance(er, bool) else ""


def _fit(d):
    fit = d.get("macro_fit")
    if isinstance(fit, dict):            # tolerate a {fit, ...} object as well as the bare token
        fit = fit.get("fit")
    return str(fit or "")


rows = []
for f in sorted(root.glob("*.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    rows.append((
        d.get("conviction", 0) or 0,
        d.get("symbol", f.stem),
        d.get("sector", ""),
        _grade(d),
        str(d.get("thesis_state") or ""),
        _entry(d),
        _er(d),
        _fit(d),
        (d.get("forcing_function") or "").replace("\n", " ")[:200],
        (d.get("consensus_delta") or "").replace("\n", " ")[:260],
        d.get("source", ""),
    ))
rows.sort(key=lambda r: (-r[0], r[1] or ""))
elig = sum(1 for r in rows if r[0] >= 3)
print(f"{len(rows)} debated records | eligible (conviction>=3): {elig}")
print("CONV | SYM | SECTOR | GRADE | THESIS | ENTRY | ER | FIT | FORCING_FUNCTION | CONSENSUS_DELTA | SOURCE")
for r in rows:
    print(" | ".join(str(x) for x in r))
