"""FMP API key lookup — the ONE place a key is resolved. Never hardcode the key.

Order: FMP_API_KEY in the environment (Cloud Run sets it on the job/service; Vercel on the
frontend), else the FMP_API_KEY line of frontend/.env.local (the local weekly box keeps it
there — same source live_debate_engine.load_api_keys uses). Returns "" when neither has it,
so a missing key fails loud at the first FMP call instead of silently using a stale literal.
"""
import os
from pathlib import Path

_ENV_LOCAL = Path(__file__).resolve().parent.parent / "frontend" / ".env.local"


def fmp_key() -> str:
    key = os.environ.get("FMP_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in _ENV_LOCAL.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "FMP_API_KEY" and not line.lstrip().startswith("#"):
                key = value.strip().strip('"').strip("'")
                break
    except OSError:
        pass
    if key:
        os.environ["FMP_API_KEY"] = key   # later os.environ readers (screener_v6) see it too
    return key
