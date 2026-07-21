# Catalyst Watch — Methodology & Scoring Rebuild

**Status:** §1 methodology locked (pending Bruno's veto on the ⚑ refinements) · mechanics derive from it
**Date:** 2026-06-05 · **Version:** v4 (methodology-first)
**Lineage:** v1/v2/v3 were "fix the broken number." v4 puts the *methodology* first — the number is downstream of it.

---

## §1 — Methodology (the *what & why*)

### 1.1 What Catalyst Watch is
An **event-driven / special-situations** sleeve. The bet: markets misprice stocks ahead of *specific, identifiable, near-term events that force a re-rating*. Not forecasting fundamentals three years out (the compounder sleeve), not riding trend (momentum) — identifying a discrete event with a date and a mechanism, before the market fully discounts it, and capturing the re-rating. The *"Loeb score"* name is the lineage: Dan Loeb / event-driven catalyst investing.

### 1.2 The central distinction — **score ≠ edge** (two axes, not one)
The old design forced one number to do two jobs. It can't.
- **Catalyst score** = how *good* the catalyst is — specific, dated, asymmetric, hard.
- **Edge** = how much of it the market *hasn't done yet* — informational / structural / attention.

A clean PDUFA date scores **9 on score and ~0 on edge** (every biotech desk is already on it). A messy forced-seller in an underfollowed name scores maybe **6 on score but carries most of the alpha**. Conflating them is *why* the system both inflated on clean catalysts and missed where the money is. **Separate them and the universe (#2), the gate (#1), the window (#3), and sizing (#4) all get cleaner.**

### 1.3 The catalyst is a **gate**, not a weighted input — and there are **two tiers**
No real, dated, *forward* catalyst → **capped low or excluded, regardless of convergence**. Convergence and confirmation only operate *above* the floor. "A 6 lifted to 8" is still additive thinking; the honest structure is binary admission, then multipliers.

What keeps the gate workable rather than brutal is **two tiers**:
- **Watch tier** — high-convergence names whose catalyst is still *soft* (activist took a stake; breakup implied, not committed). Tracked for the catalyst to **harden**. *This is where the speed edge lives.*
- **Active tier** — catalyst is *hard, dated, mechanism already in motion*. These get **sized**.

DHER pre-Prosus-sale was **active** (legally compelled divestiture, bounded timing). A name where an activist *might* push for a spin stays **watch** until the 13D lands with specific demands.

**Macro-dependent ≠ catalyst.** A thesis whose resolution *requires a macro move* — a Fed cut, an oil reversal, a multiple re-rate — is a macro bet in a catalyst's clothes; it fails the gate (or sits in **watch** until a company-specific trigger dates it). "Rates will rescue the balance sheet" is the canonical trap (it's also why the distressed lane, §1.4, is played on restructuring *terms*, not on the cycle turning).

> ⚑ **Refinement 3 (Claude) — the watch→active *hardening event* is the product.** The speed edge is entirely in catching the moment a soft catalyst hardens (13D with specific demands · divestiture *ordered* · definitive agreement · Form 10 filed). Each watch line carries an explicit **"what hardens this, is it dated"** field, and the system's primary daily alert is **"X moved watch→active"** — not the score deltas.

### 1.4 The hunting ground — **edge governs the universe** (tilt deliberately)
Agnosticism sounds principled but wastes the edge — it fills the book with high-score, low-edge names everyone already prices. Edge stacks where the catalyst is **multi-domain** (synthesis across legal + strategic + financial — *not* three flavors of "cheap") and **coverage is thin**. The lane *menu*, structurally ranked by where breadth + convergence + speed compound (which lane is fattest *this month* is the regime doc's call — §4.D):

1. **Forced sellers / regulator-mandated divestitures** — the DHER archetype. Mechanism certain, timing bounded; the second-order read (who buys the stake, what it signals) needs synthesis. **Highest edge** — and the *underfollowed beneficiaries of the forced flow* especially.
2. **Spinoffs / split-offs** — durable structural mispricing (forced index selling, orphaned smallcos); few read the Form 10. The "actually read the 10" edge is real.
3. **Activist + structural** — high edge, soft timing; lives in the **watch** tier until it hardens.
4. **Complicated merger-arb** — *not* vanilla arb (priced), but deals with a regulatory wrinkle, financing question, or competing-bid path where the spread misprices the probability tree.
5. **Distressed / restructuring / liability-management** — the *fattest-but-hardest* lane: Chapter 11, creditor fights, LMEs are the most document-heavy and least-covered, so the breadth edge is largest — but also the most macro-exposed. **Play the catalyst** (restructuring terms, fulcrum security, emergence equity), never a "rates will rescue it" bet (that's macro — §1.3 gates it out). The 2026–29 leveraged maturity wall is the structural supply engine. *(The 2026-06-05 regime read ranks this #1 fattest — §4.D.)*
6. **Mechanical index flows** — calendar-forced buying/selling (Russell reconstitution, fast-track index inclusion). Near-zero informational edge in the *headline* name (everyone sees the calendar); the edge is in the **displaced / beneficiary** names around the flow.

**Hard binary (PDUFA, trial readouts): deprioritized as a primary lane, kept as a valid convergence track.** Don't hunt them — but if a name you already like for special-sits reasons *also* has a readout, that's a legitimate independent track.

> **Evidence base (dated, refreshed monthly):** this tilt is asserted here on first principles. The *time-varying* evidence that it's right — M&A/regulatory window, distressed cycle, lane efficiency — lives in [CATALYST_WATCH_REGIME.md](CATALYST_WATCH_REGIME.md), which a scheduled task regenerates on the 8th of each month and which names the tripwires that would flip the tilt. The 2026-06-05 baseline (§4.D) ranks fertility **distressed/LME → spins → forced-sellers → activism (feeder) → merger-arb → PDUFA (thinnest)** — distressed leads *this* regime because the maturity wall is forcing supply; the firmest cross-regime prior is PDUFA-thinnest, which two agents independently confirmed.

> **Structural consequence:** there is a **universe / where-we-hunt layer *upstream* of scoring** (the current code lacks this — it scores whatever's in the candidate list). If the score alone drives selection, you drown in clean-catalyst-no-edge names.

> ⚑ **Refinement (Claude) — surface the *beneficiary*, not just the seller.** In a forced-seller situation the highest-edge name is often the second-order beneficiary of the flow (the natural consolidator / stake buyer), which is a *different ticker* from the catalyst name and even thinner-covered. The universe layer should map beneficiaries.

### 1.5 The window is **tiered and tied to expression** (a risk parameter, not a screen)
Not a single number.
- **Active tier:** ~0–6 months, mechanism already in motion.
- **Watch tier:** 6–18 months, tracked for hardening.

0–90 days is too tight for this tilt — DHER's own arc (AGM, then a Q3/Q4 Baemin window) is 6+ months.

**The part that matters most:** window must match the *instrument*. A real catalyst too slow for the option you express it in is how you're directionally right and still lose — the exact signature of the call-spread positions that have hurt: thesis intact, underlying didn't move within the contract's life. **So window and expression are one decision** — tight near-term catalyst → short-dated, accept theta (timing near-certain); 6–12mo campaign → LEAPS or you bleed waiting. **Bake "does the expiry clear the catalyst date with margin?" into the gate itself.**

> ⚑ **Refinement (Claude, 2026-07-20) — the expiry must clear the *macro cluster*, not just the name's own date.** "Margin" was implicitly measured against the position's own catalyst. That fails when the regime doc identifies a **dated macro-event cluster** — several index-level binaries packed into days (the live instance: Jul 22 Paramount-ruling/EU-deadline/Prologis-PUSU/GOOGL-TSLA → Jul 24 tariff sunset → Jul 28–30 FOMC + four hyperscalers + PCE + GDP). Two failure modes inside a cluster: (a) a correct single-name re-rate is muted/delayed because index events absorb all attention; (b) a gap on an adverse macro print stops the position before its own catalyst ever fires — worst when vol is underpricing gap risk (VIX 18.5 against a breached oil tripwire). **Rule: for active-tier positions, the expiry/exit horizon must clear both the catalyst date *and* any regime-flagged cluster overlapping it, with margin; catalysts resolving inside a cluster are sized for an overnight-gap regime, not a grind regime.** The cluster dates themselves are perishable and live in [CATALYST_WATCH_REGIME.md](CATALYST_WATCH_REGIME.md) §3–§4; this rule is standing.

### 1.6 Convergence & confirmation **multiply above the gate**
- **Convergence** = multiple *independent* catalyst tracks on one name. Independence is the crux — regulatory + strategic + technical, *not* three flavors of "cheap." One hard track = neutral (a single legally-compelled divestiture is a complete thesis); independent multi-domain tracks lift conviction.
- **Confirmation** = options (backwardation, call skew, P/C, unusual volume), credit health, analyst dispersion. These *check* that smart money is positioning and the event is unpriced. They **nudge; they never manufacture**.

> ⚑ **Refinement 1 (Claude) — confirmation is centered at ×1.0, never a [0,1] multiplicand.** The thin-coverage names with the *most* edge are exactly the ones with *no* clean options/credit signal. If confirmation can zero the score, you delete your best names. **No signal ⇒ ×1.0** (neutral), not ×0. Same for convergence: floor at ×1.0, never a penalty for a single strong track.

### 1.7 The book is built for **resolution-driver independence**, not name-level score
The convergence/independence principle scales to the portfolio. Ten high-scoring names that all resolve on "EU regulatory stays benign / financing stays cheap / risk-on holds" isn't a diversified event book — it's **one macro bet in ten tickers**. That's how nominally independent de-SPAC and arb books drew down in unison in 2021–22: a hidden common factor under deals that looked uncorrelated. **Size to the independence of each catalyst's *resolution driver*, not the per-name score.** Event-driven downside is usually estimable (deal breaks → reverts to pre-deal level), and that floor should drive size **Kelly-style**.

**Operationally:** tag every active line with its single dominant *resolution driver* and cap aggregate book exposure to any one of them. *Which* factors are hot is perishable — the current dominant shared drivers (AI-capex, oil/Hormuz, EU-regulatory, financing-cost) are named and tripwired in [CATALYST_WATCH_REGIME.md](CATALYST_WATCH_REGIME.md) §4–§5; the structural rule lives here.

> ⚑ **Refinement (Claude, 2026-07-20) — a BREACHED tripwire tightens the cap; it doesn't just get named.** Naming a driver was previously the whole mechanism. The first live breach (oil/Hormuz, 2026-07-20: ceasefire dead, blockade reinstated, Brent +24% — with equity vol NOT confirming) showed the missing step: when the regime doc rules a shared driver's tripwire **BREACHED**, that driver's aggregate-exposure cap **halves** for as long as the breach stands, and any *new* entry whose resolution driver is the breached factor requires an explicit orthogonality check against the regime doc's breach playbook (deploy orthogonal-to-driver; hedged structures preferred while vol is cheap). A PARTIAL tripwire (both current: AI-capex, credit) changes nothing structurally — it is the watch state; only BREACHED moves the cap. Second-order rule from the same instance: when **two** shared drivers are simultaneously live (AI-capex + oil/Hormuz), independence is checked against *each* axis separately — a book can be clean on one and concentrated on the other.

### 1.8 The artifact that makes this a system, not a vibe — the **tracked forward basket**
Each line records: **catalyst / date / mechanism / gate status (watch|active) / resolution driver / bull-base-bear / expression + expiry / edge (attention) score**. It is the only way to get a **calibration record** — otherwise you can't tell whether the methodology works or you got lucky. (Ties into the forward-tracking infra already run for the methodologies.)

> ⚑ **Refinement 2 (Claude) — edge is perishable and measurable as *attention*.** "How much the market hasn't done yet" decays the instant anyone acts. Operationalize it as a staleness score from observables: coverage/analyst count, float & mcap (thin = more edge), price-hasn't-moved, options-not-yet-bid, news-volume-low. Track it as a number so its **decay** is visible — which doubles as an exit signal.

> ⚑ **Refinement (Claude, 2026-07-21) — residual capture is the score; unfired ≠ unpriced.** This refinement was written but never wired into the sweep, and the gap produced the week's two wrong answers: FIP (event real, numerator fake) and VISN (event real and *forward*, payoff already ~90% harvested — the second distribution was undeclared yet fully priced; the +$7→$20 re-rate and $10/sh cash went to Q1 holders). Now enforced in the sweep prompts as two mandatory numbers per dossier: **run-up % from the pre-catalyst base** and **remaining % to the provenance-checked resolution value** — score gates on the *remaining* number, and a mostly-harvested name caps at 4 regardless of event certainty. Corollary, the **entry-arc doctrine**: a bi-weekly pipeline structurally cannot win day-of binaries (they decay in hours); its winnable trade is the early-arc setup — catalyst just knowable, price unmoved, coverage thin — held through a convergence window *longer than the pipeline's latency*. Scan tier now ranks a fresh unmoved months-out structural setup above a famous fully-run next-week binary. Realized proof the gap was expensive: basket expected +46.5% vs captured 3% — that spread is the staleness-plus-already-priced tax, and the quarterly re-fit should penalize setup types by realized capture.

### 1.9 The scoring structure (the formula §1 implies)
```
SELECTION (not a score):   in_universe(edge_tilt)  ∧  gate_pass
GATE (binary):             real ∧ dated ∧ forward catalyst
                           ∧ expiry_clears_catalyst_date(margin)
                           ∧ ¬fired ∧ ¬fully_priced
TIER:                      active  if catalyst hard + dated + mechanism in motion
                           watch   if catalyst soft (thesis present, trigger not yet dated)

SCORE (ranks *within* tier — does NOT select):
  base         = catalyst_quality            # 0–10, Bloom-rubric'd: specificity, asymmetry, hardness
  conv_mult    = clamp(1 + 0.5·(indep_domain_tracks − 1)/3, 1.0, 1.5)   # 1 track→1.0 ; 4 indep domains→1.5
  confirm_mult = clamp(1 ± 0.15·signal,                     0.85, 1.15)  # NO signal → 1.0  (⚑ never 0)
  score        = clamp(base · conv_mult · confirm_mult, 0, 10)

EDGE (separate axis):      edge = f(coverage_thinness, price_unmoved, options_unbid, news_low, mcap/float)
                           → governs universe tilt (upstream) + ranks ties (mid) + perishable (decay = exit)

SIZE (active tier only):   size ∝ EV · resolution_driver_independence · bounded_downside   # Kelly-ish
                           capped by book-level resolution-driver correlation
```
In one line: **catalyst is a gate; edge governs the universe (tilted to multi-domain special-sits in thin-coverage names); convergence and confirmation multiply above the gate; the book is built for resolution-driver independence, not name-level score.**

---

## §2 — Why today's number is broken (what we're replacing)

The current `catalyst_density_score` violates §1 at every layer (all verified in code):

| Defect | Where | Why it breaks §1 |
|--------|-------|------------------|
| **Convergence is the primary signal (70%)** | `compute_weighted_loeb` L200–214 (`0.7·conv + 0.2·claude + 0.1·options`) | Inverts §1.3/§1.6 — convergence should multiply *above* a catalyst gate, not *be* the score. Detector-hit generics → 8.8 wall; detector-miss real catalysts → ~1.8. |
| **No catalyst gate** | scorer blends, never gates | §1.3 violated — soft/fired catalysts still score. |
| **No universe layer** | candidate list scored as-is | §1.4 violated — clean-no-edge names flood the top. |
| **No score/edge split** | one number | §1.2 violated — the core conflation. |
| **No watch/active tier, no expiry-vs-catalyst check** | absent | §1.3/§1.5 violated — the call-spread failure mode is unguarded. |
| **Per-symbol hardcodes** | `convergence_detector.py` dossiers L188/294/338 (force `conv=10`); `opportunistic_catalysts.py` DHER→8.5 L948–959, VSCO floor L882, seed CVS 8.5 L547 / NKE 7.0 L551; `catalyst_fired_detector.py` COMP L83/120; `credit_health.py` VSCO L40/59 | Manufactured scores; the sample's #1 (VSCO 9.0) is a hardcode, not a finding. |
| **Mock pollutes cache *and* history** | mock L1025/1248/1284/1449 → `_save_deep_scan_to_cache` + `register_scan` L1030/1454 | §1.8 violated — fabricated lines poison the calibration record. |
| **No tracked forward basket / calibration** | absent | §1.8 violated — can't tell skill from luck. |

*(Empirical: 150-name `temp=0` sample → median 1.93, only 3 clear >7, #1 is a hardcode; GNK printed 2.82 then 6.37 on two runs.)*

---

## §3 — Implementation (mechanics, derived from §1)

> The full per-line edit list (re-weight, de-hardcode, honest-failure path, JSON shape with `score_components`/`scan_failed`/`bloom_gates_passed`/`catalyst_fired`/`model_snapshot`) carries over from v3 §0/§4/§5. v4 adds the layers §1 requires that the code lacks:

1. **Universe layer (NEW, upstream of scoring)** — tag each candidate by lane (forced-seller / spin / activist-structural / complicated-arb / other) + an **edge (attention) score** (§1.4, §1.8 ⚑2). Tilt selection; demote hard-binary to a convergence track. Map **beneficiaries** of forced flows.
2. **Catalyst gate + tiers (NEW)** — binary admission (§1.3); `tier ∈ {watch, active}` by catalyst hardness; **expiry-clears-catalyst-with-margin** in the gate (§1.5).
3. **Score = base · conv_mult · confirm_mult** (§1.9) — replaces `compute_weighted_loeb`; multipliers floored at ×1.0 (⚑1).
4. **De-hardcode** — delete the §2 hardcodes (verified list).
5. **Honest failures** — `scan_failed:true`, null score, **not cached, not registered** (skip `register_scan`); dead-letter + same-sweep retry.
6. **Tracked forward basket (NEW)** — the §1.8 line schema, wired to the forward-tracking infra; the calibration record.

---

## §4 — Validation
Pass-1 establishes **construct sanity** (the number means what §1.9 says, produced cleanly), *not* predictive validity. Held-out set disjoint from any calibration names; pre-register expected bands, web-verify facts first. Gates: no 8.8 wall · median 2–4 · >7 names clear ≥2 Bloom gates with no hardcode/mock · score stable (3× `temp=0`, SD<0.5) · confirmation centered ≈×1.0 · hardcode grep returns zero · failures flagged + absent from cache/history · every score reconstructs from `score_components`.
**Predictive validity** (does a high score precede the re-rating?) is measured later from the §1.8 tracked basket — the calibration record makes it possible.

## §5 — The weekly sweep
On the fixed scorer: **Sonnet `temp=0` (pinned snapshot), full universe, Fridays post-US-close (from next Friday)** → **Opus-4.8 deep dossier on the active tier / score >7** → **adversarial-refute pass (N independent skeptics, default-REFUTED, primary-source) gates the ACTIVE label** → Cloud Run endpoint (writes GCS, flushes fossils) → Cloud Scheduler → provisional/deep UI labeling. Pin model snapshots (not floating aliases) so sweeps are comparable. Goes live when `ux-revamp` → `main`.

> **Why the verify tier is non-optional (proven 2026-06-05):** the first live board fan-out produced 6 primary-sourced ACTIVE findings; a one-skeptic-per-name refute pass killed or gutted **3 of them** — one already FIRED 4 days prior (NVRI), one built on a fabricated balance-sheet fact (MFP), one with the edge fully arbed away (Russell). ~50% of first-pass ACTIVE did not survive. No name reaches ACTIVE/sizing without clearing the refute pass.

---

## Open / next
- **Veto check:** the three ⚑ refinements (confirmation floored at ×1.0 · edge = perishable attention score · hardening-event as the primary signal) + the beneficiary-surfacing idea.
- **Then:** populate the 2026/27 board as the live pressure-test — forced-sellers/divestitures + spins first (fattest lane) — pulling live filings + dates. This is where the methodology meets reality.
- **Regime layer (live):** [CATALYST_WATCH_REGIME.md](CATALYST_WATCH_REGIME.md) supplies the dated market-environment evidence behind §1.4/§1.5/§1.7 and the tripwires that would change them. Regenerated bi-weekly (Mondays, 13-day self-gate) by the `catalyst-watch-regime-refresh` scheduled task — re-runs the 4-agent investigation + cross-model verification, diffs vs. the prior instance, flags any breached tripwire.
