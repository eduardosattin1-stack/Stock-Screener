# Catalyst Watch — Methodology & Operating Manual

*Last updated 2026-06-08. Describes the system as built and currently running on `ux-revamp` (local, unmerged).*

---

## 1. What Catalyst Watch is

Catalyst Watch is an **event-driven / special-situations screen**. It does one job: maintain a **tracked basket of stocks that have a real, dated, forward catalyst** — a specific upcoming event (a deal close, a spin distribution, an FDA decision, a tender, a forced-seller overhang clearing) that can re-rate the stock on its own schedule, largely independent of the broad market.

It is **not** the composite screener (`/`), which ranks the whole universe on a 13-factor quality/value/technical blend. Catalyst Watch ignores all of that. A cheap, high-quality stock with no upcoming event scores **zero** here. An expensive, mediocre business with a signed take-private at a 30% spread scores high.

The output is a living watchlist (`/catalysts` tab → **231 names** today), each carrying a score, a tier, a lane, a dated milestone, an edge read, a primary-source citation, and a live options read.

### The one principle that drives everything: **score ≠ edge**

These are two *different axes* and the system keeps them separate:

| Axis | Question it answers | Range |
|---|---|---|
| **Catalyst score** (a.k.a. catalyst density) | *Is there a real, dated, forward event here, and how hard/clean is it?* | 0–10 |
| **Edge** | *How much mispricing is left to capture — or has the market already priced it?* | High / Med / Low |

A merger can be **completely real** (score 8: signed, named acquirer, shareholder-approved) yet have **no edge** (trading at a 0.3% spread — the market has fully priced the close). The score tells you the event is genuine; the edge tells you whether it's *actionable*. Conflating the two is the classic special-sits error, and the whole design exists to prevent it.

---

## 2. The gate: what qualifies as a catalyst

Catalyst is a **gate, not a weighted factor.** A name either has a qualifying catalyst or it doesn't — there is no partial credit, no "0.4 of a catalyst" blended into a composite. To pass the gate, a setup must clear **all four** filters:

1. **Real & specific** — an actual named event, not a vibe or a hope.
2. **Dated & forward** — it has a timeline and **has not happened yet**. The single most common kill is *fired* — the catalyst already occurred and the stock already re-rated.
3. **Idiosyncratic, not a macro bet** — it resolves on its own driver (deal vote, FDA panel, permit ruling), not on rates/oil/the tape.
4. **Clears the Bloom quality gates** (below).

### The three Bloom gates (the quality bar)

A qualifying catalyst must satisfy as many of these as possible; the count drives the score.

| Gate | Requirement | Fails when… |
|---|---|---|
| **G1 — named counterparty with leverage** | A specific actor is on the hook: a named acquirer, an activist with a stake, a regulator with a docket, a partner with a signed JV. | The "buyer" is unnamed ("a European company"), or it's just "the market." |
| **G2 — concrete commitment** | A binding, public action: a signed merger agreement, a board-declared special dividend, a filed Form 10, a definitive sale. | Only *intent* exists — "exploring alternatives", "considering a review." |
| **G3 — specific, currently-unpriced figure** | A hard number the market hasn't reflected: a deal price, a spread, a special-div per share, a quantified SOTP gap. | The figure is already in the price (deal trading at terms), or there's no number at all. |

**Everything that fails the gate scores 0–3 and is dropped.** In practice ~85% of any universe slice gates out at first pass.

---

## 3. Hunting grounds (lanes)

Catalysts aren't uniform — they cluster into recognizable *lanes*, and the screen **deliberately tilts** toward the lanes with the best structural asymmetry. Ranked by priority:

1. **Forced-seller overhang** *(highest priority)* — a forced/large seller suppresses the underlying; you own the suppressed stock and time the **clearing** of the overhang, which re-rates it. (The overhang *creates* the opportunity; once it clears, the stock re-rates — the DHER/overhang playbook.)
2. **Spin-offs** — orphaned post-spin forced selling, SOTP unlock, RemainCo re-rating.
3. **Distressed / restructuring / LME** — a dated balance-sheet milestone (refi, asset sale, deleveraging trigger).
4. **Mechanical index flows** — forced rebalancing buys/sells on a known date.
5. **Activist + structural** — an activist hardening a trigger toward a sale/split/board change.
6. **Complicated merger-arb** — deals where the spread reflects **real, analyzable risk** (antitrust, cross-border, contested vote) — *not* clean cash arbs already at 1%.
7. **Capital-return / deleveraging** — tender, special dividend, dated paydown.
8. **Supply-shortage + timing-moat** — a structural shortage the company is uniquely positioned to fill on a timeline (the Bloom Energy playbook).
9. **Bio-as-convergence** — a dated binary (PDUFA / pivotal readout) **with mispriced asymmetry**, not a 50/50 coin-flip.

Two corollaries the lanes encode:
- **Window = expression.** The catalyst's time horizon dictates the instrument: a near-dated binary favors defined-risk options; a 12-month structural unlock favors equity.
- **Resolution-driver independence = conviction.** Size up when the catalyst resolves on its *own* driver (a deal close can't be undone by a market selloff); size down when the "catalyst" is really a market-beta bet wearing an event costume.

Current board lane mix (top): merger-arb ≈ 49, dated binary/PDUFA ≈ 38, spin-off ≈ 14, activist ≈ 12, distressed ≈ 9, supply-shortage ≈ 5.

---

## 4. Scoring (0–10) and tiers

Once a name passes the gate, the score reflects **how strong, clean, and imminent** the catalyst is — *not* how cheap the stock is and *not* the edge.

### The rubric

| Score | Meaning | Typical tier |
|---|---|---|
| **0–2** | No catalyst. | NONE (dropped) |
| **3–4** | Vague, already priced, or **fired**. | NONE / low WATCH |
| **5–6** | One real dated catalyst. | WATCH / ACTIVE |
| **7–8** | Strong dated catalyst, **≥2 Bloom gates**, near-term. | ACTIVE |
| **9–10** | Multiple imminent, hard catalysts converging. | ACTIVE |

Two modifiers nudge within a band:
- **Convergence** — multiple independent catalysts stacking on one name raises the score (and conviction).
- **Options confirmation** — the options market corroborating the setup (elevated IV, directional skew, unusual flow into the date) is a mild confirm; it can nudge up but never *manufactures* a score.

### The tiers

| Tier | Definition | Posture |
|---|---|---|
| **ACTIVE** | Live, dated, forward catalyst, not fired, clears the gate cleanly. | Actionable now — check edge at entry. |
| **WATCH** | Real catalyst but soft-dated, partly priced, or awaiting a trigger to harden. | Monitor; escalate to ACTIVE as the date/figure firms. |
| **CONTINGENT** | Catalyst conditional on a prior event resolving first. | Watch the upstream trigger. |
| **NONE** | Failed the gate. | Dropped — never reaches the board. |

---

## 5. How it ranks stocks

Ranking is **by catalyst score (density), descending, within tier** — ACTIVE above WATCH above CONTINGENT. The board is sorted so the strongest, most imminent, best-gated catalysts surface first.

**Edge is applied as a separate overlay, not folded into the rank.** This is deliberate: the rank tells you *where the real events are*; edge — which is **perishable** and must be re-checked at the moment of entry (a spread that was 8% last week can be 1% today) — tells you *which of those are still worth acting on*. Burning edge into the score would freeze a moving quantity and reintroduce exactly the conflation the system avoids.

So the workflow is: **rank by score → scan top tiers → check edge at entry → size by resolution-driver independence.**

---

## 6. Filtering: the funnel

Scores are produced by a **3-tier adversarial pipeline** run by Opus-4.8 agents over the full universe. Each tier is a progressively harsher filter:

```
  UNIVERSE  ──────────────►  2,961 names
     │  SCAN (fast triage, batched)
     │  gate hard; rubric defaults LOW; most → NONE
     ▼
  SURVIVORS ─────────────►  ~13% pass (score ≥5, dated, not-fired)
     │  DEEP (focused dossier per survivor)
     │  strict re-gate vs primary sources; Bloom gates; edge; cite source+date
     ▼
  DOSSIERS  ─────────────►  demoted/confirmed; ~half of ACTIVE flags survive
     │  SKEPTIC (adversarial refute on every ACTIVE)
     │  default REFUTED unless primary-source-confirmed; attack fired/date/terms/thesis/tradeability
     ▼
  BOARD     ─────────────►  inject if tier ∈ {ACTIVE, WATCH} AND score ≥ 4
```

**Why three tiers and not one?** Even a strong single-pass model systematically **over-rates** discovery finds — it reads "there's a deal!" and scores it 8 without checking whether the spread already collapsed, the readout already printed, or the figure was hallucinated from a recycled article. The **skeptic tier is non-negotiable**: in this build it demoted or killed ~40–50% of ACTIVE flags, catching:
- paused rumors scored as live deals (e.g. SBAC 9 → 2.5, KKR talks paused),
- already-fired catalysts (RVMD 7 → 2, readout printed, stock +340%),
- collapsed spreads (deals trading *through* terms),
- stale theses (a 2014 activism episode misread as 2026),
- and at least one **hallucinated** figure (a $14 special dividend that couldn't coexist with a $6 stock).

The board is the post-skeptic survivor set, merged with a small hand-verified set, deduped (manual > widen > sweep).

---

## 7. Options confirmation layer

Each name carries a live **options read** (pulled read-only from IBKR), shown on the detail panel and exported:

- **ATM IV** — implied volatility level (is the market pricing an event?),
- **P/C Ratio** — put/call *volume* (positioning/skew of flow),
- **Implied Move** — 1σ 30-day move implied by IV,
- **Sentiment flag + interpretation** — synthesized read (e.g. *"Elevated IV · put-heavy flow"*).

This is a **confirmation overlay, not a driver** — it corroborates or flags a catalyst (IV running 3–4× normal into a PDUFA is a tell; dead options into a "live" deal is a warning), but it never creates a score. Coverage: 178 / 231 names (foreign/illiquid names lack US-listed options). *Note: 25-delta skew, term structure, and total OI are blank — the current feed has no option-chain endpoint, so those three microstructure fields are unavailable.*

---

## 8. Expected result

What the methodology should — and does — produce:

**A heavily-filtered, adversarially-verified basket.** Of 2,961 names screened, **231** reach the board (~92% rejected). The survivors are concentrated in the high-asymmetry lanes (merger-arb, dated binaries, spins, distressed, activist).

**Current board shape:**

| | Count |
|---|---|
| **Total candidates** | **231** |
| ACTIVE | 87 |
| WATCH | 143 |
| CONTINGENT | 1 |
| With live options | 178 |

**Score distribution (the top is legitimately sparse):**

| Score band | Names |
|---|---|
| 8.0+ | 6 |
| 7.0–7.9 | 30 |
| 6.0–6.9 | 62 |
| 5.0–5.9 | 79 |
| 4.0–4.9 | 50 |

The **8+ tier is deliberately thin** (AMLX, CELC, DFTX, FIP, NSC, VERA) — a 9–10 requires *multiple imminent hard* catalysts converging, which is rare and should be. A board that's top-heavy would mean the gate is too loose.

**What the output is — and is not:**
- ✅ It **is** a ranked hunting ground: where the real, dated, forward, idiosyncratic events are right now, each verified against primary sources and stress-tested by a skeptic.
- ❌ It is **not** a buy list. The score says the *event* is real; **edge is perishable and must be re-checked at entry**. A score-8 merger at a 0.3% spread is real and un-actionable simultaneously.
- ❌ It is **not** a quality/value screen. Cheapness, growth, and technicals are irrelevant here by design.

**Maintenance.** Catalysts decay — they fire, spreads collapse, dates slip. The basket is meant to be **re-verified on a cadence** (target: weekly, Fridays post-US-close), re-running the sweep so fired names drop, spreads refresh, and new setups enter. A catalyst board is only as good as its last verification date.

---

## 9. Pipeline & data map (for maintainers)

| Concern | Where |
|---|---|
| Sweep engine (scan→deep→skeptic, chunked) | `backend/_sweep_pipe.py` (+ `_sweep_results/chunkN_workflow.js`) |
| Accumulated survivors | `backend/_sweep_board.json` |
| Generated frontend data | `frontend/app/data/catalystBoardSweep.ts` (auto-gen; do not hand-edit) |
| Hand-verified sets | `catalystBoard.ts` (manual), `catalystBoardWiden.ts` (widen) |
| Detail page (the dossier UI) | `frontend/app/catalysts/page.tsx`, `frontend/app/stock/[symbol]/page.tsx` |
| Routes (local-first, dedup) | `app/api/catalysts/{scan,candidates}/route.ts` |
| Options pull (IBKR, read-only) | `backend/_options_fetch_gen.py` → `_opt_fetch_workflow.js` → `_options_inject.py` |
| Full export | `backend/_export_candidates.py` → `catalyst_candidates_231.{json,csv}` |

**Scoring is produced by Opus-4.8 agent judgment against the rubric above, then adversarially verified — not a closed-form formula.** A future mechanical scorer (`CATALYST_SCORING_REBUILD.md`) is specced but not yet wired; until then the agents *are* the scorer, which is why the skeptic tier carries the reliability load.
