export const meta = {
  name: 'fable-methodology-review',
  description: 'Fable 5 revision of the Speculair methodology: 6 parallel subsystem audits (debate engine, apex book, value book, basket-13 catalyst sleeve, basket-14 disruptor, cross-cutting ops) → adversarial red-team → synthesized proposal report (more return / faster / safer)',
  phases: [
    { title: 'Audit', detail: '6 subsystem auditors in parallel (Fable)' },
    { title: 'Red team', detail: 'adversarial kill-pass over the proposals' },
    { title: 'Synthesis', detail: 'prioritized revision report' },
  ],
}

const OUT = 'backend/_opus_debate/_method_review'

const EVIDENCE = `EMPIRICAL EVIDENCE ALREADY PROVEN (do not re-derive; audit AGAINST it):
- CONVICTION CEILING: across 407+ debated priced-quality names the pipeline produced 0 verdict-A / 0 conviction-5 / Director-max 78 (modal conviction 2). The SAME stack over the 17-name Basket-13 catalyst funnel produced 10 verdict-A, 6 conviction-5, 2 Director-80+ (BBIO 84, FIP 83). => the return bottleneck is FUNNEL COMPOSITION (priced-quality compounders), not calibration. An apex equity special-sit lane (catalyst-framed, floor-sized, <=3 seats / <=15% NAV / 1.5% risk-to-floor) was just wired, takes effect next weekly run.
- SKEPTIC-AS-CAP BUG (fixed in the scale-out re-grade): using the Skeptic's numeric cap as a hard ceiling crushes all scores (~35); correct = verdict-based demotion (REFUTED->kill, CORRECTIONS->modest haircut, CONFIRMED->none). The weekly pipeline still consumes value_conviction_cap numerically in places — check.
- FRESHNESS: the weekly path date-stamps (TTM "as of" block ~live_debate_engine.py:924, analyst targets :1130); ad-hoc online paths don't pre-inject dated metrics -> 87% CONFIRMED_WITH_CORRECTIONS rate, one staleness kill (MYRG). GDOT: CRO said A/5, Skeptic REFUTED (thin arb) — the kill-tier works.
- OPS PAIN: weekly run is multi-hour, needs 2-3 resume cycles; >16-wide web-heavy agent bursts trip a server-side rate limit (batch <=6 works); debate BATCH=8; models pinned sonnet radar / opus debate+director / skeptic opus (Fable directors retired 06-13 for availability, back now?).
- TRACK RECORD: /performance had censoring bias (flip-sign MTM); baskets' Live YTD TWR verified correct; B13 stamps honest (live-price entries, PENDING_LIMIT, no fiction fills); B13 caps: <=2/driver, <=40 NAV-pts/cluster, <=5 bio lane, rtf<=1.5%, binaries defined-risk <=2%.
- Value book: funded-leverage solvency replaced Altman-Z; hidden-factor correlation stress + measured 2y correlation matrix caps >=0.7 pairs; CRO-only legs half-sized; skeptic-has-teeth (REFUTED demotes). Rotation discipline (ledger + re-add-needs-thesis-change) shipped 06-22.
- Regime brief: late-cycle fully-priced; reward hard-dated catalysts, penalize fired/rate-rescue; conviction-5 requires below-SoP + live un-fired catalyst.`

const AREAS = [
  { key: 'debate_engine', title: 'Multi-agent debate engine (Radar/Interrogator/Architect/CRO)', files: 'backend/live_debate_engine.py (Radar prompts ~:661-700, Interrogator ~:702-736, Architect ~:738-752, Moderator/CRO ~:754-810, freshness block ~:860-930, debate_candidate ~:1179-1389, basket select ~:1406), backend/_opus_debate/interrogator_system.txt, architect_system.txt, moderator_system.txt, secular_themes.json', focus: 'prompt quality + biases (is the 1-5 rubric well-anchored; is the moat-erosion cap at value_conviction<=3 too blunt; signal-type trap cap; catalyst_status discipline), the single-agent-per-name design vs seat-per-agent, transcript bundling vs online fetch, peer_groups usage, what a conviction actually MEANS downstream, redundancy between Interrogator sections and CRO questions, cost per name' },
  { key: 'apex_book', title: 'Speculair APEX (regime) book: Director + skeptic + post + sizing', files: 'backend/live_director_agent.py (bands ~:194, G1-G4 ~:326-382), backend/weekly_opus_refresh.py (_WORKFLOW_TEMPLATE Director STEPs ~:2906-2916 incl the new STEP-3b special-sit lane, regime_skeptic ~:1300-1346), backend/_opus_debate/_regime_post.py, _post_common.py, publish_to_frontend.py (_apex_weights + SS floor-sizing ~:286-330)', focus: 'does the 0-100 banding + conviction>=3 eligibility + correlation stress + rotation ledger produce a coherent book; the +30-50%/12mo return goal vs a funnel that (proven) contains no verdict-A names — is the goal achievable without the special-sit lane; sizing (size_units vs conviction fallback); whether skeptic value_conviction_cap is consumed numerically (the known bug pattern); NAV/tracking integrity; runner_ups/watchlist usage' },
  { key: 'value_book', title: 'Speculair VALUE book: rubric + post-layer', files: 'backend/weekly_opus_refresh.py (value_input/value_publish, value_director_prompt generation, value_skeptic ~:1280), backend/_opus_debate/_value_post.py, forensic_ledger usage', focus: 'the pure-value re-grade of the SAME debate (is re-grading cached debates sound vs re-debating), funded-leverage solvency, cyclical-peak normalization, the deterministic post-layer (half-sizing CRO-only legs, stale anchors, measured correlation matrix, thesis_break exits, gate_sync), secular-load gauge + clean-anchor floor, whether the value book overlaps the apex too much (cross-lens duplication), and where value alpha would actually come from in a priced tape' },
  { key: 'basket13', title: 'Basket 13 catalyst sleeve (funnel -> CRO -> caps -> tracking) + the new apex lane', files: 'backend/_basket13_candidates.py (dials), _basket13_gen.py (CRO 4-surfaces + Director prompts), _basket13_inject.py (caps + validators + watchlist_state), _basket13_mark.py, _basket13_README.md, plus the full-stack catalyst debate artifacts backend/_opus_debate/_catalyst_director.json + _catalyst_summary.csv and weekly_opus_refresh.py catalyst-prep/catalyst-seed', focus: 'the funnel dials (tier/edge/blocking/6-month window), the lightweight CRO-only debate vs the proven full-stack catalyst debate (should B13 upgrade to full-stack given it found 10 verdict-A?), cap structure sanity, manual resolve CLI (should resolutions auto-detect?), expected-vs-actual calibration loop (re-fit dials quarterly — is it real?), the on-deck watchlist track record, and how the new apex special-sit lane should coexist without double-counting risk' },
  { key: 'basket14', title: 'Basket 14 Disruptor lens (thematic book)', files: 'backend/weekly_opus_refresh.py (disruptor_universe/disruptor_prep/disruptor_input/disruptor_publish, _DISRUPTOR_WORKFLOW_TEMPLATE ~:2527), backend/_opus_debate/disruptor/ (themes taxonomy, director prompt), backend/_opus_debate/_disruptor_post.py (theme caps MAX 3/theme 30%/theme)', focus: 'theme taxonomy quality + monthly rebuild cadence, whether the disruptor debate framing differs enough from regime to justify a separate debate (cost), theme-cap adequacy vs the one-factor-in-costumes problem (AI-infra names correlate ~1), sizing/NAV isolation, entry timing (momentum names bought after they ran — the scale-out evidence says the whole theme screens rich), what would make this book actually additive vs a beta basket' },
  { key: 'ops', title: 'Cross-cutting ops: speed, cost, safety, data hygiene', files: 'backend/weekly_opus_refresh.py (prep self-clean, BATCH, resume paths), backend/run_speculair_weekly.ps1 + the SKILL runbook structure, backend/_opus_debate/publish_to_frontend.py (GCS pushes), memory of: rate-limit bursts, 2-3 resume cycles, GCS read-after-write staleness, the CON.json reserved-name landmines, model seats', focus: 'END-TO-END RUNTIME (what is serial that could be parallel; the debate BATCH=8 vs rate-limit ceiling; could Radar/peer phases run on cheaper models; could unchanged names skip re-debate via a change-detection gate instead of full weekly re-debate), COST (tokens per weekly run; which seats could drop to sonnet/haiku without quality loss), SAFETY (data freshness injection for ad-hoc paths, GCS read-modify-write staleness, the reserved-name CON.json files on main, single-writer assumptions with a parallel session, guard coverage in the SKILL), and RELIABILITY (resume ergonomics, what fails silently)' },
]

function auditPrompt(a) {
  return 'You are FABLE 5 acting as a senior quant-methodology reviewer revising the CB Screener / Speculair platform. Repo root: C:\\Users\\Bruno\\Stock-Screener. Your subsystem: ' + a.title + '.\n\n' +
    EVIDENCE + '\n\n' +
    'READ the actual code (Read/Grep): ' + a.files + '. Line refs are approximate — locate precisely.\n' +
    'FOCUS: ' + a.focus + '\n\n' +
    'Produce a rigorous audit with:\n' +
    '1. WHAT WORKS (keep — with the reason it earns its complexity).\n' +
    '2. WEAKNESSES / RISKS — each with concrete file:line evidence and the failure it causes. Distinguish PROVEN (evidence above / in code) vs SUSPECTED.\n' +
    '3. PROPOSALS — each tagged [RETURN] (more alpha), [SPEED] (faster/cheaper runs), or [SAFETY] (fewer silent failures / more honest tracking), with: the specific change (file + mechanism), expected impact (be honest about magnitude), effort (S/M/L), and the main risk of doing it. Prefer proposals that DELETE or SIMPLIFY over ones that add machinery. Do NOT propose things already shipped (see evidence). 4-8 proposals max — ranked.\n' +
    '4. ONE "if you only do one thing" pick.\n\n' +
    'Write (Write tool) the full audit as markdown to ' + OUT + '/' + a.key + '.md. Then reply with ONLY a <=10-line summary: the 3 sharpest weaknesses + your top proposal per tag.'
}

phase('Audit')
log('Fable methodology review: 6 subsystem audits in parallel...')
const summaries = await parallel(AREAS.map(a => () =>
  agent(auditPrompt(a), { label: 'audit:' + a.key, phase: 'Audit', agentType: 'general-purpose', effort: 'high' })))

phase('Red team')
log('Adversarial pass over all six audits...')
await agent(
  'You are FABLE 5 as the RED TEAM. Six methodology audits of the Speculair platform were just written to ' + OUT + '/{debate_engine,apex_book,value_book,basket13,basket14,ops}.md. Read ALL SIX.\n\n' +
  EVIDENCE + '\n\n' +
  'Your job is to KILL weak proposals before they reach the owner: for EVERY proposal across the six files, attack it on (a) overfitting-to-backstory / narrative risk, (b) complexity-vs-payoff (does it add machinery the 1-person operator must maintain?), (c) whether it silently breaks the honest-track-record principles (live-price stamps, no back-fill, censoring-aware), (d) look-ahead / survivorship leakage, (e) cost/runtime blowup, (f) contradiction with another audit\'s proposal. Verdict each: KEEP / KEEP-WITH-CONDITIONS (state them) / KILL (state the kill-fact). Also list any CROSS-SUBSYSTEM issue the siloed audits missed. Write (Write tool) to ' + OUT + '/redteam.md. Reply with a <=8-line summary: kill count, the 3 most important KEEPs, the worst idea you killed.',
  { label: 'redteam', phase: 'Red team', agentType: 'general-purpose', effort: 'xhigh' })

phase('Synthesis')
log('Synthesizing the final revision report...')
const final = await agent(
  'You are FABLE 5 writing the FINAL methodology revision report for the Speculair platform owner (a hands-on solo operator; plain language, no hedging filler). Read ' + OUT + '/{debate_engine,apex_book,value_book,basket13,basket14,ops}.md AND ' + OUT + '/redteam.md.\n\n' +
  EVIDENCE + '\n\n' +
  'Write (Write tool) METHODOLOGY_REVIEW_FABLE.md at the repo root with EXACTLY these sections:\n' +
  '# Speculair Methodology Review (Fable 5)\n' +
  '## Executive summary — <=12 lines: the honest state of the system + the 3 moves that matter most.\n' +
  '## Scorecard — a table: subsystem | what it does well | sharpest weakness | grade (A-F).\n' +
  '## Top 10 revisions — ONLY red-team KEEP / KEEP-WITH-CONDITIONS items, ranked by impact-per-effort. Each: #, name, tag [RETURN]/[SPEED]/[SAFETY], the change (file + mechanism, 2-4 lines), expected impact (honest), effort S/M/L, red-team conditions if any.\n' +
  '## Quick wins (this week) — the S-effort subset, as a checklist.\n' +
  '## Structural bets (this quarter) — the M/L subset with sequencing (what unlocks what).\n' +
  '## Do NOT do — the red-team kills worth remembering, one line each with the kill-fact.\n' +
  '## What to leave alone — parts that earn their complexity; name them so future sessions do not churn them.\n' +
  'Keep the whole report <=350 lines. Cite file:line where it makes a claim actionable. Then reply with ONLY the Executive summary text + the Top-10 table in compact form.',
  { label: 'synthesis', phase: 'Synthesis', effort: 'xhigh' })

log('Methodology review complete → METHODOLOGY_REVIEW_FABLE.md')
return final
