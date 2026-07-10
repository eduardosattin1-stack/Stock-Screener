# Future Resources — Commodity & Thematic Chain Regime

**Status:** Living document · regenerated bi-weekly · companion to [FUTURE_RESOURCES_SPEC.md](FUTURE_RESOURCES_SPEC.md)
**Last run:** 2026-07-10 (6-agent investigation, live-verified) · **Version:** v1
**Relationship:** [FUTURE_RESOURCES_SPEC.md](FUTURE_RESOURCES_SPEC.md) decides the *structure* (chains, lanes, floors, debate protocol) on first principles. **This doc supplies the time-varying evidence that each chain's cycle is where the basket assumes it is _right now_, and the tripwires that would change it.** Chain definitions are stable; the regime read is perishable — hence the bi-weekly cadence.
**Machine sidecar:** [backend/_opus_debate/future_resources/regime_state.json](backend/_opus_debate/future_resources/regime_state.json) — `{chain_id: {state, spot, vs_incentive_pct, one_liner, tripwires_breached, as_of}}`, consumed by the Lane A BRIEF and the grade-input builder (`chain_regime` stamp → Director enforces "HEADWIND chain ⇒ size_units ≤ 0.5 or written justification").

---

## §0 — Why this layer exists

The spec picks six value chains on *first principles* (structural supply/demand mismatch, policy-forced reshoring, physical bottlenecks, capex-cycle inflection). A first-principles chain thesis is necessary but not sufficient: **whether a chain is actually paying today depends on where its cycle sits** — spot vs the marginal producer's incentive price, inventory direction, term-contracting behavior, policy datelines, and (for the machine chains) the capex cycle and the funding window. A uranium tilt is worthless if utilities stop term-contracting; a copper-developer tilt needs spot to actually clear greenfield hurdle rates; a quantum sleeve priced at 800x sales needs the funding window to stay open.

So this doc does three things:
1. **Reads each chain's regime** through its own fixed dial set (§2) and maps the verdict to basket decisions (§1).
2. **Records the dated, cited evidence** behind each verdict — this run's instance in §3, prior instances appended below it.
3. **Names the tripwires** — the specific, observable conditions that would flip each verdict — so every chain weight is held *conditionally*, not on faith. This includes the standing **lithium re-entry tripwire** (§4): lithium is excluded from the basket by spec until sustained spot exceeds the marginal producer's incentive price.

**Core stance: a commodity thesis without a cycle read is a narrative.** Re-run bi-weekly, diff against the prior instance, and act only on what actually moved.

---

## §1 — How regime maps to basket decisions

| Decision | Regime input that governs it | Favorable when… |
|---|---|---|
| **Chain inclusion / weight** | Verdict (TAILWIND / NEUTRAL / HEADWIND) per chain | TAILWIND chains carry full weight; **HEADWIND ⇒ size_units ≤ 0.5 or a written Director justification** (deterministically checked via `regime_state.json`) |
| **Producer vs developer split within a chain** | Spot vs incentive price; who is getting paid *now* vs who needs the price to hold | Spot > incentive with term/contract cover → producers core, developers satellite; spot < incentive → developers are optionality only |
| **Entry timing vs fundamentals** | Equity drawdowns vs physical-market state (the two frequently diverge) | Fundamentals intact + equities corrected = better entry; fundamentals intact + equities at highs = priced |
| **Lithium exclusion** | The §4 re-entry tripwire | Excluded until sustained spot > marginal-producer incentive price |

The chain *theses* are regime-invariant — this doc never edits them. Weights, splits, and the lithium exclusion are regime-conditional and are what this doc keeps honest.

---

## §2 — Investigation protocol (reproducible — what the bi-weekly task re-runs)

Run **six parallel research agents**, one per chain, each told: *today's date; your training is stale, verify everything live; use WebSearch/WebFetch + FMP MCP quotes; cite source + date; lead with a BLUF; end with a TAILWIND/NEUTRAL/HEADWIND verdict, tripwires, "Implications for Future Resources," and "Confidence & gaps."*

The four commodity/power agents read: **spot vs incentive price** (incentive = cited feasibility/analyst consensus, never invented), inventories, term-contracting state, futures-curve shape, COT positioning where available, policy datelines. The two machine-chain agents read a different dial set: **robotics** — industrial capex cycle (PMI / machine-tool orders), humanoid program datelines, robot order/backlog trends; **quantum** — the government funding cycle (NQI reauthorization, DARPA/DOE/sovereign programs), the error-correction milestone track, enterprise contract flow.

**Data reality:** copper (`HGUSD`) is an FMP commodity; **uranium spot and NdPr are NOT** — agents web-source them with citations (UxC/Numerco/TradeTech/SMM as reported in press) or proxy via SRUUF/U.UN trust NAV. Where a figure could not be verified live it is tagged in the chain's "Confidence & gaps" and never presented as sourced fact.

**Synthesis step:** reconcile the six reads, update §3 (new dated instance), refresh §4 tripwire status and the change log, and write `regime_state.json`. Diff against the prior instance and report what moved. *(First run: no prior baseline exists, so `tripwires_breached` is empty by construction unless an agent found an already-breached condition — none did.)*

---

## §3 — Current read (2026-07-10, first instance)

**Verdict board:**

| Chain | Verdict | One-line state |
|---|---|---|
| uranium_fuel_cycle | **TAILWIND** | Term at 18-yr highs, Kazatomprom cutting, 2028 Russian ban approaching; equities mid-correction |
| copper_electrification | **TAILWIND** | Spot above ~$12,000/t incentive; 3 top-10 mines impaired; tariff decision is the live binary |
| rare_earth_strategic | **TAILWIND** | NdPr at 2026 highs above MP's $110 floor; US capital deploying at record scale; China-flood is the risk |
| power_for_ai | **TAILWIND** | Turbines sold out to ~2030, transformers 2.5–4yr lead times, PJM at cap; IPP leg mid-digestion |
| robotics_automation | **TAILWIND** | ISM 6th month expanding, machine tools +37% YoY, all four anchors beat; humanoid leg is funding-driven |
| quantum | **NEUTRAL** | Substance improving (QEC in Nature, DARPA money), sentiment deflating (50–70% drawdowns, flat QNT IPO) |

---

### 3.1 uranium_fuel_cycle — TAILWIND

**BLUF:** Fundamental tailwind with an equity-market caveat: spot (~$85/lb) has consolidated ~15% below its January 2026 spike above $101, but term price is at 18-year highs (~$93–94/lb), Kazatomprom has cut 2026 supply ~10%, and Western enrichment is getting $2.7B of DOE money ahead of the 2028 hard Russian import ban — yet uranium equities have corrected 20–50% from highs on valuation, so the tailwind currently favors contracted producers and enrichers over spot-levered developers.

**Factor findings (condensed, cited):**
- **Spot vs incentive:** ~$85.85/lb (Jul 6, 2026, [Trading Economics](https://tradingeconomics.com/commodity/uranium)); spiked past $100 late Jan-2026 (TradeTech $100.25 Jan 28; [INN](https://investingnews.com/spot-uranium-surges-past-100/)) then held $84–87 through Q2 ([INN Q2 review](https://investingnews.com/uranium-forecast/)). Above most cited greenfield incentive levels (~$70–90/lb) but flow-driven. SRUUF $18.75, −24% off high (FMP) — consistent proxy. *No FMP uranium commodity; UxC paywalled — spot is press-cited.*
- **Term contracting (the cycle tell):** term broke $90/lb Jan-2026, first since 2008; TradeTech LT indicator $93.00 Mar 31, 2026, 18+ yr high; most recent ~$94 ([Sprott](https://sprott.com/insights/uranium-enters-2026-with-renewed-strength-and-strategic-tailwinds/); [TradeTech](https://www.uranium.info/press_releases.php); INN). Term > spot — utilities locking security of supply. Cameco Q1-2026: >28M lbs/yr contracted deliveries over 5 yrs; bought spot at $110.42/lb avg unit cost ([Cameco](https://www.cameco.com/media/news/cameco-reports-2026-first-quarter-results)).
- **SWU/enrichment:** SWU +52% YoY in Q1-2026, +167% since Feb-2022 ([INN](https://investingnews.com/us-looming-uranium-enrichment-shortage/)); Urenco adding 700k SWU (early 2027) + 2.1M SWU New Mexico from 2032 ([ANS](https://www.ans.org/news/2026-06-02/article-8085/)). Tightest link; new capacity lands 2027–2032+.
- **Supply/inventory:** Kazatomprom cut 2026 guidance ~10% to 29,697t (~5% of global supply) ([WNN](https://www.world-nuclear-news.org/articles/kazatomprom-to-lower-uranium-production-in-2026)); SPUT raised >$700M and bought ~6M lbs in 2026, holdings >81M lbs (Cameco Q1 MD&A via [SEC 6-K](https://www.sec.gov/Archives/edgar/data/0001009001/000119312526205080/d103546dex992.htm)). Counterpoint: latest hard EIA data (end-2024) showed US utility inventories *building* +11% ([EIA](https://www.eia.gov/uranium/marketing/)) — 2025 data not yet published.
- **Policy:** DOE $2.7B enrichment task orders finalized Jan 5, 2026 ($900M each Centrus/General Matter/Orano) ([DOE](https://www.energy.gov/articles/us-department-energy-awards-27-billion-restore-american-uranium-enrichment)); Russian-ban waivers terminate no later than Jan 1, 2028; Palisades restarted, TMI-1 fuel delivered/end-2026, Duane Arnold slipped to early 2029 (ANS). Westinghouse "10 AP1000s" is announcement, not FID.
- **Equities (FMP 2026-07-10):** CCJ $95.87; UEC −49%, UUUU −51%, LEU −63% off highs — a producer-vs-developer split on valuation, not a fundamentals break.

**Tripwires:**
- Term price prints below ~$85/lb (TradeTech/UxC monthly) or 2026 full-year contracting tracks below ~80M lbs → flip to NEUTRAL. (Conversely spot sustained >$100 with term >$95 upgrades.)
- Russian-ban waivers extended beyond Jan 1, 2028, or sanctions thaw restores Rosatom EUP/SWU flow → deflates the SWU premium, hits LEU hardest.
- Kazatomprom restores 2027 guidance to 100% of subsoil-use levels or guides materially above 30k tU3O8 → supply response caps spot.
- SPUT flips to sustained >10% NAV discount with no raises for 2+ quarters → removes the marginal spot bid.

**Basket implication:** producers with term books (CCJ) prime; LEU is the scarcest but highest-beta policy expression; developers (NXE, DNN) and spot-levered juniors sized smaller as optionality; SRUUF/UROY for cleaner commodity beta.

**Gaps flagged by the agent:** current UxC daily spot and SPUT premium/discount unverified (paywall/403); Q2-2026 industry contracting volume thin; end-2024 EIA inventory *build* is a mild counterpoint to the tight-inventory narrative; term "$80 stable" vs "$93–94" contradiction resolved in favor of dated TradeTech prints.

---

### 3.2 copper_electrification — TAILWIND

**BLUF:** Copper is in a structurally tight, policy-distorted bull regime: COMEX spot ~$6.29/lb (~$13,870/t) and LME cash ~$13,090/t sit at or above the ~$12,000/t consensus incentive price for new supply, propped by the Grasberg supply shock and a pending US refined-copper tariff decision — a tailwind for the chain, though softening Chinese physical demand and record US stockpiles make the rally vulnerable to a tariff "no" or de-stocking event.

**Factor findings (condensed, cited):**
- **Spot vs incentive:** COMEX $6.29/lb (FMP live, 2026-07-10); LME cash ~$13,090/t (Jul 8, 2026, Westmetall via search). Incentive: JPM >$12,000/t for ~15% IRR; UBS $5.50/lb (~$12,125/t) ([CNBC, Dec 18, 2025](https://www.cnbc.com/2025/12/18/copper-price-bhp-ceo-investment-banks-see-bull-run-in-2026.html)); S&P Global: >99% of current production below the 2026 consensus price. **Spot ~8–15% above the marginal-new-supply threshold** — margin-rich for producers, finally clearing the bar for developers.
- **Inventories — bifurcated and tariff-distorted:** COMEX record ~650kt (vs ~80kt pre-tariff) + Macquarie-estimated ~550kt off-exchange US; LME ~352kt late June, near 3-month low and drawing, but total visible stock built ~870kt since 2025 ([TradingKey](https://www.tradingkey.com/analysis/commodities/metal/261993589-copper-inp-comex-lme-tin-tradingkey); [IndexBox/Macquarie](https://www.indexbox.io/blog/copper-prices-hit-627lb-as-macquarie-warns-of-surplus-and-artificial-tightness/)). Macquarie's phrase: "artificial tightness."
- **Balance genuinely contested:** ICSG (Apr 2026) ~96kt 2026 *surplus*; JPM ~330kt *deficit*; Macquarie surplus through 2028; Goldman end-2026 LME target $13,735/t, >$14,000 if refined tariffs proceed. Tight either way vs a ~27Mt market.
- **Disruptions (dominant bull driver):** Grasberg mud-rush — FCX 2026 guidance cut ~35%, ~600kt cumulative loss, normal ops not before 2027 ([Mining.com](https://www.mining.com/web/graphic-grasberg-mine-accident-tightens-global-copper-supply-estimates/)); Kamoa-Kakula ~300kt loss 2025–26; El Teniente collapse ([ING](https://think.ing.com/articles/copper-upside-building-on-tight-supply/)). Three top-10 mines impaired simultaneously.
- **China:** NBS PMI 50.3 June (back expanding); **grid capex +37% y/y Q1-2026** — the strong copper leg ([Discovery Alert](https://discoveryalert.com.au/china-refined-copper-imports-rising-strong-demand-2026/)); EV signal contradictory (CAAM NEV +23.6% incl. exports vs retail deliveries −13% H1); property weak.
- **Tariff binary:** 50% on semis, 25% derivatives; cathode still exempt; Commerce assessment due Jun 30, 2026; phased refined duty (15% Jan-2027 / 30% Jan-2028) awaits presidential decision — Morgan Stanley 43% probability ([ING THINK](https://think.ing.com/articles/whats-next-for-us-copper-import-tariffs/)). **No confirmed ruling as of this run — pending, days-to-weeks.**

**Tripwires:**
- Refined-copper tariff declined/shelved → COMEX premium collapse, ~1.2Mt of US inventory overhangs; watch LME breaking below ~$12,000/t on the news.
- LME cash sustained below ~$11,000/t (~$5.00/lb) for >1 month → regime downshifts from incentive-clearing to cost-curve pricing.
- Grasberg restores faster than guided (FCX raises 2026 guidance or full ramp before mid-2027) → removes the largest single deficit driver.
- China grid capex growth <~+10% y/y for two consecutive quarters alongside NBS PMI back under 50 → the only strong physical demand leg breaks.

**Basket implication:** overweight low-cost producers (SCCO/TECK cleanest price beta; FCX both the disruption and the biggest tariff winner as largest US refiner); developer exposure is the higher-beta sleeve contingent on the tariff decision and LME holding >$12,000/t. All five anchors trade 10–35% off highs despite near-record copper — the equity market already discounts surplus/de-stocking risk.

**Gaps flagged by the agent:** same-day LME settlement and warehouse tonnage unverified (403s), directionally corroborated; ICSG-vs-JPM balance contradiction unresolved (methodology/timing); tariff outcome binary at ~43%; Kamoa/El Teniente recovery timelines not re-verified past Q4-2025 reporting. Confidence: HIGH on price/inventory direction, MEDIUM on 2026 balance, LOW on tariff outcome.

---

### 3.3 rare_earth_strategic — TAILWIND

**BLUF:** Strong policy-and-price tailwind: NdPr has rallied back to 2026 highs (SMM NdPr alloy $133/kg, Nd metal ~$146/kg at the Jul 1 print) well above MP's $110/kg DoD floor, China is actively weaponizing export controls (blacklisting MP and USAR on Jun 22, 2026), and Washington is deploying capital at unprecedented scale ($10B EXIM "Project Vault," $725M OSC loan to Energy Fuels, $1.6B LOI to USA Rare Earth). The main risk is a China easing/flood scenario, not demand.

**Factor findings (condensed, cited):**
- **NdPr price:** SMM Pr-Nd *oxide* $90.32/kg (Jun 1, 2026, after ~35% correction from late-April peak); Jul 1 SMM *metal/alloy* prints Nd $145.88/kg (+19.6% m/m), NdPr alloy $133.02/kg (+21.4% m/m) — new 2026 high, correction ended ([rare-earth-mining.com citing SMM](https://rare-earth-mining.com/rare-earth-market-outlook-july-2026/); SMM daily review). Reuters anchor: $123/kg Feb 18, 2026, highest since Jul-2022 — already above MP's floor ([US News/Reuters](https://money.usnews.com/investing/news/articles/2026-02-18/rare-earths-surge-above-price-floor-given-to-mp-materials)). **Caution: oxide vs metal/alloy bases are not directly comparable, and SMM's own pages returned 403 — July prints come via secondary trackers.**
- **China controls — net tightening on RE:** MOFCOM entity-listed 10 US firms incl. **MP and USAR** Jun 22, 2026 ([Bloomberg](https://www.bloomberg.com/news/articles/2026-06-22/china-places-two-us-rare-earths-producers-on-export-control-list)); whistleblower enforcement from Jul 1 (Morgan Lewis). Ga/Ge/antimony ban *suspended* until Nov 27, 2026 (licensing regime; antimony still $58,000–59,650/t Rotterdam, ~4x 2024 avg — Fastmarkets). Tungsten: exports via 15 approved firms 2026–27, quotas cut a third straight year, prices +200% in 2026 (Fastmarkets).
- **US response:** MP–DoD $110/kg NdPr floor ×10yrs + 100% 10X magnet offtake + $400M preferred ([FAS](https://fas.org/publication/unpacking-dod-and-mp-partnership/)); EXIM $10B "Project Vault" strategic reserve (Feb 2, 2026, [EXIM](https://www.exim.gov/news/project-vault)); OSC $725M loan to UUUU (Jun 18, 2026) + $500M Phoenix Tailings; USAR $1.6B Commerce LOI (**non-binding**) + $1.5B private raise; US Antimony $245M DLA; DOE $134M NOFO.
- **Ex-China capacity:** MP Dy/Tb circuit commissioning began Q2-2026; 10X Texas 7,000t/y magnets from 2028 (MP Q1 8-K). USAR Stillwater Phase 1a commissioned Mar 26, 2026, targeting 600t/y by Q4 — **but local press reports the plant is years behind original schedule** ([OKC Fox](https://okcfox.com/news/local/stillwater-rare-earth-plant-years-behind-schedule-as-questions-grow-over-production-manufacturing-project-operational-millions-taxpayer-dollars-support-gov-stitt-local-leaders-oklahoma-exchange-commission-development-producing-ability-hired-officials)). UUUU first US primary Tb oxide Mar 25, 2026; commercial Dy/Tb targeted Q4-2026 (Energy Fuels IR). Lynas first ex-China heavy-RE separation. S&P Global: bottlenecks persist through 2026 — ex-China capacity is still a low-single-digit % of Chinese separation volume.

**Tripwires:**
- China H2-2026 MIIT quota (due ~Jun/Jul, **still pending as of this run — the single most important near-term unknown**): large expansion → NdPr correction, cut to NEUTRAL; freeze/cut → reinforces TAILWIND.
- NdPr oxide sustains below ~$75/kg (SMM) for a month → approaching MP's floor on metal-equivalent basis; flips non-floor producers and developers toward HEADWIND-ish NEUTRAL.
- Nov 27, 2026 Ga/Ge/antimony suspension deadline: ban restored → tighten; permanent lifting + RE license liberalization → strategic-metal premia deflate materially.
- US policy reversal: MP floor structure unwound, or USAR's non-binding $1.6B LOI fails to convert to definitive agreements by end-2026 → developers de-rate.

**Basket implication:** overweight floor/contract-protected producers (MP, UUUU, Lynas — paid whether prices rise or fall); developers (USAR, juniors) at modest weight as policy optionality with real execution risk; minor-metal spot torque (antimony/tungsten, mostly-realized premia on a Nov-2026 truce timer) is a tactical, not structural, sleeve.

**Gaps flagged by the agent:** NdPr price basis confusion (oxide vs metal/alloy, secondary trackers, no direct July oxide USD print) — MEDIUM confidence; H2 quota status unconfirmed; UUUU Phase 2 / USAR ramp / MP 10X figures are company statements; $245M DLA and Lynas Seadrift figures from a secondary funding guide, not independently confirmed.

---

### 3.4 power_for_ai — TAILWIND

**BLUF:** The physical bottleneck regime is intact and hardening: gas turbines effectively sold out into 2029–30, transformer lead times still 2.5–4 years, PJM capacity cleared at its price cap — while the four big hyperscalers guide ~$630–725B of 2026 capex (+~77% y/y). Strongest for scarce-capacity equipment producers and EPC (GEV, ETN, PWR); the nuclear-IPP leg (CEG, VST, TLN) remains fundamentally supported but its equities have already corrected 25–40% on PPA-pricing opacity and transmission-delivery risk — a tailwind mid-way through digesting an overshoot.

**Factor findings (condensed, cited):**
- **Hyperscaler capex:** Big-4 2026 guidance ~$630–725B, +~77% from ~$410B in 2025 ([Tom's Hardware, Feb 2026](https://www.tomshardware.com/tech-industry/big-tech/big-techs-ai-spending-plans-reach-725-billion)). **Microsoft's figure is contradictory across sources ($120B vs ~$190B — fiscal-vs-calendar/lease treatment); do not anchor on a single number.** The "40% of AI DC projects delayed by power" stat is blog-sourced — directional only.
- **Interconnection:** LBNL Queued Up 2026 (end-2025 data): ~1,312 GW generation + 749 GW storage queued; total queue −10% y/y (first decline) but active *gas* +86% to 253 GW; median request→COD >5 years; only 13% of 2000–2020 requests ever reached COD ([LBNL](https://emp.lbl.gov/queues)). Transmission now binds even restarts: PJM says some Crane-restart upgrades could take until **2031** ([WNN](https://www.world-nuclear-news.org/articles/constellation-seeks-regulators-help-for-2027-plant-restart)).
- **Gas turbines:** GEV Q1-2026 backlog + slot reservations 83→100 GW in one quarter; target ≥110 GW by YE-2026; ~10 GW of 2029–30 capacity left; CEO expects sold out through 2030 ([GEV PR, Apr 2026](https://www.gevernova.com/news/press-releases/ge-vernova-reports-first-quarter-2026-financial)). Corroborated by Mitsubishi Heavy (~70 GW/yr demand through 2030, Bloomberg May 12, 2026) and Siemens Energy (60–65% of gas orders data-center-driven). *"Sold out through 2030" is a CEO forward expectation, not a booked fact.*
- **Nuclear-IPP PPAs:** Talen–AWS 1,920 MW through 2042 (~$18B); Vistra–AWS 1,200 MW/20yr Comanche Peak; Meta up-to-6.6 GW with Oklo/Vistra/TerraPower; CEG–Walmart 176 MW. PJM 2026/27 BRA cleared **at the FERC cap, $329.17/MW-day** (vs $28.92 in 2024/25), data centers ~40% of the $16.4B cost ([PJM](https://insidelines.pjm.com/pjm-auction-procures-134311-mw-of-generation-resources-supply-responds-to-price-signal/)). Yet CEG −26% YTD after guidance missed and Meta–Clinton PPA pricing was never disclosed — **actual PPA prices are undisclosed; the $70–100/MWh repricing math is analyst inference, the thinnest data point in the read.**
- **Transformers/switchgear:** power transformers ~128 wks avg, GSU ~144 wks (some 4 yrs), substation >160 wks; switchgear eased to ~44 wks (Wood Mackenzie; [POWER](https://www.powermag.com/transformers-in-2026-shortage-scramble-or-self-inflicted-crisis/)). ETN Q1-2026 electrical backlog +48% y/y, DC orders +240%; PWR record $48.5B backlog.

**Tripwires:**
- GEV Gas Power backlog + slot reservations flat/down sequentially in any quarter, or disclosed slot cancellations/fee forfeitures — the single cleanest real-demand signal in the chain.
- Two or more Big-4 hyperscalers cut 2027 capex guidance, or a corroborated TD Cowen-style lease-cancellation report at >2–3 GW scale re-emerges (the Feb-2025 episode was ~2 GW).
- Next PJM BRA clears materially below the cap (roughly <$250/MW-day vs $329.17), or FERC/state action forces large-load self-supply → deflates the merchant/capacity leg of CEG/VST/TLN.
- Wood Mackenzie transformer survey shows power-transformer lead times back under ~100 weeks for two consecutive readings. (Positive corollary: any *disclosed* hyperscaler nuclear PPA at/above ~$100/MWh confirms the IPP repricing thesis → add on weakness.)

**Basket implication:** GEV/ETN core (scarcity rents with multi-year visibility); PWR volume-levered on the interconnection bottleneck; nuclear IPPs are the better post-correction risk/reward but need a pricing-disclosure catalyst — basis/transmission risk is the underappreciated failure mode. The bottleneck is migrating downstream: turbine scarcity is consensus and priced; transformer/T&D scarcity has longer duration.

**Gaps flagged by the agent:** Microsoft capex contradiction; PPA economics undisclosed; LBNL medians not nationally uniform; several aggregator sources (anchored to primary filings where possible); no commodity spot exists for this chain — scarcity prices used are the PJM cap-censored clearing price and lead-time proxies.

---

### 3.5 robotics_automation — TAILWIND

**BLUF:** The industrial automation capex cycle has decisively turned up — ISM manufacturing in its sixth month of expansion, Japanese machine-tool orders +37% YoY, and all four anchor names (ISRG, TER, ROK, CGNX) beating and raising — while humanoid robotics has entered a genuine capital-formation phase (Figure at $39B, Agility SPAC, Unitree IPO approved). Tailwind, with the caveat that the humanoid leg is funding-driven and vulnerable to a hype unwind the industrial leg is not.

**Factor findings (condensed, cited):**
- **Capex cycle:** ISM Manufacturing PMI **53.3 June 2026**, 6th straight month of expansion; New Orders 56.0, 6th straight month >50 ([ISM via PR Newswire, Jul 1, 2026](https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html)) — a real regime change after 2023–25 sub-50. JMTBA Japan machine-tool orders **+37.4% YoY** to ¥176.9B May-2026 (Jan–May +32.2%), though **MoM slipping (−6.4% May) — rate of change is peaking** ([Trading Economics/JMTBA](https://tradingeconomics.com/japan/machine-tool-orders/news/557552)). IFR: 542k industrial robots installed CY2024, stock 4.66M, China 54% of installs ([IFR](https://ifr.org/ifr-press-releases/news/global-robot-demand-in-factories-doubles-over-10-years)) — lagged data; the live signal is PMI/machine-tools/earnings.
- **Anchor confirmation:** ROK FQ2-2026 sales +12%, orders ~$2.5B/qtr annualizing ~$10B vs $8.9B backlog, guidance raised ([8-K](https://www.sec.gov/Archives/edgar/data/0001024478/000102447826000020/q2fy26ex99.htm)); CGNX Q1 +24.3% YoY, EBITDA margin +1,000bps (machine vision = classic early-cycle print); TER Q1 record $1.282B (+87%, AI-test), Robotics +32% YoY, 4th straight sequential growth ([8-K](https://www.sec.gov/Archives/edgar/data/0000097210/000119312526188706/ter-ex99_1.htm)); ISRG +23%, procedures +16% — structural/acyclical diversifier.
- **Humanoids — capital real, production claims mixed:** Figure Series C >$1B at **$39B post** (verified via [Figure](https://www.figure.ai/news/series-c)); Agility **$2.5B SPAC** (AGLT, announced Jun 24, 2026; Digit at Schaeffler/GXO/Toyota; >65,000 real-world hours; claimed >$300M *pre-orders* ≠ revenue; filings show heavy losses — [GeekWire](https://www.geekwire.com/2026/digit-maker-agility-robotics-to-go-public-in-2-5b-deal-heres-what-the-filings-say-about-its-finances/)); Unitree STAR IPO approved Jul 3, 2026 (~$619M at ~$6.2B, [Caixin](https://www.caixinglobal.com/2026-07-03/unitree-robotics-wins-approval-for-618-million-star-market-ipo-102460136.html)). **Tesla Optimus is the clearest hype-vs-delivery gap** — Gen-3 unveil delayed, Fremont production "late July/August 2026," every major timeline since 2022 has slipped; the next 60 days are a live test.
- **Warehouse automation:** Symbotic bought Walmart's robotics division ($200M) with Walmart investing $520M; backlog >$5B — the most contract-backed demand line in the theme.

**Tripwires:**
- ISM Manufacturing New Orders below 50 for two consecutive months → the industrial leg flips to HEADWIND (capex upturn was a restock).
- Japan machine-tool orders YoY turn negative, or fall below ~¥130B/month (base effects get much harder in H2-2026).
- Humanoid funding window closes: AGLT breaks materially below trust at/after close, Unitree prices weakly/pulled, or Figure raises flat/down vs $39B → de-rates the entire thematic multiple.
- Tesla Optimus Fremont start slips past Q4-2026 or Gen-3 unveil cancelled → compresses humanoid-adjacent valuations chain-wide.
- ROK or CGNX guides down / order deceleration at next report (ROK FQ3 ~Aug; CGNX Q2 ~Jul–Aug 2026) — the fastest single-name falsifier.

**Basket implication:** producers/enablers over end-platform developers — machine vision, controls, test, actuators get paid whether humanoids succeed or merely keep raising. Humanoid pure-plays (AGLT, Unitree) are satellite optionality with the funding-window tripwire as stop condition. Warehouse automation > consumer humanoids (zero verified at-scale delivery). ISRG hedges the cycle. China concentration (54% of installs) cuts both ways.

**Gaps flagged by the agent:** Figure's monthly BotQ shipment ramp and Digit fleet-size counts are secondary/low-quality-sourced — do not anchor; no fresh US (USMTO) machine-tool data — Japan used as proxy; Agility's $300M pre-order composition (binding vs LOI) unaudited; Eurozone PMI not checked; the JMTBA MoM-vs-YoY contradiction (cycle may be closer to mid/late) is the live monitoring item.

---

### 3.6 quantum — NEUTRAL

**BLUF:** Quantum's fundamental drivers — government money, defense contracts, and error-correction milestones — are the strongest they have ever been, but the equity froth of 2025 has decisively cooled: pure-plays are 50–70% off 52-week highs on triple-digit-to-800x P/S, insider selling, and a $15B Quantinuum IPO that soaked up sector capital. Improving substance, deflating sentiment.

**Factor findings (condensed, cited):**
- **Funding cycle — advancing but not yet law:** NQI Reauthorization passed Senate Commerce unanimously (S.3597); House companion H.R.8462 cleared committee Apr 29, 2026 ([Congress.gov](https://www.congress.gov/bill/119th-congress/senate-bill/3597); [Quantum Insider](https://thequantuminsider.com/2026/05/01/u-s-quantum-policy-bill-advances-to-full-house-consideration/)). **Authorization ≠ appropriation** (FY26 agency spending plans don't exist yet); not signed into law per latest sources. DARPA QBI Stage B (Nov 6, 2025): 11 companies incl. IonQ/Quantinuum — **Rigetti and D-Wave notably absent**; Stage C downselects ~late 2026 ([DARPA](https://www.darpa.mil/research/programs/quantum-benchmarking-initiative/stage-b-selection)). UK added £2B for quantum procurement Mar 17, 2026; EU >€11B committed but ~5% of global private investment; Japan/China figures bundled — China quantum budget unverifiable.
- **Error correction:** Microsoft+Quantinuum 800x physical-to-logical error-rate reduction **peer-reviewed in Nature, Jun 10, 2026** — strongest validated result to date. Quantinuum "94 logical qubits" traces only to secondary blogs — company-claimed. Key sentiment datum: unlike Google Willow (Dec 2024), the 2026 milestones have **not** lifted the pure-plays — the sector sold off through the very weeks they landed ([247WallSt, Jun 16, 2026](https://247wallst.com/investing/2026/06/16/ionq-rigetti-d-wave-and-quantum-computing-inc-all-fall-5-to-7-as-the-quantum-rally-reverses/)).
- **Contracts:** IonQ $54.5M AFRL (Mar 2026 — *figure from search synthesis, verify against 8-K before quoting to clients*), DARPA HARQ award Apr 14, 2026; D-Wave $10M/2yr Fortune-100 QCaaS via 8-K ([SEC](https://www.sec.gov/Archives/edgar/data/1907982/000190798226000017/qbts-20260127.htm)) — real but small vs a ~$7.4B cap; Rigetti's "$100M CHIPS" is a **letter of intent, not a contract**. Pattern: flow is real, growing, ~90% government/defense; no named commercial deal >$10–20M found.
- **Valuation/sentiment:** IONQ $43.00 (−49% off high), RGTI $16.66 (−71%), QBTS $20.24 (−57%) — all below 50/200-day (FMP, 2026-07-10); P/S ~109/836/791 (May-2026 vintage, prices since fell 15–25%); insider net selling at all three. Quantinuum IPO (QNT, Jun 4, 2026): $60/sh, $1.68B raised at ~$14–15.7B on $31M revenue, closed roughly flat day one — appetite exists but is no longer indiscriminate. FORM $116.56 and COHR $319.44 (−27% off highs, well above 200-day) run on AI/HBM and datacom revenue, quantum is free optionality — though FormFactor's systems segment (housing cryo) *declined* ~20% last quarter.

**Tripwires:**
- NQI Reauthorization signed with FY26/27 appropriations actually attached → toward TAILWIND; bill dies in the House or appropriations far below $85M/yr → HEADWIND.
- QNT sustains >$60 IPO price 30+ days AND IONQ/RGTI/QBTS reclaim 50-day averages (~$55/$20/$23.5) → TAILWIND; QNT meaningfully below $60 → confirms HEADWIND for all quantum paper.
- DARPA QBI Stage C (~late 2026): IonQ/Quantinuum advancing → TAILWIND for selected names; IonQ dropped → sharp HEADWIND.
- Rigetti's $100M CHIPS LOI converts to a definitive funded award — or lapses; and/or any single named *commercial* contract >$50M sector-wide → first real enterprise-demand signal.

**Basket implication:** producers/suppliers (FORM, COHR) over developers; IONQ/RGTI/QBTS are a policy-flow trade, not a revenue trade — volatility sleeve, sized small, QBI Stage C the key catalyst/risk date. QNT is the sector's institutional benchmark — monitor even if not held.

**Gaps flagged by the agent:** full-House status of H.R.8462 unverified between May 1 and this run; IonQ AFRL figure needs 8-K confirmation; China budget unquantifiable; FORM/COHR quantum revenue not broken out; P/S ratios stale by ~6 weeks.

---

## §4 — Standing watch-item: lithium re-entry tripwire

Lithium/battery-chain names are **excluded from the basket at launch per spec** (2026-07-02 decision: structural oversupply). The re-entry condition is a named regime tripwire, not a judgment call:

> **Re-entry tripwire:** sustained spot lithium (carbonate/hydroxide) above the marginal producer's cited incentive price → revisit the exclusion in the next Lane A debate cycle.

**Status this run: not yet monitored — added when the basket's first Lane A debate needs it.** None of the six research agents surfaced a lithium spot or incentive-price figure in this pass (lithium was outside all six briefs), so no current spot/incentive status is recorded and none is invented here. When monitoring begins, the dial follows the same rules as §2: spot from cited assessments (Fastmarkets/SMM/Benchmark as reported in press — lithium is not a reliable FMP commodity), incentive = cited feasibility/analyst consensus, never invented; "sustained" = the condition holding across two consecutive bi-weekly runs.

---

## §5 — Tripwire status board (this run)

First run — **no prior baseline to diff against; 0 tripwires breached** (none of the six agents found an already-breached condition). The per-chain tripwires in §3 are the baseline the next run checks. Items already *pending/live* rather than breached, for the next run to resolve first:

| Chain | Live pending item | Due |
|---|---|---|
| copper_electrification | Presidential refined-copper tariff decision (Commerce report was due Jun 30, 2026; no ruling found as of this run) | days–weeks |
| rare_earth_strategic | China MIIT H2-2026 RE quota (typically issued Jun/Jul; unconfirmed as of this run) | imminent |
| robotics_automation | Tesla Optimus Fremont production start ("late July/August 2026"); ROK FQ3 / CGNX Q2 reports | ~Aug 2026 |
| quantum | H.R.8462 full-House status; DARPA QBI Stage C | H2 2026 |
| rare_earth_strategic | Ga/Ge/antimony export-ban suspension expiry | Nov 27, 2026 |
| uranium_fuel_cycle | Russian-ban waiver terminal date | Jan 1, 2028 |

---

## §6 — Cadence & change log

**Schedule:** bi-weekly, a scheduled task cloned from `catalyst-watch-regime-refresh`, ≥13-day self-gating floor (see FUTURE_RESOURCES_SPEC.md §7). Each run appends a new §3 instance, refreshes §4/§5, rewrites `regime_state.json`, and adds a row below.

| Run date | Verdicts (U/Cu/RE/Power/Robo/Q) | Tripwires breached | Notable hooks |
|---|---|---|---|
| 2026-07-10 (v1, first run — 6-agent live-verified investigation; baseline, no prior instance to diff) | TAILWIND / TAILWIND / TAILWIND / TAILWIND / TAILWIND / NEUTRAL | none (first run — baseline established) | Copper refined-tariff decision pending (MS 43%); China H2 RE quota pending; GEV 83→100 GW slots in one quarter; PJM cleared at FERC cap $329.17/MW-day; uranium term $93–94 = 18-yr high vs spot $85 consolidation; quantum = improving substance under deflating multiple (QNT flat debut); lithium re-entry tripwire logged as not-yet-monitored |

---

*Full agent transcripts for this run live in the session that produced this doc. Sources are cited inline per chain in §3 — the doc deliberately carries no figure without an agent citation; unverifiable figures are tagged in each chain's "Gaps" note rather than presented as fact.*
