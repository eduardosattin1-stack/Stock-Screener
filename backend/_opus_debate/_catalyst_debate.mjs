export const meta = {
  name: 'catalyst-funnel-debate',
  description: 'DIAGNOSTIC: run the FULL Speculair debate (Interrogator/Architect/CRO + Skeptic + Director) over the 17-name Basket-13 catalyst funnel, to test whether the event-driven special-sit archetype surfaces a verdict-A / conviction-5 / Director-80+ that the priced-quality funnels never have',
  phases: [
    { title: 'Debate', detail: '17 catalyst names x Interrogator/Architect/CRO, web-verify the event', model: 'opus' },
    { title: 'Skeptic', detail: 'adversarial: is the catalyst live + the floor real', model: 'opus' },
    { title: 'Director', detail: '0-100 conviction on the apex bands; count A / 5 / 80+', model: 'opus' },
  ],
}

const DIR = 'backend/_opus_debate'
const RES = DIR + '/_catalyst_results'
const SKEP = DIR + '/_catalyst_skeptic'

const THEME = "an EVENT-DRIVEN SPECIAL SITUATION — the thesis is NOT business quality or compounding; it is the SPREAD between the live price and the EVENT-RESOLVED value (deal close / PDUFA-FDA decision / clinical readout / spin + index flow / forced-seller supply clearing / activist outcome), gated on a HARD-DATED catalyst firing, with a defined downside FLOOR (recovery / deal-break / bear value) that bounds the loss. These names look CHEAP-AND-BAD on quality / moat / value metrics BY DESIGN — the catalyst carries the thesis, not the franchise. Judge the ASYMMETRY (upside-to-target vs downside-to-floor), the catalyst's LIVE status, and the floor's reality."

const BRIEF = "Apply the catalyst-regime discipline: a PENDING_HARD dated/binding catalyst INSIDE the window, with the live price well below the event-resolved target AND a verified downside floor (defined risk), is an AGGRESSIVE-ENTRY (verdict A / conviction 5) setup — that is the whole point of this funnel; do NOT reflexively cap it like a priced compounder. PENALIZE a FIRED (already-resolved / re-rate spent), SOFT_EXTENDED (undated / serially-slipping), or ARB (trading through terms, edge gone) catalyst. The compounder moat-erosion cap does NOT apply to a defined-risk special-sit — value_conviction here = the margin of safety to the VERIFIED downside floor, not a franchise moat."

const NAMES = [
  { sym:'AAUC', co:'Allied Gold',                       cluster:'Deal-completion', label:'M&A close',        ctx:'merger-arb, foreign-regulator close; HARD DATE 2026-07-29 (42d); live $25.26 vs target $31.54 / floor $23.00; spread R:R 2.78; edge M, ACTIVE' },
  { sym:'AMLX', co:'Amylyx Pharmaceuticals',            cluster:'FDA/biotech',     label:'FDA readout',      ctx:'bio binary, FDA clinical readout; HARD DATE 2026-09-30 (105d); live $14.59 vs target $28.00 / floor $4.00; win_prob 0.62, payoff 1.27x, EV +29%; edge M, ACTIVE' },
  { sym:'BBIO', co:'BridgeBio Pharma',                  cluster:'FDA/biotech',     label:'PDUFA',            ctx:'bio binary, FDA approval decision (PDUFA); HARD DATE 2026-11-27 (163d); live $66.80 vs target $105 / floor $58; win_prob 0.85, payoff 4.34x, EV +47%; edge H, ACTIVE' },
  { sym:'EYPT', co:'EyePoint Pharmaceuticals',          cluster:'FDA/biotech',     label:'FDA readout',      ctx:'bio binary, FDA clinical readout; HARD DATE 2026-07-31 (44d); live $13.03 vs target $37.50 / floor $5.50; win_prob 0.60, payoff 3.25x, EV +90%; edge H, ACTIVE' },
  { sym:'FIP',  co:'FTAI Infrastructure',               cluster:'Idiosyncratic',   label:'forced-seller/refi',ctx:'forced-seller recovery, distressed refi / restructuring; HARD DATE 2026-09-30 (105d); live $4.82 vs target $9.00 / floor $3.90; recovery R:R 4.54; edge H, ACTIVE' },
  { sym:'UNF',  co:'UniFirst',                          cluster:'Deal-completion', label:'M&A close',        ctx:'merger-arb, US antitrust (HSR/FTC) clearance; HARD DATE 2026-11-30 (166d); live $264.83 vs target $291.07 / floor $257.91; spread R:R 3.79; edge M, ACTIVE' },
  { sym:'VRDN', co:'Viridian Therapeutics',             cluster:'FDA/biotech',     label:'FDA readout',      ctx:'bio binary, FDA clinical readout; HARD DATE 2026-06-30 (13d, IMMINENT); live $16.35 vs target $35.00 / floor $8.00; win_prob 0.90, payoff 2.23x, EV +98%; edge H, ACTIVE' },
  { sym:'AQST', co:'Aquestive Therapeutics',            cluster:'FDA/biotech',     label:'PDUFA',            ctx:'bio binary, FDA approval decision; HARD DATE 2026-09-30 (105d); live $4.17 vs target $8.50 / floor $2.75; win_prob 0.70, payoff 3.05x, EV +62%; edge H, ACTIVE' },
  { sym:'PRX.AS',co:'Prosus NV (Delivery Hero divest)', cluster:'Idiosyncratic',   label:'forced-seller',    ctx:'forced-seller recovery (Prosus clearing a Delivery Hero overhang); UNDATED; live EUR 39.30 vs target EUR 46.21 / floor EUR 37.37; recovery R:R 3.58; edge M, WATCH/staging' },
  { sym:'BLCO', co:'Bausch + Lomb',                     cluster:'Idiosyncratic',   label:'forced-seller',    ctx:'forced-seller SoP (BHC ~88% ownership overhang clears); UNDATED; live $15.08 vs target $26.97 / floor $11.80; SoP R:R 3.62; edge H, WATCH/staging' },
  { sym:'LBTYK',co:'Liberty Global',                    cluster:'Idiosyncratic',   label:'spin/index',       ctx:'spinoff + index-flow SoP; date 2027-06-30 (378d, far); live $12.01 vs target $18.00 / floor $9.50; SoP R:R 2.39; edge M, WATCH/staging' },
  { sym:'ZYME', co:'Zymeworks',                         cluster:'FDA/biotech',     label:'PDUFA',            ctx:'bio binary, FDA approval decision; HARD DATE 2026-08-25 (69d); live $22.88 vs target $31.00 / floor $19.00; win_prob 0.88, payoff 2.09x, EV +29%; edge H, WATCH/staging' },
  { sym:'CELC', co:'Celcuity',                          cluster:'FDA/biotech',     label:'FDA readout',      ctx:'bio binary, FDA clinical readout (Ph3 topline); HARD DATE 2026-07-17 (30d); live $88.55 vs target $153 / floor $60; win_prob 0.85, payoff 2.26x, EV +57%; edge H, WATCH/staging' },
  { sym:'CLVT', co:'Clarivate',                         cluster:'Idiosyncratic',   label:'activist',         ctx:'activist process / board-or-sale; UNDATED; live $2.21 vs target $6.17 / floor $1.42; SoP R:R 5.02; edge H, WATCH/staging' },
  { sym:'KDP',  co:'Keurig Dr Pepper',                  cluster:'Idiosyncratic',   label:'spin/index',       ctx:'spinoff + index-flow SoP; UNDATED; live $31.71 vs target $37.70 / floor $28.50; SoP R:R 1.87; edge M, WATCH/staging' },
  { sym:'VIR',  co:'Vir Biotechnology',                 cluster:'FDA/biotech',     label:'FDA readout',      ctx:'bio binary, FDA clinical readout; UNDATED; live $8.61 vs target $20.00 / floor $5.50; win_prob 0.58, payoff 3.66x, EV +62%; edge H, WATCH/staging' },
  { sym:'KBR',  co:'KBR Inc',                           cluster:'Idiosyncratic',   label:'spin/index',       ctx:'spinoff (Govt Solutions / Mission Tech) SoP; UNDATED; live $35.84 vs target $53.00 / floor $33.20; SoP R:R 6.54; edge M, WATCH/staging' },
]

const SYMS = NAMES.map(n => n.sym)
function chunk(a, n) { const o = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o }

function debatePrompt(n) {
  const sym = n.sym
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' (' + n.co + ') as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital. Judge ' + sym + ' as ' + THEME + '\n' +
    'CATALYST DOSSIER (from our Catalyst-Watch board): ' + n.ctx + '. Super-cluster: ' + n.cluster + '.\n' +
    'MANDATORY web verification: use WebSearch + WebFetch to confirm the CURRENT, LIVE status of the load-bearing catalyst as of today — the exact PDUFA / decision date, the trial readout window, the merger close timeline + regulatory step, the spin record/effective date, or the forced-seller / activist process. Confirm the live price + a realistic target and the downside floor (deal-break price / cash / recovery / bear value). If the catalyst has ALREADY fired, slipped indefinitely, or the spread has closed, SAY SO — it changes everything. Never fabricate a date or status.\n' +
    '1. INTERROGATOR: read ' + DIR + '/interrogator_system.txt for the forensic DISCIPLINE, but apply it to the EVENT: is the catalyst REAL, DATED, and BINDING; how credible is the sponsor / acquirer / management on hitting it; what is the VERIFIED downside floor (what actually backstops the price if the event fails); red flags (going-concern, ATM / dilution, covenant, financing contingency, CVR games, second-request). Produce the dossier + a final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <STRENGTHENING|STABLE|DETERIORATING|PIVOTING> | MOAT: <WIDE|NARROW|ERODING|NONE> | MOAT_TREND: <WIDENING|STABLE|ERODING> | SECULAR_THREAT: <terminal|material|manageable|none>" line (moat/secular are mostly N/A — score the EVENT credibility). Write it to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '2. ARCHITECT: read ' + DIR + '/architect_system.txt; bull_thesis = the catalyst resolves favorably (to target); bear_thesis = it fails (to floor). sop_bull = the event-win value + how derived; sop_bear = the verified downside floor + how derived. Base-case SoP = probability-weighted(target, floor) using the verified odds.\n' +
    '3. CATALYST VERIFICATION (web, MANDATORY): catalyst_status = FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE, with dated evidence. This is the single most load-bearing output.\n' +
    '4. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE to a base-case sop_fair_value (+ breakdown) and risk_reward (upside-to-target vs downside-to-floor). Produce verdict (A/B/C) and conviction (int 1-5) on the EVENT ASYMMETRY: conviction 5 / verdict A = a LIVE PENDING_HARD dated catalyst inside the window, live price well below the event-resolved target, with a verified real downside floor (asymmetric, defined-risk) — give these the 5 they earn, do NOT reflexively cap. conviction 3 = real but undated/soft or thin floor; conviction <=2 = FIRED / trading-through-terms / unverifiable / the floor breaks. THEN value_conviction (int 1-5) = the margin of safety to the VERIFIED DOWNSIDE FLOOR (NOT a franchise moat). Emit moat / moat_trend / secular_threat (mostly NONE / manageable here) and secular_theme "" unless one truly applies. Plus consensus_delta, valley_of_death, positioning_washout, forcing_function (THE hard date / trigger), moderator_conclusion, and catalyst_summary (one line: the event + date + the asymmetry).\n' +
    '5. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with EXACTLY these keys: symbol(="' + sym + '"), company(="' + n.co + '"), cluster(="' + n.cluster + '"), driver(="' + n.label + '"), bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, catalyst_summary, dated_milestone, forcing_function, verdict, conviction(int 1-5), value_conviction(int 1-5), moat, moat_trend, secular_threat, secular_theme, consensus_delta, valley_of_death, positioning_washout, moderator_conclusion, interrogator_dossier(the FULL dossier text), interrogator_score(int 1-5), trajectory, live_price(number or null), target_px(number or null), downside_floor(number or null), source(="opus_catalyst_online"), transcript_source(="web").\n' +
    'Reply exactly: DONE'
}

function skepticPrompt(n) {
  const sym = n.sym
  return 'You are the SPECULAIR SKEPTIC (Claude Opus 4.8) running an ADVERSARIAL kill-check on ' + sym + ' (' + n.co + '), an EVENT-DRIVEN special situation (' + n.label + ', ' + n.cluster + '). Default verdict REFUTED unless you can INDEPENDENTLY confirm the load-bearing facts against a PRIMARY source (SEC / 8-K, company IR, FDA / regulator pages, the merger proxy / agreement, an exchange notice). You see ONLY the bear side.\n' +
    '1. Read ' + RES + '/' + sym + '.json.\n' +
    '2. ATTACK VECTORS — WebSearch / WebFetch to verify: (a) IS THE CATALYST GENUINELY LIVE + DATED + BINDING, or has it already FIRED / slipped / been priced (the spread already closed)? Confirm the exact date from a primary source. (b) IS THE TARGET REAL (the deal terms / the drug TAM / the SoP) or fantasy? (c) IS THE DOWNSIDE FLOOR REAL — what actually backstops the price if the event fails (deal-break price, cash / recovery value), or does the floor break (going-concern, dilution / ATM, financing contingency, CVR)? (d) HIDDEN DISQUALIFIER — single-binary with no real floor, trading through terms, regulatory second-request, an FDA AdCom / CRL risk the bull ignores.\n' +
    '3. Verdict: CONFIRMED (the asymmetry survives) | CONFIRMED_WITH_CORRECTIONS (survives but a load-bearing fact / date needs fixing — state it) | REFUTED (the catalyst is fired / soft, the floor breaks, or the spread is gone). Also conviction_cap (int 0-100): the MAX Director conviction this setup deserves given ONLY what you verified.\n' +
    '4. Write (Write tool) VALID JSON to ' + SKEP + '/' + sym + '.json = {symbol(="' + sym + '"), verdict, kill_fact, corrections, conviction_cap(int 0-100), evidence:[2-4 dated primary-source cites]}. Reply exactly: DONE'
}

phase('Debate')
log('Catalyst-funnel diagnostic: ' + NAMES.length + ' Basket-13 special-sits → full debate → skeptic → director, batched ≤6 (rate-safe)')
let bi = 0
for (const batch of chunk(NAMES, 6)) {
  bi++
  log('  batch ' + bi + ': ' + batch.map(n => n.sym).join(', '))
  await pipeline(
    batch,
    n => agent(debatePrompt(n), { label: 'debate:' + n.sym, phase: 'Debate', agentType: 'general-purpose', model: 'opus', effort: 'high' }),
    (_r, n) => agent(skepticPrompt(n), { label: 'skeptic:' + n.sym, phase: 'Skeptic', agentType: 'general-purpose', model: 'opus', effort: 'high' }),
  )
}

phase('Director')
log('All debates + skeptics in. Running the Catalyst-Director over ' + SYMS.length + ' names (0-100 on the apex bands).')
await agent(
  'You are the SPECULAIR CATALYST DIRECTOR (Claude Opus 4.8, 1M context) assessing ' + SYMS.length + ' EVENT-DRIVEN special situations from the Catalyst-Watch funnel (hard-dated M&A closes, PDUFA / FDA decisions, clinical readouts, spins + index flow, forced-seller supply clears, activist processes). The CRO reconciled each to a base-case SoP + risk/reward + a LIVE catalyst_status; an independent Skeptic kill-checked each.\n' +
  '1. Read CATALYST_WATCH_REGIME.md (repo root) + ' + DIR + '/macro_regime.json. One line: the regime + your risk stance for hard-dated event arbitrage right now.\n' +
  '2. Read each ' + RES + '/{SYM}.json and ' + SKEP + '/{SYM}.json for: ' + SYMS.join(', ') + '.\n' +
  '3. For EACH name assign a CONVICTION 0-100 on the SAME bands the apex book uses: 90-100 = table-pounding, maximal asymmetry, catalyst IMMINENT + huge live-to-target spread + hard floor; 70-89 = high-conviction aggressive entry (live dated catalyst, real spread, defined floor); 50-69 = solid but undated / soft or thinner floor; <50 = watchlist (no live date, thin spread, or shaky floor). HARD-CAP at the Skeptic conviction_cap; a REFUTED verdict forces <50. Be willing to score a genuinely asymmetric, imminent, well-floored setup 80+ — that is the question this run exists to answer; do NOT reflexively suppress it. Also would_seat(bool), posture(enter_now_carry | scale_in | wait_for_date | pass), expected_return_pct(to target from live), binding_reason(the single fact driving the score), catalyst_status, and copy cro_verdict + cro_conviction from the name\'s result file.\n' +
  '4. CORRELATION: the FDA/biotech binaries (BBIO/AQST/ZYME/VRDN/EYPT/CELC/AMLX/VIR) are ONE shared factor (FDA / clinical risk-on-off + biotech beta) — note the cluster and that seating many = one bet; the forced-seller / idiosyncratic names (FIP/BLCO/PRX.AS/CLVT/KBR/KDP/LBTYK) are more independent. Say which are the purest standalone asymmetries.\n' +
  '5. THE HEADLINE (this run exists to answer it): across the funnel, how many earned verdict A (from the CRO), conviction 5 (CRO 1-5), and a Director score >=80 — the bands the priced-quality funnels have NEVER produced in 407+ names? Name them, or state plainly that none did and why.\n' +
  '6. Write (Write tool) VALID JSON to ' + DIR + '/_catalyst_director.json = {regime, risk_stance, assessments:[{symbol, cluster, conviction, would_seat, posture, expected_return_pct, catalyst_status, binding_reason, cro_verdict, cro_conviction}], ranking:[syms best-to-worst], n_dir80, n_verdict_a, n_conv5, correlation_memo, memo}. Reply exactly: DONE',
  { label: 'catalyst-director', phase: 'Director', model: 'opus', effort: 'xhigh' })

log('Catalyst-funnel diagnostic complete.')
return 'DONE'
