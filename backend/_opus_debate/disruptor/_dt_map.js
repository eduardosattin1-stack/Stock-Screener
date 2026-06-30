export const meta = {
  name: 'disruptor-theme-map',
  description: 'Sonnet theme-mapping over the gated disruptor candidates (Radar-style, chunked)',
  phases: [{ title: 'ThemeMap', model: 'sonnet' }],
}
const N = 8
phase('ThemeMap')
await parallel(Array.from({ length: N }, (_, i) => () => agent(
  'You are the DISRUPTOR THEME RADAR (theme-mapping + true-competitor pass). Read backend/_opus_debate/disruptor_themes.json (the versioned theme taxonomy: ids, theses, value-chain layers, notes) and backend/_opus_debate/disruptor/_map_chunk_' + i + '.json (your candidate chunk: symbol/name/sector/industry/mcap + gates incl. revenue growth and FCF). For EACH symbol decide, skeptically:\n' +
  '- themes: array of taxonomy ids this company GENUINELY rides (max 2; [] if none — an industry filter catches many non-disruptors).\n' +
  '- value_chain_position: one line — which layer it occupies and what it sells.\n' +
  '- load_bearing_score: int 1-5 — how hard is this company to route around in the theme value chain (5 = chokepoint/toll-taker, 1 = commodity participant).\n' +
  '- s_curve_stage: early_adoption | steep_ramp | broadening | maturing.\n' +
  '- true_competitors: 4-8 REAL competitor tickers (business-model comparables, in-universe or NOT — e.g. include private-adjacent public proxies, foreign listings).\n' +
  '- relative_comps: 2-4 sentences on relative position vs those competitors (growth, margin, multiple posture).\n' +
  '- theme_fit_confidence: high | medium | low (low = the FMP industry filter caught a name that is NOT really a disruption toll-taker — e.g. a legacy prime, a balance-sheet lender, a therapy biotech).\n' +
  'Write (Write tool) VALID JSON to backend/_opus_debate/disruptor/_dt_' + i + '.json as {"<SYM>": {themes, value_chain_position, load_bearing_score, s_curve_stage, true_competitors, relative_comps, theme_fit_confidence}, ...} covering EVERY symbol in your chunk. Reply exactly: DONE',
  { label: 'dtmap:' + i, phase: 'ThemeMap', model: 'sonnet' })))
return 'DONE'
