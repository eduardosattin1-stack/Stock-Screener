import os
import datetime
from thetadata import ThetaClient

print("Connecting to ThetaData...")
client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"], dataframe_type="pandas")

# List expirations for INTU
expirations = client.option_list_expirations("INTU")

import pandas as pd

# Convert expiration column to datetime dates
expirations['exp_date'] = pd.to_datetime(expirations['expiration'].astype(str)).dt.date
future_exps = expirations[expirations['exp_date'] > datetime.date.today()]

if future_exps.empty:
    raise ValueError("No future expirations found!")

# Take a valid future expiration
exp = future_exps['exp_date'].iloc[0]

strikes_df = client.option_list_strikes("INTU", exp)
mid_strike = 650.0
print(f"Using Strike: {mid_strike} for Expiration: {exp}")

today = datetime.date.today()
start_date = today - datetime.timedelta(days=today.weekday() + 7)
end_date = start_date + datetime.timedelta(days=4)

print(f"Fetching INTU greeks for {start_date} to {end_date}...")

try:
    bars = client.option_history_greeks_eod(
        symbol="INTU", 
        right="C", 
        strike=str(mid_strike), 
        expiration=exp,
        start_date=start_date, 
        end_date=end_date
    )
    # Save to CSV to avoid encoding issues printing
    bars.to_csv("intu_greeks.csv")
    print("Success! Saved to intu_greeks.csv")
except Exception as e:
    print(f"Error fetching data: {e}")
