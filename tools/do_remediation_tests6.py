import os

path_tests = "tests/evaluation/test_trend_backtest.py"
with open(path_tests, "r") as f:
    code = f.read()

# Fix 1: reg2 initialization
code = code.replace('VenueOutage("BINANCE_SPOT", 2000, 3000, "2")',
                    'VenueOutage("BINANCE_SPOT", 2000, 3000, "2", 3000, "0"*64, "test", ("BTCUSDT",), True)')

with open(path_tests, "w") as f:
    f.write(code)
