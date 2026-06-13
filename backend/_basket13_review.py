#!/usr/bin/env python3
"""Basket 13 — human-review document (agent comments verbatim), SELF-CONTAINED from the tracker.

§1 the full CURRENT held book (each seat's stored Director rationale + CRO four-surface detail,
which persist on the entry across re-debates), §1b resolved seats, §2 the latest run's CRO kills,
§3 the recorded non-selections (counterfactuals), §4 the latest Director memo. Writes
BASKET13_REVIEW.md at the repo root. Re-run after every inject.
Usage: python _basket13_review.py
"""
import json, os, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "BASKET13_REVIEW.md")

trk = json.load(open(os.path.join(BASE, "_basket13_tracker.json"), encoding="utf-8"))
op = os.path.join(BASE, "_basket13_out.json")
out = json.load(open(op, encoding="utf-8")) if os.path.exists(op) else {}
cur_cro = {v["symbol"]: v for v in out.get("cro", []) if v.get("symbol")}     # latest run only
run = (trk.get("runs") or [{}])[-1]
names = {}
bp = os.path.join(ROOT, "catalyst_candidates_231.json")
if os.path.exists(bp):
    names = {c["symbol"]: c.get("company_name", "") for c in json.load(open(bp, encoding="utf-8"))["candidates"]}

held = [e for e in trk.get("entries", []) if not e.get("resolution") and e.get("status") != "PENDING_LIMIT"]
pend = [e for e in trk.get("entries", []) if not e.get("resolution") and e.get("status") == "PENDING_LIMIT"]
resolved = [e for e in trk.get("entries", []) if e.get("resolution")]


def fmt_expr(e):
    x = e.get("expression") or {}
    s = str(x.get("type", "equity")).replace("_", " ")
    if x.get("expiry"): s += f" exp {x['expiry']}"
    return s


def exp_ev(e):
    if e.get("expected_rr") is not None: return f"R:R {e['expected_rr']}:1"
    if e.get("expected_ev") is not None: return f"EV {round(e['expected_ev'] * 100, 1)}%"
    return "—"


def cro_detail_of(e):
    d = e.get("cro_detail") or {}
    if not any((d or {}).values()):                      # fallback to current run (a just-added seat)
        v = cur_cro.get(e["symbol"]) or {}
        d = {k: v.get(k) for k in ("live_edge_check", "tradeability_note", "window_note", "driver_confirmed", "conditions")}
    return d


def cro_block(d, verdict=None):
    L = []
    if verdict: L.append(f"**CRO verdict: {verdict}**")
    if d.get("live_edge_check"): L.append(f"- **1 · Edge at entry (live re-check):** {d['live_edge_check']}")
    if d.get("tradeability_note"): L.append(f"- **2 · Tradeability:** {d['tradeability_note']}")
    if d.get("window_note"): L.append(f"- **3 · Window ↔ expression:** {d['window_note']}")
    if d.get("driver_confirmed"): L.append(f"- **4 · Driver tag:** {d['driver_confirmed']}")
    for c in d.get("conditions") or []: L.append(f"- ⚠ **Condition:** {c}")
    return "\n".join(L) if L else "*(no CRO detail stored)*"


L = []
inv = round(sum(e.get("weight_pct") or 0 for e in held), 1)
pw = round(sum(e.get("weight_pct") or 0 for e in pend), 1)
L.append("# Basket 13 — Catalyst Sleeve · Agent Comments for Review")
L.append("")
L.append(f"*Generated {datetime.date.today().isoformat()} · {len(held)} held seats ({inv}% invested)"
         + (f" + {len(pend)} resting-limit ({pw}%)" if pend else "")
         + (f" + {len(resolved)} resolved" if resolved else "")
         + f" · last run {run.get('run_date', '?')} · paper basket, nothing executed*")
L.append("")
L.append("Pipeline: enriched board → entry/staging filter → **Catalyst-CRO** (attacks ONLY the trade — "
         "live edge / tradeability / window↔expression / driver tag; catalyst reality settled upstream by the "
         "scan→deep→skeptic tier; value/quality attacks forbidden) → **Director** (selection + sizing under HARD "
         "caps: ≤2/driver, ≤40 NAV weight-points/super-cluster, 8–12 names, risk-to-floor ≤1.5% NAV, binaries "
         "defined-risk ≤2%, staging equity-only half-weight; held seats run to resolution and consume combined-cap "
         "headroom) → deterministic cap validator → tracker stamps at CRO-verified live prices.")
L.append("")
if run.get("retags"):
    L.append("**Driver re-tags (logged, cap-relevant):** "
             + "; ".join(f"{r['symbol']}: {r['from']} → {r['to']}" for r in run["retags"]))
    L.append("")

L.append("---")
L.append(f"## 1 · The basket ({len(held)} held" + (f", {len(pend)} resting-limit" if pend else "") + ")")
for e in held + pend:
    sym = e["symbol"]; pending = e.get("status") == "PENDING_LIMIT"
    entry_txt = (f"RESTING LIMIT ≤ ${e.get('limit_price')} since {e.get('order_date')} — NOT HELD" if pending
                 else f"entry {e.get('entry_date')} @ {e.get('entry_price')} ({e.get('entry_price_source')})")
    L.append("")
    L.append(f"### {sym} — {names.get(sym, '')}" + ("  ⏳ PENDING" if pending else ""))
    L.append(f"`{e.get('weight_pct')}% · {fmt_expr(e)} · {e.get('lane_canon')} · {e.get('resolution_driver')} "
             f"({e.get('super_cluster')}) · score {e.get('score')} · edge {e.get('edge_grade')}"
             + (" · STAGING" if e.get("staging") else "") + f" · {entry_txt}`")
    L.append(f"- **Expected:** {exp_ev(e)} · milestone {e.get('dated_milestone') or 'soft/undated'} · review: {e.get('review_trigger', '—')}")
    if pending:
        L.append(f"- **Why not held:** live at stamp exceeded the CRO entry limit; fills via the daily mark when the close trades ≤ ${e.get('limit_price')}.")
    if e.get("hedge"):
        h = e["hedge"]; L.append(f"- **Hedge leg:** {h['ratio']} {h['symbol']} per share, ref ${h.get('price_at_entry')}")
    if e.get("risk_to_floor_pct") is not None:
        L.append(f"- **Risk-to-floor (computed):** {e['risk_to_floor_pct']}% of NAV (cap 1.5)")
    if e.get("entry_rationale"):
        L.append(f"- **Director — why this seat:** {e['entry_rationale']}")
    if e.get("invalidation"):
        L.append(f"- **Director — what kills it:** {e['invalidation']}")
    L.append("")
    L.append(cro_block(cro_detail_of(e), e.get("cro_verdict")))

if resolved:
    L.append(""); L.append("---"); L.append(f"## 1b · Resolved ({len(resolved)})")
    for e in resolved:
        r = e["resolution"]
        ret = ("%+.1f%%" % (r["realized_return_pct"] * 100)) if r.get("realized_return_pct") is not None else "—"
        L.append(f"- **{e['symbol']}** {r['resolution_type']} · {e.get('entry_date')}→{r['resolution_date']} "
                 f"({r.get('days_held')}d) · {e.get('entry_price')}→{r.get('exit_price')} · realized {ret} "
                 f"(exp {exp_ev(e)}) · {r.get('notes', '')}")

kills = [v for v in cur_cro.values() if v.get("verdict") == "NO_TRADE"]
L.append(""); L.append("---")
L.append(f"## 2 · CRO kills this run — NO_TRADE ({len(kills)})")
L.append("")
L.append("*Killed on trade grounds only (edge gone / untradeable / window fails) — catalyst reality was settled upstream.*")
for v in kills:
    L.append(""); L.append(f"### {v['symbol']} — {names.get(v['symbol'], '')}")
    L.append(cro_block(v, v.get("verdict")))

ns = trk.get("non_selections", [])
L.append(""); L.append("---")
L.append(f"## 3 · Non-selections ({len(ns)}) — recorded counterfactuals")
L.append("")
L.append("*CRO survivors the Director passed on, plus stamp-time exclusions; recorded for selection-calibration.*")
L.append("")
L.append("| Symbol | Lane | Driver | Edge | Passed because |")
L.append("|---|---|---|---|---|")
for p in ns:
    L.append(f"| **{p['symbol']}** | {p.get('lane_canon', '')} | {p.get('resolution_driver', '')} | {p.get('edge_grade', '')} | {p.get('passed_because', '')} |")

L.append(""); L.append("---")
L.append("## 4 · Latest Director memo (verbatim)")
L.append("")
L.append(run.get("memo") or (out.get("director") or {}).get("memo", "(none)"))
L.append("")
L.append("---")
L.append(f"*Caps at last stamp: {run.get('cap_violations', 0)} violations · {run.get('n_added', '?')} added · "
         f"{run.get('n_pending', 0)} pending · {run.get('n_excluded_at_stamp', 0)} excluded-at-stamp. "
         f"Auto-generated by backend/_basket13_review.py.*")

open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
print(f"WROTE {OUT}  ({len(L)} lines: {len(held)} held + {len(pend)} pending + {len(resolved)} resolved, "
      f"{len(kills)} kills, {len(ns)} non-selections)")
