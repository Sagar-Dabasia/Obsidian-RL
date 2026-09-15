import re

with open("tools/run_trend_backtest.py", "r") as f:
    code = f.read()

with open("tools/runner_impl.py", "r") as f:
    new_impl = f.read()

# Replace everything from `    manifest_component = None` in main
pattern = r"    manifest_component = None\s+manifest_digest = None.*?$"
new_code = re.sub(pattern, new_impl, code, flags=re.DOTALL | re.MULTILINE)

with open("tools/run_trend_backtest.py", "w") as f:
    f.write(new_code)
