export const meta = {
  name: 'scaleout-45-repair',
  description: 'Repair pass for the scale-out 45-name run: re-run the 24 debates + 15 skeptics that died to a server-side rate-limit burst, in small rate-safe batches, then re-run the Scale-Director over the full set',
  phases: [
    { title: 'Debate (repair)', detail: '24 missing debates + skeptics, batches of 6', model: 'opus' },
    { title: 'Skeptic (repair)', detail: '15 missing skeptics for already-debated names', model: 'opus' },
    { title: 'Scale Director', detail: 'cross-basket assignment over all 45', model: 'opus' },
  ],
}

const DIR = 'backend/_opus_debate'
const RES = DIR + '/_scaleout_results'
const SKEP = DIR + '/_scaleout_skeptic'

const THEME = "the AI scale-out / scale-up compute build-out — the PHYSICAL bottlenecks every hyperscaler + sovereign-AI capex dollar must pay: optical / silicon-photonics interconnect (CPO), electrical distribution / grid / HV transformers / switchgear, data-center cooling + build-out contractors, 800V-DC power semis (SiC / GaN), power generation / nuclear / SMR / fuel, and HBM memory. Evaluate this name's role, demand-durability, competitive position, and how much of the AI-capex optionality is ALREADY priced in — WITHIN that thesis."

const BRIEF = "Read CATALYST_WATCH_REGIME.md (repo root) for the current market regime and APPLY it: reward hard-dated catalysts (design wins, hyperscaler awards, capacity ramps, backlog prints, NRC/PPA milestones) inside the favorable window; PENALIZE already-fired / already-ran / out-of-window catalysts and rate-rescue theses; prize resolution-driver independence (be wary of a name whose thesis hinges on the same single shared macro factor — AI-capex durability — as the rest of the basket). Let this MOVE the conviction / verdict."

const NAMES = [
  { sym:'COHR', co:'Coherent',                  basket:'A', label:'OPTICAL',   ctx:'NVDA ~$2B stake; silicon photonics + transceivers; ran on the March bet' },
  { sym:'LITE', co:'Lumentum',                  basket:'A', label:'OPTICAL',   ctx:'NVDA ~$2B stake; EML / laser source; ran on the March bet' },
  { sym:'CRDO', co:'Credo Technology',          basket:'A', label:'OPTICAL',   ctx:'AEC into 1.6T optical DSP; bought DustPhotonics; ran' },
  { sym:'ALAB', co:'Astera Labs',               basket:'A', label:'OPTICAL',   ctx:'scale-up fabric; bought aiXscale Photonics; ran' },
  { sym:'MRVL', co:'Marvell Technology',        basket:'A', label:'OPTICAL',   ctx:'custom XPU + 3D silicon photonics; ran' },
  { sym:'FN',   co:'Fabrinet',                  basket:'A', label:'OPTICAL',   ctx:'optical contract mfg — picks-and-shovels; less hyped' },
  { sym:'GLW',  co:'Corning',                   basket:'A', label:'OPTICAL',   ctx:'optical fiber + glass substrate; broad but levered' },
  { sym:'AAOI', co:'Applied Optoelectronics',   basket:'A', label:'OPTICAL',   ctx:'transceivers; small, volatile' },
  { sym:'MTSI', co:'MACOM Technology',          basket:'A', label:'OPTICAL',   ctx:'analog + photonics for optical; mid' },
  { sym:'SMTC', co:'Semtech',                   basket:'A', label:'OPTICAL',   ctx:'AEC / connectivity (Tri-Edge); mid' },
  { sym:'POET', co:'POET Technologies',         basket:'A', label:'OPTICAL',   ctx:'silicon-photonics interposer; micro-cap, speculative' },

  { sym:'ETN',  co:'Eaton',                     basket:'B', label:'GRID',      ctx:'full electrical stack; ran hard' },
  { sym:'GEV',  co:'GE Vernova',                basket:'B', label:'GRID',      ctx:'turbines + grid + 800V DC, full-stack; ran hard' },
  { sym:'POWL', co:'Powell Industries',         basket:'B', label:'GRID',      ctx:'MV switchgear, big DC backlog; switchgear normalizing' },
  { sym:'ABB',  co:'ABB Ltd (NYSE ADR)',        basket:'B', label:'GRID',      ctx:'switchgear + NVDA 800V collab; clean US listing' },
  { sym:'VRT',  co:'Vertiv Holdings',           basket:'B', label:'GRID',      ctx:'power + thermal; ran enormously' },
  { sym:'NVT',  co:'nVent Electric',            basket:'B', label:'GRID',      ctx:'connection / protection, liquid cooling; ran' },
  { sym:'HUBB', co:'Hubbell',                   basket:'B', label:'GRID',      ctx:'electrical equipment' },
  { sym:'ATKR', co:'Atkore',                    basket:'B', label:'GRID',      ctx:'conduit / cable; cyclical' },
  { sym:'PWR',  co:'Quanta Services',           basket:'B', label:'GRID',      ctx:'grid construction / EPC; ran' },
  { sym:'MYRG', co:'MYR Group',                 basket:'B', label:'GRID',      ctx:'electrical construction' },

  { sym:'MOD',  co:'Modine Manufacturing',      basket:'C', label:'THERMAL',   ctx:'data-center thermal' },
  { sym:'FIX',  co:'Comfort Systems USA',       basket:'C', label:'THERMAL',   ctx:'mechanical / electrical contractor' },
  { sym:'EME',  co:'EMCOR Group',               basket:'C', label:'THERMAL',   ctx:'electrical / mechanical contractor' },
  { sym:'CARR', co:'Carrier Global',            basket:'C', label:'THERMAL',   ctx:'cooling / HVAC at scale' },
  { sym:'JCI',  co:'Johnson Controls',          basket:'C', label:'THERMAL',   ctx:'building systems' },

  { sym:'MPWR', co:'Monolithic Power Systems',  basket:'D', label:'PWR-SEMI',  ctx:'data-center power management' },
  { sym:'ALGM', co:'Allegro MicroSystems',      basket:'D', label:'PWR-SEMI',  ctx:'TMR sensing + 800V power ICs' },
  { sym:'POWI', co:'Power Integrations',        basket:'D', label:'PWR-SEMI',  ctx:'high-voltage power conversion' },
  { sym:'NVTS', co:'Navitas Semiconductor',     basket:'D', label:'PWR-SEMI',  ctx:'GaN — small, volatile' },
  { sym:'ON',   co:'onsemi',                    basket:'D', label:'PWR-SEMI',  ctx:'SiC' },
  { sym:'VICR', co:'Vicor',                     basket:'D', label:'PWR-SEMI',  ctx:'power modules, 800V-relevant' },
  { sym:'IFNNY',co:'Infineon Technologies (ADR)',basket:'D',label:'PWR-SEMI',  ctx:'SiC leader, broad' },

  { sym:'BE',   co:'Bloom Energy',              basket:'E', label:'POWER-GEN', ctx:'fuel cells; ran 10x' },
  { sym:'OKLO', co:'Oklo',                      basket:'E', label:'POWER-GEN', ctx:'SMR, Aurora-INL mid-2026; down ~67% from high' },
  { sym:'XE',   co:'X-Energy',                  basket:'E', label:'POWER-GEN', ctx:'SMR, Amazon anchor; post-IPO, lockup Oct — VERIFY the current ticker/listing status online before debating' },
  { sym:'SMR',  co:'NuScale Power',             basket:'E', label:'POWER-GEN', ctx:'only NRC-certified SMR; washed out' },
  { sym:'BWXT', co:'BWX Technologies',          basket:'E', label:'POWER-GEN', ctx:'HALEU + Navy, picks-and-shovels; quality compounder' },
  { sym:'NNE',  co:'Nano Nuclear Energy',       basket:'E', label:'POWER-GEN', ctx:'microreactor; pre-revenue, speculative' },
  { sym:'LEU',  co:'Centrus Energy',            basket:'E', label:'POWER-GEN', ctx:'HALEU enrichment' },
  { sym:'CCJ',  co:'Cameco',                    basket:'E', label:'POWER-GEN', ctx:'uranium; ran' },
  { sym:'VST',  co:'Vistra',                    basket:'E', label:'POWER-GEN', ctx:'IPP; ran' },
  { sym:'CEG',  co:'Constellation Energy',      basket:'E', label:'POWER-GEN', ctx:'nuclear IPP; ran' },
  { sym:'TLN',  co:'Talen Energy',              basket:'E', label:'POWER-GEN', ctx:'nuclear IPP (Amazon / Susquehanna); ran' },

  { sym:'MU',   co:'Micron Technology',         basket:'F', label:'MEMORY',    ctx:'the original supply-shock; HBM mid-cycle now' },
]

const byId = Object.fromEntries(NAMES.map(n => [n.sym, n]))
const SYMS = NAMES.map(n => n.sym)

// Gaps from the first run (rate-limit burst). SET_A = no debate result (need debate+skeptic).
// SET_B = debate present but skeptic died (need skeptic only).
const SET_A = ['HUBB','MYRG','EME','CARR','JCI','MPWR','ALGM','POWI','NVTS','ON','VICR','IFNNY','BE','OKLO','XE','SMR','BWXT','NNE','LEU','CCJ','VST','CEG','TLN','MU']
const SET_B = ['LITE','POET','MTSI','ALAB','ETN','ABB','FN','GEV','AAOI','GLW','MRVL','CRDO','POWL','COHR','VRT']

function chunk(a, n) { const o = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o }

function debatePrompt(n) {
  const sym = n.sym
  return 'You run the COMPLETE multi-agent debate for ' + sym + ' (' + n.co + ') as Claude Opus 4.8 — Interrogator, Architect, then CRO/Moderator — allocating REAL capital, evaluating the name WITHIN ' + THEME + '\n' +
    'CONTEXT: ' + sym + ' sits in scale-out Basket ' + n.basket + ' (' + n.label + '). Why in universe: ' + n.ctx + '.\n' +
    'NO data is bundled. Use WebSearch + WebFetch to get ' + sym + "'s MOST RECENT earnings-call transcript (or, if none, the latest quarterly results / earnings release / 10-Q/10-K / investor presentation) AND the LATEST fundamentals (revenue + growth, gross/operating/net margins + trend, ROIC, FCF + margin, net debt / leverage + interest coverage, segment & geographic mix, backlog / book-to-bill where relevant, buybacks / dividend, current price + market cap). If a fact is genuinely unfindable, say so and reason from fundamentals — NEVER fabricate. If " + sym + " is not a currently-traded US-listed equity (a just-IPO'd / not-yet-public / de-SPAC name), WebSearch its current listing status + correct ticker and state it plainly in listing_note.\n" +
    '1. INTERROGATOR: read ' + DIR + '/interrogator_system.txt; produce the full forensic dossier (8 sections + the final "CREDIBILITY_SCORE: <1-5> | TRAJECTORY: <STRENGTHENING|STABLE|DETERIORATING|PIVOTING> | MOAT: <WIDE|NARROW|ERODING|NONE> | MOAT_TREND: <WIDENING|STABLE|ERODING> | SECULAR_THREAT: <terminal|material|manageable|none>" line). Write it (Write tool) to ' + DIR + '/dossiers/' + sym + '.md.\n' +
    '2. PEER COMPS: identify ' + sym + "'s TRUE peers WITHIN its scale-out layer and where it ranks on VALUATION / GROWTH / MARGINS / RETURNS / AI-capex exposure. Verify each peer's CURRENT live multiple online (no stale-from-memory multiples). Write a peer_comps_note.\n" +
    '3. ARCHITECT: read ' + DIR + '/architect_system.txt; produce bull_thesis and bear_thesis AND a Sum-of-Parts / intrinsic valuation (value by parts where segments warrant, else whole-company intrinsic via the right metric / peer multiple; special-situation overlays where relevant — net cash, buyback, backlog conversion, pending deals VERIFIED). Output sop_bull and sop_bear, each a per-share value + the parts breakdown.\n' +
    '4. CATALYST VERIFICATION (web, MANDATORY): identify the load-bearing catalyst(s) (a hyperscaler design win/award, a capacity ramp, a backlog/book-to-bill inflection, a PPA, an NRC/SMR step) and WebSearch their CURRENT status as of today. catalyst_status = FIRED | ARB | PENDING_HARD | SOFT_EXTENDED | UNVERIFIABLE, with dated evidence.\n' +
    '5. CRO/MODERATOR: read ' + DIR + '/moderator_system.txt; ' + BRIEF + ' RECONCILE sop_bull/sop_bear into a base-case sop_fair_value (+ sop_breakdown) and risk_reward (downside-to-break vs upside-to-fair); DOWN-RATE conviction for FIRED / already-ran / SOFT catalysts; sanity-check the multiple vs the peer comps; explicitly weigh how much of the AI-scale-out optionality is ALREADY priced in (many of these names ran hard). Produce verdict (A/B/C), conviction (int 1-5), consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion. THEN value_conviction (int 1-5): the value case as if NO AI-capex / catalyst overlay existed (valuation vs the SoP fair value + forensic quality ONLY). Emit moat (WIDE|NARROW|ERODING|NONE — a high-but-FALLING ROIC/margin is ERODING, not WIDE), moat_trend (WIDENING|STABLE|ERODING), secular_threat (terminal|material|manageable|none) and ONE secular_theme id from ' + DIR + '/secular_themes.json (or ""). Also role_in_scaleout: one sentence on this name\'s specific role/criticality in the build-out + how durable that demand is.\n' +
    '6. Write (Write tool) VALID, escaped JSON to ' + RES + '/' + sym + '.json with EXACTLY these keys: symbol(="' + sym + '"), company(="' + n.co + '"), basket(="' + n.basket + '"), basket_label(="' + n.label + '"), sector, bull_thesis, bear_thesis, sop_bull, sop_bear, sop_fair_value, sop_breakdown, risk_reward, catalyst_status, peer_comps_note, role_in_scaleout, verdict, conviction(int 1-5), value_conviction(int 1-5), moat, moat_trend, secular_threat, secular_theme, consensus_delta, valley_of_death, positioning_washout, forcing_function, moderator_conclusion, interrogator_dossier(the FULL dossier text you wrote to the .md), interrogator_score(int 1-5), trajectory, current_price(number or null), market_cap(string or null), listing_note(=""  unless not-normally-listed), source(="opus_scaleout_online"), transcript_source(="web").\n' +
    'Reply exactly: DONE'
}

function skepticPrompt(n) {
  const sym = n.sym
  return 'You are the SPECULAIR SKEPTIC (Claude Opus 4.8) running an ADVERSARIAL kill-check on ' + sym + ' (' + n.co + ') — a scale-out Basket ' + n.basket + ' (' + n.label + ') name. Your job is to KILL the thesis; default verdict REFUTED unless you can INDEPENDENTLY confirm the load-bearing facts against a PRIMARY source (SEC filings, the company IR site, an exchange / regulator page, a customer / hyperscaler announcement). You see ONLY the bear side — do NOT reconstruct the bull case.\n' +
    '1. Read ' + RES + '/' + sym + '.json (the debate result).\n' +
    '2. ATTACK VECTORS — WebSearch / WebFetch to verify: (a) STALE-ANCHOR — is sop_fair_value built on pre-event / pre-guidance financials? (b) NUMBER TRUTH — do the load-bearing figures (revenue run-rate, backlog / book-to-bill, the named design-win / award, net debt, share count, capacity / MW, NRC / PPA milestone, cash runway) verify against a primary source? (c) THESIS WEAKNESS — is the AI-scale-out demand already PRICED IN (the name ran hard), single-customer-concentrated (one hyperscaler), or exposed to a capex-air-pocket / digestion risk; is the moat real or a commoditizing component? (d) HIDDEN DISQUALIFIER — dilution / ATM, de-SPAC or lockup expiry, customer concentration, a soft / serially-extended catalyst dressed as hard, pre-revenue burn.\n' +
    '3. Verdict: CONFIRMED (bear attacked, thesis survives) | CONFIRMED_WITH_CORRECTIONS (survives but a load-bearing claim needs fixing — state it) | REFUTED (a kill_fact breaks it). Also scale_cap: the MAX scale-out conviction (int 0-100) you would allow given ONLY the facts you verified.\n' +
    '4. Write (Write tool) VALID JSON to ' + SKEP + '/' + sym + '.json = {symbol(="' + sym + '"), verdict, kill_fact, corrections, scale_cap(int 0-100), evidence:[2-4 dated primary-source cites]}. Reply exactly: DONE'
}

phase('Debate (repair)')
log('Repairing ' + SET_A.length + ' missing debates (+ skeptics) in batches of 6 to stay under the capacity throttle...')
let bi = 0
for (const batch of chunk(SET_A, 6)) {
  bi++
  log('  debate batch ' + bi + ': ' + batch.join(', '))
  await pipeline(
    batch.map(s => byId[s]),
    n => agent(debatePrompt(n), { label: 'debate:' + n.sym, phase: 'Debate (repair)', agentType: 'general-purpose', model: 'opus', effort: 'high' }),
    (_r, n) => agent(skepticPrompt(n), { label: 'skeptic:' + n.sym, phase: 'Skeptic (repair)', agentType: 'general-purpose', model: 'opus', effort: 'high' }),
  )
}

phase('Skeptic (repair)')
log('Running ' + SET_B.length + ' missing skeptics for already-debated names in batches of 8...')
bi = 0
for (const batch of chunk(SET_B, 8)) {
  bi++
  log('  skeptic batch ' + bi + ': ' + batch.join(', '))
  await parallel(batch.map(s => () => agent(skepticPrompt(byId[s]), { label: 'skeptic:' + s, phase: 'Skeptic (repair)', agentType: 'general-purpose', model: 'opus', effort: 'high' })))
}

phase('Scale Director')
log('All 45 debates + skeptics present. Running the Scale-Director over the full set.')
await agent(
  'You are the SPECULAIR SCALE-OUT DIRECTOR (Claude Opus 4.8, 1M context). You are assessing ' + SYMS.length + ' names that together make up the AI scale-out / scale-up compute build-out, organized into six LAYERS (baskets): A OPTICAL (silicon photonics / CPO / transceivers), B GRID (electrical distribution / HV transformers / switchgear), C THERMAL (data-center cooling + build-out contractors), D PWR-SEMI (800V-DC SiC/GaN power conversion), E POWER-GEN (IPP / nuclear / SMR / fuel), F MEMORY (HBM). The CRO already reconciled each name to a SoP fair value + risk/reward + a LIVE catalyst_status; an independent Skeptic kill-checked each.\n' +
  '1. Read CATALYST_WATCH_REGIME.md (repo root) IN FULL + ' + DIR + '/macro_regime.json (live macro classifier). State the regime + your risk stance for THIS theme in one line — the whole basket is ONE leveraged bet on AI-capex durability; say how you weight that.\n' +
  '2. Read each ' + RES + '/{SYM}.json and ' + SKEP + '/{SYM}.json for: ' + SYMS.join(', ') + '.\n' +
  '3. For EACH name assign a SCALE rating WITHIN the build-out: scale_tier (CORE = thesis-pure toll every build must pay, durable demand, would-seat; LEVER = strong levered exposure but more cyclical / second-order / already-ran, sized smaller; TACTICAL = real exposure but speculative / micro-cap / pre-revenue / valuation-stretched, wait-for-weakness; PASS = weak fit / fired / over-owned / structurally-eroding / Skeptic-refuted), scale_conviction (int 0-100; HARD-CAP at the Skeptic scale_cap, and a REFUTED verdict forces TACTICAL or PASS), role (one line on the name\'s specific criticality), scale_rationale, demand_durability (how tightly the revenue is bolted to AI-capex vs broad-cyclical), valuation_posture (cheap | fair | rich vs the build-out optionality already priced in), would_seat (bool, if building a concentrated scale-out book today), posture (enter_now_carry | scale_in | wait_for_weakness | wheel-it | pass), expected_return_pct (number, to SoP fair value from the current price; can be negative).\n' +
  '4. CORRELATION / CLUSTERING (critical — this is ONE bet in six costumes): call out the intra-layer clusters that share the SAME resolution driver (e.g. COHR + LITE + CRDO + FN all NVDA-optical-supply; VST + CEG + TLN + CCJ all nuclear-IPP / uranium; ETN + VRT + GEV + PWR all grid-capex; MOD + FIX + EME thermal-contractors; the SiC names ON + IFNNY) and the single shared macro factor (AI-capex durability / a hyperscaler digestion air-pocket) that hits ALL of them at once. Say which 1-2 names per layer are the PUREST / least-redundant expression, and which are duplicative.\n' +
  '5. Rank within EACH basket best-to-worst for the build-out, then give an overall top_picks list (which you would actually SEAT today vs hold-for-weakness vs avoid). Apply rotation discipline — is the asymmetry there NOW given how much has already run.\n' +
  '6. Write (Write tool) VALID JSON to ' + DIR + '/_scaleout_director.json = {regime, risk_stance, thesis_overview, assessments:[{symbol, basket, scale_tier, scale_conviction, role, scale_rationale, demand_durability, valuation_posture, would_seat, posture, expected_return_pct}], basket_ranking:{A:[syms best-to-worst],B:[...],C:[...],D:[...],E:[...],F:[...]}, correlation_memo, top_picks:[syms], memo}. Reply exactly: DONE',
  { label: 'scale-director', phase: 'Scale Director', model: 'opus', effort: 'xhigh' })

log('Repair + director complete.')
return 'DONE'
