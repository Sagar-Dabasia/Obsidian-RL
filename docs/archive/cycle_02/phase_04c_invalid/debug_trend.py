import sys
from obsidian_rl.signals.trend import TrendConfig
from obsidian_rl.portfolio.costs import CostModel
from tests.evaluation.test_trend_backtest import make_bar
from obsidian_rl.evaluation.trend_backtest import run_trend_backtest

bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
eval_start_ms = bars[200].timestamp_utc
config = TrendConfig()
cost_model = CostModel(taker_fee=0.01, half_spread=0.0, slippage=0.0)

report = run_trend_backtest(bars, config, cost_model, eval_start_ms=eval_start_ms)
print("Warmup long baseline trade count:", report.baseline_long.trade_count)
print("Warmup long baseline net return:", report.baseline_long.net_return)

report_full = run_trend_backtest(bars, config, cost_model)
print("Full long baseline trade count:", report_full.baseline_long.trade_count)
print("Full long baseline net return:", report_full.baseline_long.net_return)
