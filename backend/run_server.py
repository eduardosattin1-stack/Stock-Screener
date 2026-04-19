"""
Cloud Run HTTP server for CB Screener v7.2.

Endpoints:
  GET  /health                          — liveness check
  GET  /transcript?symbol=X&quarters=8  — Claude earnings-call analysis
  POST /                                — run scan (body: {region, symbols})
  POST /portfolio/add                   — add position {symbol, entry_price, shares, notes}
  POST /portfolio/close                 — close position {symbol, exit_price, reason}
  GET  /portfolio/state                 — return current portfolio state.json

Security note:
  /portfolio/add and /portfolio/close are unauthenticated. Low-value write
  target; worst case is restoring portfolio/state.json from GCS versioning.
"""
import os, json, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"


# ---------------------------------------------------------------------------
# Transcripts (unchanged from v7.1)
# ---------------------------------------------------------------------------

def get_transcripts(symbol: str, num_quarters: int = 8) -> list[dict]:
    """Fetch up to num_quarters of earning call transcripts, most recent first."""
    transcripts = []
    now = datetime.now()
    candidates = []
    for offset in range(num_quarters + 4):
        m = now.month - offset * 3
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        q = (m - 1) // 3 + 1
        if (y, q) not in candidates:
            candidates.append((y, q))
    for y, q in candidates:
        if len(transcripts) >= num_quarters:
            break
        params = {"symbol": symbol, "year": str(y), "quarter": str(q), "apikey": FMP_KEY}
        try:
            r = requests.get(f"{FMP_BASE}/earning-call-transcript", params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data and data[0].get("content"):
                    transcripts.append({
                        "year": y, "quarter": q,
                        "date": data[0].get("date", ""),
                        "content": data[0]["content"],
                    })
        except Exception:
            continue
    transcripts.sort(key=lambda t: (t["year"], t["quarter"]))
    return transcripts


def analyze_transcripts(symbol: str, transcripts: list[dict]) -> str:
    """Multi-quarter transcript analysis via Claude API."""
    if not ANTHROPIC_API_KEY:
        return "Error: ANTHROPIC_API_KEY not set on server."
    if not transcripts:
        return f"No transcripts found for {symbol}."

    n = len(transcripts)
    latest = transcripts[-1]
    if n == 1:
        return _analyze_single(symbol, latest)

    max_per_transcript = 120000 // max(n, 1)
    blocks = []
    for t in transcripts:
        label = f"Q{t['quarter']} {t['year']} ({t['date']})"
        content = t["content"][:max_per_transcript]
        blocks.append(f"=== {label} ===\n{content}")
    combined = "\n\n".join(blocks)

    prompt = f"""You are analyzing {n} consecutive quarterly earnings call transcripts for {symbol}, spanning from Q{transcripts[0]['quarter']} {transcripts[0]['year']} to Q{latest['quarter']} {latest['year']}.

Trace the evolution across quarters. Identify:

1. **Narrative Shifts** — how did management's framing evolve? What themes appeared, strengthened, or faded?
2. **Guidance Track Record** — did guidance hold up? Beats, misses, revisions.
3. **Tone Trajectory** — confident → defensive, or steady, or improving? Quote specific phrases.
4. **Analyst Focus** — what concerns grew; what disappeared?
5. **Strategic Pivots** — any clear shifts in priorities, capex, M&A, capital return?
6. **Execution Quality** — consistent delivery on stated milestones? Name specific ones.

INVESTMENT IMPLICATION
Based on the trajectory of these transcripts, is the fundamental story:
- STRENGTHENING
- STABLE
- DETERIORATING
- PIVOTING

One-paragraph summary for an investor deciding whether to buy, hold, or sell.

Be specific. Reference exact quarters. Quote brief phrases when they reveal tone shifts.

Transcripts (chronological order):

{combined}"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        return f"Claude API error: {resp.status_code} - {resp.text[:200]}"
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _analyze_single(symbol: str, transcript: dict) -> str:
    """Fallback: single-quarter analysis."""
    text = transcript["content"][:80000]
    label = f"Q{transcript['quarter']} {transcript['year']}"
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2500,
            "messages": [{"role": "user", "content": f"""Analyze this {label} earnings call transcript for {symbol}. Be concise and structured.

Provide:
1. **Key Themes** — 3-5 major topics discussed
2. **Guidance** — forward guidance on revenue, EPS, margins, growth
3. **Management Tone** — confident, cautious, defensive, or evasive? Give examples.
4. **Analyst Concerns** — what did analysts push back on?
5. **Red Flags** — anything concerning in management's language or non-answers
6. **Green Flags** — signs of strong execution or improving fundamentals
7. **Buffett Score** — rate 1-10 how well this fits Buffett criteria (durable moat, predictable earnings, honest management, reinvestment)

Transcript:
{text}"""}],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        return f"Claude API error: {resp.status_code} - {resp.text[:200]}"
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


# ---------------------------------------------------------------------------
# v7.2 NEW: Portfolio CRUD handlers (user-authored positions)
# ---------------------------------------------------------------------------

def handle_portfolio_add(body: dict) -> tuple[int, dict]:
    """POST /portfolio/add — user adds a position.
    Uses monitor_v7.add_position + save_state, which persist to GCS.
    """
    try:
        from monitor_v7 import load_state, save_state, add_position
    except ImportError as e:
        return 500, {"error": f"Backend module missing: {e}"}

    symbol = (body.get("symbol") or "").strip().upper()
    entry_price = float(body.get("entry_price") or 0)
    shares = float(body.get("shares") or 0)
    notes = (body.get("notes") or "").strip()[:200]

    if not symbol:
        return 400, {"error": "symbol required"}
    if entry_price <= 0:
        return 400, {"error": "entry_price must be positive"}
    if shares <= 0:
        return 400, {"error": "shares must be positive"}

    state = load_state()
    state = add_position(state, symbol, entry_price=entry_price,
                         shares=shares, notes=notes)
    save_state(state)
    return 200, {
        "ok": True, "symbol": symbol,
        "positions": len(state.get("positions", [])),
    }


def handle_portfolio_close(body: dict) -> tuple[int, dict]:
    """POST /portfolio/close — user closes a position.
    Records exit in history via monitor_v7.remove_position.
    """
    try:
        from monitor_v7 import load_state, save_state, remove_position
    except ImportError as e:
        return 500, {"error": f"Backend module missing: {e}"}

    symbol = (body.get("symbol") or "").strip().upper()
    exit_price = float(body.get("exit_price") or 0)
    reason = (body.get("reason") or "User close").strip()[:200]

    if not symbol:
        return 400, {"error": "symbol required"}
    if exit_price <= 0:
        return 400, {"error": "exit_price must be positive"}

    state = load_state()
    if symbol not in [p["symbol"] for p in state.get("positions", [])]:
        return 404, {"error": f"{symbol} not in portfolio"}

    state = remove_position(state, symbol, exit_price=exit_price, reason=reason)
    save_state(state)
    return 200, {
        "ok": True, "symbol": symbol,
        "positions": len(state.get("positions", [])),
        "history": len(state.get("history", [])),
    }


def handle_portfolio_state_get() -> tuple[int, dict]:
    """GET /portfolio/state — return current portfolio state."""
    try:
        from monitor_v7 import load_state
    except ImportError as e:
        return 500, {"error": f"Backend module missing: {e}"}
    state = load_state()
    return 200, state


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status: int, payload: dict):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload, default=str).encode("utf-8"))

    def _text(self, status: int, text: str, ctype: str = "text/plain; charset=utf-8"):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # ─── Transcript endpoint (v7.1) ───
        if parsed.path == "/transcript":
            symbol = qs.get("symbol", [""])[0].upper()
            if not symbol:
                self._json(400, {"error": "Missing ?symbol= parameter"})
                return
            quarters = min(int(qs.get("quarters", ["8"])[0]), 12)
            try:
                transcripts = get_transcripts(symbol, num_quarters=quarters)
                analysis = analyze_transcripts(symbol, transcripts)
                self._json(200, {
                    "symbol": symbol,
                    "analysis": analysis,
                    "quarters_found": len(transcripts),
                    "quarters_requested": quarters,
                    "date_range": (
                        f"Q{transcripts[0]['quarter']} {transcripts[0]['year']} → "
                        f"Q{transcripts[-1]['quarter']} {transcripts[-1]['year']}"
                    ) if transcripts else "none",
                    "has_transcript": bool(transcripts),
                })
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": str(e)})
            return

        # ─── Portfolio state read ───
        if parsed.path == "/portfolio/state":
            try:
                status, payload = handle_portfolio_state_get()
                self._json(status, payload)
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": str(e)})
            return

        # ─── Health ───
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "version": "v7.2"})
            return

        # Default
        self._text(200, "Stock Screener v7.2 - see /health, /transcript, /portfolio/*")

    def do_POST(self):
        parsed = urlparse(self.path)

        # ─── Portfolio add ───
        if parsed.path == "/portfolio/add":
            try:
                body = self._read_body()
                status, payload = handle_portfolio_add(body)
                self._json(status, payload)
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": str(e)})
            return

        # ─── Portfolio close ───
        if parsed.path == "/portfolio/close":
            try:
                body = self._read_body()
                status, payload = handle_portfolio_close(body)
                self._json(status, payload)
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": str(e)})
            return

        # ─── Default POST = run a scan ───
        try:
            from screener_v6 import (
                get_symbols, screen, format_report, send_email,
                update_signal_history, save_scan_to_gcs,
            )
            body = self._read_body()
            region = body.get("region", os.environ.get("SCREEN_INDEX", "nasdaq100"))
            symbols_str = body.get("symbols", "")
            if symbols_str:
                symbols = [s.strip().upper() for s in symbols_str.split(",")]
            else:
                symbols = get_symbols(region)
            results, macro = screen(symbols)
            report = format_report(results, region, macro=macro)
            update_signal_history(results)
            save_scan_to_gcs(results, region, macro=macro)
            today = datetime.now().strftime("%Y-%m-%d")
            send_email(f"CB Screener v7.2: {region.upper()} — {today}", report)
            self._text(200, report)
        except Exception as e:
            traceback.print_exc()
            self._text(500, f"ERROR: {e}")


port = int(os.environ.get("PORT", 8080))
print(f"Screener v7.2 server on port {port}")
HTTPServer(("", port), Handler).serve_forever()
