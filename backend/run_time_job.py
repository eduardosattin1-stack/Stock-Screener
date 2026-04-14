#!/usr/bin/env python3
"""Cloud Run Job wrapper: download CSV from GCS, run backtest_time, upload results."""
import os, sys, json, subprocess
import requests

BUCKET = "screener-signals-carbonbridge"
INPUT = os.environ.get("INPUT_FILE", "combined_2024_2025.csv")

def get_token():
    r = requests.get(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}, timeout=3)
    return r.json()["access_token"]

def gcs_download(path, local):
    token = get_token()
    r = requests.get(f"https://storage.googleapis.com/{BUCKET}/{path}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=60)
    with open(local, "wb") as f:
        f.write(r.content)
    print(f"Downloaded {path} -> {local} ({len(r.content)} bytes)")

def gcs_upload(local, path):
    token = get_token()
    with open(local, "rb") as f:
        data = f.read()
    r = requests.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o",
        params={"uploadType": "media", "name": path},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "text/csv"},
        data=data, timeout=120)
    print(f"Uploaded {local} -> {path} ({r.status_code})")

print(f"=== Time Backtest Job: {INPUT} ===")
gcs_download(f"backtest/{INPUT}", f"/tmp/{INPUT}")
lines = sum(1 for _ in open(f"/tmp/{INPUT}"))
print(f"Input: {lines} lines")

result = subprocess.run(
    [sys.executable, "backtest_time.py", f"/tmp/{INPUT}"],
    cwd=os.path.dirname(os.path.abspath(__file__))
)

output = f"/tmp/{INPUT.replace('.csv', '_timed.csv')}"
if os.path.exists(output):
    out_lines = sum(1 for _ in open(output))
    print(f"Output: {out_lines} lines")
    gcs_upload(output, f"backtest/{INPUT.replace('.csv', '_timed.csv')}")
    print("=== Done! ===")
else:
    print(f"ERROR: {output} not found")
    sys.exit(1)
