"""The Gemini hand-off must stay blind: no earlier answer about a name may reach its step-1 inputs.

Regression for 2026-11-19: `second_opinion` (added to the debate bundles on 2026-11-12) quotes OUR
base value as `our_base_fv_px`, and strip_inputs did not drop it, so the Week 47 export leaked it.

usage:  python backend/tests/test_gemini_export_blind.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gemini_confirm"))
import export_week as X  # noqa: E402  (module has a __main__ guard; importing it runs nothing)

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def bundle():
    return {
        "symbol": "INCH.L",
        "prior_record": {"answer_source": "committee", "verdict": "A", "sop_fair_value": "950 pence a share"},
        "washout": {"entry_level_px": 600},
        "second_opinion": {"status": "repriced", "their_base_fv_px": 782.0, "our_base_fv_px": 950.0},
        "dossier": "CREDIBILITY_SCORE: 4 | ...",
        "metrics_str": "Valuation: P/E 9.1 | Fair Value 950 | Margin of Safety 32%\nGrowth: +4%\n"
                       "Valuation models (stock page): DCF 1100\nPer-method margin-of-safety: 30%",
        "company": "Inchcape",
    }


# 1. strip_inputs nulls every earlier-answer field and returns what it removed
b = bundle()
removed = X.strip_inputs(b)
for k in X.BLIND_NULL_FIELDS:
    check(f"strip_inputs nulls {k}", b.get(k) is None)
check("strip_inputs reports the removed second_opinion", removed["second_opinion"]["our_base_fv_px"] == 950.0)
check("second_opinion is in the blind list", "second_opinion" in X.BLIND_NULL_FIELDS)
check("scan fair value and margin of safety leave metrics_str",
      "Fair Value" not in b["metrics_str"] and "Margin of Safety" not in b["metrics_str"])
check("per-method valuation lines leave metrics_str",
      "Valuation models" not in b["metrics_str"] and "Per-method" not in b["metrics_str"])
check("raw multiples and growth stay", "P/E 9.1" in b["metrics_str"] and "Growth: +4%" in b["metrics_str"])
check("non-answer fields stay", b["company"] == "Inchcape")

# 2. a bundle without the newer fields still strips cleanly (older weeks)
old = {"symbol": "X", "prior_record": None, "washout": None, "metrics_str": ""}
X.strip_inputs(old)
check("old-shape bundle: no new keys invented", "second_opinion" not in old and "dossier" not in old)

with tempfile.TemporaryDirectory() as td:
    att = Path(td)
    # 3. leak_scan passes a stripped bundle
    b = bundle()
    X.strip_inputs(b)
    (att / "inputs__INCH.L.json").write_text(json.dumps(b), encoding="utf-8")
    check("leak_scan: stripped bundle is clean", X.leak_scan(att) == [])

    # 4. leak_scan catches an unstripped bundle (the Week 47 shape)
    (att / "inputs__INCH.L.json").write_text(json.dumps(bundle()), encoding="utf-8")
    problems = X.leak_scan(att)
    check("leak_scan: flags a non-empty second_opinion", any("second_opinion is not empty" in p for p in problems))
    check("leak_scan: flags our_base_fv_px text", any("our_base_fv_px" in p for p in problems))
    check("leak_scan: flags a non-empty prior_record", any("prior_record is not empty" in p for p in problems))

    # 5. leak_scan catches a marker in any other JSON attachment (e.g. a peer group)
    (att / "inputs__INCH.L.json").write_text(json.dumps(b), encoding="utf-8")
    (att / "peer_groups__INCH.L.json").write_text(json.dumps({"relative_comps": "Margin of Safety 40%"}), encoding="utf-8")
    check("leak_scan: flags a marker in a peer group", any("peer_groups__INCH.L.json" in p for p in X.leak_scan(att)))

# 6. the shared data files copied into every pick do not trip the markers (no false stops)
D = X.D
for name in ("macro_regime.json", "secular_themes.json"):
    p = D / name
    if p.exists():
        txt = p.read_text(encoding="utf-8")
        check(f"{name} carries no leak marker", not any(m in txt for m in X.LEAK_MARKERS))

print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}'}")
sys.exit(1 if FAILS else 0)
