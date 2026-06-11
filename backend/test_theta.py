import os
import datetime
from thetadata import ThetaClient

def main():
    client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"])
    
    start_date = datetime.date(2023, 9, 25)
    end_date = datetime.date(2023, 9, 25)
    
    try:
        df = client.option_history_greeks_eod(
            symbol="AAPL",
            expiration="*",
            start_date=start_date,
            end_date=end_date,
            strike="*",
            right="both",
            strike_range=1 # Only 1 strike above and below ATM
        )
        print("Type:", type(df))
        print("Columns:", df.columns if hasattr(df, 'columns') else "No columns attribute")
        print(df)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
