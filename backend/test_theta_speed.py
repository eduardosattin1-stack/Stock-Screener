import os
import time
import datetime
from thetadata import ThetaClient

client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"], dataframe_type="pandas")

tickers = ['AAPL', 'AMZN', 'MSFT', 'GOOGL', 'NVDA', 'NFLX', 'UBER', 'ADBE', 'AVGO', 'CRM']
eod_date = datetime.date(2026, 5, 21)

print("Starting speed test for 10 tickers...")
start_time = time.time()

for t in tickers:
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
    print(f"Ticker {t}: {status} (took {t_end - t_start:.2f}s)")

end_time = time.time()
print(f"Total time for 10 tickers: {end_time - start_time:.2f}s")
print(f"Average time per ticker: {(end_time - start_time) / 10:.2f}s")
