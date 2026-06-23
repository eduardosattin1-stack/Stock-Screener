#!/usr/bin/env python3
"""Cloud Run Job wrapper: download backtest from GCS, run backtest_time, upload results.
Handles both .csv (legacy) and .json (v7.2 format) inputs."""
import os, sys, json, csv, subprocess
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
                     headers={"Authorization": f"Bearer {token}"}, timeout=120)
    with open(local, "wb") as f:
        f.write(r.content)
    print(f"Downloaded {path} -> {local} ({len(r.content):,} bytes)")

def gcs_upload(local, path, content_type="text/csv"):
    token = get_token()
    with open(local, "rb") as f:
        data = f.read()
    r = requests.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o",
        params={"uploadType": "media", "name": path},
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        data=data, timeout=300)
    print(f"Uploaded {local} -> {path} ({r.status_code})")

def json_to_csv(json_path, csv_path):
    """Flatten backtest JSON payload -> CSV. Handles {data: [...]} or [...]."""
    with open(json_path, "r") as f:
        payload = json.load(f)
    samples = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not samples:
        raise RuntimeError("No samples found in JSON")
    # Union of all keys across samples (handles schema drift across regions)
    all_keys = set()
    for s in samples:
        all_keys.update(s.keys())
    fieldnames = sorted(all_keys)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for s in samples:
            # Coerce None -> "" so CSV stays clean
            w.writerow({k: ("" if v is None else v) for k, v in s.items()})
    print(f"Converted JSON -> CSV: {len(samples):,} samples, {len(fieldnames)} columns")

print(f"=== Time Backtest Job: {INPUT} ===")

local_input = f"/tmp/{INPUT}"
gcs_download(f"backtest/{INPUT}", local_input)

# Convert JSON to CSV if needed, also stash CSV on GCS for reuse
if INPUT.endswith(".json"):
    csv_name = INPUT.replace(".json", ".csv")
    local_csv = f"/tmp/{csv_name}"
    json_to_csv(local_input, local_csv)
    gcs_upload(local_csv, f"backtest/{csv_name}")
    input_path = local_csv
else:
    input_path = local_input

lines = sum(1 for _ in open(input_path))
print(f"Input: {lines:,} lines")

# backtest_time.py writes <input>_timed.csv next to the input
subprocess.run(
    [sys.executable, "backtest_time.py", input_path],
    cwd=os.path.dirname(os.path.abspath(__file__)),
    check=True,
)

output = input_path.replace(".csv", "_timed.csv")
if os.path.exists(output):
    out_lines = sum(1 for _ in open(output))
    print(f"Output: {out_lines:,} lines")
    gcs_upload(output, f"backtest/{os.path.basename(output)}")
    print("=== Done! ===")
else:
    print(f"ERROR: {output} not found")
    sys.exit(1)
