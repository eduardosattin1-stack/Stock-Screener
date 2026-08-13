export const meta = {
  name: 'fdt-chain-map',
  description: 'Sonnet chain-mapping over the gated fdt candidates (Radar-style, chunked; physical-anchor enforced)',
  phases: [{ title: 'ChainMap', model: 'sonnet' }],
}
const N = 31
phase('ChainMap')
await parallel(Array.from({ length: N }, (_, i) => () => agent(
  'You are the FDT CHAIN RADAR (chain-mapping + physical-anchor pass). Read backend/_opus_debate/fdt_chains.json (the versioned chain taxonomy: ids, theses, value-chain layers, notes) and backend/_opus_debate/fdt/_map_chunk_' + i + '.json (your candidate chunk: symbol/name/sector/industry/mcap + lane + Stage-B gates). This is the FUTURE DISRUPTIVE TECH book: equipment_services, utility and developer names belong HERE; a producer or royalty_streamer mapped into an FDT chain is a split-rule error and is DROPPED at merge (mining owns those) - map the true business_model anyway, never bend the label to keep a name. For EACH symbol decide, skeptically:\n' +
  '- physical_anchor: ONE line naming the PHYSICAL thing this company makes, moves, powers, or directly instruments for its chain (quantum hardware counts; a payments network never does). If you CANNOT name one, set chain_fit_confidence=low REGARDLESS of the industry or keyword hints (the anti-Visa rule; it binds hardest on the broad quantum and robotics filters).\n' +
  '- chains: array of taxonomy ids this company GENUINELY rides (max 2; a name may legitimately carry two chains WITHIN this book; [] if none - an industry filter catches many non-chain names).\n' +
  '- business_model: exactly one of producer | royalty_streamer | developer | equipment_services | utility (royalty_streamer auto-passes the cash gates; a pre-FCF developer belongs in lane B, never lane A; equipment_services = the toll-taker selling into the chain; utility = an operator selling power under contract).\n' +
  '- commodity_revenue_share: a number 0-1 = the fraction of revenue exposed to the chain commodity (1.0 for a pure producer; a diversified miner gets your best estimate and NEVER a default of 1.0; an equipment/services or utility name is low). This feeds a deterministic torque formula AND the cross-book dedup rule, so estimate it honestly.\n' +
  '- value_chain_position: one line - which value-chain layer it occupies and what it sells.\n' +
  '- true_competitors: 4-8 REAL competitor tickers (business-model comparables, in-universe or NOT - include foreign listings and private-adjacent public proxies).\n' +
  '- chain_fit_confidence: high | medium | low (low = the FMP industry filter caught a name that is NOT really in this chain - a chemical company in the rare-earth screen, a generic hardware or software name in quantum, a non-chain royalty company, a legacy industrial). LOW-confidence names are DROPPED at merge, printed, never silent.\n' +
  'Write (Write tool) VALID JSON to backend/_opus_debate/fdt/_chainmap_' + i + '.json as {"<SYM>": {physical_anchor, chains, business_model, commodity_revenue_share, value_chain_position, true_competitors, chain_fit_confidence}, ...} covering EVERY symbol in your chunk. Reply exactly: DONE',
  { label: 'fdtmap:' + i, phase: 'ChainMap', model: 'sonnet' })))
return 'DONE'
