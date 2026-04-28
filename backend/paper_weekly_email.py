#!/usr/bin/env python3
"""
paper_weekly_email.py
=====================
Friday 07:30 CET — single weekly email covering BOTH paper-tracked strategies:

  BORING:    top-10 SP500 Pio≥7 by ps_ratio, 26w hold
  COMPOSITE: top-10 SP500 by composite score, weekly rotation

Reads from GCS:
  performance/strategy_history_boring.json
  performance/strategy_history_composite.json
  scans/latest_sp500.json

Schedule: Cloud Scheduler Friday 07:30 CET → after both runners complete

Usage:
  export SMTP_USER=... SMTP_PASS=... EMAIL_TO=...
  python3 paper_weekly_email.py
"""
import logging
import os
import smtplib
from datetime import date
from email.mime.text import MIMEText

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paper_email")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
BORING_PATH = "performance/strategy_history_boring.json"
COMPOSITE_PATH = "performance/strategy_history_composite.json"
LATEST_SCAN_PATH = "scans/latest_sp500.json"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)


def gcs_read(path: str, default=None):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"GCS read {path}: {e}")
    return default


def fmt_pct(v, dp=2):
    if v is None: return "n/a"
    return f"{v:+.{dp}f}%"


def fmt_pp(v, dp=2):
    if v is None: return "n/a"
    return f"{v:+.{dp}f}pp"


# ─────────────────────────────────────────────────────────────────────────
# BORING sections
# ─────────────────────────────────────────────────────────────────────────
def boring_status(history: dict) -> tuple[str, str]:
    if not history:
        return "NO DATA", "  No BORING history yet.\n"
    open_basket = history.get("open_basket")
    weeks = history.get("weeks", [])

    if not open_basket and not weeks:
        return "FIRST RUN", "  BORING: no basket yet. Awaiting strategy runner.\n"

    if not open_basket and weeks:
        last = weeks[-1]
        return "BETWEEN", (
            f"  BORING: last cycle closed {last['exit_date']} — "
            f"basket {fmt_pct(last['basket_return_pct'])} vs "
            f"SPY {fmt_pct(last['spy_return_pct'])} "
            f"(alpha {fmt_pp(last['alpha_pp'])}). Awaiting next basket open.\n"
        )

    inception = date.fromisoformat(open_basket["inception_date"])
    exit_d = date.fromisoformat(open_basket["scheduled_exit_date"])
    days_held = (date.today() - inception).days
    weeks_remaining = max(0, (exit_d - date.today()).days // 7)
    marks = open_basket.get("weekly_marks") or []
    last_mark = marks[-1] if marks else None

    if (exit_d - date.today()).days <= 0:
        return "REBALANCE DUE", (
            f"  ⚠ BORING: 26-week hold reached. Inception {open_basket['inception_date']}.\n"
            f"  Strategy runner should close & open new basket today.\n"
        )

    line = (f"  BORING: open since {open_basket['inception_date']} "
            f"(day {days_held}/182, {weeks_remaining}w remaining)")
    if last_mark:
        line += (f" — basket {fmt_pct(last_mark['basket_return_pct'])}, "
                 f"SPY {fmt_pct(last_mark['spy_return_pct'])}, "
                 f"alpha {fmt_pp(last_mark['alpha_pp'])}")
    return "OPEN", line + "\n"


def boring_basket(history: dict) -> str:
    if not history:
        return "  (no data)\n"
    ob = history.get("open_basket")
    if not ob:
        return "  (no open basket)\n"
    basket = ob.get("basket", [])
    if not basket:
        return "  (basket empty)\n"
    marks = ob.get("weekly_marks") or []
    last = marks[-1] if marks else None
    days_held = (date.today() - date.fromisoformat(ob["inception_date"])).days

    lines = [
        f"  Inception: {ob['inception_date']}  ·  Day {days_held}/182  ·  "
        f"Equal-weight (10% per name)",
        "",
        f"    {'#':<3} {'Symbol':<8} {'Entry':>10} {'Pio':>4} {'P/S':>7}",
        f"    {'-'*3} {'-'*8} {'-'*10} {'-'*4} {'-'*7}",
    ]
    for i, p in enumerate(basket, 1):
        lines.append(
            f"    {i:<3} {p['symbol']:<8} ${p['entry_price']:>9.2f} "
            f"{p['piotroski_at_entry']:>4} {p['ps_ratio_at_entry']:>7.2f}"
        )
    if last:
        lines.extend([
            "",
            f"  Last mark ({last['date']}): basket {fmt_pct(last['basket_return_pct'])} · "
            f"SPY {fmt_pct(last['spy_return_pct'])} · alpha {fmt_pp(last['alpha_pp'])}",
        ])
    return "\n".join(lines) + "\n"


def boring_perf(history: dict) -> str:
    if not history:
        return "  (no data)\n"
    summary = history.get("summary")
    weeks = history.get("weeks", [])
    if not summary or not weeks:
        return "  No closed cycles yet. First closed cycle in ~26 weeks.\n"
    inception = history.get("inception_date") or "?"
    lines = [
        f"  Since inception ({inception}):",
        f"    Cycles closed:        {summary['weeks_closed']}",
        f"    Cum strategy return:  {fmt_pct(summary['cum_strategy_return_pct'])}",
        f"    Cum SPY return:       {fmt_pct(summary['cum_spy_return_pct'])}",
        f"    Cum alpha:            {fmt_pp(summary['cum_alpha_pp'])}",
        f"    Annualized return:    {fmt_pct(summary['annualized_return_pct'])}",
        f"    Annualized alpha:     {fmt_pp(summary['annualized_alpha_pp'])}",
        f"    Win rate vs SPY:      {summary['win_rate']*100:.0f}% "
        f"({summary['weeks_positive_alpha']}/{summary['weeks_closed']})",
    ]
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────
# COMPOSITE sections
# ─────────────────────────────────────────────────────────────────────────
def composite_status(history: dict) -> tuple[str, str]:
    if not history:
        return "NO DATA", "  No COMPOSITE history yet.\n"
    inception = history.get("inception_date")
    if not inception:
        return "FIRST RUN", "  COMPOSITE: no basket yet. Awaiting strategy runner.\n"

    summary = history.get("summary") or {}
    weekly_marks = history.get("weekly_marks", [])
    last_mark = weekly_marks[-1] if weekly_marks else None
    rotations = history.get("rotations", [])
    days_since = (date.today() - date.fromisoformat(inception)).days

    line = (f"  COMPOSITE: open since {inception} "
            f"(day {days_since}, {len(rotations)} rotations, "
            f"{summary.get('n_positions_closed', 0)} closed)")
    if last_mark:
        line += (f" — basket avg {fmt_pct(last_mark['basket_avg_return_pct'])}, "
                 f"SPY {fmt_pct(last_mark['spy_return_pct'])}, "
                 f"alpha {fmt_pp(last_mark['alpha_pp'])}")
    return "OPEN", line + "\n"


def composite_basket(history: dict) -> str:
    if not history:
        return "  (no data)\n"
    current = history.get("current_basket", [])
    if not current:
        return "  (no current basket)\n"

    lines = [
        f"  Inception: {history.get('inception_date', '?')}  ·  "
        f"Equal-weight (10% per name)  ·  Weekly rotation",
        "",
        f"    {'#':<3} {'Symbol':<8} {'Entry':>10} {'Last':>10} "
        f"{'Return':>10} {'Days':>5} {'Comp':>6}",
        f"    {'-'*3} {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*5} {'-'*6}",
    ]
    for i, p in enumerate(current, 1):
        days_held = (date.today() - date.fromisoformat(p["entry_date"])).days
        ret = p.get("return_pct", 0)
        lines.append(
            f"    {i:<3} {p['symbol']:<8} ${p['entry_price']:>9.2f} "
            f"${p.get('last_price', p['entry_price']):>9.2f} "
            f"{ret:>+9.2f}% {days_held:>4}d "
            f"{p.get('composite_at_entry', 0):>6.3f}"
        )
    return "\n".join(lines) + "\n"


def composite_actions(history: dict) -> str:
    """Show this week's rotations if any."""
    if not history:
        return "  (no data)\n"
    rotations = history.get("rotations", [])
    if not rotations:
        return "  No rotations yet.\n"
    last = rotations[-1]
    today = date.today().isoformat()
    if last["date"] != today:
        return f"  No rotations this week. Last rotation: {last['date']}\n"

    lines = [f"  ROTATIONS THIS WEEK ({last['date']}):"]
    if last.get("removed"):
        lines.append(f"    Removed ({last['n_removed']}):")
        for r in last["removed"]:
            lines.append(
                f"      ✗ {r['symbol']:<6} {fmt_pct(r['return_pct'])} "
                f"({r['days_held']}d held, ${r['entry_price']:.2f} → ${r['exit_price']:.2f})"
            )
    if last.get("added"):
        lines.append(f"    Added ({last['n_added']}):")
        for a in last["added"]:
            lines.append(
                f"      + {a['symbol']:<6} entry ${a['entry_price']:.2f} "
                f"(comp {a.get('composite_at_entry', 0):.3f})"
            )
    return "\n".join(lines) + "\n"


def composite_perf(history: dict) -> str:
    if not history:
        return "  (no data)\n"
    summary = history.get("summary")
    if not summary or summary.get("weeks_tracked", 0) == 0:
        return "  No tracking data yet.\n"
    inception = history.get("inception_date") or "?"
    lines = [
        f"  Since inception ({inception}):",
        f"    Weeks tracked:           {summary['weeks_tracked']}",
        f"    Rotations executed:      {summary['n_rotations']}",
        f"    Positions closed:        {summary['n_positions_closed']}",
        f"    Realized avg return:     {fmt_pct(summary['realized_avg_return_pct'])}  "
        f"(win rate: {summary['realized_win_rate']*100:.0f}%)",
        f"    Open positions avg:      {fmt_pct(summary['open_avg_return_pct'])}",
        f"    Cum basket return:       {fmt_pct(summary['cum_basket_return_pct'])}",
        f"    Cum SPY return:          {fmt_pct(summary['cum_spy_return_pct'])}",
        f"    Cum alpha vs SPY:        {fmt_pp(summary['cum_alpha_pp'])}",
        f"    Annualized return:       {fmt_pct(summary['annualized_return_pct'])}",
        f"    Annualized alpha:        {fmt_pp(summary['annualized_alpha_pp'])}",
    ]
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────
# Build email
# ─────────────────────────────────────────────────────────────────────────
def build_email() -> tuple[str, str]:
    today = date.today().isoformat()
    boring = gcs_read(BORING_PATH)
    composite = gcs_read(COMPOSITE_PATH)

    boring_lbl, _ = boring_status(boring) if boring else ("NO DATA", "")
    composite_lbl, _ = composite_status(composite) if composite else ("NO DATA", "")

    if boring_lbl == "REBALANCE DUE":
        subject_prefix = "🔔 BORING REBALANCE"
    elif "FIRST RUN" in (boring_lbl, composite_lbl):
        subject_prefix = "🚀 FIRST RUN"
    else:
        subject_prefix = "📊 PAPER TRACK"
    subject = f"{subject_prefix} — CB Screener — {today}"

    divider = "═" * 78
    sub_divider = "─" * 78

    body_parts = [
        divider,
        f"  CB SCREENER — PAPER TRACKING — {today}",
        f"  Tracking 2 strategies in parallel (paper, no capital)",
        divider,
        "",
        "┃ STATUS",
        sub_divider,
        (boring_status(boring)[1] if boring else "  No BORING history\n").rstrip(),
        (composite_status(composite)[1] if composite else "  No COMPOSITE history\n").rstrip(),
        "",
        divider,
        "  BORING — top-10 SP500 Pio≥7 by ps_ratio, 26w hold, equal-weight",
        divider,
        "",
        "┃ Current basket",
        sub_divider,
        boring_basket(boring) if boring else "  (no data)\n",
        "",
        "┃ Performance since inception",
        sub_divider,
        boring_perf(boring) if boring else "  (no data)\n",
        "",
        divider,
        "  COMPOSITE — top-10 SP500 by composite, weekly rotation, equal-weight",
        divider,
        "",
        "┃ This week's actions",
        sub_divider,
        composite_actions(composite) if composite else "  (no data)\n",
        "",
        "┃ Current basket",
        sub_divider,
        composite_basket(composite) if composite else "  (no data)\n",
        "",
        "┃ Performance since inception",
        sub_divider,
        composite_perf(composite) if composite else "  (no data)\n",
        "",
        divider,
        "  METHODOLOGY",
        divider,
        "  Both strategies are paper-tracked using FMP data; no capital deployed.",
        "",
        "  BORING:    Backtest expected ~25-30% CAGR · ~7-15pp alpha · MDD <-10%",
        "             Walk-forward OOS: Sharpe 1.75, alpha +7.1pp, MDD -0.8%",
        "             Risk: defensive bias, low MDD, lower upside in bull markets",
        "",
        "  COMPOSITE: No backtest reference (composite top-10 untested OOS).",
        "             Tracked for comparison vs BORING. Higher turnover.",
        "             Treat results as observational, not validated.",
        "",
        "  Kill-switches (review at quarterly check):",
        "    • Live MDD > -20% → halt and reassess",
        "    • Two consecutive cycles negative alpha → halt",
        "    • Single position -50%+ in <30d → investigate (data error?)",
        "",
        divider,
        f"  https://screener.carbonbridge.nl/performance",
        f"  Generated by paper_weekly_email.py",
        f"  gs://{GCS_BUCKET}/{BORING_PATH}",
        f"  gs://{GCS_BUCKET}/{COMPOSITE_PATH}",
        divider,
    ]

    return subject, "\n".join(body_parts)


def send_email(subject: str, body: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        log.info("No SMTP credentials — printing email body only:\n")
        print(f"Subject: {subject}\n")
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
        log.info(f"Sent to {EMAIL_TO}")
        return True
    except Exception as e:
        log.error(f"Email failed: {e}")
        return False


def main():
    subject, body = build_email()
    log.info(f"Subject: {subject}")
    send_email(subject, body)


if __name__ == "__main__":
    main() 
