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
