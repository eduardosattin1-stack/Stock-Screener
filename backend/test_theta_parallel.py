import time
import datetime
from concurrent.futures import ThreadPoolExecutor
from thetadata import ThetaClient

# We will use one client per thread or a shared client. Let's test a shared client first.
import os
client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"], dataframe_type="pandas")

tickers = ['AAPL', 'AMZN', 'MSFT', 'GOOGL', 'NVDA', 'NFLX', 'UBER', 'ADBE', 'AVGO', 'CRM']
eod_date = datetime.date(2026, 5, 21)

def fetch(t):
    t_start = time.time()
    try:
        greeks_df = client.option_history_greeks_eod(
            symbol=t,
            expiration="*",
            start_date=eod_date,
            end_date=eod_date,
            strike="*",
            right="call",
            strike_range=10
        )
        status = "OK" if greeks_df is not None else "Empty"
    except Exception as e:
        status = f"Error: {e}"
    t_end = time.time()
    return t, status, t_end - t_start

print("Starting parallel speed test for 10 tickers with 10 threads...")
start_time = time.time()

with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(fetch, tickers))

for t, status, duration in results:
    print(f"Ticker {t}: {status} (took {duration:.2f}s)")

end_time = time.time()
print(f"Total time for 10 tickers (parallel): {end_time - start_time:.2f}s")
