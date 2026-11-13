"""Basket audit 2026-11-13 - the four data-integrity fixes in screener_v6.py.

  1. one unit for enterprise value (pence-quoted London names)
  2. a held name missing from a scan is carried, not exited; held names are always re-scanned
  3. share-count / listing-type guard
  4. a vanished holding is priced at the vendor's last quote, not carried at 0%

No network and no GCS: FMP_OFFLINE=1 and every function under test is pure or is handed its data.
The replay section needs backend/_opus_debate/latest_global.json (the 2026-11-07 scan) and is
skipped, loudly, when that file is absent.

    python backend/tests/test_basket_integrity.py
"""
import json
import os
import sys
from pathlib import Path

os.environ["FMP_OFFLINE"] = "1"
BK = Path(__file__).resolve().parents[1]
REPO_BK = Path(os.environ.get("REPO_BACKEND", str(BK)))        # where the scan + sibling modules live
sys.path.insert(0, str(REPO_BK)); sys.path.insert(0, str(BK))  # BK first: the code under test
import logging                                                  # noqa: E402
logging.disable(logging.CRITICAL)
import screener_v6 as S                                         # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name)


class N:   # a minimal stand-in for a Stock row
    def __init__(self, **k):
        self.__dict__.update(k)


# ── fix 1: units ─────────────────────────────────────────────────────────────
rmv = N(symbol="RMV.L", currency="GBp", price=555.4, market_cap=3_997_498_820.0,
        net_debt=-3_572_200_000.0, ebit=26_700_000_000.0, gross_profit=42_000_000_000.0, basket_exclusion="")
check("a pence-quoted market value is scaled into pence before it meets net debt",
      abs(S._market_cap_in_price_units(rmv) - 399_749_882_000.0) < 1)
usd = N(symbol="X", currency="USD", market_cap=5e9)
eur = N(symbol="Y.DE", currency="EUR", market_cap=5e9)
check("dollar and euro market values are left alone",
      S._market_cap_in_price_units(usd) == 5e9 and S._market_cap_in_price_units(eur) == 5e9)
S._rank_ev_gp([rmv, N(symbol="Z", currency="USD", market_cap=1e9, net_debt=0.0, gross_profit=5e8, basket_exclusion="")])
check("Rightmove's EV / gross profit is about 9.4, not 0.01 (the stored value before the fix)",
      9.0 < rmv.ev_gp < 9.8)
netcash = N(symbol="MGNS.L", currency="GBp", price=4342.0, market_cap=2_059_352_634.0,
            net_debt=-45_760_000_000.0, gross_profit=6.4e10, basket_exclusion="")
S._rank_ev_gp([netcash, rmv])
check("a UK name with net cash no longer gets a NEGATIVE enterprise value (Morgan Sindall)", netcash.ev_gp > 0)

# ── fix 3: share count and listing type ──────────────────────────────────────
why, ratio = S._basket_exclusion("SBSP3.SA", 94_177_398_758.0, 26.78, "BRL", 684e6)
check("SBSP3.SA (684m statement shares vs 3,517m implied) is excluded", bool(why) and abs(ratio - 0.1945) < 0.002)
why, ratio = S._basket_exclusion("PAH3.DE", 1e10, 40.0, "EUR", 125e6)
check("an EXACT halving (ratio 0.50) is excluded - the old `< 0.5` test missed it", bool(why) and ratio == 0.5)
why, ratio = S._basket_exclusion("INCH.L", 2_130_657_407.0, 639.0, "GBp", 379.8e6)
check("INCH.L passes, and its ratio is computed in pence (about 1.14)", why == "" and 1.1 < ratio < 1.18)
why, ratio = S._basket_exclusion("9980.HK", 1e11, 100.0, "HKD", 755e6)
check("a 0.755 ratio (9980.HK) stays in: buybacks and issuance are not a mismatch", why == "")
why, ratio = S._basket_exclusion("NEW", 1e9, 10.0, "USD", 0)
check("missing statement shares never exclude a name by themselves", why == "" and ratio is None)
check("a US preferred series is excluded by its symbol", bool(S._basket_exclusion("ATH-PA", 1e9, 20.0, "USD", 5e7)[0]))
check("a yuan counter of a Hong Kong listing is excluded (82020.HK), the HK-dollar line is not",
      bool(S._non_ordinary_listing("82020.HK")) and not S._non_ordinary_listing("2020.HK"))
check("ordinary tickers containing a P are untouched",
      not any(S._non_ordinary_listing(s) for s in ("BP.L", "PG", "SAP.DE", "BRK-B", "HEI-A", "PBR-A")))
ex = N(symbol="BAD", currency="USD", price=10.0, eps_latest=5.0, fx_to_price=1.0, country="US",
       market_cap=1e9, net_debt=0.0, ebit=1e8, gross_profit=5e8, total_assets=1e9,
       basket_exclusion="statement share count is 0.20x")
good = N(symbol="GOOD", currency="USD", price=10.0, eps_latest=1.0, fx_to_price=1.0, country="US",
         market_cap=1e9, net_debt=0.0, ebit=1e8, gross_profit=5e8, total_assets=1e9, basket_exclusion="")
S._rank_ey_gap([ex, good]); S._rank_ev_gp([ex, good])
check("an excluded name takes no part in the earnings-yield or EV / gross-profit ranks",
      ex.earnings_yield_gap_mos == -1.0 and ex.ev_gp_mos == -1.0 and good.ev_gp_mos > -1.0)
check("the Stock dataclass carries the three new fields (asdict keeps them in the scan JSON)",
      all(f in S.Stock.__dataclass_fields__ for f in ("statement_shares", "share_count_ratio", "basket_exclusion")))

# ── fix 4: vanished holdings ─────────────────────────────────────────────────
check("a vendor quote inside the band is used", S._vanished_mark("TEAM", 100.0, {"TEAM": 67.5}) == (67.5, "vendor_quote"))
check("a quote 100x off (a pounds/pence flip) is rejected and the old carry is flagged",
      S._vanished_mark("50GP.L", 77.0, {"50GP.L": 0.77}) == (77.0, "last_known"))
check("no quote at all -> last known, flagged", S._vanished_mark("GONE", 10.0, {}) == (10.0, "last_known"))


def _track(holdings):
    return {"methodologies": {"m": {"rebalances": [{"date": "2026-10-24", "holdings": [h["symbol"] for h in holdings]}],
                                    "current_holdings": holdings, "all_exits_2026": [], "ytd_return": 0.0,
                                    "realized_ytd": 0.0, "tracking_start": "2026-10-24", "rebalance_count": 1}}}


hold = [{"symbol": "A", "entry_price": 100.0, "entry_date": "2026-10-24", "period_start_price": 100.0, "weight": 0.5},
        {"symbol": "TEAM", "entry_price": 100.0, "entry_date": "2026-10-24", "period_start_price": 100.0, "weight": 0.5}]
smap = {"A": N(price=110.0, m_mos=0.3), "B": N(price=50.0, m_mos=0.4)}
picks = {"m": {"picks": [{"symbol": "A", "price": 110.0, "mos": 0.3}, {"symbol": "B", "price": 50.0, "mos": 0.4}]}}
t_old = _track([dict(h) for h in hold])
S._append_rebalance_to_tracking(t_old, picks, "2026-11-07", stock_map=smap, fallback_px={})
t_new = _track([dict(h) for h in hold])
S._append_rebalance_to_tracking(t_new, picks, "2026-11-07", stock_map=smap, fallback_px={"TEAM": 67.5})
r_old, r_new = t_old["methodologies"]["m"]["realized_ytd"], t_new["methodologies"]["m"]["realized_ytd"]
check("with no quote the period closes at (+10% + 0%) / 2 = +5% - the old, flattering figure", abs(r_old - 0.05) < 1e-9)
check("with the vendor quote it closes at (+10% - 32.5%) / 2 = -11.25%", abs(r_new - (-0.1125)) < 1e-9)
x_old = t_old["methodologies"]["m"]["all_exits_2026"][0]
x_new = t_new["methodologies"]["m"]["all_exits_2026"][0]
check("the unpriced exit is flagged and booked flat", x_old.get("unpriced_exit") is True and x_old["return"] == 0.0)
check("the vendor-priced exit books -32.5% and says where the price came from",
      abs(x_new["return"] + 0.325) < 1e-9 and x_new.get("exit_price_source") == "vendor_quote"
      and "unpriced_exit" not in x_new)
mt = {"realized_ytd": 0.0, "current_holdings": [dict(h) for h in hold]}
check("the open period no longer DROPS a vanished name: (+10% - 32.5%) / 2",
      abs(S._compute_ytd_return(mt, {"A": 110.0}, {"TEAM": 67.5}) + 0.1125) < 1e-9)
check("legacy callers (no fallback map) behave exactly as before",
      abs(S._compute_ytd_return(mt, {"A": 110.0}) - 0.10) < 1e-9)

# ── replay on the real 2026-11-07 scan ───────────────────────────────────────
scan_f = REPO_BK / "_opus_debate" / "latest_global.json"
if not scan_f.exists():
    print("SKIPPED  replay on the 2026-11-07 scan (latest_global.json not present)")
else:
    rows = json.load(open(scan_f, encoding="utf-8"))["stocks"]
    stocks = []
    for x in rows:
        bh = (x.get("buffett_history") or {}).get("rows") or []
        sh = next((r["shares_mm"] * 1e6 for r in reversed(bh)
                   if isinstance(r.get("shares_mm"), (int, float)) and r["shares_mm"] > 0), 0.0)
        s = N(symbol=x["symbol"], currency=x.get("currency") or "USD", price=x.get("price") or 0.0,
              market_cap=x.get("market_cap") or 0.0, net_debt=x.get("net_debt"), ebit=x.get("ebit") or 0.0,
              gross_profit=x.get("gross_profit") or 0.0, sector=x.get("sector"))
        s.basket_exclusion, s.share_count_ratio = S._basket_exclusion(s.symbol, s.market_cap, s.price, s.currency, sh)
        stocks.append(s)
    excl = [s for s in stocks if s.basket_exclusion]
    q = S._rank_ev_gp(stocks)
    top = q[:60]
    pence_top = sum(1 for s in top if s.currency in ("GBp", "GBX"))
    pence_all = sum(1 for s in q if s.currency in ("GBp", "GBX"))
    print(f"         replay: {len(stocks)} names | excluded {len(excl)} ({100 * len(excl) / len(stocks):.1f}%) | "
          f"EV/GP qualifiers {len(q)} | pence names in the cheapest 60: {pence_top} (pence share of pool "
          f"{100 * pence_all / len(q):.1f}%)")
    check("fewer than 3% of the scan is excluded by the guard", len(excl) / len(stocks) < 0.03)
    check("the known bad names are all excluded (SBSP3.SA, 8035.T, DRX.L, PAH3.DE)",
          all(any(s.symbol == k and s.basket_exclusion for s in stocks) for k in ("SBSP3.SA", "8035.T", "DRX.L", "PAH3.DE")))
    check("no current seat is excluded",
          not any(s.basket_exclusion for s in stocks
                  if s.symbol in ("0175.HK", "INCH.L", "DUE.DE", "LRN", "9980.HK", "1698.HK", "2618.HK", "MGNS.L", "DECK")))
    check("pence-quoted names no longer dominate the cheapest EV / gross-profit names (was 29 of 30)",
          pence_top <= 15)
    neg_pence = sum(1 for s in q if s.currency in ("GBp", "GBX") and s.ev_gp < 0)
    print(f"         pence names with a negative enterprise value after the fix: {neg_pence}")

print(f"\n{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
