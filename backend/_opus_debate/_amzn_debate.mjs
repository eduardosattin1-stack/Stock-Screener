export const meta = {
  name: 'amzn-debate',
  description: 'Ad-hoc all-Opus full Speculair debate over AMZN (Interrogator → Architect → CRO → Skeptic → Director), online-fetch, segment Sum-of-Parts framing; surfaces on the AMZN stock page',
  phases: [
    { title: 'Debate', detail: 'Interrogator/Architect/CRO, web-sourced', model: 'opus' },
    { title: 'Skeptic', detail: 'adversarial kill-check', model: 'opus' },
    { title: 'Director', detail: '0-100 conviction', model: 'opus' },
  ],
}

const DIR = 'backend/_opus_debate'
const RES = DIR + '/_adhoc_results'
const SKEP = DIR + '/_adhoc_skeptic'
const SYM = 'AMZN'
const CO = 'Amazon.com, Inc.'

const BRIEF = "Read CATALYST_WATCH_REGIME.md (repo root) for the current market regime and APPLY it: reward hard-dated catalysts inside the favorable window; PENALIZE Fed-cut/rate-rescue or past/out-of-window catalysts; prize resolution-driver independence. Let this MOVE the conviction/verdict."

phase('Debate')
log('Full Speculair debate over AMZN (segment SoP, online-fetch).')
await agent(
  'You run the COMPLETE multi-agent debate for ' + SYM + ' (' + CO + ') as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital. Judge AMZN as a MEGA-CAP QUALITY COMPOUNDER on its fundamentals (no theme overlay): the SUM-OF-PARTS (AWS cloud + North America retail + International + Advertising + Devices/other), the moat + its trend per segment, the growth + margin trajectory (AWS reacceleration + backlog, retail margin expansion, ads scaling, the AI/capex cycle + its FCF drag), and the valuation vs a segment SoP fair value.\n' +
  'NO data is bundled. Use WebSearch + WebFetch for AMZN MOST RECENT earnings call + the latest fundamentals: revenue + growth by SEGMENT (AWS / NA / Intl / Ads), operating margin by segment + trend, AWS growth rate + backlog, capex + FCF (and the AI-capex FCF drag), net cash, buybacks, shares, current price + market cap. If a fact is genuinely unfindable, say so and reason from fundamentals — NEVER fabricate.\n' +
  '1. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; full forensic dossier (8 sections + final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <STRENGTHENING|STABLE|DETERIORATING|PIVOTING> | MOAT: <WIDE|NARROW|ERODING|NONE> | MOAT_TREND: <WIDENING|STABLE|ERODING> | SECULAR_THREAT: <terminal|material|manageable|none>"). Write it to ' + DIR + '/dossiers/' + SYM + '.md.\n' +
  '2. PEER COMPS: AWS vs MSFT-Azure/GOOG-Cloud, retail vs the e-commerce/logistics cohort, Ads vs GOOG/META — verify each CURRENT live multiple online; write a peer_comps_note + where AMZN ranks on growth/margins/returns.\n' +
  '3. ARCHITECT: read ' + DIR + '/architect_system.txt; bull_thesis + bear_thesis AND a true SEGMENT Sum-of-Parts — value AWS (EV/EBIT or EV/sales on cloud peers), NA + Intl retail (EV/sales or EV/GMV), Advertising (ad-network multiple), Devices/other; sum to an equity value/share. Output sop_bull and sop_bear (each a per-share value + the parts breakdown).\n' +
  '4. CATALYST VERIFICATION (web): the load-bearing driver (AWS reaccel print, an AI/Bedrock ramp, a retail-margin inflection, a capex-peak/FCF-trough) — catalyst_status = FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE, dated.\n' +
  '5. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward; sanity-check vs the peer comps. Produce verdict (A/B/C), conviction (int 1-5), value_conviction (int 1-5, valuation-vs-SoP + quality only), moat (WIDE|NARROW|ERODING|NONE), moat_trend, secular_threat, secular_theme (id from ' + DIR + '/secular_themes.json or ""), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion.\n' +
  '6. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + SYM + '.json with: symbol(="' + SYM + '"), company(="' + CO + '"), sector(="Consumer Discretionary"), signal_type(="quality_compounder"), bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, verdict, conviction(int), value_conviction(int), moat, moat_trend, secular_threat, secular_theme, consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_dossier(FULL text), interrogator_score(int), trajectory, current_price(number or null), target_px(number or null), source(="opus_adhoc_online"), transcript_source(="web").\n' +
  'Reply exactly: DONE',
  { label: 'debate:AMZN(web)', phase: 'Debate', agentType: 'general-purpose', model: 'opus', effort: 'high' })

phase('Skeptic')
await agent(
  'You are the SPECULAIR SKEPTIC (Claude Opus 4.8) running an ADVERSARIAL kill-check on ' + SYM + ' (' + CO + '). Default REFUTED unless you can INDEPENDENTLY confirm the load-bearing facts vs a PRIMARY source (10-Q/K, the IR site, the earnings release). You see ONLY the bear side.\n' +
  '1. Read ' + RES + '/' + SYM + '.json.\n' +
  '2. ATTACK VECTORS (web): (a) STALE-ANCHOR — is sop_fair_value built on pre-print financials? (b) NUMBER TRUTH — do the load-bearing figures (AWS growth + backlog, segment margins, capex/FCF, share count) verify? (c) THESIS WEAKNESS — is AWS DECELERATING vs Azure/GCP; is the AI capex a structural FCF sink with unclear ROI; is the retail-margin story already priced; is the multiple full? (d) HIDDEN DISQUALIFIER — antitrust/regulatory, a capex air-pocket, FX/Intl drag.\n' +
  '3. Verdict: CONFIRMED | CONFIRMED_WITH_CORRECTIONS | REFUTED. Plus value_conviction_cap (int 1-5).\n' +
  '4. Write (Write tool) VALID JSON to ' + SKEP + '/' + SYM + '.json = {symbol(="' + SYM + '"), verdict, kill_fact, corrections, value_conviction_cap(int 1-5), evidence:[2-4 dated primary-source cites]}. Reply exactly: DONE',
  { label: 'skeptic:AMZN', phase: 'Skeptic', agentType: 'general-purpose', model: 'opus', effort: 'high' })

phase('Director')
await agent(
  'You are the SPECULAIR APEX DIRECTOR (Claude Opus 4.8, 1M context) assessing ' + SYM + ' (' + CO + ') for a high-conviction equity book.\n' +
  '1. Read CATALYST_WATCH_REGIME.md (repo root) + ' + DIR + '/macro_regime.json; one line on the regime + your stance.\n' +
  '2. Read ' + RES + '/' + SYM + '.json (the debate) + ' + SKEP + '/' + SYM + '.json (the skeptic).\n' +
  '3. Assign director_conviction (0-100, apex bands: 90-100 table-pounding/maximal asymmetry, 70-89 high-conviction, 50-69 solid, <50 watchlist — HARD-CAP at the skeptic value_conviction_cap×20; a REFUTED verdict forces <50), would_seat (bool, vs the +30-50%/12mo apex goal), one-line thesis, binding_reason (the single fact that gets it in or keeps it out — price vs SoP, AWS trajectory, the capex/FCF drag), posture (enter_now_carry | scale_in | wait_for_weakness | wheel-it | pass), expected_return_pct (to sop_fair_value from current), catalyst_status, moat.\n' +
  '4. Write (Write tool) VALID JSON to ' + DIR + '/_amzn_director.json = {regime, risk_stance, assessment:{symbol, director_conviction, would_seat, thesis, binding_reason, posture, expected_return_pct, catalyst_status, moat}, memo}. Reply exactly: DONE',
  { label: 'director:AMZN', phase: 'Director', model: 'opus', effort: 'xhigh' })

log('AMZN debate + skeptic + director complete.')
return 'DONE'
