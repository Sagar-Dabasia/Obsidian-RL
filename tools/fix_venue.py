with open("tests/evaluation/test_trend_backtest.py", "r") as f:
    content = f.read()

content = content.replace('venue="BINANCE_SPOT"', 'venue="BINANCE_PERPETUAL"')

with open("tests/evaluation/test_trend_backtest.py", "w") as f:
    f.write(content)
