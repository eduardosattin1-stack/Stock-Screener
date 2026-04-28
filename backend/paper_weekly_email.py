#!/usr/bin/env python3
"""
paper_weekly_email.py
=====================
Friday 07:00 CET — single weekly email replacing weekly_report.py and
monitor_v7.py combined.

Reads strategy_history_boring.json + latest_sp500.json from GCS. Builds
plain-text email with five sections:

  1. WEEKLY STATUS  — what happened this Friday (open / mark / close / rebalance)
  2. CURRENT BASKET — 10 stocks, entry/current/PnL, days held, exit date
  3. PERFORMANCE    — cumulative + annualized vs SPY, since inception
  4. UNIVERSE WATCH — top 10 candidates by ps_ratio (regardless of action)
  5. METHODOLOGY    — strategy version, kill-switches

Schedule:
  Cloud Scheduler Friday 07:30 CET → runs after paper_strategy_runner

Usage:
  export SMTP_USER=... SMTP_PASS=... EMAIL_TO=...
  python3 paper_weekly_email.py
"""
import logging
import os
import smtplib
from datetime import date, datetime
from email.mime.text import MIMEText

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("boring_email")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
HISTORY_PATH = "performance/strategy_history_boring.json"
LATEST_SCAN_PATH = "scans/latest_sp500.json"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

STRATEGY_VERSION = "boring-v1.0-2026-04-28"
PIOTROSKI_MIN = 7
TOP_N = 10
HOLD_WEEKS = 26


def gcs_read(path: str, default=None):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"GCS read {path}: {e}")
    return default


# ─────────────────────────────────────────────────────────────────────────
# Section builders
# ─────────────────────────────────────────────────────────────────────────
def fmt_pct(v, decimals=2):
    if v is None: return "n/a"
    return f"{v:+.{decimals}f}%"


def fmt_pp(v, decimals=2):
    if v is None: return "n/a"
    return f"{v:+.{decimals}f}pp"


def section_status(history: dict) -> tuple[str, str]:
    """Returns (status_label, status_block). status_label drives subject line."""
    today = date.today().isoformat()
    open_basket = history.get("open_basket")
    weeks = history.get("weeks", [])

    if not open_basket and not weeks:
        return "FIRST RUN", (
            "  No basket yet. The strategy runner should fire this morning\n"
            "  with this Friday's scan and open the inaugural basket.\n"
        )

    if not open_basket and weeks:
        last = weeks[-1]
        return "BETWEEN CYCLES", (
            f"  Last cycle closed {last['exit_date']} — "
            f"basket {fmt_pct(last['basket_return_pct'])} vs "
            f"SPY {fmt_pct(last['spy_return_pct'])} "
            f"(alpha {fmt_pp(last['alpha_pp'])}).\n"
            f"  Awaiting next basket open.\n"
        )

    # Has open basket
    inception = date.fromisoformat(open_basket["inception_date"])
    exit_date = date.fromisoformat(open_basket["scheduled_exit_date"])
    days_held = (date.today() - inception).days
    days_remaining = (exit_date - date.today()).days
    weeks_held = days_held // 7
    weeks_remaining = max(0, days_remaining // 7)

    marks = open_basket.get("weekly_marks", [])
    last_mark = marks[-1] if marks else None

    if days_remaining <= 0:
        return "REBALANCE DUE", (
            f"  ⚠ The current basket has reached its 26-week hold.\n"
            f"  Inception: {open_basket['inception_date']} "
            f"  Today: {today}  Days held: {days_held}\n"
            f"  Strategy runner should close this cycle and open a new basket.\n"
        )

    if not last_mark:
        return "BASKET OPEN", (
            f"  Basket open from {open_basket['inception_date']}.\n"
            f"  Day {days_held} of {HOLD_WEEKS * 7} ({weeks_held}w / "
            f"{weeks_remaining}w remaining).\n"
            f"  No mark-to-market data yet (first mid-hold mark coming).\n"
        )

    return "BASKET OPEN", (
        f"  Basket open from {open_basket['inception_date']} "
        f"→ scheduled exit {open_basket['scheduled_exit_date']}.\n"
        f"  Day {days_held}/{HOLD_WEEKS * 7}  ·  "
        f"{weeks_held}w held  ·  {weeks_remaining}w remaining.\n"
        f"  Latest mark ({last_mark['date']}): "
        f"basket {fmt_pct(last_mark['basket_return_pct'])} · "
        f"SPY {fmt_pct(last_mark['spy_return_pct'])} · "
        f"alpha {fmt_pp(last_mark['alpha_pp'])}.\n"
    )


def section_basket(history: dict) -> str:
    open_basket = history.get("open_basket")
    if not open_basket:
        return "  (no open basket)\n"

    basket = open_basket.get("basket", [])
    if not basket:
        return "  (basket empty)\n"

    # Match each entry against latest weekly mark for live PnL display
    # If no mark, show entry-only
    marks = open_basket.get("weekly_marks", [])
    last_marked = marks[-1] if marks else None

    inception = open_basket["inception_date"]
    days_held = (date.today() - date.fromisoformat(inception)).days

    lines = [
        f"  Inception: {inception}  ·  Day {days_held}/{HOLD_WEEKS * 7}",
        f"  Equal-weighted ({100 // TOP_N}% per name)",
        "",
        f"    {'#':<3} {'Symbol':<8} {'Entry':>10} {'Pio':>4} {'P/S':>7}",
        f"    {'-'*3} {'-'*8} {'-'*10} {'-'*4} {'-'*7}",
    ]
    for i, p in enumerate(basket, 1):
        lines.append(
            f"    {i:<3} {p['symbol']:<8} ${p['entry_price']:>9.2f} "
            f"{p['piotroski_at_entry']:>4} {p['ps_ratio_at_entry']:>7.2f}"
        )

    if last_marked:
        lines.extend([
            "",
            f"  Last MTM ({last_marked['date']}, day {last_marked['days_held']}):",
            f"    Basket return:  {fmt_pct(last_marked['basket_return_pct'])}",
            f"    SPY return:     {fmt_pct(last_marked['spy_return_pct'])}",
            f"    Alpha:          {fmt_pp(last_marked['alpha_pp'])}",
        ])

    return "\n".join(lines) + "\n"


def section_performance(history: dict) -> str:
    summary = history.get("summary")
    weeks = history.get("weeks", [])

    if not summary or not weeks:
        return (
            "  No closed cycles yet. Performance will populate after the\n"
            f"  first 26-week hold completes (~6 months from inception).\n"
        )

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
        f"({summary['weeks_positive_alpha']}/{summary['weeks_closed']} cycles)",
        f"    Best/worst alpha:     {fmt_pp(summary['best_week_alpha_pp'])} / "
        f"{fmt_pp(summary['worst_week_alpha_pp'])}",
        "",
        "  Recent cycles:",
    ]
    for w in weeks[-3:]:
        lines.append(
            f"    {w['entry_date']} → {w['exit_date']}: "
            f"basket {fmt_pct(w['basket_return_pct'])} · "
            f"SPY {fmt_pct(w['spy_return_pct'])} · "
            f"alpha {fmt_pp(w['alpha_pp'])} ({w['n_positions']} pos)"
        )
    return "\n".join(lines) + "\n"


def section_universe(scan: dict) -> str:
    """Top 10 Pio≥7 candidates by composite score (a transparency snapshot).

    NOTE: the runner uses ps_ratio for actual basket selection (fetched from
    FMP at runtime since the scan doesn't emit it). For the weekly email we
    show by composite — what's already in the scan — to avoid 374 FMP calls
    just to render an email section. The actual basket in section 2 reflects
    the true ps_ratio-based selection.
    """
    if not scan or not scan.get("stocks"):
        return "  (no scan data this week)\n"

    candidates = []
    for s in scan["stocks"]:
        pio = s.get("piotroski") or (s.get("factors") or {}).get("piotroski")
        if pio is None or pio < PIOTROSKI_MIN: continue
        candidates.append({
            "symbol": s.get("symbol", "").upper(),
            "pio": int(pio),
            "price": s.get("price"),
            "composite": s.get("composite") or 0,
        })

    if not candidates:
        return "  (no qualifying candidates this week)\n"

    candidates.sort(key=lambda x: -x["composite"])
    top = candidates[:TOP_N]
    lines = [
        f"  Top-{TOP_N} Pio≥{PIOTROSKI_MIN} candidates by COMPOSITE this week",
        f"  (the strategy ranks by ps_ratio — see basket above for actual picks)",
        "",
        f"    {'#':<3} {'Symbol':<8} {'Price':>10} {'Pio':>4} {'Composite':>10}",
        f"    {'-'*3} {'-'*8} {'-'*10} {'-'*4} {'-'*10}",
    ]
    for i, c in enumerate(top, 1):
        price_str = f"${c['price']:.2f}" if c["price"] else "n/a"
        lines.append(f"    {i:<3} {c['symbol']:<8} {price_str:>10} "
                     f"{c['pio']:>4} {c['composite']:>10.3f}")

    note = (f"\n  Total qualifying universe: {len(candidates)} stocks "
            f"(Pio≥{PIOTROSKI_MIN})")
    return "\n".join(lines) + note + "\n"


# ─────────────────────────────────────────────────────────────────────────
# Build email
# ─────────────────────────────────────────────────────────────────────────
def build_email() -> tuple[str, str]:
    today = date.today().isoformat()
    history = gcs_read(HISTORY_PATH) or {}
    scan = gcs_read(LATEST_SCAN_PATH) or {}

    status_label, status_block = section_status(history)
    basket_block = section_basket(history)
    perf_block = section_performance(history)
    universe_block = section_universe(scan)

    if status_label == "REBALANCE DUE":
        subject_prefix = "🔔 REBALANCE"
    elif status_label == "FIRST RUN":
        subject_prefix = "🚀 FIRST BASKET"
    elif status_label == "BETWEEN CYCLES":
        subject_prefix = "⏳ BETWEEN"
    else:
        subject_prefix = "📊 BORING"
    subject = f"{subject_prefix} — CB Screener — {today}"

    divider = "═" * 78
    sub_divider = "─" * 78

    body_parts = [
        divider,
        f"  CB SCREENER — BORING STRATEGY — {today}",
        f"  ps_ratio top-{TOP_N} | SP500 Pio≥{PIOTROSKI_MIN} | "
        f"{HOLD_WEEKS}w hold | equal-weight",
        f"  Strategy version: {STRATEGY_VERSION}",
        divider,
        "",
        "┃ 1. STATUS",
        sub_divider,
        status_block,
        "",
        "┃ 2. CURRENT BASKET",
        sub_divider,
        basket_block,
        "",
        "┃ 3. PERFORMANCE SINCE INCEPTION",
        sub_divider,
        perf_block,
        "",
        "┃ 4. UNIVERSE WATCH (this week's top candidates, transparency)",
        sub_divider,
        universe_block,
        "",
        "┃ 5. METHODOLOGY & KILL-SWITCHES",
        sub_divider,
        f"  Strategy: select stocks from S&P 500 with Piotroski F-score ≥ "
        f"{PIOTROSKI_MIN};",
        f"  rank by P/S ascending; buy top {TOP_N} equal-weight; hold "
        f"{HOLD_WEEKS} weeks; rebalance.",
        "",
        "  Backtest expected: ~25-30% CAGR · ~7-15pp alpha vs SPY · MDD <-10%",
        "  Walk-forward (2024-2026 OOS): Sharpe 1.75, alpha +7.1pp, MDD -0.8%",
        "",
        "  Kill-switches (review at next 26w close):",
        "    • Live MDD > -20% → halt and reassess",
        "    • Two consecutive cycles with negative alpha vs SPY → halt",
        "    • Any single position -50%+ in <30 days → investigate (data error?)",
        "",
        "  Quarterly review: assess basket overlap, factor stability, regime fit.",
        divider,
        "",
        f"  screener.carbonbridge.nl/performance",
        f"  Generated by paper_weekly_email.py | gs://{GCS_BUCKET}/{HISTORY_PATH}",
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
