import os

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(", eval_start_ms=0, eval_start_ms=0,", ", eval_start_ms=0,")
content = content.replace(", eval_start_ms=eval_start_ms, eval_start_ms=0,", ", eval_start_ms=eval_start_ms,")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
