"""One-shot FMP price-target feed verification (temporary, like the congress check).

Answers the questions needed to build a Target Watch briefing section:
1. Which price-target / grade endpoints does this plan serve?
2. What fields does each row carry (is there a previous target for real deltas,
   or do we derive direction from the news title / price-when-posted)?
3. How many days does a page of the all-symbol feed cover at limit=100 vs 1000 —
   i.e. can we span 30 days market-wide, or must we go per-symbol?
4. A sample "most substantial deltas" ranking so the scoring rule can be sanity-
   checked against real rows before it ships.
Prints to the Actions log only; the key is never echoed.
"""
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("FMP_API_KEY", "")
BASE = "https://financialmodelingprep.com"

def hit(path: str, params: str) -> tuple[int, object]:
    url = f"{BASE}/{path}?{params}&apikey={KEY}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()[:200]
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"

PROBES = [
    ("stable/price-target-latest-news", "page=0&limit=100"),
    ("stable/price-target-news",        "symbol=NVDA&page=0&limit=5"),
    ("stable/price-target-consensus",   "symbol=NVDA"),
    ("stable/grades-latest-news",       "page=0&limit=100"),
    ("stable/grades-news",              "symbol=NVDA&page=0&limit=5"),
]

def main() -> None:
    if not KEY:
        print("FATAL: FMP_API_KEY secret is empty.")
        return

    print("=== Endpoint probe (status / rows / first-row keys) ===")
    for path, params in PROBES:
        status, data = hit(path, params)
        if isinstance(data, list) and data:
            print(f"{status:>4}  {path:<38} {len(data)} rows")
            print(f"      keys: {sorted(data[0].keys())}")
        else:
            print(f"{status:>4}  {path:<38} {str(data)[:160]}")

    print("\n=== Feed depth: date coverage per pull size ===")
    for limit in (100, 250, 1000):
        status, data = hit("stable/price-target-latest-news", f"page=0&limit={limit}")
        if isinstance(data, list) and data:
            dates = sorted(str(r.get("publishedDate", ""))[:10] for r in data)
            print(f"limit={limit}: {len(data)} rows, {dates[0]} .. {dates[-1]}")
        else:
            print(f"limit={limit}: {status} {str(data)[:120]}")

    print("\n=== Sample rows (title shapes — do they carry the prior target?) ===")
    _, data = hit("stable/price-target-latest-news", "page=0&limit=100")
    if isinstance(data, list):
        for r in data[:8]:
            print(f"  {r.get('symbol'):<7} PT {r.get('priceTarget')}  px@post {r.get('priceWhenPosted')}  "
                  f"{str(r.get('analystCompany'))[:24]}  | {str(r.get('newsTitle'))[:110]}")

        print("\n=== 'from $X' parse rate + biggest deltas in this pull ===")
        pat = re.compile(r"from\s+\$([0-9][0-9,.]*)", re.I)
        rows = []
        for r in data:
            pt = r.get("priceTarget") or 0
            px = r.get("priceWhenPosted") or 0
            m = pat.search(str(r.get("newsTitle", "")))
            prev = float(m.group(1).replace(",", "")) if m else None
            rows.append((r, pt, px, prev))
        parseable = sum(1 for _, _, _, p in rows if p)
        print(f"rows with parseable prior target in title: {parseable}/{len(rows)}")
        scored = []
        for r, pt, px, prev in rows:
            if prev and prev > 0:
                delta = (pt - prev) / prev * 100
                basis = f"vs prior ${prev:g}"
            elif px and px > 0 and pt:
                delta = (pt - px) / px * 100
                basis = "vs px@post"
            else:
                continue
            scored.append((delta, basis, r))
        scored.sort(key=lambda x: abs(x[0]), reverse=True)
        for delta, basis, r in scored[:12]:
            print(f"  {delta:+7.1f}% {basis:<16} {r.get('symbol'):<7} -> ${r.get('priceTarget')}  "
                  f"{str(r.get('analystCompany'))[:24]}  {str(r.get('publishedDate'))[:10]}")

if __name__ == "__main__":
    main()
