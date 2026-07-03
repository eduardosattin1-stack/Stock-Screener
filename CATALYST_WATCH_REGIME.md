# Catalyst Watch — Market Regime & Operating Environment

**Status:** Living document · regenerated bi-weekly · companion to [CATALYST_SCORING_REBUILD.md](CATALYST_SCORING_REBUILD.md)
**Last run:** 2026-07-01 (manual, user-ordered; 4-agent investigation + first cross-model verification pass) · **Version:** v3
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

**Verification step (added 2026-06-30):** before synthesis, run **five parallel Fable verifier agents** — cross-model on purpose (a different model re-deriving from independent sources catches what same-model review confirms). Four per-brief refuters re-verify every load-bearing figure live from *different* sources than cited, returning CONFIRMED / CORRECTED / UNVERIFIABLE per figure plus anything the brief missed. A fifth **tripwire auditor** gets only the §5 observables (not the researchers' conclusions) and independently calls breached/not-breached per tripwire. Merge rules: CORRECTED wins (cite both sources); UNVERIFIABLE is dropped or tagged *(unverified)*, never presented as sourced fact; a tripwire status is written only where researcher and auditor agree — disagreement is written ⚠️ DISPUTED and reported at headline weight.

**Synthesis step:** reconcile the verified A–D, then update §4 (new dated instance), §3 (action mapping), §5 (tripwire check), and the change log. Diff against the prior instance and report what moved.

---

## §3 — Regime → action mapping (current, from the 2026-07-01 read)

**Verdict: tilt CONFIRMED structural-special-sits; spin/forced-seller convergence is the fattest it has been all year (three live index-orphan stubs, ADIG locked for Aug 4, first-ever December recon ahead); DOJ Antitrust is now LEADERLESS — merger-arb risk mutates from break-risk to extension/timing-risk; two near-dated macro binaries (Jul 24 tariff cliff, ~mid-Aug ceasefire expiry, late-July AI-capex earnings test) tighten the tier-1 window.**

- **#2 Universe tilt — CONFIRMED, structural-special-sits.** Forced-sellers + spinoffs are ONE integrated #1 trade this cycle: HONA (Jun 29) and MBGL (Jul 1, 87.5M-share day-one forced flow) index-orphan windows are open NOW, FDXF seasoning (19.9% FedEx retained stake = overhang, only 80.1% distributed), ADI/ADIG locked (record Jul 20 → distribution Aug 3 → regular-way Aug 4), and the first-ever second Russell recon lands December 2026. Activism #3 (136 H1 campaigns, "sell yourself" top demand at 21%). Distressed demoted to #4 — supply is *rolling over*, not rising (distress ratio down two straight months to 6.53%; realized LSTA payment default just 1.35%; the old "7.5%" was a Moody's LME-inclusive forecast artifact — see §5). Merger-arb #5 (crowded + leaderless-DOJ extension risk). PDUFA #6 — kept thinnest; researcher D's promotion of it to #2 was REFUTED by the verification pass (implied-move leg unverifiable, DOGE premise decaying as FDA rehires). No change to §1.4 direction.
- **#3 Window — CONFIRMED two-tier, with a compressed tier-1 calendar.** Warsh Fed hawkish hold (median YE-2026 dot 3.8%; futures ~77% odds of a hike BY December); GS no longer expects a 2026 cut (and gives only ~30% odds to its own 2027 two-cut path). Rate-cut theses stay dead. The fat supply (spins, divestiture clocks, restructurings) remains 6–18mo — but THREE dated near-term binaries now sit inside tier 1: **Jul 24** (Section 122 tariff statutory expiry — the tariff tripwire moved UP from November), **~mid-Aug** (US-Iran 60-day ceasefire clock), **late July** (hyperscaler Q2 earnings = the AI-capex/FCF-crossover test). Match expiries around those dates with margin.
- **#4 Sizing — CONFIRMED independence; the dispersion regime is the friendliest backdrop of the year.** Mag-7 flat (−0.2% YTD) vs equal-weight +11.4% — beta is dead, single names re-rate violently on events (Broadcom −14%/SOX −10.3% June 4–5; $1.3T semi drawdown June 23–25 on the "memory tax"). CNN F&G ~27 (Fear) vs AAII bulls 44.9% — sentiment is split, no crowded consensus. Enforce §1.7 independence hard around the ONE shared factor that could swamp everything: an AI-capex guide-down at late-July earnings.

**New hooks from the 2026-07-01 read:**
1. **Section 122 tariff cliff July 24, 2026** — the 10% global replacement tariff hits its 150-day statutory wall in ~3 weeks (and the CIT already struck it down May 7, on appeal); Congress must act or it lapses. Near-dated macro binary for any tariff-exposed thesis. (The old "November dual hard-date" is superseded: SCOTUS already killed IEEPA Feb 20; refunds are FLOWING — ~$85B of ~$166B by late May.)
2. **MBGL (Mobility Global, ex-S&P Global Mobility)** — regular-way NYSE July 1 (today), 87.5M-share forced-flow day one, ~2.6× net leverage; textbook index-orphan candidate.
3. **HONA window still open** (spun Jun 29, 1-for-2 + HON reverse split); **ADIG next**: Resideo board approved TODAY (Jul 1) — record Jul 20, distribution Aug 3, NYSE regular-way Aug 4; when-issued trading late July.
4. **KBR → Mission Technology Solutions SLIPPED to Jan 4, 2027** (announced Jun 25) — exits the H2-2026 window; re-date the B13 catalyst clock. L3Harris is a *carve-out IPO* of Missile Solutions (parent keeps control, Pentagon anchor) — NOT an index-orphan spin; don't model it as one.
5. **DOJ Antitrust leaderless** — Slater out Feb 12, Acting AAG Assefi out ~Jun 28 (second chief gone in five months); FCC GC Adam Candeub expected nominee, unconfirmed. Merger-arb consequence: EXTENSION risk (slower, politically unpredictable reviews), not classic break risk; note UniFirst/Cintas got an FTC Second Request Jun 11. WBD/Paramount-Skydance was DOJ-APPROVED Jun 12 — residual risk there is state AGs, not federal.
6. **US-Iran 60-day ceasefire clock expires ~mid-August** (MoU signed Jun 17; US airstrike Jun 26 after an alleged violation — more fragile than headline "ceasefire holding"). Oil itself is deflating (Brent ~$71, below GS's $80 YE call) — a disinflationary offset, and a re-escalation would be a forced-seller window opener per the tripwire playbook.
7. **Private credit is the real credit story** — Fitch "true" private-credit default rate 5.8% TTM (record); Proskauer 2.73% Q1 and rising (60% via PIK/deferral); peer BDC redemption requests up to ~17%. Public legs (HY 278bp, IG 76bp) remain priced-for-perfection. Watch for the first forced unwind — that's where the next distressed-lane supply comes from, not the (improving) BSL loan market.
8. **AI-capex Q2 earnings test, late July** (Alphabet ~Jul 22–28 first) — guides are still RISING ($725B intact; Meta raised to $145B) but capex is ~93% of hyperscaler OCF with the aggregate FCF crossover projected ~Q3 2026. A guide-down = tripwire #3 breach = de-gross signal.

**Tension resolved this run (verification layer, first exercise):** the prior read's "distressed lane fat, loan defaults 7.5% = 2× historical" was built on a Moody's LME-inclusive, partly-forecast, issuer-count series. Realized apples-to-apples (Morningstar LSTA, May 31): payment defaults 1.35% by amount, dual-track incl. LMEs 3.11% — and FALLING. Distressed demoted on facts, not fashion; the live credit risk migrated to private credit (hook #7).

---

## §4 — Current read

### 2026-07-01 — manual full run (v3) · *live-verified 4-agent investigation + FIRST RUN of the cross-model verification layer (4 Fable refuters + 1 blind tripwire auditor); figures below are post-merge (CORRECTED wins, unverifiable tagged)*

**One-liner:** *Dispersion regime — Warsh Fed hawkish (hike odds ~77% by Dec), Mag-7 flat vs equal-weight +11.4%, oil deflating (~$71 Brent) under a fragile ceasefire; DOJ Antitrust leaderless (extension not break risk); spin/forced-seller lane the fattest of the year (HONA + MBGL windows live, ADIG Aug 4, December recon ahead); three dated near-term binaries: Jul 24 tariff cliff, late-July AI-capex earnings, ~mid-Aug ceasefire clock.*

**Verification summary (first exercise of §2's verification step):** Brief A — highly reliable (all market/Fed/sentiment figures confirmed to the decimal; 2 corrections, 2 unverifiable). Brief B — anchors solid but systematically 2–4 weeks stale (7+ corrections, one MATERIAL: Section 122 effective Feb 24 not Jun 24 → expires **Jul 24, 2026**; Turnberry RATIFIED Jun 16, not frozen; Citi 8,100 / Wells 7,950 / Barclays 7,800 superseded; Senate = GOP-lean not coin-flip). Brief C — "trust the statistics, re-date the story" (SpaceX IPO already DONE Jun 11–12 at $75B; WBD DOJ-approved Jun 12; remedy list was 2025 mislabeled YTD; CLO $472B and "$1T 2028 wall" corrected to ~$202B record / ~$700B 2028). Brief D — high numerical fidelity, weaker situational awareness (DOJ chief already gone; KBR slipped to Jan 2027; UNF ticker garbled + binary already resolved; **PDUFA #2-fat promotion REFUTED** — implied-move leg unverifiable, DOGE premise decaying). Tripwire auditor (blind): **0 breached / 4 partial / 1 not breached.** No researcher-vs-auditor tripwire status DISPUTE after merge; the one genuine dispute (D's PDUFA lane rank) is judgment, resolved against D on evidentiary grounds and flagged in the run report.

**A. Macro regime now (dispersion regime — complacent on tails, fearful on the tape)**
- S&P 500 **7,485 (+9.3% YTD)**; **equal-weight RSP +11.4%** > cap-weight > **Mag-7 −0.2% (flat)** — leadership fully rotated out of mega-cap tech; Nasdaq +12.0%. Shiller CAPE ~40.4. *(FMP live 2026-07-01; verified to the decimal by refuter A.)*
- **Fed under Chair Kevin Warsh** (confirmed 54–45 May 13, sworn May 22 — narrowest-ever confirmation): hawkish hold 3.50–3.75% (Jun 17, 12-0); dot median YE-2026 3.8%; 9/18 project ≥1 hike; SEP 2026 PCE raised to 3.6%; futures ~**77% odds of a hike BY December** (from ~24% pre-FOMC). Warsh regime change: forward guidance eliminated, statement cut to 130 words. GS: no 2026 cut, two cuts Jun+Dec 2027 — at only ~30% self-assigned odds.
- Inflation re-accelerated: May PCE **4.1% headline / 3.4% core** (rel. Jun 25, hottest since Apr 2023) — but **GDPNow collapsed to 1.2% (Jul 1)** from 2.5%, and Brent ~$71 is a live disinflationary offset. Stagflation-lite; June jobs report Jul 2.
- Rates: 2Y 4.17 / 10Y 4.48 / 30Y 4.97; 2s10s +31bp, bear-steepening. VIX **16.6** (complacent; June 4–5 stress spike to 21.5 on Broadcom −14% / SOX −10.3% fully normalized).
- Credit: HY OAS **278bp** / IG **76bp** — cycle tights, priced for perfection. Realized BSL loan defaults LOW and improving (LSTA payment 1.35%, dual-track 3.11%, distress ratio 6.53% falling) — prior "7.5%" figure retired as a Moody's-forecast artifact. The live stress: **private credit** (Fitch true default 5.8% TTM record; Proskauer 2.73% rising; peer BDC redemptions to ~17%).
- Sentiment split: AAII bulls 44.9% (swung bullish) vs CNN F&G ~27 (Fear); BofA FMS June pared risk after May's triple contrarian sell signal (cash 3.9%, record equity-allocation jump). No consensus = no crowd to fade or join — single-name work decides.

**B. Forward 2026/2027 (earnings-only bull, cluster moved UP; three dated binaries)**
- YE-2026 target cluster now **7,800–8,100** (GS 8,000 May 26; Citi 8,100 Jun 8; JPM 7,800 Jun 24; MS 7,800; Wells 7,950 ~Jun 17; Barclays 7,800; bear anchor BofA 7,100). EPS 2026 ~$340 (+24%), 2027 ~$385; AI-infra ≈ half of 2026 EPS growth. No multiple expansion assumed anywhere.
- Recession odds: GS 15% (post-ceasefire), JPM 35% — wide uncertainty band. GDP ~2% H2 (but GDPNow 1.2% print Jul 1).
- **Tariff architecture (corrected)**: SCOTUS killed IEEPA Feb 20 (6-3); Section 122 10% global tariff effective Feb 24, **statutory expiry Jul 24, 2026** (CIT struck it down May 7, on appeal; 24 states suing). Refunds FLOWING (~$85B of ~$166B). **EU Turnberry RATIFIED** (EP Jun 16, 440–151; Council ~Jun 25) — EU-trade uncertainty largely cleared. The binding tariff binary is **Jul 24**, not November.
- AI capex: $725B 2026 intact and guides still rising (Meta to $145B) — but capex ≈93% of hyperscaler OCF, aggregate FCF crossover ~Q3 2026; **late-July Q2 earnings are the test**. June 23–25: $1.3T semi-complex drawdown ("memory tax", capex-to-revenue gap) — valuation crack without a fundamentals break, yet.
- Midterms: House lean-D (generic ballot D+7.2, markets ~56–61%); **Senate GOP-lean ~58%** (corrected from "coin-flip"). Divided-government base case; the Nov date remains the regulatory-window expiry marker.

**C. M&A & deal environment (fertility 4/5 — record H1; leaderless-DOJ overlay)**
- **H1 2026 record: ~$2.8T announced (+48% YoY, LSEG; Bloomberg counts ~$2.5T)** on ~24,000 deals (six-year-low count); 47 megadeals >$10B ≈ half of value; PwC FY forecast ~$4T (best since 2021). Cross-border $893B +62%. 2025 base: $4.8T +36% (corrected from ">$5T +40%").
- **DOJ Antitrust leaderless** (Slater out Feb 12 → Assefi out ~Jun 28 → Candeub expected, unconfirmed); FTC (Ferguson) still the active, remedy-friendly enforcer — June consent orders: Sevita/BrightSpring (128 ICFs, Jun 10), Ascension/AmSurg (7 ASCs, ~Jun 2); HieFo/EMCORE CFIUS divestiture clock (180 days from Jan 2). Expanded HSR form VACATED (5th Cir. denied stay Mar 19) — filing friction reduced. Net: window open, but review *timing* is politically unpredictable → extension risk in arb.
- Financing wide open: record IG issuance $3.4T H1 (+10%); HY 278/IG 76; private credit plentiful but stress rising (see A). PE: $3.7T dry powder, ~31,000 companies/$3.7T exit backlog (Bain), record 147 continuation-fund exits 2025.
- IPO window: **SpaceX IPO COMPLETED Jun 11–12 — $75B raised, biggest ever, +19% day one (SPCX)**; Anthropic S-1 filed Jun 1 targeting October (~$60B); OpenAI S-1 filed Jun 8 but leaning 2027; 79 IPOs YTD, June busiest (16); ITG +12.5% debut Jul 1 (priced below range); KNDS pulled — window open but selective/AI-favoring. Index-inclusion flows from SPCX are a live, datable lane.
- Hot sectors: power/utilities **$216B/23 deals, +173% YoY** (NextEra/Dominion $67B + AES $49.6B take-private anchors; corrected from "+418%"); media (WBD approved, state-AG risk residual); healthcare = the regulator-ordered divestiture vein.

**D. Special-situations lane ranking (fattest → thinnest edge) — post-verification**

| Rank | Lane | State (verified 2026-07-01) | Edge |
|---|---|---|---|
| 1 | **Forced-sellers + spinoffs** (one integrated trade) | HONA window open (Jun 29); **MBGL day-one 87.5M-share forced flow (Jul 1)**; FDXF seasoning (19.9% parent overhang); **ADIG locked: record Jul 20 / dist Aug 3 / regular-way Aug 4**; first-ever **December recon** ahead; FTC consent-order divestiture stream (Sevita, Ascension) | **Fattest** — mechanical, price-insensitive, calendar-dated, and now TWICE-yearly recon; Form-10 reading edge on three live stubs simultaneously |
| 2 | *(merged into #1 — spinoffs listed separately in prior reads)* | H2 pipeline: ADIG (Aug), L3Harris Missile Solutions carve-out IPO (2H, NOT an orphan spin), **KBR/MTS slipped to Jan 4 2027** | — |
| 3 | **Activism** | 136 global campaigns H1 (+5%); 68 US (+13%); "sell yourself" top demand (21% of campaigns vs 14% '22); Elliott 11 seats, Starboard 6; live: Ashland (Ancora), Six Flags (JANA), Tripadvisor (Starboard) | **Feeder** — source sale/breakup theses upstream; the pop arbs out in days |
| 4 | **Distressed / restructuring** | Supply ROLLING OVER: LSTA payment default 1.35%, dual-track 3.11%, distress ratio 6.53% (2 straight down months); Ch.11 +37% Q1 but LMEs = 54% of defaults; real stress migrating to private credit (Fitch 5.8% record) | **Demoted** — improving public-loan tape + wrong shape (slow, legal-heavy); watch private-credit unwinds as the NEXT supply source |
| 5 | **Merger-arb** | Man Group downgrade to neutral (crowded, "safe and tight"); leaderless DOJ = extension risk (UNF/Cintas Second Request Jun 11); WBD federal-cleared; EA/PIF CFIUS outside date Sep 28 | **Thin** — crowding + timing risk without the old break-risk premium |
| 6 | **Hard-binary / biotech PDUFA** | Makary-era FDA regime change real (single-trial default, priority vouchers, surprise CRLs) but XBI near highs, NO observed pricing dislocation; FDA rehiring (~2,200) decays the DOGE tail; REPL RP1 AdCom late July / PDUFA Aug 2 (3rd resubmission, 7× off lows) | **Thinnest — HELD, against researcher D's #2-fat promotion (REFUTED: implied-move leg unverifiable).** Revisit only on hard IV/dispersion evidence |

---

### 2026-06-29 — bi-weekly run (v2) · *live-verified; all figures confirmed via WebSearch/WebFetch + FMP MCP as of June 29, 2026*

**One-liner:** *Iran war de-escalating but unresolved; Fed dot plot turned hawkish (no 2026 cuts, hike risk real); market rotating from Mag-7 into equal-weight at stretched valuations; M&A window still open but DOJ politically opaque post-Slater; forced-seller window mechanically active today (Russell recon effective).*

**A. Macro regime now (risk-ON but fearful — CNN F&G 25; hawkish pivot is the regime shift)**
- S&P 500 **7,354 (+7.6% YTD cap-weight, +9.9% equal-weight)**; Mag-7 **-4.58% YTD** — market has ROTATED since the June 5 read (then 7,584 cap-weight). Shiller CAPE ~39.9 (125% above historical avg); P/S 3.70 (near record). *(FMP live, 2026-06-29.)*
- Inflation **re-accelerated**: PCE headline **4.1% YoY** (+0.4% MoM), core **3.4%** (May 2026) — highest since 2023, driven by energy passthrough from Hormuz disruption. *(BLS/BEA, 2026-06-25.)*
- Fed **hawkish hold at 3.50–3.75%** (June 17, 12-0 vote). June dot plot median YE-2026 **3.8%** (from 3.4% in March); 9/18 members lean toward at least one hike; Goldman now projects first cut **June 2027**. No cuts priced 2026. *(Fed, 2026-06-17; Goldman Sachs.)*
- Rates: 10Y **4.38%**, 2Y **4.07%** (+31 bps positive slope — curve steepened out of inversion); 30Y **4.87%**. *(FMP treasury data, 2026-06-26.)*
- VIX **18.43** (year-high 35.3 on Iran/Hormuz spike Feb-Mar); Iran ceasefire announced ~Jun 14, talks described as "fledgling/stuttering" as of Jun 29 — tail not fully extinguished. *(FMP live; CNBC.)*
- Credit **historically tight**: HY OAS **~263–278 bps** (5Y avg ~490 bps — near multi-decade tights despite hawkish Fed); IG OAS **~77–80 bps** (bottom decile post-GFC). AI infrastructure bond demand suppressing spread widening. *(ICE BofA FRED/TradingEconomics.)*
- Positioning: CNN F&G **25 (Fear)** — dropped from 54 (Neutral) on June 5; AAII net bearish (−2.8pp); BofA FMS (May): cash 4.2%, equities 50% net OW. Sentiment has partially unwound — better catalyst re-rating base than June 5.

**B. Forward 2026/2027 (earnings-only bull, no multiple expansion; hawkish path = rate-cut thesis dead)**
- Consensus YE-2026 targets: **7,100–8,100** (GS/MS/DB 8,000; JPM 7,800; Wells 7,950; Citi 7,700; BofA 7,100) — midpoint ~**7,800** (~6% from here). No strategist is pricing in multiple expansion; the thesis is entirely EPS growth (+24% to ~$340 in 2026). *(Bank outlooks, May–Jun 2026.)*
- Recession risk dramatically reduced: GS **15%** (from 45% May peak post-ceasefire), JPM **35%**, RSM 30%. Spread between GS/JPM signals wide uncertainty band. *(GS June 22, JPM, RSM June 2026.)*
- Biggest H2 2026 tail risk: **Fed hike (9 dots) + China tariff suspension expiry November + SCOTUS IEEPA ruling** — triple convergence of policy-binary risk in Q4. EU-US "Turnberry" deal signed (trans-Atlantic tariff resolved); that front is cleared.
- AI capex continues ($725B 2026, +77% YoY; ~$1T+ 2027 projected). Power & utilities M&A +418% as a direct consequence. AI premium on Mag-7 deflating (-4.6% YTD) while the underlying capex wave intact.

**C. M&A & deal environment (fertility 4/5 — structural open window; new DOJ opacity layer)**
- 2025 confirmed **$4.8–4.9T global M&A** (+40–41% YoY, 2nd-highest ever). Q1 2026: **$861B** (record Q1; strongest since 2021). US deal value through May 2026: **~$1.2T** (+100% YoY). K-shaped: megadeals ($5B+) = **48% of value** (vs 26% in 2024). *(Bain, S&P Global, EY-Parthenon.)*
- **Antitrust: lowest deal-block risk in 10 years** — Ferguson FTC accepts behavioral remedies, 9 divestiture packages approved YTD 2026 alone, deal timeline fell to 10.8 months Q1. **KEY CHANGE: Gail Slater ousted from DOJ** (Feb 2026, after opposing HPE/Juniper settlement). DOJ enforcement now politically-driven, not process-based — idiosyncratic opacity risk on Big Tech/semiconductor/national-security deals. Standard horizontal mergers still the fastest in a decade. *(Fox Business, The Hill, Dechert DAMITT Q1 2026.)*
- Financing available and plentiful: IG spreads ~80 bps, HY ~278 bps near historic tights; CLO issuance $101B Q1 2026; private credit SOFR+450-700bps (certainty premium). LBO volumes +30%+ YoY Q1 2026. *(Northleaf, PineBridge Q1 2026.)*
- **PE dry powder $3.7T (record); 30,000+ portfolio companies awaiting exit** — LP distribution pressure is structural. IPO: 22 traditional IPOs raised $9.4B Q1 (strongest Q1 in 5 years); SPAC surge (62 SPACs Q1, $11.8B raised). *(Preqin, FTI Consulting Q1 2026.)*
- Power & Utilities +418% M&A (AI data center power demand); Life Sciences +183%; Media +128% (streaming consolidation).

**D. Special-situations lane ranking (fattest → thinnest edge)**

| Rank | Lane | State | Edge |
|---|---|---|---|
| 1 | **Forced-sellers / carve-outs** | Russell recon **effective TODAY** (Jun 29) — first semi-annual cycle; HONA forced-sell window live; FDXF (Jun 1) window still open; 9 FTC/DOJ divestiture packages YTD; CFIUS-ordered EMCORE fab sale; PE $3.7T dry powder exit pressure | **Fattest** — mechanical + motivated + regulatory supply converging; twice-yearly calendar now locked in |
| 2 | **Spinoffs** | 8 completed H1 2026 (HONA today; FDXF Jun 1; VSNT Jan; FDXF; APD/Aptiv; AnaptysBio; Hexagon; FedEx Freight); H2 pipeline large (KBR Mission Technology mid-late 2026; S&P Global Mobility Jul 1; L3Harris; Resideo ADI Global; Modine/Gentherm) | **Fat** — stub-pricing dislocation window well-documented; Form-10 reading edge; activism-driven separation pipeline building |
| 3 | **Distressed / restructuring** | HY default rate 3.2–3.75%; **leveraged loans 7.5% default rate (2× historical avg)**; +14% YoY Q1 2026 bankruptcies; Saks Global emerged Jun 26; loan-to-own reviving (Pluralsight template); PE SaaS LBO stress list growing ($1T+ maturity wall 2028) | **Fat but complex** — supply rising; requires fulcrum/post-reorg expression, never a rates-rescue bet |
| 4 | **Activism** | 62 campaigns Q1 2026 (post-record-2025 pace); Elliott/Honeywell thesis delivered today (HONA); Starboard/BILL; Trian/Solventum; 92% settled without proxy fight; fast settlements (average ~16 days) | **Feeder, not terminal** — upstream source of spinoff/sale theses; play the resulting event, not the campaign |
| 5 | **Merger-arb** | K-shaped market; clean cash deals 5–8% annualized (spread compression from arb capital inflows); complex/political deals 12–20%+ but DOJ opacity adds unmodellable risk; HFRI +8.2% through Q3 2025 | **Thin on clean deals; moderate-with-opacity on complex** — size with wider break assumptions post-Slater for tech/semi |
| 6 | **Hard-binary / biotech PDUFA** | 53 H2 2026 decisions; DOGE FDA staffing cuts (3,500+ let go, only 350/2,200 replacements hired); approval pace slowing (11 approvals through Apr, run-rate ~33 vs 46 full-year 2025); Replimune RP1 Aug 2 (3rd BLA resubmission, AdCom late July) is key live binary | **Thinnest** — confirmed again; DOGE adds new tail risk (more CRLs, reversed positions, institutional knowledge loss) WITHOUT repricing implied options moves; the edge gap vs other lanes widened |

---

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

| Tripwire | Observable | Status (2026-07-01, researcher+blind-auditor AGREED) | If breached → |
|---|---|---|---|
| **Regulatory window closes** | FTC/DOJ leadership change; HSR friction revives; **midterms flip the House (Nov-2026)** | ⚠️ **PARTIAL** — DOJ Antitrust LEADERLESS (Slater out Feb 12, Assefi out ~Jun 28 — second chief in 5 months; Candeub expected nominee, unconfirmed). But friction is DOWN, not up: expanded HSR form vacated (5th Cir. Mar 19), no new blocked deals, FTC settling with remedies. Forward leg flashing: House flip heavy-favorite (generic D+7.2, markets 56–61%). Senate GOP-lean ~58%. | Merger-arb: widen EXTENSION/timing assumptions (not break) while the division is headless; re-check on Candeub confirmation. Forced-seller/spinoff tilts unaffected — remedy-driven divestitures continue via FTC. Nov-2026 remains the dated window-expiry marker. |
| **Oil/Hormuz re-escalation** | WTI breaks higher; VIX re-spikes toward 30 | ✅ **NOT BREACHED** — WTI $68.6 / Brent $71.2 FALLING (below GS's $80 YE call); VIX 16.6; 60-day ceasefire MoU signed Jun 17, record 16M bbl/day transit. Fragility real (US airstrike Jun 26 after alleged violation; Geneva talks postponed) — **ceasefire clock expires ~mid-Aug 2026** (dated). | Forced-seller/dislocation window *opens* — deploy into catalyst names orthogonal to oil; de-risk oil-sensitive sectors mid-event |
| **AI-capex break** | Hyperscaler capex guide-down or monetization scare | ⚠️ **PARTIAL** (upgraded from not-breached) — capex leg INTACT ($725B, guides still rising, Meta to $145B) but the sentiment/valuation leg cracked: **$1.3T semi-complex drawdown Jun 23–25** ("memory tax", capex-to-revenue gap), Nasdaq −5.5% off peak, NVDA lagging. Capex ≈93% of hyperscaler OCF; FCF crossover ~Q3. **Decision point: late-July Q2 earnings (Alphabet ~Jul 22–28 first).** | Broad de-grossing risk → tighten book independence (§1.7); the dominant shared factor would dominate everything |
| **Credit cracks** | HY OAS widening materially off ~285bp; leveraged loan defaults accelerate; **private-credit stress events (leg redefined this run)** | ⚠️ **PARTIAL** — public legs GREEN (HY 278bp tighter than ref; IG 76bp near record tights; realized BSL defaults LOW and improving: LSTA payment 1.35%, dual-track 3.11%, distress ratio falling 2 straight months — **prior "7.5% loans" leg RETIRED as a Moody's LME-inclusive forecast artifact**). New flashing leg: private credit — Fitch true default 5.8% TTM (record), Proskauer 2.73% rising (60% PIK/deferral), peer BDC redemptions to ~17%, FSB warning May 6. | Watch the first forced private-credit unwind (fund gate, mark-down cascade, BDC run) — that event, not BSL defaults, is the new leading indicator; it would refill the distressed lane and crack the "priced for perfection" public legs |
| **PDUFA lane dislocates** | Binary events stop being efficiently priced; vol/dispersion regime shift in biotech | ⚠️ **PARTIAL** — regime-change leg CONFIRMED (Makary FDA: single-trial default, priority vouchers, documented surprise CRLs/position reversals) but NO priced dislocation observable (XBI ~2% off highs, +89% off lows; no IV evidence obtainable). FDA rehiring (~2,200, ~600 onboarding) DECAYS the DOGE tail into H2. Researcher D's promotion of the lane to #2-fat was REFUTED in verification — the implied-move leg is an assertion, not a finding. | Maintain thinnest-lane classification. Re-examine ONLY on hard evidence of IV/implied-move repricing (persistently elevated event vol). REPL Aug 2 PDUFA + late-July AdCom = the live test case to observe, not to size. |

---

## §6 — Cadence & change log

**Schedule:** **bi-weekly on Mondays, ~09:07 local** — the cron fires every Monday but the task self-gates to a ≥13-day floor since the most recent run below, so it runs every *other* Monday. As of 2026-06-09 the task does the **full refresh**: §2 regime protocol → full 3-tier board re-sweep → enrich → commit on `ux-revamp` (the production push is a separate gated approval; see CATALYST_WATCH_METHODOLOGY.md §10). It appends a new §4 instance, refreshes §3/§5, and adds a row below. Durable scheduled task `catalyst-watch-regime-refresh` (see `C:\Users\Bruno\.claude\scheduled-tasks\`).

| Run date | Regime one-liner | Tilt (#2) | Tripwires breached | Notable new catalysts/hooks |
|---|---|---|---|---|
| 2026-07-01 (manual run, user-ordered — 14-day gate overridden; FIRST run of the verification layer) | Dispersion regime: Warsh Fed hawkish (hike ~77% by Dec), Mag-7 flat vs EW +11.4%, oil deflating; DOJ leaderless; spin/forced-seller lane fattest of the year; 3 dated binaries (Jul 24 tariff cliff, late-Jul AI earnings, ~mid-Aug ceasefire clock) | Structural-special-sits (**confirmed**; spins+forced-sellers merged #1, activism #3, distressed DEMOTED #4, PDUFA held thinnest against researcher push) | none breached; 4 PARTIAL (reg-window leaderless-DOJ; AI-capex $1.3T semi crack; credit private-credit leg — loans-7.5% leg RETIRED as artifact; PDUFA regime-change leg) | MBGL day-one forced flow (87.5M shrs); ADIG locked Jul 20/Aug 3-4; KBR slipped to Jan-4-2027; Section 122 tariff cliff Jul 24 (supersedes Nov date); SpaceX IPO done → SPCX index-inclusion lane; private-credit stress (Fitch 5.8% record); WBD federal-cleared (state-AG residual) |
| 2026-06-29 | Iran de-escalating but unresolved; Fed turned hawkish (no 2026 cuts, hike risk); Mag-7 rotation; forced-sellers #1 (Russell recon today) | Structural-special-sits (**confirmed**; forced-sellers #1, spinoffs #2, distressed #3) | ⚠️ Slater/DOJ opacity (partial); ⚠️ leveraged loan defaults 7.5% (partial); ⚠️ PDUFA tail elevated (partial) | HONA trading today (forced-sell window live); FDXF window open; KBR SpinCo CEO named; DOJ political opacity on tech/semi; Nov dual hard-date (tariff+IEEPA); loan-to-own wave beginning |
| 2026-06-05 (baseline) | Complacent melt-up over a live oil/inflation tail; open M&A window, possibly narrowing post-midterms | Structural-special-sits (**confirmed**) | none | Russell semi-annual recon; mega-IPO index inclusion; maturity-wall→distressed engine; midterm overlay |

---

## Sources (2026-07-01 run)
Macro/sentiment: FMP live (^GSPC/RSP/MAGS/^IXIC/^VIX/treasuries/BZUSD/CLUSD/XBI/HYG/LQD, 2026-07-01); BEA May PCE (Jun-25); Fed FOMC statement + SEP (Jun-17); Warsh confirmation (CNBC/NPR May-13/22); Atlanta Fed GDPNow (Jul-1); FRED/govspending ICE BofA HY+IG OAS (Jun-25/30); AAII (Jun-25); CNN F&G via MacroMicro (Jun-30); BofA FMS June (TradingView/Mace); GuruFocus CAPE; multpl P/E; Traders Magazine/Nasdaq (Russell recon $553.9B); StockTitan (Dec-hike futures). Forward: Goldman (target May-26/27, recession Jun-22, Fed-call Jun-7, oil factbox); CNBC (JPM Jun-24, Citi Jun-8); Yahoo/GuruFocus (Wells ~Jun-17); Investing.com (Barclays June); CNBC Dec-15-25 (BofA 7,100); supremecourt.gov 24-1287 (IEEPA Feb-20); Covington/Skadden/Thompson Hine/Holland & Knight (§122 Feb-24 eff., CIT May-7, refunds, Jul-24 expiry); Agence Europe/EP press (Turnberry ratified Jun-16/25); TBAC (deficits); Epoch AI + Fortune/JPM AM (capex/OCF crossover); Polymarket/Kalshi (midterms). M&A: LSEG Insights H1 (Jul-1); Bloomberg H1 (~$2.5T, Jul-1); CNBC/PwC mid-year (Jun-23); Bain (2025 $4.8T); FTC PRs (Sevita Jun-10, Ascension ~Jun-2); Axios/WaPo (Slater Feb-12); TechTimes/JDJournal/PYMNTS/CBS (Assefi exit Jun-28, Candeub); Dechert/Duane Morris (HSR vacatur); CBS/Yahoo (WBD DOJ approval Jun-12); CNBC/NPR/Axios (SpaceX IPO Jun-11/12); TechCrunch (Anthropic/OpenAI S-1s, Google/Wiz close); PwC P&U mid-year (+173%, AES); Reuters/Barclays (activism H1, Jul-1); Alternative Credit Investor/SEC (GS PC redemptions); Fitch/Proskauer/FSB P060526/Forbes (private credit); PitchBook LCD/LSTA (loan defaults May-31); Epiq/ABI (Ch.11 Q1). Special-sits: Honeywell PR/Nasdaq alert #2026-399 (HONA); SPGI 8-K/Form 10-12B/A/StockTitan (MBGL); FDX 8-K/BusinessWire (FDXF 80.1%); REZI 8-K/PRNewswire (ADIG, Jul-1); KBR PR (Jan-4-27 slip, Jun-25); Breaking Defense/Defense News (L3Harris carve-out); LSEG/CME (semi-annual recon); Man Group Q2 outlook (arb neutral); MLex/8-Ks (UNF/Cintas Second Request Jun-11); Replimune PR/8-K (RP1 Aug-2); AJMC/BioPharma Dive (Makary FDA); BioSpace/Quartz (FDA rehiring); CDER annual report (46 approvals); EA IR (CFIUS, outside date Sep-28).

## Sources (2026-06-29 run)
Macro/sentiment: FMP live S&P/VIX/Treasuries (2026-06-29); BLS PCE May 2026 (BEA, Jun-25); BLS CPI May 2026; Fed FOMC statement + SEP dot plot (Jun-17); Goldman Sachs rate outlook (Jun-22); Atlanta Fed GDPNow (Jun-25); GuruFocus CAPE/P-E (Jun-29); ICE BofA HY/IG OAS via TradingEconomics/FRED; CNN Fear & Greed; AAII Sentiment Survey; BofA Global Fund Manager Survey (May); MarketWatch Mag-7 (Jun-29). Forward: Goldman Sachs S&P targets (May-27); JPMorgan (Jun); Wells Fargo (Jun-15); Morgan Stanley, Citi, BofA, Deutsche Bank 2026 outlooks; Fed June 2026 SEP; IMF WEO April 2026; Goldman recession probability (Jun-22); Polymarket; EU-US Turnberry deal; USTR Section 301 tariffs (Jun-2). M&A: Bain 2026 M&A Report; S&P Global Market Intelligence Q1 2026; EY M&A Activity Insights May 2026; BCG M&A Outlook 2026; Morgan Stanley/PwC M&A Outlook; Dechert DAMITT Q1 2026; Fox Business / The Hill (Slater ouster); Hogan Lovells / Davis Polk / A&O Shearman (antitrust remedies); Northleaf / PineBridge / Lord Abbett (private credit); FTI Consulting Q1 2026 IPO/SPAC; Preqin / PwC PE Outlook. Special-sits: Barclays Q1 2026 Shareholder Activism Review; Harvard Law 2025 Activism Retrospective; StockAnalysis / InsideArbitrage / StockSpinoffs (spinoffs); Moody's / S&P Global / US Courts / Octus / Deloitte (distressed); LSEG Russell Reconstitution Jun 2026; TrendSpider / StockTitan (S&P index changes); Arnold & Porter / McDermott / Davis Polk (forced divestitures); AllianceBernstein / ArbLens / InsideArbitrage (merger-arb); Assyro / BiopharmaWatch / BioPharma Dive / StockTitan (PDUFA); BioSpace / STAT News / FedScoop (FDA DOGE staffing).

## Sources (baseline 2026-06-05)
Macro/sentiment: FMP live indices/VIX/Treasuries (2026-06-05); BLS CPI (May-12) & jobs (Jun-5); CME FedWatch; BofA Global Fund Manager Survey (May); AAII; CNN Fear & Greed. Forward: Goldman/JPM/Morgan Stanley/BofA/Stifel 2026 outlooks (Dec-25→H1-26); CBO/OMB deficit; Holland & Knight / PIIE / CFR (SCOTUS-IEEPA tariffs); Eurasia Group / CFR (geopolitics); Polymarket/270toWin (midterms). M&A: Bain & Co (Dec-2025), LSEG, EY-Parthenon (Jun-2026), S&P Global, PitchBook; Capitol Forum / Hogan Lovells / MWE (antitrust); Bloomberg/MLex (Prosus/Delivery Hero). Special-sits: Barclays/Cleary/Sidley (activism); Skadden / InsideArbitrage (spinoffs); Moody's/S&P/Fitch/US Courts/Epiq/ABI (distressed); NatLawReview/Wilson Sonsini/LSEG (forced sellers); AllianceBernstein/HFRI (merger-arb); BiopharmaWatch/CatalystAlert (biotech).

*Full agent transcripts for the baseline run live in the session that produced this doc (2026-06-05).*
