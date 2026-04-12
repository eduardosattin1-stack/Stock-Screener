import os, json, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"


def get_transcript(symbol: str, year: int = 0, quarter: int = 0) -> str:
    """Fetch latest earning call transcript from FMP."""
    params = {"symbol": symbol, "apikey": FMP_KEY}
    if year:
        params["year"] = str(year)
    if quarter:
        params["quarter"] = str(quarter)
    r = requests.get(f"{FMP_BASE}/earning-call-transcript", params=params, timeout=20)
    if r.status_code != 200:
        return ""
    data = r.json()
    if isinstance(data, list) and data:
        return data[0].get("content", "")
    return ""


def analyze_transcript(symbol: str, transcript: str) -> str:
    """Send transcript to Claude for analysis."""
    if not ANTHROPIC_API_KEY:
        return "Error: ANTHROPIC_API_KEY not set on server."
    if not transcript:
        return f"No transcript found for {symbol}."

    text = transcript[:80000]

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": f"""Analyze this earnings call transcript for {symbol}. Be concise and structured.

Provide:
1. **Key Themes** - 3-5 major topics discussed
2. **Guidance** - any forward guidance on revenue, EPS, margins, or growth
3. **Risks** - concerns raised by management or analysts
4. **Competitive Position** - moat, market share, or competitive dynamics mentioned
5. **Buffett Score** - rate 1-10 how well this company fits Warren Buffett's investment criteria based on what management discussed (durable competitive advantage, predictable earnings, honest/capable management, reinvestment opportunities)

Transcript:
{text}"""}],
        },
        timeout=60,
    )

    if resp.status_code != 200:
        return f"Claude API error: {resp.status_code} - {resp.text[:200]}"

    data = resp.json()
    return "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/transcript":
            symbol = qs.get("symbol", [""])[0].upper()
            if not symbol:
                self.send_response(400)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing ?symbol= parameter"}).encode())
                return

            try:
                transcript = get_transcript(symbol)
                analysis = analyze_transcript(symbol, transcript)
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "symbol": symbol,
                    "analysis": analysis,
                    "has_transcript": bool(transcript),
                }).encode())
            except Exception as e:
                self.send_response(500)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                traceback.print_exc()
            return

        if parsed.path == "/health":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "version": "v5"}).encode())
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Stock Screener v5 - POST to run scan, GET /transcript?symbol=X for AI analysis")

    def do_POST(self):
        try:
            from screener_v5 import get_symbols, screen, format_report, send_email, update_signal_history, save_scan_to_gcs
            from datetime import datetime
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len else {}
            region = body.get("region", os.environ.get("SCREEN_INDEX", "nasdaq100"))
            symbols_str = body.get("symbols", "")
            if symbols_str:
                symbols = [s.strip().upper() for s in symbols_str.split(",")]
            else:
                symbols = get_symbols(region)
            results = screen(symbols)
            report = format_report(results, region)
            update_signal_history(results)
            save_scan_to_gcs(results, region)
            today = datetime.now().strftime("%Y-%m-%d")
            send_email(f"Screener v5: {region.upper()} - {today}", report)
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(report.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self._cors()
            self.end_headers()
            self.wfile.write(f"ERROR: {e}".encode("utf-8"))
            traceback.print_exc()


port = int(os.environ.get("PORT", 8080))
print(f"Screener v5 server on port {port}")
HTTPServer(("", port), Handler).serve_forever()
