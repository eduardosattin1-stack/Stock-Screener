export const meta = {
  name: 'catalyst-seats-debate',
  description: 'Debate the 3 held Basket-13 SEATS that were missing from the candidate funnel (FIG/GDOT/WVE) so every B13 name has a catalyst debate on its stock page. Debate + Skeptic only — does NOT run a Director (would clobber the 17-name _catalyst_director.json).',
  phases: [
    { title: 'Debate', detail: '3 missing B13 seats x Interrogator/Architect/CRO', model: 'opus' },
    { title: 'Skeptic', detail: 'adversarial primary-source kill-check', model: 'opus' },
  ],
}

const DIR = 'backend/_opus_debate'
const RES = DIR + '/_catalyst_results'
const SKEP = DIR + '/_catalyst_skeptic'

const THEME = "an EVENT-DRIVEN SPECIAL SITUATION — the thesis is NOT business quality or compounding; it is the SPREAD between the live price and the EVENT-RESOLVED value (deal close / forced-seller supply clearing / SoP / FDA-pathway), gated on the catalyst firing, with a defined downside FLOOR that bounds the loss. These names look CHEAP-AND-BAD on quality / moat / value metrics BY DESIGN — the catalyst carries the thesis. Judge the ASYMMETRY (upside-to-target vs downside-to-floor), the catalyst's LIVE status, and the floor's reality."

const BRIEF = "A PENDING_HARD dated/binding catalyst inside the window, live price below the event-resolved target AND a verified downside floor (defined risk), is an AGGRESSIVE-ENTRY (verdict A / conviction 5) setup — do NOT reflexively cap it like a priced compounder. PENALIZE a FIRED / SOFT_EXTENDED / ARB (trading-through-terms) catalyst. value_conviction = the margin of safety to the VERIFIED downside floor, not a franchise moat."

const NAMES = [
  { sym:'FIG',  co:'Figma Inc',        cluster:'Idiosyncratic',   label:'forced-seller', ctx:'forced-seller SoP (post-IPO lockup / supply overhang clearing); UNDATED; live ~$18.88 vs target $32.00 / floor $17.50; SoP R:R 3.02; edge H, held SEAT' },
  { sym:'GDOT', co:'Green Dot Corp',   cluster:'Deal-completion', label:'M&A close',     ctx:'merger-arb, generic deal close; HARD DATE 2026-09-30; live ~$12.75 vs target $14.23 / floor $11.80; spread R:R 1.56; edge M, held SEAT' },
  { sym:'WVE',  co:'Wave Life Sciences',cluster:'FDA/biotech',    label:'FDA pathway',   ctx:'bio binary, FDA pathway feedback; HARD DATE 2026-07-31; live ~$5.78 vs target $11.00 / floor $3.50; binary EV +20.6%; edge H, held SEAT (binary — B13 only, NOT apex-lane eligible)' },
]

const SYMS = NAMES.map(n => n.sym)
function chunk(a, n) { const o = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o }

function debatePrompt(n) {
  const sym = n.sym
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' (' + n.co + ') as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator. Judge ' + sym + ' as ' + THEME + '\n' +
    'CATALYST DOSSIER (Catalyst-Watch board, a HELD Basket-13 seat): ' + n.ctx + '. Super-cluster: ' + n.cluster + '.\n' +
    'MANDATORY web verification: WebSearch + WebFetch the CURRENT LIVE status of the load-bearing catalyst as of today — the deal/merger close timeline + regulatory step, the lockup/forced-seller process, the FDA pathway/meeting outcome. Confirm the live price + a realistic target and the downside floor. If the catalyst already FIRED, slipped, or the spread closed, SAY SO. Never fabricate a date/status.\n' +
    '1. INTERROGATOR: read ' + DIR + '/interrogator_system.txt for the forensic DISCIPLINE applied to the EVENT (is it real/dated/binding; the verified downside floor; red flags — dilution/ATM, lockup, going-concern, CVR, second-request). Final line "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <...> | MOAT: <...> | MOAT_TREND: <...> | SECULAR_THREAT: <...>". Write to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '2. ARCHITECT: read ' + DIR + '/architect_system.txt; bull_thesis = catalyst resolves to target; bear_thesis = it fails to floor; sop_bull / sop_bear = the win value / the verified floor; base SoP = probability-weighted.\n' +
    '3. CATALYST VERIFICATION (web, MANDATORY): catalyst_status = FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE, dated.\n' +
    '4. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE to sop_fair_value (+ breakdown) + risk_reward (upside-to-target vs downside-to-floor). verdict (A/B/C) + conviction (int 1-5) on the EVENT asymmetry (5/A = live PENDING_HARD dated catalyst, live well below the event-resolved target, verified real floor). value_conviction (int 1-5) = margin of safety to the floor. moat / moat_trend / secular_threat (mostly NONE here), secular_theme "". consensus_delta, valley_of_death, positioning_washout, forcing_function (the hard date/trigger), moderator_conclusion, catalyst_summary.\n' +
    '5. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with EXACTLY: symbol(="' + sym + '"), company(="' + n.co + '"), cluster(="' + n.cluster + '"), driver(="' + n.label + '"), bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, catalyst_summary, dated_milestone, forcing_function, verdict, conviction(int 1-5), value_conviction(int 1-5), moat, moat_trend, secular_threat, secular_theme, consensus_delta, valley_of_death, positioning_washout, moderator_conclusion, interrogator_dossier(FULL text), interrogator_score(int 1-5), trajectory, live_price(number or null), target_px(number or null), downside_floor(number or null), source(="opus_catalyst_online"), transcript_source(="web").\n' +
    'Reply exactly: DONE'
}

function skepticPrompt(n) {
  const sym = n.sym
  return 'You are the SPECULAIR SKEPTIC (Claude Opus 4.8) running an ADVERSARIAL kill-check on ' + sym + ' (' + n.co + '), a HELD Basket-13 event-driven seat (' + n.label + ', ' + n.cluster + '). Default REFUTED unless you can INDEPENDENTLY confirm the load-bearing facts vs a PRIMARY source. You see ONLY the bear side.\n' +
    '1. Read ' + RES + '/' + sym + '.json.\n' +
    '2. ATTACK VECTORS (web): (a) is the catalyst genuinely LIVE + dated + binding, or fired / slipped / priced? (b) is the target real or fantasy? (c) is the downside floor real (what backstops the price) or does it break (dilution/ATM, going-concern, lockup flood, financing contingency)? (d) hidden disqualifier — single-binary with no floor, trading through terms, a second-request / CRL risk the bull ignores.\n' +
    '3. Verdict: CONFIRMED | CONFIRMED_WITH_CORRECTIONS | REFUTED. Plus conviction_cap (int 0-100).\n' +
    '4. Write (Write tool) VALID JSON to ' + SKEP + '/' + sym + '.json = {symbol(="' + sym + '"), verdict, kill_fact, corrections, conviction_cap(int 0-100), evidence:[2-4 dated primary-source cites]}. Reply exactly: DONE'
}

phase('Debate')
log('Debating the 3 missing B13 seats: ' + SYMS.join(', '))
await pipeline(
  NAMES,
  n => agent(debatePrompt(n), { label: 'debate:' + n.sym, phase: 'Debate', agentType: 'general-purpose', model: 'opus', effort: 'high' }),
  (_r, n) => agent(skepticPrompt(n), { label: 'skeptic:' + n.sym, phase: 'Skeptic', agentType: 'general-purpose', model: 'opus', effort: 'high' }),
)
log('Missing-seat debates complete: ' + SYMS.join(', '))
return 'DONE'
