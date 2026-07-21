"""Trigger-calendar micro-check for the Catalyst Watch sweep board.

The bi-weekly sweep leaves the board static between cycles, so names whose dated
milestone fires mid-cycle sit stale (the CELC/ESPR/NFBK class of error). This
script finds board names whose parsed milestone date is imminent (within
AHEAD_DAYS) or recently past (within PAST_DAYS), generates a tiny verification
workflow (one agent per due name -- NOT a re-sweep), and merges the results back.

Usage:
  python backend/_trigger_watch.py due                 # dry-run: list due names
  python backend/_trigger_watch.py gen                 # write trigger_watch_workflow.js for due names
  python backend/_trigger_watch.py apply <results.json>  # merge verification results into the board + regen TS

Run cadence: daily (cheap -- typically 0-6 agents/day). Generated JS is pure
ASCII (json.dumps ensure_ascii) to satisfy the Workflow permission validator.
"""
import json, re, sys, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_F = os.path.join(HERE, '_sweep_board.json')
OUT_JS = os.path.join(HERE, '_sweep_results', 'trigger_watch_workflow.js')

AHEAD_DAYS = 3
PAST_DAYS = 14

MONTHS = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}


def parse_dates(text, default_year):
    """Extract candidate dates from free-text milestone fields."""
    if not text:
        return []
    out = []
    # ISO: 2026-08-22
    for m in re.finditer(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b', text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            out.append(datetime.date(y, mo, d))
        except ValueError:
            pass
    # "Aug 22, 2026" / "Aug 22 2026" / "August 22" / "22-Aug-2026" / "2-Aug-2026"
    for m in re.finditer(r'\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b', text):
        mon = MONTHS.get(m.group(1)[:3].lower())
        if not mon:
            continue
        d, y = int(m.group(2)), int(m.group(3)) if m.group(3) else default_year
        try:
            out.append(datetime.date(y, mon, d))
        except ValueError:
            pass
    for m in re.finditer(r'\b(\d{1,2})-([A-Za-z]{3})-(20\d{2})\b', text):
        mon = MONTHS.get(m.group(2).lower())
        if not mon:
            continue
        try:
            out.append(datetime.date(int(m.group(3)), mon, int(m.group(1))))
        except ValueError:
            pass
    return out


CONTEXT_RE = re.compile(
    r'(?i)\b(announced|reaffirmed|as of|granted|filed|confirmed|delivered|received|record date|stated|noticed|approved|company-confirmed|dated)\b'
    r'[^;.)|]{0,45}?(20\d{2}-\d{1,2}-\d{1,2}|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*20\d{2})?|\d{1,2}-[A-Za-z]{3}-20\d{2})')


def due_names(board, today):
    """A name is due when (a) a FUTURE parsed date falls within AHEAD_DAYS, or
    (b) the text has NO future date at all and its latest date fell within the
    last PAST_DAYS (possibly-fired). Past dates alongside a future date are
    context, not triggers; announce/as-of dates are stripped before parsing."""
    lo = today - datetime.timedelta(days=PAST_DAYS)
    hi = today + datetime.timedelta(days=AHEAD_DAYS)
    due = []
    for n in board:
        if str(n.get('tier', '')).upper() == 'NONE':
            continue
        text = ' '.join(str(n.get(k) or '') for k in ('dated_milestone', 'catalyst'))
        text = CONTEXT_RE.sub(lambda m: m.group(1), text)
        dates = parse_dates(text, today.year)
        if not dates:
            continue
        future = sorted(d for d in dates if d >= today)
        past = sorted(d for d in dates if d < today)
        if future and future[0] <= hi:
            due.append((n, future[0]))
        elif not future and past and past[-1] >= lo:
            due.append((n, past[-1]))
    return due


JS_HEAD = """export const meta = {
  name: 'trigger-watch',
  description: 'Daily trigger-calendar micro-check: re-verify board names whose dated milestone is imminent or just past',
  phases: [{ title: 'Check' }],
}
const DUE = __DUE__
const SCHEMA = { type:'object', properties:{ symbol:{type:'string'}, still_forward:{type:'boolean'}, fired:{type:'boolean'}, outcome:{type:'string', enum:['FORWARD','FIRED_GOOD','FIRED_BAD','SLIPPED','RESOLVED_OTHER','UNCLEAR']}, new_date:{type:'string'}, note:{type:'string'} }, required:['symbol','still_forward','fired','outcome','note'] }
phase('Check')
const results = (await parallel(DUE.map(n => () =>
  agent(`Today is __TODAY__. TRIGGER CHECK (fast, <=3 lookups via WebSearch/WebFetch + FMP MCP via ToolSearch). Board name ${n.symbol} carries: catalyst "${n.catalyst}" / milestone "${n.milestone}" (score ${n.score}, tier ${n.tier}). The milestone date ${n.trigger} is imminent or just passed. Determine ONLY: did the event FIRE (and favorably or adversely), SLIP (new date?), or is it still FORWARD? Do not re-underwrite the thesis. OUTCOME RULES: FIRED_GOOD/FIRED_BAD are TERMINAL only (deal closed/broke, approval/CRL issued, verdict entered, tender settled); if the situation CONTINUES with a new date -- even after an adverse interim event (TRO granted, extension, second request) -- use SLIPPED with new_date and describe the tilt in the note. Deliverable = a SINGLE StructuredOutput call: {symbol, still_forward, fired, outcome (FORWARD/FIRED_GOOD/FIRED_BAD/SLIPPED/RESOLVED_OTHER/UNCLEAR), new_date (ISO or empty), note (1-2 sentences, cite source+date)}.`,
    { label: `trig:${n.symbol}`, phase: 'Check', schema: SCHEMA })
))).filter(Boolean)
return { checked: results.length, results }
"""


def gen(today):
    board = json.load(open(BOARD_F, encoding='utf-8'))
    due = due_names(board, today)
    if not due:
        print('NO_DUE_NAMES')
        return
    payload = [{'symbol': n['symbol'], 'catalyst': (n.get('catalyst') or '')[:300],
                'milestone': (n.get('dated_milestone') or '')[:300], 'score': n.get('score'),
                'tier': n.get('tier'), 'trigger': t.isoformat()} for n, t in due]
    js = JS_HEAD.replace('__DUE__', json.dumps(payload, ensure_ascii=True, indent=1)) \
                .replace('__TODAY__', today.isoformat())
    open(OUT_JS, 'w', encoding='utf-8', newline='\n').write(js)
    print(f'WROTE {OUT_JS} ({len(payload)} due names: ' + ', '.join(p['symbol'] for p in payload) + ')')


def apply(results_file, today):
    import _sweep_pipe
    board = json.load(open(BOARD_F, encoding='utf-8'))
    res = json.load(open(results_file, encoding='utf-8'))
    results = res.get('results', res) if isinstance(res, dict) else res
    by_sym = {r['symbol']: r for r in results if isinstance(r, dict) and r.get('symbol')}
    changed = []
    for n in board:
        r = by_sym.get(n.get('symbol'))
        if not r:
            continue
        stamp = f"TRIGGER-WATCH {today.isoformat()}: {r.get('outcome')} - {r.get('note') or ''}"
        outcome = r.get('outcome')
        # outcome is authoritative: SLIPPED/FORWARD never demote, regardless of the
        # agent's fired/still_forward booleans (terminal-only rule)
        if outcome in ('FIRED_GOOD', 'FIRED_BAD', 'RESOLVED_OTHER'):
            n['tier'] = 'NONE'
            n['score'] = min(n.get('score') or 3, 3)
            changed.append(f"{n['symbol']} -> NONE ({outcome})")
        elif outcome == 'SLIPPED' and r.get('new_date'):
            n['dated_milestone'] = f"{r['new_date']} (slipped; was: {(n.get('dated_milestone') or '')[:200]})"
            changed.append(f"{n['symbol']} slipped -> {r['new_date']}")
        n['kill_fact'] = (stamp + ' | ' + (n.get('kill_fact') or ''))[:4000]
    json.dump(board, open(BOARD_F, 'w', encoding='utf-8'), indent=1)
    _sweep_pipe.regen_ts(board)
    print(f"APPLIED {len(by_sym)} results; {len(changed)} changes: {changed or 'none (all still forward)'}")
    print('board saved + TS regenerated')


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    today = datetime.date.today()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'due'
    if cmd == 'due':
        board = json.load(open(BOARD_F, encoding='utf-8'))
        for n, t in due_names(board, today):
            print(f"{n['symbol']:6} {t}  (score {n.get('score')}, {n.get('tier')})  {(n.get('dated_milestone') or '')[:90]}")
    elif cmd == 'gen':
        gen(today)
    elif cmd == 'apply':
        apply(sys.argv[2], today)
    else:
        print(__doc__)
