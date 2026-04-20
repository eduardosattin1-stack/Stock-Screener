#!/usr/bin/env python3
"""
Portfolio Monitor v7 — Daily Position Re-Scoring & Alert System
================================================================
Standalone script that re-scores all held positions using screener_v6 factors.
Generates HOLD / TRIM / SELL / ADD actions based on 8 ML-validated rules.

Usage:
  # Daily monitor (Cloud Scheduler at 18:00 CET)
  python monitor_v7.py

  # Add a position
  python monitor_v7.py --add KLAC --entry-price 1410.45 --shares 7

  # Remove a position
  python monitor_v7.py --remove ADBE

  # List all positions
  python monitor_v7.py --list

  # Force re-score without email
  python monitor_v7.py --dry-run

Cloud Scheduler:
  gcloud scheduler jobs create http screener-monitor \\
    --schedule="0 17 * * 1-5" --time-zone="Europe/Amsterdam" \\
    --uri="https://stock-screener-606056076947.europe-west1.run.app" \\
    --http-method=POST --body='{"mode":"monitor"}' \\
    --oidc-service-account-email=...

State: portfolio/state.json on GCS (screener-signals-carbonbridge)
Alerts: Email if any action != HOLD
"""

import os, sys, json, time, logging, argparse
from datetime import datetime, timedelta

# Add parent dir to path so we can import screener_v6
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("monitor_v7")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
RATE_LIMIT = 0.04

GCS_BUCKET = "screener-signals-carbonbridge"
STATE_PATH = "portfolio/state.json"
MONITOR_PATH = "portfolio/monitor.json"
LOCAL_STATE = "portfolio_state.json"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

# ---------------------------------------------------------------------------
# FMP API (lightweight — only what the monitor needs)
# ---------------------------------------------------------------------------

def fmp(endpoint, params=None):
    time.sleep(RATE_LIMIT)
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
# GCS State Management
# ---------------------------------------------------------------------------

def gcs_download(path):
    """Download JSON from GCS (public read)."""
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def gcs_upload(path, data):
    """Upload JSON to GCS (requires service account on Cloud Run)."""
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

def load_state():
    """Load portfolio state from GCS, fallback to local file.

    v7.2: normalizes schema on load — adds any missing top-level keys so
    older state files from pre-v7.2 monitors upgrade transparently.
    """
    def _normalize(s):
        s.setdefault("positions", [])
        s.setdefault("history", [])
        s.setdefault("last_monitor", "")
        return s
    state = gcs_download(STATE_PATH)
    if state and "positions" in state:
        log.info(f"Loaded state from GCS: {len(state['positions'])} positions")
        return _normalize(state)
    try:
        with open(LOCAL_STATE) as f:
            state = json.load(f)
            log.info(f"Loaded state from local: {len(state.get('positions', []))} positions")
            return _normalize(state)
    except FileNotFoundError:
        return {"positions": [], "history": [], "last_monitor": ""}

def save_state(state):
    """Save portfolio state to GCS + local."""
    state["last_updated"] = datetime.now().isoformat()
    with open(LOCAL_STATE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    if gcs_upload(STATE_PATH, state):
        log.info("State saved to GCS")
    else:
        log.info("State saved locally (GCS unavailable)")

# ---------------------------------------------------------------------------
# Import scoring functions from screener_v6
# ---------------------------------------------------------------------------

try:
    from screener_v6 import (
        get_technicals, get_analyst, get_value, get_insider_activity,
        compute_52wk_proximity, compute_earnings_momentum, compute_upside_score,
        compute_catastrophe, compute_quality_score, compute_catalyst_score,
        compute_composite_v7, get_quotes_batch, WEIGHTS,
    )
    log.info("Imported screener_v6 scoring functions")
except ImportError as e:
    log.error(f"Cannot import screener_v6: {e}")
    log.error("Place monitor_v7.py in the same directory as screener_v6.py")
    sys.exit(1)

# Try macro overlay
try:
    from macro_regime import fetch_macro_regime, apply_macro_tilt
    HAS_MACRO = True
except ImportError:
    HAS_MACRO = False

# ---------------------------------------------------------------------------
# Portfolio CRUD Operations
# ---------------------------------------------------------------------------

def add_position(state, symbol, entry_price, shares=0, notes=""):
    """Add a new position or update existing one."""
    symbol = symbol.upper()
    existing = [p for p in state["positions"] if p["symbol"] == symbol]
    if existing:
        log.info(f"Updating existing position: {symbol}")
        pos = existing[0]
        pos["entry_price"] = entry_price
        pos["shares"] = shares or pos.get("shares", 0)
        pos["notes"] = notes or pos.get("notes", "")
    else:
        # Get current composite for entry tracking
        quotes = get_quotes_batch([symbol])
        q = quotes.get(symbol)
        entry_composite = 0.5
        entry_signal = "UNKNOWN"
        if q and q["price"] > 0:
            t = get_technicals(symbol, q)
            if t:
                a = get_analyst(symbol)
                v = get_value(symbol, q["price"], q["currency"])
                ins = get_insider_activity(symbol)
                prox = compute_52wk_proximity(q)
                earn = compute_earnings_momentum(a)
                ups = compute_upside_score(a, v, q["price"])
                qual = compute_quality_score(v)
                cata = compute_catalyst_score(symbol, analyst=a)
                # v7.2: compute_composite_v7 returns 5 values (composite, signal,
                # factors, reasons, coverage). Pre-v7.2 it returned 4 — legacy
                # code here unpacked 4 and silently broke on add after the deploy.
                entry_composite, entry_signal, _, _, _ = compute_composite_v7(
                    t, a, v, q["price"], ins, prox, earn, ups,
                    quality=qual, catalyst=cata,
                )

        pos = {
            "symbol": symbol,
            "entry_price": entry_price or (q["price"] if q else 0),
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
            "entry_composite": round(entry_composite, 3),
            "entry_signal": entry_signal,
            "shares": shares,
            "peak_price": entry_price or (q["price"] if q else 0),
            "notes": notes,
            "last_monitor": "",
            "last_composite": 0,
            "last_signal": "",
        }
        state["positions"].append(pos)
        log.info(f"Added position: {symbol} @ ${entry_price:.2f} | "
                 f"Composite: {entry_composite:.3f} | Signal: {entry_signal}")
    return state

def remove_position(state, symbol, exit_price=None, reason="Manual removal"):
    """Remove a position and record in history."""
    symbol = symbol.upper()
    pos = [p for p in state["positions"] if p["symbol"] == symbol]
    if not pos:
        log.warning(f"Position not found: {symbol}")
        return state

    p = pos[0]
    pnl = ((exit_price - p["entry_price"]) / p["entry_price"] * 100) if exit_price else 0

    # v7.2: gracefully upgrade older state files that don't have 'history' yet
    state.setdefault("history", [])
    state["history"].append({
        "symbol": symbol,
        "action": "REMOVED",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "entry_price": p["entry_price"],
        "entry_date": p["entry_date"],
        "exit_price": exit_price or 0,
        "pnl_pct": round(pnl, 1),
        "reason": reason,
        "days_held": (datetime.now() - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days
            if p.get("entry_date") else 0,
    })
    state["history"] = state["history"][-100:]  # keep last 100

    state["positions"] = [p for p in state["positions"] if p["symbol"] != symbol]
    log.info(f"Removed position: {symbol} | PnL: {pnl:+.1f}%")
    return state

def list_positions(state):
    """Pretty-print current positions."""
    positions = state.get("positions", [])
    if not positions:
        print("  No positions in portfolio.")
        return

    # Get live quotes
    syms = [p["symbol"] for p in positions]
    quotes = get_quotes_batch(syms)

    print(f"\n  {'='*85}")
    print(f"  PORTFOLIO — {len(positions)} positions")
    print(f"  {'='*85}")
    print(f"  {'Sym':<8} {'Entry':>8} {'Current':>8} {'PnL':>7} {'Days':>5} "
          f"{'Entry Comp':>10} {'Last Comp':>10} {'Signal':<10}")
    print(f"  {'─'*85}")

    total_pnl = 0
    for p in positions:
        q = quotes.get(p["symbol"], {})
        current = q.get("price", 0)
        pnl = ((current - p["entry_price"]) / p["entry_price"] * 100) if p["entry_price"] > 0 and current > 0 else 0
        days = (datetime.now() - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days if p.get("entry_date") else 0
        emoji = "🟢" if pnl > 0 else "🔴"
        total_pnl += pnl

        print(f"  {p['symbol']:<8} ${p['entry_price']:>7.2f} ${current:>7.2f} {pnl:>+6.1f}% {days:>4}d "
              f"{p.get('entry_composite', 0):>9.3f} {p.get('last_composite', 0):>9.3f} "
              f"{p.get('last_signal', '?'):<10} {emoji}")

    avg_pnl = total_pnl / len(positions) if positions else 0
    print(f"  {'─'*85}")
    print(f"  Average PnL: {avg_pnl:+.1f}% across {len(positions)} positions")

    # History summary
    hist = state.get("history", [])
    if hist:
        recent = hist[-5:]
        print(f"\n  Last {len(recent)} exits:")
        for h in recent:
            print(f"    {h['date']} {h['symbol']:<8} {h.get('pnl_pct', 0):+.1f}% — {h.get('reason', '')}")

# ---------------------------------------------------------------------------
# Core Monitor Logic (8 Decision Rules)
# ---------------------------------------------------------------------------

def run_monitor(state, dry_run=False):
    """
    Re-score all held positions and generate actions.
    Returns (actions_list, report_string).
    """
    positions = state.get("positions", [])
    if not positions:
        return [], "No positions to monitor."

    syms = [p["symbol"] for p in positions]
    log.info(f"Monitoring {len(syms)} positions: {', '.join(syms)}")

    # Macro regime (once for all positions)
    active_weights = WEIGHTS.copy()
    macro_regime = "NEUTRAL"
    if HAS_MACRO:
        try:
            macro = fetch_macro_regime(fmp, rate_limit_func=lambda: time.sleep(RATE_LIMIT))
            active_weights = apply_macro_tilt(WEIGHTS, macro)
            macro_regime = macro.get("regime", "NEUTRAL")
            log.info(f"Macro: {macro_regime} — weights tilted")
        except Exception as e:
            log.warning(f"Macro failed: {e}")

    # Get all quotes at once
    quotes = get_quotes_batch(syms)
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    actions = []

    for pos in positions:
        sym = pos["symbol"]
        q = quotes.get(sym)
        if not q or q["price"] <= 0:
            actions.append({"symbol": sym, "action": "ERROR", "urgency": "low",
                           "reasons": ["No quote data available"]})
            continue

        price = q["price"]
        entry_price = pos.get("entry_price", price)
        entry_comp = pos.get("entry_composite", 0.5)
        entry_signal = pos.get("entry_signal", "BUY")
        entry_date = pos.get("entry_date", today_str)
        peak_price = pos.get("peak_price", price)

        log.info(f"  Scoring {sym}...")

        # Full v7 scoring
        t = get_technicals(sym, q)
        if not t:
            actions.append({"symbol": sym, "action": "ERROR", "urgency": "low",
                           "reasons": ["No chart data"]})
            continue

        a = get_analyst(sym)
        if a["target"] > 0:
            a["upside"] = (a["target"] - price) / price * 100
        v = get_value(sym, price, q["currency"])
        ins = get_insider_activity(sym)
        prox = compute_52wk_proximity(q)
        earn = compute_earnings_momentum(a)
        ups = compute_upside_score(a, v, price)
        qual = compute_quality_score(v)
        cata = compute_catalyst_score(sym, analyst=a)

        composite, signal, factors, reasons, coverage = compute_composite_v7(
            t, a, v, price, ins, prox, earn, ups,
            quality=qual, catalyst=cata,
            weights=active_weights,
        )

        # ─── 8 Decision Rules ───
        price_change = (price - entry_price) / entry_price if entry_price > 0 else 0
        comp_change = (composite - entry_comp) / entry_comp if entry_comp > 0 else 0
        try:
            days_held = (today - datetime.strptime(entry_date, "%Y-%m-%d")).days
        except:
            days_held = 0

        action = "HOLD"
        urgency = "normal"
        action_reasons = []

        # RULE 1: Signal downgrade (BUY/STRONG BUY → HOLD or worse)
        buy_signals = {"STRONG BUY", "BUY"}
        if entry_signal in buy_signals and signal in ("HOLD", "SELL"):
            action = "SELL"
            urgency = "high"
            action_reasons.append(f"Signal downgrade: {entry_signal} → {signal}")

        # RULE 2: Composite decay > 20%
        if comp_change < -0.20:
            if action != "SELL":
                action = "TRIM"
            urgency = "high"
            action_reasons.append(f"Composite decay: {entry_comp:.3f} → {composite:.3f} ({comp_change:+.0%})")

        # RULE 3: Stop-loss at -15% from entry
        if price_change < -0.15:
            action = "SELL"
            urgency = "critical"
            action_reasons.append(f"Stop-loss triggered: {price_change:+.1%} from entry ${entry_price:.2f}")

        # RULE 4: Trailing stop — if gained >15% then gave back >10% from peak
        if peak_price > entry_price:
            gain_from_entry = (peak_price - entry_price) / entry_price
            drop_from_peak = (price - peak_price) / peak_price
            if gain_from_entry > 0.15 and drop_from_peak < -0.10:
                if action == "HOLD":
                    action = "TRIM"
                action_reasons.append(f"Trailing stop: peak ${peak_price:.2f} ({gain_from_entry:+.0%}), "
                                     f"now {drop_from_peak:+.0%} from peak")

        # RULE 5: Catalyst warning (new downgrade, negative news)
        if cata.get("is_risky") and action == "HOLD":
            action = "TRIM"
            urgency = "medium"
            action_reasons.append(f"Catalyst warning: {', '.join(cata.get('flags', []))}")

        # RULE 6: Catalyst override (strong catalyst saves a dip)
        if cata.get("has_catalyst") and signal in ("BUY", "WATCH", "STRONG BUY"):
            if action in ("TRIM",) and comp_change > -0.30:
                action = "HOLD"
                action_reasons.append(f"Catalyst override: {', '.join(cata.get('flags', []))}")

        # RULE 7: Time decay (>90 days and not BUY)
        if days_held > 90 and signal not in ("BUY", "STRONG BUY"):
            if action == "HOLD":
                action = "TRIM"
            action_reasons.append(f"Time decay: held {days_held}d, signal now {signal}")

        # RULE 8: Composite improving → ADD
        if comp_change > 0.15 and signal in ("BUY", "STRONG BUY") and price_change < 0.05:
            action = "ADD"
            action_reasons.append(f"Composite improving: {entry_comp:.3f} → {composite:.3f} ({comp_change:+.0%})")

        # Update tracking
        if price > peak_price:
            pos["peak_price"] = price
        pos["last_monitor"] = today_str
        pos["last_composite"] = round(composite, 3)
        pos["last_signal"] = signal

        actions.append({
            "symbol": sym,
            "action": action,
            "urgency": urgency,
            "current_price": round(price, 2),
            "entry_price": entry_price,
            "pnl_pct": round(price_change * 100, 1),
            "entry_composite": entry_comp,
            "current_composite": round(composite, 3),
            "comp_change_pct": round(comp_change * 100, 1),
            "entry_signal": entry_signal,
            "current_signal": signal,
            "days_held": days_held,
            "catalyst_score": round(cata.get("score", 0.5), 2),
            "catalyst_flags": cata.get("flags", []),
            "quality_score": round(qual.get("score", 0.5), 2),
            "bull_score": t.get("bull_score", 0),
            "reasons": action_reasons,
        })

        log.info(f"    {sym}: {action} | ${price:.2f} ({price_change:+.1%}) | "
                 f"Comp: {composite:.3f} ({comp_change:+.0%}) | Signal: {signal}")

    # v7.2: Monitor NO LONGER auto-closes SELL positions.
    # SELL signal is informational; user explicitly closes via
    # /portfolio/close HTTP endpoint or the Close button on the portfolio UI.
    # This separates "what the model thinks" from "what the user decides."
    # The actions list above still records the SELL recommendation, which is
    # emailed and displayed on the portfolio page. No state mutation here.

    # Format report
    report = format_monitor_report(actions, macro_regime)

    return actions, report

# ---------------------------------------------------------------------------
# Report Formatting
# ---------------------------------------------------------------------------

def format_monitor_report(actions, macro_regime="NEUTRAL"):
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{'='*80}",
        f"  PORTFOLIO MONITOR v7 — {today_str}",
        f"  Macro: {macro_regime} | {len(actions)} positions tracked",
        f"{'='*80}",
    ]

    has_actions = False
    for action_type in ["SELL", "TRIM", "ADD", "HOLD", "ERROR"]:
        group = [a for a in actions if a["action"] == action_type]
        if not group:
            continue
        emoji = {"SELL": "🔴", "TRIM": "🟡", "ADD": "⬆️", "HOLD": "🟢", "ERROR": "⚠️"}[action_type]
        if action_type in ("SELL", "TRIM", "ADD"):
            has_actions = True

        lines.append(f"\n  {emoji} {action_type} ({len(group)}):")
        lines.append(f"  {'─'*75}")

        for a in group:
            comp_arrow = "↑" if a.get("comp_change_pct", 0) > 0 else "↓"
            lines.append(
                f"    {a['symbol']:<8} ${a['current_price']:>8.2f}  "
                f"PnL: {a['pnl_pct']:>+6.1f}%  "
                f"Comp: {a['current_composite']:.3f} ({a['comp_change_pct']:+.0f}%{comp_arrow})  "
                f"Signal: {a['current_signal']}"
            )
            if a.get("catalyst_flags"):
                lines.append(f"      Catalyst: {', '.join(a['catalyst_flags'][:3])}")
            for r in a.get("reasons", []):
                lines.append(f"      → {r}")

    # Summary
    if actions:
        total_pnl = sum(a.get("pnl_pct", 0) for a in actions) / len(actions)
        winners = sum(1 for a in actions if a.get("pnl_pct", 0) > 0)
        sells = sum(1 for a in actions if a["action"] == "SELL")
        trims = sum(1 for a in actions if a["action"] == "TRIM")
        adds = sum(1 for a in actions if a["action"] == "ADD")

        lines.append(f"\n  {'─'*75}")
        lines.append(f"  Summary: {len(actions)} positions | Avg PnL: {total_pnl:+.1f}% | "
                     f"Winners: {winners}/{len(actions)}")
        if sells:
            lines.append(f"  ⚠️  {sells} SELL signal(s) — review and decide")
        if trims:
            lines.append(f"  ⚠️  {trims} TRIM signal(s) — consider reducing")
        if adds:
            lines.append(f"  ⬆️  {adds} ADD signal(s) — consider increasing")
        if not has_actions:
            lines.append(f"  ✅ All positions healthy — no action needed")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Email Alert
# ---------------------------------------------------------------------------

def send_alert(subject, body):
    if not SMTP_USER or not SMTP_PASS:
        log.info("No SMTP credentials — skipping email")
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log.info(f"Alert email sent to {EMAIL_TO}")
    except Exception as e:
        log.warning(f"Email failed: {e}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Portfolio Monitor v7")
    parser.add_argument("--add", metavar="SYMBOL", help="Add a position")
    parser.add_argument("--entry-price", type=float, default=0, help="Entry price for --add")
    parser.add_argument("--shares", type=int, default=0, help="Number of shares for --add")
    parser.add_argument("--notes", default="", help="Notes for --add")
    parser.add_argument("--remove", metavar="SYMBOL", help="Remove a position")
    parser.add_argument("--exit-price", type=float, default=0, help="Exit price for --remove")
    parser.add_argument("--list", action="store_true", help="List all positions")
    parser.add_argument("--dry-run", action="store_true", help="Score without executing sells or emailing")
    parser.add_argument("--no-email", action="store_true", help="Skip email alerts")
    parser.add_argument("--seed", metavar="FILE", help="Seed portfolio from JSON file")
    args = parser.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set!")
        sys.exit(1)

    state = load_state()

    # ─── Seed from file ───
    if args.seed:
        try:
            with open(args.seed) as f:
                seed_data = json.load(f)
            for p in seed_data.get("positions", seed_data if isinstance(seed_data, list) else []):
                state = add_position(
                    state, p["symbol"],
                    entry_price=p.get("entry_price", 0),
                    shares=p.get("shares", 0),
                    notes=p.get("notes", "")
                )
            save_state(state)
            log.info(f"Seeded {len(state['positions'])} positions from {args.seed}")
        except Exception as e:
            log.error(f"Seed failed: {e}")
        return

    # ─── Add position ───
    if args.add:
        state = add_position(state, args.add, args.entry_price, args.shares, args.notes)
        save_state(state)
        print(f"✅ Added {args.add.upper()}")
        list_positions(state)
        return

    # ─── Remove position ───
    if args.remove:
        state = remove_position(state, args.remove, args.exit_price)
        save_state(state)
        print(f"✅ Removed {args.remove.upper()}")
        list_positions(state)
        return

    # ─── List positions ───
    if args.list:
        list_positions(state)
        return

    # ─── Run monitor (default) ───
    if not state.get("positions"):
        log.info("No positions to monitor. Use --add to add positions.")
        return

    actions, report = run_monitor(state, dry_run=args.dry_run)

    print(report)

    # Save updated state
    if not args.dry_run:
        save_state(state)

    # Upload monitor results to GCS
    gcs_upload(MONITOR_PATH, {
        "date": datetime.now().isoformat(),
        "actions": actions,
    })

    # Email alert (only if there are non-HOLD actions)
    if not args.no_email and not args.dry_run:
        has_action = any(a["action"] in ("SELL", "TRIM", "ADD") for a in actions)
        if has_action:
            today = datetime.now().strftime("%Y-%m-%d")
            sells = sum(1 for a in actions if a["action"] == "SELL")
            subj = f"{'🔴 ' if sells else ''}Portfolio Alert — {today}"
            send_alert(subj, report)
        else:
            log.info("All positions HOLD — no alert needed")

if __name__ == "__main__":
    main()
