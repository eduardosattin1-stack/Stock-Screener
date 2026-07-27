#!/usr/bin/env python3
"""Deterministic post-processing for the FUTURE DISRUPTIVE TECH (fdt) Lane A apex
(FUTURE_RESOURCES_SPLIT_SPEC §B/§C — parameterized clone of _fr_post.py, delegating to _post_common
where the signature fits, per the _value_post pattern; _post_common.py, _fr_post.py and
_regime_post.py themselves are NOT edited).

Validates / stamps backend/_opus_debate/fdt/apex_basket_fdt.json AFTER the Director and BEFORE
fdt_csv / fdt_publish. NEVER changes apex membership (design principle P1) — the ONE sanctioned
exception is the skeptic REFUTED -> runner_ups demotion inside _post_common.consume_skeptic.
Idempotent: re-running with --offline reuses the cached market data, so output is byte-identical.

What changed vs _fr_post.py (canon §B is authoritative over every appendix):
  - File constants parameterized to the fdt/ subtree (apex_basket_fdt.json, fdt_grade_input.json,
    results/, dossiers/, _fdt_post_cache.json) + the ROOT-level skeptic shard dir _skeptic_fdt (the
    _skeptic_regime / _skeptic_disruptor naming precedent — shard dirs live at _opus_debate/ level
    even when the book has its own subtree).
  - Beta benchmarks ["GRID", "QQQ"] replace ["XME", "URA"] — canon §B: the FDT benchmark is
    50/50 GRID+QQQ (grid/electrification equipment + long-duration tech), the same pair the publisher
    and the card label stamp. Emits chain_beta = {sym: {grid, qqq}}.
  - SKEPTIC TIER RESTORED (the FR Lane A chain had none): _post_common.consume_skeptic runs BEFORE
    weights (fork b — a fresh REFUTED apex member is DEMOTED to the front of runner_ups) and the
    skeptic-coverage teeth are live in _per_name_cap (MISSING / stale-REFUTED -> 0.5; a "material"
    correction -> 0.75, a bounded haircut, never a hard ceiling).
  - CHAIN CAPS: <=3 names AND <=30% weight per chain (a 2-chain name — PWR carries power_for_ai +
    electrification_grid — counts toward BOTH), solved as a JOINT closed-form system rather than
    _fr_post's one-chain-at-a-time renorm bound. See enforce_chain_caps: with k chains breaching
    simultaneously the per-chain bound is MAX_W*outside/(1-k*MAX_W), which lands EVERY breaching
    chain on exactly MAX_W of the rebuilt total in ONE pass; the sequential formula solves for k=1
    and undershoots whenever two chains breach together. Infeasible geometry (k*MAX_W >= 1, or no
    units outside the breaching chains) WARNs and caps NOTHING. The convergence loop and the residual
    audit on the FINAL weights are kept — overlapping breaching chains are not a disjoint system.
  - NO DURATION LAYER, deliberately (canon §C.7: "_fdt_post.py has no duration layer"). The Dalio
    debt-cycle advisory rides the Mining book (and the regime book); this one never imports
    _regime_post, never touches a cycle ledger, and stamps no duration_bucket. Do not "restore" it
    for symmetry — the split of the macro layer across the two books is the decision, not an omission.
  - torque x leverage quadrant KEPT but rarely live: most FDT chains carry torque_metrics=false
    (equipment/tech cohorts have no spot price to be levered to, so fcf_torque_10pct is never
    fabricated for them). The isinstance guards already make the check a no-op when the fields are
    absent — the code requires NO torque field to exist.
  - CROSS-BOOK SEAT BACKSTOP (canon §T.4): before stamping, the pick set is asserted DISJOINT from
    the Mining book's latest published payload (frontend/public/speculair_mining.json). Non-empty
    intersection = loud STOP + exit 1 (a name is NEVER seated in both books, whatever upstream
    missed). Missing/unreadable payload = WARN and continue (fail-open).
  - APEX MTIME PRESERVED after the dump (os.utime) — see the comment in main(). Without it a post
    re-run marks every skeptic shard stale and silently half-sizes the whole book.
  - Kept from _fr_post unchanged: growth_capex_fcf_negative <= 0.75, un-justified HEADWIND-chain seat
    clamped to 0.5, stale anchor 0.5, hype flag 0.5 (the disruptor gate that survived the FR trim),
    weights / stress / correlation / exits / entry plans / wheel via _post_common, gate_sync DROPPED
    (cross-book EXCLUDE overlap warns only).

Pipeline order:
    fdt_input -> [FDT Director writes apex_basket_fdt.json] -> fdt_post (THIS) -> fdt_csv -> fdt_publish

Usage:
    python _fdt_post.py            # live: fetch quotes + 2y charts, stamp, cache
    python _fdt_post.py --offline  # reuse cache (idempotency test)
"""
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../backend/_opus_debate
BK = os.path.dirname(_HERE)                             # .../backend
ROOT_DIR = os.path.dirname(BK)                          # .../Stock-Screener
sys.path.insert(0, BK)
os.chdir(BK)
if hasattr(sys.stdout, "reconfigure"):                 # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# FMP key: real key from frontend/.env.local BEFORE importing screener_v6 (it freezes FMP_KEY at
# import); demo-key fallback = the _value_post/_regime_post reference pattern.
if not os.environ.get("FMP_API_KEY"):
    _env = Path(ROOT_DIR) / "frontend" / ".env.local"
    if _env.exists():
        for _line in _env.read_text(encoding="utf-8").splitlines():
            if _line.strip().startswith("FMP_API_KEY=") and "=" in _line:
                os.environ["FMP_API_KEY"] = _line.split("=", 1)[1].strip().replace('"', "").replace("'", "")
                break
if not os.environ.get("FMP_API_KEY"):
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
from screener_v6 import fmp, get_chart                  # noqa: E402  FMP REST + OHLCV
sys.path.insert(0, _HERE)                              # sibling modules (_wheel, _post_common)
from _wheel import stamp_wheel                          # noqa: E402  CSP->CC wheel suggestion
import _post_common as _pc                              # noqa: E402  shared skeptic + weight builder + market blocks

ROOT = Path("_opus_debate")
FDTD = ROOT / "fdt"
APEX_F = FDTD / "apex_basket_fdt.json"
GIN_F = FDTD / "fdt_grade_input.json"
RES_DIR = FDTD / "results"
# dossiers/ holds the debate-side .md forensics; the post layer never reads them (results/<SYM>.json
# is the only per-name record it needs) — declared so the subtree registry lives in ONE place.
DOSS_DIR = FDTD / "dossiers"
CACHE_F = FDTD / "_fdt_post_cache.json"
SKEP_DIR = ROOT / "_skeptic_fdt"                        # shard dirs sit at _opus_debate/ level (_skeptic_regime precedent)
# cross-book overlap warning targets (gate_sync DROPPED — different universes, no demotion v1)
REGIME_F = ROOT / "apex_basket_opus_regime.json"
VALUE_F = ROOT / "apex_basket_value.json"
# canon §T.4 publish-time backstop: the OTHER book's latest published payload (a name must never sit
# in both). Absolute path — this module chdir()s to backend/.
OTHER_PAYLOAD_F = Path(ROOT_DIR) / "frontend" / "public" / "speculair_mining.json"

# chain caps (FDT Director hard constraints + the deterministic backstop here)
MAX_NAMES_PER_CHAIN = 3
MAX_WEIGHT_PER_CHAIN = 0.30
BETA_BENCH = ["GRID", "QQQ"]                            # canon §B: FDT benchmark = 50/50 GRID+QQQ
# torque x leverage blow-up quadrant. KEPT for the handful of FDT rows that DO carry torque metrics;
# torque_metrics=false chains simply never supply the fields and the isinstance guards no-op.
QUADRANT_TORQUE_MIN = 0.5
QUADRANT_NDEBT_MIN = 2.5


def load():
    apx = json.load(open(APEX_F, encoding="utf-8"))
    gin = {x["symbol"]: x for x in json.load(open(GIN_F, encoding="utf-8"))}
    return apx, gin


def live_quotes(symbols):
    return _pc.live_quotes(fmp, symbols)


def get_market(quote_syms, corr_syms, offline):
    return _pc.get_market(quote_syms, corr_syms, offline, CACHE_F,
                          quotes_fn=live_quotes, chart_fn=lambda s: get_chart(s, days=760))


# ───────────────────────── skeptic kill-tier consumption (fork b: REFUTED demotes) ─────────────────────────
def consume_skeptic(apx):
    """Delegates to the SHARED _post_common.consume_skeptic — the ONE sanctioned membership change in
    any post layer: a FRESH REFUTED apex member is DEMOTED to the front of runner_ups ("a skeptic that
    cannot demote is decoration"). It also stamps the COVERAGE flags: an apex member with no fresh
    shard gets skeptic_verdict=MISSING (+ skeptic_missing -> half-sized in _per_name_cap), and a STALE
    REFUTED shard on a still-held member is stamped skeptic_stale_refuted instead of silently ignored.
    Freshness is anchored on the Director's write (post_anchor_ts), which is exactly why main() must
    preserve the apex mtime after re-stamping this file."""
    return _pc.consume_skeptic(apx, APEX_F, SKEP_DIR)


# ───────────────────────── gate caps (FR deltas, kept verbatim + the hype flag) ─────────────────────────
def stamp_gate_caps(picks, gin):
    """Stamp the deterministic cap flags. growth_capex_fcf_negative and the torque x leverage quadrant
    clamp to 0.75; a HEADWIND-chain seat sized > 0.5 with NO written headwind_justification clamps to
    0.5 (the Director rule is 0.5 OR justification — an un-justified breach is deterministic); a
    hype_flag name clamps to 0.5 (a price embedding a more aggressive S-curve than the evidence — the
    live gate for a book carrying quantum and pre-revenue SMR cohorts). Director fields win where
    present; grade-input fields are the fallback. The quadrant legs are OPTIONAL: torque_metrics=false
    chains never emit fcf_torque_10pct, the isinstance guards no-op, and nothing here requires it."""
    for p in picks:
        g = gin.get(p["symbol"], {})
        gcf = bool(p.get("growth_capex_fcf_negative", g.get("growth_capex_fcf_negative")))
        tq = p.get("fcf_torque_10pct", g.get("fcf_torque_10pct"))
        nd = p.get("ndebt_ebitda", g.get("ndebt_ebitda"))
        quad = bool(isinstance(tq, (int, float)) and tq >= QUADRANT_TORQUE_MIN
                    and isinstance(nd, (int, float)) and nd >= QUADRANT_NDEBT_MIN)
        p["growth_capex_fcf_negative"] = gcf
        p["torque_leverage_quadrant"] = bool(p.get("torque_leverage_quadrant") or quad)
        p["hype_flag"] = bool(p.get("hype_flag", g.get("hype_flag")))
        # HEADWIND rule: worst chain verdict HEADWIND + size > 0.5 + no written justification => clamp
        cr = p.get("chain_regime") or g.get("chain_regime") or {}
        states = list(cr.values()) if isinstance(cr, dict) else [str(cr)]
        headwind = any(str(s).upper() == "HEADWIND" for s in states)
        just = str(p.get("headwind_justification") or "").strip()
        u = p.get("size_units")
        p["headwind_chain"] = headwind
        p["headwind_unjustified"] = bool(headwind and isinstance(u, (int, float)) and u > 0.5 and not just)
        if p["headwind_unjustified"]:
            print(f"WARN headwind: {p['symbol']} sits in a HEADWIND chain at size_units={u} with NO "
                  f"written justification -> clamped to 0.5")
        if p["torque_leverage_quadrant"]:
            print(f"NOTE quadrant: {p['symbol']} torque={tq} x ndebt/EBITDA={nd} (blow-up quadrant) -> <=0.75")
        if p["hype_flag"]:
            print(f"NOTE hype: {p['symbol']} carries hype_flag -> <=0.5")


def stamp_stale_anchor(picks, gin):
    """Copied semantics from _fr_post: stale + FIRED catalyst = the anchor may predate the event —
    half-size. The stale leg is balance_sheet_stale (pre-FCF developers raise equity between filings)
    + FIRED."""
    for p in picks:
        g = gin.get(p["symbol"], {})
        fired = False
        rf = RES_DIR / f"{p['symbol']}.json"
        if rf.exists():
            try:
                cs = (json.load(open(rf, encoding="utf-8")).get("catalyst_status") or "").upper()
                fired = cs.startswith("FIRED")
            except Exception:
                fired = False
        p["stale_anchor"] = bool(g.get("balance_sheet_stale") and fired)


def _per_name_cap(p, u):
    """The FDT teeth. Skeptic coverage FIRST (an un-vetted or killed-but-stale seat is half-sized
    whatever else it carries — _post_common.moat_per_name_cap's ordering), then the bounded material-
    correction haircut, then the FR hard constraints: un-justified HEADWIND / stale anchor / hype 0.5,
    growth-capex + torque-quadrant 0.75."""
    if p.get("skeptic_missing") or p.get("skeptic_stale_refuted"):
        return min(u, 0.5)
    if p.get("correction_severity") == "material":     # a load-bearing number/date moved: haircut, not a ceiling
        u = min(u, 0.75)
    if p.get("headwind_unjustified") or p.get("stale_anchor") or p.get("hype_flag"):
        return min(u, 0.5)
    if p.get("growth_capex_fcf_negative") or p.get("torque_leverage_quadrant"):
        return min(u, 0.75)
    return u


def build_weights(apx, picks, extra_caps=None):
    return _pc.build_weights(apx, picks, extra_caps=extra_caps, per_name_cap=_per_name_cap)


# ───────────────────────── chain caps (JOINT closed-form solve, <=3 names + <=30%) ─────────────────────────
def enforce_chain_caps(apx, picks):
    """From each pick's chains[], deterministically verify <=3 names AND <=30% weight per chain (a
    2-chain name counts toward BOTH). On a weight breach append {names, max_units, axis:"chain:<id>"}
    to extra_caps and let build_weights rebuild. Returns the extra chain caps (may be empty).

    JOINT CLOSED-FORM SOLVE. _fr_post capped one chain at a time with max_units = W/(1-W) x other,
    which is the exact renorm-aware bound for k=1 breaching chain and UNDERSHOOTS for k>1 (capping
    chain X shrinks the total, so chain Y — measured against the old total — is re-solved too loose
    and needs another pass). Solving all k breaching chains at once: give each the same bound
        cap = W x outside / (1 - k x W)        [outside = units in NO breaching chain]
    and the rebuilt total is k x cap + outside = outside/(1 - k x W), so every breaching chain lands
    on exactly W of it. INFEASIBLE GEOMETRY — k x W >= 1 (four chains cannot each hold 30%) or
    outside <= 0 (every seat sits in a breaching chain) — WARNs and caps NOTHING: an unsolvable slate
    shape is a Director/membership problem (P1 forbids fixing it here), and a fabricated cap would
    silently mangle the book. Overlapping breaching chains (PWR-class 2-chain names are counted in
    both chains but only once in the total) are not a disjoint system either, so the caller iterates
    to convergence and audit_chain_residual has the last word on the FINAL weights.

    A NAME-COUNT breach (>3) cannot be fixed deterministically without changing membership (P1) — it
    is WARNED here and fdt_publish hard-stops on it."""
    units = {p["symbol"]: p.get("size_units_effective", p.get("size_units") or 1.0) for p in picks}
    total_units = sum(units.values()) or 1.0
    members_by_chain = {}
    for p in picks:
        for c in (p.get("chains") or []):
            members_by_chain.setdefault(c, []).append(p["symbol"])
    breaching = []
    for c, names in sorted(members_by_chain.items()):
        names = [s for s in names if s in units]
        if not names:
            continue
        chain_units = sum(units[s] for s in names)
        chain_w = chain_units / total_units
        if len(names) > MAX_NAMES_PER_CHAIN:
            print(f"WARN chain cap: chain:{c} carries {len(names)} names (>{MAX_NAMES_PER_CHAIN}) "
                  f"{names} — a COUNT breach is a Director slate error (membership never changes in "
                  f"post, P1); fdt_publish will STOP on it")
        # 0.05pp tolerance: unit-rounding (3dp) parks a capped cluster at 30.0x% — re-detecting that
        # as a fresh breach would loop the same cap forever (fdt_publish's own guard allows 0.5pp).
        if chain_w > MAX_WEIGHT_PER_CHAIN + 5e-4:
            breaching.append((c, names, chain_units, chain_w))
    if not breaching:
        return []
    k = len(breaching)
    inside = {s for _c, names, _u, _w in breaching for s in names}
    outside = round(total_units - sum(units[s] for s in inside), 6)
    denom = 1.0 - k * MAX_WEIGHT_PER_CHAIN
    if denom <= 1e-9 or outside <= 0:
        print(f"WARN chain cap: INFEASIBLE geometry — {k} chain(s) over "
              f"{int(MAX_WEIGHT_PER_CHAIN*100)}% ({[c for c, *_ in breaching]}) with "
              f"{round(outside, 3)} units outside them (k x cap = {round(k*MAX_WEIGHT_PER_CHAIN, 2)}). "
              f"NO cap applied — the slate cannot satisfy the bound without a membership change (P1); "
              f"fix the Director slate. fdt_publish will STOP on the residual breach.")
        return []
    cap_units = round(MAX_WEIGHT_PER_CHAIN * outside / denom, 3)
    extra = []
    for c, names, chain_units, chain_w in breaching:
        print(f"WARN chain cap: chain:{c} carries {names} — {round(chain_w*100,1)}% weight "
              f"(>{int(MAX_WEIGHT_PER_CHAIN*100)}%) -> combined units capped at {cap_units} "
              f"(joint solve over {k} breaching chain(s), outside={round(outside, 3)}u)")
        extra.append({"names": names, "max_units": cap_units, "axis": f"chain:{c}"})
    return extra


def audit_chain_residual(picks, weights):
    """Residual audit on the FINAL weights — the same measurement fdt_publish's hard stop makes
    (per-chain published weight, 2-chain names counted in both, 0.5pp tolerance). Anything still over
    the bound after the joint solve + convergence loop is either an overlapping-chain geometry the
    unit caps cannot express or (with _post_common.EQUAL_WEIGHT_BOOKS True) an equal-weight book where
    3 of N seats simply ARE >30% of published weight — no unit cap can cure that. WARN-only: this
    layer never changes membership, and the publisher owns the stop. Returns chain_exposure."""
    exposure = {}
    for p in picks:
        for c in (p.get("chains") or []):
            exposure[c] = round(exposure.get(c, 0.0) + weights.get(p["symbol"], 0) * 100, 2)
    n = len([p for p in picks if p.get("symbol")]) or 1
    for c, w in sorted(exposure.items()):
        if w <= MAX_WEIGHT_PER_CHAIN * 100 + 0.5:
            continue
        seats = len([p for p in picks if c in (p.get("chains") or [])])
        # EQUAL-WEIGHT REGIME — see the twin comment in _mining_post.audit_chain_residual. With
        # _pc.EQUAL_WEIGHT_BOOKS True the published vector is 1/n, so a chain's share is purely its
        # seat count (3 of 8 IS 37.5%) and no unit cap can move it. That is arithmetic, not drift,
        # and must not become a publish stop — it would block the <=3-names allowance the Director
        # prompt grants. The NAME cap is the enforceable constraint in this regime.
        if _pc.EQUAL_WEIGHT_BOOKS and seats <= MAX_NAMES_PER_CHAIN:
            print(f"NOTE chain residual (ADVISORY): chain:{c} carries {w}% of published weight "
                  f"({seats} of {n} equal seats). Over the {int(MAX_WEIGHT_PER_CHAIN*100)}% bound by "
                  f"ARITHMETIC, not by concentration drift — under equal weighting {seats} seats are "
                  f"always {round(seats / n * 100, 1)}%. Within the <={MAX_NAMES_PER_CHAIN}-names "
                  f"rule, so NOT a publish stop; the weight bound binds again if EQUAL_WEIGHT_BOOKS "
                  f"is flipped off (a sizing change, not a display change).")
        else:
            print(f"WARN chain residual: chain:{c} still carries {w}% of FINAL published weight "
                  f"(>{int(MAX_WEIGHT_PER_CHAIN*100)}%) across {seats} seats after the cap solve — "
                  f"this exceeds the <={MAX_NAMES_PER_CHAIN}-name allowance and IS a Director slate "
                  f"error. Fix the slate (fewer seats in that chain) and re-run fdt-post.")
    return exposure


# ───────────────────────── entry timing / plans (copied from _fr_post) ─────────────────────────
def derive_entry_posture(p, rec=None):
    cat = str((p.get("catalyst_status") or (rec or {}).get("catalyst_status") or "")).upper()
    if cat.startswith("PENDING_HARD") or cat.startswith("ARB"):
        return "on_confirmation"
    blob = (str(p.get("entry_plan") or "") + " "
            + " ".join(str(a) for a in (p.get("exposure_axes") or [])) + " "
            + str(p.get("lane") or "")).lower()
    if any(k in blob for k in ("knife", "demand-cycle", "cyclical", "de-gross", "degross")):
        return "wait_for_weakness"
    return "scale_in"


def stamp_entry_posture(picks):
    for p in picks:
        if not p.get("entry_posture"):
            p["entry_posture"] = derive_entry_posture(p)


def stamp_entry_plans(picks, quotes):
    for p in picks:
        q = quotes.get(p["symbol"]) or {}
        px, lo = q.get("price"), q.get("yearLow")
        near = isinstance(px, (int, float)) and isinstance(lo, (int, float)) and lo > 0 and (px / lo - 1) < 0.05
        p["entry_plan"] = "3 tranches / 4 wks (knife: <5% above 52w low)" if near else "2 tranches / 2 wks"


def exits_block(picks, quotes):
    return _pc.exits_block(picks, quotes, thesis_break=lambda p: p.get("thesis_break_px"))


def stress_block(picks, weights, quotes, asof):
    """Shared market-based stress; the bear leg is the CRO's adverse SoP (bear_fv_px, chain-turn case)."""
    return _pc.stress_block(picks, weights, quotes, asof,
                            bear_px=lambda p: p.get("bear_fv_px"), bear_label="bear_fv_px")


# ───────────────────────── measured correlation (dual benchmark GRID + QQQ) ─────────────────────────
def corr_block(syms, weekly_rets, weights, thresh=0.6, hard=0.7):
    """Pairwise 2y weekly Pearson (shared _pearson/_beta) with the DUAL chain-beta read — the _fr_post
    XME/URA shape re-pointed to the canon §B FDT benchmark: GRID (grid & electrification equipment) +
    QQQ (long-duration tech), the same 50/50 pair the publisher and the card label stamp."""
    pairs, flagged = [], []
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            c = _pc._pearson(weekly_rets.get(a) or {}, weekly_rets.get(b) or {})
            if c is None:
                continue
            pairs.append({"a": a, "b": b, "corr": round(c, 2)})
            if c >= thresh:
                cw = weights.get(a, 0) + weights.get(b, 0)
                flagged.append({"a": a, "b": b, "corr": round(c, 2),
                                "combined_weight_pct": round(cw * 100, 1),
                                "breach": bool(c >= hard and cw > 0.16)})
    grid = weekly_rets.get("GRID")
    qqq = weekly_rets.get("QQQ")
    chain_beta = {}
    for s in syms:
        bg = _pc._beta(weekly_rets.get(s), grid)
        bq = _pc._beta(weekly_rets.get(s), qqq)
        if bg is not None or bq is not None:
            chain_beta[s] = {"grid": round(bg, 2) if bg is not None else None,
                             "qqq": round(bq, 2) if bq is not None else None}
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    return {"window": "2y weekly log returns", "avg_pairwise": avg, "n_pairs": len(pairs),
            "max_pair": max(pairs, key=lambda p: p["corr"]) if pairs else None,
            "flagged_pairs": flagged, "chain_beta": chain_beta,
            "correlation_breach": any(f.get("breach") for f in flagged),
            "fx_note": "betas vs GRID (grid & electrification equipment) + QQQ (long-duration tech) — "
                       "the 50/50 FDT benchmark and this book's systematic axes."}


# ───────────────────────── cross-book checks (overlap WARN + canon §T.4 seat STOP) ─────────────────────────
def cross_book_overlap_warn(picks, gin):
    """The FDT universe barely overlaps the regime/value books — no cross-book demotion v1. If an FDT
    forensic-EXCLUDE symbol ALSO sits in the regime or value apex, print a loud operator warning
    (gate_sync stays DROPPED: those books' membership is not this layer's to change)."""
    excluded = {x["symbol"] for x in gin.values() if (x or {}).get("forensic_gate") == "EXCLUDE"}
    if not excluded:
        return
    for other_f, label in ((REGIME_F, "REGIME"), (VALUE_F, "VALUE")):
        if not other_f.exists():
            continue
        try:
            oapx = json.load(open(other_f, encoding="utf-8"))
        except Exception:
            continue
        osyms = {p.get("symbol") for p in oapx.get("apex_basket", []) if isinstance(p, dict)}
        overlap = sorted(excluded & osyms)
        if overlap:
            print(f"!!! CROSS-BOOK WARNING: FDT forensic-EXCLUDE name(s) {overlap} ALSO sit in the "
                  f"{label} apex (different universes — no auto-demotion v1; operator should review).")


def cross_book_seat_stop(picks):
    """Canon §T.4 publish-time backstop. A name is NEVER seated in FDT AND Mining simultaneously —
    whatever the universe dedup missed upstream (the tie rule sends straddlers to Mining, so an
    intersection here is exactly the failure this backstop exists for). Assert the about-to-stamp pick
    set is DISJOINT from the Mining book's latest published payload; a non-empty intersection is a
    loud STOP + exit 1 (Do-NOT #10 discipline: report and stop, never publish a degraded/contradictory
    book). A missing or unreadable Mining payload WARNs and continues — fail-open, because the maiden
    FDT publish can legitimately precede the first Mining payload."""
    syms = {p["symbol"] for p in picks}
    if not OTHER_PAYLOAD_F.exists():
        print(f"WARN cross-book backstop: {OTHER_PAYLOAD_F} not found — cannot verify FDT/Mining seat "
              f"disjointness this run (fail-open; expected before the maiden Mining publish).")
        return
    try:
        other = json.load(open(OTHER_PAYLOAD_F, encoding="utf-8"))
    except Exception as e:
        print(f"WARN cross-book backstop: {OTHER_PAYLOAD_F} unreadable ({e}) — seat disjointness NOT "
              f"verified this run (fail-open).")
        return
    osyms = set()
    # apex_basket is the live key; final_holdings is the frozen-record rename (_retire_fr precedent).
    for key in ("apex_basket", "final_holdings"):
        for r in (other.get(key) or []):
            if isinstance(r, dict) and r.get("symbol"):
                osyms.add(r["symbol"])
            elif isinstance(r, str):
                osyms.add(r)
    both = sorted(syms & osyms)
    if both:
        print(f"!!! STOP cross-book seat collision: {both} are seated in BOTH the FDT slate and the "
              f"published Mining book ({OTHER_PAYLOAD_F.name}). A name must never be seated in both "
              f"books (canon §T.4). Nothing stamped. Fix the Director slate / re-run the universe "
              f"dedup, then re-run fdt-post.")
        sys.exit(1)
    print(f"cross-book backstop: OK — 0 of {len(syms)} FDT seats appear in "
          f"{OTHER_PAYLOAD_F.name} ({len(osyms)} published Mining names)")


def main():
    offline = "--offline" in sys.argv
    apx, gin = load()
    apx = consume_skeptic(apx)                             # fork (b): REFUTED demotes BEFORE weights
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    syms = [p["symbol"] for p in picks]
    quotes, weekly_rets, asof = get_market(syms, syms + BETA_BENCH, offline)
    stamp_gate_caps(picks, gin)
    stamp_stale_anchor(picks, gin)
    w_prov = build_weights(apx, picks)                     # provisional (no corr/chain caps)
    corr = corr_block(syms, weekly_rets, w_prov)           # provisional, for breach detection
    breach_caps = _pc.corr_breach_caps(corr, max_units=1.5)
    build_weights(apx, picks, extra_caps=breach_caps)      # rebuild so the chain solve reads post-corr units
    # NO duration layer here by decision (canon §C.7) — the Dalio advisory rides Mining + regime only.
    # ITERATE the chain backstop to convergence: the joint solve lands every DISJOINT breaching chain
    # on the bound in one pass, but a shared 2-chain name (PWR-class) makes the system non-disjoint,
    # and capping there can push another chain back over — each pass re-measures on the rebuilt
    # effective units and REPLACES that chain's cap. Converges fast (total units decrease
    # monotonically); 6 passes is far beyond any real 8-pick slate.
    chain_caps = []
    for _pass in range(6):
        new_caps = enforce_chain_caps(apx, picks)
        if not new_caps:
            break
        for nc in new_caps:                                # replace this chain's earlier (looser) cap
            chain_caps = [c for c in chain_caps if c["axis"] != nc["axis"]] + [nc]
        build_weights(apx, picks, extra_caps=breach_caps + chain_caps)
    weights = build_weights(apx, picks, extra_caps=breach_caps + chain_caps)   # final (honors all caps)
    corr = corr_block(syms, weekly_rets, weights)          # recompute combined-weight w/ final weights
    _flagged = {s for f in corr.get("flagged_pairs", []) for s in (f["a"], f["b"])}
    for p in picks:
        p["corr_flag"] = p["symbol"] in _flagged
    stamp_entry_plans(picks, quotes)
    stamp_entry_posture(picks)
    stamp_wheel(picks, "fdt", quotes)                      # CSP->CC wheel (live yield / qualitative)
    chain_exposure = audit_chain_residual(picks, weights)  # final-weight audit + chain_exposure
    apx["weights"] = weights
    apx["stress_test"] = stress_block(picks, weights, quotes, asof)
    apx["correlation"] = corr
    apx["exits"] = exits_block(picks, quotes)
    apx["chain_exposure"] = chain_exposure
    # chain_caps are a DERIVED backstop recomputed every run — surfaced under their own key, NEVER
    # folded into the Director's combined_caps (that would compound on a re-run and break --offline
    # idempotency; extra caps live in-memory only, the _fr_post/_disruptor_post precedent).
    apx["chain_caps"] = chain_caps
    apx["fdt_post_applied"] = True   # fdt_publish gates on this (fr_post_applied mirror)
    # canon §T.4: verify the seat sets are disjoint BEFORE anything is stamped — a collision must not
    # leave a stamped apex behind for a --force publish to pick up.
    cross_book_seat_stop(picks)
    # APEX MTIME PRESERVATION (critical — do not drop). _post_common.consume_skeptic measures shard
    # freshness against the DIRECTOR's write; this layer rewrites the very file it anchors on, so a
    # fresh mtime makes every same-run skeptic shard look older than the apex. The next post run then
    # stamps the whole book skeptic_verdict=MISSING and _per_name_cap silently HALF-SIZES every seat.
    # post_anchor_ts covers the already-stamped case; restoring the mtime keeps the invariant true
    # even on a re-anchored (fresh Director) file.
    _st = APEX_F.stat() if APEX_F.exists() else None
    json.dump(apx, open(APEX_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if _st is not None:
        os.utime(APEX_F, (_st.st_atime, _st.st_mtime))
    cross_book_overlap_warn(picks, gin)
    st = apx["stress_test"]
    max_chain = max(chain_exposure.items(), key=lambda kv: kv[1]) if chain_exposure else (None, 0)
    print(f"fdt_post: stamped {APEX_F} | weights sum={round(sum(weights.values()), 4)} "
          f"| stress 52w-low={st['basket_to_52w_lows_pct']}% recession={st['recession_stress_pct']}% "
          f"| corr avg={corr.get('avg_pairwise')} pairs={corr.get('n_pairs')} "
          f"breaches={sum(1 for f in corr.get('flagged_pairs', []) if f.get('breach'))} "
          f"| top chain {max_chain[0]}={max_chain[1]}% (cap {int(MAX_WEIGHT_PER_CHAIN*100)}%) "
          f"| gcf_capped={[p['symbol'] for p in picks if p.get('growth_capex_fcf_negative')]} "
          f"quadrant={[p['symbol'] for p in picks if p.get('torque_leverage_quadrant')]} "
          f"headwind_clamped={[p['symbol'] for p in picks if p.get('headwind_unjustified')]} "
          f"hype={[p['symbol'] for p in picks if p.get('hype_flag')]} "
          f"stale={[p['symbol'] for p in picks if p.get('stale_anchor')]} "
          f"skeptic_missing={[p['symbol'] for p in picks if p.get('skeptic_missing')]}")


if __name__ == "__main__":
    main()
