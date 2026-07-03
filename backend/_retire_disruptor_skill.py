"""One-time retirement hygiene for the Sunday runbook (FUTURE_RESOURCES_SPEC.md §10.1b).

Strips the retired "STEP 3C — DISRUPTOR LENS" block and any residual disruptor lines
(the STEP 4 reporting mention) from the local SKILL.md, which lives OUTSIDE the repo
(~/.claude/scheduled-tasks/speculair-opus-weekly/SKILL.md). Run automatically by
run_speculair_weekly.ps1 before the headless agent reads the runbook, so the edit
self-applies on the first post-pull Sunday run — no manual operator edit needed.

Idempotent and conservative: missing file or already-clean file is a printed no-op;
a timestamped .bak_* is written beside the original before any change; every removed
line is printed (lands in the Sunday launcher log for review).
"""
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_PATHS = [
    Path(r"C:\Users\Bruno\.claude\scheduled-tasks\speculair-opus-weekly\SKILL.md"),
    Path.home() / ".claude" / "scheduled-tasks" / "speculair-opus-weekly" / "SKILL.md",
]

STEP3C = re.compile(r"step\s*3c", re.I)
# a new step heading ends the 3C block: "STEP 4", "## STEP 3D", "STEP 5 ..." etc.
STEP_HEADER = re.compile(r"step\s*([045-9]|3d)\b", re.I)
DISRUPTOR = re.compile(r"disruptor", re.I)


def main() -> int:
    if len(sys.argv) > 1:
        candidates = [Path(sys.argv[1])]
    else:
        candidates = DEFAULT_PATHS
    skill = next((p for p in candidates if p.exists()), None)
    if skill is None:
        print(f"retire-disruptor-skill: SKILL.md not found ({', '.join(map(str, candidates))}) — nothing to patch, OK")
        return 0

    lines = skill.read_text(encoding="utf-8").splitlines(keepends=True)
    if not any(STEP3C.search(l) or DISRUPTOR.search(l) for l in lines):
        print(f"retire-disruptor-skill: {skill} already clean — no-op")
        return 0

    kept, removed = [], []
    in_3c = False
    for line in lines:
        # block start requires BOTH markers — a stray "see STEP 3C" cross-reference
        # elsewhere must not trigger a runaway cut to the next step heading
        if not in_3c and STEP3C.search(line) and DISRUPTOR.search(line):
            in_3c = True                    # cut from the STEP 3C heading...
        elif in_3c and STEP_HEADER.search(line) and not STEP3C.search(line):
            in_3c = False                   # ...up to (not including) the next step heading
        if in_3c or DISRUPTOR.search(line):  # residual disruptor lines (STEP 4 reporting) go too
            removed.append(line)
        else:
            kept.append(line)

    if not removed:
        print(f"retire-disruptor-skill: markers present but nothing matched for removal — "
              f"REVIEW {skill} BY HAND (no changes made)")
        return 1

    bak = skill.with_name(skill.name + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    bak.write_text("".join(lines), encoding="utf-8")
    skill.write_text("".join(kept), encoding="utf-8")
    print(f"retire-disruptor-skill: removed {len(removed)} line(s) from {skill} (backup: {bak})")
    for l in removed:
        print(f"  - {l.rstrip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
