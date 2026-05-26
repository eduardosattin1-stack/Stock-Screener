"""
gcs_io.py — GCS read/write helpers for the Alpha Compounder pipeline.

Reuses the fmp_cache.py pattern: raw requests with GCE metadata token.
Adds parquet support via pyarrow.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

GCS_BUCKET = "screener-signals-carbonbridge"


def _gcs_token() -> Optional[str]:
    """GCE/Cloud Run metadata token. None when running locally."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/"
            "instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2,
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------

def gcs_write_json(path: str, data: Any, bucket: str = GCS_BUCKET) -> bool:
    """Write JSON to GCS. Returns True on success."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            log.debug(f"GCS write {path}: no token (local mode)")
            return False
        body = json.dumps(data, default=str).encode("utf-8")
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/json"},
            data=body, timeout=30,
        )
        if r.status_code in (200, 201):
            return True
        log.warning(f"GCS write {path}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"GCS write {path} failed: {e}")
    return False


def gcs_read_json(path: str, bucket: str = GCS_BUCKET) -> Optional[Any]:
    """Read JSON from GCS. Returns parsed object or None on miss/error."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            return None
        r = requests.get(
            f"https://storage.googleapis.com/{bucket}/{path}",
            headers={"Authorization": f"Bearer {tok}"}, timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        log.warning(f"GCS read {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS read {path} failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Parquet I/O
# ---------------------------------------------------------------------------

def gcs_write_parquet(path: str, df, bucket: str = GCS_BUCKET) -> bool:
    """Write a pandas DataFrame as parquet to GCS."""
    try:
        import requests
        tok = _gcs_token()
        if not tok:
            log.debug(f"GCS parquet write {path}: no token (local mode)")
            return False

        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        buf.seek(0)

        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/octet-stream"},
            data=buf.read(), timeout=60,
        )
        if r.status_code in (200, 201):
            log.info(f"GCS parquet written: {path} ({len(df)} rows)")
            return True
        log.warning(f"GCS parquet write {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS parquet write {path} failed: {e}")
    return False


def gcs_read_parquet(path: str, bucket: str = GCS_BUCKET):
    """Read a parquet file from GCS into a pandas DataFrame."""
    try:
        import pandas as pd
        import requests
        tok = _gcs_token()
        if not tok:
            return None
        r = requests.get(
            f"https://storage.googleapis.com/{bucket}/{path}",
            headers={"Authorization": f"Bearer {tok}"}, timeout=30,
        )
        if r.status_code == 200:
            return pd.read_parquet(io.BytesIO(r.content))
        if r.status_code == 404:
            return None
        log.warning(f"GCS parquet read {path}: {r.status_code}")
    except Exception as e:
        log.warning(f"GCS parquet read {path} failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Local I/O fallback (for development without GCS)
# ---------------------------------------------------------------------------

def local_write_json(filepath: str, data: Any) -> bool:
    """Write JSON to local filesystem."""
    import os
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, default=str, indent=2)
    return True


def local_read_json(filepath: str) -> Optional[Any]:
    """Read JSON from local filesystem."""
    import os
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        return json.load(f)


def local_write_parquet(filepath: str, df) -> bool:
    """Write DataFrame as parquet to local filesystem."""
    import os
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_parquet(filepath, engine="pyarrow", index=False)
    return True


def local_read_parquet(filepath: str):
    """Read parquet from local filesystem."""
    import os
    import pandas as pd
    if not os.path.exists(filepath):
        return None
    return pd.read_parquet(filepath)
