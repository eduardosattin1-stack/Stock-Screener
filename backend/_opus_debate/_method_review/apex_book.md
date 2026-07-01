# Speculair APEX (regime) book — methodology audit
**Scope:** Director + skeptic + post-processing + sizing (`weekly_opus_refresh.py` Director STEPs, `regime_skeptic`, `_regime_post.py`, `_post_common.py`, `publish_to_frontend.py`, dormant `live_director_agent.py`).
**Auditor:** Fable 5, 2026-07-01. Audited against the proven evidence base (conviction ceiling, skeptic-as-cap bug, GDOT kill, B13 verdict-A density).

**State of the live book at audit time** (published 2026-06-30, `speculair_baskets.json`):
FIP 82 / KBR 76 / LBTYK 70 (all `lane=equity_special_sit`, jointly 15.0% — the lane cap binds exactly) + UHS 67, CTSH 66, EEFT 64, NTES 64, PRGS 62, THC 58, FRVIA.PA 60 (11.2–12.9% each). `weights_basis="director_conviction"`. `book_expected_return_pct=41.4` @ 11.9 mo. NAV 103.08 EW / 100.13 weighted.

---

## 1. WHAT WORKS (keep)

1. **Verdict-based skeptic demotion, not numeric capping** (`_post_common.consume_skeptic`, `_regime_post.py:77`). REFUTED physically demotes to the front of `runner_ups`; `value_conviction_cap` is *stamped only* — I grepped every consumer (backend `*.py` + frontend `*.ts/tsx`): it is stored (`_post_common.py:56-57`, `_value_post.py:138-139`) and passed to the UI payload (`publish_to_frontend.py:247`), **never consumed numerically for sizing or eligibility**. The known skeptic-as-cap bug pattern is ABSENT from this book. Earns its complexity: it is the exact fix for the proven score-crushing failure, and the GDOT kill proves the tier works.
2. **Staleness guard on skeptic shards** (`_post_common.py:27-40`, mtime-pinned). Verified doing real work right now: the 16 shards in `_skeptic_regime/` are dated 2026-06-18 vs an apex file of 2026-06-30 — a stale verdict cannot demote a fresh basket. (That the fresh basket then shipped with *no* skeptic at all is Weakness W1.)
3. **One shared post implementation for both books** (`_post_common.py` used by `_value_post.py` and `_regime_post.py`). A skeptic that demotes and a cap loop that sizes behave identically across surfaces — this is the right anti-drift shape.
4. **Rotation ledger + decision capture** (`publish_to_frontend.py:346-368` inline ledger append; Director STEP 5 rotation discipline). The 06-30 run shows 7 KEEP / 3 ADD with per-seat `decision_rationale` — low churn, auditable, and the RE-ADD-needs-thesis-change rule is encoded in the prompt.
5. **Special-sit lane floor-sizing** (`publish_to_frontend.py:289-327`). `weight ≤ 1.5% risk-to-floor` per seat, lane ≤ 15% NAV aggregate, 5% hard cap when no usable floor, redistribution proportional to units. Verified live: FIP 3.67 + KBR 5.90 + LBTYK 5.43 = 15.00%. This is honest defined-risk sizing that lets event names in without giving them compounder-tail weight.
6. **Entry-price integrity chain** (`publish_to_frontend.py:161-171` tracking-first fallback, `:193-198` new names enter at 0 → live-quote stamp, `:274-282` backfill). Fixes the EU stale-scan fake-day-1-P&L class of bug; matches the "honest stamps" standard proven on B13.
7. **Forensic ledger re-checks** (`weekly_opus_refresh.py:2790-2816, 2888-2892`). Known EXCLUDEs get a short web re-affirm instead of a full I→A→CRO debate, with TTL + earnings-rollover expiry. Pure [SPEED] win with a correct invalidation trigger.
8. **Eligibility = conviction ≥ 3 + compact table** (Director STEP 2/3). Keeps the 1M-context Director on reconciled numbers instead of re-deriving 160 dossiers; with modal conviction 2 in the priced funnel this is also the correct *composition* filter, not a calibration knob.

---

## 2. WEAKNESSES / RISKS

### W1 — [PROVEN] The 2026-06-30 basket went LIVE with no skeptic pass and no post-processor, silently
Evidence: `apex_basket_opus_regime.json` (mtime 06-30 13:16) has `weights=None`, no `moat_post_applied`, no `skeptic_verdict` on any pick; every `_skeptic_regime/` shard is dated 06-18 (prior basket: CAG/LYFT/MMS/OTF/PDD...); yet `speculair_baskets.json` `generated_at=2026-06-30T10:56` and the book is live. `publish_to_frontend.py:100-104` gates only on "picks exist". Pipeline order (Director → skeptic → `_regime_post` → publish) is enforced by *runbook discipline only*.
Failure caused: the kill-tier — the single component with a proven scalp (GDOT: CRO said A/5, skeptic REFUTED) — did not examine FIP/KBR/LBTYK/etc., and the moat + secular-theme caps were never applied. Nothing warned. This is the exact silent-failure class the memory file flags repo-wide.

### W2 — [PROVEN] The regime Director emits no `size_units`, so the entire cap machinery is a dead letter and conviction barely moves sizing
Evidence: the Director STEP 5 output schema (`weekly_opus_refresh.py:2915`) lists ~19 fields — `size_units` is not one of them (the *value*-book Director prompt has it, cf. `:558/:596`). All 10 live picks: `size_units=None`. Both sizers fall back to `conviction/100` (`_regime_post.py:85`, `publish_to_frontend.py:303`).
Two consequences, both visible in the live file:
- **Caps can never bind.** STEP 4 *mandates* `combined_caps` with `max_units` on a ~1.0-unit/name scale. Director emitted `{THC,UHS}: max_units 2.0` — but conviction-units are 0.58+0.67 = **1.25 < 2.0**; `{KBR,LBTYK}`: 1.46 < 2.0. `secular_theme_caps` (max 1.5, `_post_common.py:106`) is equally unbindable at ~0.6 units/name. Every correlation/theme cap in this book is arithmetic decoration.
- **Sizing is near-flat.** Conviction 58 vs 82 → 1.15:1 relative weight (11.18% vs 3.67%-lane-capped; among value seats 11.18–12.91%). The Director's cross-sectional ranking — the whole point of the seat — is expressed almost nowhere in NAV.

### W3 — [PROVEN by arithmetic] The +30-50%/12mo goal is not achievable with this funnel/cap configuration
The only funnel proven to produce verdict-A / conviction-5 (B13 catalyst names: 10 A, 6 conviction-5 out of 17) enters the book through a lane capped at ≤3 seats, ≤15% NAV, 1.5% risk-to-floor. Even a *perfect* lane (~40-64% seat upside) contributes ≈ **+6–9 NAV-pts**. The other 85% of NAV sits in the priced-quality funnel with a proven 0/407 verdict-A base rate, and 3 of the 7 value seats **self-declare** `meets_goal=false` (NTES +16% @ 18mo, PRGS +24%, THC +12%). The published `book_expected_return_pct=41.4` (`publish_to_frontend.py:383-399`) is a weighted average of Director *base-case* upsides with no probability haircut — a display artifact, not a forecast. Realistic expectation with historical hit rates on modal-2/3 conviction value names: mid-teens to low-20s.

### W4 — [PROVEN code path, SUSPECTED realized impact] `_regime_post` will apply the moat cap and theme caps to the special-sit lane, contradicting the Director's STEP-3b contract
STEP 3b (`weekly_opus_refresh.py:2913`): "do NOT apply the moat-erosion cap to them — the event carries the thesis, not the franchise." But `_regime_post.process` (`_regime_post.py:79-87`) runs `stamp_moat` on **all** picks and passes `per_name_cap=_pc.moat_per_name_cap` unconditionally; `secular_theme_caps` also counts lane seats (LBTYK carries `secular_theme=linear-media-decline`). The only reason this hasn't fired is W1 (`_regime_post` didn't run). Next correct run, LBTYK — a deliberately-melting business held for the spin/event — is a live candidate for a wrong half-sizing.

### W5 — [SUSPECTED] The regime skeptic rubric is value-framed and will attack lane seats on the wrong axis
`regime_skeptic` prompt (`weekly_opus_refresh.py:1328-1333`): default-REFUTED, attack "melting business, AI/fintech/cord-cutting disruption, terminal multiple, returns below cost of capital" — with moat-erosion REFUTE priors. For `source=opus_catalyst` seats the load-bearing facts are the *event* (deal terms, dated milestone, financing, floor validity), and the business is often melting **by design**. When the skeptic finally runs on this basket, the three highest-conviction seats are the most likely to be killed on a rubric the Director explicitly exempted them from. (The skeptic's *teeth* are right — the *attack surface* is wrong for one lane.)

### W6 — [PROVEN] Director `runner_ups` never reach the frontend; the UI "Watch & Wait" list is frozen at 2026-06-06
`publish_to_frontend.py` never copies `director.runner_ups` into `baskets`; it *preserves* the legacy `capitulation_watchlist` from the GCS merge base — currently AMP.MI/PFE/AA/KEYS, all `entry_date=2026-06-06`, authored by the retired engine path. `frontend/app/page.tsx:3631-3657` renders that dead list; `page.tsx:3439` renders `runner_ups` for the value and disruptor books but not regime. Consequence: skeptic demotions (the kill-tier's *output*) are invisible, and users see a 3.5-week-stale watchlist presented as current.

### W7 — [SUSPECTED / structural] Two Director implementations; all the deterministic gates live in the dormant one
`live_director_agent.py` (bands `:200-205`, G1-G4 `:332-387`, red-flag auto-veto `:476-494`, deterministic sector cap `:716`) is the nightly `live_debate_engine` path — env-gated OFF per the ops record. The live weekly path enforces ≤3/sector by *prompt only* and has no G1-G4 / red-flag analogue (partially by design — the weekly CRO+skeptic subsume them — but nothing documents which gates were deliberately dropped vs lost). Two parallel Directors that must agree is the exact generated-vs-live drift trap already bitten once (`_weekly_debate.js` GOTCHA).

### W8 — [minor] Cosmetics that invite the next bug
`value_conviction_cap` as the field name on the *regime* skeptic (`:1332`) invites someone to "fix" it by consuming it numerically (the proven bug pattern); `_regime_post.py:85` reads `p.get("director_conviction") or p.get("conviction")` while the apex file uses only `director_conviction` — harmless today, trap tomorrow.

---

## 3. PROPOSALS (ranked)

### P1 — [SAFETY] Publish gate: refuse to publish an un-post-processed, un-skepticked apex — **S**
`publish_to_frontend.py` after `:104`: abort (with `--force` override) unless (a) `director.get("moat_post_applied")` is true, and (b) `_skeptic_regime/` contains shards **newer than the apex file** covering ≥ (say) 70% of apex symbols. Both checks are 10 lines against data already on disk.
Impact: closes the exact silent failure that shipped the current live basket without its kill-tier (W1). This is the highest value-per-line change available.
Risk: blocks a deliberate skeptic-skip run — mitigated by `--force` printing what was skipped.

### P2 — [RETURN] Give the regime Director `size_units`, and make the caps able to bind — **S**
Add `size_units (0.1-1.5; your risk-sized weight — anchors large, tails small)` to the STEP 5 field list (`weekly_opus_refresh.py:2915`), exactly mirroring the value book. In `_regime_post`, after building units, WARN if any `combined_caps.max_units ≥ sum(units of its names)` (a cap that cannot bind = a mis-scaled cap).
Impact: conviction 82-vs-58 stops meaning 1.15:1; the mandated correlation/theme caps (W2) start existing. Honest magnitude: moderate — sizing alpha is real but second-order to composition.
Risk: LLM sizing noise; bounded by the existing 0.1–1.5 clamp + moat/theme caps on top.

### P3 — [RETURN] Stop pretending 30-50%: rescale the goal or grow the special-sit lane by *count*, not risk — **M**
Two honest options (pick one, don't split):
(a) set `return_goal` (`publish_to_frontend.py:382`) to what an 85%-priced-value book delivers (~15-25%/12mo) so `meets_goal`/`book_expected_return_pct` stop overstating; and/or
(b) widen the lane's *funnel* — more B13-grade non-binary event candidates (the funnel, not the caps, is the proven bottleneck) — then raise seats 3→5 and lane 15%→20% **only for floor-verified seats**, keeping 1.5% rtf per seat.
Impact: (a) is pure honesty; (b) is the only evidence-backed path to more alpha — B13's 10-of-17 verdict-A density vs 0-of-407. Even so, be honest: at 20% NAV the lane adds ~+8-12 pts, not +30.
Risk: (b) crowds the book into event names and double-counts against B13 (same names, two books) — needs an explicit overlap rule.

### P4 — [SAFETY] Honor the STEP-3b lane contract in `_regime_post` + give the skeptic a catalyst rubric — **S/M**
In `_regime_post.process`: skip `moat_per_name_cap` and exclude `lane=="equity_special_sit"` from `secular_theme_caps` membership (2-line predicate; the lane already has its own harsher floor-sizing at publish). In `regime_skeptic`: for `source=="opus_catalyst"` seats, swap the attack list to the event (terms/financing verified in primary filings, milestone actually dated, floor arithmetic vs latest balance sheet, spread-vs-terms) — keep default-REFUTED.
Impact: prevents the code from contradicting the Director's contract the first time it actually runs (W4), and keeps the kill-tier lethal *on the right facts* for the seats that carry the book's only proven verdict-A density (W5).
Risk: a genuinely-terminal franchise with a fake event escapes the moat cap — acceptable: the event-rubric skeptic + 1.5% rtf still bound the loss.

### P5 — [SAFETY] Publish `runner_ups`; retire the frozen `capitulation_watchlist` — **S**
`publish_to_frontend.py`: `baskets["runner_ups"] = director.get("runner_ups", [])` (with skeptic verdicts already stamped by `consume_skeptic`); replace or clearly date-label the legacy watchlist in `page.tsx:3631`. Impact: skeptic demotions become visible (tracking honesty), dead 06-06 list stops masquerading as live. Risk: none material.

### P6 — [SPEED/SAFETY] Quarantine or delete the dormant Tier-2 Director (`live_director_agent.py`) — **S**
Verify no live import from the env-gated nightly path, then either delete it or stamp a loud "RETIRED — weekly path is authoritative" header, after porting the *one* still-wanted piece (deterministic ≤3/sector cap, `:716-762`) into `_regime_post` as code rather than prompt. Impact: removes a two-implementations drift trap (W7); a rare DELETE. Risk: the nightly env flag gets flipped back on someday — the loud header covers that.

---

## 4. IF YOU ONLY DO ONE THING

**P1 — the publish gate.** The book that is live *right now* skipped its skeptic and its post-processor and nothing noticed. Every other property audited here — the kill-tier that demonstrably works, the moat teeth, the theme caps, the lane contract — is only as real as the pipeline's guarantee that it actually ran. Ten lines in `publish_to_frontend.py` convert the designed process into the enforced process; until then, every other improvement is conditional on runbook memory.
