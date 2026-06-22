#!/usr/bin/env python3
"""Report the conviction distribution from the catalyst-funnel diagnostic run.

Reads _catalyst_results/{SYM}.json + _catalyst_skeptic/{SYM}.json + _catalyst_director.json
and answers the one question: did ANY name in the Basket-13 catalyst funnel break the
thresholds the priced-quality funnels never have — verdict-A (CRO), conviction-5 (CRO 1-5),
Director 0-100 >= 80? Prints a per-name table + the headline counts + writes a CSV.
"""
import json, glob, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "_catalyst_results")
SKEP = os.path.join(HERE, "_catalyst_skeptic")
DIRECTOR = os.path.join(HERE, "_catalyst_director.json")
CSV = os.path.join(HERE, "_catalyst_summary.csv")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    director = _load(DIRECTOR) or {}
    dassess = {a.get("symbol", "").upper(): a for a in (director.get("assessments") or [])}

    rows = []
    for rf in sorted(glob.glob(os.path.join(RES, "*.json"))):
        sym = os.path.splitext(os.path.basename(rf))[0].upper()
        r = _load(rf) or {}
        sk = _load(os.path.join(SKEP, sym + ".json")) or {}
        a = dassess.get(sym, {})
        rows.append({
            "symbol": sym,
            "cluster": r.get("cluster", ""),
            "driver": r.get("driver", ""),
            "cro_verdict": r.get("verdict", ""),
            "cro_conviction": r.get("conviction", ""),
            "value_conviction": r.get("value_conviction", ""),
            "director_conviction": a.get("conviction", ""),
            "skeptic_verdict": sk.get("verdict", ""),
            "skeptic_cap": sk.get("conviction_cap", ""),
            "catalyst_status": r.get("catalyst_status", ""),
            "posture": a.get("posture", ""),
            "expected_return_pct": a.get("expected_return_pct", ""),
            "live_price": r.get("live_price", ""),
            "target_px": r.get("target_px", ""),
            "downside_floor": r.get("downside_floor", ""),
            "binding_reason": a.get("binding_reason", "") or r.get("catalyst_summary", ""),
        })

    def num(x):
        try:
            return float(x)
        except Exception:
            return None

    n = len(rows)
    verdict_a = [r for r in rows if str(r["cro_verdict"]).upper() == "A"]
    conv5 = [r for r in rows if num(r["cro_conviction"]) == 5]
    conv4plus = [r for r in rows if (num(r["cro_conviction"]) or 0) >= 4]
    dir80 = [r for r in rows if (num(r["director_conviction"]) or 0) >= 80]
    dir70 = [r for r in rows if (num(r["director_conviction"]) or 0) >= 70]
    max_cro = max([num(r["cro_conviction"]) or 0 for r in rows] or [0])
    max_dir = max([num(r["director_conviction"]) or 0 for r in rows] or [0])

    # ---- per-name table ----
    print(f"\n=== CATALYST FUNNEL — {n} names ===")
    print(f"{'SYM':7}{'CLUSTER':16}{'CRO':5}{'v':3}{'DIR':5}{'SKEP':10}{'CATALYST':14}{'POSTURE':16}{' exp%':7}")
    order = {"A": 0, "B": 1, "C": 2}
    for r in sorted(rows, key=lambda x: (-(num(x["director_conviction"]) or 0))):
        print(f"{r['symbol']:7}{(r['cluster'] or '')[:15]:16}"
              f"{str(r['cro_verdict']):5}{str(r['cro_conviction']):3}"
              f"{str(r['director_conviction']):5}{(r['skeptic_verdict'] or '')[:9]:10}"
              f"{(r['catalyst_status'] or '')[:13]:14}{(r['posture'] or '')[:15]:16}"
              f"{str(r['expected_return_pct']):>6}")

    # ---- headline ----
    print("\n=== HEADLINE (vs 0-of-407 in the priced-quality funnels) ===")
    print(f"  verdict-A (CRO):        {len(verdict_a):>2}/{n}   {', '.join(r['symbol'] for r in verdict_a) or '(none)'}")
    print(f"  conviction-5 (CRO 1-5): {len(conv5):>2}/{n}   {', '.join(r['symbol'] for r in conv5) or '(none)'}")
    print(f"  conviction-4+ (CRO):    {len(conv4plus):>2}/{n}   {', '.join(r['symbol'] for r in conv4plus) or '(none)'}")
    print(f"  Director >= 80:         {len(dir80):>2}/{n}   {', '.join(r['symbol'] for r in dir80) or '(none)'}")
    print(f"  Director >= 70:         {len(dir70):>2}/{n}   {', '.join(r['symbol'] for r in dir70) or '(none)'}")
    print(f"  MAX CRO conviction = {max_cro:g}   |   MAX Director conviction = {max_dir:g}")
    print(f"  (Director self-reported: n_verdict_a={director.get('n_verdict_a')}, n_conv5={director.get('n_conv5')}, n_dir80={director.get('n_dir80')})")

    verdict = ("HYPOTHESIS CONFIRMED — the catalyst funnel surfaced a high-conviction pick the "
               "priced-quality funnels never have; 0-of-407 was a funnel-composition effect, not a calibration ceiling."
               if (verdict_a or conv5 or dir80) else
               "CALIBRATION CEILING — even the genuinely-asymmetric catalyst funnel capped out; the scale "
               "structurally suppresses the top band. Revisit the 'loosen the caps' option.")
    print(f"\n  >>> {verdict}\n")

    with open(CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"CSV: {CSV}")


if __name__ == "__main__":
    main()
