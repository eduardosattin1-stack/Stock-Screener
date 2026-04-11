import os, json
from http.server import HTTPServer, BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
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
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(report.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"ERROR: {e}".encode("utf-8"))
            import traceback
            traceback.print_exc()
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Stock Screener v5 - POST to run")
port = int(os.environ.get("PORT", 8080))
print(f"Screener v5 server on port {port}")
HTTPServer(("", port), Handler).serve_forever()
