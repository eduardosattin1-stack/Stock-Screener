#!/usr/bin/env python3
"""Inject IBKR options analytics into the sweep board.
Reads the _opt_fetch_workflow.js output (results[]), computes the panel's
options_signals per symbol, attaches it to _sweep_board.json, regenerates
catalystBoardSweep.ts. Usage: python _options_inject.py <workflow_output.json>"""
import json, sys, math, os
from _sweep_pipe import regen_ts, BOARD_F

def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def build_signals(r):
    iv = f(r.get("annual_iv"))
    if iv is None:
        return None  # no listed options / no IV -> leave NO_OPTIONS
    hv = f(r.get("hist_vol_annual"))
    pct = f(r.get("iv_pctile_52w"))
    tc, tp = f(r.get("today_call_vol")), f(r.get("today_put_vol"))
    ac, ap = f(r.get("avg_call_vol")), f(r.get("avg_put_vol"))
    pc_vol = (tp / tc) if (tp is not None and tc) else None
    move30 = round(iv * math.sqrt(30.0 / 365.0) * 100, 1)  # 1-sigma 30d implied move %

    # sentiment flag (short badge)
    iv_tag = "Elevated IV" if (pct is not None and pct >= 0.70) else ("Low IV" if (pct is not None and pct <= 0.30) else "Moderate IV")
    flow = ""
    if pc_vol is not None:
        flow = " · put-heavy flow" if pc_vol >= 1.3 else (" · call-heavy flow" if pc_vol <= 0.7 else " · balanced flow")
    flag = iv_tag + flow

    # interpretation sentence
    bits = [f"ATM IV {iv*100:.0f}%"]
    if pct is not None:
        bits[0] += f" ({pct*100:.0f}th %ile, 52w)"
    if hv:
        prem = iv / hv if hv else None
        prem_txt = "rich vol/event premium" if (prem and prem >= 1.8) else ("modest premium" if (prem and prem >= 1.2) else "near realized")
        bits.append(f"vs {hv*100:.0f}% 30d realized ({prem_txt})")
    if pc_vol is not None:
        act = ""
        tot_t = (tc or 0) + (tp or 0)
        tot_a = (ac or 0) + (ap or 0)
        if tot_a:
            ratio = tot_t / tot_a
            act = ", unusually active" if ratio >= 2 else (", elevated activity" if ratio >= 1.3 else "")
        bits.append(f"P/C vol {pc_vol:.2f}{act}")
    bits.append(f"~{move30:.1f}% 30d implied move")
    interp = "; ".join(bits) + ". (IBKR; skew/term-structure/OI not available via this feed.)"

    return {
        "iv_current": round(iv, 4),
        "skew_25d": None,
        "term_structure": "N/A",
        "pc_oi_ratio": round(pc_vol, 2) if pc_vol is not None else None,  # P/C VOLUME (tile relabeled "P/C Vol")
        "total_oi": None,
        "implied_earnings_move_pct": move30,
        "market_sentiment_flag": flag,
        "overall_interpretation": interp,
    }

def main():
    out = json.load(open(sys.argv[1], encoding="utf-8"))
    res = out.get("result", out)
    rows = res.get("results", res if isinstance(res, list) else [])
    sig = {}
    for r in rows:
        if not r or not r.get("symbol"):
            continue
        s = build_signals(r)
        if s:
            sig[r["symbol"].upper()] = s

    board = json.load(open(BOARD_F, encoding="utf-8"))
    attached = 0
    for b in board:
        s = sig.get(b["symbol"].upper())
        if s:
            b["options_signals"] = s
            attached += 1
    json.dump(board, open(BOARD_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    regen_ts(board)
    print(f"ATTACHED options to {attached}/{len(board)} board names ({len(sig)} had IV from IBKR)")

if __name__ == "__main__":
    main()
