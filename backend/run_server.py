import os, json, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"


def get_transcripts(symbol: str, num_quarters: int = 8) -> list[dict]:
    """Fetch up to num_quarters of earning call transcripts, most recent first."""
    transcripts = []
    now = datetime.now()

    # Generate candidate (year, quarter) pairs going back ~2.5 years
    candidates = []
    for offset in range(num_quarters + 4):  # extra buffer for gaps
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
                        "year": y,
                        "quarter": q,
                        "date": data[0].get("date", ""),
                        "content": data[0]["content"],
                    })
        except Exception:
            continue

    # Sort: oldest first (chronological for trend analysis)
    transcripts.sort(key=lambda t: (t["year"], t["quarter"]))
    return transcripts


def analyze_transcripts(symbol: str, transcripts: list[dict]) -> str:
    """Send multiple quarters of transcripts to Claude for evolution analysis."""
    if not ANTHROPIC_API_KEY:
        return "Error: ANTHROPIC_API_KEY not set on server."
    if not transcripts:
        return f"No transcripts found for {symbol}."

    n = len(transcripts)
    latest = transcripts[-1]

    # If only 1 transcript, do single-quarter analysis
    if n == 1:
        return _analyze_single(symbol, latest)

    # Build the multi-quarter prompt
    # Truncate each transcript to fit context (~15K chars each for 8 quarters = ~120K)
    max_per_transcript = 120000 // max(n, 1)
    transcript_blocks = []
    for t in transcripts:
        label = f"Q{t['quarter']} {t['year']} ({t['date']})"
        content = t["content"][:max_per_transcript]
        transcript_blocks.append(f"=== {label} ===\n{content}")

    combined = "\n\n".join(transcript_blocks)

    prompt = f"""You are analyzing {n} consecutive quarterly earnings call transcripts for {symbol}, spanning from Q{transcripts[0]['quarter']} {transcripts[0]['year']} to Q{latest['quarter']} {latest['year']}.

Your job is to extract what ONLY transcripts reveal — the evolution of management's thinking, tone, and credibility over time. This is the investor's edge: first-hand access to management and analyst pushback that no metric captures.

Provide a structured analysis:

## 1. NARRATIVE ARC
How has management's core story evolved? What were they emphasizing 2 years ago vs now? Has the thesis shifted, expanded, or contracted? Are they still talking about the same growth drivers or have new ones emerged?

## 2. TONE & CONFIDENCE SHIFT
Rate management confidence trajectory: Rising / Stable / Declining
- Compare the language, hedging, and assertiveness across quarters
- Are they getting more or less specific with guidance?
- Any shift from offensive (growth, investment, opportunity) to defensive (efficiency, cost-cutting, macro uncertainty) language?

## 3. GUIDANCE CREDIBILITY
- Track key guidance given in past calls vs actual results in subsequent calls
- Did they deliver on promises? Over-deliver? Miss?
- Score guidance reliability: High / Medium / Low
- Any pattern of sandbagging (consistently beating low guidance)?

## 4. ANALYST PRESSURE POINTS
- What questions keep coming up that management deflects or gives non-answers to?
- Any topics analysts pushed on that management later had to address with bad news?
- What are analysts worried about that management isn't addressing?

## 5. RED FLAGS & GREEN FLAGS
🟢 Green flags (positive evolution):
- List specific examples with quarter references

🔴 Red flags (concerning shifts):
- List specific examples with quarter references

## 6. HIDDEN SIGNALS
What subtle shifts in language or emphasis might signal future changes? Things like:
- New terminology introduced or old terminology dropped
- Changing how they discuss competition
- Shifts in how they talk about capital allocation
- Any management changes and what the new voices are saying differently

## 7. INVESTMENT IMPLICATION
Based on the trajectory of these transcripts, is the fundamental story:
- STRENGTHENING: Management executing well, narrative improving
- STABLE: Consistent execution, no major shifts
- DETERIORATING: Cracks appearing, defensive posture emerging
- PIVOTING: Fundamental story changing (could be positive or negative)

One-paragraph summary for an investor deciding whether to buy, hold, or sell.

Be specific. Reference exact quarters. Quote brief phrases when they reveal tone shifts. This analysis should give an investor an edge that no financial metric provides.

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
    return "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )


def _analyze_single(symbol: str, transcript: dict) -> str:
    """Fallback: analyze a single transcript when only one is available."""
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

            # Optional: ?quarters=8 (default 8, max 12)
            quarters = min(int(qs.get("quarters", ["8"])[0]), 12)

            try:
                transcripts = get_transcripts(symbol, num_quarters=quarters)
                analysis = analyze_transcripts(symbol, transcripts)
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "symbol": symbol,
                    "analysis": analysis,
                    "quarters_found": len(transcripts),
                    "quarters_requested": quarters,
                    "date_range": f"Q{transcripts[0]['quarter']} {transcripts[0]['year']} → Q{transcripts[-1]['quarter']} {transcripts[-1]['year']}" if transcripts else "none",
                    "has_transcript": bool(transcripts),
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
            self.wfile.write(json.dumps({"status": "ok", "version": "v7"}).encode())
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Stock Screener v7 - GET /transcript?symbol=X&quarters=8 for multi-quarter AI analysis")

    def do_POST(self):
        try:
            from screener_v6 import get_symbols, screen, format_report, send_email, update_signal_history, save_scan_to_gcs
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
            send_email(f"Screener v6: {region.upper()} - {today}", report)
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
print(f"Screener v7 server on port {port}")
HTTPServer(("", port), Handler).serve_forever()
