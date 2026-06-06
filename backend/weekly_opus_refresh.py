#!/usr/bin/env python3
"""weekly_opus_refresh.py — driver for the weekly all-Opus Speculair refresh.

`prep`  : source the candidate universe from PRODUCTION GCS (all 11 per_methodology_baskets
          + current apex), build per-name input bundles (metrics) + fetch FMP transcripts,
          dump the engine system prompts, and EMIT a self-contained debate workflow JS with
          the candidate list baked in (sidesteps the Workflow `args` delivery bug). Prints the
          scriptPath + candidate count for the scheduled run to hand to the Workflow tool.

The scheduled SKILL.md runs:  python weekly_opus_refresh.py prep
  -> Workflow({scriptPath: <printed>})
  -> python _opus_debate/publish_to_frontend.py --gcs

Robust by construction: each name is a SINGLE-agent full Opus regime debate (Interrogator+
Architect+Moderator in one pass, schema-less, inline regime brief) — the pattern that proved
reliable; no fragile inter-stage handoff, no StructuredOutput dependency.
"""
import json
import os
import sys
from pathlib import Path

BK = r"C:\Users\Bruno\Stock-Screener\backend"
sys.path.insert(0, BK); sys.path.insert(0, os.path.join(BK, "alpha_compounder"))
os.chdir(BK)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import live_debate_engine as E  # noqa: E402
import gcs_io  # noqa: E402
import requests  # noqa: E402

ROOT = Path("_opus_debate")
INP, TXT, RES = ROOT / "inputs", ROOT / "transcripts", ROOT / "results_regime"
for d in (INP, TXT, RES, ROOT / "dossiers"):
    d.mkdir(parents=True, exist_ok=True)

DEEP_VAL = {"epv", "graham_revised", "iv15_deep_value", "acquirers_multiple",
            "earnings_yield_gap", "owner_earnings", "dcf_fcff", "rd_capitalized_dcf", "ev_gross_profit"}

REGIME_FILE = "CATALYST_WATCH_REGIME.md"  # repo root; read live each run for the current regime


def _ttm_cash_block(sym):
    """PATCH (2026-06-05): the screener metrics feed FISCAL-YEAR-ANNUAL FCF/EPS, which anchors
    the debate to stale cash even when the latest quarter inflected (the CON defect). Pull the
    last 4 quarters from FMP and surface TTM FCF + TTM diluted EPS + latest-quarter EPS YoY,
    flagged as overriding the annual figures. Returns '' on any failure (degrade gracefully)."""
    key = E.get_key("FMP_API_KEY")
    if not key:
        return ""
    base = "https://financialmodelingprep.com/stable"
    try:
        cf = requests.get(base + "/cash-flow-statement",
                          params={"symbol": sym, "period": "quarter", "limit": 5, "apikey": key}, timeout=20).json()
        inc = requests.get(base + "/income-statement",
                           params={"symbol": sym, "period": "quarter", "limit": 8, "apikey": key}, timeout=20).json()
    except Exception:
        return ""
    if not (isinstance(cf, list) and isinstance(inc, list) and len(cf) >= 4 and len(inc) >= 4):
        return ""

    def num(d, *ks):
        for k in ks:
            v = d.get(k) if isinstance(d, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
        return None

    fcfs = [num(q, "freeCashFlow") for q in cf[:4]]
    if any(v is None for v in fcfs):  # fallback: OCF + capex (capex stored negative)
        fcfs = [(num(q, "operatingCashFlow") or 0) + (num(q, "capitalExpenditure") or 0) for q in cf[:4]]
    ttm_fcf = sum(v for v in fcfs if isinstance(v, (int, float))) if fcfs else None
    epss = [num(q, "epsDiluted", "epsdiluted", "eps") for q in inc[:4]]
    ttm_eps = sum(epss) if all(isinstance(v, (int, float)) for v in epss) else None
    q0 = num(inc[0], "epsDiluted", "epsdiluted", "eps")
    q4 = num(inc[4], "epsDiluted", "epsdiluted", "eps") if len(inc) >= 5 else None
    yoy = ((q0 - q4) / abs(q4) * 100) if (isinstance(q0, (int, float)) and isinstance(q4, (int, float)) and q4) else None

    def amt(v):
        a = abs(v)
        return f"{v/1e9:.2f}B" if a >= 1e9 else (f"{v/1e6:.0f}M" if a >= 1e6 else f"{v:.0f}")

    parts = []
    if isinstance(ttm_fcf, (int, float)):
        parts.append(f"TTM FCF {amt(ttm_fcf)}")
    if isinstance(ttm_eps, (int, float)):
        parts.append(f"TTM diluted EPS {ttm_eps:.2f}")
    if isinstance(yoy, (int, float)):
        parts.append(f"latest-Q EPS YoY {yoy:+.0f}%")
    if not parts:
        return ""
    asof = (cf[0].get("date") if isinstance(cf[0], dict) else "") or ""
    return ("=== TTM / LATEST QUARTER (FMP, as of " + asof + " — USE THESE OVER THE FISCAL-YEAR-ANNUAL "
            "FCF/EPS ABOVE WHEN THEY DIFFER) ===\n" + " | ".join(parts))


def prep():
    E.load_api_keys()
    # SELF-CLEAN (2026-06-06): archive the PRIOR run's debate outputs so the Director only ever sees
    # ONE coherent debate pass. Mixing vintages (today's post-fix debates + last week's, built on
    # different metrics/universe) let stale or data-quality-contaminated theses win apex slots. Keeps
    # the previous run in _opus_debate/_archive_prev/ for one cycle (apex-rotation comparison), then
    # overwrites. The workflow-resume retry path does NOT call prep, so a mid-run re-invoke is safe.
    import shutil
    arch = ROOT / "_archive_prev"
    if arch.exists():
        shutil.rmtree(arch, ignore_errors=True)
    arch.mkdir(parents=True, exist_ok=True)
    for sub in ("results_regime", "dossiers"):
        src = ROOT / sub
        if src.exists() and any(src.iterdir()):
            shutil.move(str(src), str(arch / sub))
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    apx = ROOT / "apex_basket_opus_regime.json"
    if apx.exists():
        shutil.move(str(apx), str(arch / "apex_basket_opus_regime.json"))
    print(f"archived prior debate outputs -> {arch}")

    # PRIMARY SOURCE: the raw 11-methodology production screen (methodology_picks.json) — the
    # FULL opportunity set, re-read every week. Sourcing from the *curated* speculair_baskets.json
    # instead created a SHRINK LOOP: each run only re-debated last week's survivors, so the universe
    # degenerated over time (observed 2026-06-06: 8 methodologies, 15 names, apex=1 after a partial
    # 01:03 write). The raw screen breaks that loop. We still UNION-in the current apex (held names)
    # so a live position is never dropped just because it aged out of the raw screen.
    mp = gcs_io.gcs_read_json("scans/methodology_picks.json") or {}
    meth_src = mp.get("methodologies", {})
    print(f"raw screen methodology_picks.json: last_updated={mp.get('last_updated')} "
          f"methodologies={len(meth_src)}")
    sym_meths = {}
    for meth, b in meth_src.items():
        for p in (b.get("picks", b) if isinstance(b, dict) else b) or []:
            if isinstance(p, dict) and p.get("symbol"):
                sym_meths.setdefault(p["symbol"], []).append(meth)
    baskets = gcs_io.gcs_read_json("scans/speculair_baskets.json") or {}
    # Fallback: if the raw screen is unexpectedly thin, also fold in the curated baskets so a
    # transient screen problem can't starve the debate.
    if len(sym_meths) < 40:
        print(f"WARN: raw screen only yielded {len(sym_meths)} names — folding in curated baskets")
        for meth, b in baskets.get("per_methodology_baskets", {}).items():
            for p in (b.get("picks", b) if isinstance(b, dict) else b) or []:
                if isinstance(p, dict) and p.get("symbol"):
                    sym_meths.setdefault(p["symbol"], []).append(meth)
    for p in baskets.get("apex_basket", []):
        if p.get("symbol"):
            sym_meths.setdefault(p["symbol"], []).append("apex")

    scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
        open("../frontend/public/latest_global.json", encoding="utf-8"))
    scan_by_sym = {s.get("symbol"): s for s in scan.get("stocks", []) if s.get("symbol")}

    syms, no_tx = [], []
    for sym in sorted(sym_meths):
        sc = scan_by_sym.get(sym, {})
        scan_fin = {k: sc.get(k) for k in E._SCAN_FIN_FIELDS if sc.get(k) is not None}
        bh = sc.get("buffett_history") or {}
        rows = bh.get("rows")
        if isinstance(rows, list) and rows:
            scan_fin["history_rows"] = [{"year": r.get("year"), "revenue_mm": r.get("revenue_mm"),
                                         "net_income_mm": r.get("net_income_mm"), "eps": r.get("eps")} for r in rows[-6:]]
            if isinstance(bh.get("cagrs"), dict):
                scan_fin["history_cagrs"] = bh["cagrs"]
        cand = {"symbol": sym, "sector": sc.get("sector", ""), "price": sc.get("price"),
                "fair_value": sc.get("buffett_fair_value"), "mos": sc.get("margin_of_safety")}
        try:
            metrics = E._build_debate_metrics(financials=cand, scan_fin=scan_fin)
        except Exception:
            metrics = "No financial metrics available."
        # TTM/latest-quarter override is now appended inside E._build_debate_metrics (_ttm_block),
        # so it applies to BOTH the production debate and this Opus prep — no duplicate needed here.
        meths = sym_meths[sym]
        signal = "deep_value" if all(m in DEEP_VAL for m in meths if m != "apex") and any(m in DEEP_VAL for m in meths) else "catalyst"
        (INP / f"{sym}.json").write_text(json.dumps({
            "symbol": sym, "sector": sc.get("sector", ""), "signal_type": signal,
            "company": sc.get("name") or sc.get("companyName") or "",
            "metrics_str": metrics, "dossier": "", "methodologies": meths}, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            tx = E.resolve_transcripts(sym)
            real = [t for t in tx.get("all_transcripts", []) if len(t.get("content", "")) > 1000]
        except Exception:
            real = []
        if real:
            real.sort(key=lambda t: t["date"])
            (TXT / f"{sym}.txt").write_text(
                "\n\n".join("=== " + t["date"] + " ===\n" + E._slice_transcript(t["content"]) for t in real[-8:]),
                encoding="utf-8")
            syms.append(sym)
        else:
            no_tx.append(sym)

    (ROOT / "interrogator_system.txt").write_text(E.INTERROGATOR_SYSTEM_PROMPT, encoding="utf-8")
    (ROOT / "architect_system.txt").write_text(E.ARCHITECT_SYSTEM_PROMPT, encoding="utf-8")
    (ROOT / "moderator_system.txt").write_text(E.MODERATOR_SYSTEM_PROMPT, encoding="utf-8")

    # no_tx names have NO FMP transcript — instead of skipping (the user's explicit ask: "send agents
    # to fetch transcripts online so we don't skip any pick"), pass them as ONLINE_SYMS so the debate
    # agent WebSearch/WebFetches the latest transcript/results. Their input bundles (with metrics +
    # company name) were already written above, so they debate with full fundamentals grounding.
    js = (_WORKFLOW_TEMPLATE
          .replace("__SYMS__", json.dumps(syms))
          .replace("__ONLINE_SYMS__", json.dumps(no_tx)))
    out = ROOT / "_weekly_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"PREP OK: {len(syms)} with FMP transcripts + {len(no_tx)} via online fetch "
          f"= {len(syms) + len(no_tx)} total candidates (online: {no_tx})")
    print(f"WORKFLOW_SCRIPT={out.resolve()}")


_WORKFLOW_TEMPLATE = r"""export const meta = {
  name: 'speculair-opus-weekly',
  description: 'Weekly all-Opus regime debate over the full per-methodology universe, then Director picks the apex basket',
  phases: [{ title: 'Debate' }, { title: 'Director' }],
}
const DIR = 'backend/_opus_debate'
const RES = DIR + '/results_regime'
const SYMS = __SYMS__               // have a bundled FMP transcript (read local file)
const ONLINE_SYMS = __ONLINE_SYMS__ // no FMP transcript — agent fetches the latest one online
const BRIEF = "Read CATALYST_WATCH_REGIME.md (repo root) for the current market regime, then APPLY it: reward hard-dated catalysts inside the favorable window; PENALIZE Fed-cut/rate-rescue or past/out-of-window catalysts; favor structural special-sits in fat thin-coverage lanes (distressed/deleveraging > spinoffs > forced-sellers), deprioritize hard-binary/PDUFA; prize resolution-driver independence (wary of theses hinging on one shared macro factor like oil or AI-capex). Let this MOVE the conviction/verdict."

// Steps 2-5 are identical for both transcript sources; only step 1 (the evidence source) differs.
function debatePrompt(sym, online) {
  const step1 = online
    ? '1. Read ' + DIR + '/inputs/' + sym + '.json ("metrics_str","sector","signal_type","company"). NO FMP transcript is bundled for this name. Use WebSearch + WebFetch to find ' + sym + "'s MOST RECENT earnings-call transcript; if no transcript exists, get the latest quarterly results / earnings release / management commentary / investor presentation (try the company IR site, Tikr, Seeking Alpha, Investing.com, Simply Wall St, MarketScreener, plus the latest regulatory filing). Search using the company name in the bundle. Read 1-3 sources. If genuinely nothing is findable, say so EXPLICITLY and reason from the fundamentals + filings — never fabricate quotes or figures.\n"
    : '1. Read ' + DIR + '/inputs/' + sym + '.json ("metrics_str","sector","signal_type") and ' + DIR + '/transcripts/' + sym + '.txt.\n'
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' as Claude Opus 4.8 — Interrogator, then Architect, then Moderator.\n' +
    step1 +
    '2. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; produce the full forensic dossier (8 sections + final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...>"); Write it to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '3. ARCHITECT: read ' + DIR + '/architect_system.txt; produce bull_thesis and bear_thesis grounded in the dossier + metrics.\n' +
    '4. MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion.\n' +
    '5. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json: symbol(="' + sym + '"), sector, signal_type, bull_thesis, bear_thesis, verdict, conviction, consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_score(int), trajectory, source(="' + (online ? 'opus_regime_online' : 'opus_regime_mod') + '"), transcript_source(="' + (online ? 'web' : 'fmp') + '").\n' +
    'Reply exactly: DONE'
}

const ALL = SYMS.map(s => ({ sym: s, online: false })).concat(ONLINE_SYMS.map(s => ({ sym: s, online: true })))
log(`Weekly Opus debate over ${ALL.length} names (${SYMS.length} FMP + ${ONLINE_SYMS.length} online-fetch), then Director.`)
phase('Debate')
await parallel(ALL.map(it => () => agent(
  debatePrompt(it.sym, it.online),
  it.online
    ? { label: 'debate:' + it.sym + '(web)', phase: 'Debate', agentType: 'general-purpose' }
    : { label: 'debate:' + it.sym, phase: 'Debate' })))

phase('Director')
await agent(
  'You are the SPECULAIR APEX DIRECTOR (Claude Opus 4.8). The moderators already applied the regime.\n' +
  'STEP 1 — Read CATALYST_WATCH_REGIME.md (repo root) IN FULL; apply its tilt (#2 structural special-sits, #3 in-window dated catalysts / penalize Fed-cut-dependent, #4 resolution-driver independence).\n' +
  'STEP 2 — Run: python backend/_opus_debate/compact_table.py results_regime — confirm the row count.\n' +
  'STEP 3 — Eligible = conviction >= 3. Pick the 10 strongest by conviction, then regime fit, then forcing-function datedness, then consensus-delta width, then MOS. HARD: <=3 per sector AND no >3 names on one macro driver (oil, AI-capex). You MAY Read individual ' + RES + '/<SYM>.json for finalists.\n' +
  'STEP 4 — Each pick: symbol, sector, director_conviction (0-100), one-sentence thesis, forcing_function, lane, regime_fit. Plus ~6 runner_ups and a director_memo.\n' +
  'STEP 5 — Write (Write tool) VALID JSON to ' + DIR + '/apex_basket_opus_regime.json = {apex_basket:[...], director_memo, runner_ups:[...]}. Reply exactly: DONE',
  { label: 'director', phase: 'Director' })
log('Weekly debate + director complete.')
return 'DONE'
"""


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prep"
    if mode == "prep":
        prep()
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)
