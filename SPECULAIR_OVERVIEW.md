# Speculair — What We Built, in Plain English

*(as of 2026-06-10; written for a reader who has never seen the code)*

## What this is

An automated investing research desk. A **nightly screening machine** scans thousands of global stocks for cheapness and quality; a **weekly AI "investment committee"** argues — in writing — about the survivors; and the result is **three tracked model portfolios ("books")** published to the website with honest, live track records. No human picks stocks; humans pick the *rules*, and the rules are written down.

## The heartbeat (when things happen)

| Rhythm | Where it runs | What it does |
|---|---|---|
| **Nightly** (~00:00 Amsterdam) | Google Cloud (the screener job) | Re-screens ~2,500+ global stocks through **12 valuation methodologies**, refreshes the candidate baskets, and **re-prices every book** so the track-record charts move daily. The nightly job never changes an opinion — it only re-measures prices. |
| **Weekly** (Sunday 01:00) | **Locally, on Claude Code** | The full **re-debate**: every candidate gets a fresh multi-agent argument, the Directors re-pick the books, and everything republishes. Opinions change only here. |
| **Monthly** | Locally | The disruptor **theme universe rebuilds from scratch**; a **control sample** (8 random stocks that made *no* basket) gets debated to estimate what the funnel misses; expired exclusions earn a fresh full hearing (8 weeks or a new earnings report, whichever first). |

## How ~2,500 stocks become ~10 (the funnel)

1. **The scan** (nightly): ~2,500+ stocks scored by 12 independent valuation methods — discounted cash flow, earnings power, Graham-style, owner earnings, acquirer's multiple, gross profitability, a true EV/gross-profit multiple, and friends. Each method keeps its own ~20-name basket. Combined: a raw shelf of roughly **160 unique candidates**.
2. **The rule that keeps it honest**: every week re-screens **from scratch**. We learned the hard way that feeding the debate "last week's survivors" makes the universe shrink until it's debating its own echo.
3. **The debate** (weekly): all ~160 get the full multi-agent treatment (below). Names with no English transcript get a web-research agent instead of being skipped.
4. **The Directors** pick ~10 per book, under hard caps: max 3 per sector, and max 3 per *hidden* factor (e.g. "these two both live off the advertising cycle" — things sector labels miss).

The **Disruptor** variant has its own funnel: 459 screened across 7 secular themes → 154 pass the **profitability gates** → 40 debated. The gates in plain terms: the company must *actually make cash today* (or be one quarter from it), must be *genuinely growing* (≥15%/yr or accelerating), and must be able to *pay its debts* — measured on real borrowed money only, so a payments company holding customer float isn't mistaken for a leveraged one. Pre-profit moonshots (SMR developers, pre-revenue space) are excluded **by design**; they belong on the themes page, not in a "profitable disruptors" book.

## The committee (who argues, and on which AI)

- **Radar** *(Sonnet — the inexpensive model, used for sorting)*: finds each company's **true competitors** — by business model, not stock-exchange label — even competitors outside our universe.
- **Interrogator** *(Opus)*: the forensic accountant. Reads filings and transcripts looking for red flags; issues a **credibility score 1–5**. A 2 or below is a **ban from every book** — no cheapness overrides it. A *missing* score now fails closed (treated as suspect), never silently neutral.
- **Architect** *(Opus)*: writes the strongest **bull case and bear case**, and prices the company by its **parts** (sum-of-parts: each division valued like its real peers, debts subtracted — never a liability dressed up as "net cash").
- **Catalyst check** *(live web)*: did the news already happen? A catalyst that already **FIRED** is spent fuel, not upside.
- **CRO (the referee)** *(Opus)*: reconciles bull vs bear into **one fair value** and **two scores** — a catalyst-aware conviction *and* a catalyst-blind **value conviction** — so a great-value/no-news stock and a hot-news/full-price stock stop getting the same grade.
- **Skeptic** *(Fable — the strongest model, used for judging)*: a separate agent whose **only job is to kill finalists**. It sees only the bear case plus the live web, defaults to REFUTED, and a refuted name is **demoted — no appeal**.
- **Directors** *(Fable)*: pick each book, run the correlation stress, and must write a **one-sentence bear case for every pick** before sizing — if you can't state why you're wrong, you don't understand the position.

## The three books (plus the shelf)

- 🟢 **Apex** — the catalyst/event-driven book: special situations with a reason to re-rate, tilted by the current market regime.
- 🔵 **Value Lens** — the *same debate* re-graded with catalysts ignored: pure cheapness with a deterministic safety layer on top — shaky legs (only one model says cheap, or the fair value predates a big corporate event) are **auto-half-sized**; pair correlations are **measured from two years of prices**, not asserted; a **worst-case drawdown number** is published on the card; and an honest banner says what the pool really is ("best-of-B: zero A-grades in 161 names — expect slow grinding, not fireworks").
- 🟣 **Disruptor Lens** — built, debates begin on a weekend run: the profitable picks-and-shovels of secular themes (AI infrastructure, energy transition, robotics, bio tools, defense tech, fintech rails, space).
- **The shelf**: the 12 methodology baskets feed the debates and are tracked themselves. **Basket-13** (the Catalyst Watch sleeve, built in a parallel session) feeds the Director as *context with hard exclusion rules* — its names are information, not automatic candidates.

Each book has its **own** live-forward NAV. They are never blended, and never back-filled — the chart starts the day the book went live, wins and losses included.

## From a laptop to the website

The trick: **the website never talks to the laptop.** Claude Code runs the weekly debates locally → writes plain JSON files → pushes them to Google Cloud Storage. The website (Vercel) reads those files live, with a public fallback. The nightly cloud job re-prices the same files. So a pipeline that runs on a desk at home publishes to a site that's always up — and every stock page keeps a **dated dropdown of every past debate**, so you can read what the committee thought three weeks ago versus today.

## The honesty rails (what the system may NOT do)

- Re-debate from curated survivors (the universe always re-screens from scratch).
- Count an already-fired catalyst as upside.
- Full-size a position only one valuation model believes in.
- Fail open on a missing credibility score.
- Use the scan's headline cheapness as a *ranking* — we measure this weekly, and it isn't one (it's a membership filter; the debate's normalized fair value is the system of record).
- Blend the books' track records, or back-fill them.
- Let code add or remove picks. Membership belongs to the Directors; deterministic code only **sizes, stamps, and caps** — with exactly two sanctioned exceptions: the global forensic ban, and the Skeptic's demotion.
