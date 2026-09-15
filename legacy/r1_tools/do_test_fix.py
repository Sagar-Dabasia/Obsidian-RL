import os
import re

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL", "eval_start_ms=0, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL")
content = content.replace("outage_registry=reg, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL", "eval_start_ms=0, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL, outage_registry=reg")

content = content.replace("from obsidian_rl.evaluation.trend_backtest import parse_and_validate_manifest", "from obsidian_rl.data.manifest import load_and_validate_manifest")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
