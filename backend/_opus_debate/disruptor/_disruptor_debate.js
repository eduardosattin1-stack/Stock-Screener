export const meta = {
  name: 'speculair-disruptor-weekly',
  description: 'Weekly all-Opus DISRUPTOR debate (profitable secular toll-takers; theme map already produced peers). Director runs separately after disruptor-input.',
  phases: [{ title: 'Debate', model: 'opus' }],
}
const DIR = 'backend/_opus_debate/disruptor'
const RES = DIR + '/results'
const SYMS = []               // have a bundled FMP transcript (read local file)
const ONLINE_SYMS = [] // no FMP transcript — agent fetches the latest one online

// ── PHASE 1 — DEBATE: Interrogator -> Architect (bull/bear + Sum-of-Parts) -> CRO (reconcile). ──
// No Radar phase: the monthly theme map already produced peers/relative-comps. All names run as
// general-purpose agents so EVERY name (FMP + online) can web-verify its theme-load-bearing facts.
function debatePrompt(sym, online) {
  const BRIEF = "Read " + DIR + '/theme_map/' + sym + ".json — this name's assigned theme(s), value-chain position, and true competitors. This is a PROFITABLE-DISRUPTOR debate, not a catalyst debate: judge THEME DURABILITY (is the secular demand real and multi-year, or a capex air-pocket away from rollover), the company's LOAD-BEARING position in the chain (who can route around it, what breaks if it disappears), MOAT evidence (switching costs, IP, network effects — use the GROSS-MARGIN TRAJECTORY as the lie detector: expanding GM on growing revenue = pricing power; compressing GM = commoditization), and REINVESTMENT economics (incremental ROIC, TAM headroom). A live catalyst is neither a plus nor a requirement. In step 5, web-verify the THEME-LOAD-BEARING facts (backlog, hyperscaler/customer capex guidance, design wins, order trends) as of today — catalyst_status is still emitted for the record but must NOT drive the verdict."
  const step1 = online
    ? '1. Read ' + DIR + '/inputs/' + sym + ".json (fields metrics_str/sector/signal_type/company; metrics may include a SEGMENT REVENUE block). NO FMP transcript is bundled. Use WebSearch + WebFetch to find " + sym + "'s MOST RECENT earnings-call transcript; if none exists, get the latest quarterly results / earnings release / management commentary / investor presentation (IR site, Tikr, Seeking Alpha, Investing.com, Simply Wall St, MarketScreener, plus the latest regulatory filing). If genuinely nothing is findable, say so and reason from the fundamentals — never fabricate quotes or figures.\n"
    : '1. Read ' + DIR + '/inputs/' + sym + '.json (fields metrics_str/sector/signal_type; metrics may include a SEGMENT REVENUE block) and ' + DIR + '/transcripts/' + sym + '.txt.\n'
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital to a PROFITABLE SECULAR DISRUPTOR. Be skeptical and current-facts-driven.\n' +
    step1 +
    '2. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; produce the full forensic dossier (8 sections + final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...>"); note any CUSTOMER CONCENTRATION (top-customer revenue share) explicitly. Write it to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '3. PEER COMPS: read ' + DIR + '/theme_map/' + sym + '.json (this name\'s assigned theme(s), value_chain_position, load_bearing_score, true_competitors + relative_comps) as the relative-value lever for the valuation below (skip if the file is absent).\n' +
    '4. ARCHITECT: read ' + DIR + '/architect_system.txt; produce bull_thesis and bear_thesis, AND a SUM-OF-PARTS valuation — value the business by its PARTS (segment SoP from the SEGMENT REVENUE block x peer multiples where present; else whole-company intrinsic via peer multiple) then apply any overlays (net cash, announced asset-sales). Output sop_bull (favorable parts) and sop_bear (adverse parts, ASSUMING THE THEME PAUSES 12-18 MONTHS), each a per-share value + the parts breakdown.\n' +
    '5. THEME-LOAD-BEARING VERIFICATION (web, MANDATORY): identify the load-bearing theme facts (backlog, hyperscaler/customer capex guidance, design wins, order trends) and WebSearch their CURRENT status as of today. Also emit catalyst_status = FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE for the record (it must NOT drive the verdict). Dated evidence; never fabricate.\n' +
    '6. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward (downside-to-break vs upside-to-fair); judge the GROSS-MARGIN TRAJECTORY as the moat lie-detector (state gm_trajectory: direction + 3-yr numbers); sanity-check the multiple against the theme_map true_competitors. Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion. THEN, separately, value_conviction (int 1-5): the value case judged on valuation vs the SoP fair value + forensic quality ONLY. The two scores MUST be allowed to diverge.\n' +
    '7. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with: symbol(="' + sym + '"), sector, signal_type(="disruptor"), themes(array, from theme_map), value_chain_position, load_bearing_score(int), gm_trajectory(one line: direction + 3-yr numbers), bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, verdict, conviction, value_conviction(int), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_score(int), trajectory, source(="' + (online ? 'opus_disruptor_online' : 'opus_disruptor_mod') + '"), transcript_source(="' + (online ? 'web' : 'fmp') + '").\n' +
    'Reply exactly: DONE'
}

const ALL = SYMS.map(s => ({ sym: s, online: false }))
  .concat(ONLINE_SYMS.map(s => ({ sym: s, online: true })))
log(`Disruptor Opus debate over ${ALL.length} names (${SYMS.length} FMP + ${ONLINE_SYMS.length} online-fetch), then Director.`)
phase('Debate')
const BATCH = 8   // rate-limit safety: run 8 web-heavy agents at a time (429s).
for (let b = 0; b < ALL.length; b += BATCH) {
  log(`Debate batch ${Math.floor(b / BATCH) + 1}/${Math.ceil(ALL.length / BATCH)} (names ${b + 1}-${Math.min(b + BATCH, ALL.length)} of ${ALL.length})`)
  await parallel(ALL.slice(b, b + BATCH).map(it => () => agent(
    debatePrompt(it.sym, it.online),
    { label: 'disruptor:' + it.sym + (it.online ? '(web)' : ''), phase: 'Debate', agentType: 'general-purpose', model: 'opus' })))
}
// NO in-workflow Director: the Director grades disruptor_grade_input.json, which `disruptor-input`
// builds from THESE debate results AFTER this workflow (the §7.1 sequence: Workflow -> disruptor-input
// -> Director subagent). Running it here would read a non-existent/stale grade-input. Debate-only.
log('Disruptor debate complete (Director runs separately after disruptor-input).')
return 'DONE'
