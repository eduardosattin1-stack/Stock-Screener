#!/usr/bin/env python3
"""
ibkr_portfolio_sync.py — mirror the real Interactive Brokers account into the
Portfolio page.

Runs on the IB Gateway host (Bruno's always-on PC), exactly like
ibkr_options_batch.py: it reaches OUT to GCS, reads the current
portfolio/state.json, reconciles it against the live IBKR account
(ib.portfolio() + account values), and writes the merged state back with an
optimistic-concurrency (ifGenerationMatch) conditional write so it never
clobbers monitor_prices.py's nightly enrichment.

IBKR is the source of truth: positions that appear in IBKR are added, ones that
vanish are closed to history. Manual (non-`ib_synced`) rows are left untouched,
so paper/screener positions can coexist. Read-only throughout — `readonly=True`,
no order API is ever imported.

GCS auth: `gcloud auth print-access-token` (the PC is logged in via gcloud), with
a GCE-metadata fallback so it also works if ever run on Cloud Run. Mirrors
monitor_prices._get_token — NOT monitor_v7.apply_atomic, which is metadata-only
and fails on the PC.

CLI:
  python ibkr_portfolio_sync.py --dry-run        # connect, print the diff, write nothing
  python ibkr_portfolio_sync.py --once           # one live sync to GCS
  python ibkr_portfolio_sync.py --from-json positions.json --dry-run
        # offline: reconcile against a saved get_account_positions JSON
        # (the MCP/Client-Portal shape) — no gateway needed, for tests/verify
"""
from __future__ import annotations
import os, sys, re, json, time, argparse, logging, platform, subprocess
from datetime import datetime, timezone

import requests

log = logging.getLogger("ibkr_portfolio_sync")

import ibkr_symbol_map as smap

BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
STATE_PATH = "portfolio/state.json"
HISTORY_KEEP = 100

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


# ─────────────────────────────────────────────────────────────────────────
# GCS — gcloud-token auth + optimistic-concurrency state write
# ─────────────────────────────────────────────────────────────────────────
def _token() -> str | None:
    """Access token: GCE metadata first (Cloud Run), then `gcloud auth
    print-access-token` (the gateway PC). Same strategy as monitor_prices."""
    try:
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=2)
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:
        pass
    try:
        cmd = "gcloud.cmd" if platform.system() == "Windows" else "gcloud"
        proc = subprocess.run([cmd, "auth", "print-access-token"],
                              capture_output=True, text=True, check=True)
        return proc.stdout.strip()
    except Exception as e:
        log.error("no GCS token (metadata + gcloud both failed): %s", e)
        return None


def _read_state_with_gen():
    """Return (state, generation). generation is the GCS object generation string
    for the conditional write, "0" if the object doesn't exist, or None if we
    couldn't authenticate (caller then writes unconditionally as a last resort)."""
    tok = _token()
    if not tok:
        # public read, no generation -> unconditional write fallback
        try:
            r = requests.get(f"https://storage.googleapis.com/{BUCKET}/{STATE_PATH}", timeout=15)
            return (r.json() if r.ok else None), None
        except Exception:
            return None, None
    enc = STATE_PATH.replace("/", "%2F")
    try:
        meta = requests.get(
            f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{enc}",
            headers={"Authorization": f"Bearer {tok}"}, params={"alt": "json"}, timeout=15)
        if meta.status_code == 404:
            return None, "0"
        if meta.status_code == 200:
            gen = meta.json().get("generation", "0")
            media = requests.get(
                f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{enc}",
                headers={"Authorization": f"Bearer {tok}"}, params={"alt": "media"}, timeout=15)
            if media.status_code == 200:
                return media.json(), gen
    except Exception as e:
        log.warning("state read failed: %s", e)
    return None, None


def _write_state_conditional(data, gen) -> bool | None:
    """Conditional upload. True=ok, False=precondition lost (412), None=error."""
    tok = _token()
    if not tok:
        return None
    params = {"uploadType": "media", "name": STATE_PATH, "cacheControl": "no-cache, max-age=0"}
    if gen is not None:
        params["ifGenerationMatch"] = str(gen)
    try:
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o",
            params=params,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            data=json.dumps(data, default=str, indent=2), timeout=25)
        if r.status_code in (200, 201):
            return True
        if r.status_code == 412:
            return False
        log.warning("state write %s: %s", r.status_code, r.text[:200])
        return None
    except Exception as e:
        log.warning("state write failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────
# IBKR -> normalized rows
# ─────────────────────────────────────────────────────────────────────────
def _fmt_exp(yyyymmdd: str) -> str | None:
    """'20270115' -> '2027-01-15'."""
    s = (yyyymmdd or "").strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _row_from_ib_item(item) -> dict | None:
    """Map one ib_async PortfolioItem -> normalized row (per-unit prices)."""
    c = item.contract
    sec = getattr(c, "secType", "") or ""
    conid = int(getattr(c, "conId", 0) or 0)
    currency = (getattr(c, "currency", "") or "USD").upper()
    exch = getattr(c, "exchange", None)
    primary = getattr(c, "primaryExchange", None)
    pos = float(getattr(item, "position", 0) or 0)
    mkt_px = float(getattr(item, "marketPrice", 0) or 0)
    mkt_val = float(getattr(item, "marketValue", 0) or 0)
    avg = float(getattr(item, "averageCost", 0) or 0)
    upnl = float(getattr(item, "unrealizedPNL", 0) or 0)

    if sec == "OPT":
        mult = float(getattr(c, "multiplier", "") or 100)
        under = getattr(c, "symbol", "") or ""
        app, unmapped = smap.map_option_underlying(under, exch, primary, currency, conid)
        right = "CALL" if (getattr(c, "right", "") or "").upper().startswith("C") else "PUT"
        return {
            "ib_conid": conid, "symbol": app, "asset_type": "option", "currency": currency,
            "position": pos, "avg_cost": (avg / mult if mult else avg), "market_price": mkt_px,
            "market_value": mkt_val, "unrealized_pnl": upnl, "multiplier": mult,
            "right": right, "strike": float(getattr(c, "strike", 0) or 0),
            "expiration": _fmt_exp(getattr(c, "lastTradeDateOrContractMonth", "")),
            "unmapped": unmapped, "ib_symbol": under,
        }
    # stock / other -> treat as a stock row
    sym = getattr(c, "symbol", "") or ""
    app, unmapped = smap.map_stock(sym, exch, primary, currency, conid)
    return {
        "ib_conid": conid, "symbol": app, "asset_type": "stock", "currency": currency,
        "position": pos, "avg_cost": avg, "market_price": mkt_px, "market_value": mkt_val,
        "unrealized_pnl": upnl, "multiplier": None, "right": None, "strike": None,
        "expiration": None, "unmapped": unmapped, "ib_symbol": sym,
    }


def _row_from_position(pos):
    """Fallback adapter: ib_async Position (no live marks) -> normalized row, by
    shimming it into the PortfolioItem shape (mark = avg cost, so pnl = 0). Used
    only if portfolio() never populates — a marks-less mirror beats no mirror."""
    c = pos.contract
    mult = float(getattr(c, "multiplier", "") or (100 if getattr(c, "secType", "") == "OPT" else 1))

    class _Shim:
        contract = c
        position = pos.position
        averageCost = pos.avgCost
        marketPrice = (pos.avgCost / mult) if mult else pos.avgCost
        marketValue = pos.position * pos.avgCost
        unrealizedPNL = 0.0
    return _row_from_ib_item(_Shim())


def _account_summary_from_values(values) -> dict:
    """Build the headline summary from ib_async AccountValue rows. IB reports
    balances (NetLiquidation/TotalCashValue/…) once, in the base currency code
    (e.g. EUR) with NO 'BASE' row — that single row IS the consolidated total. But
    UnrealizedPnL/RealizedPnL come per-currency PLUS a literal 'BASE' row that is
    the all-currency total converted to base — so for those we must take 'BASE',
    not the base-currency-code row (which is that currency's slice only)."""
    by_tag: dict[str, dict[str, str]] = {}
    for v in values:
        by_tag.setdefault(v.tag, {})[v.currency] = v.value

    base_ccy = next((c for c in by_tag.get("NetLiquidation", {}) if c not in ("", "BASE")), None)

    def num(tag, prefer_base=False):
        d = by_tag.get(tag, {})
        if not d:
            return None
        if prefer_base and "BASE" in d:
            val = d["BASE"]
        else:
            val = next((v for c, v in d.items() if c not in ("", "BASE")), d.get("BASE"))
        try:
            return round(float(val), 2)
        except Exception:
            return None

    return {
        "currency": base_ccy,
        "net_liquidation": num("NetLiquidation"),
        "total_cash": num("TotalCashValue"),
        "gross_position_value": num("GrossPositionValue"),
        "unrealized_pnl": num("UnrealizedPnL", prefer_base=True),   # all-currency total in base
        "realized_pnl": num("RealizedPnL", prefer_base=True),
        "available_funds": num("AvailableFunds"),
    }


def fetch_account(client_id: int) -> tuple[list[dict], dict]:
    """Connect read-only to IB Gateway, return (rows, account_summary)."""
    import ibkr_options  # reuse host/port + readonly connect pattern
    try:
        from ib_async import IB
    except Exception:
        from ib_insync import IB
    ib = IB()
    ib.connect(ibkr_options.IB_HOST, ibkr_options.IB_PORT, clientId=client_id,
               timeout=20, readonly=True)
    ib.RequestTimeout = 30
    try:
        # ib_async auto-starts the account-update stream on connect; portfolio()
        # populates within a second or two. Do NOT call reqAccountUpdates() — on a
        # single managed account it blocks until accountDownloadEnd and times out.
        items = ib.portfolio()
        for _ in range(8):               # give streaming a moment to populate
            if items:
                break
            ib.sleep(1.0)
            items = ib.portfolio()
        rows = [r for r in (_row_from_ib_item(it) for it in items) if r]
        if not rows:                     # fallback: positions() (no live marks) so a mirror still happens
            log.warning("portfolio() empty — falling back to ib.positions() (no live marks)")
            rows = [r for r in (_row_from_position(p) for p in ib.positions()) if r]
        summary = _account_summary_from_values(ib.accountValues())
        log.info("IBKR: %d portfolio rows, net_liq=%s %s",
                 len(rows), summary.get("net_liquidation"), summary.get("currency"))
        return rows, summary
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────
# Offline adapter: get_account_positions (MCP / Client-Portal shape) -> rows
# Used by --from-json for tests/verification without a gateway.
# ─────────────────────────────────────────────────────────────────────────
_OPT_RE = re.compile(
    r"^(?P<sym>\S+)\s+(?:(?P<venue>[A-Z0-9.]+)\s+)?"
    r"(?P<mon>[A-Z][a-z]{2})(?P<day>\d{1,2})'(?P<yy>\d{2})\s+"
    r"(?P<strike>[\d.]+)\s+(?P<right>CALL|PUT)(?:\s+\([^)]*\))?\s+@(?P<exch>\S+)$")


def _row_from_mcp_position(p: dict) -> dict | None:
    desc = (p.get("contract_description") or "").strip()
    conid = int(p.get("contract_id") or 0)
    currency = (p.get("currency") or "USD").upper()
    pos = float(p.get("position") or 0)
    mkt_px = float(p.get("market_price") or 0)
    mkt_val = float(p.get("market_value") or 0)
    avg = float(p.get("average_price") or 0)
    upnl = float(p.get("unrealized_pnl") or 0)
    cls = (p.get("asset_class") or "STK").upper()

    if cls == "OPT":
        m = _OPT_RE.match(desc)
        if not m:
            log.warning("could not parse option description: %r", desc)
            return None
        under = m.group("sym")
        venue = m.group("venue") or m.group("exch")
        app, unmapped = smap.map_option_underlying(under, venue, None, currency, conid)
        mon = _MONTHS.get(m.group("mon"))
        exp = f"20{m.group('yy')}-{mon:02d}-{int(m.group('day')):02d}" if mon else None
        return {
            "ib_conid": conid, "symbol": app, "asset_type": "option", "currency": currency,
            "position": pos, "avg_cost": avg, "market_price": mkt_px, "market_value": mkt_val,
            "unrealized_pnl": upnl, "multiplier": 100.0,
            "right": m.group("right"), "strike": float(m.group("strike")),
            "expiration": exp, "unmapped": unmapped, "ib_symbol": under,
        }
    sym = desc.split()[0] if desc else ""
    venue = desc.split("@")[1].strip() if "@" in desc else None
    app, unmapped = smap.map_stock(sym, venue, None, currency, conid)
    return {
        "ib_conid": conid, "symbol": app, "asset_type": "stock", "currency": currency,
        "position": pos, "avg_cost": avg, "market_price": mkt_px, "market_value": mkt_val,
        "unrealized_pnl": upnl, "multiplier": None, "right": None, "strike": None,
        "expiration": None, "unmapped": unmapped, "ib_symbol": sym,
    }


def rows_from_mcp_json(obj) -> list[dict]:
    positions = obj.get("positions") if isinstance(obj, dict) else obj
    return [r for r in (_row_from_mcp_position(p) for p in (positions or [])) if r]


# ─────────────────────────────────────────────────────────────────────────
# Reconcile (pure) — field-level merge, never whole-object replace
# ─────────────────────────────────────────────────────────────────────────
def _base_fields(r: dict, today: str) -> dict:
    d = {
        "symbol": r["symbol"], "asset_type": r["asset_type"],
        "shares": r["position"], "entry_price": round(r["avg_cost"], 4),
        "entry_date": today, "last_price": round(r["market_price"], 4),
        "last_updated": today, "ib_unrealized_pnl": round(r["unrealized_pnl"], 2),
        "market_value": round(r["market_value"], 2), "currency": r["currency"],
        "ib_conid": r["ib_conid"], "ib_synced": True, "peak_price": round(r["avg_cost"], 4),
        "notes": "", "bucket": None,
    }
    if r["asset_type"] == "option":
        rt = (r.get("right") or "").upper()
        d.update({
            "right": rt, "strike": r.get("strike"), "expiration": r.get("expiration"),
            "multiplier": r.get("multiplier"), "contracts": r["position"],
            "strategy": f"{rt} {r.get('strike')}".strip(),
            "strikes": (f"{r.get('strike')}{rt[:1]}" if rt else None),
        })
    return d


def reconcile(state: dict, rows: list[dict], summary: dict | None, today: str) -> tuple[dict, dict]:
    state.setdefault("positions", [])
    state.setdefault("history", [])
    by_conid = {p["ib_conid"]: p for p in state["positions"] if p.get("ib_conid")}
    counts = {"added": 0, "updated": 0, "closed": 0, "unmapped": 0, "ib_rows": len(rows)}
    seen: set[int] = set()

    for r in rows:
        if abs(r["position"]) < 1e-9:
            continue
        if r.get("unmapped"):
            counts["unmapped"] += 1
        ex = by_conid.get(r["ib_conid"])
        if ex:
            ex["symbol"] = r["symbol"]            # refresh so a corrected CONID_OVERRIDE propagates
            ex["shares"] = r["position"]
            ex["entry_price"] = round(r["avg_cost"], 4)
            ex["last_price"] = round(r["market_price"], 4)
            ex["last_updated"] = today
            ex["ib_unrealized_pnl"] = round(r["unrealized_pnl"], 2)
            ex["market_value"] = round(r["market_value"], 2)
            ex["currency"] = r["currency"]
            ex["asset_type"] = r["asset_type"]
            ex["ib_synced"] = True
            if r["asset_type"] == "option":
                ex["multiplier"] = r.get("multiplier")
                ex["contracts"] = r["position"]
            counts["updated"] += 1
        else:
            state["positions"].append(_base_fields(r, today))
            counts["added"] += 1
        seen.add(r["ib_conid"])

    # Close vanished IBKR positions. FAIL-SAFE: only run when we actually got
    # rows back — an empty/garbled fetch must never flatten the book.
    if rows:
        survivors = []
        for p in state["positions"]:
            if p.get("ib_conid") in seen or not p.get("ib_synced"):
                survivors.append(p)
                continue
            entry = float(p.get("entry_price") or 0)
            exit_px = float(p.get("last_price") or entry)
            pnl = ((exit_px - entry) / entry * 100) if entry else 0
            days = 0
            ed = (p.get("entry_date") or "")[:10]
            if ed:
                try:
                    days = (datetime.fromisoformat(today) - datetime.fromisoformat(ed)).days
                except Exception:
                    days = 0
            state["history"].append({
                "symbol": p["symbol"], "action": "REMOVED", "date": today,
                "entry_price": entry, "entry_date": p.get("entry_date"),
                "exit_price": round(exit_px, 4), "pnl_pct": round(pnl, 1),
                "reason": "IBKR: position closed", "days_held": days,
                "asset_type": p.get("asset_type", "stock"), "bucket": p.get("bucket"),
            })
            counts["closed"] += 1
        state["positions"] = survivors
        # IBKR owns the book: drop any manual (non-synced) row that shadows a synced
        # symbol+asset_type — e.g. an old paper "CMCSA" duplicating the real IBKR
        # CMCSA holding. The synced row is authoritative; the manual one is stale.
        synced_keys = {(p["symbol"].upper(), p.get("asset_type", "stock"))
                       for p in state["positions"] if p.get("ib_synced")}
        deduped = [p for p in state["positions"] if p.get("ib_synced")
                   or (p.get("symbol", "").upper(), p.get("asset_type", "stock")) not in synced_keys]
        counts["deduped"] = len(state["positions"]) - len(deduped)
        state["positions"] = deduped
        state["history"] = state["history"][-HISTORY_KEEP:]
    else:
        log.warning("0 IBKR rows — skipping close pass (fail-safe), positions untouched")

    if summary:
        state["account_summary"] = summary
    state["ibkr_sync"] = {
        "last_sync": datetime.now(timezone.utc).isoformat(), "source": "ib_gateway", **counts,
    }
    state["last_updated"] = datetime.now().isoformat()
    return state, counts


# ─────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────
def _diff_log(rows: list[dict], counts: dict):
    log.info("── reconcile summary ──  added=%(added)d updated=%(updated)d "
             "closed=%(closed)d unmapped=%(unmapped)d (ib_rows=%(ib_rows)d)", counts)
    for r in rows:
        tag = "  ?" if r.get("unmapped") else "   "
        if r["asset_type"] == "option":
            log.info("%s %-10s OPT %s %s %s  x%-6g avg=%.4f mark=%.4f uPnL=%.0f %s",
                     tag, r["symbol"], r.get("right"), r.get("strike"), r.get("expiration"),
                     r["position"], r["avg_cost"], r["market_price"], r["unrealized_pnl"], r["currency"])
        else:
            log.info("%s %-10s STK            x%-6g avg=%.4f mark=%.4f uPnL=%.0f %s",
                     tag, r["symbol"], r["position"], r["avg_cost"], r["market_price"],
                     r["unrealized_pnl"], r["currency"])


def run_sync(dry_run: bool = False, from_json: str | None = None, client_id: int = 18) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")

    if from_json:
        with open(from_json) as f:
            rows = rows_from_mcp_json(json.load(f))
        summary = None
        log.info("loaded %d rows from %s (offline)", len(rows), from_json)
    else:
        rows, summary = fetch_account(client_id)

    if dry_run:
        state = _read_state_with_gen()[0] or {"positions": [], "history": []}
        merged, counts = reconcile(json.loads(json.dumps(state)), rows, summary, today)
        _diff_log(rows, counts)
        log.info("[DRY-RUN] no write. resulting positions=%d history=%d",
                 len(merged["positions"]), len(merged["history"]))
        return counts

    last_err = None
    for attempt in range(3):
        state, gen = _read_state_with_gen()
        if state is None:
            state, gen = {"positions": [], "history": []}, (gen or "0")
        merged, counts = reconcile(state, rows, summary, today)
        outcome = _write_state_conditional(merged, gen)
        if outcome is True:
            _diff_log(rows, counts)
            log.info("DONE — wrote state.json (gen=%s, attempt %d)", gen, attempt + 1)
            return counts
        last_err = "precondition" if outcome is False else "error"
        log.warning("state write %s on attempt %d — retrying", last_err, attempt + 1)
        time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"ibkr sync exhausted retries: {last_err}")


def main():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    ap = argparse.ArgumentParser(description="Mirror IBKR account into portfolio/state.json")
    ap.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    ap.add_argument("--once", action="store_true", help="run one live sync")
    ap.add_argument("--from-json", metavar="FILE",
                    help="offline: reconcile against a saved get_account_positions JSON")
    ap.add_argument("--client-id", type=int, default=int(os.environ.get("IB_PORTFOLIO_CLIENT_ID", "18")),
                    help="IB Gateway clientId (default 18; keep distinct from the options batch's 17)")
    a = ap.parse_args()
    if not (a.once or a.dry_run or a.from_json):
        ap.error("pass --once (live write), --dry-run, or --from-json FILE")
    counts = run_sync(dry_run=a.dry_run or bool(a.from_json and not a.once),
                      from_json=a.from_json, client_id=a.client_id)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
