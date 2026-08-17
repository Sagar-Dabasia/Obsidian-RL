import os

path_tests = "tests/evaluation/test_trend_backtest.py"
with open(path_tests, "r") as f:
    code = f.read()

# Fix 1: OutageRegistry takes outages=... not entries=...
code = code.replace('OutageRegistry(entries=(VenueOutage(', 'OutageRegistry(outages=(VenueOutage(')

with open(path_tests, "w") as f:
    f.write(code)
