import os
import time
import datetime
import concurrent.futures
from threading import Lock
from thetadata import ThetaClient

client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"], dataframe_type="pandas")

tickers = ['AAPL', 'AMZN', 'MSFT', 'GOOGL', 'NVDA', 'NFLX', 'UBER', 'ADBE', 'AVGO', 'CRM']
eod_date = datetime.date(2026, 5, 21)

class ThreadSafeRateLimiter:
    def __init__(self, rps):
        self.interval = 1.0 / rps
        self.last_called = 0.0
        self.lock = Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_called
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                self.last_called = time.time()
            else:
                self.last_called = now

limiter = ThreadSafeRateLimiter(16)

def fetch_greeks_for_symbol(sym):
    limiter.wait()
    t_start = time.time()
    try:
        greeks_df = client.option_history_greeks_eod(
            symbol=sym,
            expiration="*",
            start_date=eod_date,
            end_date=eod_date,
            strike="*",
            right="call",
            strike_range=10,
        )
        return sym, greeks_df, None, time.time() - t_start
    except Exception as e:
        return sym, None, e, time.time() - t_start

print("Starting parallel fetch with ThreadSafeRateLimiter...")
start_time = time.time()

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(fetch_greeks_for_symbol, sym) for sym in tickers]
    for fut in concurrent.futures.as_completed(futures):
        sym, greeks_df, err, dur = fut.result()
        status = "OK" if greeks_df is not None else f"Error: {err}"
        print(f"Ticker {sym}: {status} (took {dur:.2f}s)")

end_time = time.time()
print(f"Total time: {end_time - start_time:.2f}s")
