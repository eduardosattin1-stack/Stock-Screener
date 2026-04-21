#!/usr/bin/env python3
"""
Weekly Report with Action List — CB Screener v7.2 Phase 1
==========================================================
Produces the Monday 06:00 CET email. Leads with an ACTION LIST so Bruno
knows what to execute in IBKR before markets open, followed by an OPTIONS
OVERLAY CANDIDATES section (speculative, collecting data until July 2026
review), followed by the existing weekly summary.

Reads from GCS:
  rebalance/latest.json          (close X, open Y from rebalance_engine.py)
  options/latest_suggestions.json (Tradier spread candidates)
  latest_sp500.json              (top picks for the weekly summary)
  portfolio/state.json           (current positions)

Deploy: Cloud Run Job triggered by Cloud Scheduler Mon 06:00 CET
"""
import os, json, logging, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

# Strategy constants (also exported from rebalance_engine for consistency)
try:
    from rebalance_engine import (
        read_latest_rebalance,
        TARGET_PORTFOLIO_SIZE, COMPOSITE_FLOOR,
        STOP_LOSS_PCT, TAKE_PROFIT_PCT, TIME_STOP_DAYS,
    )
    from tradier_options import read_latest_suggestions
except Exception as e:
    logging.warning(f"Imports failed: {e} — running in reduced mode")
    read_latest_rebalance = lambda: {}
    read_latest_suggestions = lambda: {}
    TARGET_PORTFOLIO_SIZE, COMPOSITE_FLOOR = 5, 0.80
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, TIME_STOP_DAYS = -0.12, 0.20, 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weekly_report")

GCS_BUCKET = "screener-signals-carbonbridge"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)


def gcs_read(path, default=None):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return default if default is not None else {}


# ---------------------------------------------------------------------------
# Action list — the headline section Bruno actually acts on
# ---------------------------------------------------------------------------
def format_action_list(rebalance: dict) -> str:
    if not rebalance or not rebalance.get("summary", {}).get("actions_required"):
        return (
            "  ✓ NO ACTION REQUIRED this week.\n"
            f"  Holding {rebalance.get('summary', {}).get('positions_after_close', 0)}/{TARGET_PORTFOLIO_SIZE} positions.\n"
            "  All stops, targets, and time-limits intact.\n"
        )

    lines = []
    summary = rebalance.get("summary", {})
    closes = rebalance.get("closes", [])
    opens = rebalance.get("opens", [])

    lines.append(f"  >>> ACTION REQUIRED: {len(closes)} close(s), {len(opens)} open(s) <<<\n")

    if closes:
        lines.append(f"  ━━━ CLOSE ({len(closes)}) ━━━")
        for c in closes:
            rule = c["exit_rule"]
            emoji = {"STOP_LOSS": "🔴", "TAKE_PROFIT": "🟢", "TIME_STOP": "🟡"}.get(rule, "•")
            lines.append(
                f"  {emoji} SELL {c['symbol']} at market  ({c['pnl_pct_display']}, "
                f"{c['days_held']}d held)"
            )
            lines.append(
                f"     entry ${c['entry_price']:.2f} → now ${c['exit_price']:.2f}  "
                f"reason: {c['reason']}"
            )
        lines.append("")

    if opens:
        lines.append(f"  ━━━ OPEN ({len(opens)}) — equal weight, {100//TARGET_PORTFOLIO_SIZE}% each ━━━")
        for o in opens:
            lines.append(
                f"  🆕 BUY  {o['symbol']}  composite {o['composite']:.3f}  "
                f"({o.get('classification', '')} · {o.get('signal', '')})"
            )
            lines.append(
                f"     entry ${o['entry_price']:.2f}  "
                f"STOP ${o['stop_loss_price']:.2f} (-12%)  "
                f"TARGET ${o['take_profit_price']:.2f} (+20%)  "
                f"TIME {o['time_stop_date']}"
            )
            if o.get("hit_prob"):
                lines.append(
                    f"     ML P(+10% in 60d): {o['hit_prob']*100:.0f}%  "
                    f"upside to target: {o.get('upside_pct', 0):.0f}%"
                )
        lines.append("")

    cash = summary.get("cash_slots_remaining", 0)
    if cash > 0:
        qual = summary.get("qualifying_in_universe", 0)
        lines.append(
            f"  💰 CASH: holding {cash} slot(s) empty — only {qual} stocks "
            f"cleared composite ≥ {COMPOSITE_FLOOR:.2f} this week."
        )

    lines.append("\n  IBKR bracket order template for each OPEN:")
    lines.append("    Parent: BUY MKT (or LMT near shown entry price)")
    lines.append("    Child 1: SELL STP at STOP price (attached)")
    lines.append("    Child 2: SELL LMT at TARGET price (OCO with child 1)")
    lines.append("    Manual: set calendar reminder for TIME date\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Options overlay section
# ---------------------------------------------------------------------------
def format_options_section(options_report: dict) -> str:
    if not options_report:
        return "  (Options layer not configured — set TRADIER_TOKEN to enable.)\n"

    if options_report.get("error"):
        return f"  ⚠ {options_report['error']}\n"

    suggestions = options_report.get("suggestions", [])
    gated = options_report.get("gated", [])
    gates = options_report.get("entry_gates", {})

    if not suggestions and not gated:
        return "  No candidates evaluated this cycle (no new opens met base criteria).\n"

    lines = [
        "  ⚠ SPECULATIVE — accumulating data through July 2026 review.",
        "  Do not size these as primary positions. Sugg. sizing: 1-2% per spread, max 5% total.",
        "",
        f"  Gates: composite ≥ {gates.get('composite_min', 0.85)} · "
        f"p10 ≥ {gates.get('hit_prob_min', 0.65)} · "
        f"IV rank ≤ {gates.get('iv_rank_max', 40)} · "
        f"DTE ~ {gates.get('dte_target', 90)}d",
        "",
    ]

    if suggestions:
        lines.append(f"  ━━━ {len(suggestions)} CANDIDATE SPREAD(S) ━━━")
        for s in suggestions:
            econ = s.get("economics", {})
            iv_str = ""
            if s.get("iv_rank") is not None:
                iv_str = f"  IVR: {s['iv_rank']:.0f} ({s.get('iv_samples', 0)} samples)"
            lines.append(
                f"  📈 {s['symbol']}  spot ${s['spot']:.2f}  "
                f"composite {s['composite']:.2f}  p10 {s['hit_prob']*100:.0f}%{iv_str}"
            )
            lines.append(f"     {s['description']}")
            lines.append(
                f"     Max gain ${econ.get('max_gain_per_contract', 0):.0f}/contract  "
                f"max loss ${econ.get('max_loss_per_contract', 0):.0f}  "
                f"R/R {econ.get('risk_reward', 0):.1f}:1"
            )
            lines.append("")

    if gated:
        lines.append(f"  ━━━ {len(gated)} GATED (did not pass) ━━━")
        for g in gated:
            lines.append(f"  ✕ {g['symbol']}: {g.get('reason', 'unknown')}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Portfolio snapshot
# ---------------------------------------------------------------------------
def format_portfolio_snapshot(rebalance: dict) -> str:
    portfolio = rebalance.get("portfolio_before", [])
    if not portfolio:
        return "  (no open positions)\n"
    lines = [f"  Currently holding {len(portfolio)}/{TARGET_PORTFOLIO_SIZE} positions:"]
    for p in portfolio:
        lines.append(
            f"    {p['symbol']:<8} entry {p.get('entry_date', '?')} "
            f"@ ${p.get('entry_price', 0):.2f}  "
            f"comp_at_entry {p.get('entry_composite', 0):.3f}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Top-of-universe snapshot (for context, not action)
# ---------------------------------------------------------------------------
def format_top_picks_snapshot() -> str:
    scan = gcs_read("latest_sp500.json", {})
    if not scan:
        return "  (no recent sp500 scan available)\n"
    stocks = scan.get("stocks", []) if isinstance(scan, dict) else []
    if not stocks:
        return "  (no recent sp500 scan available)\n"
    stocks_sorted = sorted(stocks, key=lambda s: s.get("composite", 0), reverse=True)
    top10 = stocks_sorted[:10]
    lines = ["  Top-10 SP500+NASDAQ by composite (this week):"]
    for i, s in enumerate(top10, 1):
        lines.append(
            f"    {i:>2}. {s.get('symbol', ''):<8} {s.get('composite', 0):.3f}  "
            f"{s.get('classification', ''):<14} {s.get('signal', ''):<12} "
            f"${s.get('price', 0):.2f}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Build the email
# ---------------------------------------------------------------------------
def build_report() -> tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    rebalance = read_latest_rebalance() or {}
    options = read_latest_suggestions() or {}

    summary = rebalance.get("summary", {})
    has_action = summary.get("actions_required", False)

    subject_prefix = "🔔 ACTION" if has_action else "CB Weekly"
    subject = f"{subject_prefix} — CB Screener — {today}"

    divider = "═" * 78
    sub_divider = "─" * 78

    body_parts = [
        divider,
        f"  CB SCREENER — WEEKLY ACTION REPORT — {today}",
        f"  Strategy: top-{TARGET_PORTFOLIO_SIZE}, composite ≥ {COMPOSITE_FLOOR}, "
        f"SL {STOP_LOSS_PCT*100:+.0f}%, TP {TAKE_PROFIT_PCT*100:+.0f}%, "
        f"time {TIME_STOP_DAYS}d",
        divider,
        "",
        "┃ 1. ACTION LIST (execute at market open)",
        sub_divider,
        format_action_list(rebalance),
        "",
        "┃ 2. CURRENT PORTFOLIO",
        sub_divider,
        format_portfolio_snapshot(rebalance),
        "",
        "┃ 3. OPTIONS OVERLAY CANDIDATES (speculative, Phase 2 assessment)",
        sub_divider,
        format_options_section(options),
        "",
        "┃ 4. UNIVERSE SNAPSHOT (for reference, not for action)",
        sub_divider,
        format_top_picks_snapshot(),
        "",
        divider,
        "  Realistic live expectation: +22-35% CAGR, -20-30% MaxDD, Sharpe 0.8-1.2.",
        "  Kill switches: 3-month negative vs S&P+ | win rate <55% over 30 trades |",
        "  live DD > -25% | avg hold <15d or >50d. Quarterly review Jul 2026.",
        divider,
        "",
        f"  Generated by CB Screener v7.2 | screener.carbonbridge.nl",
        f"  Rebalance date: {rebalance.get('date', 'n/a')} · "
        f"Options date: {options.get('date', 'n/a')}",
        divider,
    ]
    return subject, "\n".join(body_parts)


def send_email(subject: str, body: str):
    if not SMTP_USER or not SMTP_PASS:
        log.info("No SMTP credentials — printing report only")
        print(body)
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log.info(f"Email sent to {EMAIL_TO}")
        return True
    except Exception as e:
        log.warning(f"Email failed: {e}")
        return False


def main():
    subject, body = build_report()
    log.info(f"Subject: {subject}")
    send_email(subject, body)


if __name__ == "__main__":
    main()
