import os, json, traceback, logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
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


# ────────────────────────────────────────────────────────────────────────────
# 2026-04-25: bucket-stamping helper for portfolio positions.
# After add_position_atomic creates the position, we re-read state.json,
# set the `bucket` field on the matching position, and write back. The
# brief race window (someone else closing the position concurrently) is
# acceptable for personal-use scope. On any failure we silently log; the
# successful add is what matters.
# ────────────────────────────────────────────────────────────────────────────
_GCS_BUCKET = os.environ.get("GCS_BUCKET", "screener-signals-carbonbridge")
_PORTFOLIO_STATE_PATH = "portfolio/state.json"


def _gcs_token() -> str:
    r = requests.get(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}, timeout=3,
    )
    return r.json().get("access_token", "")


def _stamp_bucket_on_position(symbol: str, bucket: str) -> None:
    """Set position.bucket on the position matching `symbol` in portfolio/state.json.

    Best-effort. Any exception propagates to the caller (which logs and
    swallows so the successful add isn't masked).
    """
    token = _gcs_token()
    if not token:
        raise RuntimeError("no GCS access token")

    headers = {"Authorization": f"Bearer {token}"}
    from urllib.parse import quote
    encoded = quote(_PORTFOLIO_STATE_PATH, safe="")
    get_url = f"https://storage.googleapis.com/storage/v1/b/{_GCS_BUCKET}/o/{encoded}?alt=media"
    r = requests.get(get_url, headers=headers, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"GCS GET state.json -> {r.status_code}")

    state = r.json() or {}
    positions = state.get("positions") or state.get("open") or []
    found = False
    for pos in positions:
        if (pos.get("symbol") or "").upper() == symbol.upper():
            pos["bucket"] = bucket
            found = True
            break
    if not found:
        raise RuntimeError(f"position {symbol} not found in state.json")

    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{_GCS_BUCKET}/o"
    pr = requests.post(
        upload_url,
        params={"uploadType": "media", "name": _PORTFOLIO_STATE_PATH},
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(state, default=str),
        timeout=15,
    )
    if pr.status_code not in (200, 201):
        raise RuntimeError(f"GCS PUT state.json -> {pr.status_code}: {pr.text[:120]}")


def _read_bucket_for_symbol(symbol: str):
    """Read state.json and return the position's bucket if any, else None."""
    token = _gcs_token()
    if not token:
        return None
    from urllib.parse import quote
    encoded = quote(_PORTFOLIO_STATE_PATH, safe="")
    url = f"https://storage.googleapis.com/storage/v1/b/{_GCS_BUCKET}/o/{encoded}?alt=media"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if r.status_code != 200:
        return None
    state = r.json() or {}
    positions = state.get("positions") or state.get("open") or []
    for pos in positions:
        if (pos.get("symbol") or "").upper() == symbol.upper():
            return pos.get("bucket")
    return None


def _stamp_bucket_on_latest_history(symbol: str, bucket: str) -> None:
    """Find the most recent history entry for `symbol` and set bucket on it.

    state.json shape varies — history may live under "history" or "closed".
    We pick the most recent one matching the symbol.
    """
    token = _gcs_token()
    if not token:
        raise RuntimeError("no GCS access token")

    from urllib.parse import quote
    encoded = quote(_PORTFOLIO_STATE_PATH, safe="")
    headers = {"Authorization": f"Bearer {token}"}
    get_url = f"https://storage.googleapis.com/storage/v1/b/{_GCS_BUCKET}/o/{encoded}?alt=media"
    r = requests.get(get_url, headers=headers, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"GCS GET state.json -> {r.status_code}")

    state = r.json() or {}
    history = state.get("history") or state.get("closed") or []
    # Find the most recent matching entry. History is typically
    # appended in chronological order, so iterate from the tail.
    target = None
    for entry in reversed(history):
        if (entry.get("symbol") or "").upper() == symbol.upper():
            target = entry
            break
    if target is None:
        raise RuntimeError(f"no history entry found for {symbol}")
    target["bucket"] = bucket

    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{_GCS_BUCKET}/o"
    pr = requests.post(
        upload_url,
        params={"uploadType": "media", "name": _PORTFOLIO_STATE_PATH},
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(state, default=str),
        timeout=15,
    )
    if pr.status_code not in (200, 201):
        raise RuntimeError(f"GCS PUT state.json -> {pr.status_code}: {pr.text[:120]}")


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
            self.wfile.write(json.dumps({"status": "ok", "version": "v7.2"}).encode())
            return

        # v7.2: Signal performance tracker (System 1 — BUY/STRONG BUY → SELL cycles)
        if parsed.path == "/performance/signal-tracks":
            try:
                from signal_tracker import read_signal_tracks
                data = read_signal_tracks()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, max-age=60")
                self.end_headers()
                self.wfile.write(json.dumps(data, default=str).encode())
            except Exception as e:
                self.send_response(500)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                traceback.print_exc()
            return

        # v7.2: P(+10%) hit-rate tracker (System 2 — 60d windows, p10 > 0.70)
        if parsed.path == "/performance/hit-rates":
            try:
                from signal_tracker import read_hitrate_tracks
                data = read_hitrate_tracks()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, max-age=60")
                self.end_headers()
                self.wfile.write(json.dumps(data, default=str).encode())
            except Exception as e:
                self.send_response(500)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                traceback.print_exc()
            return

        # v7.2: Per-symbol (date, price, composite) history for stock-page chart
        # URL form: /stock/{SYMBOL}/history
        if parsed.path.startswith("/stock/") and parsed.path.endswith("/history"):
            parts = parsed.path.strip("/").split("/")
            # Expect: ["stock", "{SYMBOL}", "history"]
            if len(parts) == 3 and parts[0] == "stock" and parts[2] == "history":
                symbol = parts[1].upper()
                try:
                    from signal_tracker import read_stock_history
                    rows = read_stock_history(symbol)
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "public, max-age=300")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "symbol": symbol,
                        "rows": rows,   # [[date, price, composite], ...]
                    }, default=str).encode())
                except Exception as e:
                    self.send_response(500)
                    self._cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                    traceback.print_exc()
                return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Stock Screener v7 - GET /transcript?symbol=X&quarters=8 for multi-quarter AI analysis")

    def do_POST(self):
        parsed = urlparse(self.path)

        # ───────────────────────────────────────────────────────────────────
        # v7.2: /portfolio/add — add or update a position in the portfolio.
        # Writes to GCS portfolio/state.json. Uses add_position_atomic to
        # prevent race conditions between concurrent add/close requests
        # (previously: two concurrent writes would silently lose one because
        # both read the same state, both mutated their copy, and last-writer-
        # wins overwrote the first). Now uses GCS object generation
        # preconditions and retries on conflict.
        #
        # 2026-04-25: Optional `bucket` field ("midcap" | "sp500" | null)
        # tags the position with the strategy basket that inspired the trade.
        # Stamped onto the position record after add_position_atomic returns,
        # so the underlying atomic helper doesn't need to change.
        # Expected JSON body: {symbol, entry_price, shares, notes?, bucket?}
        # ───────────────────────────────────────────────────────────────────
        if parsed.path == "/portfolio/add":
            try:
                from monitor_v7 import add_position_atomic
                content_len = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_len)) if content_len else {}
                symbol = (body.get("symbol") or "").upper().strip()
                entry_price = float(body.get("entry_price") or 0)
                shares = float(body.get("shares") or 0)
                notes = (body.get("notes") or "")[:200]
                bucket_in = body.get("bucket")
                bucket = bucket_in if bucket_in in ("midcap", "sp500") else None
                if not symbol or entry_price <= 0:
                    self.send_response(400); self._cors()
                    self.send_header("Content-Type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"error": "symbol and entry_price > 0 required"}).encode())
                    return
                _, result = add_position_atomic(symbol, entry_price, shares=shares, notes=notes)
                # Stamp bucket onto the freshly-added position. Best-effort —
                # silently no-op if the helper layout is unexpected so the
                # successful add isn't surfaced as a failure to the caller.
                if bucket:
                    try:
                        _stamp_bucket_on_position(symbol, bucket)
                        result["bucket"] = bucket
                    except Exception as be:
                        traceback.print_exc()
                        logging.warning(f"[portfolio/add] failed to stamp bucket on {symbol}: {be}")
                self.send_response(200); self._cors()
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"ok": True, **result}, default=str).encode())
            except Exception as e:
                self.send_response(500); self._cors()
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                traceback.print_exc()
            return

        # ───────────────────────────────────────────────────────────────────
        # v7.2: /portfolio/close — close an existing position, record in
        # history. Uses remove_position_atomic for concurrency safety.
        # Returns 404 if symbol is not in the current portfolio (previously
        # silently returned 200 even when the position didn't exist, which
        # made it hard to tell that a close had no effect).
        #
        # 2026-04-25: Copy `bucket` (if any) from the open position into the
        # newly-created history entry so the Performance page can compare
        # tagged trades to the right model basket.
        # Expected JSON body: {symbol, exit_price, reason?}
        # ───────────────────────────────────────────────────────────────────
        if parsed.path == "/portfolio/close":
            try:
                from monitor_v7 import remove_position_atomic
                content_len = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_len)) if content_len else {}
                symbol = (body.get("symbol") or "").upper().strip()
                exit_price = float(body.get("exit_price") or 0)
                reason = (body.get("reason") or "User close")[:200]
                if not symbol or exit_price <= 0:
                    self.send_response(400); self._cors()
                    self.send_header("Content-Type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"error": "symbol and exit_price > 0 required"}).encode())
                    return

                # Read the bucket tag off the position BEFORE removal, so
                # we can stamp it on the history entry once the close lands.
                pre_bucket = None
                try:
                    pre_bucket = _read_bucket_for_symbol(symbol)
                except Exception as be:
                    logging.warning(f"[portfolio/close] couldn't read bucket pre-close for {symbol}: {be}")

                _, result = remove_position_atomic(symbol, exit_price=exit_price, reason=reason)
                if not result.get("removed"):
                    self.send_response(404); self._cors()
                    self.send_header("Content-Type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({
                        "ok": False,
                        "error": f"Position {symbol} not found in portfolio",
                        **result,
                    }).encode())
                    return

                if pre_bucket:
                    try:
                        _stamp_bucket_on_latest_history(symbol, pre_bucket)
                        result["bucket"] = pre_bucket
                    except Exception as be:
                        traceback.print_exc()
                        logging.warning(f"[portfolio/close] failed to stamp bucket on history for {symbol}: {be}")

                self.send_response(200); self._cors()
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"ok": True, **result}, default=str).encode())
            except Exception as e:
                self.send_response(500); self._cors()
                self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                traceback.print_exc()
            return

        # ───────────────────────────────────────────────────────────────────
        # Default: run a screener scan. Previously this handler matched any
        # POST regardless of path — that caused `/portfolio/add` requests to
        # kick off 12-minute NASDAQ scans instead of adding a position. Now
        # gated to explicit scan paths ("/", "/scan") so POST-to-any-other-
        # path rejects cleanly instead of running expensive work.
        # ───────────────────────────────────────────────────────────────────
        if parsed.path not in ("/", "/scan"):
            self.send_response(404); self._cors()
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"error": f"No POST handler for {parsed.path}"}).encode())
            return

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
            results, macro = screen(symbols)
            report = format_report(results, region, macro=macro)
            update_signal_history(results)
            save_scan_to_gcs(results, region, macro=macro)
            today = datetime.now().strftime("%Y-%m-%d")
            send_email(f"CB Screener v7.2: {region.upper()} — {today}", report)
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
print(f"Screener v7.2 server on port {port}")
ThreadingHTTPServer(("", port), Handler).serve_forever()
