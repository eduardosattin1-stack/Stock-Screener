"""Macro quadrant inputs + inflation-resilience label (2026-10-12).

No network: fixtures are the real 2026 tape as FMP/BLS printed it on 2026-10-12. Run:
    python backend/tests/test_macro_inputs.py
Background: from 2026-07-16 (quadrant shipped) to 2026-10-12 the growth x inflation quadrant
read GOLDILOCKS every week on a 0.5 CPI default + a hardcoded Q4-2025 GDP seed, because FMP's
economic-indicators endpoint stopped honouring from/to windows. These tests pin the repair.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import macro_regime as M          # noqa: E402
import inflation_resilience as IR  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# CPI-U SA headline, newest first. 2025-10 is ABSENT on purpose: BLS never published it
# (federal shutdown) - the series must tolerate the hole.
CPI = [("2026-08-01", 334.131), ("2026-07-01", 332.813), ("2026-06-01", 332.568),
       ("2026-05-01", 333.979), ("2026-04-01", 332.407), ("2026-03-01", 330.293),
       ("2026-02-01", 327.460), ("2026-01-01", 326.588), ("2025-12-01", 326.031),
       ("2025-11-01", 325.063), ("2025-09-01", 324.245), ("2025-08-01", 323.290)]
REAL_GDP = [("2026-04-01", 24408.011), ("2026-01-01", 24274.383), ("2025-10-01", 24125.479),
            ("2025-07-01", 24112.966), ("2025-04-01", 23884.563), ("2025-01-01", 23650.213)]
TODAY = datetime(2026, 10, 12)

print("=== CPI measures (date-matched, y/y level + 6m trend) ===")
m = M.cpi_measures(CPI)
check("y/y matched by date across the missing Oct-2025 print", m and abs(m["yoy_pct"] - 3.35) < 0.02, m)
check("6m annualized ~4.1%", m and abs(m["ann_6m_pct"] - 4.12) < 0.05, m)
check("trend accelerating (6m above y/y by > 0.3pp)", m and m["trend"] == "accelerating", m)
check("score = 0.50 band x 0.7 acceleration penalty = 0.35", m and abs(m["score"] - 0.35) < 1e-9, m)
check("the one-month June dip no longer reads as 'at target'", M._score_cpi_trend(CPI) < 0.5)
check("too thin (< 7 points) -> None, and the scorer's neutral 0.5", M.cpi_measures(CPI[:5]) is None
      and M._score_cpi_trend(CPI[:5]) == 0.5)
m7 = M.cpi_measures(CPI[:8])
check("7-12 points: 6m annualized stands in as the level, flagged", m7 and m7["level_basis"] == "6m_annualized", m7)

print("\n=== real GDP momentum (annualized on the live path) ===")
g = M._score_gdp_momentum(REAL_GDP, annualize=True)
check("real Q2-2026 +2.2% annualized, decelerating -> 0.85 (growth up)", abs(g - 0.85) < 1e-9, g)
check("same data un-annualized would have read growth DOWN (0.45) - the reason for the flag",
      abs(M._score_gdp_momentum(REAL_GDP) - 0.45) < 1e-9, M._score_gdp_momentum(REAL_GDP))

print("\n=== quadrant inputs provenance + fail-open ===")
qi = M.quadrant_inputs(CPI, REAL_GDP, "fmp_points", "fmp_points", TODAY)
check("live 2026-10-12 tape is usable", qi["ok"], qi["problems"])
sub = {"cpi_trend": M._score_cpi_trend(CPI), "gdp_momentum": g}
q = M.growth_inflation_quadrant(sub, inputs=qi)
check("quadrant = REFLATION on the real tape", q["quadrant"] == "REFLATION", q)
check("basis carries the measured numbers", "+3.35% y/y" in q["quadrant_basis"] and "real GDP" in q["quadrant_basis"], q)
bad = M.quadrant_inputs([], REAL_GDP, "none", "fmp_points", TODAY)
check("no CPI -> not usable", not bad["ok"] and any("CPI" in p for p in bad["problems"]), bad)
qb = M.growth_inflation_quadrant({"cpi_trend": 0.5, "gdp_momentum": 0.65}, inputs=bad)
check("defaulted inputs publish UNKNOWN, never GOLDILOCKS (the 07-16..10-12 failure)",
      qb["quadrant"] == "UNKNOWN", qb)
seed = M.quadrant_inputs(CPI, REAL_GDP, "fmp_points", "seed", TODAY)
check("a seeded axis is flagged", not seed["ok"] and any("seed" in p for p in seed["problems"]), seed)
stale = M.quadrant_inputs(CPI, REAL_GDP, "gcs_cache", "gcs_cache", datetime(2027, 3, 1))
check("a cache that stopped updating is flagged stale", not stale["ok"]
      and any("old" in p for p in stale["problems"]), stale["problems"])
check("historical callers (no inputs) keep the old un-gated behaviour",
      M.growth_inflation_quadrant({"cpi_trend": 0.5, "gdp_momentum": 0.65})["quadrant"] == "GOLDILOCKS")

print("\n=== FMP window-drop backfill (_fetch_monthly_series) ===")
calls = []


def fake_fmp(endpoint, params):
    calls.append(dict(params))
    pts = {d: v for d, v in CPI}
    if params["from"] != params["to"]:          # window query: FMP returns ONE row now
        return [{"date": "2026-08-01", "value": 334.131}]
    v = pts.get(params["from"])
    return [{"date": params["from"], "value": v}] if v is not None else []


vals = M._fetch_monthly_series(fake_fmp, "CPI", "2025-08-08", "2026-10-12")
check("thin window is backfilled with point queries", len(vals) == len(CPI), len(vals))
check("newest first, no duplicates", vals[0][0] == "2026-08-01" and len({d for d, _ in vals}) == len(vals))
check("provenance records the point backfill", M._FETCH_META["CPI"]["source"] == "fmp_points", M._FETCH_META["CPI"])
check("quarter starts enumerate correctly",
      M._period_starts("2025-04-08", "2026-10-12", "Q")[:3] == ["2025-04-01", "2025-07-01", "2025-10-01"],
      M._period_starts("2025-04-08", "2026-10-12", "Q"))

print("\n=== inflation resilience (deterministic label) ===")


def stmt(date, rev, cogs, oi):
    return {"date": date, "revenue": rev, "costOfRevenue": cogs, "grossProfit": rev - cogs, "operatingIncome": oi}


ko = [stmt("2019-12-31", 100, 39.2, 27.1), stmt("2021-12-31", 100, 39.7, 26.7), stmt("2022-12-31", 100, 41.84, 25.4)]
r = IR.classify(ko, "Consumer Defensive")
check("KO-shaped -2.6pp -> mixed", r["inflation_resilience"] == "mixed", r)
check("basis shows the numbers", "60.8%" in r["inflation_resilience_basis"] and "-2.6pp" in r["inflation_resilience_basis"], r)
up = [stmt("2019-11-29", 100, 15, 29), stmt("2022-12-02", 100, 12.3, 34.6)]
check("margin held/expanded -> resilient", IR.classify(up, "Technology")["inflation_resilience"] == "resilient")
sq = [stmt("2019-12-31", 100, 60, 10), stmt("2022-12-31", 100, 66, 5)]
check("-6pp squeeze -> exposed", IR.classify(sq, "Consumer Cyclical")["inflation_resilience"] == "exposed")
check("financial sector -> unknown (no cost-of-sales line)",
      IR.classify(ko, "Financial Services")["inflation_resilience"] == "unknown")
bank = [stmt("2019-12-31", 100, 22.7, 31.5), {"date": "2021-12-31", "revenue": 100, "costOfRevenue": -3.6,
                                             "grossProfit": 103.6, "operatingIncome": 46.8}]
rb = IR.classify(bank, None)
check("negative cost-of-sales (JPM FY2021) -> unknown even without a sector",
      rb["inflation_resilience"] == "unknown" and rb["inflation_resilience_source"] == "no_cogs", rb)
check("listed after 2020 -> unknown, never a penalty",
      IR.classify([stmt("2022-12-31", 100, 50, 10)], None)["inflation_resilience"] == "unknown")
recl = [stmt("2019-08-31", 100, 77, 8.1), stmt("2023-06-30", 100, 93.2, 7.0)]
rr = IR.classify(recl, "Consumer Defensive")
check("gross margin -16pp with operating margin ~flat -> reclassification, unknown",
      rr["inflation_resilience"] == "unknown" and rr["inflation_resilience_source"] == "reclassified", rr)
jan = [stmt("2020-02-01", 100, 55.8, 19.2), stmt("2022-01-29", 100, 51.1, 25.5), stmt("2023-01-28", 100, 56.9, 18.2)]
rj = IR.classify(jan, "Consumer Cyclical")
check("January year-ends land in the right windows (FY to 2020-01 base, worst FY to 2023-01)",
      rj.get("base_fy_end") == "2020-02-01" and rj.get("shock_fy_end") == "2023-01-28", rj)
picks = [{"symbol": "AAA"}, {"symbol": "ZZZ"}]
import json, tempfile                                      # noqa: E401,E402
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "ir.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"by_symbol": {"AAA": IR.classify(ko, "Consumer Defensive")}}, f)
    n = IR.stamp(picks, p)
check("stamp copies the label onto seats; a missing name reads unknown",
      n == 1 and picks[0]["inflation_resilience"] == "mixed" and picks[1]["inflation_resilience"] == "unknown", picks)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
