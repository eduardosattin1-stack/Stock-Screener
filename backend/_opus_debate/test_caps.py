#!/usr/bin/env python3
"""Unit test for the shared cap mechanics in _post_common: the moat-erosion half-cap, the secular-
theme concentration cap (with WIDE-moat durable exemption), and combined-cap scaling. Pure — no data
files, no API key. Usage: python backend/_opus_debate/test_caps.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _post_common as pc  # noqa: E402


def main():
    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    # The user's exact worry: AI-displacement concentration ADBE/IT/GLOB + payments EEFT/PLX.PA.
    picks = [
        {"symbol": "ADBE",   "moat": "WIDE",    "moat_erosion": "",    "secular_theme": "ai-displacement",            "size_units": 0.76},
        {"symbol": "IT",     "moat": "ERODING", "moat_erosion": "CAP", "secular_theme": "ai-displacement",            "size_units": 0.74},
        {"symbol": "GLOB",   "moat": "ERODING", "moat_erosion": "CAP", "secular_theme": "ai-displacement",            "size_units": 0.60},
        {"symbol": "EEFT",   "moat": "NARROW",  "moat_erosion": "",    "secular_theme": "payments-disintermediation", "size_units": 0.69},
        {"symbol": "PLX.PA", "moat": "NARROW",  "moat_erosion": "",    "secular_theme": "payments-disintermediation", "size_units": 0.68},
        {"symbol": "NTES",   "moat": "WIDE",    "moat_erosion": "",    "secular_theme": "",                           "size_units": 0.66},
    ]

    # 1. secular_theme_caps: a >=2 NON-DURABLE cluster gets a cap; a WIDE non-eroding anchor is exempt.
    caps = pc.secular_theme_caps(picks)
    by_axis = {c["axis"]: c for c in caps}
    ai = by_axis.get("secular-theme:ai-displacement")
    pay = by_axis.get("secular-theme:payments-disintermediation")
    check("ai-displacement cap exists", ai is not None)
    check("ai cap names = [IT, GLOB] (ADBE WIDE-exempt)", ai and sorted(ai["names"]) == ["GLOB", "IT"])
    check("ADBE not in any cap (durable exemption)", all("ADBE" not in c["names"] for c in caps))
    check("payments cap = [EEFT, PLX.PA]", pay and sorted(pay["names"]) == ["EEFT", "PLX.PA"])

    # 2. moat_per_name_cap half-caps moat_erosion=='CAP' / cro_only / stale_anchor; leaves others.
    check("moat CAP -> 0.5", pc.moat_per_name_cap({"moat_erosion": "CAP"}, 0.74) == 0.5)
    check("cro_only -> 0.5", pc.moat_per_name_cap({"cro_only": True}, 0.9) == 0.5)
    check("stale_anchor -> 0.5", pc.moat_per_name_cap({"stale_anchor": True}, 1.0) == 0.5)
    check("clean name untouched", pc.moat_per_name_cap({"moat_erosion": ""}, 0.76) == 0.76)

    # 3. build_weights: moat cap applies (IT/GLOB -> 0.5 effective) and a binding combined cap scales.
    apx = {"combined_caps": [{"names": ["IT", "GLOB"], "max_units": 0.6, "axis": "secular-theme:ai-displacement"}]}
    wts = pc.build_weights(apx, picks, per_name_cap=pc.moat_per_name_cap)
    eff = {p["symbol"]: p["size_units_effective"] for p in picks}
    check("IT half-capped then scaled (<0.5)", eff["IT"] < 0.5)
    check("GLOB half-capped then scaled (<0.5)", eff["GLOB"] < 0.5)
    check("IT+GLOB scaled to combined cap 0.6", abs(eff["IT"] + eff["GLOB"] - 0.6) < 1e-3)
    check("ADBE not capped (0.76)", abs(eff["ADBE"] - 0.76) < 1e-9)
    check("weights sum to 1.0", abs(sum(wts.values()) - 1.0) < 1e-6)

    print("effective units:", {k: round(v, 3) for k, v in eff.items()})
    print("theme caps:", [c["axis"] + "->" + str(c["names"]) for c in caps])
    if failures:
        print("FAILED:", failures)
        sys.exit(1)
    print("ALL CAP TESTS PASSED.")


if __name__ == "__main__":
    main()
