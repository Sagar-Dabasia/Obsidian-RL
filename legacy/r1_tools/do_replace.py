import re

with open("src/obsidian_rl/evaluation/trend_backtest.py", "r") as f:
    code = f.read()

with open("tools/backtest_impl.py", "r") as f:
    new_impl = f.read()

# Replace everything from def _run_single_backtest to the end of the file
pattern = r"def _run_single_backtest\(.*?$"
new_code = re.sub(pattern, new_impl, code, flags=re.DOTALL | re.MULTILINE)

with open("src/obsidian_rl/evaluation/trend_backtest.py", "w") as f:
    f.write(new_code)
