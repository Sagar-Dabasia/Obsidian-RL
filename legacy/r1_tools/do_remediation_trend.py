import os
import re

path = "src/obsidian_rl/evaluation/trend_backtest.py"
with open(path, "r") as f:
    code = f.read()

code = code.replace("from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine", 
                    "from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine, MarketModel, ExposurePolicy")

code = code.replace("first_decision_ts: int | None", "first_decision_ts: int | None\n    first_submitted_target: float | None")

# Replace `_run_single_backtest` signature and identity
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
        raise ValueError("SPOT market model cannot execute short positions")

    import hashlib
    h = hashlib.sha256()
    for b in bars:
        h.update(b.row_hash.encode("utf-8"))
    dataset_digest = h.hexdigest()"""

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
        raise ValueError("SPOT market model cannot execute BIDIRECTIONAL positions")

    import hashlib
    h = hashlib.sha256()
    for b in bars:
        h.update(b.row_hash.encode("utf-8"))
    dataset_digest = h.hexdigest()"""
code = code.replace(old_sig, new_sig)

# Fix backtest identity
old_ident = """                "portfolio": {
                    "initial_cash": 10000.0,
                    "max_abs_exposure": 1.0,
                    "allow_short": allow_short
                },
                "cost_model": {
                    "taker_fee": cost_model.taker_fee,
                    "half_spread": cost_model.half_spread,
                    "slippage": cost_model.slippage
                },
                "execution_timing": "NEXT_BAR_OPEN",
                "terminal_liquidation": "LAST_BAR_CLOSE",
                "market_model": market_model,
                "outage_registry_present": outage_registry is not None"""

new_ident = """                "portfolio": {
                    "initial_cash": 10000.0,
                    "max_abs_exposure": 1.0,
                    "allow_short": exposure_policy == ExposurePolicy.BIDIRECTIONAL
                },
                "cost_model": {
                    "taker_fee": cost_model.taker_fee,
                    "half_spread": cost_model.half_spread,
                    "slippage": cost_model.slippage
                },
                "execution_timing": "NEXT_BAR_OPEN",
                "terminal_liquidation": "LAST_BAR_CLOSE",
                "market_model": market_model.value,
                "exposure_policy": exposure_policy.value,
                "outage_registry_identity": outage_registry.identity() if hasattr(outage_registry, 'identity') else (outage_registry is not None),
                "manifest_digest": manifest_digest,
                "runtime_digest": dataset_digest"""
code = code.replace(old_ident, new_ident)

code = code.replace("portfolio_config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0, allow_short=allow_short)",
                    "portfolio_config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0, allow_short=(exposure_policy == ExposurePolicy.BIDIRECTIONAL))")

# Fix fields logic
code = code.replace("first_decision_ts = None\n    first_exec_ts = None\n    first_exec_price = None", 
                    "first_decision_ts = None\n    first_submitted_target = None\n    first_exec_ts = None\n    first_exec_price = None")

code = code.replace("if first_decision_ts is None and target_exposure != 0.0:\n                    first_decision_ts = bar.timestamp_utc",
                    "if first_decision_ts is None and target_exposure != 0.0:\n                    first_decision_ts = bar.timestamp_utc\n                    first_submitted_target = target_exposure")

code = code.replace("first_exec_price=first_exec_price,\n        liq_ts=liq_ts,\n        liq_price=liq_price,\n        backtest_identity=backtest_identity,",
                    "first_submitted_target=first_submitted_target,\n        first_exec_price=first_exec_price,\n        liq_ts=liq_ts,\n        liq_price=liq_price,\n        backtest_identity=backtest_identity,")

old_run = """def run_trend_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
    allow_short: bool = True,
    market_model: str | None = None,
) -> TrendBacktestReport:"""

new_run = """def run_trend_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
    market_model: MarketModel = MarketModel.PERPETUAL,
    exposure_policy: ExposurePolicy = ExposurePolicy.BIDIRECTIONAL,
    manifest_digest: str | None = None,
) -> TrendBacktestReport:"""
code = code.replace(old_run, new_run)

# We must remove the fallback market_model assignment inside run_trend_backtest.
old_fallback = """    if market_model is None:
        market_model = "SPOT" if "SPOT" in venue else ("FOREX_MARGIN" if asset == AssetClass.FOREX else "PERPETUAL")

    res_strategy = _run_single_backtest(bars, config, cost_model, "strategy", outage_registry, eval_start_ms, allow_short, market_model)
    res_flat = _run_single_backtest(bars, config, cost_model, "flat", outage_registry, eval_start_ms, allow_short, market_model)
    res_long = _run_single_backtest(bars, config, cost_model, "long", outage_registry, eval_start_ms, allow_short, market_model)"""

new_fallback = """
    res_strategy = _run_single_backtest(bars, config, cost_model, "strategy", outage_registry, eval_start_ms, market_model, exposure_policy, manifest_digest)
    res_flat = _run_single_backtest(bars, config, cost_model, "flat", outage_registry, eval_start_ms, market_model, exposure_policy, manifest_digest)
    res_long = _run_single_backtest(bars, config, cost_model, "long", outage_registry, eval_start_ms, market_model, exposure_policy, manifest_digest)"""
code = code.replace(old_fallback, new_fallback)

# The exception handling inside mode == "strategy":
old_except = """            except InsufficientHistoryError:
                target_exposure = 0.0"""
new_except = """            except InsufficientHistoryError:
                target_exposure = 0.0
            except Exception as e:
                # The user says: No bare except or strategy-level except Exception
                # Wait, "DataQualityError propagates; RuntimeError propagates"
                # "Only InsufficientHistoryError may produce flat during warm-up."
                raise e"""
code = code.replace(old_except, new_except)

with open(path, "w") as f:
    f.write(code)
