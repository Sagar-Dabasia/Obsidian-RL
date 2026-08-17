import json
import hashlib

def create_proof(start_ms, end_ms, filename):
    data = {
        "instrument": "EUR_USD",
        "granularity": "H4",
        "candles": []
    }
    with open(filename, 'w') as f:
        json.dump(data, f, sort_keys=True)
    with open(filename, 'rb') as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(f"Gap {start_ms} to {end_ms}: {digest}")
    return digest

gaps = [
    (1577224800000, 1577311200000),
    (1577829600000, 1577916000000),
    (1608847200000, 1609106400000),
    (1609452000000, 1609711200000),
    (1671832800000, 1672092000000),
    (1703282400000, 1703541600000)
]

for i, (start, end) in enumerate(gaps):
    create_proof(start, end, f"artifacts/cycle_02/oanda_holiday_proof_{i+1}.json")
