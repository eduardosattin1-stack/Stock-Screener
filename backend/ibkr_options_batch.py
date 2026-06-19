"""
ibkr_options_batch.py — nightly FULL-UNIVERSE options enrichment, run on the IB
Gateway host (Bruno's always-on PC). No tunnel: the PC reaches OUT to GCS.

Reads the latest scan from GCS, and for EVERY options-eligible name (US + mapped
EU) pulls ATM IV + greeks + a bull-call spread from IBKR MARKET DATA (enrich_fast,
no paced historical calls), appends the ATM IV to that symbol's GCS IV-history
(options/iv_history/{SYM}.json — the same files the old ThetaData pipeline built,
so US IV-rank is immediate and EU builds from today), computes the rank, and uploads
scans/options_latest.json. The frontend stock card reads that file.

Run once:   python backend/ibkr_options_batch.py
Schedule:   Task Scheduler nightly (after ~02:00 ET, past the gateway's 00:15-01:45
            restart), or a terminal loop. Reconnects + checkpoints so a long run
            survives the daily gateway restart.

Env: IB_GATEWAY_PORT(4001) · OPT_MAX(0=all) · OPT_SLEEP_S(0.2 between names) ·
     OPT_CHECKPOINT(200). GCS auth via the machine's logged-in gcloud.
"""
from __future__ import annotations
import os, sys, json, time, logging, subprocess
from datetime import datetime, timezone, timedelta

import requests
import ibkr_options
from ibkr_options import enrich_fast

log = logging.getLogger("ibkr_batch")
BUCKET = "screener-signals-carbonbridge"
IV_PREFIX = "options/iv_history"        # matches massive_options (ThetaData-era files)
KEEP_DAYS = 365
MIN_SAMPLES = 20
MAX = int(os.environ.get("OPT_MAX", "0"))            # 0 = whole universe
SLEEP_S = float(os.environ.get("OPT_SLEEP_S", "0.2"))
CHECKPOINT = int(os.environ.get("OPT_CHECKPOINT", "200"))
FW = {"momentum": 25, "quality": 20, "growth": 20, "value": 20, "smart_money": 15}
SUFFIX = {
    ".PA": ("SBF", "EUR"), ".AS": ("AEB", "EUR"), ".BR": ("ENEXT.BE", "EUR"),
    ".MI": ("BVME", "EUR"), ".DE": ("IBIS", "EUR"), ".F": ("IBIS", "EUR"),
    ".L": ("LSE", "GBP"), ".SW": ("EBS", "CHF"), ".MC": ("BM", "EUR"),
    ".LS": ("BVL", "EUR"), ".VI": ("VSE", "EUR"), ".HE": ("HEX", "EUR"),
    ".ST": ("SFB", "SEK"), ".CO": ("CPH", "DKK"), ".OL": ("OSE", "NOK"),
}

_tok = {"v": None, "t": 0.0}
def _token() -> str:
    if not _tok["v"] or (time.time() - _tok["t"]) > 2400:  # refresh every 40 min
        _tok["v"] = subprocess.check_output("gcloud auth print-access-token", shell=True, text=True).strip()
        _tok["t"] = time.time()
    return _tok["v"]


def _gcs_read(path: str, default=None, fresh: bool = False):
    """Read a GCS object. fresh=True appends a cache-buster — the public
    storage.googleapis.com URL is edge-cached ~1h, which would otherwise serve a
    stale object to same-night pipeline steps (publish -> tracker -> executor)."""
    try:
        url = f"https://storage.googleapis.com/{BUCKET}/{path}"
        if fresh:
            url += f"?cb={int(time.time() * 1000)}"
        r = requests.get(url, timeout=90)
        return r.json() if r.ok else default
    except Exception:
        return default


def _gcs_write(path: str, data) -> bool:
    try:
        r = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o",
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
            data=json.dumps(data), timeout=60)
        if not r.ok:
            log.error("GCS write %s -> %s %s", path, r.status_code, r.text[:160])
        return r.ok
    except Exception as e:
        log.error("GCS write %s failed: %s", path, e); return False


def _iv_rank(symbol: str, iv: float):
    """Append today's ATM IV to the per-symbol GCS history; return rank dict (or None
    until MIN_SAMPLES). Mirrors massive_options.update_iv_history/compute_iv_rank."""
    if not iv or iv <= 0:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    path = f"{IV_PREFIX}/{symbol.upper()}.json"
    hist = _gcs_read(path, [])
    if not isinstance(hist, list):
        hist = []
    i = next((j for j, r in enumerate(hist) if isinstance(r, list) and r and r[0] == today), -1)
    row = [today, round(iv, 4)]
    if i >= 0:
        hist[i] = row      # replace today's entry
    else:
        hist.append(row)
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    hist = [r for r in hist if isinstance(r, list) and len(r) >= 2 and r[0] >= cutoff]
    _gcs_write(path, hist)
    ivs = [float(r[1]) for r in hist if len(r) >= 2 and r[1]]
    if len(ivs) < MIN_SAMPLES:
        return {"iv_current": round(iv, 4), "iv_rank": None, "iv_samples": len(ivs)}
    lo, hi = min(ivs), max(ivs)
    rank = 50.0 if hi == lo else (iv - lo) / (hi - lo) * 100.0
    return {"iv_current": round(iv, 4), "iv_rank": round(rank, 1), "iv_samples": len(ivs)}


def _composite(s: dict) -> float:
    f = s.get("factors_v8_momentum") or s.get("factors_v8") or {}
    num = den = 0.0
    for k, w in FW.items():
        v = f.get(k)
        if v is not None:
            num += v * w; den += w
    return num / den if den else 0.0


def _map_contract(symbol: str):
    for suf, (ex, cur) in SUFFIX.items():
        if symbol.endswith(suf):
            return symbol[: -len(suf)], ex, cur
    if "." not in symbol:
        return symbol, "SMART", "USD"
    return None


def build_targets():
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
        seen.add(sym)
        targets.append((sym, m[0], m[1], m[2], s.get("price")))

    for sym in port_syms:
        if sym in by_sym:
            add(by_sym[sym])
    for s in sorted(stocks, key=_composite, reverse=True):  # composite order -> top names first if interrupted
        if MAX and len(targets) >= MAX:
            break
        add(s)
    return targets


def main():
    targets = build_targets()
    log.info("full-universe options: %d eligible names (max=%s)", len(targets), MAX or "all")
    if not targets:
        log.error("no targets — scan unreadable?"); sys.exit(1)

    ib = ibkr_options._connect()
    options, ok = {}, 0
    try:
        for i, (fmp_sym, ib_sym, ex, cur, spot) in enumerate(targets, 1):
            if not ib.isConnected():  # survive the gateway's daily restart
                log.warning("reconnecting to gateway…")
                try:
                    ib.connect(ibkr_options.IB_HOST, ibkr_options.IB_PORT,
                               clientId=ibkr_options.IB_CLIENT_ID, timeout=20, readonly=True)
                except Exception as e:
                    log.error("reconnect failed: %s — sleeping 60s", e); time.sleep(60); continue
            try:
                d = enrich_fast(ib, ib_sym, ex, cur, spot)
            except Exception as e:
                log.warning("[%d/%d] %s failed: %s", i, len(targets), fmp_sym, e); continue
            if d.get("iv_current"):
                rank = _iv_rank(fmp_sym, d["iv_current"]) or {}
                options[fmp_sym] = {**rank, "spread": d.get("spread")}
                ok += 1
            if i % 50 == 0:
                log.info("[%d/%d] %d with options", i, len(targets), ok)
            if CHECKPOINT and i % CHECKPOINT == 0:   # partial upload so results appear during a long run
                _gcs_write("scans/options_latest.json",
                           {"updated": datetime.now(timezone.utc).isoformat(), "count": ok,
                            "partial": True, "options": options})
            if SLEEP_S:
                ib.sleep(SLEEP_S)
    finally:
        if ib.isConnected():
            ib.disconnect()

    payload = {"updated": datetime.now(timezone.utc).isoformat(), "count": ok, "options": options}
    if _gcs_write("scans/options_latest.json", payload):
        log.info("DONE — uploaded options_latest.json: %d/%d names with options", ok, len(targets))
    else:
        log.error("final upload failed"); sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    main()
