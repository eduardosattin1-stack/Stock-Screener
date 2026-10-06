"""FMP API key lookup — the ONE place a key is resolved. Never hardcode the key.

Order: FMP_API_KEY in the environment (Cloud Run sets it on the job/service; Vercel on the
frontend), else the FMP_API_KEY line of the nearest frontend/.env.local walking up from this
file (the local weekly box keeps it there — same source live_debate_engine.load_api_keys
uses; walking up also finds the main checkout's file from a .claude/worktrees/<x> worktree).
Returns "" with a stderr WARN when neither has it — callers must treat "" as "no key".
"""
import os
import sys
from pathlib import Path


def _env_local_candidates():
    for parent in Path(__file__).resolve().parents:
        yield parent / "frontend" / ".env.local"


def fmp_key() -> str:
    key = os.environ.get("FMP_API_KEY", "").strip()
    if key:
        return key
    for env_local in _env_local_candidates():
        try:
            lines = env_local.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            name, sep, value = line.partition("=")
            if sep and name.strip() == "FMP_API_KEY" and not line.lstrip().startswith("#"):
                key = value.strip().strip('"').strip("'")
                break
        if key:
            break
    if key:
        os.environ["FMP_API_KEY"] = key   # later os.environ readers (screener_v6) see it too
    else:
        print("WARN _fmp_key: FMP_API_KEY not in env or any frontend/.env.local - FMP calls will fail",
              file=sys.stderr)
    return key
