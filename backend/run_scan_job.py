#!/usr/bin/env python3
"""
run_scan_job.py — Cloud Run Job entrypoint for scheduled scans
================================================================
Runs a full screener scan, writes latest_{region}.json to GCS, and
triggers post-scan tracking + rebalance + options suggestions.

Invoked by:
  - gcloud scheduler jobs run (via Cloud Scheduler targeting screener-sp500)
  - Manual GitHub Actions workflow_dispatch

*NOTE: Single-region runner. Set REGIONS_TO_SCAN below to change. Currently: ["global"].*
"""
import os, sys, json, logging
from datetime import datetime, timezone

# Make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_scan_job")


def _scan_date_eastern(ts) -> str | None:
    """YYYY-MM-DD trading date from the payload's scan_date. The screener stamps
    a full tz-aware UTC ISO timestamp (screener_v6.save_scan_to_gcs), so a naive
    [:10] slice rolls to TOMORROW on post-00:00-UTC manual re-runs — which the
    calibration tracker's weekday gate would then mishandle. Convert to
    US/Eastern first. Date-only strings pass through unchanged."""
    s = str(ts or "").strip()
    if not s:
        return None
    if len(s) == 10:  # already a bare YYYY-MM-DD date — no clock to convert
        return s
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10] or None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _load_scan_from_gcs(region: str) -> tuple:
    """Reload tonight's scan payload. The screener writes scans/latest_{region}.json
    (screener_v6.save_scan_to_gcs) — NOT the bucket root. Returns (stocks, scan_date)
    where scan_date is the payload's US/Eastern YYYY-MM-DD date (None if unavailable)."""
    import requests
    url = f"https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest_{region}.json"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                scan_date = _scan_date_eastern(data.get("scan_date"))
                return data.get("stocks", []), scan_date
            if isinstance(data, list):
                return data, None
    except Exception as e:
        log.warning(f"Could not reload scan from GCS: {e}")
    return [], None


def main():
    # HARDCODED REGIONS TO SCAN SEQUENTIALLY
    REGIONS_TO_SCAN = ["global"]
    log.info(f"═══ Scan job starting: processing {len(REGIONS_TO_SCAN)} regions sequentially ═══")

    import screener_v6
    import signal_tracker
    import tradier_options

    for region in REGIONS_TO_SCAN:
        log.info(f"═══ Processing region={region} ═══")

        # ─── 1. Run the screener ───
        try:
            sys.argv = ["screener_v6.py", "--region", region]
            screener_v6.main()
        except Exception as e:
            log.error(f"[{region}] Screener failed: {e}", exc_info=True)
            continue # Skip to the next region if this one crashes

        # ─── 1b. v2 calibration tracker (calibration_tracking/v2/) ───
        # First-class job step with its own log section. Runs in PARALLEL with the
        # legacy signal_tracker call buried inside screener_v6.save_scan_to_gcs —
        # the namespaces are disjoint (hit_rate_tracking/ vs calibration_tracking/v2/).
        # No-ops (logged ERROR) until scratch/build_v2_config.py publishes config.json.
        log.info(f"═══ [{region}] Calibration tracker v2 ═══")
        try:
            import calibration_tracker
            stocks, scan_date = _load_scan_from_gcs(region)
            if stocks:
                counters = calibration_tracker.update_from_scan(stocks, scan_date=scan_date)
                log.info(f"[{region}] Calibration tracker v2 complete: "
                         f"{json.dumps(counters, default=str)}")
            else:
                log.warning(f"[{region}] Calibration tracker v2 skipped: "
                            f"could not reload scans/latest_{region}.json from GCS")
        except Exception as e:
            log.error(f"[{region}] Calibration tracker v2 failed: {e}", exc_info=True)

        # ─── 2. Speculair Debate Pipeline — DISABLED on Cloud Run (2026-06-10) ───
        # The debate runs LOCALLY on Claude Code (weekly speculair-opus-weekly skill), which
        # publishes the authoritative speculair_baskets.json. Running the keyless cross-model
        # engine here every night REWROTE that file (wiped engine=opus-4.8-claude-code-subagents,
        # shrank per_methodology_baskets 203 -> 71 picks). Nightly NAV marking is handled by
        # _mark_speculair_nav() inside screener_v6.main() — no debate needed.
        if os.environ.get("SPECULAIR_DEBATE_CLOUDRUN", "").lower() in ("1", "true", "yes"):
            try:
                from live_debate_engine import debate_and_allocate
                log.info(f"[{region}] Running Speculair debate pipeline...")
                debate_and_allocate(dry_run=False)
                log.info(f"[{region}] Debate pipeline complete.")
            except Exception as e:
                log.error(f"[{region}] Debate pipeline failed: {e}", exc_info=True)
        else:
            log.info(f"[{region}] Speculair debate skipped — runs locally via the weekly Claude Code "
                     f"skill (set SPECULAIR_DEBATE_CLOUDRUN=1 to re-enable here).")

        log.info(f"═══ Completed processing region={region} ═══")

    log.info(f"═══ Consolidated Scan job complete ═══")


if __name__ == "__main__":
    main()
