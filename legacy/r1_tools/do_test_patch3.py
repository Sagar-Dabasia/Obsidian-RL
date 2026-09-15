import os

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "run_trend_backtest(tuple(mutated_bars), config, cost_model, eval_start_ms=eval_start_ms)",
    "run_trend_backtest(tuple(mutated_bars), config, cost_model, eval_start_ms=eval_start_ms, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)"
)

content = content.replace(
    "run_trend_backtest(tuple(make_custom_bar(i) for i in range(10)), TrendConfig(), CostModel())",
    "run_trend_backtest(tuple(make_custom_bar(i) for i in range(10)), TrendConfig(), CostModel(), eval_start_ms=0, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)"
)

content = content.replace(
    "run_trend_backtest(bars, config, cost, market_model=MarketModel.FOREX_MARGIN, exposure_policy=ExposurePolicy.BIDIRECTIONAL)",
    "run_trend_backtest(bars, config, cost, eval_start_ms=0, market_model=MarketModel.FOREX_MARGIN, exposure_policy=ExposurePolicy.BIDIRECTIONAL)"
)

content = content.replace(
    'parse_and_validate_manifest(manifest, "CRYPTO", "BINANCE_SPOT", "BTCUSDT", "4h")',
    'load_and_validate_manifest(str(p), "CRYPTO", "BINANCE_SPOT", "BTCUSDT", "4h", 1000, 2000, 10, "0"*64, 1000, 2000)'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
