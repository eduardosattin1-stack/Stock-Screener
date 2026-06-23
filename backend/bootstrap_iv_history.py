#!/usr/bin/env python3
"""
Bootstrap IV-rank history from the ThetaData parquet cache.
=========================================================

`massive_options.compute_iv_rank` ranks today's ATM IV against a trailing
window stored at GCS `options/iv_history/{SYMBOL}.json` (format: [[YYYY-MM-DD, iv], ...]).
That history is normally grown one sample per nightly scan — so IVR stays `None`
for the first ~20 scans of each symbol.

This one-off seeds the history NOW from the local ThetaData parquet cache
(`Cache_Data/Theta_Historical/{SYMBOL}_theta.parquet`), so a real 52-week IV rank
is available on the very next scan. Run locally (the parquet cache + GCS creds are
local; the cache is .gcloudignore'd and not on Cloud Run).

ATM IV per date = implied_vol of the call whose delta is closest to 0.50
(matching build_theta_features.py and massive_options._extract_atm_iv intent),
filtered to iv_error < 0.1 and implied_vol > 0.

Usage:
  python bootstrap_iv_history.py                 # all symbols in the cache
  python bootstrap_iv_history.py --limit 50      # first 50 (smoke test)
  python bootstrap_iv_history.py --symbols AAPL,MSFT,NVDA
  python bootstrap_iv_history.py --dry-run       # compute + print, don't write GCS
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime, timedelta

import pandas as pd
from google.cloud import storage

from massive_options import IV_HISTORY_PREFIX, IV_HISTORY_KEEP_DAYS

CACHE_DIR = os.environ.get("THETA_CACHE_DIR", os.path.join("Cache_Data", "Theta_Historical"))
GCS_BUCKET = "screener-signals-carbonbridge"

# Local GCS auth via ADC (`gcloud auth application-default login`) or
# GOOGLE_APPLICATION_CREDENTIALS — NOT massive_options._gcs_write, whose metadata-server
# token only works on GCP. Matches backfill_history.py's local write pattern.
_bucket = None


def _gcs_put_json(path: str, data) -> bool:
    global _bucket
    try:
        if _bucket is None:
            _bucket = storage.Client().bucket(GCS_BUCKET)
        _bucket.blob(path).upload_from_string(json.dumps(data), content_type="application/json")
        return True
    except Exception as e:
        print(f"  GCS write error for {path}: {e}")
        return False


def atm_iv_series(df: pd.DataFrame) -> list[list]:
    """Return [[scan_date, atm_iv], ...] sorted ascending, within the keep window."""
    cols = set(df.columns)
    if not {"scan_date", "implied_vol", "delta"}.issubset(cols):
        return []

    d = df.copy()
    d = d[(d["implied_vol"] > 0)]
    if "iv_error" in cols:
        d = d[d["iv_error"] < 0.1]
    # calls only (delta > 0); ATM = delta closest to 0.50
    d = d[d["delta"] > 0]
    d = d.dropna(subset=["scan_date", "implied_vol", "delta"])
    if d.empty:
        return []

    d["_atm_dist"] = (d["delta"] - 0.50).abs()
    d = d.sort_values(["scan_date", "_atm_dist"])
    atm = d.groupby("scan_date", as_index=False).first()

    cutoff = (datetime.now() - timedelta(days=IV_HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")
    out = []
    for _, row in atm.iterrows():
        date_str = str(row["scan_date"])[:10]
        if date_str < cutoff:
            continue
        iv = float(row["implied_vol"])
        if iv > 0:
            out.append([date_str, round(iv, 4)])
    out.sort(key=lambda r: r[0])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap number of symbols (0 = all)")
    ap.add_argument("--symbols", type=str, default="", help="comma-separated symbol allowlist")
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write GCS")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*_theta.parquet")))
    if not files:
        print(f"No parquet files under {CACHE_DIR!r} — run from backend/ or set THETA_CACHE_DIR.")
        return

    allow = {s.strip().upper() for s in args.symbols.split(",") if s.strip()} if args.symbols else None
    if args.limit:
        files = files[: args.limit]

    written = skipped = errored = 0
    for i, path in enumerate(files, 1):
        symbol = os.path.basename(path).replace("_theta.parquet", "").upper()
        if allow and symbol not in allow:
            continue
        try:
            df = pd.read_parquet(path)
            series = atm_iv_series(df)
            if len(series) < 2:
                skipped += 1
                continue
            if args.dry_run:
                print(f"[{i}/{len(files)}] {symbol}: {len(series)} samples "
                      f"(latest {series[-1][0]} iv={series[-1][1]})")
                written += 1
                continue
            ok = _gcs_put_json(f"{IV_HISTORY_PREFIX}/{symbol}.json", series)
            if ok:
                written += 1
                if written % 100 == 0:
                    print(f"  …{written} written ({i}/{len(files)} scanned)")
            else:
                errored += 1
                print(f"  GCS write FAILED for {symbol}")
        except Exception as e:
            errored += 1
            print(f"  {symbol}: error {e}")

    print(f"\nDone. wrote={written} skipped(<2 samples)={skipped} errored={errored} "
          f"of {len(files)} parquet files. {'(dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
