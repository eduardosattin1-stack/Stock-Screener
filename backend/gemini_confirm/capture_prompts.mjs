// Capture the exact prompts a Speculair workflow would send, for ONE symbol, without running agents.
// usage: node capture_prompts.mjs <workflow.js> <SYM> <out.json>
import fs from 'node:fs'

const [, , wfPath, SYM, outPath, mode] = process.argv
const ONLINE = mode === '--online'          // no FMP transcript: the debate runs the online variant
let src = fs.readFileSync(wfPath, 'utf8')
src = src.replace(/^export const meta[\s\S]*?^}\s*$/m, '')
const one = JSON.stringify([SYM])
const set = (name, val) => { src = src.replace(new RegExp('^const ' + name + ' = \\[.*$', 'm'), 'const ' + name + ' = ' + val) }
set('SYMS', ONLINE ? '[]' : one)
set('ONLINE_SYMS', ONLINE ? one : '[]')
set('DELTA_SYMS', one)
set('SKEPTIC_SYMS', one)
set('COVERAGE_SYMS', '[]')
set('RECHECK_SYMS', '[]')
src = src.replace(/^const N_RADAR = \d+/m, 'const N_RADAR = 0')

// BLINDNESS (2026-11-19): the skeptic prompt embeds PRIOR_SEATS (every name we hold) and the lane/hint
// maps for every Tier-U name. A prompt exported for ONE symbol must say nothing about any other name,
// or the second model learns which names we hold before it debates them. Keep only this symbol's entry;
// a line that cannot be parsed stops the capture rather than passing through unfiltered.
const keepOnly = (name) => {
  src = src.replace(new RegExp('^const ' + name + ' = (.*)$', 'm'), (whole, rhs) => {
    let v
    for (const body of [rhs, rhs.replace(/\s*\/\/[^"]*$/, '')]) {
      try { v = JSON.parse(body.trim()); break } catch { /* try the next form */ }
    }
    if (v === undefined) throw new Error('capture_prompts: cannot parse ' + name + ' - refusing to export it unfiltered')
    const out = Array.isArray(v) ? v.filter(s => s === SYM) : Object.fromEntries(Object.entries(v).filter(([k]) => k === SYM))
    return 'const ' + name + ' = ' + JSON.stringify(out)
  })
}
for (const name of ['PRIOR_SEATS', 'SKEPTIC_LANES', 'SKEPTIC_HINTS', 'RECHECK_INFO']) keepOnly(name)

const captured = []
const agent = async (prompt, opts = {}) => {
  captured.push({ label: opts.label || '', model: opts.model || '', phase: opts.phase || '', prompt: String(prompt) })
  return opts.label === 'skeptic-apply' ? 'REVISE_NEEDED=[]' : 'DONE'
}
const parallel = async (fns) => Promise.all(fns.map(f => f()))
const pipeline = async (items, ...stages) => items
const phase = () => {}
const log = () => {}
const args = undefined

const run = new Function('agent', 'parallel', 'pipeline', 'phase', 'log', 'args',
  'return (async () => {\n' + src + '\n})()')
await run(agent, parallel, pipeline, phase, log, args)
fs.writeFileSync(outPath, JSON.stringify(captured, null, 1))
console.log(captured.map(c => `${c.label} [${c.model}] ${c.prompt.length} chars`).join('\n'))
