#!/usr/bin/env python3
"""
Portfolio Monitor v7 â€” Daily Position Re-Scoring & Alert System
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
# FMP API (lightweight â€” only what the monitor needs)
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

def gcs_download_with_gen(path):
    """Download JSON + object generation. Used for optimistic concurrency.

    Returns: (data, generation_string) or (None, "0") if missing/error.
    generation="0" is the special value to use on write to mean "only if the
    object does not yet exist."
    """
    try:
        tok = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3
        ).json().get("access_token", "")
        if not tok:
            # No metadata service (local dev) â€” fall back to public download, no gen
            return gcs_download(path), None
        r = requests.get(
            f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET}/o/{path.replace('/', '%2F')}",
            headers={"Authorization": f"Bearer {tok}"},
            params={"alt": "json"}, timeout=10,
        )
        if r.status_code == 200:
            meta = r.json()
            gen = meta.get("generation", "0")
            media_url = meta.get("mediaLink") or f"https://storage.googleapis.com/{GCS_BUCKET}/{path}"
            rr = requests.get(media_url, headers={"Authorization": f"Bearer {tok}"}, timeout=10)
            if rr.status_code == 200:
                return rr.json(), gen
        if r.status_code == 404:
            return None, "0"  # object does not exist â€” generation=0 for conditional create
    except Exception as e:
        log.warning(f"gcs_download_with_gen {path} failed: {e}")
    return None, None

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

def gcs_upload_conditional(path, data, if_generation_match):
    """Upload with optimistic concurrency. Returns True on success, False if
    precondition failed (someone else wrote first), None on other errors.

    if_generation_match: the generation string returned by gcs_download_with_gen
    when we read the object, OR "0" to mean "object must not yet exist", OR
    None to skip the precondition entirely (unsafe â€” only for migrations).
    """
    try:
        tok = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=3
        ).json().get("access_token", "")
        if not tok: return None
        params = {"uploadType": "media", "name": path}
        if if_generation_match is not None:
            params["ifGenerationMatch"] = str(if_generation_match)
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o",
            params=params,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(data, default=str), timeout=15
        )
        if r.status_code in (200, 201):
            return True
        if r.status_code == 412:  # precondition failed â€” someone else wrote
            return False
        log.warning(f"gcs_upload_conditional {path}: {r.status_code} {r.text[:200]}")
        return None
    except Exception as e:
        log.warning(f"gcs_upload_conditional {path} failed: {e}")
        return None

def _load_scan_composites():
    """Track D.1 - read latest_<region>.json from GCS for sp500/nasdaq/russell2000.

    Returns {SYMBOL: {composite, signal, price, _region}}.
    Later regions overwrite earlier on collision (rare). Empty dict on
    failure - callers fall back to local compute.

    This is the single source of truth for the composite across the app:
    portfolio page / stock page / screener page all eventually trace their
    composite value back to these JSON files.
    """
    out = {}
    for region in ("global", "nasdaq", "sp500"):
        data = gcs_download(f"scans/latest_{region}.json")
        if not data:
            log.warning(f"Scan snapshot scans/latest_{region}.json not found - monitor will fall back to local compute for that region")
            continue
        stocks = data.get("stocks") if isinstance(data, dict) else data
        if not isinstance(stocks, list):
            continue
        n = 0
        for s in stocks:
            if not isinstance(s, dict):
                continue
            sym = s.get("symbol")
            if not sym:
                continue
            out[str(sym).upper()] = {
                "composite": s.get("composite"),
                "signal": s.get("signal"),
                "price": s.get("price"),
                "_region": region,
            }
            n += 1
        log.info(f"Loaded {n} composites from scans/latest_{region}.json")
    return out

def load_state():
    """Load portfolio state from GCS, fallback to local file.

    v7.2: normalizes schema on load â€” adds any missing top-level keys so
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
# Import scoring functions from screener_v6 (CRUD-only: just need quotes
# for add_position entry composite and list_positions live display)
# ---------------------------------------------------------------------------

try:
    from screener_v6 import get_quotes_batch
    log.info("Imported get_quotes_batch from screener_v6")
except ImportError as e:
    log.error(f"Cannot import screener_v6: {e}")
    log.error("Place monitor_v7.py in the same directory as screener_v6.py")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Portfolio CRUD Operations
# ---------------------------------------------------------------------------

def add_position(state, symbol, entry_price, shares=0, notes="", **kwargs):
    """Add a new position or update existing one."""
    symbol = symbol.upper()
    existing = [p for p in state["positions"] if p["symbol"] == symbol and p.get("asset_type", "stock") == kwargs.get("asset_type", "stock")]
    if existing:
        log.info(f"Updating existing position: {symbol}")
        pos = existing[0]
        pos["entry_price"] = entry_price
        pos["shares"] = shares or pos.get("shares", 0)
        pos["notes"] = notes or pos.get("notes", "")
        pos.update(kwargs)
    else:
        # Get current price for entry tracking (composite will be
        # backfilled from scan snapshots by monitor_prices.py)
        quotes = get_quotes_batch([symbol])
        q = quotes.get(symbol)

        pos = {
            "symbol": symbol,
            "entry_price": entry_price or (q["price"] if q else 0),
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
            "entry_composite": 0,
            "shares": shares,
            "peak_price": entry_price or (q["price"] if q else 0),
            "notes": notes,
        }
        pos.update(kwargs)
        state["positions"].append(pos)
        log.info(f"Added position: {symbol} @ ${entry_price:.2f}")
    return state

def remove_position(state, symbol, exit_price=None, reason="Manual removal", **kwargs):
    """Remove a position and record in history."""
    symbol = symbol.upper()
    asset_type = kwargs.get("asset_type", "stock")
    pos = [p for p in state["positions"] if p["symbol"] == symbol and p.get("asset_type", "stock") == asset_type]
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
        **kwargs
    })
    state["history"] = state["history"][-100:]  # keep last 100

    state["positions"] = [p for p in state["positions"] if p["symbol"] != symbol or p.get("asset_type", "stock") != asset_type]
    log.info(f"Removed position: {symbol} | PnL: {pnl:+.1f}%")
    return state

# ---------------------------------------------------------------------------
# Atomic portfolio transactions (v7.2)
#
# These wrap add_position / remove_position with optimistic concurrency control.
# Why: Cloud Run's ThreadingHTTPServer can process POSTs concurrently, and
# Cloud Run itself can run multiple instances. Without conditional writes, two
# concurrent add/close requests both read state, both mutate their own copy,
# and the second upload silently overwrites the first â€” positions vanish.
#
# With gcs_upload_conditional(..., if_generation_match=gen), the write fails
# with 412 if the object changed since we read it. We retry the entire
# read-modify-write cycle up to 3 times. This is cheap for the portfolio
# workload (1-10 positions, tiny JSON, handful of writes per day).
# ---------------------------------------------------------------------------

def apply_atomic(mutate_fn, max_retries: int = 3):
    """Load state, apply mutate_fn, save atomically. Retry on generation
    conflict. mutate_fn takes (state) and returns (state, result_info).

    result_info is a dict returned to the caller (e.g. {'position': {...}}
    or {'ok': True}). Returns (state_after, result_info) on success, raises
    RuntimeError after max_retries exhausted.
    """
    import time as _time
    last_error = None
    for attempt in range(max_retries):
        state, gen = gcs_download_with_gen(STATE_PATH)

        # Normalize shape (same as load_state does)
        if state is None:
            state = {"positions": [], "history": [], "last_monitor": ""}
            gen = "0"  # object doesn't exist yet â€” require "create only"
        state.setdefault("positions", [])
        state.setdefault("history", [])
        state.setdefault("last_monitor", "")

        # Apply the mutation
        state, result_info = mutate_fn(state)
        state["last_updated"] = datetime.now().isoformat()

        # Conditional write
        # gen=None means we couldn't get a generation â€” fall back to unconditional
        # write. This is the local-dev path where there's no metadata service.
        if gen is None:
            if gcs_upload(STATE_PATH, state):
                log.info(f"State saved to GCS (unconditional â€” local dev)")
                return state, result_info
            raise RuntimeError("gcs_upload failed (local dev fallback)")

        outcome = gcs_upload_conditional(STATE_PATH, state, if_generation_match=gen)
        if outcome is True:
            log.info(f"State saved to GCS (gen={gen}, attempt {attempt+1})")
            # Also persist locally as a debug trail (ephemeral on Cloud Run).
            try:
                with open(LOCAL_STATE, "w") as f:
                    json.dump(state, f, indent=2, default=str)
            except Exception:
                pass
            return state, result_info
        elif outcome is False:
            last_error = "precondition_failed"
            log.warning(f"State write conflict on attempt {attempt+1}/{max_retries} "
                        f"(gen={gen} no longer current) â€” retrying")
            _time.sleep(0.15 * (attempt + 1))  # small backoff
            continue
        else:
            last_error = "upload_error"
            log.warning(f"State write error on attempt {attempt+1}/{max_retries} â€” retrying")
            _time.sleep(0.15 * (attempt + 1))
            continue

    raise RuntimeError(f"apply_atomic exhausted {max_retries} retries: {last_error}")


def add_position_atomic(symbol, entry_price, shares=0, notes="", **kwargs):
    """Atomic wrapper around add_position. Read-modify-write with retry.
    Returns the final state + dict with the new/updated position."""
    def _mutate(state):
        state = add_position(state, symbol, entry_price, shares=shares, notes=notes, **kwargs)
        pos = next((p for p in state["positions"] if p["symbol"].upper() == symbol.upper() and p.get("asset_type", "stock") == kwargs.get("asset_type", "stock")), {})
        return state, {"position": pos}
    return apply_atomic(_mutate)


def remove_position_atomic(symbol, exit_price=None, reason="Manual removal", **kwargs):
    """Atomic wrapper around remove_position. Returns final state + dict with
    removal result. Distinguishes 'not found' from 'removed'."""
    def _mutate(state):
        before = len(state.get("positions", []))
        state = remove_position(state, symbol, exit_price=exit_price, reason=reason, **kwargs)
        after = len(state.get("positions", []))
        return state, {
            "removed": before != after,
            "symbol": symbol.upper(),
            "positions_remaining": after,
        }
    return apply_atomic(_mutate)

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
    print(f"  PORTFOLIO â€” {len(positions)} positions")
    print(f"  {'='*85}")
    print(f"  {'Sym':<8} {'Entry':>8} {'Current':>8} {'PnL':>7} {'Days':>5} "
          f"{'Entry Comp':>10} {'Last Comp':>10} {'Signal':<10}")
    print(f"  {'â”€'*85}")

    total_pnl = 0
    for p in positions:
        q = quotes.get(p["symbol"], {})
        current = q.get("price", 0)
        pnl = ((current - p["entry_price"]) / p["entry_price"] * 100) if p["entry_price"] > 0 and current > 0 else 0
        days = (datetime.now() - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days if p.get("entry_date") else 0
        emoji = "ðŸŸ¢" if pnl > 0 else "ðŸ”´"
        total_pnl += pnl

        print(f"  {p['symbol']:<8} ${p['entry_price']:>7.2f} ${current:>7.2f} {pnl:>+6.1f}% {days:>4}d "
              f"{p.get('entry_composite', 0):>9.3f} {p.get('last_composite', 0):>9.3f} "
              f"{p.get('last_signal', '?'):<10} {emoji}")

    avg_pnl = total_pnl / len(positions) if positions else 0
    print(f"  {'â”€'*85}")
    print(f"  Average PnL: {avg_pnl:+.1f}% across {len(positions)} positions")

    # History summary
    hist = state.get("history", [])
    if hist:
        recent = hist[-5:]
        print(f"\n  Last {len(recent)} exits:")
        for h in recent:
            print(f"    {h['date']} {h['symbol']:<8} {h.get('pnl_pct', 0):+.1f}% â€” {h.get('reason', '')}")

# ---------------------------------------------------------------------------
# Main (CRUD-only CLI â€” scoring removed, handled by monitor_prices.py)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Portfolio Monitor v8 (CRUD-only)")
    parser.add_argument("--add", metavar="SYMBOL", help="Add a position")
    parser.add_argument("--entry-price", type=float, default=0, help="Entry price for --add")
    parser.add_argument("--shares", type=int, default=0, help="Number of shares for --add")
    parser.add_argument("--notes", default="", help="Notes for --add")
    parser.add_argument("--remove", metavar="SYMBOL", help="Remove a position")
    parser.add_argument("--exit-price", type=float, default=0, help="Exit price for --remove")
    parser.add_argument("--list", action="store_true", help="List all positions")
    parser.add_argument("--seed", metavar="FILE", help="Seed portfolio from JSON file")
    args = parser.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set!")
        sys.exit(1)

    state = load_state()

    # â”€â”€â”€ Seed from file â”€â”€â”€
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

    # â”€â”€â”€ Add position â”€â”€â”€
    if args.add:
        state = add_position(state, args.add, args.entry_price, args.shares, args.notes)
        save_state(state)
        print(f"âœ… Added {args.add.upper()}")
        list_positions(state)
        return

    # â”€â”€â”€ Remove position â”€â”€â”€
    if args.remove:
        state = remove_position(state, args.remove, args.exit_price)
        save_state(state)
        print(f"âœ… Removed {args.remove.upper()}")
        list_positions(state)
        return

    # â”€â”€â”€ List positions â”€â”€â”€
    if args.list:
        list_positions(state)
        return

    print("Usage: python monitor_v7.py --add SYMBOL --entry-price 100 --shares 10")
    print("       python monitor_v7.py --remove SYMBOL --exit-price 120")
    print("       python monitor_v7.py --list")


if __name__ == "__main__":
    main()

