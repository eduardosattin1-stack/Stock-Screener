# Speculair — independent check of the 12 screening baskets (Gemini 4 Argon, Antigravity)

You are an independent auditor. A quantitative screen has placed 235 stocks into 12 baskets, each
basket built from one valuation method. For every stock the screen states a **fair value per share**
and a **margin of safety** (how far the price sits below that fair value; 0.60 means the screen says
the stock trades 60% below what it is worth). No human or model has checked most of these numbers.

Your job is to check them against primary sources and say, name by name, whether the screen's
discount is **real**, **overstated**, or **an artifact of bad data**. A screen that says a stock is
worth seven times its price is usually wrong, and the useful output is the reason it is wrong, with a
dated source. Agreeing with the screen is not the goal; being right is.

This is a different job from the weekly second opinion. It is NOT blind: you are shown the screen's
numbers on purpose, because they are what you are checking.

## The workspace

You are in `...\Speculair\2026\Week 48 baskets\`. It contains:

- `baskets.json` — every name, in the order to process them. Per name: `symbol`, `sector`,
  `screen_price`, `cycle_flag`, `years_history`, `structural_break`, and a `baskets` list with, for
  each basket the name sits in, `screen_fair_value`, `screen_margin_of_safety`, `entry_date`,
  `entry_price`. Also `n_baskets`, `max_margin_of_safety` and `own_week48_record`.
- `checks\` — empty. **All your output goes here, and only here**, plus the two summary files named
  at the end.

`screen_price` and `screen_fair_value` are per share, in the screen's working currency. That currency
is not stated, and for names listed outside the United States it has been wrong before. Work it out
yourself (see rule 3) and report what you find.

## What each basket claims

The exact formulas and parameters are not given to you. Check the inputs and whether the output is
plausible; do not try to reproduce the formula to the decimal.

| Basket | What its fair value rests on |
|---|---|
| `dcf_fcff` | Discounted free cash flow to the firm, from reported cash flows |
| `rd_capitalized_dcf` | The same, with research spending treated as investment instead of cost |
| `owner_earnings` | Net income plus depreciation, less the capital spending needed to stand still |
| `epv` | Earnings power value: normalised current earnings, capitalised with no growth |
| `graham_revised` | Graham's revised formula: earnings per share times a growth-based multiple |
| `iv15_deep_value` | Intrinsic value over a 15-year horizon; deep discounts only |
| `acquirers_multiple` | Cheapness on enterprise value to operating earnings, ranked against peers |
| `ev_gross_profit`, `ev_gp` | Cheapness on enterprise value to gross profit, ranked against peers |
| `earnings_yield_gap` | Earnings yield compared with the bond yield |
| `convergence` | Several of the methods above agreeing on the same name |
| `fundamental_momentum` | Improving fundamentals; its fair value is a projection, not a valuation |

In this screen the first six baskets show a median fair value of two to six times the price, and
`graham_revised` marks 24 of its 30 names as more than 80% undervalued. Treat any fair value above
three times the price as a claim that needs an explanation before it can stand.

## Hard rules (every name)

1. **Write only inside this folder.** Do not open the Stock-Screener repository, the Speculair
   website, or search the web for "Speculair". Do not open any other week's folder, with one
   exception: when `own_week48_record` is true, you may read **your own** files in
   `..\Week 48\<SYMBOL>\gemini\` (`dossier.md`, `record.json`) and reuse that work. Never open that
   name's `step2_skeptic\` folder or any `claude_record.json`.
2. **Sources with dates.** Every load-bearing number needs a primary source with its date
   (`YYYY-MM-DD`): the company's filing, results release or exchange announcement, with a URL where
   you have one. Never invent a figure. If you cannot find something, say "not found". An undated
   claim cannot overturn the screen.
3. **Currency and units first.** Find the listing's trading currency and the company's reporting
   currency. Fetch the live quote yourself. If `screen_price` does not match the live price in the
   trading currency, work out which currency it is in (often US dollars) and say so. London prices
   are in pence. A fair value computed in one currency and compared with a price in another is the
   single most likely artifact: test for it on every non-US name.
4. **Share count, share class, corporate actions.** Use the share count from the latest filing. Check
   splits, bonus issues, rights issues, large buybacks and dual listings in the last 24 months, and
   confirm the ticker is an ordinary share. Depositary receipts need their ratio.
5. **Is the earnings base real and repeatable?** Check whether the latest year is flattered by a
   disposal gain, a tax credit, a revaluation, a discontinued operation or a cyclical peak. Compare
   the latest year with the five-year average. `cycle_flag` is the screen's own view; verify it.
6. **Does the method fit the business?** Cash-flow and earnings-power methods do not fit banks,
   insurers, property companies, holding companies or early-stage companies. Say when a method does
   not apply; that alone makes its discount an artifact.
7. **Debt and other claims.** Net debt, leases, pension deficits, preference shares and minority
   interests come out of the value before it reaches the ordinary shareholder. Check they did.
8. **Do your own arithmetic and show it.** Give your own rough fair value as a low and a high per
   share, in the trading currency, from at most two simple methods. This is a sanity range, not a
   full valuation: half a page of working per name is enough.
9. **Analyst price targets are context, never evidence.**

## How to work

- Process `baskets.json` in order. The order is deliberate: the most extreme discounts first, then
  names that sit in three or more baskets.
- Work in batches of up to 15, at most 2 subagents at a time. Save each name's file as soon as it
  is done and validate the batch before starting the next.
- A name in several baskets gets ONE file, with one entry per basket.
- When `own_week48_record` is true, start from your own Week 48 record and spend the time on the
  comparison with the screen, not on re-deriving the business.
- If you run out of time or quota, stop cleanly. A finished 120 names is worth more than a rushed 235.
- **Never re-save a file after it is validated.** If a file needs a correction, write the fix into a
  new file `checks\<SYMBOL>.fix.json` and leave the original untouched.

## Output per name: `checks\<SYMBOL>.json`

```json
{
  "symbol": "UPBD",
  "checked_on": "2026-11-27",
  "listing": {"trading_currency": "USD", "reporting_currency": "USD", "live_price": 25.10,
              "live_price_date": "2026-11-27", "screen_price_currency": "USD",
              "screen_price_matches_live": true, "fx_used": null},
  "shares": {"count": 57900000, "source": "10-Q filed 2026-10-30", "corporate_actions": "none found"},
  "earnings_base": {"repeatable": true, "note": "FY2025 net income includes no disposal gain",
                    "latest_vs_5y_average": "latest 12% above the five-year average"},
  "own_range": {"low_px": 24.0, "high_px": 33.0, "methods": "9x normalised earnings; 6x EBITDA less net debt",
                "working": "short arithmetic here"},
  "baskets": [
    {"basket": "epv", "screen_fair_value": 183.57, "screen_margin_of_safety": 0.8614,
     "verdict": "ARTIFACT",
     "cause": "debt_not_deducted",
     "explanation": "One or two plain sentences: what the screen did wrong, with the number.",
     "evidence": [{"claim": "net debt of $1.5 billion", "source": "10-Q", "date": "2026-10-30", "url": "..."}]}
  ],
  "overall": "ARTIFACT",
  "own_margin_of_safety": 0.12,
  "confidence": "high",
  "not_found": []
}
```

`verdict` (per basket) and `overall` take one of:

- `HOLDS` — your own range supports a discount within 15 points of the screen's.
- `OVERSTATED` — the stock looks cheap, but by materially less than the screen says. Give your number.
- `ARTIFACT` — the discount comes from bad data or a method that does not fit. Not cheap on the evidence.
- `NOT_APPLICABLE` — a rank or momentum basket where there is no fair value to check; say whether the
  cheapness ranking itself looks right.
- `CANNOT_CHECK` — primary sources not found. Say what is missing.

`cause` is required for `OVERSTATED` and `ARTIFACT`, one of: `currency_mismatch`, `share_count`,
`corporate_action`, `one_off_earnings`, `cyclical_peak`, `method_does_not_fit`, `debt_not_deducted`,
`stale_financials`, `growth_assumption`, `data_error_other`.

`overall` is the worst verdict among the name's valuation baskets. `own_margin_of_safety` is
`1 - live_price / midpoint of your range`, and may be negative. `confidence` is `high`, `medium` or `low`.

## When you finish (or stop)

1. `BASKETS_CHECK.json` in the folder root: `{"screen_date", "finished_on", "checked": [...],
   "not_reached": [...], "by_verdict": {...}, "by_basket": {"epv": {"HOLDS": n, "OVERSTATED": n,
   "ARTIFACT": n, ...}, ...}, "by_cause": {...}}`.
2. `BASKETS_CHECK.md`, one page, in plain language:
   - how many names hold, are overstated, are artifacts;
   - which baskets are most and least reliable, with the counts;
   - the three most common causes, each with two example names and the number that was wrong;
   - the 15 names whose discount holds best on your own numbers, with your range beside the screen's;
   - anything in `baskets.json` itself that looks broken (for example a whole exchange priced in the
     wrong currency).

State counts as counts. Do not round a doubtful name up to `HOLDS`.
