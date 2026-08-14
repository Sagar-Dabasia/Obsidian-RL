import os
import re

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix the remaining run_trend_backtest missing positional arguments
content = content.replace(
    "run_trend_backtest(bars, TrendConfig(), CostModel())",
    "run_trend_backtest(bars, TrendConfig(), CostModel(), eval_start_ms=0, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)"
)

content = content.replace(
    "run_trend_backtest(tuple(bars), TrendConfig(), CostModel())",
    "run_trend_backtest(tuple(bars), TrendConfig(), CostModel(), eval_start_ms=0, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)"
)

# And if eval_start_ms is missing but market_model is there:
# For those `def test_manifest_...` tests, `p` is missing because tmp_path was not passed in the signature
content = content.replace("def test_manifest_duplicate_exact_match_rejected() -> None:", "def test_manifest_duplicate_exact_match_rejected(tmp_path) -> None:")
content = content.replace("def test_manifest_wrong_identity_rejected() -> None:", "def test_manifest_wrong_identity_rejected(tmp_path) -> None:")
content = content.replace("def test_manifest_malformed_values_rejected() -> None:", "def test_manifest_malformed_values_rejected(tmp_path) -> None:")
content = content.replace("def test_runtime_bounds_count_and_digest_rejected() -> None:", "def test_runtime_bounds_count_and_digest_rejected(tmp_path) -> None:")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
