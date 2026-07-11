#!/usr/bin/env python3
"""Deterministic post-processing for the FUTURE RESOURCES Lane A apex (spec §5 — parameterized clone
of _disruptor_post.py, delegating to _post_common where the signature fits, per the _value_post
pattern; _post_common.py and _disruptor_post.py themselves are NOT edited — Do-NOT #5).

Validates / stamps backend/_opus_debate/future_resources/apex_basket_fr.json AFTER the Director and
BEFORE fr_csv / fr_publish. NEVER changes apex membership (design principle P1). Idempotent:
re-running with --offline reuses the cached market data, so output is byte-identical.

What changed vs _disruptor_post.py (spec §5 deltas):
  - File constants parameterized to the future_resources/ subtree.
  - Beta benchmarks ["XME", "URA"] replace ["SMH", "QQQ"] (metals/mining + uranium are this book's
    systematic axes); emits chain_beta = {sym: {xme, ura}}.
  - enforce_theme_caps -> enforce_chain_caps: same mechanics over each pick's chains[] (a 2-chain
    name counts toward both), axis "chain:<id>", <=3 names AND <=30%-of-units per chain.
  - stamp_gate_caps: growth_capex_fcf_negative => size_units <= 0.75 (spec §1.2 hard clamp);
    torque x leverage quadrant (fcf_torque_10pct >= 0.5 AND ndebt_ebitda >= 2.5) => <= 0.75;
    HEADWIND-chain seat sized > 0.5 WITHOUT a written headwind_justification => clamped to 0.5
    (the Director rule is "0.5 OR justification" — an un-justified breach is deterministic).
  - NO SKEPTIC TIER for Lane A (spec §5 — the chain has none): consume_skeptic is NOT called and the
    skeptic-coverage half-caps are deliberately absent from the per-name cap.
  - weights / stress block / correlation / exits / entry plans / wheel: shared _post_common
    machinery (stress bear leg = bear_fv_px; exits = thesis_break_px) — copied semantics.
  - gate_sync DROPPED (disruptor precedent): cross-book EXCLUDE overlap prints a loud warning only.

Pipeline order:
    fr_input -> [FR Director writes apex_basket_fr.json] -> fr_post (THIS) -> fr_csv -> fr_publish

Usage:
    python _fr_post.py            # live: fetch quotes + 2y charts, stamp, cache
    python _fr_post.py --offline  # reuse cache (idempotency test)
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
import _post_common as _pc                              # noqa: E402  shared weight builder + market blocks

ROOT = Path("_opus_debate")
FRD = ROOT / "future_resources"
APEX_F = FRD / "apex_basket_fr.json"
GIN_F = FRD / "fr_grade_input.json"
RES_DIR = FRD / "results"
CACHE_F = FRD / "_fr_post_cache.json"
# cross-book overlap warning targets (gate_sync DROPPED — different universes, no demotion v1)
REGIME_F = ROOT / "apex_basket_opus_regime.json"
VALUE_F = ROOT / "apex_basket_value.json"

# chain caps (FR Director hard constraints + the deterministic backstop here)
MAX_NAMES_PER_CHAIN = 3
MAX_WEIGHT_PER_CHAIN = 0.30
BETA_BENCH = ["XME", "URA"]
# torque x leverage blow-up quadrant (spec §3: high-torque + high-leverage names get a mandatory
# size cap). Calibratable — tune against real grade inputs before tightening.
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


# ───────────────────────── gate caps (FR deltas; NO skeptic tier for Lane A) ─────────────────────────
def stamp_gate_caps(picks, gin):
    """Stamp the deterministic cap flags. growth_capex_fcf_negative and the torque x leverage
    quadrant clamp to 0.75; a HEADWIND-chain seat sized > 0.5 with NO written headwind_justification
    clamps to 0.5 (the Director rule is 0.5 OR justification). Director fields win where present;
    grade-input fields are the fallback."""
    for p in picks:
        g = gin.get(p["symbol"], {})
        gcf = bool(p.get("growth_capex_fcf_negative", g.get("growth_capex_fcf_negative")))
        tq = p.get("fcf_torque_10pct", g.get("fcf_torque_10pct"))
        nd = p.get("ndebt_ebitda", g.get("ndebt_ebitda"))
        quad = bool(isinstance(tq, (int, float)) and tq >= QUADRANT_TORQUE_MIN
                    and isinstance(nd, (int, float)) and nd >= QUADRANT_NDEBT_MIN)
        p["growth_capex_fcf_negative"] = gcf
        p["torque_leverage_quadrant"] = bool(p.get("torque_leverage_quadrant") or quad)
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


def stamp_stale_anchor(picks, gin):
    """Copied semantics from _value_post/_disruptor_post: stale + peak-ish + FIRED catalyst = the
    anchor may predate the event — half-size. FR grade input has no eps_peak_ratio; the stale leg is
    balance_sheet_stale (miners raise equity between filings) + FIRED."""
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
    """The FR teeth. NO skeptic-coverage caps (Lane A has no skeptic tier — spec §5); the caps are
    the FR hard constraints: growth-capex 0.75, quadrant 0.75, un-justified HEADWIND 0.5, stale 0.5."""
    if p.get("headwind_unjustified") or p.get("stale_anchor"):
        return min(u, 0.5)
    if p.get("growth_capex_fcf_negative") or p.get("torque_leverage_quadrant"):
        return min(u, 0.75)
    return u


def build_weights(apx, picks, extra_caps=None):
    return _pc.build_weights(apx, picks, extra_caps=extra_caps, per_name_cap=_per_name_cap)


# ───────────────────────── chain caps (enforce_theme_caps mechanics, chains[] + 30%) ─────────────────────────
def enforce_chain_caps(apx, picks):
    """From each pick's chains[], deterministically verify <=3 names AND <=30% weight per chain
    (a 2-chain name counts toward BOTH). On a weight breach append {names, max_units, axis:"chain:<id>"}
    to extra_caps and let build_weights rebuild. DEVIATION from the disruptor formula (sanctioned by
    the P3 acceptance "chain caps hold after post"): the disruptor capped a cluster to 30% of the
    PRE-scaled total units, which leaves the cluster ABOVE 30% of WEIGHT once the total renormalizes
    (4x1.0 of 8 units -> capped 2.4 -> 2.4/6.4 = 37.5%). The FR cap is renormalization-aware:
    max_units = W/(1-W) x other_units, so the cluster lands at exactly the 30% weight bound. A
    NAME-COUNT breach (>3) cannot be fixed deterministically without changing membership (P1) — it
    is WARNED here and fr_publish hard-stops on it. Returns the extra chain caps (may be empty)."""
    units = {p["symbol"]: p.get("size_units_effective", p.get("size_units") or 1.0) for p in picks}
    total_units = sum(units.values()) or 1.0
    members_by_chain = {}
    for p in picks:
        for c in (p.get("chains") or []):
            members_by_chain.setdefault(c, []).append(p["symbol"])
    extra = []
    for c, names in sorted(members_by_chain.items()):
        names = [s for s in names if s in units]
        if not names:
            continue
        chain_units = sum(units[s] for s in names)
        other_units = total_units - chain_units
        chain_w = chain_units / total_units
        # renorm-aware bound: after scaling the cluster to r x other (r = W/(1-W)), its share of the
        # NEW total is exactly W. Degenerate all-one-chain books (other=0) fall back to the raw cap.
        cap_units = round(MAX_WEIGHT_PER_CHAIN / (1 - MAX_WEIGHT_PER_CHAIN) * other_units, 3) \
            if other_units > 0 else round(MAX_WEIGHT_PER_CHAIN * total_units, 3)
        # 0.05pp tolerance: unit-rounding (3dp) parks a capped cluster at 30.0x% — re-detecting that
        # as a fresh breach would loop the same cap forever (fr_publish's own guard allows 0.5pp).
        breach_weight = chain_w > MAX_WEIGHT_PER_CHAIN + 5e-4
        breach_count = len(names) > MAX_NAMES_PER_CHAIN
        if breach_count:
            print(f"WARN chain cap: chain:{c} carries {len(names)} names (>{MAX_NAMES_PER_CHAIN}) "
                  f"{names} — a COUNT breach is a Director slate error (membership never changes in "
                  f"post, P1); fr_publish will STOP on it")
        if breach_weight:
            print(f"WARN chain cap: chain:{c} carries {names} — {round(chain_w*100,1)}% weight "
                  f"(>{int(MAX_WEIGHT_PER_CHAIN*100)}%) -> combined units capped at {cap_units} (renorm-aware)")
            extra.append({"names": names, "max_units": cap_units, "axis": f"chain:{c}"})
    return extra


# ───────────────────────── entry timing / plans (copied from _disruptor_post) ─────────────────────────
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


# ───────────────────────── measured correlation (dual benchmark XME + URA) ─────────────────────────
def corr_block(syms, weekly_rets, weights, thresh=0.6, hard=0.7):
    """Pairwise 2y weekly Pearson (shared _pearson/_beta) with the DUAL chain-beta read — the
    _disruptor_post SMH/QQQ shape parameterized to XME (metals & mining) + URA (uranium)."""
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
    xme = weekly_rets.get("XME")
    ura = weekly_rets.get("URA")
    chain_beta = {}
    for s in syms:
        bx = _pc._beta(weekly_rets.get(s), xme)
        bu = _pc._beta(weekly_rets.get(s), ura)
        if bx is not None or bu is not None:
            chain_beta[s] = {"xme": round(bx, 2) if bx is not None else None,
                             "ura": round(bu, 2) if bu is not None else None}
    avg = round(sum(p["corr"] for p in pairs) / len(pairs), 2) if pairs else None
    return {"window": "2y weekly log returns", "avg_pairwise": avg, "n_pairs": len(pairs),
            "max_pair": max(pairs, key=lambda p: p["corr"]) if pairs else None,
            "flagged_pairs": flagged, "chain_beta": chain_beta,
            "correlation_breach": any(f.get("breach") for f in flagged),
            "fx_note": "betas vs XME (metals & mining) + URA (uranium) — this book's systematic commodity axes."}


# ───────────────────────── cross-book overlap warning (gate_sync DROPPED) ─────────────────────────
def cross_book_overlap_warn(picks, gin):
    """The FR universe barely overlaps the regime/value books — no cross-book demotion v1. If an FR
    forensic-EXCLUDE symbol ALSO sits in the regime or value apex, print a loud operator warning."""
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
            print(f"!!! CROSS-BOOK WARNING: FR forensic-EXCLUDE name(s) {overlap} ALSO sit in the {label} "
                  f"apex (different universes — no auto-demotion v1; operator should review).")


def main():
    offline = "--offline" in sys.argv
    apx, gin = load()
    # NO skeptic consumption: Lane A's chain has no skeptic tier (spec §5) — deliberate, not a gap.
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    syms = [p["symbol"] for p in picks]
    quotes, weekly_rets, asof = get_market(syms, syms + BETA_BENCH, offline)
    stamp_gate_caps(picks, gin)
    stamp_stale_anchor(picks, gin)
    w_prov = build_weights(apx, picks)                     # provisional (no corr/chain caps)
    corr = corr_block(syms, weekly_rets, w_prov)           # provisional, for breach detection
    breach_caps = _pc.corr_breach_caps(corr, max_units=1.5)
    # rebuild with corr caps, then ITERATE the chain backstop to convergence: capping chain X shrinks
    # the total, which can push chain Y (or X, via a 2-chain overlap) back over the 30% weight bound —
    # each pass re-measures on the rebuilt effective units and replaces that chain's cap. Converges
    # fast (total units decrease monotonically); 6 passes is far beyond any real 8-pick slate.
    build_weights(apx, picks, extra_caps=breach_caps)
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
    stamp_wheel(picks, "fr", quotes)                       # CSP->CC wheel (live yield / qualitative)
    # chain_exposure (final weights by chain; a 2-chain name counts toward both)
    chain_exposure = {}
    for p in picks:
        for c in (p.get("chains") or []):
            chain_exposure[c] = round(chain_exposure.get(c, 0.0) + weights.get(p["symbol"], 0) * 100, 2)
    apx["weights"] = weights
    apx["stress_test"] = stress_block(picks, weights, quotes, asof)
    apx["correlation"] = corr
    apx["exits"] = exits_block(picks, quotes)
    apx["chain_exposure"] = chain_exposure
    # chain_caps are a DERIVED backstop recomputed every run — surfaced under their own key, NEVER
    # folded into the Director's combined_caps (that would compound on a re-run and break --offline
    # idempotency; extra caps live in-memory only, exactly the _disruptor_post precedent).
    apx["chain_caps"] = chain_caps
    apx["fr_post_applied"] = True   # fr_publish gates on this (value_post_applied mirror)
    json.dump(apx, open(APEX_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    cross_book_overlap_warn(picks, gin)
    st = apx["stress_test"]
    max_chain = max(chain_exposure.items(), key=lambda kv: kv[1]) if chain_exposure else (None, 0)
    print(f"fr_post: stamped {APEX_F} | weights sum={round(sum(weights.values()), 4)} "
          f"| stress 52w-low={st['basket_to_52w_lows_pct']}% recession={st['recession_stress_pct']}% "
          f"| corr avg={corr.get('avg_pairwise')} pairs={corr.get('n_pairs')} "
          f"breaches={sum(1 for f in corr.get('flagged_pairs', []) if f.get('breach'))} "
          f"| top chain {max_chain[0]}={max_chain[1]}% (cap {int(MAX_WEIGHT_PER_CHAIN*100)}%) "
          f"| gcf_capped={[p['symbol'] for p in picks if p.get('growth_capex_fcf_negative')]} "
          f"quadrant={[p['symbol'] for p in picks if p.get('torque_leverage_quadrant')]} "
          f"headwind_clamped={[p['symbol'] for p in picks if p.get('headwind_unjustified')]} "
          f"stale={[p['symbol'] for p in picks if p.get('stale_anchor')]}")


if __name__ == "__main__":
    main()
