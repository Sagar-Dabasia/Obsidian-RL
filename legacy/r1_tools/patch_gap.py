import re

with open("tests/data/test_outages.py", "r") as f:
    code = f.read()

# Replace b1.timestamp_utc with b1.timestamp_utc + 14400000
code = code.replace(
    'assert reg.covers_gap("BINANCE_SPOT", b1.timestamp_utc, b2.timestamp_utc)',
    'assert reg.covers_gap("BINANCE_SPOT", b1.timestamp_utc + 14400000, b2.timestamp_utc)'
)

with open("tests/data/test_outages.py", "w") as f:
    f.write(code)
