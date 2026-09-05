import os

path = "src/obsidian_rl/evaluation/trend_backtest.py"
with open(path, "r") as f:
    code = f.read()

old_sig = """def _run_single_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    mode: str,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
    allow_short: bool = True,
    market_model: str = "PERPETUAL",
) -> TrendBacktestResult:
    \"\"\"Run a single pass of the backtest logic.\"\"\"
    if not bars:
        raise ValueError("Empty dataset")

    if market_model == "SPOT" and allow_short:
        raise ValueError("SPOT market model cannot execute short positions")"""

new_sig = """def _run_single_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    mode: str,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
    market_model: MarketModel = MarketModel.PERPETUAL,
    exposure_policy: ExposurePolicy = ExposurePolicy.BIDIRECTIONAL,
    manifest_digest: str | None = None,
) -> TrendBacktestResult:
    \"\"\"Run a single pass of the backtest logic.\"\"\"
    if not bars:
        raise ValueError("Empty dataset")

    if market_model == MarketModel.SPOT and exposure_policy == ExposurePolicy.BIDIRECTIONAL:
        raise ValueError("SPOT market model cannot execute BIDIRECTIONAL positions")"""

code = code.replace(old_sig, new_sig)

with open(path, "w") as f:
    f.write(code)
