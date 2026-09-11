import os

files = [
    "src/obsidian_rl/evaluation/trend_backtest.py",
    "tests/evaluation/test_trend_backtest.py",
    "tools/run_trend_backtest.py"
]

for f in files:
    with open(f, "r") as file:
        lines = file.readlines()
    with open(f, "w") as file:
        for line in lines:
            file.write(line.rstrip() + "\n")
