"""One-shot FMP congress-feed verification, run from the fmp-congress-check workflow.

Probes every plausible senate/house disclosure endpoint (stable + legacy v4) so we
learn which ones this FMP plan actually serves, then summarizes the last 30 days of
filings from whichever all-symbol feeds respond: totals, date coverage, and every
trade with a range lower bound >= $100,001. Prints to the Actions log only — the
key never appears in output (Actions masks the secret anyway; we also never echo
URLs). Delete this script + workflow once /api/briefing's Congress Watch is confirmed.
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
            body = e.read().decode()[:300]
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"

PROBES = [
    ("stable/senate-latest",            "page=0&limit=100"),
    ("stable/house-latest",             "page=0&limit=100"),
    ("stable/senate-trades",            "symbol=NVDA"),
    ("stable/house-trades",             "symbol=NVDA"),
    ("api/v4/senate-trading-rss-feed",  "page=0"),
    ("api/v4/senate-disclosure-rss-feed", "page=0"),
]

def main() -> None:
    if not KEY:
        print("FATAL: FMP_API_KEY secret is empty in this workflow run.")
        return

    print("=== Endpoint probe ===")
    ok_feeds: dict[str, list] = {}
    for path, params in PROBES:
        status, data = hit(path, params)
        rows = len(data) if isinstance(data, list) else None
        note = f"{rows} rows" if rows is not None else str(data)[:200]
        print(f"{status:>4}  {path:<38} {note}")
        if isinstance(data, list) and data and "latest" in path:
            ok_feeds[path] = data

    print("\n=== 30-day filing summary (from working all-symbol feeds) ===")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    merged = []
    for path, first_page in ok_feeds.items():
        rows = list(first_page)
        for page in range(1, 6):
            status, data = hit(path, f"page={page}&limit=100")
            if not isinstance(data, list) or not data:
                break
            rows.extend(data)
            if data[-1].get("disclosureDate", "")[:10] < cutoff:
                break
        chamber = "S" if "senate" in path else "H"
        dates = sorted(str(r.get("disclosureDate", ""))[:10] for r in rows if r.get("disclosureDate"))
        print(f"{path}: fetched {len(rows)} rows, disclosureDate {dates[0] if dates else '?'} .. {dates[-1] if dates else '?'}")
        merged.extend((chamber, r) for r in rows)

    if not merged:
        print("No all-symbol feed returned data — Congress Watch needs a different endpoint.")
        return

    def lo(amount) -> int:
        nums = re.findall(r"\d+", str(amount or "").replace(",", ""))
        return int(nums[0]) if nums else 0

    recent = [(c, r) for c, r in merged if str(r.get("disclosureDate", ""))[:10] >= cutoff]
    big = [(c, r) for c, r in recent if lo(r.get("amount")) >= 100_001]
    buys = sum(1 for _, r in big if re.search(r"purchase|buy", str(r.get("type", "")), re.I))
    print(f"\nFilings in last 30d: {len(recent)}   big (>=$100K): {len(big)}  ({buys} buys / {len(big) - buys} sells+other)")
    print("\nAll >=$100K filings, largest first:")
    for c, r in sorted(big, key=lambda x: lo(x[1].get("amount")), reverse=True):
        who = f"{r.get('firstName', '')} {r.get('lastName', '')}".strip() or r.get("office", "?")
        print(f"  [{c}] {r.get('symbol') or '(no ticker)':<8} {str(r.get('type'))[:14]:<14} "
              f"{str(r.get('amount')):<28} {who:<28} tx {str(r.get('transactionDate'))[:10]}  "
              f"filed {str(r.get('disclosureDate'))[:10]}")

if __name__ == "__main__":
    main()
