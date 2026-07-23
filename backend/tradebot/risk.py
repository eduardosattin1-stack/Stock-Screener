"""Risk gates — every new entry must pass ALL gates; any failure blocks with a reason.

Gates are pure functions over explicit state so tests can hit each one. The
kill switch is honored in two places (GCS blob for the supervisor / remote halt,
local file for Bruno standing at the gateway PC) and is checked FIRST.
"""
import logging
import os
from datetime import date

from .config import BotConfig
from .signals import health_status

log = logging.getLogger("tradebot.risk")


def slot_size_usd(equity: float, cfg: BotConfig, today: str = "") -> float:
    """Equity/max_slots per NEW entry, clamped to [floor, cap]. 0 = don't trade.

    Open positions are never resized; slots compound with the book.
    """
    slots = cfg.max_slots
    if cfg.ramp_until and (today or date.today().isoformat()) <= cfg.ramp_until:
        slots = cfg.ramp_slots
    raw = equity / cfg.max_slots  # size off the FULL slot count even during ramp
    if raw < cfg.slot_floor_usd:
        return 0.0
    return min(raw, cfg.slot_cap_usd)


def max_open_slots(cfg: BotConfig, today: str = "") -> int:
    if cfg.ramp_until and (today or date.today().isoformat()) <= cfg.ramp_until:
        return cfg.ramp_slots
    return cfg.max_slots


def is_halted(cfg: BotConfig, gcs) -> bool:
    """Kill switch — GCS HALT blob (supervisor / remote) OR local HALT file
    (Bruno at the gateway PC). Checked first everywhere; the --watch loop skips
    every phase when this is true."""
    if gcs["read_text"](cfg.halt_path, "") != "":
        return True
    return os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       cfg.local_halt_file))


def calibration_validated(summary: dict, cfg: BotConfig) -> tuple:
    """(ok, detail) — has at least one window run to a TERMINAL outcome yet?

    Until it has, HEALTHY is certified on fully-censored, touch-only data: z is
    structurally pinned positive and the health gate cannot fail (supervisor
    blocker F1, 2026-07-17). This is a GO-LIVE readiness question, not a
    rehearsal-integrity one — real terminal proof matters before risking real
    money, but it says nothing about whether the paper rehearsal should keep
    running (it should: [[feedback_commit_to_ux_revamp_only]]-style scope
    creep is exactly what got HALT #5 wrong the first time — corrected
    2026-07-23 after halting new dry-run entries on this same check turned out
    to be the identical category error the supervisor made). Called ONLY from
    run_bot's LIVE-startup refusal, never from entry_gates."""
    try:
        from .config import HORIZON_LABEL
        cyc = summary["horizons"][HORIZON_LABEL[cfg.regime]]["cycle"]
        ok = int(cyc["n_matured"]) > int(cyc["n_touched"])
        terminals = int(cyc["n_matured"]) - int(cyc["n_touched"])
        return ok, (f"{terminals} terminal outcome(s)" if ok
                    else "0 terminal outcomes yet — health gate has no teeth")
    except (KeyError, TypeError, ValueError):
        return False, "summary missing cycle block"


def entry_gates(cfg: BotConfig, gcs, state: dict, summary: dict,
                equity: float, day_start_equity: float,
                n_open: int, n_pending: int, today: str = "",
                check_sizing: bool = True) -> list:
    """[(gate, ok, detail)] — all must be ok before ANY entry order is placed,
    in EITHER mode (dry-run or live) — this is the rehearsal-integrity path,
    testing the same logic the live bot would run. Live-readiness-only concerns
    (is the safety gate itself proven yet?) do NOT belong here — see
    calibration_validated(), enforced instead at LIVE startup in run_bot.py.

    check_sizing=False for the morning pass: quantities were fixed at --stage,
    so the morning only re-checks kill-switch / health / slots / daily-loss."""
    gates = []

    halted = is_halted(cfg, gcs)
    gates.append(("kill-switch", not halted, "HALT present" if halted else "clear"))

    hs = health_status(summary, cfg)
    gates.append(("calibration-health", hs == cfg.require_health, f"{cfg.regime}={hs}"))

    slots = max_open_slots(cfg, today)
    free = slots - n_open - n_pending
    gates.append(("slots", free > 0, f"open={n_open} pending={n_pending} max={slots}"))

    if day_start_equity and day_start_equity > 0:
        dd = equity / day_start_equity - 1.0
        ok = dd > -cfg.daily_loss_halt_frac
        gates.append(("daily-loss", ok, f"{dd:+.2%} vs -{cfg.daily_loss_halt_frac:.0%} halt"))
    else:
        gates.append(("daily-loss", True, "no day-start equity yet"))

    if check_sizing:
        size = slot_size_usd(equity, cfg, today)
        gates.append(("slot-size", size > 0, f"${size:,.0f}" if size else
                      f"equity/{cfg.max_slots} below ${cfg.slot_floor_usd:,.0f} floor"))

    for name, ok, detail in gates:
        if not ok:
            log.warning(f"entry gate BLOCKED [{name}]: {detail}")
    return gates


def corp_action_guard(scan_price: float, live_quote: float, cfg: BotConfig) -> bool:
    """True = safe. Blocks the DD/MQ class: scan price vs live quote divergence
    means a split/spinoff/symbol-reuse — do not trade it, flag to supervisor."""
    if not scan_price or not live_quote or scan_price <= 0 or live_quote <= 0:
        return False
    return abs(live_quote / scan_price - 1.0) <= cfg.corp_action_max_dev


def all_pass(gates: list) -> bool:
    return all(ok for _, ok, _ in gates)
