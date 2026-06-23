# Catalyst Watch — Market Regime & Operating Environment

**Status:** Living document · regenerated monthly (8th, from 2026-06-08) · companion to [CATALYST_SCORING_REBUILD.md](CATALYST_SCORING_REBUILD.md)
**Baseline:** 2026-06-05 (4-agent investigation, live-verified) · **Version:** v1
**Relationship:** [CATALYST_SCORING_REBUILD.md](CATALYST_SCORING_REBUILD.md) decides the *structure* (gate, tilt, window, sizing) on first principles. **This doc supplies the time-varying evidence that the structure is right _now_, and the tripwires that would change it.** The scoring methodology is stable; the regime read is perishable — hence the monthly cadence.

---

## §0 — Why this layer exists

The scoring doc's §1.4 tilts the universe to multi-domain special-sits in thin-coverage names, deprioritizing hard-binary/PDUFA. That is asserted on *first principles* (edge stacks where coverage is thin). A first-principles tilt is necessary but not sufficient: **whether the fattest lane is actually open, and how mispriced events actually are, depends on the regime** — rates, the M&A/regulatory window, the credit/distressed cycle, positioning. A spinoff tilt is worthless if no one is spinning; a forced-seller tilt needs regulators actually forcing sales.

So this doc does three things:
1. **Reads the regime** through four fixed lenses (§2) and maps each finding to the four Catalyst Watch decisions (§3).
2. **Records the dated evidence** that backs (or would flip) the tilt — this month's instance in §4, prior instances appended below it.
3. **Names the tripwires** (§5) — the specific, observable conditions that would change each decision — so the tilt is held *conditionally*, not on faith.

**Core stance: edge is perishable; so is the regime that creates it.** Re-run the investigation monthly, diff against last month, and act only on what actually moved.

---

## §1 — How regime maps to the four decisions

The four calls from the methodology, and the regime input that governs each:

| Decision (scoring doc) | Regime input that governs it | This is "open"/favorable when… |
|---|---|---|
| **#1 Anchor = catalyst, convergence multiplies** (§1.3, §1.6) | *Structural — does not flex with regime.* | Always. The regime can't make a narrative a catalyst. |
| **#2 Hunting ground / universe tilt** (§1.4) | M&A volume, antitrust window, spinoff supply, distressed cycle, activism pace, lane efficiency | Deal machine hot **and** regulators permissive **and** distress rising **and** PDUFA still crowded → tilt structural-special-sits. |
| **#3 Window & expression** (§1.5) | Rate path, deal-financing availability, how slow-burn the live supply is | Higher-for-longer + 6–18mo structural supply → tier the window, match expiry to catalyst date with margin. |
| **#4 Sizing / book independence** (§1.7) | Positioning extremes, factor concentration, the dominant shared macro driver | Stretched positioning + one dominant macro factor (AI-capex, oil) → enforce resolution-driver independence hard. |

**#1 is regime-invariant — never relax it.** #2/#3/#4 are regime-conditional and are what this doc keeps honest.

---

## §2 — Investigation protocol (reproducible — this is what the monthly task re-runs)

Run **four parallel research agents** (`general-purpose`), each told: *today's date; your training is stale, verify everything live; use WebSearch/WebFetch + load the FMP market-data MCP tools via ToolSearch; cite source + date; lead with a BLUF; end with "Implications for Catalyst Watch" + "Confidence & gaps."* The four briefs:

- **Agent A — Macro regime & sentiment (now):** equity level & valuation; volatility regime (VIX, any stress episode); rates & curve + priced Fed path; inflation & growth; credit spreads (IG/HY); breadth & positioning (Mag-7 concentration, BofA FMS cash, AAII, put/call, Fear & Greed). → risk-on/off, cycle stage, complacent/fearful; what it means for how mispriced near-term catalysts are and the market's willingness to re-rate.
- **Agent B — Forward outlook 2026/2027:** strategist S&P targets (YE-2026 + 2027), EPS-growth consensus, GDP/rate path, recession probability; swing factors (fiscal/Treasury supply, tariffs, AI-capex durability, geopolitics, US midterms); bull/base/bear. → does the *expected* regime favor more deal-making/forced realizations, and which macro waves spawn single-name catalysts.
- **Agent C — M&A & deal environment:** M&A volume (2025 actual, current-YTD, forecast); financing conditions (LBO debt, private credit, HY/loan issuance); antitrust posture (FTC/DOJ + EU/UK — permissive vs restrictive, forced-divestiture trend); PE dry powder & exit pressure; IPO/SPAC window; hot sectors. → is the deal/merger-arb/forced-seller lane fertile, and which deal types flow.
- **Agent D — Special-situations lane ranking:** for each of {activism, spinoffs, distressed, forced-sellers, merger-arb, hard-binary/biotech} assess activity level **and** pricing efficiency; rank fattest→thinnest edge for an LLM-breadth, convergence strategy. → where to tilt, what to de-emphasize.

**Synthesis step:** reconcile A–D, then update §4 (new dated instance), §3 (action mapping), §5 (tripwire check), and the change log. Diff against the prior instance and report what moved.

---

## §3 — Regime → action mapping (current, from the 2026-06-05 read)

**Verdict: the regime confirms the scoring doc's tilt — build it, tilt structural, respect book independence — but the window is good, not infinitely open.**

- **#2 Universe tilt — CONFIRMED, structural-special-sits.** Two independent agents converged on the same lane ranking the scoring doc already encodes; the hard-binary/PDUFA "thinnest edge" prior was independently validated. No change to §1.4. *Catalyst supply is abundant and structural (multi-year), not a flash.*
- **#3 Window — CONFIRMED two-tier.** Higher-for-longer (Fed on hold to ~Dec, inflation re-accelerating) + the fattest live supply being 6–18mo (spins, restructurings, divestiture clocks) backs the §1.5 tiered window over a 0–90d screen. *Macro raises the stakes on expression: avoid theses that need a Fed cut to work.*
- **#4 Sizing — CONFIRMED, independence is not academic.** BofA FMS cash 3.9% (sell-signal) + 50% net OW equities + Mag-7 ~30% of the index = little dry powder to absorb a shock; a single dominant factor (AI-capex) under the tape. Enforce §1.7 resolution-driver independence at the book level.

**New hooks this read surfaced (candidates for the universe layer / §1.4 lanes):**
1. **Russell reconstitution goes semi-annual in 2026** (June + December) — a new, twice-a-year mechanical forced-seller/buyer calendar. Hard-code both windows.
2. **Mega-IPO fast-track index inclusion** (SpaceX/OpenAI/Anthropic pipeline; new 15-trading-day Nasdaq rule) → $15–30B of mechanical index buying per event. A clean forced-flow lane; map the *displaced* names too.
3. **$1.2T 2026–2029 leveraged maturity wall** is the *supply engine* for the distressed lane — wire refinancing-wall + LME (liability-management) detection as a primary screen for the fattest lane.
4. **Nov-2026 midterms = a dated "window-narrowing" overlay** on every M&A-dependent thesis — the open-regulator tailwind may be widest in H1-2026 (see §5).

**The one tension to hold:** distressed is the *fattest* lane **and** the most macro-exposed — higher-for-longer is what creates the supply *and* what can break the balance sheet. Resolution: play the **catalyst** (restructuring terms, fulcrum security, emergence equity), never a "rates will rescue it" bet. Fattest ≠ easiest; it is fattest *because* it is hardest and least-covered — which is exactly where the breadth edge pays.

---

## §4 — Current read

### 2026-06-05 — baseline (v1) · *live-verified; analyst training cutoff was ~Jan-2026, so the items below were confirmed against June-2026 sources, not priors*

**One-liner:** *Late-cycle, fully-invested, low-vol melt-up sitting on top of an unresolved oil/inflation shock — a complacent tape over a live tail, with an unusually open M&A/regulatory window that may narrow after the November midterms.*

**A. Macro regime now (risk-ON, recovery-flavored, complacent over a live tail)**
- S&P 500 **7,584 (+10.8% YTD)**, Nasdaq **+15.4%**, both ~0.5% off all-time highs — but a *recovery* high after a Q1 ~7.4% "Iran war" correction (VIX spiked ~26 on Apr 7, since collapsed to **15.8**). *(FMP live, 2026-06-05.)*
- Inflation **re-accelerated to 3.8% YoY** (April CPI, core 2.8%) on an energy shock (war with Iran / Strait of Hormuz; WTI ~$92 vs $75 200-dma). Fed **on hold 3.50–3.75%**, first cut not priced until ~December. *(BLS 2026-05-12; CME FedWatch.)*
- Growth/labor resilient: unemployment **4.3%**, May payrolls **+172k** vs +80k cons. Credit **tight** (HY ~285bp), no stress. *(BLS 2026-06-05; ICE BofA.)*
- Positioning **stretched-bullish**: BofA FMS cash **3.9%** (<4% = contrarian sell signal), **50% net OW** equities; retail not euphoric (AAII bulls 35.6%); F&G 54 (Neutral); Mag-7 ~30% of S&P but breadth broadening. *(BofA FMS May; AAII; CNN.)*

**B. Forward 2026/2027 (constructive but maturing — earnings carry it, multiples don't)**
- Strategist YE-2026 targets ~**7,600–8,100** (Goldman 8,000, JPM 7,600; bears Stifel/BofA 7,000–7,100) → mid-single-digit upside, bulls +8–10%. No recession base case (est. range 17% market-implied → 42% Moody's). *(Bank outlooks, Dec-25→H1-26.)*
- **AI capex is the load-bearing wall:** ~$725B in 2026 (+77% YoY), ~40% of 2026 S&P EPS growth — continuing, not digesting; the dominant two-sided risk.
- Dated macro risks: **Feb-2026 SCOTUS struck down IEEPA tariffs** → §122/§232/§301 scramble + $200B refund question; ~$1.9T deficit / heavy Treasury supply; **Nov-2026 midterms** (Democrats favored to take the House → divided government, revived antitrust scrutiny).

**C. M&A & deal environment (HOT and structural — the regulatory window is the key change)**
- 2025 M&A **~$4.5–4.8T (+36% YoY, 2nd-highest ever)**; **record Q1-2026 (~$1.2T)**; 2026 forecast +8% US deal volume. K-shaped — mega-cap-led (68 deals ≥$10bn, all-time high), deal *count* flat-to-down, mid-market financing tightening. *(Bain/LSEG/EY-Parthenon.)*
- **US regulatory window OPEN** — Ferguson FTC / Slater→Assefi DOJ are remedy-friendly, predictable, faster (2025: 12 challenges, **9 settled via consent**, not blocked). The single biggest change vs. the Khan era. EU/UK also more deal-friendly (UK CMA "4Ps"). *(Multiple law-firm reviews, 2025–26.)*
- **Forced-seller archetype is LIVE:** EU-mandated Prosus sell-down of its ~27% Delivery Hero stake (the DHER template), blocks dumped through 2026. PE dry powder record ~$1.7T with deploy-or-return pressure; IPO/SPAC window reopening. Tech/AI the dominant deal sector.

**D. Special-situations lane ranking (fattest → thinnest edge)**

| Rank | Lane | State | Edge |
|---|---|---|---|
| 1 | **Distressed / restructuring** | Ch11 **+37% YoY** Q1-26; "extend & pretend → resolve or reset"; LMEs/creditor fights | **Fattest** — messiest, most document-heavy, least covered |
| 2 | **Spinoffs / split-offs** | Elevated, *dated* pipeline (Honeywell 3-way, WBD, J&J/DePuy, Eaton, GPC, Textron…) | **Fat** — underfollowed stubs; "read the Form 10" edge |
| 3 | **Forced sellers** | Antitrust divestitures (Google/AdX) + double Russell recon 2026 | **Good (lumpy)** — mechanical, price-insensitive |
| 4 | **Activism** | Record 255 campaigns 2025, 61% M&A-themed; fast settlements (~16.5d) | **Feeder, not terminal** — source breakup/sale theses upstream |
| 5 | **Merger-arb (mega-cap)** | Spreads tight, breaks rare (open regulator) | **Thin/compressing** — capital-crowded |
| 6 | **Hard-binary / biotech PDUFA** | Dense calendar (52 Ph-3 in Q2-26) | **Thinnest** — run-up priced 4–8wks ahead; *both agents independently confirmed* |

---

## §5 — Tripwires (what would change the call)

Hold the tilt *conditionally*. Each monthly run checks these; a breach is a methodology event, not a footnote.

| Tripwire | Observable | If breached → |
|---|---|---|
| **Regulatory window closes** | FTC/DOJ leadership change (Assefi is *acting*); HSR friction revives; **midterms flip the House (Nov-2026)** → antitrust hearings | M&A/forced-seller lane fertility drops; lengthen expected deal timelines, widen merger-arb break assumptions, shift weight toward spins/distressed (less politically exposed) |
| **Oil/Hormuz re-escalation** | WTI breaks higher, VIX re-spikes toward 26 (the Apr precedent: 0→26 in days) | Forced-seller/dislocation window *opens* — deploy dry powder into catalyst names orthogonal to oil; but de-risk anything mid-event in oil-sensitive sectors |
| **AI-capex break** | A hyperscaler capex guide-down or monetization scare (it is ~40% of 2026 EPS growth) | Broad de-grossing risk → tighten book independence (§1.7); the dominant shared factor would dominate everything |
| **Credit cracks** | HY OAS widening off ~285bp; the $1.2T maturity wall starts defaulting hard | Distressed lane gets *fatter* but riskier — raise the bar on balance-sheet quality for non-distressed theses; favor fulcrum/post-reorg expressions |
| **PDUFA lane dislocates** | Evidence binary events stop being efficiently priced (a vol/dispersion regime shift in biotech) | Re-examine the §1.4 deprioritization of hard-binary — currently the firmest "thin edge" prior |

---

## §6 — Cadence & change log

**Schedule:** **bi-weekly on Mondays, ~09:07 local** — the cron fires every Monday but the task self-gates to a ≥13-day floor since the most recent run below, so it runs every *other* Monday. As of 2026-06-09 the task does the **full refresh**: §2 regime protocol → full 3-tier board re-sweep → enrich → commit on `ux-revamp` (the production push is a separate gated approval; see CATALYST_WATCH_METHODOLOGY.md §10). It appends a new §4 instance, refreshes §3/§5, and adds a row below. Durable scheduled task `catalyst-watch-regime-refresh` (see `C:\Users\Bruno\.claude\scheduled-tasks\`).

| Run date | Regime one-liner | Tilt (#2) | Tripwires breached | Notable new catalysts/hooks |
|---|---|---|---|---|
| 2026-06-05 (baseline) | Complacent melt-up over a live oil/inflation tail; open M&A window, possibly narrowing post-midterms | Structural-special-sits (**confirmed**) | none | Russell semi-annual recon; mega-IPO index inclusion; maturity-wall→distressed engine; midterm overlay |

---

## Sources (baseline 2026-06-05)
Macro/sentiment: FMP live indices/VIX/Treasuries (2026-06-05); BLS CPI (May-12) & jobs (Jun-5); CME FedWatch; BofA Global Fund Manager Survey (May); AAII; CNN Fear & Greed. Forward: Goldman/JPM/Morgan Stanley/BofA/Stifel 2026 outlooks (Dec-25→H1-26); CBO/OMB deficit; Holland & Knight / PIIE / CFR (SCOTUS-IEEPA tariffs); Eurasia Group / CFR (geopolitics); Polymarket/270toWin (midterms). M&A: Bain & Co (Dec-2025), LSEG, EY-Parthenon (Jun-2026), S&P Global, PitchBook; Capitol Forum / Hogan Lovells / MWE (antitrust); Bloomberg/MLex (Prosus/Delivery Hero). Special-sits: Barclays/Cleary/Sidley (activism); Skadden / InsideArbitrage (spinoffs); Moody's/S&P/Fitch/US Courts/Epiq/ABI (distressed); NatLawReview/Wilson Sonsini/LSEG (forced sellers); AllianceBernstein/HFRI (merger-arb); BiopharmaWatch/CatalystAlert (biotech).

*Full agent transcripts for the baseline run live in the session that produced this doc (2026-06-05).*
