#!/usr/bin/env python3
"""
Weekly Report Generator — CB Screener v7
==========================================
Generates a weekly portfolio report with:
  - Top 20 ranked picks (sorted by composite)
  - Swap recommendations (what to buy/sell vs current holdings)
  - Catalyst calendar (earnings, upgrades in next 21 days)
  - Options candidates (high conviction + near-term catalyst)
  - Composite erosion tracking (score history per position)
  - Probability table from ML backtest

Usage:
  # Standalone (reads latest scan from GCS):
  python weekly_report.py

  # With specific scan file:
  python weekly_report.py --scan scans/latest.json

  # With portfolio state:
  python weekly_report.py --portfolio portfolio/state.json

  # Email the report:
  python weekly_report.py --email

Output: GCS portfolio/weekly_report.json + email if configured
"""

import os, sys, json, time, logging, argparse
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weekly_report")

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
GCS_BUCKET = "screener-signals-carbonbridge"
RATE = 0.04

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

# ---------------------------------------------------------------------------
# ML Probability Lookup Table (from 15,120 samples, 24 months)
# ---------------------------------------------------------------------------

PROBABILITY_TABLE = {
    # composite_bucket: (P_5pct_30d, P_10pct_60d, P_20pct_60d, avg_max_gain, avg_max_dd, avg_days_to_10pct)
    ">0.90":    (0.79, 0.72, 0.42, 25.7, -9.1, 18),
    "0.85-0.90":(0.69, 0.53, 0.28, 17.9, -9.8, 22),
    "0.80-0.85":(0.69, 0.53, 0.28, 17.9, -9.8, 22),  # same bucket as 0.75-0.85
    "0.75-0.80":(0.61, 0.44, 0.19, 12.8, -10.8, 24),
    "0.70-0.75":(0.61, 0.44, 0.19, 12.8, -10.8, 24),
    "0.65-0.70":(0.59, 0.43, 0.18, 12.1, -10.3, 26),
    "<0.65":    (0.53, 0.37, 0.20, 10.7, -10.7, 22),
}

def get_probability(composite):
    """Look up ML probability metrics for a composite score."""
    if composite >= 0.90: return PROBABILITY_TABLE[">0.90"]
    elif composite >= 0.85: return PROBABILITY_TABLE["0.85-0.90"]
    elif composite >= 0.80: return PROBABILITY_TABLE["0.80-0.85"]
    elif composite >= 0.75: return PROBABILITY_TABLE["0.75-0.80"]
    elif composite >= 0.70: return PROBABILITY_TABLE["0.70-0.75"]
    elif composite >= 0.65: return PROBABILITY_TABLE["0.65-0.70"]
    else: return PROBABILITY_TABLE["<0.65"]

# ---------------------------------------------------------------------------
# GCS I/O
# ---------------------------------------------------------------------------

def gcs_download(path):
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def gcs_upload(path, data):
    try:
        tok = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3
        ).json().get("access_token", "")
        if not tok: return False
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(data, default=str), timeout=15
        )
        return r.status_code in (200, 201)
    except:
        return False

# ---------------------------------------------------------------------------
# FMP helpers
# ---------------------------------------------------------------------------

def fmp(endpoint, params=None):
    time.sleep(RATE)
    p = {"apikey": FMP_KEY}
    if params: p.update(params)
    try:
        r = requests.get(f"{FMP}/{endpoint}", params=p, timeout=20)
        if r.status_code != 200: return None
        d = r.json()
        if isinstance(d, dict) and "Error Message" in d: return None
        return [d] if isinstance(d, dict) else (d if isinstance(d, list) else None)
    except:
        return None

# ---------------------------------------------------------------------------
# Composite History Tracking
# ---------------------------------------------------------------------------

def load_composite_history():
    """Load composite score history from GCS."""
    data = gcs_download("portfolio/composite_history.json")
    return data or {}

def save_composite_history(history):
    """Save composite history to GCS."""
    gcs_upload("portfolio/composite_history.json", history)

def update_composite_history(stocks, history=None):
    """
    Append today's composite scores for all Top 20 + held positions.
    History format: { "SYMBOL": [ {date, composite, signal, price}, ... ] }
    Keep last 90 days per symbol.
    """
    if history is None:
        history = load_composite_history()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    for s in stocks:
        sym = s.get("symbol", "")
        if not sym:
            continue
        if sym not in history:
            history[sym] = []
        
        # Don't duplicate same day
        if history[sym] and history[sym][-1].get("date") == today:
            history[sym][-1] = {
                "date": today,
                "composite": round(s.get("composite", 0), 3),
                "signal": s.get("signal", ""),
                "price": round(s.get("price", 0), 2),
            }
        else:
            history[sym].append({
                "date": today,
                "composite": round(s.get("composite", 0), 3),
                "signal": s.get("signal", ""),
                "price": round(s.get("price", 0), 2),
            })
        
        # Keep last 90 entries
        history[sym] = history[sym][-90:]
    
    save_composite_history(history)
    return history

def compute_erosion(sym, history):
    """
    Compute composite score erosion metrics for a symbol.
    Returns: { trend_7d, trend_30d, peak_composite, current_composite, days_since_peak }
    """
    entries = history.get(sym, [])
    if not entries:
        return None
    
    current = entries[-1]["composite"]
    
    # 7-day trend
    if len(entries) >= 7:
        week_ago = entries[-7]["composite"]
        trend_7d = current - week_ago
    else:
        trend_7d = 0
    
    # 30-day trend
    if len(entries) >= 30:
        month_ago = entries[-30]["composite"]
        trend_30d = current - month_ago
    else:
        trend_30d = 0
    
    # Peak
    peak = max(e["composite"] for e in entries)
    peak_idx = next(i for i, e in enumerate(entries) if e["composite"] == peak)
    days_since_peak = len(entries) - 1 - peak_idx
    erosion_pct = (current - peak) / peak * 100 if peak > 0 else 0
    
    return {
        "current": round(current, 3),
        "trend_7d": round(trend_7d, 3),
        "trend_30d": round(trend_30d, 3),
        "peak": round(peak, 3),
        "days_since_peak": days_since_peak,
        "erosion_pct": round(erosion_pct, 1),
        "sparkline": [round(e["composite"], 3) for e in entries[-14:]],  # last 14 days
    }

# ---------------------------------------------------------------------------
# Options Candidate Detection
# ---------------------------------------------------------------------------

def flag_options_candidate(stock):
    """
    Flag a stock as an options candidate if ALL conditions are met:
    - Composite > 0.80
    - Active catalyst (catalyst_score > 0.65)
    - Earnings within 21 days
    - Beat rate >= 75% (6/8 or better)
    - Quality >= 0.50
    
    Returns: None or options dict with strategy suggestions
    """
    composite = stock.get("composite", 0)
    catalyst_score = stock.get("catalyst_score", 0)
    quality_score = stock.get("quality_score", 0)
    days_to_earnings = stock.get("days_to_earnings", -1)
    beat_rate = stock.get("eps_beat_rate", 0)
    price = stock.get("price", 0)
    
    if not (composite > 0.80 and
            catalyst_score > 0.65 and
            0 < days_to_earnings <= 21 and
            beat_rate >= 0.75 and
            quality_score >= 0.50):
        return None
    
    # Suggest strategies based on timeframe
    prob = get_probability(composite)
    p10 = prob[1]  # P(+10% in 60d)
    
    target_price = round(price * 1.10, 2)  # +10% target
    
    return {
        "is_candidate": True,
        "composite": composite,
        "catalyst": stock.get("catalyst_flags", []),
        "days_to_earnings": days_to_earnings,
        "beat_rate": beat_rate,
        "p_10pct_60d": p10,
        "strategies": {
            "conservative": f"Buy shares at ${price:.2f}, target ${target_price:.2f} (+10%)",
            "moderate": f"Buy monthly call ~${round(price*1.02, 0):.0f} strike, 30-45 DTE",
            "aggressive": f"Buy weekly call ~${round(price*1.05, 0):.0f} strike, earnings play ({days_to_earnings}d)",
        },
        "risk_note": f"Max expected drawdown: {prob[4]}%. Set stop at {prob[4]*1.2:.0f}%."
    }

# ---------------------------------------------------------------------------
# Weekly Report Generation
# ---------------------------------------------------------------------------

def generate_weekly_report(scan_data, portfolio_state=None):
    """
    Generate the full weekly report.
    
    Args:
        scan_data: Full scan JSON from GCS (scans/latest.json)
        portfolio_state: Portfolio state JSON from GCS (portfolio/state.json)
    
    Returns: (report_text, report_json)
    """
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    stocks = scan_data.get("stocks", [])
    macro = scan_data.get("macro", {})
    
    # Sort by composite, highest first
    stocks.sort(key=lambda x: x.get("composite", 0), reverse=True)
    
    # Top 20
    top20 = stocks[:20]
    
    # Current portfolio
    held_symbols = set()
    held_positions = {}
    if portfolio_state and portfolio_state.get("positions"):
        for p in portfolio_state["positions"]:
            held_symbols.add(p["symbol"])
            held_positions[p["symbol"]] = p
    
    # Composite history
    comp_history = load_composite_history()
    update_composite_history(top20 + [s for s in stocks if s.get("symbol") in held_symbols], comp_history)
    
    # ─── Top 20 with probabilities ───
    top20_enriched = []
    for s in top20:
        sym = s.get("symbol", "")
        comp = s.get("composite", 0)
        prob = get_probability(comp)
        erosion = compute_erosion(sym, comp_history)
        options = flag_options_candidate(s)
        
        in_portfolio = sym in held_symbols
        
        top20_enriched.append({
            "rank": len(top20_enriched) + 1,
            "symbol": sym,
            "price": s.get("price", 0),
            "composite": comp,
            "signal": s.get("signal", ""),
            "classification": s.get("classification", ""),
            "p_5pct_30d": prob[0],
            "p_10pct_60d": prob[1],
            "p_20pct_60d": prob[2],
            "expected_max_gain": prob[3],
            "expected_max_dd": prob[4],
            "avg_days_to_10pct": prob[5],
            "in_portfolio": in_portfolio,
            "action": "HOLD" if in_portfolio else "NEW",
            "erosion": erosion,
            "options_candidate": options,
            "catalyst_flags": s.get("catalyst_flags", []),
            "quality_score": s.get("quality_score", 0),
            "bull_score": s.get("bull_score", 0),
            "factor_coverage": s.get("factor_coverage", 0),
            "factors_evaluated": s.get("factors_evaluated", []),
            "factors_missing": s.get("factors_missing", []),
        })
    
    # ─── Swap Recommendations ───
    top20_syms = set(s["symbol"] for s in top20)
    
    # Stocks to BUY (in top 20, not held)
    to_buy = [s for s in top20_enriched if not s["in_portfolio"]]
    
    # Stocks to SELL (held, but dropped out of top 20)
    to_sell = []
    for sym in held_symbols:
        if sym not in top20_syms:
            # Find where it ranks now
            rank = next((i+1 for i, s in enumerate(stocks) if s.get("symbol") == sym), 999)
            stock_data = next((s for s in stocks if s.get("symbol") == sym), {})
            erosion = compute_erosion(sym, comp_history)
            to_sell.append({
                "symbol": sym,
                "current_rank": rank,
                "composite": stock_data.get("composite", 0),
                "signal": stock_data.get("signal", ""),
                "erosion": erosion,
                "reason": f"Dropped to rank #{rank}" + (
                    f", composite eroding ({erosion['erosion_pct']:+.0f}% from peak)" 
                    if erosion and erosion["erosion_pct"] < -10 else ""
                ),
            })
    to_sell.sort(key=lambda x: x["current_rank"], reverse=True)  # worst rank first
    
    # ─── Catalyst Calendar (next 21 days) ───
    catalysts = []
    for s in top20_enriched:
        if s.get("catalyst_flags"):
            catalysts.append({
                "symbol": s["symbol"],
                "flags": s["catalyst_flags"],
                "composite": s["composite"],
                "in_portfolio": s["in_portfolio"],
            })
    
    # ─── Options Candidates ───
    options_picks = [s for s in top20_enriched if s.get("options_candidate")]
    
    # ─── Erosion Alerts ───
    erosion_alerts = []
    for sym in held_symbols:
        er = compute_erosion(sym, comp_history)
        if er and (er["erosion_pct"] < -15 or er["trend_7d"] < -0.05):
            erosion_alerts.append({
                "symbol": sym,
                "current_composite": er["current"],
                "peak_composite": er["peak"],
                "erosion_pct": er["erosion_pct"],
                "trend_7d": er["trend_7d"],
                "days_since_peak": er["days_since_peak"],
                "alert": "EROSION" if er["erosion_pct"] < -15 else "DECLINING",
            })
    
    # ─── Format Text Report ───
    report = format_report_text(
        today_str, macro, top20_enriched, to_buy, to_sell,
        catalysts, options_picks, erosion_alerts, held_symbols
    )
    
    # ─── Build JSON (for frontend) ───
    report_json = {
        "date": today_str,
        "macro": macro,
        "top20": top20_enriched,
        "swaps": {"buy": to_buy, "sell": to_sell},
        "swap_count": len(to_buy),
        "catalysts": catalysts,
        "options_candidates": [s["symbol"] for s in options_picks],
        "erosion_alerts": erosion_alerts,
        "portfolio_overlap": len(held_symbols & top20_syms),
        "portfolio_size": len(held_symbols),
    }
    
    return report, report_json

# ---------------------------------------------------------------------------
# Text Report Formatting
# ---------------------------------------------------------------------------

def format_report_text(date, macro, top20, to_buy, to_sell, catalysts, options, erosion_alerts, held):
    regime = macro.get("regime", "NEUTRAL")
    regime_emoji = {"RISK_ON": "🟢", "NEUTRAL": "⚪", "CAUTIOUS": "🟡", "RISK_OFF": "🔴"}.get(regime, "⚪")
    
    lines = [
        f"{'═'*80}",
        f"  CB SCREENER — WEEKLY REPORT — {date}",
        f"  Macro: {regime_emoji} {regime} ({macro.get('score', 0.5):.2f})",
        f"  Portfolio: {len(held)} positions | {len(held & set(s['symbol'] for s in top20))}/{len(top20)} overlap with Top 20",
        f"{'═'*80}",
    ]
    
    # Swaps summary
    if to_buy or to_sell:
        lines.append(f"\n  📊 SWAPS THIS WEEK: {len(to_buy)} buy, {len(to_sell)} sell")
        lines.append(f"  {'─'*75}")
        for s in to_sell[:5]:
            lines.append(f"    🔴 SELL  {s['symbol']:<8} — {s['reason']}")
        for s in to_buy[:5]:
            prob = get_probability(s["composite"])
            lines.append(f"    🟢 BUY   {s['symbol']:<8} — Comp {s['composite']:.3f} | "
                        f"P(+10%): {prob[1]*100:.0f}% | Signal: {s['signal']}")
    else:
        lines.append(f"\n  ✅ NO SWAPS NEEDED — portfolio aligned with Top 20")
    
    # Top 20
    lines.append(f"\n  {'─'*85}")
    lines.append(f"  TOP 20 PORTFOLIO {'':>53}")
    lines.append(f"  {'#':>3} {'Sym':<8} {'Price':>8} {'Comp':>6} {'Signal':<12} "
                f"{'P(+10%)':>8} {'MaxGain':>8} {'MaxDD':>7} {'Cov':>5} {'Action':<8}")
    lines.append(f"  {'─'*85}")
    
    for s in top20:
        status = "HOLD ✅" if s["in_portfolio"] else "⬆️ NEW"
        options_flag = " ⚡" if s.get("options_candidate") else ""
        erosion_flag = ""
        if s.get("erosion") and s["erosion"]["trend_7d"] < -0.03:
            erosion_flag = " ↘"
        elif s.get("erosion") and s["erosion"]["trend_7d"] > 0.03:
            erosion_flag = " ↗"
        
        cov = s.get("factor_coverage", 0)
        cov_str = f"{cov}/10"
        
        lines.append(
            f"  {s['rank']:>3} {s['symbol']:<8} ${s['price']:>7.2f} {s['composite']:>5.3f} "
            f"{s['signal']:<12} {s['p_10pct_60d']*100:>7.0f}% {s['expected_max_gain']:>+7.1f}% "
            f"{s['expected_max_dd']:>+6.1f}% {cov_str:>5} {status}{options_flag}{erosion_flag}"
        )
    
    # Erosion alerts
    if erosion_alerts:
        lines.append(f"\n  ⚠️  COMPOSITE EROSION ALERTS:")
        lines.append(f"  {'─'*75}")
        for a in erosion_alerts:
            lines.append(f"    {a['symbol']:<8} Peak {a['peak_composite']:.3f} → Now {a['current_composite']:.3f} "
                        f"({a['erosion_pct']:+.0f}%) | 7d trend: {a['trend_7d']:+.3f} | "
                        f"{'🔴 SELL CANDIDATE' if a['alert']=='EROSION' else '🟡 Watch closely'}")
    
    # Catalysts
    if catalysts:
        lines.append(f"\n  ⚡ CATALYST CALENDAR (next 21 days):")
        lines.append(f"  {'─'*75}")
        for c in catalysts:
            held_mark = "✅" if c["in_portfolio"] else "  "
            lines.append(f"    {held_mark} {c['symbol']:<8} {', '.join(c['flags'][:2])}")
    
    # Options candidates
    if options:
        lines.append(f"\n  🎯 OPTIONS CANDIDATES (high conviction + catalyst):")
        lines.append(f"  {'─'*75}")
        for s in options:
            opt = s["options_candidate"]
            lines.append(f"    {s['symbol']:<8} Comp {s['composite']:.3f} | P(+10%): {opt['p_10pct_60d']*100:.0f}% | "
                        f"Beat rate: {opt['beat_rate']*100:.0f}%")
            lines.append(f"      Conservative: {opt['strategies']['conservative']}")
            lines.append(f"      Moderate:     {opt['strategies']['moderate']}")
            lines.append(f"      Aggressive:   {opt['strategies']['aggressive']}")
            lines.append(f"      Risk:         {opt['risk_note']}")
    
    lines.append(f"\n{'═'*85}")
    lines.append(f"  Generated by CB Screener v7.1 | screener.carbonbridge.nl")
    lines.append(f"{'═'*85}")
    
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(subject, body):
    if not SMTP_USER or not SMTP_PASS:
        log.info("No SMTP credentials — skipping email")
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log.info(f"Email sent to {EMAIL_TO}")
    except Exception as e:
        log.warning(f"Email failed: {e}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CB Screener Weekly Report")
    parser.add_argument("--scan", default="", help="Path to scan JSON (default: GCS latest)")
    parser.add_argument("--portfolio", default="", help="Path to portfolio state JSON")
    parser.add_argument("--email", action="store_true", help="Send report via email")
    parser.add_argument("--output", default="", help="Save report text to file")
    args = parser.parse_args()
    
    # Load scan data
    if args.scan:
        with open(args.scan) as f:
            scan_data = json.load(f)
    else:
        scan_data = gcs_download("scans/latest.json")
        if not scan_data:
            log.error("Cannot load scan data from GCS")
            sys.exit(1)
    
    # Load portfolio state
    if args.portfolio:
        with open(args.portfolio) as f:
            portfolio_state = json.load(f)
    else:
        portfolio_state = gcs_download("portfolio/state.json")
    
    # Generate report
    report_text, report_json = generate_weekly_report(scan_data, portfolio_state)
    
    print(report_text)
    
    # Save to GCS
    gcs_upload("portfolio/weekly_report.json", report_json)
    gcs_upload("portfolio/composite_history.json", load_composite_history())
    log.info("Report saved to GCS")
    
    # Save locally
    if args.output:
        with open(args.output, "w") as f:
            f.write(report_text)
        log.info(f"Report saved to {args.output}")
    
    # Email
    if args.email:
        today = datetime.now().strftime("%Y-%m-%d")
        swaps = report_json["swap_count"]
        erosions = len(report_json["erosion_alerts"])
        options_count = len(report_json["options_candidates"])
        
        subject = f"CB Screener — {today}"
        if swaps > 0:
            subject += f" — {swaps} swap{'s' if swaps > 1 else ''}"
        if erosions > 0:
            subject += f" — ⚠️ {erosions} erosion alert{'s' if erosions > 1 else ''}"
        if options_count > 0:
            subject += f" — ⚡ {options_count} options"
        
        send_email(subject, report_text)

if __name__ == "__main__":
    main()
