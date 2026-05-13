from google.cloud import storage
import json

client = storage.Client()
bucket = client.bucket("screener-signals-carbonbridge")

for prefix in ["fmp_cache/income-statement", "fmp_cache/key-metrics", "cache"]:
    blob = bucket.blob(f"{prefix}/AAPL.json")
    if blob.exists():
        data = json.loads(blob.download_as_string())
        print(f"{prefix}/AAPL.json exists. Type: {type(data)}, length: {len(data)}")
        if isinstance(data, dict):
            print("Keys:", list(data.keys())[:5])
    else:
        print(f"{prefix}/AAPL.json does not exist.")

blob = bucket.blob(f"cache/historical-price-full_AAPL.json")
if blob.exists():
    data = json.loads(blob.download_as_string())
    print(f"cache/historical-price-full_AAPL.json exists. Type: {type(data)}, length: {len(data)}")
else:
    print(f"cache/historical-price-full_AAPL.json does not exist.")
