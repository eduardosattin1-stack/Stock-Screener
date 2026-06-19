"""
ibkr_options_batch.py — runs on the IB Gateway host (Bruno's always-on PC).

No tunnel / no inbound exposure: the PC reaches OUT to GCS. Reads the latest scan
+ portfolio from GCS, fetches options (via the local IB Gateway) for the portfolio
holdings + the top-N US/EU names, and uploads scans/options_latest.json to GCS.
The frontend stock page reads that file and renders the Options Intelligence card.

Spot is taken from the scan (FMP price) and passed to enrich(), so only the OPTION
market-data feed is needed (no EU underlying data sub). One IB connection is reused
across all symbols, throttled to stay under IBKR's 60-historical-requests/10-min pacing.

Run once:   python backend/ibkr_options_batch.py
Schedule:   Windows Task Scheduler every few hours, OR a terminal loop:
            while ($true) { python backend/ibkr_options_batch.py; Start-Sleep 14400 }

Env: IB_GATEWAY_PORT (4001) · OPT_TOP_N (60) · OPT_SLEEP_S (11) · GCS auth via the
machine's logged-in `gcloud` (gcloud auth print-access-token).
"""
from __future__ import annotations
import os, sys, json, logging, subprocess
from datetime import datetime, timezone

import requests
import ibkr_options
from ibkr_options import enrich, _connect

log = logging.getLogger("ibkr_batch")
BUCKET = "screener-signals-carbonbridge"
TOP_N = int(os.environ.get("OPT_TOP_N", "60"))
SLEEP_S = float(os.environ.get("OPT_SLEEP_S", "11"))   # ~5.5 hist-req/min < 60/10min limit
FW = {"momentum": 25, "quality": 20, "growth": 20, "value": 20, "smart_money": 15}

# FMP symbol suffix -> (IBKR exchange, currency). US has no suffix -> SMART/USD.
SUFFIX = {
    ".PA": ("SBF", "EUR"), ".AS": ("AEB", "EUR"), ".BR": ("ENEXT.BE", "EUR"),
    ".MI": ("BVME", "EUR"), ".DE": ("IBIS", "EUR"), ".F": ("IBIS", "EUR"),
    ".L": ("LSE", "GBP"), ".SW": ("EBS", "CHF"), ".MC": ("BM", "EUR"),
    ".LS": ("BVL", "EUR"), ".VI": ("VSE", "EUR"), ".HE": ("HEX", "EUR"),
    ".ST": ("SFB", "SEK"), ".CO": ("CPH", "DKK"), ".OL": ("OSE", "NOK"),
}


def _gcs_read(path: str, default=None):
    try:
        r = requests.get(f"https://storage.googleapis.com/{BUCKET}/{path}", timeout=90)
        return r.json() if r.ok else default
    except Exception as e:
        log.warning("GCS read %s failed: %s", path, e)
        return default


def _gcs_write(path: str, data: dict) -> bool:
    token = subprocess.check_output("gcloud auth print-access-token", shell=True, text=True).strip()
    r = requests.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o",
        params={"uploadType": "media", "name": path},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(data), timeout=60,
    )
    if not r.ok:
        log.error("GCS write %s -> %s %s", path, r.status_code, r.text[:200])
    return r.ok


def _composite(s: dict) -> float:
    f = s.get("factors_v8_momentum") or s.get("factors_v8") or {}
    num = den = 0.0
    for k, w in FW.items():
        v = f.get(k)
        if v is not None:
            num += v * w; den += w
    return num / den if den else 0.0


def _map_contract(symbol: str):
    """FMP symbol -> (ibkr_symbol, exchange, currency) or None if unsupported."""
    for suf, (ex, cur) in SUFFIX.items():
        if symbol.endswith(suf):
            return symbol[: -len(suf)], ex, cur
    if "." not in symbol:
        return symbol, "SMART", "USD"
    return None  # e.g. .HK / .KS / .T — no US/EU options path


def build_targets() -> list[tuple]:
    scan = _gcs_read("scans/latest_global.json", {})
    stocks = scan.get("stocks") or (scan if isinstance(scan, list) else [])
    by_sym = {s.get("symbol"): s for s in stocks if s.get("symbol")}
    port = _gcs_read("portfolio/state.json", {}) or {}
    port_syms = [p.get("symbol") for p in (port.get("positions") or []) if p.get("symbol")]

    targets, seen = [], set()

    def add(s):
        sym = s.get("symbol")
        if not sym or sym in seen:
            return
        m = _map_contract(sym)
        if not m:
            return
        ib_sym, ex, cur = m
        seen.add(sym)
        targets.append((sym, ib_sym, ex, cur, s.get("price")))

    for sym in port_syms:               # always cover holdings
        if sym in by_sym:
            add(by_sym[sym])
    for s in sorted(stocks, key=_composite, reverse=True):   # then top-N by composite
        if len(targets) >= TOP_N + len(port_syms):
            break
        add(s)
    return targets


def main():
    targets = build_targets()
    log.info("targets: %d (top_n=%d, sleep=%.0fs)", len(targets), TOP_N, SLEEP_S)
    if not targets:
        log.error("no targets — scan/portfolio unreadable?"); sys.exit(1)

    ib = _connect()
    options: dict = {}
    ok = 0
    try:
        for i, (fmp_sym, ib_sym, ex, cur, spot) in enumerate(targets, 1):
            try:
                data = enrich(ib_sym, ex, cur, spot, ib=ib)
            except Exception as e:
                log.warning("[%d/%d] %s failed: %s", i, len(targets), fmp_sym, e)
                ib.sleep(SLEEP_S); continue
            if data.get("iv_current") is not None or data.get("spread"):
                options[fmp_sym] = data   # key by FMP symbol (what the frontend uses)
                ok += 1
                log.info("[%d/%d] %s OK iv=%s rank=%s spread=%s", i, len(targets), fmp_sym,
                         data.get("iv_current"), data.get("iv_rank"), bool(data.get("spread")))
            else:
                log.info("[%d/%d] %s no data", i, len(targets), fmp_sym)
            ib.sleep(SLEEP_S)   # pacing
    finally:
        ib.disconnect()

    payload = {"updated": datetime.now(timezone.utc).isoformat(), "count": ok, "options": options}
    if _gcs_write("scans/options_latest.json", payload):
        log.info("uploaded scans/options_latest.json — %d/%d names with options", ok, len(targets))
    else:
        log.error("upload failed"); sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    main()
