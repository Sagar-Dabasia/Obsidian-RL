import os

path_tests = "tests/evaluation/test_trend_backtest.py"
with open(path_tests, "r") as f:
    code = f.read()

# Fix 1: VenueOutage affected_symbols must be a tuple
code = code.replace('VenueOutage("BINANCE_SPOT", 1000, 2000, "1", 3000, "0"*64, "test", ["BTCUSDT"], True)',
                    'VenueOutage("BINANCE_SPOT", 1000, 2000, "1", 3000, "0"*64, "test", ("BTCUSDT",), True)')
# Also replace in the second reg2 initialization!
code = code.replace('VenueOutage("BINANCE_SPOT", 1000, 2000, "2", 3000, "0"*64, "test", ["BTCUSDT"], True)',
                    'VenueOutage("BINANCE_SPOT", 1000, 2000, "2", 3000, "0"*64, "test", ("BTCUSDT",), True)')

with open(path_tests, "w") as f:
    f.write(code)
