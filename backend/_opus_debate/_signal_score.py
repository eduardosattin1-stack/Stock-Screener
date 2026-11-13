"""Weekly signal scorecard (2026-11-12 reliability review).

Scores what the debate SAID against what prices DID, so a rule that leans on a signal can be checked
against evidence instead of belief. One row per run is appended to _signal_scorecard.jsonl.

Why it exists: the review found the debate reliable as a FILTER (pass grades and low value
conviction lagged on almost every run date) but not as a RANKING at the top (grade A no better than
B, value conviction 4 no better than 3, the value Director's score ran backwards inside its own
book). The one promising ranking signal - the gap between the live price and the typed fair value -
rested on only two scoreable run dates. The value Director now ranks by that gap, so it has to keep
earning the job. This file is the test.

Method: every dated entry in the per-symbol debate history is a statement "on date D the system
graded this name X". Forward return = first daily close AFTER D to the last close on or before
D + horizon. Each group is measured against the average of ALL names debated on the same date
(so a falling or rising market cancels out), and a group "wins a date" when its mean beat that pool.

Read-only apart from its own price cache and the scorecard file. It never changes a record, a seat,
a weight or a grade.

    python backend/weekly_opus_refresh.py signal-score            (fetches prices, appends a row)
    python backend/_opus_debate/_signal_score.py --offline        (cache only, prints, no append)
"""
import collections
import datetime as dt
import glob
import json
import math
import os
import statistics as st
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HIST = REPO / "frontend" / "public" / "speculair_debate_history"
PXC = HERE / "_px_cache"
CARD = HERE / "_signal_scorecard.jsonl"
START = "2026-06-01"
HORIZONS = (("4w", 28), ("8w", 56))
MIN_POOL = 30            # a run date needs at least this many scoreable names to count
CACHE_MAX_AGE_D = 5


def D(s):
    return dt.date.fromisoformat(str(s)[:10])


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def spearman(a, b):
    if len(a) < 8:
        return None

    def rk(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            for k in range(i, j + 1):
                r[s[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    ma, mb = st.mean(ra), st.mean(rb)
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / den if den else None


# ── prices ───────────────────────────────────────────────────────────────────
def load_prices(symbols, offline=False, key=None):
    """{symbol: [(date, close), ...] ascending}. Cached per symbol; refetched when older than
    CACHE_MAX_AGE_D days. A failed fetch keeps whatever the cache already holds."""
    PXC.mkdir(parents=True, exist_ok=True)
    out, need = {}, []
    now = time.time()
    for s in symbols:
        p = PXC / (s.replace("/", "_") + ".json")
        fresh = p.exists() and (now - p.stat().st_mtime) < CACHE_MAX_AGE_D * 86400
        if p.exists():
            try:
                out[s] = sorted(json.load(open(p)).items())
            except Exception:
                pass
        if not fresh:
            need.append(s)
    if need and not offline and key:
        import requests
        from concurrent.futures import ThreadPoolExecutor

        def get(s):
            for _ in range(3):
                try:
                    r = requests.get("https://financialmodelingprep.com/stable/historical-price-eod/light",
                                     params={"symbol": s, "from": START, "to": dt.date.today().isoformat(),
                                             "apikey": key}, timeout=25)
                    if r.status_code == 200:
                        d = r.json()
                        rows = {x["date"]: x["price"] for x in d
                                if isinstance(x, dict) and x.get("price")} if isinstance(d, list) else {}
                        if rows:
                            json.dump(rows, open(PXC / (s.replace("/", "_") + ".json"), "w"))
                        return s, rows
                    if r.status_code == 429:
                        time.sleep(3)
                except Exception:
                    time.sleep(1)
            return s, None
        with ThreadPoolExecutor(6) as ex:
            for s, rows in ex.map(get, need):
                if rows:
                    out[s] = sorted(rows.items())
    return out


def _after(px, day, lag=6):
    for ds, p in px or []:
        dd = D(ds)
        if dd > day:
            return (dd, p) if (dd - day).days <= lag else None
    return None


def _onbefore(px, day, lag=6):
    best = None
    for ds, p in px or []:
        dd = D(ds)
        if dd <= day:
            best = (dd, p)
        else:
            break
    return best if best and (day - best[0]).days <= lag else None


def forward(px, day, cal_days):
    a, b = _after(px, day), _onbefore(px, day + dt.timedelta(days=cal_days))
    if not a or not b or b[0] <= a[0]:
        return None
    r = b[1] / a[1] - 1
    return r if -0.85 < r < 4 else None


# ── history ──────────────────────────────────────────────────────────────────
def load_history(hist_dir=HIST):
    obs = []
    for f in glob.glob(str(Path(hist_dir) / "*.json")):
        sym = os.path.basename(f)[:-5]
        try:
            x = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for e in (x.get("history") if isinstance(x, dict) else x) or []:
            try:
                d = D(e.get("date"))
            except Exception:
                continue
            g = str(e.get("verdict") or "")[:1].upper()
            if g not in ("A", "B", "C"):
                continue
            v = e.get("valuation") if isinstance(e.get("valuation"), dict) else {}
            px, base = _num(v.get("live_price")), _num(v.get("base_fv_px"))
            gap = (base / px - 1) if px and base and -0.9 < base / px - 1 < 5 else None
            obs.append({"s": sym, "d": d, "grade": g, "vconv": _num(e.get("value_conviction")),
                        "carried": bool(e.get("carried")), "gap": gap})
    return obs


# ── scoring ──────────────────────────────────────────────────────────────────
def score(obs, prices, today=None):
    today = today or dt.date.today()
    card = {"scored_at": today.isoformat(), "history_entries": len(obs), "horizons": {}}
    for lab, cal in HORIZONS:
        o = []
        for x in obs:
            f = forward(prices.get(x["s"]), x["d"], cal)
            if f is not None:
                o.append({**x, "f": f})
        n_by_date = collections.Counter(x["d"] for x in o)
        o = [x for x in o if n_by_date[x["d"]] >= MIN_POOL]
        if not o:
            card["horizons"][lab] = {"dates": 0}
            continue
        pool = {d: st.mean(x["f"] for x in o if x["d"] == d) for d in set(x["d"] for x in o)}

        def group(key, keys):
            g = collections.defaultdict(list)
            for x in o:
                g[key(x)].append(x)
            res = {}
            for k in keys:
                v = g.get(k, [])
                if len(v) < 5:
                    continue
                byd = collections.defaultdict(list)
                for x in v:
                    byd[x["d"]].append(x["f"] - pool[x["d"]])
                res[str(k)] = {"n": len(v), "excess_pct": round(100 * st.mean(x["f"] - pool[x["d"]] for x in v), 2),
                               "dates_won": sum(1 for q in byd.values() if st.mean(q) > 0), "dates": len(byd)}
            return res
        h = {"dates": len(pool), "obs": len(o), "first": min(pool).isoformat(), "last": max(pool).isoformat(),
             "grade": group(lambda x: x["grade"], ["A", "B", "C"]),
             "value_conviction": group(lambda x: x["vconv"], [1.0, 2.0, 3.0, 4.0, 5.0]),
             "record": group(lambda x: "carried" if x["carried"] else "fresh", ["fresh", "carried"])}
        ics = []
        for d in sorted(pool):
            gq = [x for x in o if x["d"] == d and x["gap"] is not None]
            ic = spearman([x["gap"] for x in gq], [x["f"] for x in gq])
            if ic is not None and len(gq) >= MIN_POOL:
                ics.append(ic)
        u = sorted([x for x in o if x["gap"] is not None], key=lambda x: x["gap"])
        gap = {"dates": len(ics), "mean_rank_corr": round(st.mean(ics), 3) if ics else None,
               "dates_positive": sum(1 for i in ics if i > 0)}
        if len(u) >= 50:
            n = len(u) // 5
            q = [round(100 * st.mean(x["f"] - pool[x["d"]] for x in u[i * n:(i + 1) * n if i < 4 else len(u)]), 2)
                 for i in range(5)]
            gap["quintile_excess_pct_low_to_high"] = q
            gap["top_minus_bottom_pct"] = round(q[4] - q[0], 2)
        h["fair_value_gap"] = gap
        card["horizons"][lab] = h
    return card


def verdict(card):
    """Plain one-paragraph read of the 4-week horizon: is each rule's signal still earning its job?"""
    h = (card.get("horizons") or {}).get("4w") or {}
    if not h.get("dates"):
        return "signal scorecard: not enough scoreable run dates yet"
    g, vc, rec, gap = h.get("grade", {}), h.get("value_conviction", {}), h.get("record", {}), h.get("fair_value_gap", {})
    parts = [f"signal scorecard ({h['dates']} run dates, {h['first']} to {h['last']}, 4 weeks forward, excess over the same-week pool):"]
    if g:
        parts.append("  grade  " + " | ".join(f"{k} {v['excess_pct']:+.1f} pts ({v['dates_won']}/{v['dates']} dates)" for k, v in g.items()))
    if vc:
        parts.append("  value conviction  " + " | ".join(f"{k[0]} {v['excess_pct']:+.1f}" for k, v in vc.items()))
    if rec:
        parts.append("  record  " + " | ".join(f"{k} {v['excess_pct']:+.1f} ({v['dates_won']}/{v['dates']})" for k, v in rec.items()))
    if gap.get("dates"):
        parts.append(f"  fair-value gap  rank correlation {gap['mean_rank_corr']:+.3f} over {gap['dates']} date(s), positive on "
                     f"{gap['dates_positive']}" + (f" | top fifth minus bottom fifth {gap['top_minus_bottom_pct']:+.1f} pts"
                                                   if gap.get("top_minus_bottom_pct") is not None else ""))
        if gap["dates"] < 8:
            parts.append(f"  NOTE: the fair-value gap has only {gap['dates']} scoreable date(s) - still a lead, not a finding")
        elif gap["mean_rank_corr"] is not None and (gap["mean_rank_corr"] <= 0 or gap["dates_positive"] * 2 <= gap["dates"]):
            parts.append("  WARN: the fair-value gap is NOT ranking outcomes - the value Director's seat order rests on it; review that rule")
    else:
        parts.append("  fair-value gap  no scoreable date yet")
    return "\n".join(parts)


def main(offline=False, append=True, key=None):
    obs = load_history()
    if not obs:
        print("signal scorecard: no debate history found")
        return None
    syms = sorted({x["s"] for x in obs})
    prices = load_prices(syms, offline=offline, key=key)
    card = score(obs, prices)
    card["symbols"], card["symbols_priced"] = len(syms), sum(1 for s in syms if prices.get(s))
    print(verdict(card))
    print(f"  ({card['symbols_priced']} of {card['symbols']} names priced)")
    if append and not offline:
        with open(CARD, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(card, ensure_ascii=False) + "\n")
        print(f"  appended -> {CARD.name}")
    return card


if __name__ == "__main__":
    _off = "--offline" in sys.argv
    _key = os.environ.get("FMP_API_KEY", "")
    main(offline=_off, append=not _off, key=_key)
