#!/usr/bin/env python3
"""ab_compare.py — side-by-side CSV of the 2026-07-10 A/B: full multi-agent pipeline (Opus debate +
Opus skeptic) vs ONE Fable agent running the whole pipeline solo, over PRX.AS/AAUC/KBR/CMCSA/FIP.
Ratios are computed HERE from each arm's typed valuation block (never trusted from prose) via
_numeric_core — the same arithmetic discipline the Week-0.4 numeric gate enforces.
Usage: python backend/_opus_debate/_ab/ab_compare.py
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../_opus_debate/_ab
BK = HERE.parent.parent                          # .../backend
sys.path.insert(0, str(BK))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAMES = ["PRX.AS", "AAUC", "KBR", "CMCSA", "FIP"]


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _num(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _rr(val):
    """Computed R:R from a typed valuation block: (base-live)/(live-bear). None when un-computable
    or inverted — never a prose-trusted number."""
    live, base, bear = _num(val.get("live_price")), _num(val.get("base_fv_px")), _num(val.get("bear_px"))
    if None in (live, base, bear) or live <= bear or base <= live:
        return None
    return round((base - live) / (live - bear), 2)


def _er(val):
    live, base = _num(val.get("live_price")), _num(val.get("base_fv_px"))
    if None in (live, base) or not live:
        return None
    return round((base / live - 1) * 100, 1)


def row_for(sym):
    m = _load(HERE / "multi" / f"{sym}.json")
    msk = _load(HERE / "multi_skeptic" / f"{sym}.json")
    f = _load(HERE / "fable" / f"{sym}.json")
    fsk = f.get("skeptic_self") or {}
    mv, fv = m.get("valuation") or {}, f.get("valuation") or {}

    def pair(field, getter=lambda d, k: d.get(k)):
        return getter(m, field), getter(f, field)

    m_rr, f_rr = _rr(mv), _rr(fv)
    m_er, f_er = _er(mv), _er(fv)
    conv_m, conv_f = _num(m.get("conviction")), _num(f.get("conviction"))
    base_m, base_f = _num(mv.get("base_fv_px")), _num(fv.get("base_fv_px"))
    return {
        "symbol": sym,
        "live_price_multi": mv.get("live_price"), "live_price_fable": fv.get("live_price"),
        "currency_multi": mv.get("price_currency"), "currency_fable": fv.get("price_currency"),
        "bear_px_multi": mv.get("bear_px"), "bear_px_fable": fv.get("bear_px"),
        "base_fv_multi": base_m, "base_fv_fable": base_f,
        "base_fv_delta_pct": (round(abs(base_m - base_f) / base_m * 100, 1)
                              if base_m and base_f else None),
        "bull_px_multi": mv.get("bull_px"), "bull_px_fable": fv.get("bull_px"),
        "computed_rr_multi": m_rr, "computed_rr_fable": f_rr,
        "expected_return_pct_multi": m_er, "expected_return_pct_fable": f_er,
        "verdict_multi": m.get("verdict"), "verdict_fable": f.get("verdict"),
        "verdict_match": (m.get("verdict") == f.get("verdict")) if m.get("verdict") and f.get("verdict") else None,
        "conviction_multi": m.get("conviction"), "conviction_fable": f.get("conviction"),
        "conviction_delta": (abs(int(conv_m) - int(conv_f)) if conv_m is not None and conv_f is not None else None),
        "value_conviction_multi": m.get("value_conviction"), "value_conviction_fable": f.get("value_conviction"),
        "catalyst_multi": m.get("catalyst_status"), "catalyst_fable": f.get("catalyst_status"),
        "moat_multi": m.get("moat"), "moat_fable": f.get("moat"),
        "skeptic_multi": msk.get("verdict"), "skeptic_fable_self": fsk.get("verdict"),
        "skeptic_killscope_multi": msk.get("kill_scope"), "skeptic_killscope_fable": fsk.get("kill_scope"),
        "conclusion_multi": str(m.get("moderator_conclusion") or "")[:200],
        "conclusion_fable": str(f.get("moderator_conclusion") or "")[:200],
    }


def main():
    rows = [row_for(s) for s in NAMES]
    out = HERE / "ab_comparison.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:   # BOM for Excel
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # console summary
    print(f"{'SYM':8} {'px m/f':>16} {'base m/f':>16} {'rr m/f':>12} {'verdict m/f':>12} "
          f"{'conv m/f':>9} {'cat m/f':>26} {'skeptic m/f-self':>30}")
    for r in rows:
        print(f"{r['symbol']:8} {str(r['live_price_multi'])+'/'+str(r['live_price_fable']):>16} "
              f"{str(r['base_fv_multi'])+'/'+str(r['base_fv_fable']):>16} "
              f"{str(r['computed_rr_multi'])+'/'+str(r['computed_rr_fable']):>12} "
              f"{str(r['verdict_multi'])+'/'+str(r['verdict_fable']):>12} "
              f"{str(r['conviction_multi'])+'/'+str(r['conviction_fable']):>9} "
              f"{str(r['catalyst_multi'])+'/'+str(r['catalyst_fable']):>26} "
              f"{str(r['skeptic_multi'])+'/'+str(r['skeptic_fable_self']):>30}")
    n_v = sum(1 for r in rows if r["verdict_match"])
    n_c1 = sum(1 for r in rows if r["conviction_delta"] is not None and r["conviction_delta"] <= 1)
    fv_ok = [r["base_fv_delta_pct"] for r in rows if r["base_fv_delta_pct"] is not None]
    print(f"\nAGREEMENT: verdict {n_v}/{len(rows)} | conviction within ±1: {n_c1}/{len(rows)} | "
          f"base-FV deltas: {fv_ok} (%)")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
