#!/usr/bin/env python3
"""
_post_board.py — deterministic post-skeptic enforcement + enrichment pass.

Sits between the skeptic tier and _export_candidates.py in the Catalyst Watch
pipeline (see Methodology manual §6, §9). It does ONLY the things that should be
deterministic — the parts the Opus-4.8 agents are structurally bad at (consistency,
the §3 lane tilt, driver tagging, rubric-floor hygiene) — and leaves all judgment
(is the catalyst real? is the figure hallucinated? is the thesis stale?) to the
agents + skeptic, where the manual correctly puts the reliability load.

DESIGN INVARIANTS
  * score != edge is preserved. The §3 lane TILT goes into a separate sort key
    (`board_priority`), never into `adjusted_loeb_score`. The catalyst score stays
    a pure "how clean/hard/imminent is the catalyst" measure.
  * Corrections only ever DEMOTE, never promote. Promotion needs judgment → agents.
  * Every mutated field keeps a `<field>_orig` backup. Nothing is destructive.
  * NO blanket verify-cap. Verified against the live board: every ACTIVE name is
    SKEPTIC_CONFIRMED and every unverified/(sweep) name is already held in WATCH,
    so a verify-cap would be redundant with the tier system. The only score
    correction here is the lane-9 coin-flip cap (a score-VALIDITY fix, not edge).

Field access is isolated in COLS so this can be repointed from the flat export
schema to _sweep_board.json by editing one dict.

Usage:
    python3 _post_board.py IN.csv  --report            # dry-run: print deltas, write nothing
    python3 _post_board.py IN.csv  -o OUT --tilt 0.12   # write enriched OUT.{csv,json}
"""
from __future__ import annotations
import argparse, json, os, re, sys
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Field adapter — the ONLY place that knows the input schema. Repoint here for
# _sweep_board.json if its keys differ from the flat export.
# ---------------------------------------------------------------------------
COLS = {
    "symbol":   "symbol",
    "score":    "adjusted_loeb_score",
    "tier":     "tier",
    "lane":     "lane",
    "edge":     "edge",
    "thesis":   "thesis_summary",
    "verdict":  "verdict",
    "rr":       "rr_ratio",
    "rr_prose": "loeb_risk_reward",
}
TILT_DEFAULT = 0.12          # sort-key nudge per lane-priority step (lane1..lane9 ≈ one score band)
INJECT_FLOOR = 4.0           # manual §6: inject only if score >= 4
COINFLIP_CAP = 6.0           # lane-9 (bio-as-convergence) that is a 50/50 cannot hold a 7-8

# ---------------------------------------------------------------------------
# §3 canonical lanes + priority (1 = highest structural asymmetry / edge-richness)
# ---------------------------------------------------------------------------
LANE_PRIORITY = {
    "forced_seller":   1,
    "spinoff":         2,
    "distressed":      3,
    "index_flow":      4,
    "activist":        5,
    "merger_arb":      6,
    "capital_return":  7,
    "supply_timing":   8,
    "bio_convergence": 9,
    "unknown":         9,   # unmapped → treated as lowest-priority, and counted/warned
}

def canon_lane(raw: str) -> str:
    """Collapse the 105 free-text lane strings to the 9 §3 canon lanes."""
    s = ("" if raw is None else str(raw)).lower()
    if not s.strip():
        return "unknown"
    # order matters: most specific structural lane wins before generic merger/arb
    if re.search(r"forced[- ]?sell|forced.?divest|divestit|forced[- ]?seller", s):  return "forced_seller"
    if re.search(r"spin[- ]?off|spinoff|spin_", s) and "rmt merger" not in s:        return "spinoff"
    if re.search(r"distress|restructur|\blme\b|refi|in-court|deleverag|litigation", s): return "distressed"
    if re.search(r"index[ _-]?flow|forced rebalan", s):                              return "index_flow"
    if re.search(r"activist|cooperation|proxy|sotp|structural|simplif|strategic-review", s): return "activist"
    if re.search(r"capital[-_ ]?return|capital[-_ ]?milestone|forced_capital|buyback|special[-_ ]?div|tender|mandatory tender", s): return "capital_return"
    if re.search(r"supply|shortage|moat|timing|project sanction|\bjv\b|index inclusion", s): return "supply_timing"
    if re.search(r"pdufa|clinical|biotech|\bbio\b|readout|\bfda\b|\bpma\b|vrbpac|adcomm|binary", s): return "bio_convergence"
    if re.search(r"merger|\barb\b|m&a|\bma\b|take[- ]?private|squeeze|de-?spac|spac|cash event|distribution", s): return "merger_arb"
    return "unknown"

# ---------------------------------------------------------------------------
# Resolution-driver classifier (the §3 conviction metric — now a first-class tag)
# Lane-aware: the lane sets the family, text picks the specific gate.
# ---------------------------------------------------------------------------
def resolution_driver(lane_c: str, text: str) -> str:
    s = text.lower()
    if lane_c == "bio_convergence":
        if re.search(r"pdufa|approval|crl|adcomm|vrbpac|\bbla\b|label|resubmiss", s) \
           and not re.search(r"topline|efficacy data|readout (met|positive)|interim (look|analysis)", s):
            return "FDA_approval_decision"
        return "FDA_clinical_readout"
    if lane_c in ("merger_arb", "capital_return"):
        if re.search(r"\bferc\b|\bstb\b|\bfcc\b|\bpuc\b|nmprc|cpuc|insurance.?reg|public util", s): return "US_sector_regulator"
        if re.search(r"cfius|fdi review|foreign.?acquirer", s):                                     return "CFIUS_FDI"
        if re.search(r"samr|mofcom|china|\beu\b|european comm|\buk\b|\bcma\b|morocco|israel|golden share|kenya|tanzania|works.?council|saudi", s): return "Foreign_regulator"
        if re.search(r"\bdoj\b|\bftc\b|\bhsr\b|second request|antitrust", s):                       return "US_antitrust"
        if re.search(r"shareholder vote|written consent|proxy advisor", s):                          return "Shareholder_vote"
        return "Deal_close_generic"
    if lane_c == "spinoff":                       return "Spin_index_flow"
    if lane_c == "index_flow":                    return "Spin_index_flow"
    if lane_c == "forced_seller":                 return "Forced_divest_flow"
    if lane_c == "distressed":                    return "Refi_restructuring"
    if lane_c == "activist":                      return "Activist_process"
    if lane_c == "supply_timing":
        return "Commodity_price" if re.search(r"copper|gold|oil|potash|uranium|pulp|rare.?earth|helium|silver|\bcoal\b", s) else "Supply_timing"
    return "Other"

# super-cluster rollup for the §3 #5 "hidden common factor" view
SUPER = {
    "FDA_approval_decision": "FDA/biotech", "FDA_clinical_readout": "FDA/biotech",
    "US_antitrust": "Deal-completion", "US_sector_regulator": "Deal-completion",
    "CFIUS_FDI": "Deal-completion", "Foreign_regulator": "Deal-completion",
    "Deal_close_generic": "Deal-completion", "Shareholder_vote": "Deal-completion",
}

def edge_grade(edge: str) -> str:
    s = ("" if edge is None else str(edge)).strip()
    if re.match(r"^high", s, re.I): return "H"
    if re.match(r"^med",  s, re.I): return "M"
    if re.match(r"^low",  s, re.I): return "L"
    m = re.match(r"^(H|M|L)\b", s, re.I)
    return m.group(1).upper() if m else "?"

def verify_status(verdict: str) -> str:
    s = ("" if verdict is None else str(verdict)).lower()
    if "refuted" in s:                                                       return "REFUTED"
    if s.strip() == "(sweep)":                                               return "SCAN_ONLY"
    if "pending adversarial" in s or "adversarial pass pending" in s \
       or s.startswith("unverified") or "discovery-verified" in s or "wave-1" in s: return "UNVERIFIED"
    if "confirmed" in s:                                                     return "SKEPTIC_CONFIRMED"
    return "OTHER"

_COINFLIP = re.compile(
    r"coin[- ]?flip|50/50|true (clinical )?binary|two-sided (clinical |binary )?risk"
    r"|genuinely uncertain|binary downside is severe|directional risk, not a structurally",
    re.I)

# ===========================================================================
# Phase 2 — computed lane-aware R:R (the EDGE axis, quantified). Division of labor:
# the Opus deep dossier owns the VALUATION (target/floor/prob + the SoP build, all
# judgment); THIS module owns the RATIO MATH against a FRESH live price (deterministic,
# identical across lanes). Edge drives edge_grade + the edge view — it NEVER touches
# adjusted_loeb_score or board_priority. The one allowed edge→tier move: an inverted/
# negative R:R (no upside left / trading through terms) drops to NONE.
# ===========================================================================
FMP_KEY  = os.environ.get("FMP_API_KEY") or "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
FMP_BASE = "https://financialmodelingprep.com/stable"
DRIFT_REDOSSIER = 0.15            # |move since dossier| beyond this -> RE_DOSSIER flag
RATIO_METHODS = ("sop", "recovery", "capital_return")
# lane -> default valuation method (fallback only; the dossier sets valuation_method)
METHOD_FOR_LANE = {
    "forced_seller": "sop", "spinoff": "sop", "activist": "sop",
    "merger_arb": "spread", "capital_return": "capital_return",
    "bio_convergence": "binary_prob", "distressed": "recovery",
}

def fetch_live_quotes(symbols, batch=80):
    """Fresh FMP REST batch quotes -> {SYMBOL: price}. {} on failure (caller flags stale)."""
    out = {}
    syms = sorted({str(x).upper() for x in symbols if x and isinstance(x, str)})
    for i in range(0, len(syms), batch):
        try:
            r = requests.get(f"{FMP_BASE}/batch-quote",
                             params={"symbols": ",".join(syms[i:i + batch]), "apikey": FMP_KEY}, timeout=25)
            for q in (r.json() or []):
                if q.get("symbol") and q.get("price") is not None:
                    out[str(q["symbol"]).upper()] = float(q["price"])
        except Exception:
            continue
    return out

def _vf(row, key):
    v = row.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v

def rr_ratio_lane(method, live, f):
    """Deterministic lane-aware R:R vs the fresh `live` price. f = dossier fields (dict).
    Returns: float (clean ratio), dict (binary barbell), ('TINY', rr) (rr but <5% downside),
    ('FLAG', reason) (edge L, stays on board), ('DROP', reason) (tier->NONE), or None (un-computable)."""
    if method in RATIO_METHODS:
        tgt, flr = _vf(f, "fair_value_target"), _vf(f, "downside_floor")
        if tgt is None or flr is None: return None
        up, dn = tgt - live, live - flr
        if up <= 0: return ("FLAG", "NO_UPSIDE")        # target<=live: catalyst already played out
        if dn <= 0: return ("FLAG", "FLOOR_GE_LIVE")    # floor>=live: no/inverted downside
        return up / dn                                  # thin-floor handled in the overlay (needs dn)
    if method == "spread":
        dp, un = _vf(f, "deal_price"), _vf(f, "undisturbed_price")
        if dp is None or un is None: return None
        up, dn = dp - live, live - un
        if up <= 0: return ("DROP", "TRADING_THROUGH_TERMS")   # negative spread
        if dn <= 0: return ("FLAG", "NO_BREAK_DOWNSIDE")
        return up / dn
    if method == "binary_prob":                                # barbell, NOT a single ratio
        p, tw, dl = _vf(f, "win_prob"), _vf(f, "target_on_win"), _vf(f, "downside_on_loss")
        if p is None or tw is None or dl is None: return None
        ev = p * (tw - live) + (1 - p) * (dl - live)
        payoff = (tw - live) / max(live - dl, 1e-9)
        return {"ev_pct": ev / live, "win_prob": p, "payoff": payoff,
                "up_leg": tw - live, "down_leg": live - dl}
    return None

def grade_from_measure(method, res):
    """edge_grade from the computed measure (calibratable starting thresholds)."""
    if method == "binary_prob" and isinstance(res, dict):
        if res["ev_pct"] >= 0.15 and res["payoff"] >= 2: return "H"
        return "M" if res["ev_pct"] > 0 else "L"
    if isinstance(res, (int, float)):
        if res >= 2.5: return "H"
        if res >= 1.5: return "M"
        return "L"
    return "?"

MULT_BAND = {"EBITDA": (4, 25), "sales": (0.5, 12)}   # plausible EV/x bands; outliers flagged

def _n(x):
    try:
        v = float(x)
        return None if v != v else v   # drop NaN
    except (TypeError, ValueError):
        return None

def sop_integrity(v, live, tol=0.05):
    """Deterministic backstop (sop lanes only). Recompute the build from the components and run the
    integrity checks that catch this run's failures MECHANICALLY: units chaos, per-row arithmetic,
    out-of-band multiples, advocacy/premium stacked on the build, and absurd per-share values.
    Returns (built_per_share|None, flags[list], quarantine_bool). R:R is ALWAYS driven off `built`;
    a quarantined name shows NO number (its inputs are broken)."""
    flags = []
    comps = v.get("sop_components") or []
    so = _n(v.get("shares_out"))
    if not comps or not so:
        return (None, flags, False)
    nd = _n(v.get("net_debt")) or 0.0
    adj = _n(v.get("adjustments")) or 0.0
    tgt = _n(v.get("fair_value_target"))
    # per-row arithmetic + multiple bands  (ev == metric x multiple, or metric x ownership for stakes)
    for c in comps:
        m = c.get("driver_metric"); mv = _n(c.get("metric_value")); ev = _n(c.get("ev_contribution"))
        mult = _n(c.get("multiple")); own = _n(c.get("ownership"))
        seg = str(c.get("segment", ""))[:18]
        if mv is not None and ev is not None:
            factor = own if (m == "stake_mv" and own is not None) else (mult if mult is not None else 1.0)
            expect = mv * factor
            if abs(expect) > 1e-9 and abs(expect - ev) / abs(expect) > 0.01:
                flags.append("ROW_EV_MISMATCH:" + seg)
        if m in MULT_BAND and mult is not None and not (MULT_BAND[m][0] <= mult <= MULT_BAND[m][1]):
            flags.append("MULTIPLE_OUT_OF_BAND:%s(%gx)" % (seg, mult))
    try:
        built = (sum(_n(c.get("ev_contribution")) or 0.0 for c in comps) - nd - adj) / so
    except ZeroDivisionError:
        return (None, flags, True)
    # units: declared+sane is clean; declared-insane or implausible build -> quarantine
    u = v.get("units") or {}
    units_ok = u.get("shares") == "millions" and u.get("money") == "usd_millions"
    if not units_ok:
        flags.append("UNITS_UNDECLARED")
    # implausible per-share build = the unit-chaos signature (INIO -$2M/sh, B/BN built ~0 vs a real target)
    absurd = (built < 0 or (live and abs(built) > 50 * live)
              or (tgt and abs(tgt) > 1 and abs(built) < 0.1 * abs(tgt)))
    quarantine = any(f.startswith("ROW_EV_MISMATCH") for f in flags) or absurd
    if absurd:
        flags.append("ABSURD_BUILD")
    # reconcile asserted target to the build (MAT's $24-vs-$30 advocacy gap)
    if tgt and built and abs(built - tgt) / abs(built) > tol:
        flags.append("SOP_TARGET_MISMATCH")
    return (built, flags, quarantine)

# ---------------------------------------------------------------------------
def process(df: pd.DataFrame, tilt: float, live_prices=None):
    c = COLS
    deltas = []  # (symbol, field, old, new, reason)

    # ---- enrichment (non-destructive) ----
    df["lane_canon"]    = df[c["lane"]].apply(canon_lane)
    df["lane_priority"] = df["lane_canon"].map(LANE_PRIORITY).astype(int)
    df["edge_grade"]    = df[c["edge"]].apply(edge_grade)
    df["verify_status"] = df[c["verdict"]].apply(verify_status)
    _txt = (df[c["edge"]].fillna("") + " " + df[c["thesis"]].fillna(""))
    df["resolution_driver"] = [resolution_driver(l, t) for l, t in zip(df["lane_canon"], _txt)]

    # backups before any mutation
    df[c["score"] + "_orig"] = df[c["score"]]
    df[c["tier"] + "_orig"]  = df[c["tier"]]
    df[c["rr"] + "_orig"]    = df[c["rr"]]
    df["corrections"]        = [[] for _ in range(len(df))]

    def log(i, field, old, new, reason):
        deltas.append((df.at[i, c["symbol"]], field, old, new, reason))
        df.at[i, "corrections"].append(reason)

    for i in df.index:
        sym = df.at[i, c["symbol"]]
        score = float(df.at[i, c["score"]])
        tier  = str(df.at[i, c["tier"]])
        vs    = df.at[i, "verify_status"]
        lane_c = df.at[i, "lane_canon"]

        # (1) lane-9 coin-flip cap — score VALIDITY fix (a 50/50 fails the §3 lane-9
        #     "mispriced asymmetry, not a coin-flip" qualifier, so it cannot be a 7-8).
        if lane_c == "bio_convergence" and score > COINFLIP_CAP and _COINFLIP.search(_txt.iloc[df.index.get_loc(i)]):
            log(i, "score", score, COINFLIP_CAP, "COINFLIP_NOT_ASYMMETRIC (lane-9 qualifier)")
            score = COINFLIP_CAP
            df.at[i, c["score"]] = score

        # (2) REFUTED still on board → drop (manual §4: failed gate → NONE)
        if vs == "REFUTED" and tier != "NONE":
            log(i, "tier", tier, "NONE", "REFUTED_NOT_DROPPED")
            df.at[i, c["tier"]] = "NONE"; tier = "NONE"

        # (3) below inject floor → drop (manual §6: inject only if score >= 4)
        if score < INJECT_FLOOR and tier != "NONE":
            log(i, "tier", tier, "NONE", f"BELOW_INJECT_FLOOR(<{INJECT_FLOOR})")
            df.at[i, c["tier"]] = "NONE"; tier = "NONE"

        # (4) R/R hygiene — the stamped 1.8 template is not a computed ratio; we cannot
        #     compute a real one from export fields, so null it and flag for the agent layer.
        rr = df.at[i, c["rr"]]
        if pd.notna(rr) and abs(float(rr) - 1.8) < 1e-9:
            log(i, "rr_ratio", rr, None, "RR_TEMPLATE_NULLED")
            df.at[i, c["rr"]] = None

    # ---- computed lane-aware R:R overlay (EDGE axis) — activates ONLY when the deep
    #      dossier has valued the name. Un-valued rows keep phase-1 behavior (rr null,
    #      text-parsed edge_grade), so score/board_priority stay byte-identical to phase 1.
    for col in ("computed_rr", "ev_pct", "win_prob", "payoff", "up_leg", "down_leg",
                "live_price", "drift", "sop_built"):
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df), dtype="object")   # object: holds float|None (pandas-3 strict)
    if "edge_flags" not in df.columns:
        df["edge_flags"] = [[] for _ in range(len(df))]
    has_val = "valuation_method" in df.columns and df["valuation_method"].notna().any()
    if has_val:
        live_prices = live_prices if live_prices is not None else fetch_live_quotes(list(df[c["symbol"]]))
        for i in df.index:
            method = df.at[i, "valuation_method"]
            if not method or (isinstance(method, float) and pd.isna(method)):
                continue
            method = str(method)
            row = df.loc[i].to_dict()
            sym = str(df.at[i, c["symbol"]]).upper()
            ref = _vf(row, "reference_price")
            live = live_prices.get(sym)
            px = live if live is not None else ref
            if px is None:
                continue
            df.at[i, "live_price"] = px
            if live is None:
                df.at[i, "edge_flags"].append("RR_STALE")   # staleness surfaced via edge_flags
            if ref:
                drift = (px - ref) / ref
                df.at[i, "drift"] = round(drift, 4)
                if abs(drift) > DRIFT_REDOSSIER:
                    df.at[i, "edge_flags"].append("RE_DOSSIER")
            # sop integrity guard — units / per-row arithmetic / multiple-band / reconcile. R:R is
            # ALWAYS driven off the reconciled BUILD (never the asserted/advocacy target); names whose
            # inputs are broken (unit chaos / row arithmetic) are QUARANTINED — no number on bad data.
            quarantined = False
            if method == "sop":
                vdict = row.get("_val")
                if isinstance(vdict, dict):
                    built, sflags, quarantined = sop_integrity(vdict, px)
                    for sf in sflags:
                        df.at[i, "edge_flags"].append(sf)
                    if built is not None:
                        df.at[i, "sop_built"] = round(built, 2)
                        row = dict(row); row["fair_value_target"] = built   # R:R off the build, period
            if quarantined:
                df.at[i, "edge_grade"] = "L"
                df.at[i, "edge_flags"].append("QUARANTINED")
                continue                                    # broken inputs -> show no R:R
            res = rr_ratio_lane(method, px, row)
            if isinstance(res, tuple) and res[0] == "DROP":
                # spread trading through terms -> NONE (the one allowed edge->tier move). score/bp untouched.
                if str(df.at[i, c["tier"]]) != "NONE":
                    log(i, "tier", df.at[i, c["tier"]], "NONE", res[1])
                    df.at[i, c["tier"]] = "NONE"
                df.at[i, "edge_grade"] = "L"
                df.at[i, "edge_flags"].append(res[1])
            elif isinstance(res, tuple) and res[0] == "FLAG":
                # no upside / floor>=live / no break downside -> edge L, STAYS (re-opens on a pullback)
                df.at[i, "edge_grade"] = "L"
                df.at[i, "edge_flags"].append(res[1])
            elif method == "binary_prob" and isinstance(res, dict):
                df.at[i, "ev_pct"]   = round(res["ev_pct"], 4)
                df.at[i, "win_prob"] = round(res["win_prob"], 3)
                df.at[i, "payoff"]   = round(res["payoff"], 2)
                df.at[i, "up_leg"]   = round(res["up_leg"], 2)
                df.at[i, "down_leg"] = round(res["down_leg"], 2)
                df.at[i, "edge_grade"] = grade_from_measure(method, res)
                df.at[i, c["rr"]] = None            # binary: suppress a single R:R (the AMLX-1.8 trap)
            elif isinstance(res, (int, float)):
                df.at[i, "computed_rr"] = round(res, 2)
                df.at[i, c["rr"]] = round(res, 2)   # rr_ratio = computed (replaces the null)
                g = grade_from_measure(method, res)
                # a ratio resting on too little downside is not a confident H — cap at M + flag.
                # (catches MAT-class: a chart-low floor manufactures a thin denominator and inflates the ratio.)
                flr = _vf(row, "undisturbed_price") if method == "spread" else _vf(row, "downside_floor")
                dn = (px - flr) if flr is not None else None
                if dn is not None and dn < 0.15 * px:
                    df.at[i, "edge_flags"].append("TINY_FLOOR" if dn < 0.05 * px else "THIN_FLOOR")
                    if g == "H":
                        g = "M"
                df.at[i, "edge_grade"] = g

    # ---- ranking: §3 tilt as a SEPARATE sort key; score stays pure ----
    df["board_priority"] = df[c["score"]].astype(float) - tilt * (df["lane_priority"] - 1)
    tier_rank = {"ACTIVE": 0, "CONTINGENT": 1, "WATCH": 2, "NONE": 9}
    src_rank  = {"manual": 0, "widen": 1, "sweep": 2}
    df["_tr"]  = df[c["tier"]].map(tier_rank).fillna(3)
    df["_sr"]  = df.get("source", pd.Series(["sweep"] * len(df))).map(src_rank).fillna(2)
    df = df.sort_values(["_tr", "board_priority", "lane_priority", "_sr", c["symbol"]],
                        ascending=[True, False, True, True, True]).drop(columns=["_tr", "_sr"])
    return df, deltas

# ---------------------------------------------------------------------------
def reports(df, deltas, tilt):
    c = COLS
    out = []
    out.append("=" * 72)
    out.append(f"POST-BOARD ENFORCEMENT — {len(df)} rows in,  tilt={tilt}")
    out.append("=" * 72)

    # lane mapping coverage (flag unmapped so the normalizer can be extended)
    unk = (df["lane_canon"] == "unknown").sum()
    out.append(f"\nLane normalization: {df['lane_canon'].nunique()} canon lanes "
               f"from {df[c['lane']].nunique()} raw strings"
               + (f"   ⚠ {unk} UNMAPPED → review canon_lane()" if unk else "   (all mapped)"))

    # deltas (the auditable reproduce→correct piece)
    out.append(f"\n--- CORRECTIONS ({len(deltas)} total) ---")
    if not deltas:
        out.append("  none")
    else:
        by_reason = {}
        for sym, field, old, new, reason in deltas:
            by_reason.setdefault(reason, []).append((sym, field, old, new))
        for reason, items in sorted(by_reason.items()):
            out.append(f"\n  [{reason}]  x{len(items)}")
            for sym, field, old, new in items[:25]:
                o = "∅" if old is None else (f"{old:.1f}" if isinstance(old, float) else old)
                n = "∅" if new is None else (f"{new:.1f}" if isinstance(new, float) else new)
                out.append(f"      {sym:8s} {field:6s} {o} → {n}")

    # tier movement summary
    moved = df[df[c["tier"]] != df[c["tier"] + "_orig"]]
    out.append(f"\n--- TIER MOVEMENT: {len(moved)} names re-tiered ---")
    for _, r in moved.iterrows():
        out.append(f"    {r[c['symbol']]:8s} {r[c['tier']+'_orig']:10s} → {r[c['tier']]}")

    # lane-mix BEFORE vs AFTER tilt (top-15 by each), shows the §3 tilt working
    board = df[df[c["tier"]].isin(["ACTIVE", "CONTINGENT", "WATCH"])]
    out.append("\n--- TOP 15 by RAW score (pre-tilt) vs board_priority (post-tilt) ---")
    a = board.sort_values(c["score"]+"_orig", ascending=False).head(15)
    b = board.head(15)  # already sorted by board_priority within tier
    out.append(f"    {'RAW score':<34}{'TILTED (board_priority)':<34}")
    for (_, ra), (_, rb) in zip(a.iterrows(), b.iterrows()):
        la = f"{ra[c['symbol']]:6s} {ra[c['score']+'_orig']:.1f} {ra['lane_canon'][:14]:14s}"
        lb = f"{rb[c['symbol']]:6s} {rb['board_priority']:.2f} {rb['lane_canon'][:14]:14s}"
        out.append(f"    {la:<34}{lb:<34}")

    # §3 #5 resolution-driver concentration (ACTIVE, post-correction)
    act = df[df[c["tier"]] == "ACTIVE"]
    out.append(f"\n--- RESOLUTION-DRIVER CONCENTRATION — ACTIVE (n={len(act)}) ---")
    vc = act["resolution_driver"].value_counts()
    for d, n in vc.items():
        out.append(f"    {d:24s} {n:2d}  ({100*n/len(act):4.1f}%)")
    sup = act["resolution_driver"].map(lambda d: SUPER.get(d, "Idiosyncratic")).value_counts()
    out.append("    " + "-" * 40)
    for d, n in sup.items():
        out.append(f"    » {d:22s} {n:2d}  ({100*n/len(act):4.1f}%)")
    return "\n".join(out)

# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp1252 stdout chokes on the → glyphs
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("-o", "--out", default="catalyst_board_enriched")
    ap.add_argument("--tilt", type=float, default=TILT_DEFAULT)
    ap.add_argument("--report", action="store_true", help="dry-run: print reports, write nothing")
    args = ap.parse_args()

    df = pd.read_csv(args.infile) if args.infile.endswith(".csv") else pd.read_json(args.infile)
    df, deltas = process(df, args.tilt)
    print(reports(df, deltas, args.tilt))

    if not args.report:
        df.to_csv(args.out + ".csv", index=False)
        df.to_json(args.out + ".json", orient="records", indent=2)
        print(f"\nwrote {args.out}.csv  +  {args.out}.json")

if __name__ == "__main__":
    main()
