import os

path = "src/obsidian_rl/evaluation/trend_backtest.py"
with open(path, "r") as f:
    code = f.read()

code = code.replace("maximum_drawdown=engine.path_maximum_drawdown_pct", "maximum_drawdown=engine.state.path_maximum_drawdown_pct")

with open(path, "w") as f:
    f.write(code)
