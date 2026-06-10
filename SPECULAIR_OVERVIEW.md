# Speculair — What We Built, in Plain English

*(as of 2026-06-10; written for a reader who has never seen the code)*

## What this is

An automated investing research desk with **two product lines**. The first: a **nightly screening machine** scans thousands of global stocks for cheapness and quality, and a **weekly AI "investment committee"** argues — in writing — about the survivors, producing **three tracked model portfolios ("books")**. The second: **Catalyst Watch**, an event-driven board that hunts *dated corporate events* (deals, spinoffs, forced sellers, regulatory rulings) across ~3,000 names, plus its own paper-traded sleeve (**Basket 13**) that bridges the two worlds. Everything publishes to the website with honest, live track records. No human picks stocks; humans pick the *rules*, and the rules are written down.

## The heartbeat (when things happen)

| Rhythm | Where it runs | What it does |
|---|---|---|
| **Nightly** (~00:00 Amsterdam) | Google Cloud (the screener job) | Re-screens ~2,500+ global stocks through **12 valuation methodologies**, refreshes the candidate baskets, and **re-prices every book** so the track-record charts move daily. The nightly job never changes an opinion — it only re-measures prices. |
| **Weekly** (Sunday 01:00) | **Locally, on Claude Code** | The full **re-debate**: every candidate gets a fresh multi-agent argument, the Directors re-pick the books, and everything republishes. Opinions change only here. |
| **Bi-weekly** (Mondays, 14-day floor) | Locally | **Catalyst Watch full refresh**: re-investigate the market **regime** (rates, the M&A window, the credit cycle — written to a living doc every debate reads), then re-sweep ~3,000 names through the 3-tier event hunt → a fresh ~231-name board → enriched and pushed to the site after a human go-ahead. |
| **Monthly** | Locally | The disruptor **theme universe rebuilds from scratch**; a **control sample** (8 random stocks that made *no* basket) gets debated to estimate what the funnel misses; expired exclusions earn a fresh full hearing (8 weeks or a new earnings report, whichever first). |
| **Quarterly** | Locally | Basket-13's **calibration loop**: entry gates, lane tilts, and sizing dials get re-fit against *realized* event outcomes from its append-only tracker. |

## How ~2,500 stocks become ~10 (the funnel)

1. **The scan** (nightly): ~2,500+ stocks scored by 12 independent valuation methods — discounted cash flow, earnings power, Graham-style, owner earnings, acquirer's multiple, gross profitability, a true EV/gross-profit multiple, and friends. Each method keeps its own ~20-name basket. Combined: a raw shelf of roughly **160 unique candidates**.
2. **The rule that keeps it honest**: every week re-screens **from scratch**. We learned the hard way that feeding the debate "last week's survivors" makes the universe shrink until it's debating its own echo.
3. **The debate** (weekly): all ~160 get the full multi-agent treatment (below). Names with no English transcript get a web-research agent instead of being skipped.
4. **The Directors** pick ~10 per book, under hard caps: max 3 per sector, and max 3 per *hidden* factor (e.g. "these two both live off the advertising cycle" — things sector labels miss).

The **Disruptor** variant has its own funnel: 459 screened across 7 secular themes → 154 pass the **profitability gates** → 40 debated. The gates in plain terms: the company must *actually make cash today* (or be one quarter from it), must be *genuinely growing* (≥15%/yr or accelerating), and must be able to *pay its debts* — measured on real borrowed money only, so a payments company holding customer float isn't mistaken for a leveraged one. Pre-profit moonshots (SMR developers, pre-revenue space) are excluded **by design**; they belong on the themes page, not in a "profitable disruptors" book.

## The committee (who argues, and on which AI)

- **Radar** *(Sonnet — the inexpensive model, used for sorting)*: finds each company's **true competitors** — by business model, not stock-exchange label — even competitors outside our universe, and writes a per-stock peer file (who the peers are, where the stock ranks against them on valuation/growth/margins/momentum, and a cheap / in-line / rich verdict). **That file actively grades the pick downstream at four points**: the Architect prices the sum-of-parts off the *peers'* multiples; the CRO sanity-checks the implied multiple against the peer set before settling fair value; the Value rubric's fourth pillar is literally "cheap vs TRUE peers"; and the Directors read the full peer map for the relative-value picture. (The same peers power the "similar stocks" section on each stock page.)
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
- **The shelf**: the 12 methodology baskets feed the debates and are tracked themselves.

Each book has its **own** live-forward NAV. They are never blended, and never back-filled — the chart starts the day the book went live, wins and losses included.

## Catalyst Watch + Basket 13 (the event-driven product line)

A different hunt with a different clock. While the books ask *"what is this worth?"*, Catalyst Watch asks *"what dated event will force the market to re-price this — and is the trade mispriced?"* Its one commandment: **score ≠ edge** — how *dense* the catalysts are is not the same as whether the price is wrong.

- **The board**: a 3-tier AI sweep over ~3,000 names — a wide scan, a deep read of the survivors, then a **skeptic tier that kills 40–50% of the "active" flags** — produces a ~231-name board. A deterministic layer then computes each name's risk/reward by lane (sum-of-parts, recovery, capital-return, merger-spread, binary), sanity-reconciles the valuations, caps thin-edge names, and prices everything live. An **options layer** confirms which trades have a sane defined-risk expression. The board lives on the site's Signals page with priorities, tooltips, and edge grades.
- **The regime layer**: a living document (refreshed bi-weekly) records whether the fat lanes are actually *open right now* — is anyone spinning off, are regulators forcing sales, is the M&A window alive — with tripwires that would change the tilt. **Every weekly debate reads it**, so the books and the board share one view of the world.
- **Basket 13 — the catalyst sleeve** (paper-traded): the bridge from board to portfolio. The board's best names (active, real edge, dated milestone within ~6 months, no blocking flags — about 9 entries + 20 staging from 231) get a **two-phase Fable debate** that judges *only the trade* — the Catalyst-CRO is explicitly **forbidden** from attacking value or quality, because a catalyst name is *supposed* to look bad on those. A Director then sizes under hard, code-enforced caps (8–12 names, ≤2 per resolution driver, ≤40% per super-cluster, ≤1.5% NAV at risk to the floor per name, binaries defined-risk only). Every entry lands in an **append-only tracker with event-resolution semantics** — positions resolve when the *event* resolves, not just on price — and **non-selections are recorded too**, so the quarterly calibration loop can learn from the road not taken. Paper only; any broker access is read-only.
- **The bridge to the books**: the Apex Director sees the sleeve's names as *context with hard exclusion rules* (never a binary-probability name, never a low-edge grade, never a blocked flag) — information, not automatic candidates — and a constraint test runs after every apex re-pick to prove it.

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
- (Basket 13) Place a live order — paper only, broker access read-only; mutate the board's scores; skip a resolution (every entry must eventually resolve, and non-selections are stamped); or let the debate judge the *event's reality* — the skeptic tier upstream already settled that, so the sleeve debate may only judge the *trade*.
