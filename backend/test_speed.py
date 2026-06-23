import time
import datetime
from thetadata import ThetaClient, DataType, OptionRight, DateRange

print("Connecting...")
import os
client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"])

symbol = "AAPL"
start_date = datetime.date(2023, 9, 1)
end_date = datetime.date(2023, 9, 30)

print(f"Fetching Greeks using get_hist_option from {start_date} to {end_date}...")
t0 = time.time()
try:
    with client.connect():
        data = client.get_hist_option(
            req=DataType.EOD_GREEKS,
            root=symbol,
            exp=None, # all expirations
            strike=None, # all strikes
            right=OptionRight.CALL,
            date_range=DateRange(start_date, end_date)
        )
    t1 = time.time()
    print(f"Successfully fetched. Rows: {len(data)}. Time: {t1 - t0:.3f} seconds")
except Exception as e:
    print(f"Error: {e}")
