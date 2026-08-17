import os
import re

path = "src/obsidian_rl/evaluation/trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Remove parse_and_validate_manifest
content = re.sub(r'def parse_and_validate_manifest\(.*?return digest, end_ts\s*', '', content, flags=re.DOTALL)

# Update _run_single_backtest signature
old_sig = """def _run_single_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    mode: str,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
    market_model: MarketModel = MarketModel.PERPETUAL,
    exposure_policy: ExposurePolicy = ExposurePolicy.BIDIRECTIONAL,
    manifest_digest: str | None = None,
) -> TrendBacktestResult:"""

new_sig = """def _run_single_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    mode: str,
    eval_start_ms: int,
    market_model: MarketModel,
    exposure_policy: ExposurePolicy,
    outage_registry: OutageRegistry | None = None,
    manifest_digest: str | None = None,
) -> TrendBacktestResult:"""

content = content.replace(old_sig, new_sig)

# Update hash logic
old_hash = """    backtest_identity = hashlib.sha256(
        json.dumps(
            {
                "mode": mode,
                "dataset": dataset_digest,
                "asset_class": bars[0].asset_class.value,
                "venue": bars[0].venue,
                "symbol": bars[0].symbol,
                "timeframe": bars[0].timeframe.value,
                "eval_start_ms": eval_start_ms,
                "eval_end_ms": bars[-1].timestamp_utc,
                "config": config_identity,
                "portfolio": {
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
                "runtime_digest": dataset_digest
            }, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()"""

new_hash = """    tf = bars[0].timeframe
    expected_interval = tf.value_ms() if hasattr(tf, "value_ms") else 14400000
    outage_id = outage_registry.identity() if hasattr(outage_registry, 'identity') else "empty"
    backtest_identity = hashlib.sha256(
        json.dumps(
            {
                "mode": mode,
                "manifest_digest": manifest_digest,
                "runtime_digest": dataset_digest,
                "asset_class": bars[0].asset_class.value,
                "venue": bars[0].venue,
                "symbol": bars[0].symbol,
                "timeframe": tf.value,
                "data_start": bars[0].timestamp_utc,
                "eval_start_ms": eval_start_ms,
                "eval_end_excl_ms": bars[-1].timestamp_utc + expected_interval,
                "config": config_identity,
                "portfolio": {
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
                "outage_registry_identity": outage_id,
            }, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()"""

content = content.replace(old_hash, new_hash)

# Fix TrendBacktestResult dataclass and call
content = content.replace("market_model: str\n    first_decision_ts", "market_model: str\n    exposure_policy: str\n    first_decision_ts")

content = content.replace("market_model=market_model,\n        first_decision_ts", "market_model=market_model.value,\n        exposure_policy=exposure_policy.value,\n        first_decision_ts")

# Update run_trend_backtest signature
old_run_sig = """def run_trend_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
    market_model: MarketModel = MarketModel.PERPETUAL,
    exposure_policy: ExposurePolicy = ExposurePolicy.BIDIRECTIONAL,
    manifest_digest: str | None = None,
) -> TrendBacktestReport:"""

new_run_sig = """def run_trend_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    eval_start_ms: int,
    market_model: MarketModel,
    exposure_policy: ExposurePolicy,
    outage_registry: OutageRegistry | None = None,
    manifest_digest: str | None = None,
) -> TrendBacktestReport:"""

content = content.replace(old_run_sig, new_run_sig)

# Update calls to _run_single_backtest
content = content.replace(
    'res_strategy = _run_single_backtest(bars, config, cost_model, "strategy", outage_registry, eval_start_ms, market_model, exposure_policy, manifest_digest)',
    'res_strategy = _run_single_backtest(bars, config, cost_model, "strategy", eval_start_ms, market_model, exposure_policy, outage_registry, manifest_digest)'
)
content = content.replace(
    'res_flat = _run_single_backtest(bars, config, cost_model, "flat", outage_registry, eval_start_ms, market_model, exposure_policy, manifest_digest)',
    'res_flat = _run_single_backtest(bars, config, cost_model, "flat", eval_start_ms, market_model, exposure_policy, outage_registry, manifest_digest)'
)
content = content.replace(
    'res_long = _run_single_backtest(bars, config, cost_model, "long", outage_registry, eval_start_ms, market_model, exposure_policy, manifest_digest)',
    'res_long = _run_single_backtest(bars, config, cost_model, "long", eval_start_ms, market_model, exposure_policy, outage_registry, manifest_digest)'
)

# Remove broad excepts
# Find:
#             except InsufficientHistoryError:
#                 target_exposure = 0.0
#             except Exception as e:
#                 # The user says: No bare except or strategy-level except Exception
#                 # Wait, "DataQualityError propagates; RuntimeError propagates"
#                 # "Only InsufficientHistoryError may produce flat during warm-up."
#                 raise e
content = re.sub(r'            except Exception as e:.*?raise e\n', '', content, flags=re.DOTALL)


with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Backtest fixed")
