import os
from google.cloud import storage

def probe_bucket():
    bucket_name = "screener-signals-carbonbridge"
    print(f"🔍 Probing GCS Bucket: {bucket_name}...\n")
    
    try:
        # This will automatically pick up your Cloud Shell credentials
        client = storage.Client()
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"❌ Failed to authenticate or access GCS: {e}")
        print("Please ensure you are running this in Cloud Shell or have run 'gcloud auth application-default login'")
        return

    # List top-level folders (prefixes)
    iterator = client.list_blobs(bucket, delimiter='/')
    list(iterator)  # Consume the iterator to populate prefixes
    
    prefixes = iterator.prefixes
    if not prefixes:
        print("No folders found at top level.")
        return
        
    print(f"Found {len(prefixes)} top-level folders. Filtering for potential FMP caches...\n")
    
    # Filter for folders that likely contain FMP or cached data
    target_folders = [p for p in prefixes if 'cache' in p.lower() or 'fmp' in p.lower() or 'backtest' in p.lower()]
    
    for folder in target_folders:
        print(f"{'='*70}")
        print(f"📁 Inspecting Directory: {folder}")
        print(f"{'='*70}")
        
        # Get subfolders (which represent the FMP endpoints like 'income-statement', 'financial-scores')
        sub_iterator = client.list_blobs(bucket, prefix=folder, delimiter='/')
        list(sub_iterator)
        
        sub_prefixes = sub_iterator.prefixes
        if not sub_prefixes:
            # Check if there are files directly in the folder
            blobs = list(client.list_blobs(bucket, prefix=folder, max_results=10))
            if blobs:
                print(f"  No sub-folders. Contains direct files (e.g., {blobs[0].name.split('/')[-1]}).")
            else:
                print("  (Empty Folder)")
            continue
            
        for sub in sub_prefixes:
            endpoint_name = sub.replace(folder, '').strip('/')
            
            # Count files and find the newest file in this specific endpoint folder
            # We limit to 500 max_results per subfolder to keep the probe script extremely fast
            endpoint_blobs = list(client.list_blobs(bucket, prefix=sub, max_results=500))
            count = len(endpoint_blobs)
            
            if count == 0:
                print(f"  - /{endpoint_name:<35} | (Empty)")
                continue
                
            newest_blob = max(endpoint_blobs, key=lambda b: b.updated)
            newest_date = newest_blob.updated.strftime("%Y-%m-%d")
            
            count_display = f"{count}+" if count == 500 else str(count)
            print(f"  - /{endpoint_name:<35} | {count_display:>4} files | Newest: {newest_date}")
            
    print(f"\n✅ Probe complete.")

if __name__ == "__main__":
    probe_bucket()
