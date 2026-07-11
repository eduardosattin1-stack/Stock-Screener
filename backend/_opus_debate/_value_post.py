#!/usr/bin/env python3
"""Deterministic post-processing for the VALUE apex (audit fixes 1-5,7, 2026-06-09).

Validates / stamps backend/_opus_debate/apex_basket_value.json AFTER the Director and
BEFORE value_csv / value_publish. NEVER changes value-apex membership (design principle P1;
the sole exception is gate_sync, which may demote a globally-EXCLUDEd name on the REGIME side).
Idempotent: re-running with --offline reuses the cached market data, so output is byte-identical.

Pipeline order:
    value_input -> [Director writes apex_basket_value.json] -> value_post (THIS) -> value_csv -> value_publish

Usage:
    python _value_post.py            # live: fetch quotes + 2y charts, stamp, cache
    python _value_post.py --offline  # reuse cache (idempotency test)
"""
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../backend/_opus_debate
BK = os.path.dirname(_HERE)                             # .../backend
sys.path.insert(0, BK)
os.chdir(BK)
if not os.environ.get("FMP_API_KEY"):                  # match fmp_facts.py / _funded_leverage fallback
    os.environ["FMP_API_KEY"] = "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
from screener_v6 import fmp, get_chart                  # noqa: E402  FMP REST + OHLCV
sys.path.insert(0, _HERE)                              # so the sibling _wheel module resolves
from _wheel import stamp_wheel                          # noqa: E402  CSP->CC wheel suggestion
import _post_common as _pc                              # noqa: E402  shared skeptic + weight builder (also used by _regime_post)

ROOT = Path("_opus_debate")
APEX_F = ROOT / "apex_basket_value.json"
GIN_F = ROOT / "value_grade_input.json"
RES_DIR = ROOT / "results_regime"
REGIME_F = ROOT / "apex_basket_opus_regime.json"
CACHE_F = ROOT / "_value_post_cache.json"

# (The 2026-06-09 one-off MEMO_UNITS migration map was deleted 2026-07-01 — the Director emits
# structured size_units since the 06-09 schema fix, so the map was dead weight that would have
# silently half-sized SAX.DE forever if it ever re-entered the book.)


def load():
    apx = json.load(open(APEX_F, encoding="utf-8"))
    gin = {x["symbol"]: x for x in json.load(open(GIN_F, encoding="utf-8"))}
    return apx, gin


# ───────────────────────── shared market blocks (moved to _post_common 2026-07-11) ─────────────────────────
# live_quotes / weekly_logrets / get_market / stress_block / corr_block / exits_block now live in
# _post_common as book-agnostic pure functions (value-book-parity guards for the regime book). The
# wrappers below bind THIS book's specifics — FMP fetcher, 760d chart window, _value_post_cache.json,
# bear_fv_px getter, XLY consumer beta, thesis_break_px getter — so behavior is byte-identical.

def live_quotes(symbols):
    """Batch quotes incl. yearHigh/yearLow (FMP stable batch-quote, comma symbols, chunked 50)."""
    return _pc.live_quotes(fmp, symbols)


def weekly_logrets(chart):
    """Resample an ascending OHLCV chart to the last close of each ISO week; return {YYYY-WW: logret}."""
    return _pc.weekly_logrets(chart)


def get_market(quote_syms, corr_syms, offline):
    """Fetch (or, --offline, reuse cached) live quotes + 2y weekly log-returns. Caches once for idempotency."""
    return _pc.get_market(quote_syms, corr_syms, offline, CACHE_F,
                          quotes_fn=live_quotes, chart_fn=lambda s: get_chart(s, days=760))


# ───────────────────────── 8b — skeptic kill-tier consumption (fork b: REFUTED demotes) ─────────────────────────
def consume_skeptic(apx):
    """Delegates to the SHARED _post_common.consume_skeptic (one implementation for both books —
    this used to be a pre-factoring duplicate with the same fail-OPEN hole that shipped the un-vetted
    06-30 books). The shared version adds the skeptic-COVERAGE stamps: apex members with no fresh
    shard get skeptic_verdict=MISSING (+ half-size via moat_per_name_cap), and a STALE REFUTED shard
    on a still-held member (the HRMY case) is stamped skeptic_stale_refuted instead of silently
    ignored. Fork (b) preserved: a fresh REFUTED member is DEMOTED to the front of runner_ups."""
    return _pc.consume_skeptic(apx, APEX_F, ROOT / "_skeptic")


# ───────────────────────── Fix 2 — CRO-only legs ─────────────────────────
def stamp_cro_only(picks, gin):
    for p in picks:
        g = gin.get(p["symbol"], {})
        ms = g.get("mos_spread") or {}
        n_pos = sum(1 for v in ms.values() if isinstance(v, (int, float)) and v > 0)
        scan = g.get("scan_headline_mos_pct")
        p["mos_agreement_n"] = n_pos
        p["cro_only"] = bool(n_pos <= 2 and (not isinstance(scan, (int, float)) or scan < 10))


# ───────────────────────── Fix 3 — stale-anchor (deterministic half) ─────────────────────────
def stamp_stale_anchor(picks, gin):
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
        p["stale_anchor"] = bool(g.get("freshness_stale") and (g.get("eps_peak_ratio") or 0) >= 1.8 and fired)


# ───────────────────────── Moat terminal-erosion (ADDITIVE to peak/stale — targets moat decline) ─────────────────────────
def stamp_moat_erosion(picks, gin):
    """Carry the screener's deterministic moat signals onto each pick so build_weights can half-cap an
    eroding moat (moat_erosion=='CAP') and the skeptic targeting can see the value-destroyers. This is
    a SECOND family of teeth, separate from the cyclical-peak/stale-anchor gates (which stay as-is —
    they fixed a prior issue). NEVER changes membership (P1)."""
    for p in picks:
        g = gin.get(p["symbol"], {})
        p["moat_erosion"] = g.get("moat_erosion", "")
        p["erosion_severity"] = g.get("erosion_severity", "none")
        if g.get("moat_score") is not None:
            p["moat_score"] = g.get("moat_score")
        if not p.get("moat"):
            p["moat"] = g.get("moat", "")
        if not p.get("secular_theme"):
            p["secular_theme"] = g.get("secular_theme", "")


# ───────────────────────── Fix 5 — weight vector ─────────────────────────
def build_weights(apx, picks, extra_caps=None):
    """Normalize size_units -> weight_pct via the shared builder (_post_common). Per-name half-caps now
    include moat_erosion=='CAP' alongside cro_only (fix 2) / stale_anchor (fix 3); secular-theme
    concentration caps are appended to extra_caps so one melting tail cannot carry the book."""
    caps = list(extra_caps or []) + _pc.secular_theme_caps(picks)
    return _pc.build_weights(apx, picks, extra_caps=caps, per_name_cap=_pc.moat_per_name_cap)


def derive_entry_posture(p, rec=None):
    """Deterministic fallback for entry TIMING when the Director didn't tag one (Director always wins).
    enter_now_carry can't be derived (needs the carry signal) -> scale_in (which also means 'enter now')."""
    cat = str((p.get("catalyst_status") or (rec or {}).get("catalyst_status") or "")).upper()
    if cat.startswith("PENDING_HARD") or cat.startswith("ARB"):
        return "on_confirmation"
    blob = (str(p.get("entry_plan") or "") + " "
            + " ".join(str(a) for a in (p.get("exposure_axes") or [])) + " "
            + str(p.get("lane") or "")).lower()
    if any(k in blob for k in ("knife", "demand-cycle", "cyclical", "de-gross", "degross")):
        return "wait_for_weakness"
    return "scale_in"


def stamp_entry_posture(picks, gin=None):
    """Stamp entry_posture (WHEN to enter) when the Director didn't — his value always wins."""
    for p in picks:
        if p.get("entry_posture"):
            continue
        p["entry_posture"] = derive_entry_posture(p, (gin or {}).get(p["symbol"], {}))


def stamp_entry_plans(picks, quotes):
    """Fix 5c — display-only tranching guidance from distance to the 52w low."""
    for p in picks:
        q = quotes.get(p["symbol"]) or {}
        px, lo = q.get("price"), q.get("yearLow")
        near = isinstance(px, (int, float)) and isinstance(lo, (int, float)) and lo > 0 and (px / lo - 1) < 0.05
        p["entry_plan"] = "3 tranches / 4 wks (knife: <5% above 52w low)" if near else "2 tranches / 2 wks"


def exits_block(picks, quotes):
    """Fix 5d — thesis-break exit levels, sanity-checked against live price (shared; tb = thesis_break_px)."""
    return _pc.exits_block(picks, quotes, thesis_break=lambda p: p.get("thesis_break_px"))


# ───────────────────────── Fix 1 — market-based stress ─────────────────────────
def stress_block(picks, weights, quotes, asof):
    """Shared market-based stress; THIS book's bear leg is the CRO's adverse SoP (bear_fv_px)."""
    return _pc.stress_block(picks, weights, quotes, asof,
                            bear_px=lambda p: p.get("bear_fv_px"), bear_label="bear_fv_px")


# ───────────────────────── Fix 4 — measured correlation ─────────────────────────
def corr_block(syms, weekly_rets, weights, thresh=0.6, hard=0.7):
    """Shared pairwise correlation + betas; THIS book's benchmark is XLY (consumer_beta_xly)."""
    return _pc.corr_block(syms, weekly_rets, weights, beta_symbol="XLY",
                          beta_key="consumer_beta_xly", thresh=thresh, hard=hard)


# ───────────────────────── Fix 7 — cross-surface forensic gate sync ─────────────────────────
def gate_sync(gin):
    """EXCLUDE is a global forensic veto -> strip from the REGIME apex too (the ONE P1 exception).
    CAP may sit in the regime apex but must carry a visible forensic_cap flag. Idempotent."""
    if not REGIME_F.exists():
        return
    try:
        rapx = json.load(open(REGIME_F, encoding="utf-8"))
    except Exception:
        return
    keep, demoted = [], []
    for p in rapx.get("apex_basket", []):
        g = (gin.get(p.get("symbol"), {}) or {}).get("forensic_gate", "")
        if g == "EXCLUDE":
            p["gate_demotion"] = "EXCLUDE: interrogator credibility <=2 (global forensic veto)"
            demoted.append(p)
        else:
            p["forensic_cap"] = (g == "CAP")
            keep.append(p)
    rapx["apex_basket"] = keep
    if demoted:
        dsyms = {d.get("symbol") for d in demoted}
        prior = [r for r in (rapx.get("runner_ups") or [])
                 if (r.get("symbol") if isinstance(r, dict) else r) not in dsyms]
        rapx["runner_ups"] = demoted + prior
    json.dump(rapx, open(REGIME_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if demoted:
        print(f"gate_sync: demoted {[p.get('symbol') for p in demoted]} from regime apex (EXCLUDE)")
    caps = [p.get("symbol") for p in keep if p.get("forensic_cap")]
    if caps:
        print(f"gate_sync: regime apex CAP-flagged (allowed, visible): {caps}")


def main():
    offline = "--offline" in sys.argv
    apx, gin = load()
    apx = consume_skeptic(apx)                              # 8b fork (b): REFUTED demotes BEFORE weights
    picks = [p for p in apx.get("apex_basket", []) if p.get("symbol")]
    syms = [p["symbol"] for p in picks]
    quotes, weekly_rets, asof = get_market(syms, syms + ["XLY"], offline)
    stamp_cro_only(picks, gin)                              # fix 2
    stamp_stale_anchor(picks, gin)                          # fix 3
    stamp_moat_erosion(picks, gin)                          # moat terminal-erosion teeth (additive)
    w_prov = build_weights(apx, picks)                      # provisional (no corr caps)
    corr = corr_block(syms, weekly_rets, w_prov)            # fix 4 (provisional, for breach detection)
    breach_caps = _pc.corr_breach_caps(corr, max_units=1.5)   # shared: breach pairs -> extra_caps (+ WARN print)
    weights = build_weights(apx, picks, extra_caps=breach_caps)   # fix 5 (final, honors breaches)
    corr = corr_block(syms, weekly_rets, weights)                 # recompute combined-weight w/ final weights
    _flagged = {s for f in corr.get("flagged_pairs", []) for s in (f["a"], f["b"])}
    for p in picks:
        p["corr_flag"] = p["symbol"] in _flagged                # fix 4: member of any >=0.6 pair
    stamp_entry_plans(picks, quotes)                             # fix 5c
    stamp_entry_posture(picks, gin)                              # entry TIMING (Director-tag fallback)
    stamp_wheel(picks, "value", quotes)                          # CSP->CC wheel (live yield / qualitative)
    apx["weights"] = weights
    apx["stress_test"] = stress_block(picks, weights, quotes, asof)   # fix 1
    apx["correlation"] = corr                                         # fix 4
    apx["exits"] = exits_block(picks, quotes)                         # fix 5d
    apx["value_post_applied"] = True   # publish gate keys on this (mirror of the regime moat_post_applied)
    json.dump(apx, open(APEX_F, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    gate_sync(gin)                                                   # fix 7 (regime side; separate file)
    st = apx["stress_test"]
    print(f"value_post: stamped {APEX_F} | weights sum={round(sum(weights.values()), 4)} "
          f"| stress 52w-low={st['basket_to_52w_lows_pct']}% recession={st['recession_stress_pct']}% "
          f"| corr avg={corr.get('avg_pairwise')} pairs={corr.get('n_pairs')} "
          f"breaches={sum(1 for f in corr.get('flagged_pairs', []) if f.get('breach'))} "
          f"| cro_only={[p['symbol'] for p in picks if p.get('cro_only')]} "
          f"stale={[p['symbol'] for p in picks if p.get('stale_anchor')]}")


if __name__ == "__main__":
    main()
