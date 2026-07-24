"""Two cohort joins the reviewer asked for, on the 2151-entry point-in-time debate panel:
  JOIN 1 — FIRED/SOFT-penalized cohort vs non-penalized, forward return.
  JOIN 2 — valuation-gate (NO_UPSIDE / thin implied upside) cohort vs the rest.
Both entry-level AND symbol-clustered (weekly carries make entries autocorrelated), with
bootstrap CIs clustered on symbol. One regime (~7 weeks) — stated, not hidden."""
import json, glob, re, statistics, random
from pathlib import Path
from collections import defaultdict

random.seed(7)
SP = Path(r"C:\Users\Bruno\AppData\Local\Temp\claude\C--Users-Bruno-Stock-Screener\0d7172e2-459b-4bfd-9afa-c9112bcf0023\scratchpad")
HIST = Path(r"C:\Users\Bruno\Stock-Screener\frontend\public\speculair_debate_history")
PX = SP / "px_cache"

# ── price series ────────────────────────────────────────────────────────────
px = {}
for f in PX.glob("*.json"):
    try:
        rows = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    ser = sorted(((r["date"][:10], r["close"]) for r in rows
                  if r.get("date") and isinstance(r.get("close"), (int, float)) and r["close"] > 0))
    if ser:
        px[f.stem] = ser

def px_on_or_after(sym, date):
    ser = px.get(sym)
    if not ser:
        return None, None
    for d, c in ser:
        if d >= date:
            return c, d
    return None, None

def px_fwd(sym, date, ndays):
    """close ndays TRADING days after the first bar >= date"""
    ser = px.get(sym)
    if not ser:
        return None
    idx = next((i for i, (d, _) in enumerate(ser) if d >= date), None)
    if idx is None or idx + ndays >= len(ser):
        return None
    return ser[idx + ndays][1]

def px_last(sym):
    ser = px.get(sym)
    return ser[-1][1] if ser else None

NUM = re.compile(r"-?\d[\d,]*\.?\d*")
def parse_fv(s):
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    m = NUM.search(s.replace(",", ""))
    try:
        return float(m.group()) if m else None
    except ValueError:
        return None

# ── build the panel ─────────────────────────────────────────────────────────
rows = []
for f in HIST.glob("*.json"):
    sym = f.stem
    try:
        entries = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    for e in entries:
        d = str(e.get("date") or "")[:10]
        if not d:
            continue
        p0, d0 = px_on_or_after(sym, d)
        if not p0:
            continue
        pnow, p21 = px_last(sym), px_fwd(sym, d, 21)
        cs = str(e.get("catalyst_status") or "").strip().upper()
        cs = next((t for t in ("PENDING_HARD", "SOFT_EXTENDED", "UNVERIFIABLE", "FIRED", "ARB")
                   if cs.startswith(t)), "")
        fv = parse_fv(e.get("sop_fair_value"))
        upside = (fv / p0 - 1) if (fv and 0.1 < fv / p0 < 10) else None
        rows.append({
            "symbol": sym, "date": d, "px0": p0, "verdict": e.get("verdict"),
            "conviction": e.get("conviction"), "value_conviction": e.get("value_conviction"),
            "catalyst": cs, "upside": upside,
            "fwd_now": (pnow / p0 - 1) if pnow else None,
            "fwd_21d": (p21 / p0 - 1) if p21 else None,
        })
print(f"panel: {len(rows)} entries | {len({r['symbol'] for r in rows})} symbols "
      f"| catalyst-tagged {sum(1 for r in rows if r['catalyst'])} | upside-parsed {sum(1 for r in rows if r['upside'] is not None)}")

def desc(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return "n=0"
    return (f"n={len(vals):4} mean={statistics.mean(vals)*100:+6.2f}% "
            f"med={statistics.median(vals)*100:+6.2f}% win%={sum(1 for v in vals if v > 0)/len(vals)*100:4.0f}")

def clustered_boot(rows_a, rows_b, key, iters=4000):
    """bootstrap the mean difference (A - B), resampling SYMBOLS (clusters), not entries"""
    by_a, by_b = defaultdict(list), defaultdict(list)
    for r in rows_a:
        if isinstance(r.get(key), (int, float)): by_a[r["symbol"]].append(r[key])
    for r in rows_b:
        if isinstance(r.get(key), (int, float)): by_b[r["symbol"]].append(r[key])
    sa, sb = list(by_a), list(by_b)
    if not sa or not sb:
        return None
    diffs = []
    for _ in range(iters):
        ra = [v for s in (random.choice(sa) for _ in sa) for v in by_a[s]]
        rb = [v for s in (random.choice(sb) for _ in sb) for v in by_b[s]]
        if ra and rb:
            diffs.append(statistics.mean(ra) - statistics.mean(rb))
    diffs.sort()
    return (statistics.mean(diffs) * 100, diffs[int(.025 * len(diffs))] * 100, diffs[int(.975 * len(diffs))] * 100)

def first_obs(rows_sub):
    """one row per symbol — its EARLIEST entry (independent-ish observations)"""
    best = {}
    for r in rows_sub:
        if r["symbol"] not in best or r["date"] < best[r["symbol"]]["date"]:
            best[r["symbol"]] = r
    return list(best.values())

out = []
def P(s=""):
    print(s); out.append(s)

# ════════ JOIN 1 — the catalyst penalty ════════
P("=" * 96)
P("JOIN 1 — FIRED/SOFT-penalized cohort vs non-penalized (PENDING_HARD/ARB)")
P("=" * 96)
pen = [r for r in rows if r["catalyst"] in ("FIRED", "SOFT_EXTENDED")]
non = [r for r in rows if r["catalyst"] in ("PENDING_HARD", "ARB")]
for horizon in ("fwd_now", "fwd_21d"):
    P(f"\n-- {horizon} --")
    P(f"  PENALIZED (FIRED/SOFT) : {desc([r[horizon] for r in pen])}")
    P(f"  NON-PENALIZED (PH/ARB) : {desc([r[horizon] for r in non])}")
    b = clustered_boot(pen, non, horizon)
    if b:
        P(f"  diff (pen - nonpen)    : {b[0]:+.2f}pp   95% CI [{b[1]:+.2f}, {b[2]:+.2f}]  "
          f"{'SIGNIFICANT' if (b[1] > 0) == (b[2] > 0) else 'not significant (CI spans 0)'}")
P("\n-- symbol-clustered (each symbol's FIRST entry only) --")
fp, fn = first_obs(pen), first_obs(non)
P(f"  PENALIZED     : {desc([r['fwd_now'] for r in fp])}")
P(f"  NON-PENALIZED : {desc([r['fwd_now'] for r in fn])}")
P("\n-- per catalyst_status --")
for cs in ("FIRED", "SOFT_EXTENDED", "PENDING_HARD", "ARB", "UNVERIFIABLE"):
    sub = [r for r in rows if r["catalyst"] == cs]
    P(f"  {cs:14}: {desc([r['fwd_now'] for r in sub])}")

P("\n-- does the (penalty-depressed) CONVICTION predict forward return? --")
for cv in (1, 2, 3, 4, 5):
    sub = [r for r in rows if r["conviction"] == cv]
    if sub:
        P(f"  conviction {cv}: {desc([r['fwd_now'] for r in sub])}")
P("\n-- verdict --")
for v in ("A", "B", "C"):
    sub = [r for r in rows if r["verdict"] == v]
    if sub:
        P(f"  verdict {v}: {desc([r['fwd_now'] for r in sub])}")
P("\n-- catalyst-blind value_conviction (where present) --")
for cv in (1, 2, 3, 4, 5):
    sub = [r for r in rows if r["value_conviction"] == cv]
    if sub:
        P(f"  value_conviction {cv}: {desc([r['fwd_now'] for r in sub])}")

# ════════ JOIN 2 — the valuation stack ════════
P("\n" + "=" * 96)
P("JOIN 2 — valuation gate: implied upside (sop_fair_value vs price at debate) vs forward return")
P("=" * 96)
up = [r for r in rows if r["upside"] is not None and isinstance(r["fwd_now"], (int, float))]
noup = [r for r in up if r["upside"] <= 0]
posup = [r for r in up if r["upside"] > 0]
P(f"\n  NO_UPSIDE (fv <= px)  : {desc([r['fwd_now'] for r in noup])}")
P(f"  POSITIVE UPSIDE       : {desc([r['fwd_now'] for r in posup])}")
b = clustered_boot(noup, posup, "fwd_now")
if b:
    P(f"  diff (noup - posup)   : {b[0]:+.2f}pp   95% CI [{b[1]:+.2f}, {b[2]:+.2f}]  "
      f"{'SIGNIFICANT' if (b[1] > 0) == (b[2] > 0) else 'not significant (CI spans 0)'}")
P("\n-- forward return by implied-upside quintile (does the FV stack rank anything?) --")
su = sorted(up, key=lambda r: r["upside"])
q = max(1, len(su) // 5)
for i in range(5):
    chunk = su[i * q:(i + 1) * q] if i < 4 else su[4 * q:]
    if chunk:
        P(f"  Q{i+1} upside [{chunk[0]['upside']*100:+7.1f}%..{chunk[-1]['upside']*100:+7.1f}%]: "
          f"{desc([r['fwd_now'] for r in chunk])}")
# Spearman
def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); rk = [0.0] * len(v)
        for pos, i in enumerate(s): rk[i] = pos
        return rk
    rx, ry = rank(xs), rank(ys); n = len(xs)
    if n < 3: return None
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** .5
    return num / den if den else None
sp = spearman([r["upside"] for r in up], [r["fwd_now"] for r in up])
P(f"\n  Spearman(implied upside, forward return) = {sp:+.3f}  (n={len(up)})")
fo = first_obs(up)
sp2 = spearman([r["upside"] for r in fo], [r["fwd_now"] for r in fo])
P(f"  symbol-clustered (first entry each)      = {sp2:+.3f}  (n={len(fo)})")

# the 20 winners under the FV stack
WIN = ["DAVE","SEZL","TDOC","CORT","INSP","WEX","RVLV","TNET","LZ","ANF","HUBG","EEFT","CALM","INNV","CARG","HRB","UPBD","MOH","YELP","CTSH"]
P("\n-- the 20 winners: what the FV stack said at their FIRST debate --")
nz = 0
for s in WIN:
    fr = [r for r in up if r["symbol"] == s]
    if not fr:
        P(f"  {s:6}: no parsed FV"); continue
    r = min(fr, key=lambda x: x["date"])
    flag = "NO_UPSIDE" if r["upside"] <= 0 else ""
    nz += 1 if r["upside"] <= 0 else 0
    P(f"  {s:6} {r['date']}: implied upside {r['upside']*100:+6.1f}%  ->  realized {r['fwd_now']*100:+6.1f}%  {flag}")
P(f"  ({nz} of {len([s for s in WIN if any(r['symbol']==s for r in up)])} winners were NO_UPSIDE at first debate)")

(SP / "cohort_joins_output.txt").write_text("\n".join(out), encoding="utf-8")
json.dump(rows, open(SP / "panel.json", "w"), indent=0)
print(f"\nwrote {SP/'cohort_joins_output.txt'} and panel.json")
