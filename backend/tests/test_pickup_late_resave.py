"""Late re-save rule in the Gemini pickup (Bruno 2026-11-26, Week 48).

A record file re-saved after the skeptic step counts as blind only when an earlier file of
Gemini's own quotes the same base value. Run: python backend/tests/test_pickup_late_resave.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gemini_confirm"))
import pickup_week as P  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def make(dossier, selfcheck, base=70.0, order=("dossier", "skeptic", "self", "record")):
    g = Path(tempfile.mkdtemp())
    files = {"dossier": ("dossier.md", dossier), "skeptic": ("skeptic_on_claude.json", "{}"),
             "self": ("skeptic_on_gemini.json", selfcheck), "record": ("record.json", "{}")}
    for i, key in enumerate(order):
        name, text = files[key]
        if text is None:
            continue
        (g / name).write_text(text, encoding="utf-8")
        os.utime(g / name, (1000 + i * 100, 1000 + i * 100))
    return g, {"valuation": {"base_fv_px": base}}


g, rec = make("We value it at $70.00 per share.", None)
check("dossier quoting the base value -> dossier", P._late_resave_evidence(g, rec) == "dossier")

g, rec = make("No number here.", json.dumps({"corrections": "base fair value from $70.00 to $66.00"}))
check("only the self-check quotes it -> self-check", P._late_resave_evidence(g, rec) == "self-check")

g, rec = make("No number here.", None)
check("no corroborating file -> stays not blind", P._late_resave_evidence(g, rec) is None)

g, rec = make("Fair value 170.0, or 70.05 on the bear case.", None)
check("a different number containing the digits does not count", P._late_resave_evidence(g, rec) is None)

g, rec = make("We value it at $70.00.", None, order=("skeptic", "dossier", "self", "record"))
check("dossier written after it read ours -> stays not blind", P._late_resave_evidence(g, rec) is None)

g, rec = make("No number.", json.dumps({"c": "from 70.00"}), order=("dossier", "skeptic", "record", "self"))
check("self-check written after the re-save does not count", P._late_resave_evidence(g, rec) is None)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
