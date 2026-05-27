#!/usr/bin/env python3
"""
run_all_strategies.py
=====================
Single dispatcher for the three paper strategy runners. Invoked weekly by
the Cloud Run Job `strategy-runner-3-strategies` (Friday 06:30 CET, after
the global scan completes).

Each strategy self-gates its rotation cadence — Compounder rotates monthly,
Momentum and FA weekly — so a single weekly invocation is correct for all
three. Per-strategy failures are isolated: a broken Compounder doesn't
block Momentum or FA from running.

Strategies:
  - Compounder (v8, primary): top-20 SP500 ex Fin/Ins/HC by compounder_score,
    monthly rebalance, 50% sector cap, Top-40 hysteresis.
  - Momentum (v7.2 baseline): top-10 by composite_momentum, weekly rotation.
    Kept as the falsifier for v8 — Compounder must beat this to justify v8.
  - Fallen Angel (v8 portfolio + options source): top-10 by composite_fallen_angel,
    weekly rotation. Generates option-trade candidates from each scan.

Usage:
  export FMP_API_KEY=...
  python3 run_all_strategies.py [--dry-run]

Adding/removing strategies: edit the ENABLED list. Each entry must be an
importable module that exposes a top-level `run(dry_run: bool = False) -> bool`.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from importlib import import_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("dispatcher")

ENABLED = [
    "paper_strategy_runner_compounder_us",
    "paper_strategy_runner_compounder_global",
    "paper_strategy_runner_momentum",
    "paper_strategy_runner_fa",
    "paper_strategy_runner_speculair",
]


def run_one(mod_name: str, dry_run: bool) -> tuple[bool, float]:
    """Import + invoke one strategy. Returns (success, elapsed_seconds).
    Failures are caught and logged but don't propagate."""
    started = time.time()
    try:
        mod = import_module(mod_name)
        if not hasattr(mod, "run"):
            log.error(f"  {mod_name}: no top-level run() function — skipping")
            return False, time.time() - started
        ok = mod.run(dry_run=dry_run)
        return bool(ok), time.time() - started
    except SystemExit as e:
        # Some runners call sys.exit(1) on aborted runs; treat code 0 as success.
        log.warning(f"  {mod_name}: SystemExit({e.code})")
        return (e.code == 0), time.time() - started
    except Exception as e:
        log.error(f"  {mod_name}: crashed with {type(e).__name__}: {e}")
        log.error("  Traceback:\n" + traceback.format_exc())
        return False, time.time() - started


def main(dry_run: bool = False) -> int:
    log.info(f"Dispatcher starting — {len(ENABLED)} strategies enabled")
    log.info(f"  Strategies: {ENABLED}")
    if dry_run:
        log.info("  DRY-RUN mode: no GCS writes")

    if not os.environ.get("FMP_API_KEY"):
        log.error("FMP_API_KEY not set; aborting all strategies")
        return 1

    results: dict[str, dict] = {}
    overall_started = time.time()

    for i, mod_name in enumerate(ENABLED, 1):
        log.info("=" * 70)
        log.info(f"[{i}/{len(ENABLED)}] {mod_name}")
        log.info("=" * 70)
        ok, elapsed = run_one(mod_name, dry_run)
        results[mod_name] = {"ok": ok, "elapsed_s": round(elapsed, 1)}

    overall_elapsed = round(time.time() - overall_started, 1)

    log.info("=" * 70)
    log.info(f"Dispatcher complete in {overall_elapsed}s")
    for name, r in results.items():
        status = "✓" if r["ok"] else "✗"
        log.info(f"  {status} {name}: {r['elapsed_s']}s")

    n_ok = sum(1 for r in results.values() if r["ok"])
    n_total = len(results)
    if n_ok == n_total:
        log.info(f"All {n_total} strategies succeeded")
        return 0
    log.error(f"{n_total - n_ok}/{n_total} strategies failed")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Dispatcher for all paper strategies")
    ap.add_argument("--dry-run", action="store_true",
                    help="Pass --dry-run to every strategy (no GCS writes)")
    args = ap.parse_args()
    sys.exit(main(dry_run=args.dry_run))
