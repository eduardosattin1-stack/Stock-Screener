"""
ibkr_service.py — tiny HTTP wrapper around ibkr_options.enrich, run on the
IB Gateway host. Vercel's /api/options/[symbol] proxies to this.

    GET /options?symbol=AAPL&exchange=SMART&currency=USD&spot=298.0
    GET /health

Returns the options-card contract JSON (iv_current/iv_rank/iv_samples/spread).
Requests are serialized (one IB socket connection at a time — ib_async is not
thread-safe). Low-traffic by design: the card is opened on demand, not in bulk.

Run:  IB_GATEWAY_PORT=4001 python backend/ibkr_service.py        # serves :8787
Expose it to Vercel with a stable URL (small VM + domain, or `cloudflared tunnel`).
Set IBKR_SERVICE_TOKEN to require a Bearer token (recommended once public).
"""
from __future__ import annotations
import os, json, logging, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import ibkr_options

log = logging.getLogger("ibkr_service")
PORT = int(os.environ.get("IBKR_SERVICE_PORT", "8787"))
TOKEN = os.environ.get("IBKR_SERVICE_TOKEN")  # optional Bearer auth
_lock = threading.Lock()  # one IB connection at a time


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "public, max-age=300")  # card data is fine cached ~5min
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send(200, {"ok": True})
        if parsed.path != "/options":
            return self._send(404, {"error": "not found"})
        if TOKEN and self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"error": "unauthorized"})

        q = parse_qs(parsed.query)
        symbol = (q.get("symbol", [""])[0] or "").strip().upper()
        if not symbol:
            return self._send(400, {"error": "symbol required"})
        exchange = (q.get("exchange", ["SMART"])[0] or "SMART").strip()
        currency = (q.get("currency", ["USD"])[0] or "USD").strip()
        try:
            spot = float(q["spot"][0]) if q.get("spot") else None
        except (ValueError, IndexError):
            spot = None
        try:
            with _lock:
                data = ibkr_options.enrich(symbol, exchange, currency, spot)
            return self._send(200, data)
        except Exception as e:
            log.warning("enrich %s failed: %s", symbol, e)
            return self._send(502, {"error": str(e), "symbol": symbol})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("IBKR options service on :%d (gateway %s:%s, token=%s)",
             PORT, ibkr_options.IB_HOST, ibkr_options.IB_PORT, "set" if TOKEN else "none")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
