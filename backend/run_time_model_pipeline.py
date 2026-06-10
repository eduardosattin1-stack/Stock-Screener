"""
Orchestrator for the multi-agent time-model pipeline.

Runs three stages sequentially:
  1. Data Steward  – builds the training parquet
  2. Trainer       – fits the time model
  3. Validator     – checks quality gates

Usage:
    python run_time_model_pipeline.py
    python run_time_model_pipeline.py --skip-data
    python run_time_model_pipeline.py --validate-only
"""

import argparse
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("TimeModel-Pipeline")

BACKEND = os.path.dirname(os.path.abspath(__file__))

# Staged promotion: the trainer writes to *.staging; only a full gate pass
# promotes the artifact to its final name. Serving auto-promotes v4 by file
# presence (screener_v6), so a failed run must leave NO time_model_v4.pkl
# and NO time_model_v4_meta.json behind.
FINAL_PKL = os.path.join(BACKEND, "time_model_v4.pkl")
STAGING_PKL = FINAL_PKL + ".staging"
REJECTED_PKL = FINAL_PKL + ".rejected"
FINAL_META = os.path.join(BACKEND, "time_model_v4_meta.json")
STAGING_META = FINAL_META + ".staging"


def _run_stage(name: str, func) -> float:
    """Execute *func*, log elapsed time, and re-raise on failure."""
    log.info("▶ Stage [%s] starting …", name)
    t0 = time.perf_counter()
    func()
    elapsed = time.perf_counter() - t0
    log.info("✔ Stage [%s] finished in %.2f s", name, elapsed)
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Time-model pipeline orchestrator")
    parser.add_argument("--skip-data", action="store_true", help="Skip Stage 1 (reuse existing parquet)")
    parser.add_argument("--skip-train", action="store_true", help="Skip Stage 2 (reuse existing pickle)")
    parser.add_argument("--validate-only", action="store_true", help="Run Stage 3 only")
    args = parser.parse_args()

    timings: dict[str, float] = {}

    # ── Stage 1: Data Steward ────────────────────────────────────────
    if not args.skip_data and not args.validate_only:
        try:
            from time_model_data_steward import TimeModelDataSteward
            steward = TimeModelDataSteward()
            timings["DataSteward"] = _run_stage("DataSteward", steward.build)
        except Exception:
            log.exception("✘ Stage [DataSteward] failed")
            sys.exit(1)
    else:
        log.info("⏭ Stage [DataSteward] skipped")

    # ── Stage 2: Trainer ─────────────────────────────────────────────
    if not args.skip_train and not args.validate_only:
        try:
            from time_model_trainer import TimeModelTrainer
            trainer = TimeModelTrainer(output_path=STAGING_PKL)
            timings["Trainer"] = _run_stage("Trainer", trainer.train)
        except Exception:
            log.exception("✘ Stage [Trainer] failed")
            sys.exit(1)
    else:
        log.info("⏭ Stage [Trainer] skipped")

    # ── Stage 3: Validator ───────────────────────────────────────────
    # Validate the STAGING artifact when one exists (fresh train, or a
    # leftover from an interrupted run); otherwise re-validate the final pkl.
    staged = os.path.exists(STAGING_PKL)
    try:
        from time_model_validator import TimeModelValidator
        validator = TimeModelValidator(
            model_path=STAGING_PKL if staged else FINAL_PKL,
        )
        timings["Validator"] = _run_stage("Validator", validator.validate)
    except Exception:
        log.exception("✘ Stage [Validator] failed")
        sys.exit(1)

    # ── Persist the validation report (pass or fail) ────────────────
    try:
        report_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "time_model_v4_validation.json",
        )
        validator.save_report(report_path)
    except Exception:
        log.exception("Failed to save validation report (continuing to gate check)")

    # ── Gate check + staged promotion / quarantine ───────────────────
    if validator.passes_all_gates():
        log.info("✅ All quality gates passed")
        if staged:
            os.replace(STAGING_PKL, FINAL_PKL)
            log.info("⬆ Promoted %s → %s", STAGING_PKL, FINAL_PKL)
            if os.path.exists(STAGING_META):
                os.replace(STAGING_META, FINAL_META)
                log.info("⬆ Promoted %s → %s", STAGING_META, FINAL_META)
            else:
                log.warning("Staging meta sidecar %s missing — final sidecar "
                            "not written", STAGING_META)
    else:
        failed = validator.failed_gates() if hasattr(validator, "failed_gates") else ["(unknown)"]
        log.error("❌ Quality gates FAILED: %s", ", ".join(failed))
        if staged:
            os.replace(STAGING_PKL, REJECTED_PKL)
            log.error("🗑 Quarantined staging artifact → %s (serving will NOT "
                      "see a time_model_v4.pkl from this run)", REJECTED_PKL)
            if os.path.exists(STAGING_META):
                os.remove(STAGING_META)
                log.error("🗑 Deleted staging meta sidecar %s", STAGING_META)
        else:
            log.error("Existing %s failed re-validation — left in place "
                      "(promoted by an earlier passing run); investigate.", FINAL_PKL)
        sys.exit(1)

    # ── Summary ──────────────────────────────────────────────────────
    log.info("─── Pipeline Summary ───")
    for stage, secs in timings.items():
        log.info("  %-15s %8.2f s", stage, secs)
    log.info("  %-15s %8.2f s", "TOTAL", sum(timings.values()))


if __name__ == "__main__":
    main()
