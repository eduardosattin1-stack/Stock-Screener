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

RUBRIC — four pillars ~25 pts each, applied ONLY to names that clear the gate:
1. MARGIN OF SAFETY — primary = sop_mos_pct (CRO-normalized). Cross-check `mos_spread` AGREEMENT (4-5/5 models positive = high-confidence cheap) but DISCOUNT any model MoS on a name flagged peak/stale below.
2. CYCLICAL-PEAK vs DURABLE-GROWTH — apply BEFORE crediting any cheapness. `peak_flag`=true (eps_peak_ratio>=1.4 OR fcf_cagr_3y>=60%) means the latest earnings sit far above the multi-year base — you MUST distinguish two cases, because the flag fires on BOTH:
   (a) CYCLICAL PEAK / recovery artifact = peak_flag AND (`freshness_stale`=true [FY numerator > live TTM, or latest_q_eps_yoy<=-15%] OR weak/negative `revenue_cagr_3y` OR a commodity/cyclical end-market). Earnings are at a cycle high and ALREADY ROLLING OVER. NORMALIZE to mid-cycle (use `eps_normalized`, not `fy_eps`) and treat the headline multiple as FAKE-cheap. These are the BRBR/CALM artifacts (CALM eps_peak_ratio ~9 on the egg windfall; both rolling over). A low multiple on peak earnings is NOT value.
   (b) DURABLE GROWTH = peak_flag BUT `freshness_stale`=false (still growing, positive latest-Q YoY) AND durable positive `revenue_cagr_3y` AND healthy ROIC. The high ratio reflects a secular re-rate or a real turnaround (a brand compounding), NOT a cycle peak — do NOT normalize it away; credit it, but sanity-check the multiple vs true peers.
   In BOTH cases `sop_mos_pct` (the CRO's already-normalized fair value) is the ANCHOR: if the CRO normalized the name and STILL shows a positive MoS, the cheapness is real; if the CRO's MoS collapsed far below `scan_headline_mos_pct`, it was a peak artifact.
3. FUNDED-LEVERAGE SOLVENCY (this REPLACES raw Altman-Z, which uses total liabilities and over-penalizes float/reserve businesses). Judge solvency on FUNDED debt only — `net_funded_debt_ebitda` (net interest-bearing debt / EBITDA, so settlement/payroll float and policyholder reserves are structurally excluded) + `interest_coverage`; the `funded_solvency` field pre-buckets it. IGNORE raw `altman_z`.
   - `is_financial`=true (banks/insurers) OR `funded_solvency` in {exempt_financial, strong}: solvency is FINE — do NOT penalize. This clears EEFT/TNET (~0.8-1.6x funded, strong coverage), SCR.PA and the bank/insurer set on the RIGHT basis (their low Altman-Z was a float/reserve artifact), and any net-cash name.
   - REAL-funded-debt names (`funded_solvency` = moderate or weak): drop the Z number and near-VETO ONLY when the metrics are JOINTLY weak — high funded leverage (net_funded_debt_ebitda > ~3.5x) AND thin coverage (interest_coverage < ~3x) AND a near-term MATURITY WALL (check the name's dossier at backend/_opus_debate/dossiers/<SYM>.md for refinancing/maturity risk). ONE weak metric alone is NOT a veto: a 2-3x-levered name with healthy coverage and no wall is acceptable value — just note the leverage in the thesis. (Worked example: SAX.DE ~3.0x / 3.7x coverage = the book's most-levered name → keep only if the dossier shows no near maturity wall.)
   - `net_debt_exceeds_mktcap`=true remains a thin-equity flag — NEVER credit net debt as "net cash."
4. MULTIPLES vs TRUE PEERS (`peer_verdict`/`peer_relative_comps`) + GROWTH DURABILITY/QUALITY (durable positive revenue/EPS growth + ROIC>~8-10% SUPPORT value; negative 3yr revenue CAGR + sub-WACC ROIC + thin/eroding margins = a value trap even when optically cheap).

HARD CONSTRAINTS: <=3 names per sector. Every apex name must (a) clear forensic_gate, (b) survive cyclical-peak normalization with a STILL-POSITIVE normalized MoS, (c) be cheap on TRUE peers, (d) not be a value trap.

HIDDEN-FACTOR CORRELATION STRESS (run over the final 10 BEFORE sizing — the <=3/sector cap is NOT a correlation control; GICS sectors miss shared real-world factors). Decompose the 10 on HIDDEN factors: (a) END-MARKET DEMAND CYCLE (consumer-discretionary / travel / housing), (b) REGULATORY or REIMBURSEMENT REGIME (e.g. US hospital Medicaid Directed-Payment-Program / a 2028 reimbursement ruling), (c) ADVERTISING CYCLE (cable & theme-park ad spend, out-of-home advertising), (d) RATE / CREDIT sensitivity, (e) a SINGLE shared macro (one commodity, one FX, one policy). FLAG every hidden factor carrying >=2 names. Known live clusters to check EXPLICITLY: THC+UHS (both ride the 2028 Medicaid-DPP / US hospital-reimbursement outcome) and CMCSA+SAX.DE (both advertising-cycle — cable ads + theme-park spend, and out-of-home advertising). For each >=2 cluster, EITHER (i) DIVERSIFY: swap the lower-value leg for the best orthogonal eligible name / runner-up that does NOT re-cluster (note ARDT re-clusters with hospitals, SREN.SW with SCR.PA reinsurance), OR (ii) keep both ONLY with an explicit combined-size cap + written justification — no hidden factor may quietly carry two full-size legs. A single reimbursement ruling or an ad-recession must not hit two legs at once.

OUTPUT — Write VALID JSON to backend/_opus_debate/apex_basket_value.json = {apex_basket:[{symbol, sector, value_score(0-100), thesis(one sentence), mos_agreement(e.g. "4/5"), sop_mos_pct, net_funded_debt_ebitda, interest_coverage, funded_solvency, peer_verdict, growth_durability, peak_normalized(bool: did you have to discount peak/stale earnings), exposure_axes(list of the hidden factors this name carries, e.g. ["hospital-reimbursement","advertising-cycle"]), forensic_gate, trap_flag}], runner_ups:[...~6], value_memo}. The value_memo MUST: (a) state the rubric weighting; (b) LIST the names EXCLUDED or CAPPED by the forensic gate and those down-rated as cyclical-peak/stale artifacts — call out BRBR and CALM EXPLICITLY with their CRO-normalized fair value vs the raw scan MoS; (c) give the name-by-name RISE/FALL vs the prior value apex (the caller specifies the prior apex in the run instruction; if none is given, read the existing backend/_opus_debate/apex_basket_value.json for the prior slate BEFORE you overwrite it); (d) a correlation_stress section naming EACH hidden-factor cluster of >=2 (INCLUDING the THC/UHS reimbursement and CMCSA/SAX.DE advertising pairs) and EXACTLY how you resolved it (diversified -> which swap and why; or kept-with-sizing -> the combined cap and the justification). Reply exactly: DONE"""


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
    (ROOT / "value_director_prompt.txt").write_text(VALUE_DIRECTOR_PROMPT, encoding="utf-8")
    npeak = sum(1 for x in out if x["peak_flag"])
    ngate = sum(1 for x in out if x["forensic_gate"])
    nstale = sum(1 for x in out if x["freshness_stale"])
    from collections import Counter as _C
    fs = _C(x["funded_solvency"] for x in out)
    print(f"value_grade_input.json: {len(out)} names | peak_flag={npeak} forensic_gate={ngate} freshness_stale={nstale}")
    print(f"  funded_solvency: {dict(fs)}")
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
            "peak_flag", "eps_peak_ratio", "freshness_stale", "peer_verdict_director", "growth_durability", "exposure_axes", "trap_flag",
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
            "regime_role", "regime_director_conviction", "regime_lane", "regime_catalyst_status", "regime_director_thesis",
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
    out = {"apex_basket": picks, "runner_ups": apx.get("runner_ups", []),
           "value_memo": apx.get("value_memo", ""), "value_tracking": vt,
           "generated_at": _dt.date.today().isoformat(),
           "engine": "opus-4.8-value-funded-leverage", "universe": 161}
    (PUB / "speculair_value_apex.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"value_publish: {len(picks)} apex + {len(out['runner_ups'])} runners | tracking nav={vt.get('nav')} "
          f"since={vt.get('since_inception_pct')}% open={vt.get('n_open')} closed={vt.get('n_closed')} inception={vt.get('inception_date')}")
    if push_gcs:
        import subprocess
        for localf, key in [(PUB / "speculair_value_apex.json", "scans/speculair_value_apex.json"),
                            (PUB / "speculair_value_tracking.json", "scans/speculair_value_tracking.json")]:
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
    js = (_WORKFLOW_TEMPLATE
          .replace("__SYMS__", json.dumps(syms))
          .replace("__ONLINE_SYMS__", json.dumps(no_tx))
          .replace("__N_RADAR__", str(len(radar_groups))))
    out = ROOT / "_weekly_debate.js"
    out.write_text(js, encoding="utf-8")
    print(f"PREP OK: {len(syms)} with FMP transcripts + {len(no_tx)} via online fetch "
          f"= {len(syms) + len(no_tx)} total candidates (online: {no_tx})")
    print(f"WORKFLOW_SCRIPT={out.resolve()}")


_WORKFLOW_TEMPLATE = r"""export const meta = {
  name: 'speculair-opus-weekly',
  description: 'Weekly all-Opus regime debate (Radar peer-comps + Sum-of-Parts) over the per-methodology universe, then Director picks the apex basket',
  phases: [{ title: 'Radar', model: 'sonnet' }, { title: 'Debate' }, { title: 'Director' }],
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
    '6. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward (downside-to-break vs upside-to-fair); DOWN-RATE conviction for FIRED/SOFT catalysts and size ARB to the spread; sanity-check the multiple against the peer comps. Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion.\n' +
    '7. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type, bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, verdict, conviction, consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_score(int), trajectory, source(="' + (online ? 'opus_regime_online' : 'opus_regime_mod') + '"), transcript_source(="' + (online ? 'web' : 'fmp') + '").\n' +
    'Reply exactly: DONE'
}

const ALL = SYMS.map(s => ({ sym: s, online: false })).concat(ONLINE_SYMS.map(s => ({ sym: s, online: true })))
log(`Radar done. Weekly Opus debate over ${ALL.length} names (${SYMS.length} FMP + ${ONLINE_SYMS.length} online-fetch), then Director.`)
phase('Debate')
const BATCH = 8   // rate-limit safety: run 8 web-heavy agents at a time, not the full universe burst (429s).
for (let b = 0; b < ALL.length; b += BATCH) {
  log(`Debate batch ${Math.floor(b / BATCH) + 1}/${Math.ceil(ALL.length / BATCH)} (names ${b + 1}-${Math.min(b + BATCH, ALL.length)} of ${ALL.length})`)
  await parallel(ALL.slice(b, b + BATCH).map(it => () => agent(
    debatePrompt(it.sym, it.online),
    { label: 'debate:' + it.sym + (it.online ? '(web)' : ''), phase: 'Debate', agentType: 'general-purpose' })))
}

phase('Director')
await agent(
  'You are the SPECULAIR APEX DIRECTOR (Claude Opus 4.8). The CRO already reconciled each name to a Sum-of-Parts fair value + risk/reward + a LIVE catalyst_status, with Radar peer comps.\n' +
  'STEP 1 — Read CATALYST_WATCH_REGIME.md (repo root) IN FULL and apply its tilt.\n' +
  'STEP 2 — Run: python backend/_opus_debate/compact_table.py results_regime — confirm the row count; also read ' + DIR + '/peer_groups.json for the relative-value picture.\n' +
  'STEP 3 — Eligible = conviction >= 3. Select using sop_fair_value / risk_reward / catalyst_status AS PRIMARY LEVERS: a FIRED catalyst is NOT an asymmetric special-sit (re-rate it to a sized-to-spread ARB or a defensive anchor — do NOT size as conviction-4); a SOFT_EXTENDED catalyst is mid-conviction at best; prefer the widest risk_reward to a credible SoP fair value. Then regime fit, forcing-function datedness, consensus-delta width. You MAY Read individual ' + RES + '/<SYM>.json for finalists.\n' +
  'STEP 4 — CORRELATION/EXPOSURE STRESS over the proposed 10 (MANDATORY, beyond the <=3/sector cap): decompose on (a) DEMAND-CYCLE beta (cyclical industrials/consumption that de-rate together in a recession), (b) REGULATORY JURISDICTION (e.g. Italian/EU sign-off), (c) LIQUIDITY/POSITIONING (small-caps that de-gross together), (d) POSTURE (count of wait-for-the-flush entries — a correlated timing bet). No hidden factor may carry >3 names; stress the book against a EUROPEAN-CYCLICAL-RECESSION + CORRELATED-DE-GROSS scenario and diversify if it fails; sequence entries assuming flushes arrive together.\n' +
  'STEP 5 — Each pick: symbol, sector, director_conviction (0-100), one-sentence thesis, sop_fair_value, catalyst_status, lane, regime_fit, exposure_axes (hidden factors it carries). Plus ~6 runner_ups and a director_memo stating the correlation-stress result.\n' +
  'STEP 6 — Write (Write tool) VALID JSON to ' + DIR + '/apex_basket_opus_regime.json = {apex_basket:[...], director_memo, runner_ups:[...]}. Reply exactly: DONE',
  { label: 'director', phase: 'Director' })
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
    elif mode == "value-publish":
        value_publish(push_gcs=("--gcs" in sys.argv))
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)
