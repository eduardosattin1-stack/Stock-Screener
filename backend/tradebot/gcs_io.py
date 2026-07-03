"""GCS layer for the bot — reuses calibration_tracker's hardened helpers.

Those helpers carry the generation-pinned read fix (GCS ?alt=media can serve
the PRIOR generation for seconds after a write, which silently corrupts
read-modify-write appends — see memory reference_gcs_read_after_write_staleness).
Do not reimplement raw GCS reads here.

Tests swap `impl` for a dict-backed fake (same pattern as test_calibration_tracker).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calibration_tracker import _gcs_read, _gcs_write, _gcs_append_jsonl, _gcs_read_text  # noqa: E402

impl = {
    "read": _gcs_read,            # (path, default) -> json, generation-pinned
    "read_text": _gcs_read_text,  # (path, default) -> str
    "write": _gcs_write,          # (path, data) -> bool
    "append_jsonl": _gcs_append_jsonl,  # (path, rows) -> bool, precondition-safe
}


def make_fake(store: dict) -> dict:
    """Dict-backed impl for unit tests."""
    import json as _json

    def read(path, default, generation=None):
        return _json.loads(store[path]) if path in store else default

    def read_text(path, default="", generation=None):
        return store.get(path, default)

    def write(path, data, content_type="application/json"):
        store[path] = data if isinstance(data, str) else _json.dumps(data)
        return True

    def append_jsonl(path, rows):
        if not rows:
            return True
        payload = "".join(_json.dumps(r, default=str) + "\n" for r in rows)
        existing = store.get(path, "")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        store[path] = existing + payload
        return True

    return {"read": read, "read_text": read_text, "write": write, "append_jsonl": append_jsonl}
