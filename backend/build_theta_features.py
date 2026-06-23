import os
import json
import logging
import datetime
import polars as pl
import pandas as pd
from thetadata import ThetaClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
log = logging.getLogger("Theta-Extractor")

def process_theta_options(client, symbol, date_obj):
    """
    Pulls End-of-Day Greeks for a specific symbol on a specific date.
    Calculates 25-Delta Skew and ATM Implied Volatility.
    """
    try:
        # ThetaData EOD Greeks Endpoint
        # strike_range=5 means we only pull strikes immediately around the ATM price (to save memory)
        df_polars = client.option_history_greeks_eod(
            symbol=symbol,
            expiration="*",
            start_date=date_obj,
            end_date=date_obj,
            strike="*",
            right="both",
            strike_range=5 
        )
        
        if df_polars.is_empty():
            return None
            
        # Fetch Open Interest
        oi_df_polars = client.option_history_open_interest(
            symbol=symbol,
            expiration="*",
            start_date=date_obj,
            end_date=date_obj,
            strike="*",
            right="both",
            strike_range=5 
        )
            
        # Convert to Pandas
        df_greeks = df_polars.to_pandas()
        
        if not oi_df_polars.is_empty():
            df_oi = oi_df_polars.to_pandas()
            df = pd.merge(df_greeks, df_oi[['expiration', 'strike', 'right', 'open_interest']], 
                          on=['expiration', 'strike', 'right'], how='left')
        else:
            df = df_greeks
            df['open_interest'] = 0.0
        
        # 1. Filter out garbage IVs or errors
        df = df[(df['iv_error'] < 0.1) & (df['implied_vol'] > 0)]
        
        # 2. Extract 25-Delta Skew
        # Find Puts near -0.25 delta
        puts = df[df['right'] == 'PUT'].copy()
        calls = df[df['right'] == 'CALL'].copy()
        
        # We find the contract with delta closest to -0.25
        puts['delta_dist'] = (puts['delta'] - (-0.25)).abs()
        p25 = puts.loc[puts['delta_dist'].idxmin()] if not puts.empty else None
        
        # Find Calls near 0.25 delta
        calls['delta_dist'] = (calls['delta'] - 0.25).abs()
        c25 = calls.loc[calls['delta_dist'].idxmin()] if not calls.empty else None
        
        skew_25d = None
        if p25 is not None and c25 is not None:
            skew_25d = p25['implied_vol'] - c25['implied_vol']
            
        # 3. Extract ATM IV (Delta closest to 0.50 or underlying price)
        calls['atm_dist'] = (calls['delta'] - 0.50).abs()
        atm_call = calls.loc[calls['atm_dist'].idxmin()] if not calls.empty else None
        atm_iv = atm_call['implied_vol'] if atm_call is not None else None
        
        # 4. Extract Net Gamma (Proxy for GEX using Open Interest)
        net_gamma = (calls['gamma'] * calls['open_interest']).sum() - (puts['gamma'] * puts['open_interest']).sum()

        return {
            "symbol": symbol,
            "date": str(date_obj),
            "skew_25d": round(float(skew_25d), 4) if skew_25d else 0.0,
            "atm_iv": round(float(atm_iv), 4) if atm_iv else 0.0,
            "net_gamma": round(float(net_gamma), 4)
        }
        
    except Exception as e:
        log.warning(f"Failed extracting ThetaData for {symbol} on {date_obj}: {e}")
        return None

if __name__ == "__main__":
    log.info("Connecting to ThetaData...")
    client = ThetaClient(email=os.environ["THETA_EMAIL"], password=os.environ["THETA_PASSWORD"])
    
    # Just a test run to prove the math works perfectly
    test_date = datetime.date(2024, 1, 10)
    res = process_theta_options(client, "AAPL", test_date)
    
    if res:
        log.info(f"Test Extraction Complete: {json.dumps(res, indent=2)}")
    else:
        log.info("No data returned for test.")
