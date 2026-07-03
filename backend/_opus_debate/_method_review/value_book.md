# Method Review — Speculair VALUE Book (rubric + post-layer)

Reviewer: Fable 5 (senior quant-methodology pass), 2026-07-01
Scope: `backend/weekly_opus_refresh.py` (value_input :608, VALUE_DIRECTOR_PROMPT :544-571, value_publish :1076, value_skeptic :1250), `backend/_opus_debate/_value_post.py`, `backend/_opus_debate/_post_common.py`, forensic ledger (:836-867, prep :2794-2816), live basket state `apex_basket_value.json` (2026-06-30 run).

Audited against the proven evidence set (conviction ceiling = funnel composition, skeptic-as-cap bug, freshness, ops pain, track-record verifications). Live basket at review time: 8 seats (EEFT 20.4%w, WKL.AS, HRB, UHS, THC, NTES, SCR.PA, HRMY), secular_load 70%, clean_anchors 3, corr avg 0.13, published downside −28.7%, regime-apex overlap 4/8.

---

## 1. WHAT WORKS (keep)

**1.1 Re-grading the cached debate instead of re-debating — SOUND, keep.** This was the focus question. Three reasons it holds:
- The debates are NOT stale: `prep()` self-cleans `results_regime/` every weekly run (weekly_opus_refresh.py:2660-2678), so the value re-grade always consumes THIS week's debates, not a mixed vintage.
- The catalyst-blind score is elicited *inside* the debate as a separate output: the CRO emits `value_conviction` "as if NO catalyst overlay existed... the two scores MUST be allowed to diverge" (workflow template :2880), and value_input prefers it over the regime-tilted `debate_conviction` (:729-732, prompt :550).
- The proven conviction-ceiling evidence says the bottleneck is FUNNEL COMPOSITION, not scoring. A second full 161-name debate under a value brief would double the multi-hour, 2-3-resume-cycle run cost to re-score the same priced-quality pool. That's the wrong trade. (The residual regime-frame leakage into SoP numbers is real — see W4 — but it's a second-order error vs. composition.)

**1.2 The deterministic post-layer with the P1 membership rule.** `_value_post.py` never changes membership (sole exceptions: skeptic demotion, gate_sync EXCLUDE), is idempotent via `--offline` cache (:83-96), and stamps everything it does. This earns its complexity because it makes the agentic layer auditable: sizing teeth (`moat_per_name_cap`, `_post_common.py:128-134`), correlation, stress, exits are all reproducible code, not prose.

**1.3 Funded-leverage solvency** (`_funded_solvency` weekly_opus_refresh.py:524-535, prompt :559-562). Correct basis (interest-bearing only; float/reserves excluded; financials exempt), joint-weakness near-veto only (leverage AND coverage AND maturity wall). This fixed a real Altman-Z artifact (EEFT/TNET/insurers) with a 12-line function. Keep exactly as is.

**1.4 Measured correlation + feed-forward.** 2y weekly log-return Pearson with a ≥60-common-week floor (`_value_post.py:294-341`), breach caps applied to units, and — the underrated part — the PRIOR run's measured pairs are injected into the next Director prompt so it must "argue AGAINST these real numbers, do not merely assert 'barely co-move'" (weekly_opus_refresh.py:766-778). This closed the assertion loophole. Live: it carries the UHS-THC 0.68 pair and the Director capped it (combined_caps 1.1u) even though the mechanical breach (≥0.7 AND >16%w) didn't fire — the human-in-the-prompt layer and the deterministic layer backstop each other.

**1.5 Skeptic-has-teeth (fork b) + the staleness guard's *intent*.** REFUTED physically demotes (`consume_skeptic`, `_value_post.py:100-157`); GDOT proves the kill-tier works. The numeric `value_conviction_cap` is stamped for display only — grepped the tree: nothing in the value path consumes it as a hard ceiling (only `publish_to_frontend.py:247` surfaces it to the UI). So the proven skeptic-as-cap bug is correctly ABSENT from the value book. Good.

**1.6 Forensic ledger re-checks** (:836-867, prep :2794-2816). Known EXCLUDEs get a short re-affirm instead of a full I→A→CRO debate; TTL 8 weeks; earnings rollover forces a full re-debate; re-affirmation doesn't extend the clock. Direct, honest SPEED win against the weekly self-clean amnesia.

**1.7 Honest self-measurement.** The 11a funnel stats (Spearman scan-vs-CRO, collapse rate, cross-lens rescues, :788-834) and the pool-quality banner ("Best-of-B basket... expect SLOW gap-closure", :1127-1131) publish the book's own limitation instead of hiding it. Rare and valuable.

---

## 2. WEAKNESSES / RISKS

### W1 — PROVEN (live, this basket): the skeptic tier fails OPEN — the top-weight seat is un-vetted and a REFUTED name is seated.
Evidence from the working tree, 2026-06-30 run:
- `apex_basket_value.json` mtime = Jun 30 13:16. The staleness guard (`_value_post.py:110-115`) drops any shard older than the apex file.
- `_skeptic/EEFT.json` is from **Jun 21** → silently ignored. EEFT is the **largest position (20.4% weight, 1.1 units, value_score 84)** and carries `skeptic_verdict: None` in the published basket.
- `_skeptic/THC.json` (Jun 18) → ignored; THC seated, verdict None.
- `_skeptic/HRMY.json` (Jun 18) is **REFUTED, cap 2** → ignored as stale; **HRMY sits in the apex with an ERODING moat and no fresh verdict**. The Director prompt (:567) makes an eroding name apex-eligible only "unless the skeptic CONFIRMS a durable moat" — the skeptic never confirmed anything; it last said REFUTED.

The staleness guard is correct in isolation (a stale verdict must never demote a fresh basket) but the *combination* — stale shard dropped + no requirement that a fresh shard exists — means partial skeptic runs (the multi-hour, resume-cycle ops reality) silently produce an unvetted book. `_value_post.main()` prints counts (:156) but asserts nothing. **Failure caused: the one proven kill-tier covers an arbitrary subset of the book, biased toward whatever batch completed before a resume, and nobody is told.**

### W2 — PROVEN (by the evidence set + live pool stats): the funnel starves the book; re-weighting the same pool can't produce value alpha.
`value_input()` grades exactly the `results_regime/*.json` set (:622), which prep() builds from `methodology_picks.json` — the priced-quality quant screen (:2686). The conviction ceiling (0/407 verdict-A on this funnel vs 10 verdict-A on the 17-name catalyst funnel) proves composition, not calibration, is the bottleneck; the book's own banner concedes "Best-of-B." The rubric, skeptic, correlation stress and sizing teeth are all *risk-reduction* machinery operating on a pool with no live mispricing in it. **Failure caused: the value book's expected excess return over a quality-value ETF is approximately the cost of running it.** The just-wired apex special-sit lane addresses this for the catalyst book only; the value book has no drawdown/forced-seller intake of its own.

### W3 — PROVEN (live): 50% cross-lens duplication with the regime apex.
Regime apex ∩ value apex = {EEFT, NTES, THC, UHS} = 4 of 8 seats. The CSV stamps `in_regime_apex` (:875-899) but nothing consumes it: no combined-exposure view, no overlap discipline, and the two NAV tracks (`speculair_apex_tracking` + `speculair_value_tracking`) each bank the same names' P&L. Additionally both books run *separate but near-identical skeptic tiers* over overlapping finalist sets (`value_skeptic` :1250 vs `regime_skeptic` :1301 — same default-REFUTED prompt, same dossier inputs, different shard dirs), so the overlapping names burn 2x Opus web-heavy agent calls per week for two verdicts that should agree. **Failure caused: (a) overstated diversification across the "3 books"; (b) real-money double-concentration if both books are followed; (c) pure waste in the most expensive phase.**

### W4 — PROVEN (live): the debate's adverse SoP is systematically optimistic — and the value book anchors exits/stress on it.
Live `stress_test`: `cro_bear_weighted_pct = +1.0`, `bear_case_invalid = true` — the weight-averaged *bear* fair value sits ABOVE spot for the whole basket. The post-layer correctly detects this and falls back to mechanical recession stress (`_value_post.py:279-290` — good design), but the same regime-framed debate also supplies `bear_fv_px` and `thesis_break_px` per name, and `exits_block` (:245-256) only sanity-checks `0 < tb < px`, not whether the break level is a real bear case or a bull's idea of one. This is the genuine cost of re-grading a regime-framed debate: the *numbers* (SoP bull/bear built while the brief rewarded catalyst asymmetry, :2851) leak optimism into the value book's risk rails. **Failure caused: thesis_break exits set too close to spot's downside fantasy → exits that never trigger; published per-name bear anchors that mislead sizing.**

### W5 — PROVEN (vs the evidence spec): CONFIRMED_WITH_CORRECTIONS carries zero consequence.
The proven fix for the skeptic-as-cap bug is "REFUTED→kill, CORRECTIONS→**modest haircut**, CONFIRMED→none." The value path implements kill (demote) and none, but CWC only *stamps* the correction + cap (`_value_post.py:133-139`); sizing is untouched (`moat_per_name_cap` keys only on cro_only/stale_anchor/moat_erosion). Live: WKL.AS/NTES CWC-cap 4, UHS/HRB/SCR.PA CWC-cap 3 — all sized purely by the Director. With an 87% CWC base rate the middle verdict is currently pure decoration. **Failure caused: a skeptic who found a load-bearing number wrong changes nothing about the position.** (SUSPECTED severity: low-moderate — most CWCs are minor corrections; the cap≤2 subset is the one that matters.)

### W6 — SUSPECTED: `cro_only` conflates "models dissent" with "models missing."
`stamp_cro_only` (`_value_post.py:161-168`): `n_pos` counts positive values among the mos_spread keys *present*; `value_input` only includes keys that computed (:708-710). A data-sparse name (e.g. an EU name where only 2 of 5 methods produced output, both positive) gets `mos_agreement_n=2` → half-sized as "CRO-only" even though 2/2 available models agree it's cheap. Conservative direction, so no blow-up — but it mislabels data sparsity as model dissent, and the memo requirement ("state why your SoP beats five dissenting models", prompt :553) is then built on a false premise. **Failure: wrong haircut reason on thin-coverage non-US names — exactly the pool where residual value alpha is likeliest.**

### W7 — PROVEN (live): the secular-load rule is prose-only and currently breached.
Live book: `book_secular_load_pct = 70` vs the ~60% line; the prompt requires only that the Director "defend the whole-book decline beta in the memo" (:565). The deterministic layer enforces per-theme caps (`secular_theme_caps`) but nothing enforces (or even warns on) the *book-level* load. A deep-value book that is 70% melting-ice-cube in a late-cycle fully-priced tape is the single biggest structural return risk this book carries, and the only control is that the Director wrote a paragraph. **Failure: shared junk/flight-to-quality factor hits ~70% of the book at once in a de-rate.**

### W8 — Minor hygiene (PROVEN in code):
- `MEMO_UNITS_20260609` migration map (`_value_post.py:42-45`) — self-documented as "DELETE after the first post-fix Director run"; several runs later it's still there. SAX.DE/ANF/BKNG are long gone, so it's inert, but it's exactly the kind of silent fallback that bites when one of those tickers re-enters without size_units.
- `value_publish` hardcodes `"universe": 161` (weekly_opus_refresh.py:1149) — a stale constant published to the UI every week regardless of the actual pool (pool_stats already carries the true `n_pool`).
- `value_grade_input.json` rows carry no as-of date; the Director prompt is undated (the proven freshness lesson from the ad-hoc paths — 87% CWC rate was largely staleness corrections). Cheap to stamp.

---

## 3. PROPOSALS (ranked)

### P1. [SAFETY] Skeptic coverage gate — fail loud, not open. **Effort: S.**
Mechanism: in `_post_common.consume_skeptic` (and thus both books), after merging shards, compute `uncovered = apex members with no FRESH shard` and (a) print a `WARN skeptic-coverage` naming them, (b) stamp `skeptic_verdict:"MISSING"` on each, (c) apply the existing half-size cap to uncovered members via `moat_per_name_cap` extra_flags, and (d) if a *stale* shard for a still-held member says REFUTED (the HRMY case), stamp `skeptic_stale_refuted:true` and half-size + flag for re-run instead of silently dropping it. Do NOT hard-block publish (partial runs are the ops norm); make the failure visible and priced.
Expected impact: eliminates the live failure class (top-weight seat un-vetted; stale-REFUTED seated). This is the highest defect-per-line fix available.
Risk: half-sizing on a merely-late shard penalizes a name the skeptic would have confirmed — acceptable; the fix is "run the skeptic," which the warning now forces.

### P2. [SPEED] One skeptic pass per unique finalist across both books — delete the duplicate tier. **Effort: S-M.**
Mechanism: merge `value_skeptic()` and `regime_skeptic()` (weekly_opus_refresh.py:1250/:1301 — the prompts differ by ~2 clauses) into one generator over `union(value finalists, regime finalists)`, writing to a single `_skeptic/` dir with the union of attack instructions (add the regime's "binary/soft catalyst dressed as hard" clause to the value prompt — it costs nothing). Both `_value_post` and `_regime_post` consume the same shards.
Expected impact: with 4/8 apex overlap plus runner-up overlap, ~30-40% fewer Opus web-heavy skeptic agents per week — directly attacks the 2-3-resume-cycle ops pain — and removes the PLX.PA/SCR.PA class of cross-surface verdict disagreement by construction.
Risk: a single verdict serves two rubrics; a name could be REFUTED on catalyst grounds that don't break the value case. Mitigate: skeptic emits `kill_scope: "value"|"catalyst"|"both"` and each post only demotes on its scope. (One extra field, not a new tier.)

### P3. [RETURN] Give the value book its own funnel slice — a drawdown/forced-seller intake. **Effort: M.**
Mechanism: in `prep()` (:2686-2706), union into `sym_meths` a small dedicated slice (≤20 names/week, tagged `value_drawdown`) screened deterministically from the nightly scan: quality names (positive FCF, funded_solvency strong/moderate, non-EXCLUDE) trading in the bottom decile of their own 2y range with a recent −25%+ drawdown, plus any spin-off/index-deletion/forced-seller flags already computed for Catalyst Watch. These debate through the normal pipeline; the value Director sees them as ordinary rows.
Expected impact — honest magnitude: this is where the proven evidence says the return lives (the SAME stack over a differently-composed funnel produced 10 verdict-A / 6 conviction-5). It will not manufacture a drawdown when the tape offers none; expect most weeks to add 0-3 credible candidates and occasional weeks (a sector de-rate) to transform the book. The alternative — keep grading the priced pool harder — is proven not to work.
Risk: universe growth lengthens the run (cap the slice; the forensic ledger already dampens repeat cost); drawdown screens catch falling knives — but that is precisely what the funded-leverage gate, skeptic and normalization machinery were built to filter, and today they filter a pool that doesn't need them.

### P4. [SAFETY] Bear-anchor honesty: cross-check `thesis_break_px`/`bear_fv_px` against the market anchor. **Effort: S.**
Mechanism: extend `exits_block`/`stress_block` (`_value_post.py:245-290`): flag any name whose `bear_fv_px >= price` individually (today only the aggregate is flagged) and any `thesis_break_px` above the 52w low (a "break" the market already visited without breaking the thesis is not a break level); stamp `bear_anchor_suspect:true` and publish per-name in the stress table. No sizing change — visibility first.
Expected impact: turns the live `bear_case_invalid=true` from a buried aggregate boolean into per-name accountability; feeds the skeptic targeting (a suspect bear anchor is a NUMBER-TRUTH attack). Modest but cheap.
Risk: 52w-low is a crude floor for genuinely re-rated names; it's a flag, not a gate, so the cost of a false positive is one line of Director prose.

### P5. [SAFETY] Implement the CWC haircut the evidence already prescribes — bounded, not a ceiling. **Effort: S.**
Mechanism: in `consume_skeptic`, when a FRESH shard is CWC with `value_conviction_cap <= 2`, set a boolean `skeptic_capped:true`; add it to the `moat_per_name_cap` extra_flags OR (half-size). Never consume the cap as a numeric score ceiling (the proven bug).
Expected impact: the middle verdict stops being decoration exactly in the subset (cap≤2) where the skeptic found the thesis load-bearing-wrong but not dead. Live it would have touched nothing this run (fresh caps are all ≥3) — which is the right amount of teeth.
Risk: with the 87% CWC base rate, prompt drift could inflate cap≤2 frequency; monitor the cap distribution in `_skeptic_results.json` for one month.

### P6. [SAFETY] Delete the dead machinery + stamp dates. **Effort: S.**
Mechanism: delete `MEMO_UNITS_20260609` (`_value_post.py:42-45` and the arg at :210); replace `"universe": 161` (weekly_opus_refresh.py:1149) with `pool_stats["n_pool"]`; add `"as_of"` to `value_grade_input.json` rows and a dated header line to `value_director_prompt.txt` (the proven freshness lesson, applied to the one path that lacks it).
Expected impact: no alpha; removes two silent-failure fuses and one standing UI lie.
Risk: none worth naming.

### P7. [RETURN] Enforce the book-level secular-load line deterministically. **Effort: S.**
Mechanism: in `_value_post`, compute the load from stamped fields (share of weight with material/terminal `secular_threat` or `moat_erosion=='CAP'`/ERODING); if >65%, scale the non-clean-anchor legs' units down pro-rata until ≤65% (weights only — P1 membership untouched), print what it did, and stamp `secular_load_enforced`. The Director's 60% prose defense remains, but the tail is capped in code.
Expected impact: caps the book's dominant structural risk (live: 70%). In a junk de-rate this is the difference between a −15% and a −25% book week. It costs some upside in melting-but-mispriced names — that is the explicit design intent of a value book with clean anchors.
Risk: overriding Director sizing judgment; mitigated by triggering only above 65% (a buffer past his own 60% line) and only scaling, never re-picking.

---

## 4. IF YOU ONLY DO ONE THING

**P1 — the skeptic coverage gate.** The kill-tier is the value book's one empirically-proven source of edge-protection (GDOT; REFUTED-demotes), and the live basket shows it silently not covering the largest position while a stale-REFUTED, eroding-moat name sits seated. Every other control in this book assumes the skeptic ran. Twenty lines in `_post_common.py` make that assumption either true or loudly false.
