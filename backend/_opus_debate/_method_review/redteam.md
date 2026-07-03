# RED TEAM — adversarial review of the six methodology audits

Red team: Fable 5, 2026-07-01.
Scope: every proposal in `debate_engine.md` (DE), `apex_book.md` (AX), `value_book.md` (VB), `basket13.md` (B13), `basket14.md` (B14), `ops.md` (OPS).
Attack axes: (a) overfitting-to-backstory / narrative risk, (b) complexity-vs-payoff for a 1-person operator, (c) honest-track-record breakage, (d) look-ahead / survivorship leakage, (e) cost/runtime blowup, (f) cross-audit contradiction.
Facts re-verified in the working tree before use as kill-facts: `value_conviction` is already a shipped, catalyst-blind CRO output preferred by the value rubric (`weekly_opus_refresh.py:552, :732-734`); both skeptic tiers already run over apex + runner_ups (~16 finalists, `:1262-1266, :1311-1315`); the numeric `value_conviction_cap` is still demanded by both skeptic prompts (`:1285, :1334`).

**Tally: 42 proposal items → 3 KILLED outright, 3 killed-in-part (one arm killed, one kept), 18 KEEP-WITH-CONDITIONS, the rest KEEP.**

---

## 1. DEBATE ENGINE (debate_engine.md)

### DE-P1 — Decouple conviction from verdict; re-gate on `verdict OR value_conviction`
**VERDICT: SPLIT — KILL the rubric rewrite; KEEP-WITH-CONDITIONS the gate widening.**
- **Kill-fact (rewrite arm):** the decoupled, catalyst-blind confidence score DE-P1 wants **already exists and already ships** — the CRO emits `value_conviction` "judged on valuation + forensics with the regime overlay explicitly ignored" and the value rubric already prefers it everywhere (`weekly_opus_refresh.py:552`). Rewriting the semantics of `conviction` across 3 prompt surfaces duplicates an existing field at the price of destroying longitudinal comparability of the platform's ONLY 407-debate historical signal — in the same weeks the special-sit lane experiment (designed against the OLD scale) is reading out. That is maximal narrative risk (the audit's "timing verdict wearing a confidence costume" story is elegant, but the fix is redundant) for zero marginal information.
- The audit's claimed value-book benefit is also overstated: `value_input` grades **all** of `results_regime`, not the conviction≥3 subset — the gate never censored the value book.
- **Kept arm + conditions:** widening apex-Director eligibility to `conviction >= 3 OR value_conviction >= 4` is one line, uses the existing field, and addresses the real censoring (quality names never reaching the regime Director). Conditions: (1) land only after ≥1 full special-sit-lane cycle so the lane's baseline isn't perturbed; (2) stamp `rubric_version`/gate version in the artifacts so calibration (B13-P5, calibration v2) can segment.

### DE-P2 — Fix the `-None` sort crash at `live_debate_engine.py:1415`
**VERDICT: KEEP.** Two-token fix for a guaranteed crash on the fallback path. No attack survives. Do it even if AX-P6 retires the nightly path (defense-in-depth for backfill runs).

### DE-P3 — Tiered moat cap; collapse the triple-punishment
**VERDICT: KEEP-WITH-CONDITIONS.** The triple-stacking diagnosis is sound and rhymes with the proven skeptic-as-cap bug. But the proposed "cyclical dip test" is a leniency escape hatch — LLMs given an exemption clause will rationalize secular decline as cyclical (the same failure direction as the fabricated non-US options edge). Conditions: (1) the ERODING cap-3 applies unless the CRO **names the structural mechanism with a dated source** — the burden stays on exempting, not on capping; (2) deterministic teeth (`moat_per_name_cap`, erosion eligibility bar) untouched, as proposed; (3) monitor the value_conviction distribution for one run — if 4-5s spike >25% of the pool, the test is leaking.

### DE-P4 — Delete the skeptic's numeric `value_conviction_cap`
**VERDICT: KEEP-WITH-CONDITIONS — must merge with VB-P5, else the two audits contradict.**
- **Contradiction (axis f):** DE-P4 deletes the number; VB-P5 consumes `cap <= 2` as the trigger for the evidence-prescribed CWC haircut. Pure deletion leaves VB-P5 with no input; consuming the number as a threshold is exactly the "reintroduction magnet" DE-P4 warns about.
- Condition: replace the numeric field in both skeptic prompts (`:1285, :1334`) with a categorical `correction_severity: "minor"|"load_bearing"`; CWC + load_bearing drives VB-P5's half-size flag; the number disappears from stamping and the UI (`publish_to_frontend.py:247`). One decision, both audits satisfied, no numeric cap anywhere.

### DE-P5 — Uniform freshness + peer anchors on non-weekly paths
**VERDICT: KEEP — merged with OPS-P5 (same proposal, two audits).** Implement ONCE via `fmp_facts.py` as OPS-P5 specifies; don't build two freshness injectors. Directly attacks the measured 87%-corrections/MYRG class.

### DE-P6 — De-duplicate Interrogator/CRO; trim nightly Moderator transcript
**VERDICT: SPLIT — KILL the nightly half; KEEP-WITH-CONDITIONS the weekly trim.**
- **Kill-fact (nightly half):** the nightly debate path is env-gated OFF and AX-P6 (correctly) proposes retiring its Director. Optimizing token flow on a dormant path being retired is negative payoff — pure maintenance surface.
- Weekly trim (§5/§8): the audit itself concedes weekly duplication "is free (one context)"; the real saving is second-order next to OPS-P2's 50-70% debate cut. Condition: do it only if the run still doesn't fit one session AFTER OPS-P2 lands. Sequencing, not merit.

### DE-P7 — Strip dated ticker examples (BRBR/CALM/Edenred…) from durable Director prompts
**VERDICT: KEEP.** Proven staleness contamination in a reusable prompt; the generated live-cluster block is strictly fresher. Keep one generic worked example per rule as the audit proposes.

### DE-P8 — Skeptic pass for the near-miss band
**VERDICT: KILL.**
- **Kill-fact:** the premise is false. Both skeptic tiers already cover **apex + runner_ups** (`weekly_opus_refresh.py:1262-1266` value, `:1311-1315` regime — ~16 finalists vs 8-10 seats). And every name promoted into a basket is by construction a finalist of the run that promotes it, so it receives its skeptic pass before publish (when pipeline order holds — which is AX-P1/VB-P1's job, not a coverage-band job). What remains is pre-reviewing names that MIGHT be promoted next week — ~10 web-heavy Opus agents/week of the exact budget the ops audit proves is the binding constraint, spent on the lowest-value review in the stack.

---

## 2. APEX / REGIME BOOK (apex_book.md)

### AX-P1 — Hard publish gate (abort unless post-processed + fresh skeptic coverage)
**VERDICT: KEEP-WITH-CONDITIONS — reconciled with VB-P1, which it directly contradicts.**
- **Contradiction (axis f):** AX-P1 hard-aborts on missing skeptic coverage; VB-P1 explicitly says "do NOT hard-block publish (partial runs are the ops norm)". Both audits cite the same ops reality and prescribe opposite policies for the same failure class.
- Red-team resolution: **hard-gate the deterministic post, soft-gate the skeptic.** `_regime_post`/`_value_post` are local, deterministic, seconds — there is no ops excuse for `moat_post_applied` missing; abort on that (with `--force`). Skeptic coverage gets VB-P1's treatment (stamp `MISSING`, half-size uncovered, print loudly) because a hard abort in a headless scheduled run whose launcher already dies silently (OPS-W1) converts "published without skeptic" into "didn't publish and nobody was told" — the exact failure OPS-P1 exists to fix.
- Extra condition: the gate must print its reason into the log OPS-P1's sentinel reads, so an intentional abort isn't burned as 2 wasted auto-resume cycles.

### AX-P2 — Give the regime Director `size_units`; WARN on unbindable caps
**VERDICT: KEEP-WITH-CONDITIONS.** The dead-letter cap arithmetic (max_units 2.0 vs conviction-units 1.25) is a real, proven defect. But temper the expected impact: the sister book that already HAS Director `size_units` (B14) emits a compressed 0.75-1.05 band and set its one combined_cap at exactly the current sum (B14-W6) — LLM sizing produces paperwork, not conviction spread. Conditions: (1) ship the unbindable-cap WARN (that part is deterministic and cheap); (2) if the first run reproduces the B14 compression, switch to a deterministic conviction→units map in `_regime_post` instead of iterating prompts. Expect risk hygiene, not sizing alpha.

### AX-P3(a) — Rescale the stated return goal to what the book can deliver
**VERDICT: KEEP.** Pure honesty; the arithmetic (85% of NAV in a 0/407-verdict-A funnel) is airtight. Add: label `book_expected_return_pct` as un-haircut base-case or probability-weight it — changing the goal number without fixing the 41.4% display artifact fixes half the lie.

### AX-P3(b) — Grow the special-sit lane 3→5 seats / 15%→20% NAV
**VERDICT: KILL (defer ≥1 quarter). The worst idea in the six audits.**
- **Kill-facts:** (1) the lane has run **zero** complete cycles — it was wired days ago and takes effect next weekly run; growing it now destroys the experiment's baseline before a single observation exists. (2) The supporting evidence for "the queue outruns the book" is a 3-week, n≈12 counterfactual (108.7 vs 102.1) — one regime, no resolutions; sizing NAV on it is textbook overfitting-to-backstory. (3) Cross-book double-counting is LIVE and unstamped (B13-W7: FIP simultaneously a B13 seat and an apex lane seat; risk composes invisibly) — widening the lane amplifies an unmeasured overlap. (4) The ops audit explicitly ruled "anything touching the special-sit lane — just shipped, let it run," and it is right.
- Re-open conditions: one quarter of lane data + B13-P4's overlap stamping shipped + resolutions actually accruing (B13-P1/P3). The audit's own honesty note ("+8-12 pts, not +30") concedes the payoff doesn't justify breaking the baseline now.

### AX-P4 — Honor the STEP-3b lane contract in `_regime_post`; catalyst rubric for lane seats
**VERDICT: KEEP — and it is URGENT once AX-P1 lands.** Today W4 hasn't fired only because the post never ran; the moment the publish gate forces `_regime_post` to run, LBTYK gets wrongly half-sized by the moat cap the Director exempted it from. The lane predicate is 2 lines. Condition: the catalyst attack-rubric must be implemented inside the ONE unified skeptic redesign (see X1), not as a divergent regime-only branch.

### AX-P5 — Publish `runner_ups`; retire the frozen 06-06 capitulation watchlist
**VERDICT: KEEP.** A 3.5-week-stale list presented as live is a standing honesty defect; skeptic demotions invisible = the kill-tier's output unaccountable. Cheap.

### AX-P6 — Quarantine/retire the dormant `live_director_agent.py`
**VERDICT: KEEP.** Two Directors that must agree is the proven generated-vs-live drift trap. Port the deterministic ≤3/sector cap into `_regime_post` first, as proposed. Pairs with killing DE-P6's nightly arm — decide the nightly path's status ONCE (see X9).

---

## 3. VALUE BOOK (value_book.md)

### VB-P1 — Skeptic coverage gate: fail loud, stamp MISSING, half-size uncovered, flag stale-REFUTED
**VERDICT: KEEP — and promote it to the platform-wide policy (it wins the AX-P1 conflict for the skeptic half).** The live evidence (EEFT 20.4% un-vetted, HRMY seated over a stale REFUTED) is the strongest single finding in the six audits. Conditions already in the proposal are right (no hard block; visible and priced). One addition: both posts must consume the same stamps via `_post_common` so the regime book can't drift.

### VB-P2 — One skeptic pass per unique finalist across both books
**VERDICT: KEEP-WITH-CONDITIONS.**
- **Cross-audit collision (axis f):** four audits rewrite the skeptic tier independently (DE-P4 field deletion, VB-P2 merge, VB-P5 CWC haircut, AX-P4 catalyst rubric, B14-P2 new disruptor tier, B13-P7 cap removal). Shipped separately these collide in the same functions and prompts.
- Conditions: (1) implement as ONE unified skeptic work item — single generator, per-lane rubric selection (value / regime / catalyst / disruptor), `kill_scope` field, categorical `correction_severity` (per DE-P4×VB-P5 merge), coverage stamping (VB-P1), staleness rule unchanged; (2) the merge's ~10-13 agent saving is the budget that pays for B14-P2's +13 — land them together, net ≤ today's agent count.

### VB-P3 — Dedicated drawdown/forced-seller intake slice for the value book
**VERDICT: KEEP-WITH-CONDITIONS.** This is the composition fix the proven evidence actually supports, applied to the one book with no intake of its own. Attacks checked: no look-ahead (screen is point-in-time on live FMP fields); falling knives are what the funded-solvency gate + skeptic exist for; "sees them as ordinary rows" correctly avoids narrative priming. Conditions: (1) the ≤20/week cap enforced in code, not prose; (2) rows tagged `value_drawdown` for attribution; (3) sequence AFTER OPS-P2 so the added debates don't reinstate the third resume cycle; (4) one composition change per book per cycle — don't co-launch with a same-book gate change or attribution dies.

### VB-P4 — Per-name bear-anchor sanity flags
**VERDICT: KEEP.** Visibility-only, no sizing teeth, feeds skeptic targeting. The 52w-low false-positive on re-rated names is priced (flag, not gate).

### VB-P5 — CWC haircut when the skeptic found a load-bearing error
**VERDICT: KEEP-WITH-CONDITIONS.** It implements the exact evidence prescription (CORRECTIONS→modest haircut). Condition (binding): trigger on the categorical `correction_severity == "load_bearing"` from the DE-P4 merge, NOT on numeric `cap <= 2` — a numeric threshold re-normalizes consuming the cap, the proven bug's doorstep. Monitor the severity distribution one month as proposed.

### VB-P6 — Delete dead machinery, fix `universe:161`, stamp as-of dates
**VERDICT: KEEP.** All three are proven inert-lie/fuse removals.

### VB-P7 — Deterministic book-level secular-load cap at 65%
**VERDICT: KEEP-WITH-CONDITIONS.** The 70%-live breach of a prose-only rule is real and it is the book's dominant structural risk. Attacks: the 65% threshold is an unback-tested dial with real teeth; the load classification comes from LLM stamps (prose-derived input, deterministic consequence); and scaling non-clean legs re-normalizes weight INTO the 3 clean anchors — check the resulting single-name concentration (EEFT is already 20.4%). Conditions: (1) warn-and-publish the computed load for 2 runs before enforcement; (2) re-normalization must respect existing per-name/theme caps; (3) stamp the 65% as a versioned dial for the calibration loop to revisit.

---

## 4. BASKET 13 (basket13.md)

### B13-P1 — Resolution radar in the daily mark (alert-only)
**VERDICT: KEEP.** Closes the VRDN/AQST rot vector without touching stamp honesty (resolution stays a human act on primary sources). The mtime-guarded shard read matches `consume_skeptic`'s staleness rule. No attack survives.

### B13-P2 — Feed the weekly full-stack catalyst artifacts into the B13 entry gate
**VERDICT: KEEP — the single best return-per-line proposal in the six audits.** Consumes artifacts already paid for; would have blocked ~27 NAV-points of proven-broken seats (GDOT 14%, AQST 4.5%, UNF 8%). Conditions: (1) runbook ordering (catalyst Workflow before any B13 re-debate) written into the SKILL, not tribal memory; (2) align the freshness bound with B13-P6's reuse window (both 10d or both 14d — as written, a 13-day-old shard is reusable by P6 but stale for P2's hard-reject, which flips the gate to warn-only unpredictably).

### B13-P3 — Resolve dead seats promptly so the queue graduates
**VERDICT: KEEP.** It is discipline plus one report line, not machinery. Note: resolving GDOT/AQST/UNF prints honest realized losses on the tracker — that is the system working, not a reason to defer. The BBIO story is emotionally loaded (narrative risk axis), but the seats being freed are dead on documented facts, not on the story.

### B13-P4 — Stamp cross-book overlap; carry skeptic verdicts into `catalyst_seed`
**VERDICT: KEEP.** The FIP double-print is live today. Also the hard precondition for ever re-opening AX-P3(b). The `catalyst_seed` half fixes a real leak (apex Director consuming un-skeptic'd catalyst dossiers; FIP 82 vs cap 75 with date corrections lost).

### B13-P5 — Make `report()` an actual calibration report
**VERDICT: KEEP-WITH-CONDITIONS.** The sleeve's stated purpose currently emits nothing — fair. Conditions: (1) print-only stays (as proposed); (2) hard minimum-n per cell (suggest n≥8 resolved) before any dial-suggestion line renders — 12 entries and 0 resolutions is an overfitting invitation the audit only half-prices with "quarterly cadence"; (3) include the per-record table (platform rule: never aggregates alone).

### B13-P6 — Delta-debate the weekly catalyst lane
**VERDICT: KEEP-WITH-CONDITIONS.** Right pattern (the ledger/disruptor precedent), right lane to be cautious in (perishable edges). Conditions: (1) a REFUTED/FIRED shard forces re-debate (or resolution) regardless of price/date stability — verdict changes must never be cache-hit; (2) window alignment with P2 (above); (3) the `_cat_ctx()` fix (held-seat rows carrying `co:GDOT … UNDATED; live None`) ships with it — cache reuse on degraded context compounds.

### B13-P7 — Replace the catalyst Director's numeric HARD-CAP with verdict-based demotion
**VERDICT: KEEP.** Direct application of the proven skeptic-as-cap fix to the one funnel that can breach the ceiling; BBIO 84→78 was the cap binding, not information. Monitor one run for inflation (the audit's own condition suffices).

---

## 5. BASKET 14 (basket14.md)

### B14-P1 — Reserve Stage-D slots for early/steep-S-curve sub-$25B names
**VERDICT: KEEP.** The only composition fix that costs zero new agents (slot reallocation inside the existing ≤8/theme cut). Attack checked: `s_curve_stage` is an LLM map label (narrative input) — acceptable because the hard profitability gates remain the junk filter, and the 0-A/0-c5/modal-3 signature on the first 40 names is the platform's most cleanly replicated evidence. Keep the 5/3 split fixed for ≥2 graded runs so the effect is attributable.

### B14-P2 — Disruptor skeptic kill-tier
**VERDICT: KEEP-WITH-CONDITIONS.** The highest-vol book grading its own homework is indefensible given the GDOT proof. Conditions: (1) implement inside the unified skeptic (X1) — a third near-identical clone generator is the AX-W7 two-implementations trap in a new costume; (2) budget-neutral: lands with VB-P2's dedupe in the same change; (3) batch ≤6 for this web-heavy tier; (4) the audit's own tuning note (accept dated call guidance as primary source for momentum names) is load-bearing — without it, default-REFUTED razes the whole book and the tier gets turned off within two runs (the fate of all over-eager gates).

### B14-P3 — Beta-matched benchmark line next to the disruptor NAV
**VERDICT: KEEP.** This is the instrument that decides the book's existence; everything else in B14 is secondary. Conditions (small): use the simple same-inception SMH/QQQ NAV lines the audit itself offers, not the beta-weighted blend — fewer estimated parameters in the scoreboard the book will be judged by; generation-pinned reads on the tracking file (X6).

### B14-P4 — Fix `ev_gp` (dead `if False` branch, funded-leverage net debt, GM from Stage-B)
**VERDICT: KEEP.** Proven silent corruption of the book's only valuation guard; the `ev_gp_basis` degradation stamp is the right honesty pattern. No attack survives.

### B14-P5 — Make `entry_posture` real (PENDING_LIMIT) or delete it
**VERDICT: SPLIT — KILL the PENDING_LIMIT retrofit for now; KEEP the delete arm.**
- **Kill-fact (retrofit arm):** it modifies `_update_apex_tracking` — the shared, VERIFIED-correct TWR machinery for all baskets — to change fill mechanics mid-track-record, for a book whose right to exist is unproven until P3's scoreboard reads out. A mid-stream fill-regime change breaks NAV comparability (the before/after is no longer one methodology), which is an honest-track-record violation dressed as an honesty improvement. B13 could do PENDING_LIMIT honestly because it was append-only from day 1.
- Keep arm: delete the stamped-but-ignored field now (the audit is right that it reads as exercised discipline). Revisit real fills only if the book survives 2 quarters of P3 — and then as a new tracking epoch, stamped.

### B14-P6(a) — Reuse scale-out overlay shards as debate cache
**VERDICT: KILL.**
- **Kill-fact:** the scale-out overlay was a ONE-OFF (45 names, shipped to main 06-22, no refresh cadence — overlay only, no NAV, per the project record). By the time this ships, every shard is past the 28-day freshness bound the proposal itself sets — machinery keyed to a source that will never be fresh again. If the overlay ever becomes a recurring run, revisit; today it is dead code on arrival.

### B14-P6(b) — Stop debating perennially seatless themes
**VERDICT: KEEP-WITH-CONDITIONS.** The cost is real (defense_tech: ~8 debates/run, 0 seats ever). But as written it is a survivorship feedback loop: a theme that never seats stops being debated and therefore can never seat — the funnel-composition lesson inverted. Conditions: (1) frozen themes keep a 1-2 name monthly sentinel debate OR a deterministic re-open trigger from Stage-A/B screen stats (member count, gate-pass rate inflection); (2) the frozen list prints in the publish banner so the freeze is a visible dial, not silent rot.

### B14-P7 — Count measured SMH-beta toward the AI-infra theme cap
**VERDICT: KEEP-WITH-CONDITIONS.** The label-vs-factor gap (27.5% labeled vs ≈41% factor) is the book's most likely death. But a 2y-weekly single-benchmark beta conflates risk-on market beta with theme exposure (in an AI-led tape, everything volatile co-moves with SMH); CCJ's 0.66 carries wide error bars. Conditions: (1) shadow-report label-vs-factor exposure for 2 runs before the cap binds; (2) scale-don't-evict (as proposed); (3) fixed 0.6 threshold stamped as a versioned dial.

---

## 6. OPS (ops.md)

### OPS-P1 — Harden the launcher (drop `2>&1`, sentinel-gated auto-resume, fail loud)
**VERDICT: KEEP — the highest-priority item in all six audits.** Every methodology property only exists in weeks the run happens; the 06-28 log is three days old. Conditions: (1) the resume loop stays bounded at 2 and gates on the sentinel, as proposed; (2) the sentinel must distinguish "publish aborted by the AX-P1 gate" from "run died" — the gate prints its reason where the sentinel reads (else intentional aborts burn resume cycles and then page the operator with the wrong story).

### OPS-P2 — Change-detection gate / carry-forward for the main universe
**VERDICT: KEEP-WITH-CONDITIONS — the biggest run-economics win, and the proposal with the most dangerous unstated interaction.**
- **Cross-audit contradiction (axis f):** the value audit's whole defense of re-grading cached debates (VB §1.1) is "the debates are NOT stale — prep self-cleans weekly." OPS-P2 makes up to 70% of records deliberately 1-4 weeks stale. Carried records feed the value re-grade's `bear_fv_px`, `thesis_break_px`, MoS and exit rails at stale prices — the exact staleness class that produced the 87%-corrections rate, re-imported through the back door.
- Conditions (binding): (1) carried records get a deterministic freshness restamp — `_ttm_block` + live price — at carry time (no LLM needed); (2) `carried_from` age is exposed in `value_grade_input` rows, the CSV, and the Director prompt; (3) exits/stress in both posts recompute from live price, never the carried `live_price`; (4) finalists/seat-relevant names always re-debate (already in the proposal — it is the clause that keeps the money-bearing layer weekly; do not soften it); (5) start at a 21-day ceiling (the disruptor gate's precedent), widen to 28 only after 2 clean cycles.

### OPS-P3 — Generation-pinned GCS reads for every read-modify-write
**VERDICT: KEEP, unconditional.** Proven bug class (calibration_tracker), now sitting under the public NAV chain with two writers. Also binds prospectively: every NEW tracking writer (B14-P3's benchmark line, any B13 mark change) adopts it from day one (X6).

### OPS-P4 — Prep refuses to destroy the last completed run's archive
**VERDICT: KEEP.** Both trigger incidents observed within 10 days. Cap partial archives at 2, as proposed.

### OPS-P5 — Wire `fmp_facts.py` into ad-hoc debate prep
**VERDICT: KEEP — merged with DE-P5 into one work item.** Same defect, same fix, two audits; build it once at the prep seam.

### OPS-P6 — Batch width to the proven ceiling (prefer retry-in-workflow)
**VERDICT: KEEP-WITH-CONDITIONS.** The retry-in-workflow variant is the right call ONLY if the harness demonstrably surfaces per-agent failures to the JS layer — verify on one batch (the audit's own condition; it is load-bearing, not a nicety). If it doesn't, fall to BATCH=6 the same day; do not ship an unverified retry wrapper and keep the flaky width.

### OPS-P7 — Reserved-ticker `safe_name` quarantine
**VERDICT: KEEP-WITH-CONDITIONS.** The landmine is proven (CON.json committed; the 761-file near-disaster). The risk is the fix: 6+ read sites edited by hand, and a missed one = a silent empty debate for that ticker — the exact silent-failure class this review exists to kill. Conditions: (1) implement as ONE shared path-resolver helper used by every write AND read site (no scattered inline renames); (2) a selftest that round-trips all reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9) through write→read→publish joins, run in the weekly SKILL preflight; (3) grep-audit the `results_regime/`+`HIST_DIR` joins before shipping, as the audit says.

---

## 7. CROSS-SUBSYSTEM ISSUES THE SILOED AUDITS MISSED

**X1 — Four audits are rewriting the skeptic tier independently; nobody owns the composite.** DE-P4 (delete the cap field), VB-P1 (coverage stamps), VB-P2 (merge tiers), VB-P5 (CWC haircut), AX-P4 (catalyst rubric), B14-P2 (new tier), B13-P7 (cap removal in the catalyst Director) all touch one generator/consumer pair (`weekly_opus_refresh.py:1252-1349`, `_post_common.consume_skeptic`). Shipped as seven PRs they collide; shipped as one **unified skeptic redesign** (single generator, per-lane rubric, `kill_scope`, categorical `correction_severity`, coverage/staleness stamps, net agent count ≤ today's) they compose. This should be a single work item with a single owner-session.

**X2 — Publish-gate policy contradiction (AX-P1 vs VB-P1), resolved above:** hard-gate the deterministic post, soft-gate skeptic coverage, gate reason printed for OPS-P1's sentinel. Without the resolution, the two books ship opposite failure policies for the same failure.

**X3 — No global agent-budget ledger.** Proposals net roughly: OPS-P2 −80..100 debates, VB-P2 −10 skeptics, B13-P6 −12..15, B14-P6(b) −8..15, vs B14-P2 +13, VB-P3 +≤20, (DE-P8 +10, killed). The "fits one session" goal is the binding constraint and no audit tracks the sum. Rule: land reductions before additions, and print agents-invoked-per-run in the run log so the budget is a measured number, not a vibe.

**X4 — Rubric/dial versioning is a precondition every scoring proposal skipped.** DE-P1(gate), DE-P3, B13-P7, VB-P7, B14-P7 all change scoring/threshold semantics while the calibration loop (B13-P5, calibration v2) is supposed to learn from history. Every artifact needs a `rubric_version`/dial stamp or the E-vs-O series becomes uninterpretable across the change boundary. One shared constant, stamped everywhere.

**X5 — OPS-P2 silently invalidates the value book's freshness premise** (detailed under OPS-P2). The staleness that was eliminated by prep's self-clean returns by design; the value re-grade must become carry-aware or W4's optimistic bear anchors get worse, not better.

**X6 — The two-writer NAV race is about to gain writers.** OPS-P3 fixes the three known read-modify-write sites, but B14-P3 (benchmark line) and any B13 mark extension add new writers to the same GCS tracking files. The generation-pin rule must be a stated invariant for new code, not a one-time patch.

**X7 — No per-symbol cross-book risk aggregation exists.** FIP is simultaneously a B13 seat (10%, rtf-capped), an apex special-sit seat (1.5% risk-to-floor), and its catalyst-skeptic cap/corrections were dropped in `catalyst_seed` (B13-W4). Three subsystems hold three different FIP truths and the summed event risk appears nowhere. B13-P4's stamps are the fix's first half; the second half is one report line summing per-symbol exposure across books — cheap, and none of the audits proposed it.

**X8 — The 3-week counterfactual cohort (watchlist 108.7 vs held 102.1) is doing double duty as evidence.** Legitimate as a tiebreaker for freeing seats that are dead on documented facts (B13-P3); illegitimate as sizing evidence for growing lanes (AX-P3b, killed). Guard the distinction: the cohort becomes decision-grade only with resolutions and quarters, not marks and weeks.

**X9 — The nightly tier-1 path needs ONE status decision.** DE-P2 fixes its crash, DE-P6 optimizes its tokens, AX-P6 retires its Director — three independent treatments of one dormant path. Decide once: retired-in-place (loud header, port the sector cap, take DE-P2's 2-token fix as cheap insurance, skip DE-P6-nightly).

**X10 — The `value_conviction_cap` field needs a single lifecycle decision** (delete / consume / rename), currently proposed three different ways (DE-P4 delete, VB-P5 consume-as-threshold, AX-W8 rename-trap warning). Resolution: categorical severity replaces the number everywhere — both skeptic prompts, `_post_common` stamping, `publish_to_frontend.py:247`, and the UI field. Half-measures leave the proven bug's reintroduction seam open.

---

## 8. VERDICT SUMMARY

| # | Proposal | Verdict |
|---|----------|---------|
| DE-P1 | Conviction decoupling | KILL rewrite arm / KWC gate arm |
| DE-P2 | None-sort crash fix | KEEP |
| DE-P3 | Tiered moat cap | KEEP-WITH-CONDITIONS |
| DE-P4 | Delete numeric skeptic cap | KWC (merge w/ VB-P5 → categorical severity) |
| DE-P5 | Ad-hoc freshness | KEEP (merged w/ OPS-P5) |
| DE-P6 | Dedup/token trim | KILL nightly arm / KWC weekly arm (after OPS-P2) |
| DE-P7 | De-date Director prompts | KEEP |
| DE-P8 | Near-miss skeptic band | **KILL** (runner-ups already covered) |
| AX-P1 | Publish gate | KWC (hard on post, soft on skeptic) |
| AX-P2 | Regime size_units | KWC (expect no sizing alpha; WARN yes) |
| AX-P3a | Honest return goal | KEEP |
| AX-P3b | Grow special-sit lane | **KILL** (zero cycles run; n=3wk evidence; unstamped overlap) |
| AX-P4 | Lane contract in post + catalyst rubric | KEEP (urgent with AX-P1; inside X1) |
| AX-P5 | Publish runner_ups | KEEP |
| AX-P6 | Retire dormant Director | KEEP |
| VB-P1 | Skeptic coverage fail-loud | KEEP (platform policy) |
| VB-P2 | Merge skeptic tiers | KWC (inside X1, budget-neutral) |
| VB-P3 | Drawdown intake | KWC (cap in code; after OPS-P2) |
| VB-P4 | Bear-anchor flags | KEEP |
| VB-P5 | CWC haircut | KWC (categorical trigger, not numeric) |
| VB-P6 | Dead machinery/dates | KEEP |
| VB-P7 | Secular-load enforcement | KWC (warn 2 runs first) |
| B13-P1 | Resolution radar | KEEP |
| B13-P2 | Wire catalyst artifacts to entry gate | KEEP (best return/line) |
| B13-P3 | Free dead seats | KEEP |
| B13-P4 | Cross-book stamps + seed skeptic | KEEP |
| B13-P5 | Calibration report | KWC (min-n per cell) |
| B13-P6 | Delta-debate catalyst lane | KWC (verdict changes never cached) |
| B13-P7 | Remove Director hard-cap | KEEP |
| B14-P1 | S-curve reserved slots | KEEP |
| B14-P2 | Disruptor skeptic | KWC (inside X1) |
| B14-P3 | Beta benchmark | KEEP (simple variant) |
| B14-P4 | ev_gp fix | KEEP |
| B14-P5 | entry_posture | KILL PENDING_LIMIT arm / KEEP delete arm |
| B14-P6a | Scale-out cache reuse | **KILL** (source is a one-off; permanently stale) |
| B14-P6b | Prune seatless themes | KWC (sentinel debate / re-open trigger) |
| B14-P7 | Factor-based theme cap | KWC (shadow 2 runs) |
| OPS-P1 | Launcher hardening | KEEP (top priority) |
| OPS-P2 | Change-detection carry-forward | KWC (freshness restamp; carry-aware value grade) |
| OPS-P3 | Generation-pinned reads | KEEP |
| OPS-P4 | Prep archive protection | KEEP |
| OPS-P5 | fmp_facts into ad-hoc | KEEP |
| OPS-P6 | Batch width/retry | KWC (verify failure surfacing first) |
| OPS-P7 | Reserved-ticker quarantine | KWC (one resolver + selftest) |

**Recommended sequencing for a 1-person operator** (safety → economics → composition):
1. Same-day, no-risk: DE-P2, VB-P6, B14-P4, OPS-P4, AX-P5.
2. This week: OPS-P1, OPS-P3, VB-P1 (+AX-P1's post-only hard gate), B13-P1+P3, AX-P4 (before the next run — LBTYK mis-cap fires otherwise).
3. One work item, one session: the unified skeptic redesign (X1: VB-P2 + AX-P4 rubric + B14-P2 + DE-P4×VB-P5 severity).
4. Then economics: OPS-P2 (with its conditions), B13-P6, OPS-P6, DE-P5/OPS-P5.
5. Then composition, one change per book per cycle: B14-P1, VB-P3, DE-P1's gate arm, B13-P2.
6. Deferred a quarter: AX-P3(b), B14-P5 fills, DE-P6 weekly trim.
