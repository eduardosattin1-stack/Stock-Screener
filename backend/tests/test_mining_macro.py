#!/usr/bin/env python3
"""Offline tests for _opus_debate/mining_macro.py — FUTURE_RESOURCES_SPLIT_SPEC §2.

Zero network: a synthetic `fmp` closure serves deterministic series, so every number below is
predictable from the fixtures.

  M1 pure math      — percentile floor, joint/rebase/chg/dma semantics.
  M2 dials          — D1-D8 present, D4 stamped display-only, sparkline series attached.
  M3 GOLD SEAM      — the precious (monetary_metal) chain scores NEUTRAL on momentum and on the
                      price-percentile setup path, and a gold moonshot cannot move its score.
  M4 fail-open      — a total FMP outage still writes a payload; scores compress to neutral and NO
                      chain is singled out; the banner is honest.
  M5 tilt/phase     — the Dalio tilt leg tracks the published phase and is neutral when UNKNOWN.
  M6 scoreboard     — legs sum to the score, rows are taxonomy-driven, authority string present.

Run: python backend/tests/test_mining_macro.py
"""
import json
import math
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
BK = os.path.dirname(HERE)
OD = os.path.join(BK, "_opus_debate")
sys.path.insert(0, OD)

import mining_macro as MM                                     # noqa: E402

TODAY = date(2026, 7, 27)
TAX = json.loads(Path(OD, "mining_chains.json").read_text(encoding="utf-8"))


def series(n=1600, start=100.0, drift=0.0002, wobble=0.01, end=None):
    """Deterministic pseudo-series; if `end` is given the last close is scaled to exactly that."""
    out, px = [], start
    d0 = TODAY - timedelta(days=int(n * 1.4))
    for i in range(n):
        px *= math.exp(drift + wobble * math.sin(i / 7.0))
        out.append(((d0 + timedelta(days=int(i * 1.4))).isoformat(), round(px, 6)))
    if end is not None and out[-1][1] > 0:
        k = end / out[-1][1]
        out = [(d, round(c * k, 6)) for d, c in out]
    return out


def make_fmp(overrides=None, fail=(), treasury=True, cpi=True):
    """A synthetic screener_v6.fmp. `fail` = symbols/groups that return None (an FMP outage)."""
    over = overrides or {}

    def fmp(endpoint, params=None):
        params = params or {}
        if endpoint.startswith("historical-price-eod"):
            sym = params.get("symbol")
            if sym in fail:
                return None
            rows = over.get(sym)
            if rows is None:
                rows = series(drift=0.0003 if sym in ("GCUSD", "GDX") else 0.0001)
            return [{"date": d, "close": c} for d, c in rows]
        if endpoint == "treasury-rates":
            if not treasury or "TREASURY" in fail:
                return None
            out = []
            for i in range(400):
                d = (TODAY - timedelta(days=399 - i)).isoformat()
                out.append({"date": d, "month3": 3.9, "year2": 4.3, "year10": 4.6 + i * 0.0005,
                            "year30": 5.1})
            return out
        if endpoint == "economic-indicators":
            if not cpi or "CPI" in fail:
                return None
            if params.get("name") == "CPI":
                return [{"date": (TODAY - timedelta(days=30 * (84 - i))).isoformat(),
                         "value": 300 + i * 1.0} for i in range(84)]
            return [{"date": TODAY.isoformat(), "value": 2.3}]
        return None
    return fmp


# ── M1 pure math ──────────────────────────────────────────────────────────────────────────────────
assert MM._pctile(5, list(range(300))) is not None
assert MM._pctile(5, [1, 2, 3]) is None, "percentile must be None below the 252-observation floor"
assert MM._pctile(150, list(range(300))) == 50.2 or 49 < MM._pctile(150, list(range(300))) < 51
assert MM._pctile(1e9, list(range(300))) == 100.0
assert MM._pctile(-1, list(range(300))) == 0.0
a = [("2026-01-01", 10.0), ("2026-01-02", 11.0), ("2026-01-03", 12.0)]
b = [("2026-01-02", 2.0), ("2026-01-03", 3.0), ("2026-01-04", 4.0)]
assert MM._joint(a, b) == [("2026-01-02", 11.0, 2.0), ("2026-01-03", 12.0, 3.0)]
assert MM._rebase(a)[0][1] == 100.0 and round(MM._rebase(a)[-1][1], 4) == 120.0
assert abs(MM._chg(a, 2) - 0.2) < 1e-9 and MM._chg(a, 99) is None
assert MM._dma(a, 2) == 11.5 and MM._dma(a, 99) is None
assert MM._ratio_series(a, b) == [("2026-01-02", 5.5), ("2026-01-03", 4.0)]
assert MM._direction(0.05) == "rising" and MM._direction(-0.05) == "falling"
assert MM._direction(0.0) == "flat" and MM._direction(None) == "unknown"
assert MM._confirmation(0.03) == "confirming" and MM._confirmation(-0.03) == "diverging"
assert len(MM._weekly(series(500))) <= 52
print("M1 OK: percentile floor + joint/rebase/chg/dma/ratio/direction semantics")


# ── M2 dials ──────────────────────────────────────────────────────────────────────────────────────
data, meta = MM.gather(make_fmp(), today=TODAY, cache_path=tempfile.mktemp(suffix=".json"))
dials = MM.build_dials(data, meta)
for want in ("commodities_vs_equities", "copper_gold", "silver_gold", "gold_vs_real_rates",
             "miners_vs_metal", "curve", "dxy", "momentum_table"):
    assert want in dials, f"dial {want} missing"
    assert dials[want].get("source") in ("live", "cache", "missing")
    assert dials[want].get("read"), f"{want} has no human-readable `read` line"
assert dials["gold_vs_real_rates"]["display_only"] is True
assert "scoreboard" in dials["gold_vs_real_rates"]["never_input_to"]
assert dials["commodities_vs_equities"]["series"], "D1 needs a sparkline series for the page"
assert dials["momentum_table"]["rows"] and len(dials["momentum_table"]["rows"]) == len(MM.MOMENTUM_TABLE)
ura = [r for r in dials["momentum_table"]["rows"] if r["symbol"] == "URA"][0]
assert ura["is_proxy"] and "not uranium spot" in ura["proxy_note"]
assert dials["curve"]["spread_2s10s_bp"] is not None and dials["curve"]["shape_2s10s"] in (
    "inverted", "flat", "steep")
print("M2 OK: D1-D8 built, D4 stamped display-only + scoreboard-excluded, sparklines + proxy notes present")


# ── M3 THE GOLD SEAM ──────────────────────────────────────────────────────────────────────────────
snapshot = {"quadrant": "REFLATION", "regime": "NEUTRAL",
            "debt_cycle": {"debt_cycle_phase": "DISCIPLINE", "asof": TODAY.isoformat()}}
board = MM.build_scoreboard(data, meta, TAX, {}, "DISCIPLINE")
prec = next(r for r in board if r["chain_id"] == "precious_metals")
assert prec["monetary_metal"] is True, "precious_metals must carry monetary_metal=true"
assert prec["legs"]["momentum"]["source"] == "monetary_metal_excluded"
assert prec["legs"]["momentum"]["points"] == MM.NEUTRAL_MOM
assert prec["legs"]["setup"]["source"] == "monetary_metal_excluded", \
    "with no vs_incentive_pct the setup leg would be gold's own price percentile — must be excluded"
assert prec["legs"]["setup"]["points"] == MM.NEUTRAL_SETUP
copper = next(r for r in board if r["chain_id"] == "copper_mining")
assert copper["monetary_metal"] is False and copper["legs"]["momentum"]["source"] != "monetary_metal_excluded"

# A gold MOONSHOT (+300%) must never REWARD the chain. Two distinct assertions, because the legs
# have deliberately different sensitivities:
#   - setup + momentum are FROZEN: gold's own price action cannot add a single point. This is the
#     momentum-loop guard proper.
#   - confirmation is ALLOWED to react, but only ever contrarily: it measures miners-vs-metal, so a
#     metal spike the equities do not confirm scores DOWN (an unconfirmed, paper move). Scoring a
#     gold rip lower is the guard working, not leaking — do not "fix" this by freezing the leg.
moon = MM.gather(make_fmp({"GCUSD": series(end=4000.0, drift=0.0025),
                           "SIUSD": series(end=90.0, drift=0.0025)}),
                 today=TODAY, cache_path=tempfile.mktemp(suffix=".json"))
board_moon = MM.build_scoreboard(moon[0], moon[1], TAX, {}, "DISCIPLINE")
prec_moon = next(r for r in board_moon if r["chain_id"] == "precious_metals")
for leg in ("setup", "momentum"):
    assert prec_moon["legs"][leg] == prec["legs"][leg], (
        f"gold price action moved the {leg} leg ({prec['legs'][leg]} -> {prec_moon['legs'][leg]}) "
        f"on a +300% gold move — the momentum-loop guard is broken.")
assert prec_moon["score"] <= prec["score"], (
    f"a gold moonshot RAISED the precious score ({prec['score']} -> {prec_moon['score']}) — that is "
    f"momentum chasing, exactly what the Jan-2026-top guard forbids.")
assert prec_moon["legs"]["confirmation"]["points"] < prec["legs"]["confirmation"]["points"], \
    "an unconfirmed metal spike should score the confirmation leg DOWN"
print(f"M3 OK: GOLD SEAM — setup + momentum legs FROZEN across a +300% gold move; the score falls "
      f"{prec['score']} -> {prec_moon['score']} via miners-confirmation (unconfirmed move penalized, "
      f"never rewarded)")

# ...but genuine cost-curve economics (vs_incentive_pct) DO score, even for a monetary metal
regime_live = {"precious_metals": {"state": "TAILWIND", "vs_incentive_pct": -20.0,
                                   "as_of": TODAY.isoformat()}}
b2 = MM.build_scoreboard(data, meta, TAX, regime_live, "DISCIPLINE")
prec2 = next(r for r in b2 if r["chain_id"] == "precious_metals")
assert prec2["legs"]["setup"]["source"] == "vs_incentive" and prec2["legs"]["setup"]["points"] == 25.0
assert prec2["legs"]["momentum"]["source"] == "monetary_metal_excluded", "momentum stays excluded"
print("M3b OK: cost-curve economics (vs_incentive_pct -20% -> 25/30 pts) still score a monetary "
      "chain; only PRICE MOMENTUM is excluded")


# ── M4 fail-open under a total outage ─────────────────────────────────────────────────────────────
allsyms = MM.CORE_SERIES + MM.CORE_ETFS + ["TREASURY", "CPI"]
d0, m0 = MM.gather(make_fmp(fail=set(allsyms)), today=TODAY, cache_path=tempfile.mktemp(suffix=".json"))
assert all(v == "missing" for v in m0["source"].values())
board0 = MM.build_scoreboard(d0, m0, TAX, {}, "UNKNOWN")
scores = {r["chain_id"]: r["score"] for r in board0}
assert len(set(scores.values())) == 1, f"an outage must not differentiate chains: {scores}"
assert all(r["confidence"] == "low" for r in board0)
pay0 = MM.build_payload(d0, m0, TAX, {}, {}, today=TODAY)
assert pay0["degraded"] is True and "NO data" in pay0["stale_banner"]
assert pay0["scoreboard"] and pay0["dials"], "a degraded run still publishes a full payload"
assert pay0["debt_cycle_phase"] == "UNKNOWN"
assert set(pay0["tilt"]["resolved"].values()) == {"neutral"}, "no snapshot -> all-neutral tilt"
print(f"M4 OK: total outage -> every chain scores {list(scores.values())[0]}/100 (symmetric, "
      f"nothing singled out), payload still written, banner honest")


# ── M5 the Dalio tilt leg tracks the phase ────────────────────────────────────────────────────────
def tilt_for(chain_id, phase):
    b = MM.build_scoreboard(data, meta, TAX, {}, phase)
    return next(r for r in b if r["chain_id"] == chain_id)["legs"]["tilt"]["points"]


assert tilt_for("precious_metals", "FORCING") == 20 and tilt_for("copper_mining", "FORCING") == 4
assert tilt_for("precious_metals", "EXPANSION") == 8 and tilt_for("copper_mining", "EXPANSION") == 15
assert tilt_for("precious_metals", "MONETIZATION") == tilt_for("copper_mining", "MONETIZATION") == 20
assert tilt_for("precious_metals", "UNKNOWN") == tilt_for("copper_mining", "UNKNOWN") == 10
assert tilt_for("copper_mining", "garbage-phase") == 10, "unknown phase must fail open to neutral"
print("M5 OK: Dalio tilt leg tracks the published phase (FORCING favors monetary 20/4, EXPANSION "
      "inverts 8/15, MONETIZATION lifts both, UNKNOWN neutral 10/10)")


# ── M6 scoreboard integrity ───────────────────────────────────────────────────────────────────────
assert {r["chain_id"] for r in board} == {c["id"] for c in TAX["chains"]}, "rows must be taxonomy-driven"
for r in board:
    legs = sum(r["legs"][k]["points"] for k in ("setup", "momentum", "confirmation", "tilt"))
    assert abs(legs - r["score"]) < 0.05, f"{r['chain_id']}: legs {legs} != score {r['score']}"
    assert 0 <= r["score"] <= 100
assert [r["rank"] for r in board] == sorted(r["rank"] for r in board)
assert board == sorted(board, key=lambda r: -r["score"]), "rows must be ranked descending"
pay = MM.build_payload(data, meta, TAX, {}, snapshot, today=TODAY)
assert "Never gates membership" in pay["scoreboard_authority"]
assert "scores nothing" in pay["gold_note"]
assert pay["tilt"]["resolved"] and pay["generated_at"] == TODAY.isoformat()
json.dumps(pay)
uranium = next(r for r in board if r["chain_id"] == "uranium_fuel_cycle")
assert uranium["legs"]["confirmation"]["source"] == "n/a_proxy_only", \
    "a proxy-only chain has no independent metal to confirm against"
print("M6 OK: legs sum to score, taxonomy-driven rows, ranked, proxy-only confirmation stamped, "
      "authority + gold notes present, payload JSON-serializable")

print("\nALL MINING-MACRO TESTS PASSED")
