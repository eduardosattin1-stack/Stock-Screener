# Future Resources — Commodity / Power / Machine Regime & Operating Environment

**Status:** Living document · regenerated bi-weekly · companion to [FUTURE_RESOURCES_SPEC.md](FUTURE_RESOURCES_SPEC.md)
**Last run:** — (SKELETON, Phase 2; the first bi-weekly research run appends the first §4 instance) · **Version:** v0 (skeleton)
**Relationship:** [FUTURE_RESOURCES_SPEC.md](FUTURE_RESOURCES_SPEC.md) decides the *structure* (two lanes, chain taxonomy, torque metrics, sizing gates) on first principles. **This doc supplies the perishable, time-varying evidence of where each chain sits in its cycle — and the tripwires that would flip a verdict.** The commodity/power cycles are slower and more legible than the deal windows the Catalyst Watch regime doc tracks, so the read is per-chain, not one market-wide call. Structural model and rigor: [CATALYST_WATCH_REGIME.md](CATALYST_WATCH_REGIME.md).

---

## §0 — Why this layer exists

The Lane A debate scores a name's *company-specific* cost-curve position, contract book, and capital discipline. None of that tells the Director whether the **chain itself** is in a tailwind or a headwind right now — whether uranium term-contracting is re-opening, whether copper inventories are drawing, whether the humanoid order cycle has actually turned, whether the quantum funding cycle is cresting. A cost-curve-cheap producer in a chain rolling over is a value trap with torque pointed the wrong way; the same producer into a tightening term cycle is the trade.

So this doc does three things, per chain:
1. **Reads each chain's cycle** through a fixed dial set (§2) and assigns a verdict — **TAILWIND / NEUTRAL / HEADWIND** (§3).
2. **Records the dated, cited evidence** behind each verdict — this run's instance in §4, prior instances appended below it (append-only).
3. **Names the tripwires** (§5) — the observable conditions that flip a verdict, **including the lithium re-entry tripwire** (the one excluded chain, watched for the day the oversupply clears).

**Core stance: commodity edge is a cycle bet with a citation, never a spot-price guess.** Uranium and NdPr spot are NOT FMP commodities — they carry a web citation (UxC / Numerco / SMM as reported in press) or a labeled proxy (SRUUF / U.UN trust NAV), or they do not appear (Do-NOT #8, never fabricate a spot). Copper is `HGUSD` and natural gas is `NGUSD` on FMP.

---

## §1 — How the regime maps to the Lane A decisions

The Lane A debate + Director read this doc's chain section. The mapping:

| Decision | Regime input that governs it | The chain is a TAILWIND when… |
|---|---|---|
| **Cost-curve / torque quality** (Director pillar 1) | Spot vs incentive price; where spot sits on the cost curve | Spot is above the marginal-producer incentive price and the futures curve backwardated — torque points UP and the low-cost quartile compounds. |
| **Contracting cycle & reserve life** (pillar 2) | Term-vs-spot state, inventories, term-contracting volume, offtake pace | Term contracting is re-opening at prices above spot (uranium's canonical tell), inventories drawing, offtakes signing. |
| **Capital discipline** (pillar 3) | Where the chain sits in the capex cycle (starved vs over-building) | The chain is capital-*starved* (a decade of under-investment) rather than mid-binge — discipline is rewarded, supply stays thin. |
| **Sizing / regime overlay** (Director hard constraint) | The chain verdict itself | A **HEADWIND chain caps `size_units <= 0.5` unless the Director writes an explicit justification** (deterministically checkable via the `chain_regime` field stamped into the grade input). |

**The torque metric is symmetric and so is the regime read:** a HEADWIND chain turns the same fcf_torque_10pct into downside. The Director must price the chain verdict into sizing, not just the name's cost-curve rank.

---

## §2 — Investigation protocol (reproducible — this is what the bi-weekly task re-runs)

Run **six parallel research agents** (`general-purpose`), **one per chain** in `backend/_opus_debate/future_resources_chains.json`, each told: *today's date; your training is stale, verify everything live; use WebSearch/WebFetch + load the FMP market-data MCP tools via ToolSearch; every spot/price figure carries a source + date or is dropped; lead with a BLUF; end with "Implications for Future Resources Lane A" + "Confidence & gaps."*

**The four commodity/power chains** (`uranium_fuel_cycle`, `copper_electrification`, `rare_earth_strategic`, `power_for_ai`) read this dial set:
- **Spot vs incentive price** — the current spot AND the marginal-producer incentive price (the price that clears new supply). The incentive price is **CITED** from a feasibility study / analyst consensus, **never invented**. `vs_incentive_pct = (spot / incentive - 1) * 100`.
- **Inventories** — reported stockpiles / days-of-consumption and the direction (drawing vs building).
- **Term-contracting state** — for uranium the term-vs-spot spread and annual contracting volume (the canonical cycle tell); for the others, offtake / long-term-contract pace.
- **Futures-curve shape** — contango vs backwardation on the FMP commodity where one exists (`HGUSD` copper, `NGUSD` natural gas), else the term structure as reported.
- **COT positioning** — CFTC Commitments of Traders **IF the FMP plan tier serves it** (verify on the first live run; on failure COT stays agent-narrative-only, cited from the CFTC release).
- **Policy datelines** — export controls, Section 232, critical-minerals lists, DoD/DOE price floors and awards, interconnection-queue and PPA policy (the forced-buyer catalysts).

**Data reality (audited 2026-07-02):** copper (`HGUSD`) and natural gas (`NGUSD`) are FMP commodities; **uranium spot and NdPr are NOT** — agents web-source them with citations (UxC / Numerco / Shanghai Metals Market via press) or proxy via SRUUF / U.UN trust NAV, labeled a proxy. COT exists on FMP but is plan-tier-gated — on failure, narrative-only.

**The two machine chains** read a different dial set (no spot price — Do-NOT #8: pretending an ETF is one is a fabricated number):
- **robotics_automation** — the industrial-capex cycle (ISM/PMI new orders, machine-tool orders), humanoid-program datelines (named production starts), robot order/backlog trends.
- **quantum** — the government funding cycle (NQI reauthorization, DARPA/DOE/sovereign programs), the error-correction milestone track (logical-qubit / error-rate demos), enterprise/defense contract flow.

**Verdict per chain:** TAILWIND / NEUTRAL / HEADWIND, with the one-line reason and the dated evidence. Then update §4 (new dated instance, append-only), §3 (action mapping), §5 (tripwire check incl. the lithium re-entry line), the change log, and write the machine-readable sidecar `future_resources/regime_state.json` (§ below).

---

## §3 — Regime → action mapping (SKELETON — filled by the first §4 run)

Per chain, the verdict maps to Lane A sizing + the debate BRIEF:

- **TAILWIND** — the chain section tells the debate the cycle is supportive; no size cap from the regime (the name's own gates still bind). The Director may REACH within the chain caps.
- **NEUTRAL** — no regime tilt; size on the name's cost-curve / torque / balance-sheet merits alone.
- **HEADWIND** — the Director **must cap `size_units <= 0.5` for every name whose primary chain is HEADWIND, OR write an explicit justification** naming the name-specific reason it survives the chain headwind (a contracted book that is insulated from spot, a cost position so low the downside torque is bounded). This rule is enforced off the `chain_regime` field the grade-input builder stamps from the sidecar; it lives in the FR Director prompt as a hard constraint.

*(No live verdicts yet — the first bi-weekly research run writes the first mapping here alongside the §4 instance.)*

---

## §4 — Dated instances (APPEND-ONLY — empty until the first research run)
| 2026-07-11 | copper_electrification | NEUTRAL | HG $6.28/lb (FMP HGUSD 2026-07-10) ~= $13.8k/t, -31% vs >$20k/t greenfield incentive (Crux Investor 2026-02-18); COMEX stocks record 652kt, visible +870kt since early-2025, Macquarie surpluses 262kt 2026e / >700kt-yr 2027-28e (IndexBox 2026-07-09); LME curve flipped to backwardation 2026-06-03 (SMM); COT spec net long +64k easing (CFTC 2026-07-07); S232 restructure eff 2026-04-06, refined-Cu phased tariff pending post-2026-06-30 review | Price strength is tariff/financial-flow-driven while the physical market builds stock in surplus; spot below incentive blocks new supply - neither the TAILWIND gates nor the building-stocks+contango HEADWIND tripwire fully met |
| 2026-07-11 | power_for_ai | TAILWIND | NG $2.94/MMBtu (FMP NGUSD 2026-07-11); EIA storage +6.6% vs 5-yr avg (wk 2026-07-03); PJM 26/27 BRA cleared at $329.17/MW-day cap, +22% (Utility Dive 2025-07-22; 28/29 results 2026-07-14); ~2,600 GW queue, ~5-yr waits (LBNL/enkiai 2026); >9.8 GW hyperscaler nuclear PPAs (smrintel 2026-05); COT NG specs net short -165k (CFTC via FMP 2026-07-07) | Queue-bound demand + firming gigawatt PPAs + cheap fuel = wide spark spreads; no PPA pause, no gas spike; no cited incentive price so vs_incentive omitted |
| 2026-07-11 | quantum | TAILWIND | no spot (machine chain); EOs 2026-06-22 QC-ADDS + DOE Quantum Genesis (whitehouse.gov/energy.gov); ~$2B CHIPS quantum May-2026 incl. $100M LOIs QBTS (8-K 05-21) + RGTI (8-K, sec.gov); NQI reauth S.3597 passed Senate Commerce cmte / H.R.8462 out of House Science 04-29 (congress.gov); DARPA QBI 11 teams Stage B (darpa.mil 2025-11-06); MSFT+Quantinuum 800x EC peer-reviewed Nature 2026-06-10; QTUM $154.46 proxy (FMP 07-10) | Funding renewal + first peer-reviewed EC demo both fired the tailwind trigger; caveats: NQI not yet enacted, CHIPS LOIs non-definitive, pure-play valuations stretched — tailwind is partly priced, sizing discipline stays on the name gates |
| 2026-07-11 | rare_earth_strategic | TAILWIND | Pr-Nd oxide $90.32/kg (SMM 2026-06-01); NdPr alloy $133.02/kg +21.4% m/m (SMM 2026-07-01); -17.9% vs DoD $110/kg floor (DoD-MP 2025-07); MOFCOM entity-lists MP+USAR 2026-06-22; Project Vault $12B 2026-02-02; suspension expiry 2026-11-10 | Forced-buyer policy stack (floor + reserve + floored 15-yr offtakes) plus China escalation reprices ex-China supply - tailwind on policy, not spot, with spot converging toward the floor |
| 2026-07-11 | robotics_automation | TAILWIND | ISM PMI 53.3 / new orders 56.0, 6th mo expanding (ISM, 2026-07-01); Japan machine-tool orders +37.4% YoY May-26 (JMTBA via Trading Economics); NA robot orders Q1-26 flat, -0.1% units / -6.4% rev (A3, 2026-05-11); Optimus V3 low-vol production Fremont summer-26 + Figure 02/Apollo pilot shipments Q2-26 (RivCut/Tesery/eWeek) | Capex orders in a six-month expansion streak plus the first dated humanoid production starts turn the cycle supportive; flat NA robot orders (auto-OEM drag) tempers but does not offset it |
| 2026-07-11 | uranium_fuel_cycle | TAILWIND | spot $85.75/lb (Trading Economics 2026-07-10; UxC/TradeTech m-e avg $85.00 via Cameco 2026-06-30); term $95.50/lb (same, 18-yr high) = +12.4% term premium; incentive $75-90/lb (Discovery Alert 2026 analyst range); 2025 contracting 116 Mlbs, Q4 72 Mlbs (UxC via Sprott); DOE $2.7B enrichment 2026-01-05 + Sec-232 2026-01-14 + Centrus >$1B DOE contract 2026-07-10 | Term cycle re-opened at term>spot with term at 18-yr highs while greenfield supply stays starved and US policy creates forced buyers |

> The bi-weekly protocol (§2) appends a new dated instance at the TOP of this section each run — one block
> per run, each carrying the six chain verdicts with cited spot/incentive figures, the dial readings, and
> the diff vs the prior instance. Prior instances are never edited or deleted (the honest-rails rule: a
> regime read is perishable, but its history is the track record of the call).

*(No instances yet — this is the Phase-2 skeleton. The first run populates it and the sidecar together.)*

<!--
TEMPLATE for the first run (copy, fill, cite, place ABOVE this comment):

### YYYY-MM-DD — <bi-weekly | manual> run (v1) · *live-verified; every spot/incentive figure cited + dated*

**BLUF:** <one line — which chains are tailwind/headwind and the single biggest mover this run>

| Chain | Verdict | Spot (cited) | vs incentive | One-liner | Key dated hooks |
|---|---|---|---|---|---|
| uranium_fuel_cycle | TAILWIND/NEUTRAL/HEADWIND | $NN/lb (UxC, YYYY-MM-DD) | +NN% | … | … |
| copper_electrification | … | $N.NN/lb (HGUSD, YYYY-MM-DD) | … | … | … |
| rare_earth_strategic | … | NdPr $NN/kg (SMM via press, YYYY-MM-DD) | … | … | … |
| power_for_ai | … | (spark spread; NGUSD fuel cost) | … | … | … |
| robotics_automation | … | (no spot — PMI / order dials) | n/a | … | … |
| quantum | … | (no spot — funding / EC dials) | n/a | … | … |

**Chain notes:** <per-chain dial detail: inventories, term-contracting, futures curve, COT, policy datelines>
**Diff vs prior:** <what moved and why>
-->

---

## §5 — Tripwires (what would flip a chain verdict)

Each bi-weekly run checks these; a breach is a methodology event, not a footnote. **The lithium re-entry line is the standing watch on the one deliberately-excluded chain.**

| Tripwire | Chain | Observable | If breached → |
|---|---|---|---|
| **Uranium term cycle re-opens / stalls** | uranium_fuel_cycle | Term-vs-spot spread + annual term-contracting volume (UxC); utility RFP pace | Re-open at term > spot ⇒ TAILWIND (contracted producers re-rate); a stall / term below spot ⇒ HEADWIND. |
| **Copper inventory / curve flip** | copper_electrification | `HGUSD` spot vs incentive (~cited), LME+COMEX+SHFE inventory direction, curve contango⇄backwardation | Drawing inventories + backwardation + spot > incentive ⇒ TAILWIND; building inventories + contango ⇒ HEADWIND (downside torque). |
| **Rare-earth policy repricing** | rare_earth_strategic | Export-control / Section-232 actions, DoD/DOE price floors & awards, NdPr spot (SMM via press) | A forced-buyer action (price floor, stockpile, award) ⇒ TAILWIND on policy, not spot; an export-control *relaxation* ⇒ HEADWIND. |
| **Power demand vs interconnection** | power_for_ai | Datacenter load-growth vs interconnection-queue clearance, PPA signing pace, `NGUSD` spark-spread | Queue-bound demand + firming PPAs ⇒ TAILWIND; a hyperscaler PPA-appetite pause or a gas-price spike compressing spark spreads ⇒ HEADWIND. |
| **Industrial-capex / humanoid cycle** | robotics_automation | ISM/PMI new orders, machine-tool orders, humanoid production-start datelines, robot backlog | Orders inflecting up + a dated humanoid production start ⇒ TAILWIND; a capex air-pocket (PMI < 50, backlog rolling over) ⇒ HEADWIND. |
| **Quantum funding / EC milestone** | quantum | NQI reauthorization + DARPA/DOE/sovereign funding flow, error-correction milestone track, enterprise/defense contract flow | A funding renewal or a real error-correction demo ⇒ TAILWIND; a funding-cycle trough or a milestone slip ⇒ HEADWIND (the pre-FCF names de-rate hardest). |
| **LITHIUM re-entry (excluded chain watch)** | *lithium (excluded)* | Sustained spot > marginal-producer incentive price (cited); oversupply clearing (inventory draw, curtailment reversals) | **Sustained spot > incentive ⇒ revisit the exclusion** — propose lithium/battery as a new chain in `future_resources_chains.json` (config edit + version bump), only if it can pass the physical-anchor rule. Until then, lithium stays OUT (spec header + §0.1). |

---

## §6 — Cadence & change log

**Schedule (Phase 6, spec §7):** bi-weekly, a scheduled task cloned from `catalyst-watch-regime-refresh`, self-gating to a **≥13-day floor** since the most recent §4 instance (so a Monday cron runs every *other* Monday). Each run appends a §4 instance, refreshes §3/§5, rewrites the sidecar, and adds a change-log row below. **This is the ONE genuinely new scheduled artifact the Future Resources build introduces** (everything else rides an existing cadence).

| Run date | Per-chain one-liner | Verdicts (U / Cu / RE / Pwr / Robo / Qtm) | Tripwires breached | Notable dated hooks |
|---|---|---|---|---|
| — (skeleton, Phase 2) | *no live run yet* | — | — | first run populates §4 + the sidecar |

**Change log:**
- 2026-07-11 (v0, Phase 2) — skeleton created: full §2 protocol (6 agents, per-chain dial sets, data-reality note), §5 tripwire table incl. the lithium re-entry line, empty §4 (append-only), sidecar template. No live verdicts — the first bi-weekly research run writes them.

---

## §7 — Machine-readable sidecar

`future_resources/regime_state.json` — the debate + grade-input builder read this so the Director can enforce the HEADWIND size rule deterministically. Schema, one entry per chain id:

```json
{
  "<chain_id>": {
    "state": "TAILWIND | NEUTRAL | HEADWIND",
    "spot": "cited spot string or null (uranium/NdPr carry a citation or stay null — Do-NOT #8)",
    "vs_incentive_pct": 0.0,
    "one_liner": "the cycle read in one sentence",
    "tripwires_breached": [],
    "as_of": "YYYY-MM-DD"
  }
}
```

The skeleton sidecar ships every chain at `NEUTRAL` with `as_of: null` and a note that no live run has populated it — it PARSES (so the grade-input builder never crashes) but tilts nothing until the first research run overwrites it.
