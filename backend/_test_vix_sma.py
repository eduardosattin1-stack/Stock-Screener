import os
import requests
from dotenv import load_dotenv

load_dotenv(r"c:\Users\Bruno\Stock-Screener\frontend\.env.local")
MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
print("KEY:", MASSIVE_API_KEY[:5])

url = f"https://api.polygon.io/v1/indicators/sma/I:VIX?timespan=day&adjusted=true&window=200&series_type=close&order=desc&limit=1&apiKey={MASSIVE_API_KEY}"
r = requests.get(url)
print("I:VIX", r.status_code)
print(r.text)
