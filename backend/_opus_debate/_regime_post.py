#!/usr/bin/env python3
"""Deterministic post-processing for the REGIME / APEX book (apex_basket_opus_regime.json).

The mirror of _value_post.py for the catalyst/apex book, which until now had NO kill-tier and NO
post-processor (publish_to_frontend.py stamped weights straight from the Director's size_units). This:
  1. consumes the APEX skeptic (_skeptic_regime/<SYM>.json) — REFUTED demotes to runner_ups;
  2. stamps the deterministic moat terminal-erosion teeth (moat_erosion=='CAP' -> 0.5 size cap);
  3. enforces the secular-theme concentration cap + any Director combined_caps;
  4. stamps size_units_effective + weight_pct (the Director's raw size_units is left UNTOUCHED, so the
     step is idempotent and publish_to_frontend can prefer the effective units).

Runs AFTER the Director and the regime skeptic, BEFORE publish_to_frontend.py. Pure file I/O +
computation — no FMP fetch, no API key. Shares ONE implementation with the value book via _post_common
+ _moat, so a skeptic that demotes and a cap loop that sizes behave identically across both surfaces.

Pipeline order:
    Director -> apex_basket_opus_regime.json -> [regime-skeptic Workflow] -> _regime_post (THIS)
    -> publish_to_frontend.py

Usage: python backend/_opus_debate/_regime_post.py
"""
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../backend/_opus_debate
BK = _HERE.parent                                 # .../backend
ROOT = _HERE
sys.path.insert(0, str(BK))                       # backend on path for _moat (pure, no API key)
sys.path.insert(0, str(_HERE))                    # _opus_debate on path for _post_common
from _moat import moat_features                    # noqa: E402
import _post_common as _pc                          # noqa: E402

REGIME_F = ROOT / "apex_basket_opus_regime.json"
SKEP_DIR = ROOT / "_skeptic_regime"
RES_DIR = ROOT / "results_regime"


def _load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _scan_by_sym():
    for p in (BK.parent / "frontend" / "public" / "latest_global.json", ROOT / "latest_global.json"):
        d = _load(p)
        if d:
            return {x.get("symbol"): x for x in d.get("stocks", []) if x.get("symbol")}
    return {}


def stamp_moat(picks, uni, scan_by):
    """Compute + stamp the deterministic moat signals and the agent moat read onto each pick. Computes
    moat_features locally (from _radar_universe + scan + results_regime) so the regime book does NOT
    depend on value-input having run first — decoupling the weekly ordering."""
    for p in picks:
        sym = p.get("symbol")
        if not sym:
            continue
        r = _load(RES_DIR / f"{sym}.json", {}) or {"sector": p.get("sector", "")}
        mf = moat_features(uni.get(sym, {}), scan_by.get(sym, {}), r)
        p["moat_erosion"] = mf["moat_erosion"]
        p["erosion_severity"] = mf["erosion_severity"]
        p["moat_score"] = mf["moat_score"]
        p["roic_below_hurdle"] = mf["roic_below_hurdle"]
        if not p.get("moat"):
            p["moat"] = r.get("moat", "")
        if not p.get("secular_theme"):
            p["secular_theme"] = r.get("secular_theme", "")


def process(apx, uni, scan_by):
    """Consume the apex skeptic, stamp the moat teeth, enforce the secular-theme + Director combined
    caps, and build weights. Mutates + returns (apx, picks, extra). Pure — safe on an in-memory copy."""
    apx = _pc.consume_skeptic(apx, REGIME_F, SKEP_DIR)        # REFUTED -> demote BEFORE weights
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    stamp_moat(picks, uni, scan_by)
    stamp_moat([r for r in apx.get("runner_ups", []) if isinstance(r, dict)], uni, scan_by)  # visibility only
    extra = _pc.secular_theme_caps(picks)                    # don't put all eggs in one secular tail
    # Base unit = Director size_units when present, else director_conviction/100 — the SAME fallback
    # publish_to_frontend._apex_weights uses — so the moat/theme caps apply ON TOP of the Director's
    # sizing rather than flattening it.
    memo = {p["symbol"]: max(0.1, (p.get("director_conviction") or p.get("conviction") or 0) / 100.0)
            for p in picks}
    weights = _pc.build_weights(apx, picks, extra_caps=extra, memo_units=memo, per_name_cap=_pc.moat_per_name_cap)
    apx["weights"] = weights
    apx["secular_theme_caps"] = extra
    apx["moat_post_applied"] = True
    return apx, picks, extra


def main():
    apx = _load(REGIME_F)
    if not apx or not apx.get("apex_basket"):
        print(f"_regime_post: {REGIME_F} missing or empty — nothing to do.")
        return
    uni = {x["symbol"]: x for x in (_load(ROOT / "_radar_universe.json", []) or [])}
    scan_by = _scan_by_sym()
    apx, picks, extra = process(apx, uni, scan_by)
    json.dump(apx, open(REGIME_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    capped = [p["symbol"] for p in picks if p.get("moat_erosion") == "CAP"]
    refute = [p["symbol"] for p in picks
              if p.get("erosion_severity") == "value-destroying"
              or (p.get("moat_erosion") == "CAP" and p.get("roic_below_hurdle"))]
    print(f"_regime_post: {len(picks)} apex | moat-capped={capped} | skeptic-REFUTE-candidates={refute} "
          f"| secular-theme caps={[c['axis'] for c in extra]}")


if __name__ == "__main__":
    main()
