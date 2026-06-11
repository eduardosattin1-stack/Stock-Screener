#!/usr/bin/env python3
"""Basket 13 — generate the human-review document (agent comments verbatim).

Reads _basket13_out.json (full debate provenance: CRO verdicts + Director output)
+ _basket13_candidates.json (native board fields) + _basket13_tracker.json (stamps),
writes BASKET13_REVIEW.md at the repo root. Re-run after every debate run.

Usage: python _basket13_review.py
"""
import json, os, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "BASKET13_REVIEW.md")

out = json.load(open(os.path.join(BASE, "_basket13_out.json"), encoding="utf-8"))
cands = {c["symbol"]: c for c in json.load(open(os.path.join(BASE, "_basket13_candidates.json"), encoding="utf-8"))["candidates"]}
trk = json.load(open(os.path.join(BASE, "_basket13_tracker.json"), encoding="utf-8"))
cro = {v["symbol"]: v for v in out.get("cro", []) if v.get("symbol")}
director = out.get("director") or {}
entries = {e["symbol"]: e for e in trk.get("entries", [])}
# only stamped seats render in §1 — Director picks excluded at stamp time fall to the counterfactual table
picks = {p["symbol"]: p for p in director.get("picks", []) if p["symbol"] in entries}
run = (trk.get("runs") or [{}])[-1]
held = [e for e in trk.get("entries", []) if not e.get("resolution") and e.get("status") != "PENDING_LIMIT"]
pend = [e for e in trk.get("entries", []) if not e.get("resolution") and e.get("status") == "PENDING_LIMIT"]


def fmt_expr(p):
    x = p.get("expression") or {}
    s = str(x.get("type", "equity")).replace("_", " ")
    if x.get("expiry"):
        s += f" exp {x['expiry']}"
    if x.get("strikes"):
        s += f" strikes {x['strikes']}"
    return s


def cro_block(v, indent=""):
    L = []
    L.append(f"{indent}**CRO verdict: {v.get('verdict')}**")
    if v.get("live_edge_check"):
        L.append(f"{indent}- **1 · Edge at entry (live re-check):** {v['live_edge_check']}")
    if v.get("tradeability_note"):
        L.append(f"{indent}- **2 · Tradeability:** {v['tradeability_note']}")
    if v.get("window_note"):
        L.append(f"{indent}- **3 · Window ↔ expression:** {v['window_note']}")
    if v.get("driver_confirmed"):
        L.append(f"{indent}- **4 · Driver tag:** {v['driver_confirmed']}")
    for c in v.get("conditions") or []:
        L.append(f"{indent}- ⚠ **Condition:** {c}")
    return "\n".join(L)


lines = []
lines.append("# Basket 13 — Inaugural Run, Agent Comments for Review")
lines.append("")
lines.append(f"*Run {run.get('run_date', '?')} · generated {datetime.date.today().isoformat()} · "
             f"{out.get('generated_for', '?')} candidates debated → {len(out.get('cro', []))} CRO verdicts → "
             f"{len(out.get('survivors', []))} survivors → {len(picks)} seats · paper basket (nothing executed)*")
lines.append("")
lines.append("Pipeline: enriched board → entry/staging filter → **Catalyst-CRO** (attacks ONLY the trade: "
             "live edge, tradeability, window↔expression, driver tag — catalyst reality settled upstream by "
             "the scan→deep→skeptic tier; value/quality attacks forbidden) → **Director** (selection + sizing "
             "under hard caps: ≤2/driver, ≤40 NAV weight-points/super-cluster, 8–12 names, risk-to-floor "
             "≤1.5% NAV, binaries defined-risk ≤2%, staging equity-only half-weight) → deterministic cap "
             "validator → tracker stamps.")
lines.append("")
lines.append("**Stamp policy (2026-06-11 review):** entries stamped at the **CRO-verified live price** "
             "(source recorded per stamp), never the dossier reference; CRO entry limits enforced at stamp "
             "time — a live price above the limit stamps as a **resting limit, not held** (no fiction fills); "
             "hedge legs recorded on the entry; risk-to-floor **computed**, not quoted; driver re-tags logged. "
             "Cluster-cap basis pinned: ≤40 weight-points of NAV (the invested-share basis is unstable to "
             "exclusions; the memo's stricter invested-share read is reported alongside).")
if run.get("retags"):
    lines.append("")
    lines.append("**Driver re-tags this run (logged, cap-relevant):** " +
                 "; ".join(f"{r['symbol']}: {r['from']} → {r['to']} ({r['authority']})" for r in run["retags"]))
lines.append("")

# ── the basket ──
inv = round(sum(e.get("weight_pct") or 0 for e in held), 1)
pw = round(sum(e.get("weight_pct") or 0 for e in pend), 1)
lines.append("---")
lines.append(f"## 1 · The basket ({len(held)} held seats, {inv}% invested"
             + (f"; +{len(pend)} resting limit, {pw}% reserved" if pend else "") + ")")
for sym, p in picks.items():
    c, v, e = cands.get(sym, {}), cro.get(sym, {}), entries.get(sym, {})
    pending = e.get("status") == "PENDING_LIMIT"
    entry_txt = (f"RESTING LIMIT ≤ ${e.get('limit_price')} since {e.get('order_date')} — NOT HELD"
                 if pending else f"entry {e.get('entry_date')} @ {e.get('entry_price')} ({e.get('entry_price_source')})")
    lines.append("")
    lines.append(f"### {sym} — {c.get('company_name', '')}" + ("  ⏳ PENDING" if pending else ""))
    lines.append(f"`{p.get('weight_pct')}% · {fmt_expr(p)} · {c.get('lane_canon')} · {p.get('resolution_driver')} "
                 f"({p.get('super_cluster') or c.get('super_cluster')}) · score {c.get('score')} · edge {c.get('edge_grade')}"
                 + (" · STAGING (half-weight, equity-only)" if c.get("staging") else "")
                 + f" · {entry_txt}`")
    if pending:
        lines.append(f"- **Why not held:** live price at stamp exceeded the CRO entry limit — a real book does not "
                     f"fill this order. Fills automatically via the daily mark when the close trades ≤ ${e.get('limit_price')}.")
    if e.get("hedge"):
        h = e["hedge"]
        lines.append(f"- **Hedge leg (recorded):** {h['ratio']} {h['symbol']} per share, reference ${h.get('price_at_entry')} — {h.get('basis')}")
    if e.get("risk_to_floor_pct") is not None:
        lines.append(f"- **Risk-to-floor (computed):** {e['risk_to_floor_pct']}% of NAV (cap 1.5%)")
    exp = p.get("expected_rr")
    ev = p.get("expected_ev")
    lines.append(f"- **Expected:** " + (f"R:R {exp}:1" if exp is not None else f"EV {round(ev * 100, 1)}%" if ev is not None else "—")
                 + f" · milestone {c.get('dated_milestone') or 'soft/undated'}"
                 + (f" ({c.get('days_to_milestone')}d)" if c.get("days_to_milestone") is not None else ""))
    if p.get("entry_rationale"):
        lines.append(f"- **Director — why this seat:** {p['entry_rationale']}")
    if p.get("invalidation"):
        lines.append(f"- **Director — what kills it:** {p['invalidation']}")
    if p.get("review_trigger"):
        lines.append(f"- **Review trigger:** {p['review_trigger']}")
    lines.append("")
    lines.append(cro_block(v))

# ── CRO kills ──
kills = [v for s, v in cro.items() if v.get("verdict") == "NO_TRADE"]
lines.append("")
lines.append("---")
lines.append(f"## 2 · CRO kills — NO_TRADE ({len(kills)})")
lines.append("")
lines.append("*Killed on trade grounds only (edge gone / untradeable / window fails) — the catalyst itself was already verified upstream.*")
for v in kills:
    c = cands.get(v["symbol"], {})
    lines.append("")
    lines.append(f"### {v['symbol']} — {c.get('company_name', '')}  `{c.get('tier')} · {c.get('lane_canon')} · edge {c.get('edge_grade')}`")
    lines.append(cro_block(v))

# ── non-selections (the TRACKER's record: Director passes + stamp-time exclusions) ──
passed = trk.get("non_selections", [])
lines.append("")
lines.append("---")
lines.append(f"## 3 · Non-selections ({len(passed)}) — recorded counterfactuals")
lines.append("")
lines.append("*CRO survivors the Director passed on, plus stamp-time exclusions; the tracker records these "
             "for selection-calibration (did the passes outperform the picks?).*")
lines.append("")
lines.append("| Symbol | Lane | Driver | Edge | CRO verdict | Passed because |")
lines.append("|---|---|---|---|---|---|")
for p in passed:
    sym = p["symbol"]
    c, v = cands.get(sym, {}), cro.get(sym, {})
    lines.append(f"| **{sym}** | {c.get('lane_canon', '')} | {c.get('resolution_driver', '')} | {c.get('edge_grade', '')} "
                 f"| {v.get('verdict', '')} | {p.get('passed_because', '')} |")

# ── director memo ──
lines.append("")
lines.append("---")
lines.append("## 4 · Director memo (verbatim)")
lines.append("")
lines.append(director.get("memo", "(none)"))
lines.append("")
lines.append("---")
lines.append(f"*Caps at stamp time: {run.get('cap_violations', 0)} violations · {run.get('n_added')} entries stamped · "
             f"{run.get('n_passed')} non-selections recorded. Review doc auto-generated by backend/_basket13_review.py.*")

open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"WROTE {OUT}  ({len(lines)} lines: {len(picks)} seats, {len(kills)} kills, {len(passed)} passes)")
