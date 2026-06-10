#!/usr/bin/env python3
"""weekly_opus_refresh.py — driver for the weekly all-Opus Speculair refresh.

`prep`  : source the candidate universe from PRODUCTION GCS (all 11 per_methodology_baskets
          + current apex), build per-name input bundles (metrics) + fetch FMP transcripts,
          dump the engine system prompts, and EMIT a self-contained debate workflow JS with
          the candidate list baked in (sidesteps the Workflow `args` delivery bug). Prints the
          scriptPath + candidate count for the scheduled run to hand to the Workflow tool.

The scheduled SKILL.md runs:
  python weekly_opus_refresh.py prep            (raw-screen universe + bundles + ledger re-check routing)
  -> Workflow({scriptPath: <printed>})          (Radar [sonnet] -> Debate [opus] -> Director [fable])
  -> python _opus_debate/publish_to_frontend.py --gcs                 (regime/catalyst book)
  -> python weekly_opus_refresh.py value-input                        (value signals + funnel stats + ledger)
  -> [value Director agent, fable]
  -> python weekly_opus_refresh.py value-skeptic -> Workflow(...)     (independent kill-tier, fable)
  -> python weekly_opus_refresh.py value-post                         (deterministic safety layer; consumes skeptic)
  -> python weekly_opus_refresh.py value-csv / baskets-csv
  -> python weekly_opus_refresh.py value-publish --gcs                (value book + both NAV trackers)
Periodic verbs: shadow-debate / shadow-diff (Fable A/B with a pre-committed migration trigger),
control-sample (monthly funnel miss-rate), value-revalidate (stale-anchor pro-forma re-debate),
disruptor-universe / disruptor-map-merge (monthly Disruptor Lens universe build).

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

# LEGACY-9 method set — used ONLY for signal typing (deep_value vs catalyst), never for selection.
DEEP_VAL = {"epv", "graham_revised", "iv15_deep_value", "acquirers_multiple",
            "earnings_yield_gap", "owner_earnings", "dcf_fcff", "rd_capitalized_dcf", "ev_gross_profit"}
# 8e: convergence (multi-model agreement — the purest value signal in the system) and the true
# EV/GP basket are VALUE signals too; without this they were branded "catalyst" and routed down
# the Moderator's catalyst lens.
VALUE_SIGNAL_METHS = DEEP_VAL | {"convergence", "ev_gp"}

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


def _fmp_segments(sym):
    """Best-effort FMP product-segmentation -> compact 'Segment: revenue (share%)' block for segment SoP.
    Returns '' on any failure (degrade gracefully, like the transcript fetch)."""
    key = E.get_key("FMP_API_KEY")
    if not key:
        return ""
    try:
        r = requests.get("https://financialmodelingprep.com/stable/revenue-product-segmentation",
                         params={"symbol": sym, "period": "annual", "apikey": key}, timeout=20).json()
    except Exception:
        return ""
    if not (isinstance(r, list) and r and isinstance(r[0], dict)):
        return ""
    latest = r[0]
    data = latest.get("data")
    if not isinstance(data, dict):
        for v in latest.values():
            if isinstance(v, dict):
                data = v
                break
    if not isinstance(data, dict):
        return ""
    segs = [(k, float(v)) for k, v in data.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v]
    if len(segs) < 2:   # one "segment" = no SoP signal
        return ""
    segs.sort(key=lambda kv: -abs(kv[1]))
    total = sum(abs(v) for _, v in segs) or 1.0

    def _a(v):
        a = abs(v)
        return f"{v/1e9:.2f}B" if a >= 1e9 else (f"{v/1e6:.0f}M" if a >= 1e6 else f"{v:.0f}")
    body = " | ".join(f"{k}: {_a(v)} ({v/total*100:.0f}%)" for k, v in segs[:8])
    asof = latest.get("date") or latest.get("fiscalYear") or ""
    return ("\n\n=== SEGMENT REVENUE (FMP, " + str(asof) + " — build a TRUE segment Sum-of-Parts: "
            "value each segment by its peer multiple, then sum) ===\n" + body)


_RADAR_FIELDS = ("p_fcf", "dcf_fcff_mos", "epv_mos", "graham_revised_mos", "owner_earnings_mos",
                 "iv15_deep_value_mos", "revenue_yoy", "revenue_cagr_3y", "eps_yoy", "gross_margin",
                 "net_margin", "roic_avg", "altman_z", "sma200", "proximity_52wk", "sector_momentum")


def merge_radar():
    """Merge the chunked Radar shards (_opus_debate/_pg_*.json) into peer_groups.json,
    deterministically. The Radar runs as N parallel Sonnet agents (one per sector chunk); merging by
    an LLM would force it to re-emit all ~160 entries in one response, which TRUNCATES — so it is a
    plain dict-update here. Invoked as the final step of the Radar phase via this allowlisted CLI."""
    import glob
    out, shards = {}, sorted(glob.glob(str(ROOT / "_pg_*.json")))
    for f in shards:
        try:
            d = json.load(open(f, encoding="utf-8"))
            if isinstance(d, dict):
                out.update(d)
        except Exception as e:
            print(f"  WARN: {os.path.basename(f)} skipped ({e})")
    (ROOT / "peer_groups.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also explode to per-symbol files: the combined 161-entry file is ~29k tokens, over the 25k Read
    # cap, so each debate agent reads ONLY its own small entry from peer_groups/<sym>.json.
    pgd = ROOT / "peer_groups"
    pgd.mkdir(exist_ok=True)
    for _sym, _e in out.items():
        try:
            (pgd / f"{_sym}.json").write_text(json.dumps(_e, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    print(f"merged {len(shards)} Radar shards -> peer_groups.json ({len(out)} entries) + per-symbol files")
    return len(out)


def _val_money(s):
    """Parse a CRO fair-value string ('~$12-13', '$78-88 (base case ~$82)', '$12.5') to a float."""
    import re
    if s is None:
        return None
    txt = str(s)
    m = re.search(r'base[^$0-9]{0,14}\$?\s*([0-9]+(?:\.[0-9]+)?)', txt, re.I)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    vals = []
    for n in re.findall(r'([0-9]+(?:\.[0-9]+)?)', txt):
        try:
            vals.append(float(n))
        except Exception:
            pass
    if not vals:
        return None
    if len(vals) >= 2 and vals[1] <= vals[0] * 3:   # 'lo-hi' range -> midpoint
        return round((vals[0] + vals[1]) / 2, 2)
    return vals[0]


def _funded_leverage(symbols):
    """Net-funded-debt/EBITDA + interest coverage (TTM, FMP /stable/) per symbol, cached to
    funded_leverage.json. Funded debt = interest-bearing only, so settlement/payroll float and
    policyholder reserves are structurally excluded — a cleaner solvency test than Altman-Z (which
    uses total liabilities and over-penalizes float/reserve businesses)."""
    import concurrent.futures
    cache_p = ROOT / "funded_leverage.json"
    cache = {}
    if cache_p.exists():
        try:
            cache = json.load(open(cache_p, encoding="utf-8"))
        except Exception:
            cache = {}
    key = os.environ.get("FMP_API_KEY") or "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
    todo = [s for s in symbols if s not in cache]

    def one(sym):
        nd = ic = None
        try:
            km = requests.get("https://financialmodelingprep.com/stable/key-metrics-ttm",
                              params={"symbol": sym, "apikey": key}, timeout=15).json()
            if isinstance(km, list) and km:
                nd = km[0].get("netDebtToEBITDATTM")
        except Exception:
            pass
        try:
            r = requests.get("https://financialmodelingprep.com/stable/ratios-ttm",
                             params={"symbol": sym, "apikey": key}, timeout=15).json()
            if isinstance(r, list) and r:
                ic = r[0].get("interestCoverageRatioTTM")
        except Exception:
            pass
        return sym, {"net_funded_debt_ebitda": nd, "interest_coverage": ic}

    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for sym, v in ex.map(one, todo):
                cache[sym] = v
        cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def _funded_solvency(sector, ndE, icov):
    """Bucket funded leverage: financials exempt; <0 or <=2x w/ healthy coverage = strong;
    <=3.5x w/ >=3x coverage = moderate; else weak (the joint-weakness near-veto candidates)."""
    if "financ" in (sector or "").lower():
        return "exempt_financial"
    if not isinstance(ndE, (int, float)):
        return "unknown"
    if ndE < 0 or (ndE <= 2.0 and (not isinstance(icov, (int, float)) or icov >= 4)):
        return "strong"
    if ndE <= 3.5 and (not isinstance(icov, (int, float)) or icov >= 3):
        return "moderate"
    return "weak"


VALUE_DIRECTOR_PROMPT = """You are the SPECULAIR VALUE DIRECTOR (Claude Opus 4.8), allocating REAL capital on a PURE VALUE rubric with the CATALYST_WATCH_REGIME overlay FULLY REMOVED (a live catalyst is neither a plus nor a requirement). Read backend/_opus_debate/value_grade_input.json — one row per debated name, every field pre-computed.

SYSTEM OF RECORD (decisive — read FIRST). The multi-agent DEBATE already ran on each name. When the debate conflicts with the raw scan factors, THE DEBATE WINS:
  - `sop_mos_pct` (the CRO's reconciled sop_fair_value expressed as MoS vs price) is the SYSTEM-OF-RECORD margin of safety, NOT the 5-method `mos_spread` (that is the RAW scan MoS and can be built on stale/peak inputs). Where sop_mos_pct sits FAR BELOW the raw scan MoS (see `scan_headline_mos_pct`), the raw MoS is an ARTIFACT — trust sop_mos_pct.
  - `forensic_gate`: "EXCLUDE" => INELIGIBLE for the apex (interrogator credibility<=2 — a forensic red flag the factors miss). "CAP" => value_score capped at ~50 (DETERIORATING trajectory: credible but worsening). These are regime-INDEPENDENT forensics; a factor-cheap name NEVER overrides them.
  - `debate_verdict` letter: set partly under the (now-removed) catalyst regime, so it is NOT a blanket cap. BUT a verdict-C name is eligible ONLY if its CRO-normalized `sop_mos_pct` is genuinely positive AND it clears the forensic gate AND it is not a peak/stale artifact — otherwise the C is just confirming the raw MoS is fake. Name in the value_memo every verdict-C name you keep and justify it on pure-value grounds.
  - `value_conviction` (1-5, when present): the CRO's CATALYST-BLIND value score — judged on valuation + forensics with the regime overlay explicitly ignored. PREFER it over `debate_conviction` everywhere in this rubric (debate_conviction is regime-tilted and collapses to a constant in catalyst-light pools). Where value_conviction is null (older results), fall back to debate_conviction but say so.

RUBRIC — four pillars ~25 pts each, applied ONLY to names that clear the gate:
1. MARGIN OF SAFETY — primary = sop_mos_pct (CRO-normalized). Cross-check `mos_spread` AGREEMENT (4-5/5 models positive = high-confidence cheap) but DISCOUNT any model MoS on a name flagged peak/stale below. CRO-ONLY LEG: a name with <=2/5 positive model MoS AND a scan MoS below ~+10% (`scan_headline_mos_pct`) means your SoP is the SOLE evidence of cheapness — you may seat it, but you MUST set its `size_units` <= 0.5, tag it by name in the memo, and state in one sentence why your SoP beats five dissenting models.
2. CYCLICAL-PEAK vs DURABLE-GROWTH — apply BEFORE crediting any cheapness. `peak_flag`=true (eps_peak_ratio>=1.4 OR fcf_cagr_3y>=60%) means the latest earnings sit far above the multi-year base — you MUST distinguish two cases, because the flag fires on BOTH:
   (a) CYCLICAL PEAK / recovery artifact = peak_flag AND (`freshness_stale`=true [FY numerator > live TTM, or latest_q_eps_yoy<=-15%] OR weak/negative `revenue_cagr_3y` OR a commodity/cyclical end-market). Earnings are at a cycle high and ALREADY ROLLING OVER. NORMALIZE to mid-cycle (use `eps_normalized`, not `fy_eps`) and treat the headline multiple as FAKE-cheap. These are the BRBR/CALM artifacts (CALM eps_peak_ratio ~9 on the egg windfall; both rolling over). A low multiple on peak earnings is NOT value.
   (b) DURABLE GROWTH = peak_flag BUT `freshness_stale`=false (still growing, positive latest-Q YoY) AND durable positive `revenue_cagr_3y` AND healthy ROIC. The high ratio reflects a secular re-rate or a real turnaround (a brand compounding), NOT a cycle peak — do NOT normalize it away; credit it, but sanity-check the multiple vs true peers.
   In BOTH cases `sop_mos_pct` (the CRO's already-normalized fair value) is the ANCHOR: if the CRO normalized the name and STILL shows a positive MoS, the cheapness is real; if the CRO's MoS collapsed far below `scan_headline_mos_pct`, it was a peak artifact.
   (c) STALE ANCHOR: `freshness_stale`=true AND `eps_peak_ratio` >= ~1.8 AND the load-bearing catalyst already FIRED means the CRO fair value itself may be built on PRE-EVENT segments (pre-spin/pre-divestiture share count + EBITDA) — treat `sop_mos_pct` as PROVISIONAL, set `size_units` <= 0.5, and say so in the thesis (e.g. CMCSA post-Versant).
3. FUNDED-LEVERAGE SOLVENCY (this REPLACES raw Altman-Z, which uses total liabilities and over-penalizes float/reserve businesses). Judge solvency on FUNDED debt only — `net_funded_debt_ebitda` (net interest-bearing debt / EBITDA, so settlement/payroll float and policyholder reserves are structurally excluded) + `interest_coverage`; the `funded_solvency` field pre-buckets it. IGNORE raw `altman_z`.
   - `is_financial`=true (banks/insurers) OR `funded_solvency` in {exempt_financial, strong}: solvency is FINE — do NOT penalize. This clears EEFT/TNET (~0.8-1.6x funded, strong coverage), SCR.PA and the bank/insurer set on the RIGHT basis (their low Altman-Z was a float/reserve artifact), and any net-cash name.
   - REAL-funded-debt names (`funded_solvency` = moderate or weak): drop the Z number and near-VETO ONLY when the metrics are JOINTLY weak — high funded leverage (net_funded_debt_ebitda > ~3.5x) AND thin coverage (interest_coverage < ~3x) AND a near-term MATURITY WALL (check the name's dossier at backend/_opus_debate/dossiers/<SYM>.md for refinancing/maturity risk). ONE weak metric alone is NOT a veto: a 2-3x-levered name with healthy coverage and no wall is acceptable value — just note the leverage in the thesis. (Worked example: SAX.DE ~3.0x / 3.7x coverage = the book's most-levered name → keep only if the dossier shows no near maturity wall.)
   - `net_debt_exceeds_mktcap`=true remains a thin-equity flag — NEVER credit net debt as "net cash."
4. MULTIPLES vs TRUE PEERS (`peer_verdict`/`peer_relative_comps`) + GROWTH DURABILITY/QUALITY (durable positive revenue/EPS growth + ROIC>~8-10% SUPPORT value; negative 3yr revenue CAGR + sub-WACC ROIC + thin/eroding margins = a value trap even when optically cheap).

HARD CONSTRAINTS: <=3 names per sector. Every apex name must (a) clear forensic_gate, (b) survive cyclical-peak normalization with a STILL-POSITIVE normalized MoS, (c) be cheap on TRUE peers, (d) not be a value trap.

HIDDEN-FACTOR CORRELATION STRESS (run over the final 10 BEFORE sizing — the <=3/sector cap is NOT a correlation control; GICS sectors miss shared real-world factors). Decompose the 10 on HIDDEN factors: (a) END-MARKET DEMAND CYCLE (consumer-discretionary / travel / housing), (b) REGULATORY or REIMBURSEMENT REGIME (e.g. US hospital Medicaid Directed-Payment-Program / a 2028 reimbursement ruling), (c) ADVERTISING CYCLE (cable & theme-park ad spend, out-of-home advertising), (d) RATE / CREDIT sensitivity, (e) a SINGLE shared macro (one commodity, one FX, one policy). FLAG every hidden factor carrying >=2 names. Known live clusters to check EXPLICITLY: THC+UHS (both ride the 2028 Medicaid-DPP / US hospital-reimbursement outcome) and CMCSA+SAX.DE (both advertising-cycle — cable ads + theme-park spend, and out-of-home advertising). For each >=2 cluster, EITHER (i) DIVERSIFY: swap the lower-value leg for the best orthogonal eligible name / runner-up that does NOT re-cluster (note ARDT re-clusters with hospitals, SREN.SW with SCR.PA reinsurance), OR (ii) keep both ONLY with an explicit combined-size cap + written justification — no hidden factor may quietly carry two full-size legs. A single reimbursement ruling or an ad-recession must not hit two legs at once. Every keep-with-combined-size-cap resolution MUST appear in the output `combined_caps` as NUMBERS (not prose): combined_caps:[{names:[...], max_units(float), axis(str)}] — prose-only caps are a spec violation.

OUTPUT — Write VALID JSON to backend/_opus_debate/apex_basket_value.json = {apex_basket:[{symbol, sector, value_score(0-100), thesis(one sentence), mos_agreement(e.g. "4/5"), sop_mos_pct, net_funded_debt_ebitda, interest_coverage, funded_solvency, peer_verdict, growth_durability, peak_normalized(bool: did you have to discount peak/stale earnings), exposure_axes(list of the hidden factors this name carries, e.g. ["hospital-reimbursement","advertising-cycle"]), size_units(float 0.1-1.5: 1.0=full unit, 0.5=half — the SAME sizing you justified in the memo; every CRO-only leg, stale anchor, and combined-cap member MUST carry its number here), thesis_break_px(number: the price at which the thesis is BROKEN, from your downside-to-break — below it the name exits at the next review), bear_fv_px(number: your adverse-SoP per-share value, used for the market stress test), forensic_gate, trap_flag}], runner_ups:[...~6], combined_caps:[{names:[...], max_units(float), axis(str)}], value_memo}. The value_memo MUST: (a) state the rubric weighting; (b) LIST the names EXCLUDED or CAPPED by the forensic gate and those down-rated as cyclical-peak/stale artifacts — call out BRBR and CALM EXPLICITLY with their CRO-normalized fair value vs the raw scan MoS; (c) give the name-by-name RISE/FALL vs the prior value apex (the caller specifies the prior apex in the run instruction; if none is given, read the existing backend/_opus_debate/apex_basket_value.json for the prior slate BEFORE you overwrite it); (d) a correlation_stress section naming EACH hidden-factor cluster of >=2 (INCLUDING the THC/UHS reimbursement and CMCSA/SAX.DE advertising pairs) and EXACTLY how you resolved it (diversified -> which swap and why; or kept-with-sizing -> the combined cap and the justification); (e) a BEAR REBUTTAL subsection: ONE sentence per apex seat stating the STRONGEST reason that pick is wrong, written BEFORE final sizing — if you cannot articulate the bear in one sentence, you do not understand the position. Reply exactly: DONE"""


def value_input():
    """Build value_grade_input.json: per DEBATED name, the VALUE-rubric metrics PLUS the four
    robustness signal families the raw-MoS pillar was missing — (1) cyclical-peak/extrapolation
    (EPS-history peak ratio + FCF 3yr CAGR), (2) TTM-vs-FY freshness (stale numerator), (3) the
    forensic gate (interrogator credibility/trajectory + verdict), (4) the CRO sop_fair_value as the
    system-of-record MoS that overrides the raw scan MoS. Also writes value_director_prompt.txt so the
    value re-grade is one reproducible low-rate agent call."""
    import glob
    import re
    import statistics
    uni = {s["symbol"]: s for s in json.load(open(ROOT / "_radar_universe.json", encoding="utf-8"))}
    scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
        open("../frontend/public/latest_global.json", encoding="utf-8"))
    sc_by = {s.get("symbol"): s for s in scan.get("stocks", [])}
    res_files = sorted(glob.glob(str(ROOT / "results_regime" / "*.json")))
    fl = _funded_leverage([os.path.basename(f)[:-5] for f in res_files])
    out = []
    for f in res_files:
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or os.path.basename(f)[:-5]
        u = uni.get(sym, {})
        s = sc_by.get(sym, {})
        pg = {}
        pgp = ROOT / "peer_groups" / f"{sym}.json"
        if pgp.exists():
            try:
                pg = json.load(open(pgp, encoding="utf-8"))
            except Exception:
                pg = {}
        ms = ""
        bp = ROOT / "inputs" / f"{sym}.json"
        if bp.exists():
            try:
                ms = json.load(open(bp, encoding="utf-8")).get("metrics_str", "")
            except Exception:
                ms = ""

        def _f(pat, cast=float):
            m = re.search(pat, ms)
            if not m:
                return None
            try:
                return cast(m.group(1))
            except Exception:
                return None

        ttm_note = (re.search(r'(TTM FCF[^\n]*)', ms) or [None])
        ttm_note = ttm_note.group(1).strip()[:160] if hasattr(ttm_note, "group") else ""
        ttm_eps = _f(r'TTM diluted EPS\s*(-?[0-9.]+)')
        lq_eps_yoy = _f(r'latest-Q EPS YoY\s*(-?[0-9.]+)%')
        scan_mos_head = _f(r'Margin of Safety\s*(-?[0-9.]+)%')
        fcf_cagr_3y = _f(r'FCF growth:[^\n]*3-yr CAGR\s*([+\-]?[0-9.]+)%')
        # EPS history (cyclical-peak) from the scan's buffett_history
        bh = (s.get("buffett_history") or {}).get("rows") or []
        eps_hist = [row.get("eps") for row in bh if isinstance(row.get("eps"), (int, float))]
        eps_latest = eps_hist[-1] if eps_hist else None
        eps_norm = eps_peak_ratio = None
        if len(eps_hist) >= 3:
            pos = [e for e in eps_hist[:-1] if e and e > 0]
            if pos:
                eps_norm = round(statistics.median(pos), 3)
                if eps_latest and eps_latest > 0 and eps_norm > 0:
                    eps_peak_ratio = round(eps_latest / eps_norm, 2)
        net_debt = s.get("net_debt")
        mktcap = s.get("market_cap")
        price = s.get("price") or u.get("price")
        net_debt_gt_mktcap = bool(isinstance(net_debt, (int, float)) and isinstance(mktcap, (int, float))
                                  and net_debt > 0 and net_debt > mktcap)
        sop_num = _val_money(r.get("sop_fair_value"))
        sop_mos = round((sop_num - price) / price * 100, 1) if (sop_num and isinstance(price, (int, float)) and price > 0) else None
        freshness_stale = False
        fresh_note = ""
        if isinstance(eps_latest, (int, float)) and isinstance(ttm_eps, (int, float)) and ttm_eps > 0 and eps_latest > ttm_eps * 1.15:
            freshness_stale = True
            fresh_note = f"FY EPS {eps_latest} vs live TTM {ttm_eps} (+{round((eps_latest/ttm_eps-1)*100)}%)"
        if isinstance(lq_eps_yoy, (int, float)) and lq_eps_yoy <= -15:
            freshness_stale = True
            fresh_note = (fresh_note + "; " if fresh_note else "") + f"latest-Q EPS YoY {lq_eps_yoy}%"
        peak_flag = bool((eps_peak_ratio and eps_peak_ratio >= 1.4)
                         or (isinstance(fcf_cagr_3y, (int, float)) and fcf_cagr_3y >= 60))
        iscore = r.get("interrogator_score")
        traj = (r.get("trajectory") or "").upper()
        verdict = (r.get("verdict") or "").upper()
        # Forensic gate = regime-INDEPENDENT veto (credibility + trajectory), NOT the verdict letter
        # (the A/B/C was set partly under the now-stripped catalyst regime). The verdict is surfaced
        # for the system-of-record reconciliation but is not a blanket cap.
        if isinstance(iscore, (int, float)) and iscore <= 2:
            gate = "EXCLUDE"            # credibility veto — a forensic red flag the factors miss
        elif iscore is None:
            # 8f: a malformed/missing CREDIBILITY_SCORE must NOT fail open as neutral —
            # cap it (fail toward caution) and say so, without nuking the name on a transient.
            gate = "CAP"
            print(f"WARN: {sym} interrogator_score missing/unparseable -> gate=CAP (fail-closed)")
        elif "DETERIORAT" in traj:
            gate = "CAP"               # deteriorating but credible -> mid-tier cap, not a veto
        else:
            gate = ""
        mos = {k: round(u[k], 3) for k in ("dcf_fcff_mos", "epv_mos", "graham_revised_mos",
                                           "owner_earnings_mos", "iv15_deep_value_mos")
               if isinstance(u.get(k), (int, float))}
        flv = fl.get(sym, {})
        ndE = flv.get("net_funded_debt_ebitda")
        icov = flv.get("interest_coverage")
        is_fin = "financ" in (r.get("sector", "") or "").lower()
        funded_solv = _funded_solvency(r.get("sector", ""), ndE, icov)
        out.append({
            "symbol": sym, "sector": r.get("sector", ""),
            "mos_spread": mos, "altman_z": u.get("altman_z"), "p_fcf": u.get("p_fcf"),
            "revenue_yoy": u.get("revenue_yoy"), "revenue_cagr_3y": u.get("revenue_cagr_3y"),
            "eps_yoy": u.get("eps_yoy"), "roic_avg": u.get("roic_avg"),
            "net_margin": u.get("net_margin"), "gross_margin": u.get("gross_margin"),
            "peer_verdict": pg.get("verdict", ""),
            "peer_relative_comps": (pg.get("relative_comps", "") or "")[:400],
            # system of record: CRO fair value + debate forensics override the raw scan MoS
            "sop_fair_value": r.get("sop_fair_value", ""), "sop_mos_pct": sop_mos,
            "price": price, "scan_headline_mos_pct": scan_mos_head,
            "risk_reward": (r.get("risk_reward", "") or "")[:220],
            "debate_verdict": verdict, "debate_conviction": r.get("conviction"),
            # 8a: value_conviction = the CRO's catalyst-blind value score (decoupled from the
            # regime-tilted `conviction`); older results lack it -> None, Director falls back.
            "value_conviction": r.get("value_conviction"),
            "interrogator_score": iscore, "trajectory": r.get("trajectory", ""),
            "forensic_gate": gate,
            # cyclical-peak / extrapolation normalization (ahead of trusting MoS)
            "eps_history": eps_hist[-5:], "eps_normalized": eps_norm, "eps_peak_ratio": eps_peak_ratio,
            "fcf_cagr_3y": fcf_cagr_3y, "peak_flag": peak_flag,
            # TTM-vs-FY freshness (stale numerator)
            "ttm_note": ttm_note, "ttm_eps": ttm_eps, "fy_eps": eps_latest,
            "latest_q_eps_yoy": lq_eps_yoy, "freshness_stale": freshness_stale, "freshness_note": fresh_note,
            # solvency: funded-leverage (interest-bearing debt only; float/reserves netted out) replaces raw Altman-Z
            "net_funded_debt_ebitda": round(ndE, 2) if isinstance(ndE, (int, float)) else None,
            "interest_coverage": round(icov, 1) if isinstance(icov, (int, float)) else None,
            "is_financial": is_fin, "funded_solvency": funded_solv,
            # leverage (BRBR net-debt-not-net-cash)
            "net_debt": net_debt, "market_cap": mktcap, "net_debt_exceeds_mktcap": net_debt_gt_mktcap,
        })
    (ROOT / "value_grade_input.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    prompt_txt = VALUE_DIRECTOR_PROMPT
    pa = ROOT / "apex_basket_value.json"                # Fix 4 feed-forward: prior MEASURED correlations
    if pa.exists():
        try:
            pc = json.load(open(pa, encoding="utf-8")).get("correlation") or {}
            if pc.get("avg_pairwise") is not None:
                fl = pc.get("flagged_pairs") or []
                lines = [f"  {f['a']}-{f['b']}: {f['corr']}" + (" [BREACH]" if f.get("breach") else "") for f in fl[:12]]
                prompt_txt += ("\n\nPRIOR-RUN MEASURED CORRELATIONS (2y weekly log returns; argue your hidden-factor "
                               f"stress AGAINST these real numbers, do not merely assert 'barely co-move'). "
                               f"avg pairwise={pc.get('avg_pairwise')}, max={pc.get('max_pair')}. Pairs >=0.6:\n"
                               + ("\n".join(lines) if lines else "  (none >=0.6 last run)"))
        except Exception:
            pass
    (ROOT / "value_director_prompt.txt").write_text(prompt_txt, encoding="utf-8")
    npeak = sum(1 for x in out if x["peak_flag"])
    ngate = sum(1 for x in out if x["forensic_gate"])
    nstale = sum(1 for x in out if x["freshness_stale"])
    from collections import Counter as _C
    fs = _C(x["funded_solvency"] for x in out)
    print(f"value_grade_input.json: {len(out)} names | peak_flag={npeak} forensic_gate={ngate} freshness_stale={nstale}")
    print(f"  funded_solvency: {dict(fs)}")

    # ── 11a — weekly FUNNEL-QUALITY stats: is the scan's headline MoS a ranking signal or only a
    # membership filter? (Measured 2026-06-10: Spearman 0.41 overall but 0.15 in the scan top
    # quintile; 61% of scan-positive names cut >50% by the CRO — magnitude carries no in-funnel
    # ranking signal. These make that measurable EVERY week.) Pure-python Spearman, no scipy.
    def _spearman(pairs):
        if len(pairs) < 10:
            return None
        import statistics as _st

        def _ranks(vals):
            order = sorted(range(len(vals)), key=lambda i: vals[i])
            rk = [0.0] * len(vals)
            i = 0
            while i < len(order):
                j = i
                while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                    j += 1
                avg = (i + j) / 2 + 1
                for k in range(i, j + 1):
                    rk[order[k]] = avg
                i = j + 1
            return rk
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        try:
            return round(_st.correlation(_ranks(xs), _ranks(ys)), 3)
        except Exception:
            return None

    both = [(x["scan_headline_mos_pct"], x["sop_mos_pct"]) for x in out
            if isinstance(x.get("scan_headline_mos_pct"), (int, float)) and isinstance(x.get("sop_mos_pct"), (int, float))]
    sp_all = _spearman(both)
    topq = sorted(both, key=lambda p: -p[0])[:max(5, len(both) // 5)]
    sp_topq = _spearman(topq)
    pos = [p for p in both if p[0] > 0]
    collapse = sum(1 for p in pos if p[1] < p[0] * 0.5)
    artifact = sum(1 for p in pos if p[1] <= 0)
    rescues = [x["symbol"] for x in out
               if isinstance(x.get("scan_headline_mos_pct"), (int, float)) and isinstance(x.get("sop_mos_pct"), (int, float))
               and x["scan_headline_mos_pct"] <= 10 and x["sop_mos_pct"] >= 30]
    funnel_stats = {"n_both": len(both), "spearman_scan_vs_cro": sp_all, "spearman_top_quintile": sp_topq,
                    "collapse_rate_50": round(collapse / len(pos), 3) if pos else None,
                    "artifact_rate": round(artifact / len(pos), 3) if pos else None,
                    "cross_lens_rescues": {"n": len(rescues), "symbols": sorted(rescues)},
                    "note": "scan MoS = membership/divergence signal only; never a rank or weight"}
    (ROOT / "_funnel_stats.json").write_text(json.dumps(funnel_stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  funnel: spearman={sp_all} (top-quintile {sp_topq}) collapse>50%={funnel_stats['collapse_rate_50']} "
          f"artifact={funnel_stats['artifact_rate']} rescues={len(rescues)} {sorted(rescues)}")

    # ── 11c — FORENSIC LEDGER: persist EXCLUDE gates so prep() can route unexpired ones to a short
    # re-check instead of a full debate. A ledger_recheck re-affirmation does NOT extend the clock —
    # only a FULL debate that again scores <=2 restarts the 8-week TTL.
    from datetime import datetime as _dtt, timedelta as _td
    led_p = ROOT / "forensic_ledger.json"
    led = {}
    if led_p.exists():
        try:
            led = json.load(open(led_p, encoding="utf-8"))
        except Exception:
            led = {}
    today_s = _dtt.now().strftime("%Y-%m-%d")
    for x in out:
        if x["forensic_gate"] != "EXCLUDE":
            continue
        sym = x["symbol"]
        src = ""
        rf = ROOT / "results_regime" / f"{sym}.json"
        if rf.exists():
            try:
                src = json.load(open(rf, encoding="utf-8")).get("source", "")
            except Exception:
                src = ""
        if sym in led and src == "ledger_recheck":
            continue                                       # re-affirmation: keep the original clock
        led[sym] = {"gate": "EXCLUDE", "date": today_s,
                    "reason": f"interrogator credibility {x.get('interrogator_score')} | {x.get('trajectory', '')}",
                    "expires": (_dtt.now() + _td(days=56)).strftime("%Y-%m-%d"),
                    "days_to_earnings": (sc_by.get(sym) or {}).get("days_to_earnings")}
    led = {s: e for s, e in led.items() if (e.get("expires") or "") >= today_s}   # prune expired
    led_p.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  forensic ledger: {len(led)} unexpired EXCLUDE entr{'y' if len(led) == 1 else 'ies'} -> {led_p.name}")
    print(f"value_director_prompt.txt written ({len(VALUE_DIRECTOR_PROMPT)} chars)")
    return len(out)


def value_csv():
    """CSV of the VALUE apex (apex_basket_value.json) with the FULL output of every agent per name —
    Radar / Interrogator / Architect / Catalyst / CRO + the value-Director's per-name grade — plus the
    value_memo companion. Rows ordered by value_score desc; in_regime_apex flags cross-lens overlap."""
    import csv
    apex = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    picks = [p for p in apex.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    regime = set()
    rapx = ROOT / "apex_basket_opus_regime.json"
    if rapx.exists():
        try:
            regime = {p.get("symbol") for p in json.load(open(rapx, encoding="utf-8")).get("apex_basket", []) if isinstance(p, dict)}
        except Exception:
            regime = set()
    gin = {}
    if (ROOT / "value_grade_input.json").exists():
        try:
            gin = {x["symbol"]: x for x in json.load(open(ROOT / "value_grade_input.json", encoding="utf-8"))}
        except Exception:
            gin = {}
    cols = ["rank", "symbol", "sector", "value_score", "in_regime_apex", "value_thesis", "mos_agreement",
            "altman_z", "net_funded_debt_ebitda", "interest_coverage", "funded_solvency",
            "sop_mos_pct", "scan_headline_mos_pct", "forensic_gate", "peak_normalized",
            "peak_flag", "eps_peak_ratio", "freshness_stale", "peer_verdict_director", "growth_durability", "exposure_axes",
            "size_units_effective", "weight_pct", "mos_agreement_n", "cro_only", "stale_anchor", "corr_flag", "entry_plan", "trap_flag",
            "debate_verdict", "debate_conviction", "catalyst_status", "sop_fair_value", "sop_breakdown",
            "risk_reward", "peer_comps_note", "radar_peers", "radar_relative_comps", "radar_verdict",
            "radar_rationale", "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "consensus_delta",
            "valley_of_death", "positioning_washout", "forcing_function", "moderator_conclusion",
            "interrogator_score", "trajectory", "interrogator_dossier"]
    rows = []
    for rank, p in enumerate(sorted(picks, key=lambda x: -(x.get("value_score") or 0)), 1):
        sym = p["symbol"]
        r = {}
        if (ROOT / "results_regime" / f"{sym}.json").exists():
            try:
                r = json.load(open(ROOT / "results_regime" / f"{sym}.json", encoding="utf-8"))
            except Exception:
                r = {}
        doss = ""
        if (ROOT / "dossiers" / f"{sym}.md").exists():
            doss = (ROOT / "dossiers" / f"{sym}.md").read_text(encoding="utf-8")
        pg = {}
        if (ROOT / "peer_groups" / f"{sym}.json").exists():
            try:
                pg = json.load(open(ROOT / "peer_groups" / f"{sym}.json", encoding="utf-8"))
            except Exception:
                pg = {}
        rows.append({
            "rank": rank, "symbol": sym, "sector": p.get("sector", ""), "value_score": p.get("value_score", ""),
            "in_regime_apex": sym in regime, "value_thesis": p.get("thesis", "") or p.get("value_thesis", ""),
            "mos_agreement": p.get("mos_agreement", ""), "altman_z": p.get("altman_z", ""),
            "net_funded_debt_ebitda": p.get("net_funded_debt_ebitda", gin.get(sym, {}).get("net_funded_debt_ebitda", "")),
            "interest_coverage": p.get("interest_coverage", gin.get(sym, {}).get("interest_coverage", "")),
            "funded_solvency": p.get("funded_solvency", gin.get(sym, {}).get("funded_solvency", "")),
            "sop_mos_pct": p.get("sop_mos_pct", gin.get(sym, {}).get("sop_mos_pct", "")),
            "scan_headline_mos_pct": gin.get(sym, {}).get("scan_headline_mos_pct", ""),
            "forensic_gate": p.get("forensic_gate", gin.get(sym, {}).get("forensic_gate", "")),
            "peak_normalized": p.get("peak_normalized", ""),
            "peak_flag": gin.get(sym, {}).get("peak_flag", ""),
            "eps_peak_ratio": gin.get(sym, {}).get("eps_peak_ratio", ""),
            "freshness_stale": gin.get(sym, {}).get("freshness_stale", ""),
            "peer_verdict_director": p.get("peer_verdict", ""), "growth_durability": p.get("growth_durability", ""),
            "exposure_axes": "; ".join(p["exposure_axes"]) if isinstance(p.get("exposure_axes"), list) else (p.get("exposure_axes", "") or ""),
            "size_units_effective": p.get("size_units_effective", ""), "weight_pct": p.get("weight_pct", ""),
            "mos_agreement_n": p.get("mos_agreement_n", ""), "cro_only": p.get("cro_only", ""),
            "stale_anchor": p.get("stale_anchor", ""), "corr_flag": p.get("corr_flag", ""),
            "entry_plan": p.get("entry_plan", ""),
            "trap_flag": p.get("trap_flag", ""),
            "debate_verdict": r.get("verdict", ""), "debate_conviction": r.get("conviction", ""),
            "catalyst_status": r.get("catalyst_status", ""), "sop_fair_value": r.get("sop_fair_value", ""),
            "sop_breakdown": r.get("sop_breakdown", ""), "risk_reward": r.get("risk_reward", ""),
            "peer_comps_note": r.get("peer_comps_note", ""),
            "radar_peers": ", ".join(pg.get("peers", [])) if isinstance(pg.get("peers"), list) else "",
            "radar_relative_comps": pg.get("relative_comps", ""), "radar_verdict": pg.get("verdict", ""),
            "radar_rationale": pg.get("rationale", ""), "bull_thesis": r.get("bull_thesis", ""),
            "bear_thesis": r.get("bear_thesis", ""), "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""),
            "consensus_delta": r.get("consensus_delta", ""), "valley_of_death": r.get("valley_of_death", ""),
            "positioning_washout": r.get("positioning_washout", ""), "forcing_function": r.get("forcing_function", ""),
            "moderator_conclusion": r.get("moderator_conclusion", ""), "interrogator_score": r.get("interrogator_score", ""),
            "trajectory": r.get("trajectory", ""), "interrogator_dossier": doss,
        })
    out = ROOT / "speculair_value_apex.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    mm = apex.get("value_memo", "")
    (ROOT / "speculair_value_apex_memo.txt").write_text(
        mm if isinstance(mm, str) else json.dumps(mm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} value-apex rows x {len(cols)} cols -> {out}")
    print(f"value_memo -> {ROOT / 'speculair_value_apex_memo.txt'}")
    return len(rows)


def baskets_csv():
    """One CSV joining BASKET MEMBERSHIP (regime apex/runner, value apex/runner, and the 11
    per-methodology baskets) with the FULL debate output (every agent) for ALL debated names —
    'all baskets + all debates' in a single file. Companion to the apex-specific CSVs."""
    import csv
    res_dir, doss_dir, pg_dir = ROOT / "results_regime", ROOT / "dossiers", ROOT / "peer_groups"

    def _roles(path):
        d = {}
        j = json.load(open(ROOT / path, encoding="utf-8")) if (ROOT / path).exists() else {}
        for p in j.get("apex_basket", []):
            if isinstance(p, dict) and p.get("symbol"):
                d[p["symbol"]] = {**p, "_role": "APEX"}
        for p in j.get("runner_ups", []):
            s = p.get("symbol") if isinstance(p, dict) else p
            if s and s not in d:
                d[s] = ({**p} if isinstance(p, dict) else {"symbol": s})
                d[s]["_role"] = "RUNNER_UP"
        return d

    reg = _roles("apex_basket_opus_regime.json")
    val = _roles("apex_basket_value.json")
    gin = {}
    if (ROOT / "value_grade_input.json").exists():
        try:
            gin = {x["symbol"]: x for x in json.load(open(ROOT / "value_grade_input.json", encoding="utf-8"))}
        except Exception:
            gin = {}
    meth_of = {}
    try:
        sb = json.load(open("../frontend/public/speculair_baskets.json", encoding="utf-8"))
        for meth, basket in (sb.get("per_methodology_baskets") or {}).items():
            picks = basket.get("picks") if isinstance(basket, dict) else basket
            for pk in (picks or []):
                s = pk.get("symbol") if isinstance(pk, dict) else pk
                if s:
                    meth_of.setdefault(s, []).append(meth)
    except Exception as e:
        print(f"WARN: per_methodology basket map failed ({e})")
    cols = ["symbol", "sector", "signal_type",
            "regime_role", "regime_director_conviction", "regime_lane", "regime_catalyst_status", "regime_forensic_cap", "regime_director_thesis",
            "value_role", "value_score", "value_thesis", "funded_solvency", "net_funded_debt_ebitda", "interest_coverage",
            "sop_mos_pct", "scan_headline_mos_pct", "forensic_gate", "peak_flag", "freshness_stale", "trap_flag",
            "n_methodology_baskets", "methodology_baskets",
            "verdict", "conviction", "catalyst_status", "sop_fair_value", "risk_reward", "trajectory", "interrogator_score",
            "radar_verdict", "radar_peers", "radar_relative_comps", "radar_rationale",
            "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "sop_breakdown",
            "consensus_delta", "valley_of_death", "positioning_washout", "forcing_function", "moderator_conclusion",
            "peer_comps_note", "interrogator_dossier"]
    rows = []
    for f in sorted(res_dir.glob("*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or f.stem
        rg, vl, gi = reg.get(sym, {}), val.get(sym, {}), gin.get(sym, {})
        doss = (doss_dir / f"{sym}.md").read_text(encoding="utf-8") if (doss_dir / f"{sym}.md").exists() else ""
        pg = {}
        if (pg_dir / f"{sym}.json").exists():
            try:
                pg = json.load(open(pg_dir / f"{sym}.json", encoding="utf-8"))
            except Exception:
                pg = {}
        mb = meth_of.get(sym, [])
        rows.append({
            "symbol": sym, "sector": r.get("sector", ""), "signal_type": r.get("signal_type", ""),
            "regime_role": rg.get("_role", ""), "regime_director_conviction": rg.get("director_conviction", ""),
            "regime_lane": rg.get("lane", ""), "regime_catalyst_status": rg.get("catalyst_status", r.get("catalyst_status", "")),
            "regime_forensic_cap": rg.get("forensic_cap", ""),
            "regime_director_thesis": rg.get("thesis", ""),
            "value_role": vl.get("_role", ""), "value_score": vl.get("value_score", ""), "value_thesis": vl.get("thesis", ""),
            "funded_solvency": gi.get("funded_solvency", ""), "net_funded_debt_ebitda": gi.get("net_funded_debt_ebitda", ""),
            "interest_coverage": gi.get("interest_coverage", ""), "sop_mos_pct": gi.get("sop_mos_pct", ""),
            "scan_headline_mos_pct": gi.get("scan_headline_mos_pct", ""), "forensic_gate": gi.get("forensic_gate", ""),
            "peak_flag": gi.get("peak_flag", ""), "freshness_stale": gi.get("freshness_stale", ""),
            "trap_flag": vl.get("trap_flag", ""),
            "n_methodology_baskets": len(mb), "methodology_baskets": ";".join(mb),
            "verdict": r.get("verdict", ""), "conviction": r.get("conviction", ""), "catalyst_status": r.get("catalyst_status", ""),
            "sop_fair_value": r.get("sop_fair_value", ""), "risk_reward": r.get("risk_reward", ""),
            "trajectory": r.get("trajectory", ""), "interrogator_score": r.get("interrogator_score", ""),
            "radar_verdict": pg.get("verdict", ""),
            "radar_peers": ", ".join(pg.get("peers", [])) if isinstance(pg.get("peers"), list) else "",
            "radar_relative_comps": pg.get("relative_comps", ""), "radar_rationale": pg.get("rationale", ""),
            "bull_thesis": r.get("bull_thesis", ""), "bear_thesis": r.get("bear_thesis", ""),
            "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""), "sop_breakdown": r.get("sop_breakdown", ""),
            "consensus_delta": r.get("consensus_delta", ""), "valley_of_death": r.get("valley_of_death", ""),
            "positioning_washout": r.get("positioning_washout", ""), "forcing_function": r.get("forcing_function", ""),
            "moderator_conclusion": r.get("moderator_conclusion", ""), "peer_comps_note": r.get("peer_comps_note", ""),
            "interrogator_dossier": doss,
        })
    role_rank = {"APEX": 0, "RUNNER_UP": 1, "": 2}
    rows.sort(key=lambda x: (role_rank.get(x["regime_role"], 2), role_rank.get(x["value_role"], 2),
                             -x["n_methodology_baskets"], x["symbol"]))
    out = ROOT / "speculair_baskets_debates.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    n_reg = sum(1 for x in rows if x["regime_role"])
    n_val = sum(1 for x in rows if x["value_role"])
    n_meth = sum(1 for x in rows if x["n_methodology_baskets"])
    print(f"wrote {len(rows)} rows x {len(cols)} cols -> {out}")
    print(f"  basket coverage: regime-tagged={n_reg} value-tagged={n_val} in>=1 methodology basket={n_meth}")
    return len(rows)


def value_publish(push_gcs=False):
    """Stage the public Value Lens payload (frontend/public/speculair_value_apex.json) AND maintain a
    live-forward NAV track record for the value book — a separate chained-NAV state file
    (speculair_value_tracking.json) from the apex, via the same _update_apex_tracking engine."""
    import datetime as _dt
    PUB = E.FRONTEND_DIR / "public"
    apx = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    picks = [p for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    track_in = [{**p, "conviction": p.get("value_score", 0)} for p in picks]   # value_score -> conviction log
    try:
        vt = E._update_apex_tracking(track_in, push_gcs=False,
                                     gcs_path="scans/speculair_value_tracking.json",
                                     local_name="speculair_value_tracking.json")
    except Exception as e:
        print(f"WARN: value tracking failed ({e})")
        vt = {}
    weights = apx.get("weights")                       # fix 5e: parallel WEIGHTED NAV (separate state file)
    vtw = {}
    if weights:
        try:
            vtw = E._update_apex_tracking(track_in, push_gcs=False, weights=weights,
                                          gcs_path="scans/speculair_value_tracking_weighted.json",
                                          local_name="speculair_value_tracking_weighted.json")
        except Exception as e:
            print(f"WARN: weighted value tracking failed ({e})")
    pos = {}
    tp = PUB / "speculair_value_tracking.json"
    if tp.exists():
        try:
            pos = json.load(open(tp, encoding="utf-8")).get("positions", {})
        except Exception:
            pos = {}
    for p in picks:                                   # attach entry for per-pick perf in the card
        pp = pos.get(p["symbol"], {})
        if pp:
            p["entry_price"] = pp.get("entry_price")
            p["entry_date"] = pp.get("entry_date")
    pool_stats = {}                                    # fix 6: honest pool-quality banner
    gp = ROOT / "value_grade_input.json"
    if gp.exists():
        try:
            from collections import Counter as _C
            gin = json.load(open(gp, encoding="utf-8"))
            vc = _C((x.get("debate_verdict") or "?") for x in gin)
            na = vc.get("A", 0)
            gin_by = {x.get("symbol"): x for x in gin}
            apex_verdicts = {(gin_by.get(p["symbol"]) or {}).get("debate_verdict") for p in picks}
            pool_stats = {"n_pool": len(gin), "verdict_counts": dict(vc), "n_verdict_a": na,
                          "apex_all_verdict_b": apex_verdicts == {"B"},
                          "banner": (f"Best-of-B basket: {na} verdict-A names in a {len(gin)}-name pool — "
                                     f"every apex pick is a verdict-B value name. Expect SLOW gap-closure: "
                                     f"margin-of-safety re-rating, no hard catalysts by design.")}
            fst = ROOT / "_funnel_stats.json"
            if fst.exists():
                try:
                    pool_stats["funnel"] = json.load(open(fst, encoding="utf-8"))   # 11a weekly stats
                except Exception:
                    pass
        except Exception:
            pool_stats = {}
    out = {"apex_basket": picks, "runner_ups": apx.get("runner_ups", []),
           "value_memo": apx.get("value_memo", ""), "value_tracking": vt,
           "value_tracking_weighted": vtw, "weights": weights,
           "stress_test": apx.get("stress_test"), "correlation": apx.get("correlation"),
           "exits": apx.get("exits"), "combined_caps": apx.get("combined_caps"),
           "pool_stats": pool_stats,
           "generated_at": _dt.date.today().isoformat(),
           "engine": "opus-4.8-value-funded-leverage", "universe": 161}
    (PUB / "speculair_value_apex.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"value_publish: {len(picks)} apex + {len(out['runner_ups'])} runners | tracking nav={vt.get('nav')} "
          f"since={vt.get('since_inception_pct')}% open={vt.get('n_open')} closed={vt.get('n_closed')} inception={vt.get('inception_date')}")
    if push_gcs:
        import subprocess
        for localf, key in [(PUB / "speculair_value_apex.json", "scans/speculair_value_apex.json"),
                            (PUB / "speculair_value_tracking.json", "scans/speculair_value_tracking.json"),
                            (PUB / "speculair_value_tracking_weighted.json", "scans/speculair_value_tracking_weighted.json")]:
            try:
                # shell=True so Windows resolves gcloud.cmd (and Linux/Cloud Run still works)
                r = subprocess.run(f'gcloud storage cp "{localf}" "gs://screener-signals-carbonbridge/{key}"',
                                   shell=True, capture_output=True, text=True, timeout=120)
                print(f"  GCS push {key}: {'OK' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-140:]}")
            except Exception as e:
                print(f"  GCS push {key} ERR: {e}")
    return len(picks)


def finish_debate():
    """Emit _finish_debate.js: debate ONLY the not-yet-done names (universe minus results_regime),
    reusing the already-built bundles/peer_groups (Radar skipped), batched to dodge the rate limit,
    then the Director over ALL results. For completing a run a transient outage left partial."""
    import glob
    import re
    uni = [s["symbol"] for s in json.load(open(ROOT / "_radar_universe.json", encoding="utf-8"))]
    done = {os.path.basename(f)[:-5] for f in glob.glob(str(ROOT / "results_regime" / "*.json"))}
    missing = [s for s in uni if s not in done]
    fmp = [s for s in missing if (ROOT / "transcripts" / f"{s}.txt").exists()]
    online = [s for s in missing if not (ROOT / "transcripts" / f"{s}.txt").exists()]
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = " + json.dumps(fmp), js)
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(online), js)
    out = ROOT / "_finish_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"FINISH OK: {len(fmp)} FMP + {len(online)} online = {len(missing)} still-missing (of {len(uni)})")
    print(f"FINISH_SCRIPT={out.resolve()}")
    return len(missing)


def value_revalidate():
    """Fix 3 (revalidation half): emit _revalidate_debate.js to re-debate ONLY the stale-anchor
    value-apex names (stamped by _value_post: freshness_stale + eps_peak_ratio>=1.8 + catalyst FIRED)
    on POST-EVENT PRO-FORMA segments. Forces them through the ONLINE path so the agent web-fetches the
    post-spin/post-divestiture financials, and injects a pro-forma instruction into the debate BRIEF.
    The operator runs the emitted script via the Workflow tool; fresh results then flow into value-input
    -> Director. Mirrors finish_debate()."""
    import re
    apx = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    stale = [p["symbol"] for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("stale_anchor")]
    if not stale:
        print("value_revalidate: no stale_anchor names stamped — nothing to revalidate (run value-post first).")
        return 0
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = []", js)                       # force all online
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(stale), js)
    instr = ("REVALIDATION RUN: this name's load-bearing STRUCTURAL EVENT has already FIRED — WebSearch the "
             "POST-EVENT PRO-FORMA financials (post-spin/post-divestiture share count + segment EBITDA + net "
             "debt from the most recent filing AFTER the event date) and rebuild the Sum-of-Parts on THOSE; do "
             "NOT reuse pre-event segment data. State the event date and the pro-forma basis explicitly. ")
    js = re.sub(r'(const BRIEF = ")', lambda m: m.group(1) + instr, js, count=1)
    out = ROOT / "_revalidate_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"value_revalidate: {len(stale)} stale-anchor name(s) {stale} -> online pro-forma re-debate")
    print(f"REVALIDATE_SCRIPT={out.resolve()}")
    return len(stale)


def value_skeptic():
    """8b — SKEPTIC TIER over the value-apex finalists (apex + runner_ups, ~16 names). The weekly
    debate runs Interrogator->Architect->CRO in ONE context, so the 'adversarial' CRO shares the
    bull's activations; this emits an INDEPENDENT kill-tier (the Catalyst Watch Skeptic pattern,
    which kills 40-50% of ACTIVE flags): default REFUTED unless the load-bearing facts verify
    against a primary source; inputs are the BEAR side + live web only — never the bull case.
    Runs on Fable (9b: adversarial kill-quality is what the capability premium buys).
    Pipeline order: Director -> value-skeptic (Workflow) -> value-post -> csv -> publish."""
    apx = json.load(open(ROOT / "apex_basket_value.json", encoding="utf-8"))
    finalists = [p["symbol"] for p in apx.get("apex_basket", []) if isinstance(p, dict) and p.get("symbol")]
    for r in apx.get("runner_ups", []):
        s = r.get("symbol") if isinstance(r, dict) else r
        if s and s not in finalists:
            finalists.append(s)
    (ROOT / "_skeptic").mkdir(exist_ok=True)
    js = """export const meta = {
  name: 'value-skeptic',
  description: 'Independent skeptic kill-tier over the value-apex finalists (default REFUTED)',
  phases: [{ title: 'Skeptic', model: 'fable' }],
}
const DIR = 'backend/_opus_debate'
const SYMS = __FINALISTS__
phase('Skeptic')
const BATCH = 8
for (let b = 0; b < SYMS.length; b += BATCH) {
  await parallel(SYMS.slice(b, b + BATCH).map(sym => () => agent(
    'SKEPTIC tier for ' + sym + ' (value-apex finalist). Your job is to KILL this value thesis; default verdict REFUTED unless you can independently confirm the load-bearing facts against a PRIMARY source (filings, the company IR site, regulator pages). You see ONLY the bear side — do NOT read or reconstruct the bull case.\\n' +
    '1. Read ' + DIR + '/results_regime/' + sym + '.json but USE ONLY: bear_thesis, sop_bear, risk_reward, catalyst_status. Read the forensic dossier ' + DIR + '/dossiers/' + sym + '.md.\\n' +
    '2. WebSearch the CURRENT facts. Attack: (a) STALE-ANCHOR — is the fair value built on pre-event financials (spin/divestiture/peak quarter)? (b) NUMBER TRUTH — do the load-bearing figures (segment EBITDA, net debt, share count, preferred stack) verify against the latest primary filing? (c) THESIS WEAKNESS — is the claimed cheapness real edge, or priced/structural (melting business, governance brake, terminal multiple)? (d) HIDDEN DISQUALIFIER — litigation, covenant, dilution, regulatory action the debate missed.\\n' +
    '3. Verdict: CONFIRMED (bear attacked, thesis survives) | CONFIRMED_WITH_CORRECTIONS (survives but a load-bearing number/claim needed fixing — state it) | REFUTED (a kill_fact breaks the value case). Also value_conviction_cap (int 1-5): the MAX value conviction this name deserves given what you verified.\\n' +
    '4. Write (Write tool) VALID JSON to ' + DIR + '/_skeptic/' + sym + '.json = {symbol:"' + sym + '", verdict, kill_fact, corrections, value_conviction_cap, evidence:[2-4 dated primary-source cites]}. Never fabricate. Reply exactly: DONE',
    { label: 'skeptic:' + sym, phase: 'Skeptic', agentType: 'general-purpose', model: 'fable' })))
}
return 'DONE'
"""
    js = js.replace("__FINALISTS__", json.dumps(finalists))
    out = ROOT / "_skeptic_workflow.js"
    out.write_text(js, encoding="utf-8")
    print(f"value_skeptic: {len(finalists)} finalists (apex + runners) -> independent Fable kill-tier")
    print(f"SKEPTIC_WORKFLOW={out.resolve()}")
    return len(finalists)


def shadow_debate():
    """9c — SHADOW A/B: emit _shadow_debate.js — identical debate prompts on model 'fable' over a
    stratified 40-name subsample (sector x verdict), results to results_shadow/ (results_regime
    untouched, Director phase stripped so nothing can overwrite the live apex). Migration trigger is
    PRE-COMMITTED in shadow_diff — never decided after seeing results."""
    import re
    import random
    import glob as _g
    rows = []
    for f in _g.glob(str(ROOT / "results_regime" / "*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
            if r.get("source") != "ledger_recheck":
                rows.append((r.get("symbol") or os.path.basename(f)[:-5], r.get("sector", "?"), r.get("verdict", "?")))
        except Exception:
            continue
    strata = {}
    for sym, sec, ver in rows:
        strata.setdefault((sec, ver), []).append(sym)
    rng = random.Random(20260610)                      # deterministic sample
    target, sample = 40, []
    keys = sorted(strata)
    while len(sample) < target and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(sample) < target:
                sample.append(strata[k].pop(rng.randrange(len(strata[k]))))
    has_tx = [s for s in sample if (ROOT / "transcripts" / f"{s}.txt").exists()]
    online = [s for s in sample if s not in has_tx]
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    js = re.sub(r"const RES = DIR \+ '/results_regime'", "const RES = DIR + '/results_shadow'", js)
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = " + json.dumps(has_tx), js)
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(online), js)
    js = re.sub(r"const RECHECK_SYMS = \[[^\]]*\]", "const RECHECK_SYMS = []", js)
    js = js.replace("model: 'opus' }", "model: 'fable' }")          # debate agents -> fable
    js = js.split("phase('Director')")[0] + "log('Shadow debate complete (no Director).')\nreturn 'DONE'\n"
    js = js.replace("name: 'speculair-opus-weekly'", "name: 'speculair-shadow-fable'")
    (ROOT / "results_shadow").mkdir(exist_ok=True)
    out = ROOT / "_shadow_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"shadow_debate: {len(sample)} stratified names ({len(has_tx)} FMP + {len(online)} online) on fable -> results_shadow/")
    print(f"SHADOW_WORKFLOW={out.resolve()}")
    return len(sample)


def shadow_diff():
    """9c — compare results_shadow/ (fable) vs results_regime/ (opus) on the common symbols and
    write _shadow_report.md with the PRE-COMMITTED migration trigger in the header."""
    import glob as _g
    import statistics as _st
    sh = {}
    for f in _g.glob(str(ROOT / "results_shadow" / "*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
            sh[r.get("symbol") or os.path.basename(f)[:-5]] = r
        except Exception:
            continue
    if not sh:
        print("shadow_diff: no results_shadow/ — run shadow-debate first. STOP")
        raise SystemExit(1)
    base = {}
    for s in sh:
        f = ROOT / "results_regime" / f"{s}.json"
        if f.exists():
            try:
                base[s] = json.load(open(f, encoding="utf-8"))
            except Exception:
                pass
    common = sorted(set(sh) & set(base))
    uni = {x["symbol"]: x for x in json.load(open(ROOT / "_radar_universe.json", encoding="utf-8"))}

    def _mos(r, s):
        fv = _val_money(r.get("sop_fair_value"))
        px = (uni.get(s) or {}).get("price")
        return (fv - px) / px * 100 if (fv and isinstance(px, (int, float)) and px > 0) else None

    def _hist(vals):
        from collections import Counter as _C2
        return dict(sorted(_C2(v for v in vals if v is not None).items()))

    iv_b = [base[s].get("interrogator_score") for s in common]
    iv_s = [sh[s].get("interrogator_score") for s in common]
    med_shift = abs(_st.median([v for v in iv_s if isinstance(v, (int, float))]) -
                    _st.median([v for v in iv_b if isinstance(v, (int, float))]))
    exc_b = sum(1 for v in iv_b if isinstance(v, (int, float)) and v <= 2) / len(common) * 100
    exc_s = sum(1 for v in iv_s if isinstance(v, (int, float)) and v <= 2) / len(common) * 100
    dmos = [abs(a - b) for s in common
            for a, b in [(_mos(sh[s], s), _mos(base[s], s))] if a is not None and b is not None]
    mean_dmos = round(sum(dmos) / len(dmos), 1) if dmos else None
    ok = (med_shift < 1) and (abs(exc_s - exc_b) < 5) and (mean_dmos is not None and mean_dmos < 15)
    rep = [
        "# Shadow A/B — Opus 4.8 (results_regime) vs Fable 5 (results_shadow)",
        "",
        "## PRE-COMMITTED MIGRATION TRIGGER (decided before results were seen)",
        "Migrate the per-name debate to Fable ONLY IF: interrogator median shift < 1 point AND",
        "EXCLUDE-rate delta < 5pp AND mean |dMoS| < 15pts. Otherwise re-tune gate thresholds first.",
        "",
        f"## VERDICT: {'MIGRATE — trigger CLEARED' if ok else 'DO NOT MIGRATE — trigger FAILED (re-tune gates first)'}",
        "",
        f"- common symbols compared: {len(common)}",
        f"- interrogator median shift: {med_shift} (need < 1)",
        f"- EXCLUDE rate: opus {exc_b:.1f}% -> fable {exc_s:.1f}% (delta {abs(exc_s - exc_b):.1f}pp, need < 5)",
        f"- mean |d sop_mos_pct|: {mean_dmos} (need < 15)",
        f"- verdict counts opus: {_hist([base[s].get('verdict') for s in common])}",
        f"- verdict counts fable: {_hist([sh[s].get('verdict') for s in common])}",
        f"- conviction hist opus: {_hist([base[s].get('conviction') for s in common])} | fable: {_hist([sh[s].get('conviction') for s in common])}",
        f"- value_conviction hist opus: {_hist([base[s].get('value_conviction') for s in common])} | fable: {_hist([sh[s].get('value_conviction') for s in common])}",
        f"- interrogator hist opus: {_hist(iv_b)} | fable: {_hist(iv_s)}",
        "",
        "9d on migration: stamp engine_change events into both tracking histories.",
    ]
    (ROOT / "_shadow_report.md").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep[:14]))
    print(f"shadow_diff -> {ROOT / '_shadow_report.md'}")
    return ok


def control_sample():
    """11b — monthly FALSE-NEGATIVE estimate: debate N=8 random names from the scan that sit in NO
    methodology basket; report how many clear the forensic gate with CRO MoS >= 30% — the funnel's
    miss-rate on its own success metric. Tagged control=true; results land in results_control/ and
    NEVER feed baskets."""
    import random
    from datetime import datetime as _dtt
    scan = gcs_io.gcs_read_json("scans/latest_global.json") or json.load(
        open("../frontend/public/latest_global.json", encoding="utf-8"))
    mp = gcs_io.gcs_read_json("scans/methodology_picks.json") or {}
    in_basket = set()
    for meth in (mp.get("methodologies") or {}).values():
        picks_l = meth.get("picks") if isinstance(meth, dict) else meth     # dict-with-picks or bare list
        for p in (picks_l or []):
            s = p.get("symbol") if isinstance(p, dict) else p
            if s:
                in_basket.add(s)
    pool = [s for s in scan.get("stocks", [])
            if s.get("symbol") and s["symbol"] not in in_basket
            and isinstance(s.get("market_cap"), (int, float)) and s["market_cap"] >= 2e9]
    rng = random.Random(int(_dtt.now().strftime("%Y%m")))          # deterministic within the month
    picks = rng.sample(pool, min(8, len(pool)))
    (ROOT / "results_control").mkdir(exist_ok=True)
    syms = []
    for s in picks:
        sym = s["symbol"]
        syms.append(sym)
        ms = "\n".join(f"{k}: {s.get(k)}" for k in
                       ("price", "market_cap", "sector", "company_name", "revenue_yoy", "revenue_cagr_3y",
                        "eps_yoy", "gross_margin", "net_margin", "roic_avg", "altman_z", "p_fcf",
                        "dcf_fcff_mos", "epv_mos", "graham_revised_mos", "owner_earnings_mos",
                        "iv15_deep_value_mos", "net_debt", "days_to_earnings") if s.get(k) is not None)
        (ROOT / "inputs" / f"{sym}.json").write_text(json.dumps(
            {"symbol": sym, "company": s.get("company_name", ""), "sector": s.get("sector", ""),
             "signal_type": "control", "control": True,
             "metrics_str": "=== CONTROL SAMPLE (random non-basket name; scan fields) ===\n" + ms},
            ensure_ascii=False, indent=1), encoding="utf-8")
    js = (ROOT / "_weekly_debate.js").read_text(encoding="utf-8")
    import re
    js = re.sub(r"const RES = DIR \+ '/results_regime'", "const RES = DIR + '/results_control'", js)
    js = re.sub(r"const SYMS = \[[^\]]*\]", "const SYMS = []", js)
    js = re.sub(r"const ONLINE_SYMS = \[[^\]]*\]", "const ONLINE_SYMS = " + json.dumps(syms), js)
    js = re.sub(r"const RECHECK_SYMS = \[[^\]]*\]", "const RECHECK_SYMS = []", js)
    js = js.split("phase('Director')")[0] + "log('Control sample complete (no Director).')\nreturn 'DONE'\n"
    js = js.replace("name: 'speculair-opus-weekly'", "name: 'speculair-control-sample'")
    out = ROOT / "_control_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"control_sample: {len(syms)} random non-basket names {syms} -> results_control/")
    print(f"CONTROL_WORKFLOW={out.resolve()}")
    print("After the workflow: count results_control names with interrogator_score>=3 AND CRO MoS>=30% "
          "= the funnel's false-negative (miss) rate this month.")
    return len(syms)


DISRUPTOR_DIR = ROOT / "disruptor"


def disruptor_universe():
    """DISRUPTOR LENS Stage A+B (spec §1.2-1.3, monthly): deterministic FMP screen per theme ->
    liquidity gate -> financial gates (TTM-FCF-positive-or-inflecting, revenue CAGR>=15%-or-
    accelerating, funded-leverage solvency != weak) -> writes gated candidates + chunked Sonnet
    theme-map workflow (_dt_map.js, spec §1.4). The merge + Stage-D cut runs as disruptor-map-merge
    AFTER the workflow. Anti-shrink: re-screens FMP from scratch every run; never reads a prior
    universe.json. Gates cached by symbol+month (re-runs inside a month are free)."""
    import concurrent.futures
    from datetime import datetime as _dt
    tax = json.load(open(ROOT / "disruptor_themes.json", encoding="utf-8"))
    key = E.get_key("FMP_API_KEY")
    if not key:
        print("GUARD: no FMP_API_KEY — STOP")
        raise SystemExit(1)
    DISRUPTOR_DIR.mkdir(exist_ok=True)
    (DISRUPTOR_DIR / "theme_map").mkdir(exist_ok=True)
    base = "https://financialmodelingprep.com/stable"
    floors = tax.get("floors") or {}
    mcap_floor = floors.get("market_cap_usd", 2_000_000_000)
    adv_floor = floors.get("adv_usd", 10_000_000)

    # ── Stage A — FMP company-screener per theme x industry x exchange (no LLM) ──
    seen = {}                                   # sym -> candidate row
    hints = {}                                  # sym -> [theme ids whose screen caught it]
    raw_total = 0
    for th in tax["themes"]:
        th_syms = set()
        for ind in th.get("fmp_industries") or []:
            for exch in tax.get("exchanges") or ["NYSE", "NASDAQ"]:
                try:
                    rows = requests.get(base + "/company-screener", params={
                        "industry": ind, "exchange": exch,
                        "marketCapMoreThan": mcap_floor,
                        "volumeMoreThan": 200_000, "priceMoreThan": floors.get("price_min", 5),
                        "isActivelyTrading": "true", "isEtf": "false", "isFund": "false",
                        "limit": 1000, "apikey": key}, timeout=25).json()
                except Exception:
                    rows = []
                if not isinstance(rows, list):
                    rows = []
                raw_total += len(rows)
                for r in rows:
                    sym = r.get("symbol")
                    if not sym or "." in sym and not sym.replace(".", "").isalnum():
                        continue
                    seen.setdefault(sym, {"symbol": sym, "name": r.get("companyName", ""),
                                          "sector": r.get("sector", ""), "industry": r.get("industry", ""),
                                          "mcap": r.get("marketCap"), "price": r.get("price"),
                                          "volume": r.get("volume")})
                    th_syms.add(sym)
                    hints.setdefault(sym, [])
                    if th["id"] not in hints[sym]:
                        hints[sym].append(th["id"])
        print(f"  Stage A [{th['id']}]: {len(th_syms)} unique candidates")
    print(f"Stage A: {len(seen)} unique candidates from {raw_total} raw rows")
    if raw_total < 100:
        print("GUARD: FMP screen returned <100 raw rows (key/quota failure?) — STOP, not a silent small universe")
        raise SystemExit(1)

    # ── liquidity gate (free — from the screener rows) ──
    liquid = {s: c for s, c in seen.items()
              if isinstance(c.get("price"), (int, float)) and isinstance(c.get("volume"), (int, float))
              and c["price"] * c["volume"] >= adv_floor}
    print(f"liquidity gate (ADV >= ${adv_floor/1e6:.0f}M): {len(liquid)} pass")

    # ── Stage B — financial gates, cached by symbol+month ──
    cache_p = DISRUPTOR_DIR / "_gates_cache.json"
    cache = {}
    if cache_p.exists():
        try:
            cache = json.load(open(cache_p, encoding="utf-8"))
        except Exception:
            cache = {}
    month = _dt.now().strftime("%Y-%m")

    def gates_for(sym):
        ck = f"{sym}|{month}"
        if ck in cache:
            return sym, cache[ck]
        g = {"ttm_fcf": None, "fcf_inflecting": False, "rev_cagr_3y": None, "rev_yoy": None,
             "ttm_revenue": None, "fcf_margin": None, "pass_fcf": False, "pass_growth": False}
        try:
            cf = requests.get(base + "/cash-flow-statement",
                              params={"symbol": sym, "period": "quarter", "limit": 5, "apikey": key}, timeout=20).json()
            if isinstance(cf, list) and len(cf) >= 4:
                fcfs = []
                for q in cf[:4]:
                    v = q.get("freeCashFlow")
                    if not isinstance(v, (int, float)):
                        v = (q.get("operatingCashFlow") or 0) + (q.get("capitalExpenditure") or 0)
                    fcfs.append(v if isinstance(v, (int, float)) else 0)
                g["ttm_fcf"] = sum(fcfs)
                g["fcf_inflecting"] = bool(g["ttm_fcf"] <= 0 and len(fcfs) >= 2 and fcfs[0] > 0 and fcfs[1] > 0)
        except Exception:
            pass
        try:
            ann = requests.get(base + "/income-statement",
                               params={"symbol": sym, "period": "annual", "limit": 4, "apikey": key}, timeout=20).json()
            if isinstance(ann, list) and len(ann) >= 4:
                r0, r3 = ann[0].get("revenue"), ann[3].get("revenue")
                if isinstance(r0, (int, float)) and isinstance(r3, (int, float)) and r3 > 0 and r0 > 0:
                    g["rev_cagr_3y"] = round((r0 / r3) ** (1 / 3) - 1, 4)
        except Exception:
            pass
        try:
            qs = requests.get(base + "/income-statement",
                              params={"symbol": sym, "period": "quarter", "limit": 8, "apikey": key}, timeout=20).json()
            if isinstance(qs, list) and len(qs) >= 8:
                now4 = sum(q.get("revenue") or 0 for q in qs[:4])
                pri4 = sum(q.get("revenue") or 0 for q in qs[4:8])
                g["ttm_revenue"] = now4
                if pri4 > 0:
                    g["rev_yoy"] = round(now4 / pri4 - 1, 4)
        except Exception:
            pass
        if isinstance(g["ttm_fcf"], (int, float)) and isinstance(g["ttm_revenue"], (int, float)) and g["ttm_revenue"] > 0:
            g["fcf_margin"] = round(g["ttm_fcf"] / g["ttm_revenue"], 4)
        g["pass_fcf"] = bool((isinstance(g["ttm_fcf"], (int, float)) and g["ttm_fcf"] > 0) or g["fcf_inflecting"])
        c3, yy = g["rev_cagr_3y"], g["rev_yoy"]
        g["pass_growth"] = bool(
            (isinstance(c3, (int, float)) and c3 >= 0.15)
            or (isinstance(yy, (int, float)) and isinstance(c3, (int, float)) and yy > c3 and yy >= 0.10)
            or (c3 is None and isinstance(yy, (int, float)) and yy >= 0.15))
        cache[ck] = g
        return sym, g

    syms = sorted(liquid)
    print(f"Stage B: financial gates over {len(syms)} names (cached: {sum(1 for s in syms if f'{s}|{month}' in cache)})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        done = 0
        for sym, g in ex.map(gates_for, syms):
            liquid[sym]["gates"] = g
            done += 1
            if done % 50 == 0:
                print(f"  ...{done}/{len(syms)}")
    cache_p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    fg = [s for s, c in liquid.items() if c["gates"]["pass_fcf"] and c["gates"]["pass_growth"]]
    print(f"FCF+growth gates: {len(fg)} pass")

    fl = _funded_leverage(fg)                                   # batch, shared cache
    gated = []
    for s in fg:
        c = liquid[s]
        flv = fl.get(s, {})
        solv = _funded_solvency(c.get("sector", ""), flv.get("net_funded_debt_ebitda"), flv.get("interest_coverage"))
        c["gates"]["funded_solvency"] = solv
        c["gates"]["net_funded_debt_ebitda"] = flv.get("net_funded_debt_ebitda")
        c["gates"]["adv_usd"] = round(c["price"] * c["volume"], 0)
        c["themes_hint"] = hints.get(s, [])
        if solv != "weak":
            gated.append(c)
    print(f"funded-solvency gate (!= weak): {len(gated)} pass")

    funnel = {"screened": len(seen), "liquid": len(liquid), "gated": len(gated)}
    (DISRUPTOR_DIR / "_candidates.json").write_text(
        json.dumps({"built_at": _dt.now().isoformat(), "taxonomy_version": tax.get("version"),
                    "funnel_partial": funnel, "candidates": gated}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # ── emit the chunked Sonnet theme-map workflow (spec §1.4) ──
    CH = 20
    chunks = [gated[i:i + CH] for i in range(0, len(gated), CH)]
    for i, ch in enumerate(chunks):
        (DISRUPTOR_DIR / f"_map_chunk_{i}.json").write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(chunks)
    js = """export const meta = {
  name: 'disruptor-theme-map',
  description: 'Sonnet theme-mapping over the gated disruptor candidates (Radar-style, chunked)',
  phases: [{ title: 'ThemeMap', model: 'sonnet' }],
}
const N = __N__
phase('ThemeMap')
await parallel(Array.from({ length: N }, (_, i) => () => agent(
  'You are the DISRUPTOR THEME RADAR (theme-mapping + true-competitor pass). Read backend/_opus_debate/disruptor_themes.json (the versioned theme taxonomy: ids, theses, value-chain layers, notes) and backend/_opus_debate/disruptor/_map_chunk_' + i + '.json (your candidate chunk: symbol/name/sector/industry/mcap + gates incl. revenue growth and FCF). For EACH symbol decide, skeptically:\\n' +
  '- themes: array of taxonomy ids this company GENUINELY rides (max 2; [] if none — an industry filter catches many non-disruptors).\\n' +
  '- value_chain_position: one line — which layer it occupies and what it sells.\\n' +
  '- load_bearing_score: int 1-5 — how hard is this company to route around in the theme value chain (5 = chokepoint/toll-taker, 1 = commodity participant).\\n' +
  '- s_curve_stage: early_adoption | steep_ramp | broadening | maturing.\\n' +
  '- true_competitors: 4-8 REAL competitor tickers (business-model comparables, in-universe or NOT — e.g. include private-adjacent public proxies, foreign listings).\\n' +
  '- relative_comps: 2-4 sentences on relative position vs those competitors (growth, margin, multiple posture).\\n' +
  '- theme_fit_confidence: high | medium | low (low = the FMP industry filter caught a name that is NOT really a disruption toll-taker — e.g. a legacy prime, a balance-sheet lender, a therapy biotech).\\n' +
  'Write (Write tool) VALID JSON to backend/_opus_debate/disruptor/_dt_' + i + '.json as {"<SYM>": {themes, value_chain_position, load_bearing_score, s_curve_stage, true_competitors, relative_comps, theme_fit_confidence}, ...} covering EVERY symbol in your chunk. Reply exactly: DONE',
  { label: 'dtmap:' + i, phase: 'ThemeMap', model: 'sonnet' })))
return 'DONE'
"""
    js = js.replace("__N__", str(n))
    (DISRUPTOR_DIR / "_dt_map.js").write_text(js, encoding="utf-8")
    print(f"UNIVERSE STAGE A+B OK: screened={len(seen)} liquid={len(liquid)} gated={len(gated)} -> {n} Sonnet map chunks")
    print(f"MAP_WORKFLOW={DISRUPTOR_DIR.resolve() / '_dt_map.js'}")
    print("Next: run the Workflow, then: python backend/weekly_opus_refresh.py disruptor-map-merge")
    return len(gated)


def disruptor_map_merge():
    """DISRUPTOR LENS Stage C-merge + Stage D (spec §1.4-1.6): merge the Sonnet shards, DROP
    theme_fit_confidence=low (printed, never silent), explode per-symbol theme_map/<SYM>.json,
    pre-rank cut to <=8/theme & <=40 global (the pre-rank only decides who gets DEBATED, never
    who gets PICKED), union in current disruptor apex holders, enforce the anti-shrink guards,
    and write disruptor/universe.json with the full funnel."""
    import glob as _g
    from datetime import datetime as _dt
    tax = json.load(open(ROOT / "disruptor_themes.json", encoding="utf-8"))
    cand_f = DISRUPTOR_DIR / "_candidates.json"
    if not cand_f.exists():
        print("GUARD: no _candidates.json — run disruptor-universe first. STOP")
        raise SystemExit(1)
    cd = json.load(open(cand_f, encoding="utf-8"))
    cands = {c["symbol"]: c for c in cd.get("candidates", [])}
    shards = sorted(_g.glob(str(DISRUPTOR_DIR / "_dt_*.json")))
    mapped = {}
    for f in shards:
        try:
            mapped.update(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print(f"WARN: shard {os.path.basename(f)} unreadable ({e})")
    if not mapped:
        print("GUARD: no theme-map shards — run the _dt_map.js workflow first. STOP")
        raise SystemExit(1)
    low = [s for s, m in mapped.items() if (m.get("theme_fit_confidence") or "").lower() == "low"
           or not (m.get("themes") or [])]
    keep = {s: m for s, m in mapped.items() if s not in set(low) and s in cands}
    print(f"map-merge: {len(mapped)} mapped from {len(shards)} shards | DROPPED low-confidence/themeless ({len(low)}): {sorted(low)}")
    for s, m in keep.items():
        (DISRUPTOR_DIR / "theme_map" / f"{s}.json").write_text(
            json.dumps({"symbol": s, **m}, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── Stage D — transparent pre-rank cut: <=8/theme, <=40 global ──
    def prerank(s):
        m, g = keep[s], cands[s].get("gates", {})
        return (-(m.get("load_bearing_score") or 0), -(g.get("rev_cagr_3y") or 0), -(g.get("fcf_margin") or 0))

    by_theme = {}
    for s, m in keep.items():
        for t in m.get("themes") or []:
            by_theme.setdefault(t, []).append(s)
    selected = set()
    for t, ss in by_theme.items():
        for s in sorted(ss, key=prerank)[:8]:
            selected.add(s)
    if len(selected) > 40:
        selected = set(sorted(selected, key=prerank)[:40])
    # union current disruptor apex holders — a held name is never dropped by the screen
    held = []
    apx_f = E.FRONTEND_DIR / "public" / "speculair_disruptor_apex.json"
    if apx_f.exists():
        try:
            held = [p.get("symbol") for p in json.load(open(apx_f, encoding="utf-8")).get("apex_basket", []) if p.get("symbol")]
        except Exception:
            held = []
    for s in held:
        if s in keep:
            selected.add(s)
    members = []
    for s in sorted(selected):
        m, c = keep[s], cands[s]
        members.append({"symbol": s, "name": c.get("name", ""), "sector": c.get("sector", ""),
                        "industry": c.get("industry", ""), "mcap": c.get("mcap"),
                        "themes": m.get("themes") or [], "value_chain_position": m.get("value_chain_position", ""),
                        "load_bearing_score": m.get("load_bearing_score"), "s_curve_stage": m.get("s_curve_stage", ""),
                        "held": s in held, "gates": c.get("gates", {})})
    theme_counts = {}
    for mm in members:
        for t in mm["themes"]:
            theme_counts[t] = theme_counts.get(t, 0) + 1
    for th in tax["themes"]:
        theme_counts.setdefault(th["id"], 0)
    funnel = {**(cd.get("funnel_partial") or {}), "mapped_high_med": len(keep), "debated": len(members)}
    print(f"FUNNEL: screened={funnel.get('screened')} liquid={funnel.get('liquid')} gated={funnel.get('gated')} "
          f"mapped_high_med={len(keep)} debated={len(members)}")
    print(f"by_theme: {theme_counts}")
    if len(members) < 25:
        print("GUARD: debated < 25 — DEGRADED universe, STOP (universe.json NOT written; "
              "do not proceed, do not reuse a prior month)")
        raise SystemExit(1)
    uni = {"built_at": _dt.now().isoformat(), "taxonomy_version": tax.get("version"),
           "funnel": funnel, "by_theme": theme_counts, "members": members}
    (DISRUPTOR_DIR / "universe.json").write_text(json.dumps(uni, ensure_ascii=False, indent=1), encoding="utf-8")
    zero = [t for t, n in theme_counts.items() if n == 0]
    if zero:
        print(f"NOTE: zero-member themes {zero} — acceptable if honestly empty (e.g. space pre-FCF), "
              f"but STOP if a historically >=3-member theme zeroed out.")
    print(f"UNIVERSE OK: {len(members)} names -> {DISRUPTOR_DIR / 'universe.json'}")
    return len(members)


def export_debate_csv():
    """Write a CSV of every debated name in results_regime/ with the FULL output of every agent in the
    chain — Radar (peer_groups), Interrogator (dossier+score+trajectory), Architect (bull/bear+SoP),
    Catalyst verification (catalyst_status), CRO/Moderator (verdict/conviction/SoP reconcile/etc.), and
    the Director's per-name assessment — plus a companion director_memo .txt. UTF-8 BOM for Excel."""
    import csv
    res_dir, doss_dir, pg_dir = ROOT / "results_regime", ROOT / "dossiers", ROOT / "peer_groups"
    apex = {}
    apx = ROOT / "apex_basket_opus_regime.json"
    if apx.exists():
        try:
            apex = json.load(open(apx, encoding="utf-8"))
        except Exception:
            apex = {}
    director = {}
    for p in apex.get("apex_basket", []):
        if isinstance(p, dict) and p.get("symbol"):
            director[p["symbol"]] = {**p, "_role": "APEX"}
    for p in apex.get("runner_ups", []):
        if isinstance(p, dict) and p.get("symbol"):
            director[p["symbol"]] = {**p, "_role": "RUNNER_UP"}
        elif isinstance(p, str):
            director[p] = {"_role": "RUNNER_UP"}
    cols = ["symbol", "sector", "signal_type", "source", "transcript_source",
            "verdict", "conviction", "catalyst_status", "sop_fair_value", "risk_reward",
            "trajectory", "interrogator_score",
            "director_role", "director_conviction", "director_thesis", "director_lane",
            "director_regime_fit", "director_exposure_axes",
            "radar_verdict", "radar_peers", "radar_relative_comps", "radar_rationale",
            "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "sop_breakdown",
            "consensus_delta", "valley_of_death", "positioning_washout", "forcing_function",
            "moderator_conclusion", "peer_comps_note", "interrogator_dossier"]
    rows = []
    for f in sorted(res_dir.glob("*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        sym = r.get("symbol") or f.stem
        doss = ""
        if (doss_dir / f"{sym}.md").exists():
            doss = (doss_dir / f"{sym}.md").read_text(encoding="utf-8")
        pg = {}
        if (pg_dir / f"{sym}.json").exists():
            try:
                pg = json.load(open(pg_dir / f"{sym}.json", encoding="utf-8"))
            except Exception:
                pg = {}
        dd = director.get(sym, {})
        rows.append({
            "symbol": sym, "sector": r.get("sector", ""), "signal_type": r.get("signal_type", ""),
            "source": r.get("source", ""), "transcript_source": r.get("transcript_source", ""),
            "verdict": r.get("verdict", ""), "conviction": r.get("conviction", ""),
            "catalyst_status": r.get("catalyst_status", ""), "sop_fair_value": r.get("sop_fair_value", ""),
            "risk_reward": r.get("risk_reward", ""), "trajectory": r.get("trajectory", ""),
            "interrogator_score": r.get("interrogator_score", ""),
            "director_role": dd.get("_role", ""), "director_conviction": dd.get("director_conviction", ""),
            "director_thesis": dd.get("thesis", ""), "director_lane": dd.get("lane", ""),
            "director_regime_fit": dd.get("regime_fit", ""),
            "director_exposure_axes": json.dumps(dd.get("exposure_axes", ""), ensure_ascii=False) if isinstance(dd.get("exposure_axes"), (list, dict)) else dd.get("exposure_axes", ""),
            "radar_verdict": pg.get("verdict", ""),
            "radar_peers": ", ".join(pg.get("peers", [])) if isinstance(pg.get("peers"), list) else "",
            "radar_relative_comps": pg.get("relative_comps", ""), "radar_rationale": pg.get("rationale", ""),
            "bull_thesis": r.get("bull_thesis", ""), "bear_thesis": r.get("bear_thesis", ""),
            "sop_bull": r.get("sop_bull", ""), "sop_bear": r.get("sop_bear", ""),
            "sop_breakdown": r.get("sop_breakdown", ""), "consensus_delta": r.get("consensus_delta", ""),
            "valley_of_death": r.get("valley_of_death", ""), "positioning_washout": r.get("positioning_washout", ""),
            "forcing_function": r.get("forcing_function", ""), "moderator_conclusion": r.get("moderator_conclusion", ""),
            "peer_comps_note": r.get("peer_comps_note", ""), "interrogator_dossier": doss,
        })
    out = ROOT / "speculair_debate_66.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    (ROOT / "speculair_debate_66_director_memo.txt").write_text(apex.get("director_memo", ""), encoding="utf-8")
    print(f"wrote {len(rows)} rows x {len(cols)} cols -> {out}")
    print(f"director_memo -> {ROOT / 'speculair_debate_66_director_memo.txt'}")
    return len(rows)


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

    syms, no_tx, radar_universe = [], [], []
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
        metrics = (metrics or "") + _fmp_segments(sym)   # segment revenue for a true SoP (best-effort)
        meths = sym_meths[sym]
        # Structured row for the Radar peer-clustering phase (relative-value lever, see _WORKFLOW_TEMPLATE).
        radar_universe.append({"symbol": sym, "sector": sc.get("sector", ""),
                               "industry": sc.get("industry", ""), "sector_class": sc.get("sector_class", ""),
                               "methodologies": meths,
                               **{k: sc.get(k) for k in _RADAR_FIELDS if sc.get(k) is not None}})
        signal = "deep_value" if all(m in VALUE_SIGNAL_METHS for m in meths if m != "apex") and any(m in VALUE_SIGNAL_METHS for m in meths) else "catalyst"
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
            # Cap to the last 5 quarters: 8 × 18k chars ~= 36k tokens, over the 25k Read cap an agent
            # hits when it reads transcripts/<sym>.txt. 5 × 18k ~= 22k tokens stays under it.
            (TXT / f"{sym}.txt").write_text(
                "\n\n".join("=== " + t["date"] + " ===\n" + E._slice_transcript(t["content"]) for t in real[-5:]),
                encoding="utf-8")
            syms.append(sym)
        else:
            no_tx.append(sym)

    (ROOT / "_radar_universe.json").write_text(
        json.dumps(radar_universe, ensure_ascii=False, indent=2), encoding="utf-8")
    # Radar runs CHUNKED (one Sonnet agent per <=20-name sector chunk) — a single agent over the full
    # universe truncates its peer_groups output (observed at 161 names). Group by sector, split >20,
    # write _radar_groups.json (each chunk = [label, [syms]]); the workflow spawns one agent per index
    # and a deterministic merge (weekly_opus_refresh.py merge). Clear stale shards first.
    import glob as _glob
    for _f in _glob.glob(str(ROOT / "_pg_*.json")):
        try:
            os.remove(_f)
        except OSError:
            pass
    _by_sec = {}
    for _r in radar_universe:
        _by_sec.setdefault(_r.get("sector") or "Other", []).append(_r["symbol"])
    radar_groups = []
    for _sec in sorted(_by_sec, key=lambda s: -len(_by_sec[s])):
        _ss = sorted(_by_sec[_sec])
        for _i in range(0, len(_ss), 20):
            _lab = _sec if len(_ss) <= 20 else f"{_sec} ({_i // 20 + 1})"
            radar_groups.append([_lab, _ss[_i:_i + 20]])
    (ROOT / "_radar_groups.json").write_text(json.dumps(radar_groups, ensure_ascii=False), encoding="utf-8")
    (ROOT / "interrogator_system.txt").write_text(E.INTERROGATOR_SYSTEM_PROMPT, encoding="utf-8")
    (ROOT / "architect_system.txt").write_text(E.ARCHITECT_SYSTEM_PROMPT, encoding="utf-8")
    (ROOT / "moderator_system.txt").write_text(E.MODERATOR_SYSTEM_PROMPT, encoding="utf-8")

    # no_tx names have NO FMP transcript — instead of skipping (the user's explicit ask: "send agents
    # to fetch transcripts online so we don't skip any pick"), pass them as ONLINE_SYMS so the debate
    # agent WebSearch/WebFetches the latest transcript/results. Their input bundles (with metrics +
    # company name) were already written above, so they debate with full fundamentals grounding.
    # 11c — FORENSIC LEDGER: unexpired EXCLUDE names get a SHORT re-check, not a full
    # I->A->CRO debate (the weekly self-clean wipes all memory, so known frauds/red-flags were
    # burning a full debate every week to rediscover known facts). Entries expire after 8 weeks
    # or on an earnings rollover (days_to_earnings jumped up vs when the entry was written).
    recheck, recheck_info = [], {}
    led_p = ROOT / "forensic_ledger.json"
    if led_p.exists():
        try:
            from datetime import datetime as _dtt
            led = json.load(open(led_p, encoding="utf-8"))
            today_s = _dtt.now().strftime("%Y-%m-%d")
            uni_syms = set(syms) | set(no_tx)
            for s, ent in led.items():
                if ent.get("gate") != "EXCLUDE" or s not in uni_syms:
                    continue
                if (ent.get("expires") or "") < today_s:
                    continue                                   # TTL expired -> full debate again
                dte_now = next((x.get("days_to_earnings") for x in radar_universe if x.get("symbol") == s), None)
                dte_then = ent.get("days_to_earnings")
                if isinstance(dte_now, (int, float)) and isinstance(dte_then, (int, float)) and dte_now > dte_then + 14:
                    continue                                   # earnings happened since -> full debate again
                recheck.append(s)
                recheck_info[s] = {"date": ent.get("date", ""), "reason": ent.get("reason", "")}
        except Exception as _e:
            print(f"WARN: forensic ledger unreadable ({_e}) — all names get full debates")
    syms = [s for s in syms if s not in recheck]
    no_tx = [s for s in no_tx if s not in recheck]

    js = (_WORKFLOW_TEMPLATE
          .replace("__SYMS__", json.dumps(syms))
          .replace("__ONLINE_SYMS__", json.dumps(no_tx))
          .replace("__RECHECK_SYMS__", json.dumps(recheck))
          .replace("__RECHECK_INFO__", json.dumps(recheck_info))
          .replace("__N_RADAR__", str(len(radar_groups))))
    out = ROOT / "_weekly_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"PREP OK: {len(syms)} with FMP transcripts + {len(no_tx)} via online fetch "
          f"+ {len(recheck)} ledger re-checks = {len(syms) + len(no_tx) + len(recheck)} total candidates "
          f"(online: {no_tx}{'; recheck: ' + str(recheck) if recheck else ''})")
    print(f"WORKFLOW_SCRIPT={out.resolve()}")


_WORKFLOW_TEMPLATE = r"""export const meta = {
  name: 'speculair-opus-weekly',
  description: 'Weekly all-Opus regime debate (Radar peer-comps + Sum-of-Parts) over the per-methodology universe, then Director picks the apex basket',
  phases: [{ title: 'Radar', model: 'sonnet' }, { title: 'Debate', model: 'opus' }, { title: 'Director', model: 'fable' }],
}
const DIR = 'backend/_opus_debate'
const RES = DIR + '/results_regime'
const SYMS = __SYMS__               // have a bundled FMP transcript (read local file)
const ONLINE_SYMS = __ONLINE_SYMS__ // no FMP transcript — agent fetches the latest one online
const BRIEF = "Read CATALYST_WATCH_REGIME.md (repo root) for the current market regime, then APPLY it: reward hard-dated catalysts inside the favorable window; PENALIZE Fed-cut/rate-rescue or past/out-of-window catalysts; favor structural special-sits in fat thin-coverage lanes (distressed/deleveraging > spinoffs > forced-sellers), deprioritize hard-binary/PDUFA; prize resolution-driver independence (wary of theses hinging on one shared macro factor like oil or AI-capex). Let this MOVE the conviction/verdict."

// ── PHASE 0 — RADAR (Sonnet, cheaper), CHUNKED by sector. A single agent over the full universe
// truncates its peer_groups output (observed at 161 names), so N parallel agents each tag <=20 names
// with their TRUE real-world competitors, then a deterministic merge combines the shards.
const N_RADAR = __N_RADAR__
phase('Radar')
await parallel(Array.from({ length: N_RADAR }, (_, i) => () => agent(
  'You are the RADAR (relative-value analyst). Read ' + DIR + '/_radar_groups.json — a JSON array; take element [' + i + '] = [label, [symbols]]. Those symbols are your ASSIGNMENT. Read ' + DIR + '/_radar_universe.json for their Speculair data (filter to your symbols).\n' +
  '1. For EACH assigned symbol, identify its TRUE business competitors / closest comparables — by business model, economics, end-market, value chain and capital intensity — REGARDLESS of whether the competitor is in this candidate universe. Name the ACTUAL competitors even if NOT screened here (e.g. a stainless-steel maker -> Outokumpu / Aperam; a broadcast-tower operator -> Cellnex / INWIT / American Tower). 4-8 real tickers each.\n' +
  '2. For EACH, relative_comps: where it ranks vs that TRUE peer set on VALUATION (p_fcf, the multi-method MoS spread), GROWTH (rev/eps), MARGINS (gross/net, roic) and TREND/MOMENTUM (price vs sma200, 52-wk position, sector_momentum) — cheap / in-line / rich, and whether the gap is JUSTIFIED by quality/growth or is a real mispricing. Use _radar_universe.json data for in-universe peers + your sector knowledge for the rest. 2-4 tight sentences each.\n' +
  '3. Write (Write tool) VALID JSON to ' + DIR + '/_pg_' + i + '.json = a map of SYMBOL to { peers:[...], relative_comps:"...", verdict:"cheap_vs_peers|in_line|rich_vs_peers", rationale:"why these are the real peers" } for ONLY your assigned symbols. Reply exactly: DONE',
  { label: 'radar:' + i, phase: 'Radar', model: 'sonnet' })))
await agent(
  'Run this exact command (it merges the Radar shards into peer_groups.json deterministically): python backend/weekly_opus_refresh.py merge\nConfirm the entry count it prints is > 0. Reply exactly: DONE',
  { label: 'radar-merge', phase: 'Radar', model: 'sonnet' })

// ── PHASE 1 — DEBATE: Interrogator -> Architect (bull/bear + Sum-of-Parts) -> CRO (reconcile). ──
// All names run as general-purpose agents so EVERY name (FMP + online) can web-verify its catalyst.
function debatePrompt(sym, online) {
  const step1 = online
    ? '1. Read ' + DIR + '/inputs/' + sym + ".json (fields metrics_str/sector/signal_type/company; metrics may include a SEGMENT REVENUE block). NO FMP transcript is bundled. Use WebSearch + WebFetch to find " + sym + "'s MOST RECENT earnings-call transcript; if none exists, get the latest quarterly results / earnings release / management commentary / investor presentation (IR site, Tikr, Seeking Alpha, Investing.com, Simply Wall St, MarketScreener, plus the latest regulatory filing). If genuinely nothing is findable, say so and reason from the fundamentals — never fabricate quotes or figures.\n"
    : '1. Read ' + DIR + '/inputs/' + sym + '.json (fields metrics_str/sector/signal_type; metrics may include a SEGMENT REVENUE block) and ' + DIR + '/transcripts/' + sym + '.txt.\n'
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital. Be skeptical and current-facts-driven.\n' +
    step1 +
    '2. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; produce the full forensic dossier (8 sections + final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...>"); Write it to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '3. PEER COMPS: read ' + DIR + '/peer_groups/' + sym + '.json (this name\'s peers + relative_comps + verdict) as an INDEPENDENT relative-value lever for the valuation below (skip if the file is absent).\n' +
    '4. ARCHITECT: read ' + DIR + '/architect_system.txt; produce bull_thesis and bear_thesis, AND a SUM-OF-PARTS valuation — value the business by its PARTS (segment SoP from the SEGMENT REVENUE block x peer multiples where present; else whole-company intrinsic via the methodology metric/peer multiple), then apply special-situation OVERLAYS where relevant (net cash, pending distributions [VERIFY whether already paid], announced asset-sales, tender/deal terms minus liabilities). Output sop_bull (favorable parts) and sop_bear (adverse parts), each a per-share value + the parts breakdown.\n' +
    '5. CATALYST VERIFICATION (web, MANDATORY for every name): identify the load-bearing catalyst(s) and WebSearch their CURRENT status as of today. catalyst_status = FIRED (already happened, re-rate spent) | ARB (deal terms fixed, tight merger-arb capped at the offer) | PENDING_HARD (dated, binding, real asymmetry) | SOFT_EXTENDED (non-binding / serially-extended / third-party / single-binary) | UNVERIFIABLE. Dated evidence; never fabricate.\n' +
    '6. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward (downside-to-break vs upside-to-fair); DOWN-RATE conviction for FIRED/SOFT catalysts and size ARB to the spread; sanity-check the multiple against the peer comps. Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion. THEN, separately, produce value_conviction (int 1-5): rate the VALUE case as if NO catalyst overlay existed — judged on valuation vs the SoP fair value + forensic quality ONLY, explicitly IGNORING catalyst_status and the regime tilt. The two scores MUST be allowed to diverge (a FIRED-catalyst name can be value_conviction 5; a hot-catalyst name can be value_conviction 1); do not default both to the same number.\n' +
    '7. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type, bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, verdict, conviction, value_conviction(int), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_score(int), trajectory, source(="' + (online ? 'opus_regime_online' : 'opus_regime_mod') + '"), transcript_source(="' + (online ? 'web' : 'fmp') + '").\n' +
    'Reply exactly: DONE'
}

// ── LEDGER RE-CHECKS: unexpired forensic-EXCLUDE names get a SHORT re-affirm pass, not a full debate ──
const RECHECK_SYMS = __RECHECK_SYMS__
const RECHECK_INFO = __RECHECK_INFO__
function recheckPrompt(sym) {
  const info = RECHECK_INFO[sym] || {}
  return 'LEDGER RE-CHECK for ' + sym + ' (Claude Opus 4.8). This name was forensically EXCLUDED on ' + (info.date || 'a prior run') + ' (interrogator credibility <= 2: ' + (info.reason || 'see ledger') + '). Do NOT run a full debate. Read ' + DIR + '/inputs/' + sym + '.json, then WebSearch ONLY for material changes since ' + (info.date || 'the exclusion') + ' (new filings, restatements, management change, resolved investigations, a transformed balance sheet). If NOTHING material changed, re-affirm the exclusion in one paragraph. If something material DID change, say so and recommend a full re-debate next run.\n' +
    'Write (Write tool) VALID JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type, verdict(="C" unless materially changed), conviction(int, keep 1-2 unless changed), value_conviction(int), catalyst_status(="UNVERIFIABLE" unless verified), interrogator_score(int, keep <=2 unless the forensic picture genuinely changed), trajectory, moderator_conclusion(the one-paragraph re-affirmation or the change note), bull_thesis(""), bear_thesis(""), sop_bull(""), sop_bear(""), sop_fair_value(""), sop_breakdown(""), risk_reward(""), peer_comps_note(""), consensus_delta(""), valley_of_death(""), positioning_washout(""), forcing_function(""), source(="ledger_recheck"), transcript_source(="web"). Reply exactly: DONE'
}

const ALL = SYMS.map(s => ({ sym: s, online: false, recheck: false }))
  .concat(ONLINE_SYMS.map(s => ({ sym: s, online: true, recheck: false })))
  .concat(RECHECK_SYMS.map(s => ({ sym: s, online: true, recheck: true })))
log(`Radar done. Weekly Opus debate over ${ALL.length} names (${SYMS.length} FMP + ${ONLINE_SYMS.length} online-fetch + ${RECHECK_SYMS.length} ledger re-checks), then Director.`)
phase('Debate')
const BATCH = 8   // rate-limit safety: run 8 web-heavy agents at a time, not the full universe burst (429s).
for (let b = 0; b < ALL.length; b += BATCH) {
  log(`Debate batch ${Math.floor(b / BATCH) + 1}/${Math.ceil(ALL.length / BATCH)} (names ${b + 1}-${Math.min(b + BATCH, ALL.length)} of ${ALL.length})`)
  await parallel(ALL.slice(b, b + BATCH).map(it => () => agent(
    it.recheck ? recheckPrompt(it.sym) : debatePrompt(it.sym, it.online),
    { label: (it.recheck ? 'recheck:' : 'debate:') + it.sym + (it.online && !it.recheck ? '(web)' : ''), phase: 'Debate', agentType: 'general-purpose', model: 'opus' })))
}

phase('Director')
await agent(
  'You are the SPECULAIR APEX DIRECTOR (Claude Fable 5). The CRO already reconciled each name to a Sum-of-Parts fair value + risk/reward + a LIVE catalyst_status, with Radar peer comps.\n' +
  'STEP 1 — Read CATALYST_WATCH_REGIME.md (repo root) IN FULL and apply its tilt.\n' +
  'STEP 2 — Run: python backend/_opus_debate/compact_table.py results_regime — confirm the row count; also read ' + DIR + '/peer_groups.json for the relative-value picture.\n' +
  'STEP 3 — Eligible = conviction >= 3. Select using sop_fair_value / risk_reward / catalyst_status AS PRIMARY LEVERS: a FIRED catalyst is NOT an asymmetric special-sit (re-rate it to a sized-to-spread ARB or a defensive anchor — do NOT size as conviction-4); a SOFT_EXTENDED catalyst is mid-conviction at best; prefer the widest risk_reward to a credible SoP fair value. Then regime fit, forcing-function datedness, consensus-delta width. You MAY Read individual ' + RES + '/<SYM>.json for finalists.\n' +
  'STEP 4 — CORRELATION/EXPOSURE STRESS over the proposed 10 (MANDATORY, beyond the <=3/sector cap): decompose on (a) DEMAND-CYCLE beta (cyclical industrials/consumption that de-rate together in a recession), (b) REGULATORY JURISDICTION (e.g. Italian/EU sign-off), (c) LIQUIDITY/POSITIONING (small-caps that de-gross together), (d) POSTURE (count of wait-for-the-flush entries — a correlated timing bet). No hidden factor may carry >3 names; stress the book against a EUROPEAN-CYCLICAL-RECESSION + CORRELATED-DE-GROSS scenario and diversify if it fails; sequence entries assuming flushes arrive together.\n' +
  'STEP 5 — Each pick: symbol, sector, director_conviction (0-100), one-sentence thesis, sop_fair_value, catalyst_status, lane, regime_fit, exposure_axes (hidden factors it carries). Plus ~6 runner_ups and a director_memo stating the correlation-stress result. The director_memo MUST end with a "BEAR REBUTTAL" subsection: ONE sentence per apex seat stating the STRONGEST reason that pick is wrong, written BEFORE final sizing — if you cannot articulate the bear in one sentence, you do not understand the position.\n' +
  'STEP 6 — Write (Write tool) VALID JSON to ' + DIR + '/apex_basket_opus_regime.json = {apex_basket:[...], director_memo, runner_ups:[...]}. Reply exactly: DONE',
  { label: 'director', phase: 'Director', model: 'fable' })
log('Radar + debate + director complete.')
return 'DONE'
"""


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prep"
    if mode == "prep":
        prep()
    elif mode == "merge":
        merge_radar()
    elif mode == "export-csv":
        export_debate_csv()
    elif mode == "finish":
        finish_debate()
    elif mode == "value-input":
        value_input()
    elif mode == "value-csv":
        value_csv()
    elif mode == "baskets-csv":
        baskets_csv()
    elif mode in ("value-post", "value_post"):
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "_value_post.py")] + (["--offline"] if "--offline" in sys.argv else []), check=True)
    elif mode in ("value-revalidate", "value_revalidate"):
        value_revalidate()
    elif mode in ("disruptor-universe", "disruptor_universe"):
        disruptor_universe()
    elif mode in ("disruptor-map-merge", "disruptor_map_merge"):
        disruptor_map_merge()
    elif mode in ("value-skeptic", "value_skeptic"):
        value_skeptic()
    elif mode in ("shadow-debate", "shadow_debate"):
        shadow_debate()
    elif mode in ("shadow-diff", "shadow_diff"):
        shadow_diff()
    elif mode in ("control-sample", "control_sample"):
        control_sample()
    elif mode == "value-publish":
        value_publish(push_gcs=("--gcs" in sys.argv))
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)
