import re

with open("src/obsidian_rl/evaluation/trend_backtest.py", "r") as f:
    code = f.read()

if "InsufficientHistoryError" not in code:
    code = code.replace(
        "from obsidian_rl.signals.trend import TrendConfig, calculate_trend_signal",
        "from obsidian_rl.signals.trend import TrendConfig, calculate_trend_signal, InsufficientHistoryError"
    )

if "market_model: str" not in code:
    code = code.replace(
        "    backtest_identity: str",
        "    market_model: str\n    first_decision_ts: int | None\n    first_exec_ts: int | None\n    first_exec_price: float | None\n    liq_ts: int | None\n    liq_price: float | None\n    backtest_identity: str"
    )

with open("tools/backtest_impl.py", "r") as f:
    new_impl = f.read()

pattern = r"def _run_single_backtest\(.*"
new_code = re.sub(pattern, new_impl, code, flags=re.DOTALL)

with open("src/obsidian_rl/evaluation/trend_backtest.py", "w") as f:
    f.write(new_code)
