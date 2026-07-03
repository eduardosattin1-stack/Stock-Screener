# Methodology audit — Basket 13 catalyst sleeve + apex special-sit lane
**Reviewer:** Fable 5 (senior quant-methodology pass) · **Date:** 2026-07-01
**Scope:** funnel dials → CRO-only debate → caps/inject → mark/resolve/report → watchlist book → apex `equity_special_sit` lane coexistence.
**Files read:** `backend/_basket13_candidates.py`, `_basket13_gen.py`, `_basket13_inject.py`, `_basket13_mark.py`, `_basket13_README.md`, `_basket13_tracker.json` (live), `_opus_debate/_catalyst_debate.mjs`, `_catalyst_weekly.mjs`, `_catalyst_director.json`, `_catalyst_skeptic/*`, `_catalyst_summary.csv`, `_post_common.py`, `weekly_opus_refresh.py` (STEP 3b ~line 2913, catalyst-prep/seed lines 2923–3027).

**Live book state at audit (tracker):** 12 entries, **0 resolved**, 39 non-selections, 4 runs, 11 marks; held NAV **102.1**; watchlist 9 names, separate equal-weight cohort NAV **108.7**.

---

## 1. WHAT WORKS (keep)

1. **"The LLM proposes, the code asserts" — deterministic cap validator + append-only tracker** (`_basket13_inject.py:323-373` `validate()`, entries flow :464-504). Every cap (≤2/driver, ≤40 pts/cluster, bio-lane ≤5, rtf ≤1.5%, binary ≤2%, staging half-weight) is re-asserted in code at stamp time, at the price the book actually carries (`live_px`, pending counted as-if-filled). This is the single reason the sleeve's track record is trustable — it earns its ~700 lines.
2. **Stamp honesty rules** — CRO-verified live entry prices with `entry_price_source`, `PENDING_LIMIT` no-fiction fills (`inject.py:400-413`, fill logic `_basket13_mark.py:47-60`), hedge-aware marks, computed (never quoted) `risk_to_floor_pct`, pinned weight-points cluster basis (header :24-27). Directly answers the censoring-bias lesson from the /performance audit.
3. **The funnel-composition thesis itself is validated.** The same debate stack that produced 0/407 verdict-A on priced quality produced 10 A / 6 conv-5 / 2 Director-80+ on this 17-name funnel (06-22 diagnostic). The sleeve and the new apex lane are aimed at the *proven* bottleneck (composition, not calibration). Keep both.
4. **CRO four-surface separation of concerns** (`_basket13_gen.py:119-130`): edge-at-entry perishability, tradeability, window↔expression, driver tag are exactly the surfaces the full-stack catalyst debate does NOT cover. The structured `live_price` output + parsed entry limits produced real PENDING_LIMIT behavior (GDOT stamped pending at 12.75, filled later). Complementary, not redundant — keep this phase even if the entry gate upgrades (see P2).
5. **Counterfactual capture**: non-selections recorded (39), and the on-deck watchlist is marked daily as a separate equal-weight cohort NAV (`_basket13_mark.py:94-114`). This is already producing the sharpest signal in the sleeve (see W2) — the machinery paid for itself in three weeks.
6. **Kill-tier with teeth where it is wired.** The full-stack catalyst skeptic REFUTED GDOT (fabricated unlisted-stub spread, cap 22), PRX.AS (mislabeled forced-seller), VRDN (already fired) — and `_post_common.consume_skeptic()` uses the proven verdict-based demotion (REFUTED → physically demoted; the numeric cap is stamped for display only, :56-63). GDOT (CRO said TRADE) is the empirical proof the pattern works.
7. **Apex STEP-3b hard constraint** (no `binary_prob` / edge-L / blocking flag into apex; `weekly_opus_refresh.py:2913`) plus the negative-tested `_basket13_apex_check.py`. Cheap, deterministic, already caught a synthetic violation.

---

## 2. WEAKNESSES / RISKS

### W1 — PROVEN: manual `resolve` is the sleeve's rot vector; dead seats sit OPEN past their catalysts
- **VRDN**: FDA approved Lumvoa **2026-06-26** (four days early — per the full-stack skeptic + Director, `_catalyst_director.json` assessments[VRDN]: "REFUTED: the binary already FIRED favorably"). Its tracker `dated_milestone` was 2026-06-30. As of this audit (07-01) VRDN is still `OPEN`, unresolved (`_basket13_tracker.json`).
- **AQST**: the load-bearing catalyst fired as a **CRL on 2026-01-30** — *before* the 06-10 entry; the "2026-09-30" milestone is the resubmission window, not a decision (`_catalyst_summary.csv` row AQST; skeptic cap 35). It holds a seat and an `FDA_approval_decision` driver slot.
- **Failure caused:** the NAV series marks phantom event-exposure; driver caps stay consumed by dead seats (see W2); the calibration loop gets zero resolutions (see W5). Nothing in `_basket13_mark.py` even prints "milestone passed N days ago" — the daily mark has the data (dates + quotes) and stays silent.

### W2 — PROVEN: caps + run-to-resolution + stale seats lock the best names out of the book
- **BBIO — the highest-conviction name the entire platform has ever produced** (Director 84 in the 06-22 diagnostic, 78 = book-max in the 06-29 weekly; verdict A, conviction 5, skeptic CONFIRMED) — is **on the watchlist, not held**: `blocked_by: "FDA_approval_decision driver is full (2/2: VRDN, AQST)"` (tracker watchlist). The driver cap is filled by one REFUTED/fired seat and one fictional-date seat.
- The counterfactual cohort is already scoring the cost: watchlist NAV **108.7** vs held NAV **102.1** since 06-13 (small n, 3 weeks — but it is exactly the on-deck-vs-held comparison the sleeve was built to measure, and it currently says the seating loses to its own queue).
- **Failure caused:** the sleeve exists to harvest the funnel's verdict-A names and is structurally holding B-grade seats instead of its A-grade queue.

### W3 — PROVEN: design invariant #1 ("catalyst reality is settled upstream") is false at entry time, and the sleeve's own debate is forbidden from fixing it
- `_basket13_gen.py:119,126`: the Catalyst-CRO "NEVER re-litigates whether the event is real… DO NOT attack… whether the catalyst is real." But "upstream" is the *board*, whose dates go stale between sweeps (the freshness evidence: ad-hoc paths → 87% CONFIRMED_WITH_CORRECTIONS; and concretely: AQST's fired CRL, VIR's Q1-2027-not-Q4-2026 readout, KBR's slip to 2027-01-04 with a still-confidential Form 10 — all found by the full-stack skeptic, none by the sleeve's CRO).
- Consequences already in the book: **GDOT seated at 14% — the largest seat** (full-stack skeptic: REFUTED, "the apparent spread is fabricated… $8.11 hard cash + unlisted NewCo at full book", cap 22); **UNF at 8%** (spread collapsed to ~even-money, cap 30); **AQST at 4.5%** (catalyst pre-fired). That is ~26.5 of 66.5 invested NAV-points in names the proven kill-tier rejects.
- The entry gate itself (`_basket13_candidates.py:115-121`) filters on `valuation.expected_close_date` verbatim — garbage-in dates pass the 6-month window unchallenged.

### W4 — PROVEN: the weekly full-stack catalyst debate now covers the whole B13 book (`_b13_universe()` = candidates ∪ held seats, `weekly_opus_refresh.py:2935-2955`) — and B13 consumes none of it
- The artifacts land weekly in `_catalyst_results/` + `_catalyst_skeptic/` (20 names, 06-29 run). No code path feeds a REFUTED/FIRED verdict back into `_basket13_tracker.json` held seats (no THESIS_BROKEN/EDGE_GONE trigger — `resolve()` is CLI-only). The sleeve paid for the diagnosis of its own sick seats and ignored it.
- Related seeding gap: `catalyst_seed()` (:2998-3027) copies `_catalyst_results/{SYM}.json` into `results_regime/` but drops `_catalyst_skeptic` verdict/corrections/cap — the apex Director reads **un-skeptic'd** catalyst dossiers. Visible effect: apex seated FIP at conviction **82** while the catalyst skeptic's cap was 75 (the apex book's own later skeptic pass partially covers this, but the verified date corrections are lost).

### W5 — PROVEN: the "re-fit dials quarterly" calibration loop is structurally real but functionally vacuous
- 0/12 resolutions after 3 weeks (expected — but VRDN *should* be resolution #1 and isn't, per W1).
- `report()` (`inject.py:617-644`) computes hit-rate/realized-RR by lane/driver/edge **only over resolved entries**; it never touches `non_selections` (39 recorded, zero analytics), never compares `win_prob`/`ev_pct` to outcomes, and never reads `watchlist_marks`. The re-fit itself is a trailing print: "-> re-fit the • edge thresholds… (quarterly)". There is no tool that proposes new dial values.
- **Failure caused:** the sleeve's whole justification ("a calibration sleeve") currently rests on machinery that emits no calibration.

### W6 — SUSPECTED: the persistent-watchlist machinery is live-untested
- All 4 tracker runs predate the 06-30 12:52 rework: run records lack the `watchlist_delta` key `inject()` now writes (:517-522), `watchlist_history` is empty (0 events despite carries since 06-13), watchlist rows lack `de_prioritized`/`first_seen_date`, and `watchlist_state` entries carry only 3 legacy keys. `_basket13_selftest.py` covers it synthetically, but the first real re-debate exercises `build_watchlist()`'s carry/trim/graduate set algebra (:174-319) against a legacy-shaped ledger for the first time. Watch the first inject closely.

### W7 — PROVEN (code): apex-lane / B13 double-counting is live, unflagged
- **FIP is simultaneously a B13 held seat (10%, entry 4.56, 06-10) and an apex `equity_special_sit` seat (conviction 82)** in `apex_basket_opus_regime.json`; AAUC is a B13 seat (7%) and an apex runner-up. Nothing stamps the overlap; the STEP-3b constraint blocks only binaries/edge-L/blocked flags, not already-held-in-B13 names.
- Both books publish tracked NAVs. The same catalyst's P&L will print twice in the platform's headline track record, and when it fires, B13 stamps a resolution while the apex book just drifts — two different stories about one event. Cross-book risk (rtf in B13 + 1.5% risk-to-floor in apex on the same name) also composes invisibly.
- Verdict: overlap between methodology books is acceptable (value/regime already overlap) — but it must be *stamped*, not silent.

### W8 — MINOR (grab-bag)
- `_catalyst_weekly.mjs` Director step 3 retains the numeric **"HARD-CAP at the Skeptic conviction_cap"** — the same skeptic-as-cap pattern the scale-out re-grade removed. Effect: the 06-29 weekly printed `n_dir80: 0` with BBIO pinned *exactly* at its cap (78) where the 06-22 diagnostic (same instruction, laxer caps) gave 84/83. The 0-100 caps here are better-calibrated than the old 1-5 crush, so this is a haircut not a catastrophe — but it deterministically re-imposes the conviction ceiling the lane exists to escape.
- `_cat_ctx()` degrades held-seat rows in catalyst-prep: tracker entries lack `company_name`/`live_price`/`days_to_milestone`, so GDOT/FIG/WVE went to the debate as `co:"GDOT" … UNDATED; live None` — GDOT actually had a 09-30 milestone (`weekly_opus_refresh.py:2966-2971`).
- README/code dial drift: README table says basket 8–12; `inject.py:55` says 8–20 (gen prompt agrees with 20). Cosmetic but the README is the dial registry.
- `resolve()`'s hedge handling is a `pass` stub (`inject.py:557-558`) — hedge-leg exit P&L rides only in free-text notes; UNF/CTAS will resolve with an un-computed hedged return.

---

## 3. PROPOSALS (ranked)

### P1 [SAFETY] — Resolution radar: auto-detect "this seat should be dead" in the daily mark — **S/M effort**
**Change:** `_basket13_mark.py` (already fetching every quote daily): after marking, flag any OPEN seat where (a) `dated_milestone` + grace (≈5 trading days) has passed, (b) the close crossed `fair_value_target` or `downside_floor`, or (c) the latest `_opus_debate/_catalyst_results/{SYM}.json` has `catalyst_status == FIRED` or `_catalyst_skeptic/{SYM}.json` has `verdict == REFUTED` (mtime-guarded, same staleness rule as `consume_skeptic`). Stamp `resolution_due: {date, reason}` on the entry + print loudly; `report()` lists them first. Stamping the actual resolution stays manual (exit price/type deserve a human + primary source — keep the honesty).
**Impact:** closes the VRDN/AQST/GDOT hole permanently; the calibration loop starts actually accumulating resolutions. Honesty gain is large; return gain indirect but real (frees caps — see P3).
**Risk:** false FIRED/REFUTED from an LLM shard — mitigated by alert-only (no auto-stamp).

### P2 [RETURN] — Feed the full-stack catalyst debate (which already runs weekly over the whole B13 book) into the B13 entry gate — **M effort, ~zero marginal token cost**
**Change:** `_basket13_gen.py`: join each candidate with its latest `_catalyst_results` (`catalyst_status`, verdict, conviction, corrected dates) + `_catalyst_skeptic` (verdict, kill_fact) and put them in the CRO/Director context; `_basket13_inject.validate()`: hard-reject a NEW seat whose skeptic verdict is REFUTED or whose `catalyst_status` ∈ {FIRED, ARB-through-terms}, with a freshness guard (artifact ≤10 days old, else warn-only). Do **not** replace the light CRO — its four surfaces (live edge, tradeability, expression↔window) are uncovered by the full stack; this is a union, not a swap.
**Impact:** would have blocked GDOT (14%), AQST (4.5%) and flagged UNF (8%) — ~27 NAV-points of the current book. This is the single largest expected-return lever in the sleeve, and it is a *consume-existing-artifact* change, not new machinery.
**Risk:** ordering dependency (catalyst Workflow must precede a B13 re-debate in the weekly runbook) and one more coupling to the multi-hour weekly run; the freshness guard keeps ad-hoc mid-week injects working.

### P3 [RETURN] — Free the dead seats so the queue graduates (BBIO-class) — **S effort**
**Change:** no new dial. Simply: when P1 flags a seat `resolution_due`, resolve it promptly (the existing CLI), which releases its driver/lane/cluster headroom; `build_watchlist` graduation then seats the on-deck leader on the next inject. Optionally have `report()` print "cap headroom released if due-seats resolved: {driver: n}" so the operator sees BBIO's path.
**Impact:** the watchlist cohort is outrunning the held book by ~6.6 NAV-points in 3 weeks; getting A-grade names out of the queue is where the funnel's proven verdict-A surplus actually converts to tracked return. Magnitude honest: on 12 seats, replacing 2-3 dead ones with the top of the queue.
**Risk:** whipsaw if a "due" flag is wrong — mitigated because resolution is still a human stamp.

### P4 [SAFETY] — Stamp cross-book overlap + carry the skeptic into `catalyst_seed` — **S effort**
**Change:** (a) `catalyst_seed()`: merge `_catalyst_skeptic/{SYM}.json` (verdict, corrections, conviction_cap) into the seeded `results_regime` record so the apex Director sees the kill-checked dossier, not the raw bull. (b) In both `catalyst_seed()` and `_basket13_inject.inject()`: if the symbol has an unresolved entry in the *other* book (B13 tracker ↔ `apex_basket_opus_regime.json`), stamp `cross_book: true` on both records and print it; surface in `report()`. No dedupe/blocking — overlap is legitimate, silence is not.
**Impact:** honest consolidated track record (FIP/AAUC today); apex conviction stops floating above the catalyst skeptic's verified corrections.
**Risk:** essentially none; a few extra fields.

### P5 [SAFETY] — Make `report()` an actual calibration report — **M effort**
**Change:** add three sections computed from data already in the tracker: (1) expected-vs-realized — `win_prob` vs FIRED_WIN rate and `ev_pct`/`expected_rr` vs realized, by lane/edge band (the E-vs-O discipline calibration_tracker v2 already established); (2) counterfactual returns — mark `non_selections` and the watchlist cohort from stamp date to now (quotes via the same `fetch_live_quotes`) so "what the Director passed on" is a number, not a list; (3) a dial-suggestion block (e.g. "H-edge hit rate X vs M-edge Y → EDGE_OK candidate change"), print-only — the human re-fits.
**Impact:** converts the sleeve's core promise (calibration) from aspiration to output. No return by itself, but it is the precondition for ever moving a dial defensibly.
**Risk:** tiny-n overfitting — mitigated by report-only + quarterly cadence.

### P6 [SPEED] — Delta-debate the weekly catalyst lane — **S/M effort**
**Change:** `catalyst_prep()`: reuse a name's existing `_catalyst_results`/`_catalyst_skeptic` shard when the board row is unchanged (same `dated_milestone`, `edge_grade`, `tier`, price within ~5%) and the shard is <14 days old; emit only new/changed names into `_catalyst_weekly.mjs`. Also fix `_cat_ctx()` to carry company/live/milestone from tracker entries (W8).
**Impact:** the weekly's most expensive block (≈20 × 2 web-heavy Opus agents + xhigh Director) drops to ~5-8 names in a typical week — meaningful against the 2-3-resume-cycle pain; batching ≤6 already respected.
**Risk:** stale reuse across a fast-moving event — the 14-day bound + "price moved >5% forces re-debate" covers the perishable-edge case.

### P7 [SAFETY] — Replace the numeric HARD-CAP in the catalyst Director with verdict-based demotion — **S effort**
**Change:** `_catalyst_debate.mjs` step 3 (and its `_catalyst_weekly.mjs` copy): REFUTED forces <50 (keep), CONFIRMED_WITH_CORRECTIONS = the Director must *state* the correction's haircut in `binding_reason` (no numeric ceiling), CONFIRMED = none; keep `conviction_cap` as a reported column only — matching the proven `consume_skeptic` pattern.
**Impact:** removes the deterministic re-imposition of the conviction ceiling on the one funnel proven able to breach it (BBIO 84 → 78 was the cap binding, not new information). Modest: a few points on a few names — but those points are exactly the 80+ apex-seat band the lane keys on.
**Risk:** score inflation without the ceiling — the REFUTED-kill + the band definitions retain the teeth; monitor one run.

*(Not proposed: upgrading B13 to run its own full-stack debate — redundant once P2 consumes the weekly artifacts; auto-stamping resolutions — violates the stamp-honesty rules that make this tracker credible; new cap dials — the caps are fine once dead seats stop consuming them.)*

---

## 4. IF YOU ONLY DO ONE THING

**P1+P2 as one unit: wire the weekly full-stack catalyst artifacts into the sleeve — REFUTED/FIRED blocks new seats, and flags held seats as resolution-due in the daily mark.** The evidence is unambiguous: every materially broken position in the current book (GDOT 14%, AQST 4.5%, UNF 8%, VRDN unresolved-after-firing) was correctly diagnosed by machinery the platform *already runs and pays for weekly* — the sleeve just never reads the answer, and its own CRO is forbidden by design from finding it. One consume-artifacts change fixes entry quality, unblocks the BBIO-class queue behind dead seats, and starts the calibration loop actually resolving.
