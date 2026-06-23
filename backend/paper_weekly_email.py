#!/usr/bin/env python3
"""
paper_weekly_email.py
=====================
Friday 07:30 CET — Weekly system email covering:
1. Current Portfolio & Trade Execution
2. Strategy Baskets Performance (Compounder US, Global, Momentum, FA)
3. P(20) Model Calibration & Hit Rates
4. Top 3 New Stock Ideas per category

Reads from GCS:
  portfolio/state.json
  performance/strategy_history_*.json
  hit_rate_tracking/rolling_health.json
  scans/latest_global.json

Schedule: Cloud Scheduler Friday 07:30 CET
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
# SECTIONS
# ─────────────────────────────────────────────────────────────────────────

def section_portfolio(state: dict) -> list[str]:
    lines = ["┃ 1. CURRENT PORTFOLIO & TRADES", "─" * 78]
    if not state:
        return lines + ["  (No portfolio state found)\n"]
        
    positions = state.get("positions", [])
    if positions:
        lines.append(f"  OPEN POSITIONS ({len(positions)}):")
        lines.append(f"    {'Symbol':<8} {'Entry':>10} {'Last':>10} {'PnL':>9} {'Comp':>7}")
        for p in positions:
            sym = p.get('symbol', '')
            entry = float(p.get('entry_price', 0))
            last = float(p.get('last_price', entry))
            pnl = float(p.get('pnl_pct', 0))
            comp = float(p.get('last_composite', p.get('entry_composite', 0)))
            lines.append(f"    {sym:<8} ${entry:>9.2f} ${last:>9.2f} {fmt_pct(pnl,1):>9} {comp:>7.3f}")
    else:
        lines.append("  No open positions.")
    
    history = state.get("history", [])
    if history:
        recent = history[-5:]
        lines.append("")
        lines.append(f"  RECENT EXITS (Last {len(recent)}):")
        for h in recent:
            lines.append(f"    {h.get('date', '?'):<10} {h.get('symbol',''):<8} {fmt_pct(h.get('pnl_pct',0),1):>9} — {h.get('reason','')}")
    lines.append("")
    return lines


def section_strategies() -> list[str]:
    lines = ["┃ 2. PAPER STRATEGY BASKETS", "─" * 78]
    strategies = {
        "COMPOUNDER US": "performance/strategy_history_compounder_us.json",
        "COMPOUNDER GLOBAL": "performance/strategy_history_compounder_global.json",
        "MOMENTUM": "performance/strategy_history_momentum.json",
        "FALLEN ANGEL": "performance/strategy_history_fa.json"
    }
    
    for name, path in strategies.items():
        data = gcs_read(path)
        if not data:
            lines.append(f"  ■ {name}")
            lines.append("    (No data found)")
            lines.append("")
            continue
            
        summary = data.get("summary", {})
        c_ret = summary.get("cum_basket_return_pct")
        c_alpha = summary.get("cum_alpha_pp")
        w_rate = summary.get("realized_win_rate", summary.get("win_rate", 0))
        
        stat = f"Cum Ret: {fmt_pct(c_ret)} | Alpha: {fmt_pp(c_alpha)} | Win Rate: {w_rate*100:.0f}%"
        lines.append(f"  ■ {name}")
        lines.append(f"    {stat}")
        
        rots = data.get("rotations", [])
        if rots:
            last_rot = rots[-1]
            lines.append(f"    Last Rotation ({last_rot.get('date')}): +{last_rot.get('n_added',0)} / -{last_rot.get('n_removed',0)} positions")
        lines.append("")
    return lines


def section_health(health: dict) -> list[str]:
    lines = ["┃ 3. P(20) MODEL HEALTH & CALIBRATION", "─" * 78]
    if not health:
        return lines + ["  (No rolling health data found)\n"]
    
    status = health.get("status", "UNKNOWN")
    d10_hr = health.get("d10_hit_rate", 0)
    d1_hr = health.get("d1_hit_rate", 0)
    d10_n = health.get("d10_n", 0)
    
    lines.append(f"  Status: {status}")
    if "top_cohort_n" in health:
        top_n = health["top_cohort_n"]
        top_obs = health["top_cohort_observed_rate"]
        top_exp = health["top_cohort_expected_rate"]
        lines.append(f"  Top Deciles (D7-D10) Hit Rate: {top_obs*100:.1f}% (Expected: {top_exp*100:.1f}%, n={top_n})")
    else:
        lines.append(f"  D10 Hit Rate: {d10_hr*100:.1f}% (Baseline: 22.3%, n={d10_n})")
        lines.append(f"  D1  Hit Rate: {d1_hr*100:.1f}% (Baseline:  1.1%)")
        
    if health.get("kill_switch_active"):
        lines.append("\n  ⚠ KILL SWITCH ACTIVE: Model degradation detected.")
    lines.append("")
    return lines


def section_ideas(sp500, global_data) -> list[str]:
    lines = ["┃ 4. NEW STOCK IDEAS (TOP 3)", "─" * 78]
    
    def get_top(stocks, key, n=3):
        valid = [s for s in stocks if isinstance(s, dict) and s.get(key) is not None]
        valid.sort(key=lambda x: float(x[key]), reverse=True)
        return valid[:n]

    sp_stocks = sp500.get("stocks", []) if isinstance(sp500, dict) else (sp500 if isinstance(sp500, list) else [])
    gl_stocks = global_data.get("stocks", []) if isinstance(global_data, dict) else (global_data if isinstance(global_data, list) else [])
    
    categories = [
        ("US COMPOUNDERS", sp_stocks, "compounder_score_us"),
        ("GLOBAL COMPOUNDERS", gl_stocks, "compounder_score_global"),
        ("MOMENTUM", sp_stocks, "composite_momentum"),
        ("FALLEN ANGELS", sp_stocks, "composite_fallen_angel"),
    ]
    
    for title, pool, score_key in categories:
        lines.append(f"  [ {title} ]")
        top_stocks = get_top(pool, score_key, 3)
        if not top_stocks:
            lines.append("    (No candidates found)")
        for s in top_stocks:
            sym = s.get('symbol', '???')
            score = float(s.get(score_key, 0))
            price = float(s.get('price', 0))
            lines.append(f"    {sym:<6} Score: {score:.3f} | Price: ${price:.2f}")
        lines.append("")
        
    return lines


# ─────────────────────────────────────────────────────────────────────────
# CORE
# ─────────────────────────────────────────────────────────────────────────

def build_email() -> tuple[str, str]:
    today = date.today().isoformat()
    
    state = gcs_read("portfolio/state.json")
    health = gcs_read("hit_rate_tracking/rolling_health.json")
    gl_data = gcs_read("scans/latest_global.json")
    # latest_sp500.json was retired (dead pointer frozen 2026-05-05); the global
    # scan is a superset, so the US idea categories draw from it too.
    sp500 = gl_data

    subject = f"📊 CB Screener Weekly — {today}"

    body_parts = [
        "═" * 78,
        f"  CB SCREENER WEEKLY REPORT — {today}",
        "═" * 78,
        "",
    ]
    
    body_parts.extend(section_portfolio(state))
    body_parts.extend(section_strategies())
    body_parts.extend(section_health(health))
    body_parts.extend(section_ideas(sp500, gl_data))
    
    body_parts.extend([
        "═" * 78,
        f"  https://screener.carbonbridge.nl/performance",
        f"  Generated by paper_weekly_email.py",
        "═" * 78,
    ])
    
    return subject, "\n".join(body_parts)


def send_email(subject: str, body: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        log.info("No SMTP credentials — printing email body only:\n")
        import sys
        sys.stdout.buffer.write(f"Subject: {subject}\n\n".encode("utf-8"))
        sys.stdout.buffer.write(body.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
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
