# Basket audit — the four data-integrity fixes (13 November 2026)

Approved by Bruno ("fix those four"). All four are in `backend/screener_v6.py` on this branch only.
Nothing is deployed: the production scan runs from `main`, and these do not reach it until this
branch is merged and pushed. Tests: `python backend/tests/test_basket_integrity.py` (27 checks).

These fixes contain no judgement about which companies are good. They make the numbers the baskets
rank mean what they say. The formula and selection changes (items 5 to 8 in `SUMMARY.md`) are not
done and remain the owner's call.

## 1. One unit for enterprise value

The vendor quotes a pence-quoted London stock's price in pence but reports its market value in
pounds. The 20 August currency fix scaled the statement figures into the price currency, and the two
enterprise-value ranks then added pounds to pence. `_market_cap_in_price_units` now scales the
market value by 100 for pence, cents and agorot quotes before it meets net debt, in both
`_rank_ev_gp` and the acquirer's multiple.

## 2. A name missing from a scan is "no data", not an exit

- **Grace period.** A held name absent from this scan keeps its seat, carried verbatim from the
  previous file and flagged `carried_missing_scan`, for up to `MISSING_SCAN_GRACE` = 2 scans. On
  the third it leaves. Its entry date is preserved when it returns.
- **Held names are always re-scanned.** `_held_names_to_rescan` adds every name in last week's
  baskets or seated in a published book that fell outside this week's universe lists, after
  confirming with the vendor that it still trades.
- **Row limits are reported, not raised.** The scan holds exactly 200 Hong Kong, 100 Tokyo, 100
  Zurich, 50 Seoul and 50 São Paulo names, which are the per-exchange limits. `get_symbols` now logs
  a warning whenever a limit binds, and the comment that said they never bind is corrected.
  Raising them grows the universe (run time, vendor calls), so that is left as a decision.

## 3. Share count and listing type

- `_basket_exclusion` compares the statement share count with market value divided by price. A
  ratio outside 0.55 to 1.8 bars the name from every basket and every rank. Its valuations are
  still computed and stored, with the reason in the new `basket_exclusion` field.
- US preferred series (`-PA` style symbols) and yuan counters of Hong Kong listings (`8xxxx.HK`)
  are excluded by symbol, and dropped from the universe before any vendor call is spent on them.
- **Not caught:** a preference share or note whose own market value matches its own price and
  count, with no symbol pattern. That needs the vendor's security type, which the scan does not fetch.

## 4. A vanished holding is priced, not carried at 0%

When a held name is absent from the scan, the tracker now marks it at the vendor's last quote, both
when a period closes and when the name exits (`_vendor_last_closes`, `_vanished_mark`). A quote more
than three times away from the last known price is treated as a unit glitch and rejected. The old
0% carry survives only as the last resort and stays flagged `unpriced_exit`. The open period no
longer drops such a name from its average.

## What the fixes do to today's baskets

Replayed in isolation on the 2026-11-07 scan, with last week's picks as the incumbents:

| Basket | Names replaced | Pence-quoted names, before → after |
|---|---|---|
| `acquirers_multiple` | 22 of 30 | 24 → 5 |
| `ev_gp` | 24 of 30 | 29 → 5 |
| `convergence` | 5 of 30 | 0 → 3 |
| `earnings_yield_gap` | 4 of 30 | 4 → 3 |
| `dcf_fcff` | 2 of 30 | 2 → 3 |
| `rd_capitalized_dcf`, `owner_earnings`, `epv`, `graham_revised` | 1 each | unchanged |
| `ev_gross_profit`, `iv15_deep_value`, `fundamental_momentum` | 0 | unchanged |

- 61 of 3,430 names (1.8%) are barred by the share-count guard. No current seat is among them.
- SBSP3.SA, 8035.T, DRX.L, PAH3.DE, ATH-PA and 82020.HK are out of every basket.
- INCH.L stays in `acquirers_multiple` on correct units. MGNS.L is no longer in any basket; it
  keeps its seat only through the held-seat rule in the weekly prep.
- Grace period, tested by removing 2618.HK from the scan: carried on scans one and two with its
  entry date intact, gone on scan three, and unchanged if it returns after one missed scan.

## Before this is merged

- **The first scan after merging will rotate about 46 names in the two enterprise-value baskets.**
  That is the fix working, but the tracker will book it as one large rebalance.
- **Not exercised:** `_held_names_to_rescan` and `_vendor_last_closes` call the vendor and GCS, so
  they were tested only through their pure helpers and with supplied data, not live.
- **`replay_baseline.py` was not changed.** It builds market value as price times shares, so its
  enterprise values were already in one unit; it does not have the share-count guard.
- A push to `main` redeploys the scan service. Merge deliberately.
