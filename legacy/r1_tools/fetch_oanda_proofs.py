import os
import json
import hashlib
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

from obsidian_rl.data.providers.oanda import OandaPracticeProvider
from obsidian_rl.data.contracts import Timeframe

def ms_to_rfc3339(ms):
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")

def fetch_and_hash(provider, start_ms, end_ms, filename):
    url = f"{provider._base_url}/v3/instruments/EUR_USD/candles"
    params = {
        "price": "MBA",
        "granularity": "H4",
        "from": ms_to_rfc3339(start_ms),
        "to": ms_to_rfc3339(end_ms)
    }
    headers = {"Authorization": f"Bearer {provider._api_token}"}
    payload = provider._request("GET", url, params=params, headers=headers)
    
    with open(filename, 'w') as f:
        json.dump(payload, f, sort_keys=True)
        
    with open(filename, 'rb') as f:
        digest = hashlib.sha256(f.read()).hexdigest()
        
    print(f"[{start_ms}, {end_ms}]: {digest}")

gaps = [
    (1577224800000, 1577311200000),
    (1577829600000, 1577916000000),
    (1608847200000, 1609106400000),
    (1609452000000, 1609711200000),
    (1671832800000, 1672092000000),
    (1703282400000, 1703541600000)
]

provider = OandaPracticeProvider()
for i, (start, end) in enumerate(gaps):
    fetch_and_hash(provider, start, end, f"artifacts/cycle_02/oanda_holiday_proof_{i+1}.json")
