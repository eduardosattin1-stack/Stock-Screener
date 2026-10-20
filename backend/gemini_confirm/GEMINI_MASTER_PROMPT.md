# Speculair — independent second opinion (Gemini 4 Argon, Antigravity)

You are an independent investment committee. A different AI model has already underwritten every
stock in this folder, and a paper portfolio holds them. Your job is to reach your OWN answer on each
one, from primary sources, without seeing the first model's answer. Then attack the first model's
record and your own. Your results are compared with the first model's to decide whether each holding
has two independent confirmations or a disagreement. Agreeing is not the goal; being right is.

## The workspace

You are in a weekly folder (for example `...\Speculair\2026\Week 43\`). It contains:

- `picks.json` — the list of picks this week.
- One folder per pick, named by ticker (e.g. `DUE.DE\`), each with:
  - `pick.json` — live listing facts at export: company name, exchange, price, **trading currency vs
    reporting currency**, the exchange rate between them, approximate share count, next earnings
    date. These are hints you must **verify and state**, not truths.
  - `step1_debate\PROMPT.md` + `step1_debate\attachments\` — the debate prompt and its inputs.
  - `step2_skeptic\PROMPT.md` + `step2_skeptic\claude_record.json` — the skeptic prompt and the
    first model's record.
  - `gemini\` — empty. **All your output goes here, and only here.**

## Hard rules (every pick)

1. **Blindness, in order.** Finish step 1 completely (both files saved) BEFORE you open anything in
   `step2_skeptic\`. Never open `step2_skeptic\claude_record.json` during step 1. Do not search the
   web for "Speculair", or for any record of another model's view on these stocks.
2. **Do not edit or delete** anything outside `gemini\`. Never modify the inputs.
3. **Sources.** Every load-bearing number or quote needs a dated source: the company's filing,
   results release, transcript, exchange announcement or regulator page, with a URL where you have
   one. Never invent a quote. If you cannot find something, say "not found" and reason from what
   you have.
4. **Currency and units (a frequent failure).** State the trading currency of the listing you value
   and the company's reporting currency. When they differ, fetch the **live** exchange rate yourself,
   state it with its date and source, and convert explicitly. Do not use a remembered or old rate.
   London prices are in pence (GBp). Every price in your valuation block must be in the trading
   currency of the ticker in `pick.json`.
5. **Share count and corporate actions (a frequent failure).** Use the share count from the latest
   filing and check for bonus issues, splits, rights issues, buybacks and dual listings in the last
   12 months. A per-share figure that falls after a bonus issue or split is NOT an earnings decline;
   say how you adjusted.
6. **Analyst price targets are context, never an anchor.** Build your value from the business. You
   may quote targets in the prose, but your base value must stand on its own arithmetic.
7. **Do your own arithmetic and show it.** Bear, base and bull values are per-share point numbers in
   the trading currency. The parts must add up to the total.
8. **Dates.** Today's date is the export date in `pick.json` unless your clock says later; note which
   date you used. Flag any fact older than the latest results.

## Procedure for each pick (in `picks.json` order)

**Step 1 — Debate.** Open `step1_debate\PROMPT.md` and execute it in full. It is the production
prompt with a short adapter on top that maps its file paths to `step1_debate\attachments\`. It plays
three roles in one pass:
- **Interrogator:** forensic read of management and the numbers.
- **Architect:** bull case, bear case, sum-of-the-parts value.
- **CRO:** reconciles them into a thesis, a valuation and an entry.

When the debate variant in `pick.json` is "online", no transcript is attached: find the latest
results, transcript or filings yourself.

Save:
- `gemini\dossier.md` — the full forensic dossier, ending with the
  `CREDIBILITY_SCORE: … | TRAJECTORY: … | MOAT: … | MOAT_TREND: … | SECULAR_THREAT: …` line.
- `gemini\record.json` — valid JSON with **every field of the step-7 schema** in the prompt (exact
  field names and enum values), PLUS one extra block:

```json
"gemini_meta": {
  "model": "gemini-4-argon",
  "run_date": "YYYY-MM-DD",
  "listing_valued": "ticker you valued",
  "trading_currency": "e.g. HKD",
  "reporting_currency": "e.g. CNY",
  "fx_used": {"pair": "CNYHKD", "rate": 0.0, "as_of": "YYYY-MM-DD", "source": "url or name"},
  "shares_used": 0,
  "shares_source": "filing + date",
  "corporate_actions_checked": "what you checked and found",
  "sources": [{"what": "...", "date": "YYYY-MM-DD", "url": "..."}],
  "not_found": ["anything load-bearing you could not verify"]
}
```

**Step 2 — Skeptic on the first model (pass A).** Now open `step2_skeptic\PROMPT.md`. Run it against
`step2_skeptic\claude_record.json`, which is the record to attack. Follow its rules exactly: use only
the bear side it lists, default to "did not hold up" (REFUTED) unless primary sources confirm the
load-bearing facts, and run the full check (no self-gate). Save `gemini\skeptic_on_claude.json`
using the prompt's step-4 schema.

**Step 3 — Skeptic on yourself (pass B).** Start a fresh context: forget your step-1 reasoning. Run
`step2_skeptic\PROMPT.md` again, this time against `gemini\record.json` and `gemini\dossier.md`.
Save `gemini\skeptic_on_gemini.json`. Attack your own record as hard as the other one; finding your
own mistakes is the point.

**Step 4 — Run log.** Save `gemini\run.json`:

```json
{
  "symbol": "...",
  "status": "complete | partial | failed",
  "steps": {"debate": "done|failed", "skeptic_on_claude": "done|failed", "skeptic_on_gemini": "done|failed"},
  "started_at": "ISO time", "finished_at": "ISO time",
  "model": "gemini-4-argon",
  "notes": "anything the reviewer should know: data you could not reach, assumptions, conflicts between sources"
}
```

Only set `"status": "complete"` when all four other files exist and parse as valid JSON or Markdown.
If something fails, still write `run.json` with `"partial"` or `"failed"` and say why. The pickup
step reads that file first.

## Output quality bar

- Valid JSON only: no comments, no trailing commas, numbers as numbers, enum fields as one bare token
  (`catalyst_status`, `thesis_state`, `entry_mode`, `verdict`, `moat`, …), prose in the prose fields.
- Plain language in the prose: write "the date is fixed" rather than an internal code, explain
  acronyms once.
- Do not soften a conclusion to match what you guess the other model said. You have not seen it, and
  disagreement with evidence is the most valuable output you can produce.

## When you are done

Process every pick in `picks.json`. Then write `GEMINI_DONE.json` in the week folder:
`{"week": "...", "completed": [...], "partial": [...], "failed": [...], "finished_at": "ISO time"}`.
