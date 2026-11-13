# Basket audit — consolidated findings (13 November 2026)

Thirteen independent Fable reviewers audited the twelve methodology baskets and the selection,
rotation and tracking code they share. Each worked read-only from its own evidence pack, the
2026-11-07 scan, the code and live vendor data. Full reports: `reports/<basket>.md` and
`reports/machinery.md`. The brief they followed is `BRIEF.md`; the packs are in `packs/`.

Nothing in the pipeline was changed. This is not investment advice.

## Verdict

**All twelve baskets were judged unsound as rankings.** The selection code does what it is written
to do (every reviewer reproduced the live picks from the scan), and currency conversion is clean
for the valuation-method baskets. The problem is what gets ranked: numbers that are wrong by a
unit, a share count or an accounting definition, formulas that are not the method they are named
after, and a scan universe that changes for data reasons.

The debate downstream catches much of it. Across the value-method baskets the screen's median
discount is 66–83% while the debate's reconciled discount for the same names is 10–18%, and the
two are uncorrelated (−0.04 to +0.01). That is why the books still worked. But the screen decides
which companies the debate ever sees, and today it is closer to a wide, noisy net than a filter.

## One line per basket

| Basket | Main reason it is unsound | Picks the reviewer calls artefacts |
|---|---|---|
| `acquirers_multiple` | Pounds added to pence for London stocks | 29 of 30 |
| `ev_gp` | Same pounds/pence error | 28 of 30 |
| `earnings_yield_gap` | One reported year of EPS; preference shares and notes admitted; wrong share counts | 9 of 30 (+9 suspected) |
| `ev_gross_profit` | Vendor gross profit not comparable; a quality rank routed as value; frozen by the held-name bonus | 7 of 30 (+4 suspected) |
| `dcf_fcff` | Share count unchecked; minorities not deducted; one-offs in the cash-flow base; growth tied to return on equity | 9 of 30 (+7 overstated) |
| `rd_capitalized_dcf` | Adds 80% of this year's R&D to profit instead of capitalising it | 8 of 30 (+4 inflated) |
| `owner_earnings` | All depreciation added back, only plant spending charged (leases never charged) | 22 of 30 to some degree |
| `epv` | Same add-back; flat 21% tax; no minority deduction | 10 of 30 (+9 suspected or contaminated) |
| `graham_revised` | Growth saturated at the cap (21 of 30); broken "normalised" EPS; no bond-yield term | 10 of 30 (+3 suspected) |
| `iv15_deep_value` | Fifteen-year extrapolation of three years' growth; every qualifier is seated | 7 of 14 |
| `convergence` | Three of eleven "votes" are the price in disguise; exits on moves of 10% or less | 5 of 30 (+5 questionable) |
| `fundamental_momentum` | Seats every qualifier, no exit rule; score rises as price falls | none on units; 4 weak-reason picks |

## The root causes, grouped

What I (the coordinating session) confirmed myself against the code and the scan is marked
**verified**. Everything else is the reviewers' finding, reproduced by them but not re-checked by me.

**1. Units and currency**
- **Pence read as pounds — verified.** For the 178 London names quoted in pence, `market_cap` is in
  pounds while `net_debt`, `ebit` and `gross_profit` are scaled by 100 into pence
  (`screener_v6.py:2879-2882`), and enterprise value adds them (`:6549`, `:6618`). Rightmove's
  multiple is stored as 0.016. Pence names are 5% of the scan but 24 of 30 `acquirers_multiple`
  picks and 29 of 30 `ev_gp` picks. Reviewers date it to the 2026-08-20 currency fix.
- Multi-year averages that mix reporting currencies (GMAB.CO, OKEA.OL, SOFF.OL).

**2. Share counts and share classes**
- **Stale share count — partly verified.** SBSP3.SA's market value and price imply 3,517m shares;
  reviewers report the per-share models use 684m. It sits in five baskets at a 73–94% discount.
  Others reported: 8035.T, PAH3.DE, DRX.L. 85 names scan-wide show the mismatch.
- Preference shares, participation certificates and notes were valued as ordinary shares
  (`50GP.L` is a Croda preference share; also BP-A.L, BP-B.L, LISP.SW, UHRN.SW, ATH-PA). They
  left only because the vendor stopped listing them on 11-07.
- One company in two seats: 2020.HK and 82020.HK are both ANTA Sports.

**3. Accounting definitions**
- **Leases never charged — formula verified.** Owner earnings is net income + depreciation −
  estimated maintenance spending (`:2973`); earnings power is EBIT + depreciation − maintenance
  spending (`:3000`). Lease repayments, rental fleets and concession investment are not charged.
- **Flat 21% tax, no minority deduction in earnings power — verified** (`:3001-3004`).
- One 10% discount rate for every country, below Brazil's own 13.9% yield in the same file.
- Vendor fields that are not what their name says: gross profit equal to revenue for 35 names;
  an "operating income" that changes meaning between years; customer cash counted as net cash.

**4. One-offs and peaks**
- A single exceptional year puts names at the top of several baskets (SPB, PTEC.L, ZEAL.CO,
  GUBRA.CO, BYD, LYFT). DUE.DE's FY2025 net income of €204m includes €256m from discontinued
  operations; continuing operations lost money.

**5. Formulas that are not the named method**
- **R&D "capitalised" DCF — verified.** `adj_net_income = net_income + rd − rd/5` (`:2952`).
- **Graham — verified.** No bond-yield term; growth capped at 20 gives 48.5 times earnings (`:3011-3015`).
- **Convergence — verified.** Rank scores are turned into `price × (1 + score)` and counted as
  valuations (`:6779-6782`).
- The four rank baskets publish a "margin of safety" that is a rescaled rank, and a "fair value"
  that is price × 1.12 to 1.20.

**6. Selectivity**
- `fundamental_momentum` seats all 28 qualifiers; `iv15_deep_value` seats 14 of 17;
  `convergence` has 40 qualifiers for 30 seats.

**7. Rotation**
- **Names vanish from the scan — verified.** The scan holds exactly 200 Hong Kong, 100 Tokyo, 100
  Zurich, 50 Seoul and 50 São Paulo names: the per-exchange row limits bind every week
  (`:1295-1316`), although the code comment says they never do. Names near a cut-off, or near the
  1bn floor, drop in and out. I count 53 of 117 logged exits after 22 September as names missing
  from that week's scan; the machinery reviewer, rebuilding all eight scans, puts it at 71 of 149.
  2618.HK, a value seat, was missing from 3 of 8 scans.
- **The held-name bonus — verified in code.** For the four rank baskets it equals roughly 160
  rank places against a 30-seat basket (`:6870-6873`), so they are frozen; for `convergence` it is
  overwritten, so that basket churns.
- If the previous picks cannot be loaded, every entry date resets silently. It happened on 22 September.

**8. The record**
- **Vanished names are booked at no change — verified** (`:6303-6311`). The 35 cases the machinery
  reviewer could price averaged −6.7%. Year-to-date is overstated in 8 of 12 baskets by 0.8 to 2.7
  points. Otherwise every weekly value reconciles to daily closes.
- Returns are local-currency, price-only, with no split or unit guard.
- `fundamental_momentum` is published as −30.3% in one place and "−14.1% frozen" in another.

## What this means for the seats

| Seat | Books | How it reached the debate | Reviewer's read |
|---|---|---|---|
| 0175.HK | regime | `dcf_fcff`, `graham_revised`, `rd_capitalized_dcf` | Real; discount overstated by working-capital inflows |
| DUE.DE | regime + value | same three | Earnings base is mostly a discontinued-operations gain |
| 2618.HK | value | `dcf_fcff`, `epv`, `owner_earnings`, `iv15_deep_value` | Lease-blind cash flow; one reviewer estimates the discount falls from 60% to about zero once leases are charged |
| INCH.L | regime + value | `acquirers_multiple` | Entered through the pence error; still cheap when corrected (71st of 2,731) |
| MGNS.L | value | `ev_gp` | Entered through the pence error; not cheap when corrected (376th of 3,183) |
| 1698.HK, 9980.HK | value / regime | value-drawdown intake, not a basket | — |
| DECK, LRN | value / both | convergence in July (DECK); route not recoverable (LRN) | — |

These are claims about the SCREEN's numbers. Each seat rests on the debate's own valuation, which
this audit did not re-do. DUE.DE, INCH.L and 2618.HK are already scheduled for a full re-debate by
the 28-day rule added on 12 November; the points above are exactly what those debates should test.

## Fixes, in the order I would make them

1. **Units:** put `market_cap` and the statement figures in the same unit before computing any
   enterprise value. This alone repopulates two baskets.
2. **Scan universe:** raise or remove the per-exchange row limits and add a buffer to the 1bn floor,
   so names stop flickering. Treat a name missing from one scan as "no data", not as an exit.
3. **Security type and share count:** exclude preference shares, certificates and notes; check the
   statement share count against market value divided by price and skip a name when they disagree.
4. **The record:** price a vanished name at its last real close instead of booking 0%.
5. **Formulas:** charge leases in owner earnings and earnings power; deduct minorities; use a
   country discount rate; fix or rename the R&D method; give Graham its bond-yield term and a
   sane growth input; stop counting rank scores as valuations in convergence.
6. **One-offs:** rank on continuing, normalised earnings rather than one reported year.
7. **Rotation:** scale the held-name bonus to the basket's own spread; fail loudly when the
   previous picks cannot be loaded.
8. **Selectivity:** fewer seats than qualifiers for `convergence`, `iv15_deep_value` and
   `fundamental_momentum`, and decide whether the last one is live or frozen.

Items 1 to 4 are data-integrity fixes with no judgement in them. Items 5 to 8 change what the
baskets select and are the owner's call. All of them touch `screener_v6.py`, the production scan.

## Limits of this audit

- Only seven weekly scans exist since the 22 September rebuild; nothing before 7 September could
  be checked.
- I verified the cross-cutting claims listed as **verified** above. The per-name findings (which
  picks are artefacts, the corrected ranks, the lease-adjusted values) are the reviewers' work,
  based on their own reproductions and 10 to 15 live spot checks each.
- No fix was replayed, so the effect of each fix on membership is an estimate.
