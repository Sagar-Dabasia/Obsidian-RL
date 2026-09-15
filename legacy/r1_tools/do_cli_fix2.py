import os
import re

path = "tools/run_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("outage_registry=registry,\n            eval_start_ms=eval_start_ms,\n            market_model=market_model,\n            exposure_policy=exposure_policy,\n            market_model=market_model,\n            exposure_policy=exposure_policy,", "eval_start_ms=eval_start_ms,\n            market_model=market_model,\n            exposure_policy=exposure_policy,\n            outage_registry=registry,")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
