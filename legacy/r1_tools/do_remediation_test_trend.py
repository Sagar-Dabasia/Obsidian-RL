import os
import re

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r") as f:
    code = f.read()

# Replace BINANCE_PERPETUAL back to BINANCE_SPOT
code = code.replace("venue: str = \"BINANCE_PERPETUAL\",", "venue: str = \"BINANCE_SPOT\",")
code = code.replace("venue=\"BINANCE_PERPETUAL\"", "venue=\"BINANCE_SPOT\"")
code = code.replace("venue='BINANCE_PERPETUAL'", "venue='BINANCE_SPOT'")

# In run_trend_backtest calls, add MarketModel.PERPETUAL and ExposurePolicy.BIDIRECTIONAL since tests use BIDIRECTIONAL and shorting, which is forbidden on SPOT
code = code.replace("run_trend_backtest(bars, config, cost_model)", 
                    "run_trend_backtest(bars, config, cost_model, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)")
code = code.replace("run_trend_backtest(tuple(bars), config, cost_model, outage_registry=registry, eval_start_ms=eval_start_ms)", 
                    "run_trend_backtest(tuple(bars), config, cost_model, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL, outage_registry=registry, eval_start_ms=eval_start_ms)")

code = code.replace("from obsidian_rl.portfolio.costs import CostModel", 
                    "from obsidian_rl.portfolio.costs import CostModel\nfrom obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy")

with open(path, "w") as f:
    f.write(code)
