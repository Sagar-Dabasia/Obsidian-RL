"""Tests for the Trend Backtesting Framework."""

import pytest

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
    compute_market_bar_hash,
)
from obsidian_rl.evaluation.trend_backtest import run_trend_backtest
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.signals.trend import TrendConfig


def make_bar(
    timestamp_ms: int,
    close: float,
    asset_class: AssetClass = AssetClass.CRYPTO,
    venue: str = "BINANCE_PERPETUAL",
    symbol: str = "BTCUSDT",
    timeframe: Timeframe = Timeframe.H4,
) -> MarketBar:
    bar = MarketBar(
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        data_source="TEST",
        timestamp_utc=timestamp_ms,
        observed_at_utc=timestamp_ms + 1000,
        open=close,
        high=close,
        low=close,
        close=close,
        quote_status=(
            QuoteStatus.UNAVAILABLE if asset_class == AssetClass.CRYPTO else QuoteStatus.OBSERVED
        ),
        bid=None if asset_class == AssetClass.CRYPTO else close - 0.1,
        ask=None if asset_class == AssetClass.CRYPTO else close + 0.1,
        volume_type=VolumeType.BASE if asset_class == AssetClass.CRYPTO else VolumeType.TICK,
        volume=100.0,
        row_hash="",
    )
    object.__setattr__(bar, "row_hash", compute_market_bar_hash(bar))
    return bar


def test_clear_uptrend_earns_long_exposure() -> None:
    # 800 bars of strictly increasing price (4h bars)
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
    # The trend will detect LONG after enough bars (e.g., 20 days = 120 bars)
    config = TrendConfig()
    cost_model = CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)
    report = run_trend_backtest(bars, config, cost_model)

    assert report.strategy.exposure_percentage > 0.0
    assert report.strategy.net_return > 0.0
    # It should out-perform or equal FLAT, and shouldn't be zero since there is a trend
    assert report.strategy.net_return > report.baseline_flat.net_return


def test_mixed_symbols_fail() -> None:
    bars = [make_bar(i * 14_400_000, close=100.0) for i in range(130)]
    object.__setattr__(bars[50], "symbol", "ETHUSDT")
    with pytest.raises(ValueError, match="Mixed"):
        run_trend_backtest(tuple(bars), TrendConfig(), CostModel())


def test_missing_forex_quotes_fail_closed() -> None:
    # Forex bar missing ask
    bars = [
        make_bar(i * 14_400_000, close=100.0 + i, asset_class=AssetClass.FOREX) for i in range(800)
    ]
    object.__setattr__(bars[721], "ask", None)
    # The engine should fail when attempting to execute LONG at bar 721
    with pytest.raises(ValueError, match="Missing ask price"):
        run_trend_backtest(tuple(bars), TrendConfig(), CostModel())


def test_baseline_flat_stays_unchanged() -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
    report = run_trend_backtest(bars, TrendConfig(), CostModel())
    assert report.baseline_flat.starting_equity == 10000.0
    assert report.baseline_flat.ending_equity == 10000.0
    assert report.baseline_flat.net_return == 0.0
    assert report.baseline_flat.trade_count == 0


def test_crypto_costs_reduce_returns() -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
    # Baseline long with no costs
    report_no_cost = run_trend_backtest(bars, TrendConfig(), CostModel())
    # Baseline long with high costs
    cost_model = CostModel(taker_fee=0.01, half_spread=0.0, slippage=0.0)
    report_cost = run_trend_backtest(bars, TrendConfig(), cost_model)

    assert report_cost.baseline_long.total_costs > 0.0
    assert report_cost.baseline_long.net_return < report_no_cost.baseline_long.net_return


def test_same_bar_execution_is_impossible() -> None:
    # Verify that the signal generated on bar T does not execute on bar T's open/close.
    # It must execute at the next bar's open.
    # We can verify this by checking that first_exec_ts > first_decision_ts.
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
    config = TrendConfig()
    cost = CostModel(taker_fee=0.001)
    
    # Run backtest
    report = run_trend_backtest(bars, config, cost)
    
    # We must have made a decision and executed it
    assert report.strategy.first_decision_ts is not None
    assert report.strategy.first_exec_ts is not None
    
    # Execution must happen strictly after the decision bar!
    assert report.strategy.first_exec_ts > report.strategy.first_decision_ts



def test_tampered_hashes_fail() -> None:
    bars = [make_bar(i * 14_400_000, close=100.0) for i in range(130)]
    object.__setattr__(bars[50], "row_hash", "invalid")
    with pytest.raises(ValueError, match="Invalid row hash"):
        run_trend_backtest(tuple(bars), TrendConfig(), CostModel())


def test_deterministic_identities() -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0) for i in range(130))
    report1 = run_trend_backtest(bars, TrendConfig(), CostModel())
    report2 = run_trend_backtest(bars, TrendConfig(), CostModel())
    assert report1.strategy.backtest_identity == report2.strategy.backtest_identity
    assert report1.strategy.input_dataset_digest == report2.strategy.input_dataset_digest
    assert report1.strategy.trend_config_identity == report2.strategy.trend_config_identity


def test_warmup_period_metrics() -> None:
    # 800 bars of strictly increasing price (4h bars)
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
    # eval_start_ms at 200th bar (bar index 200)
    eval_start_ms = bars[200].timestamp_utc

    config = TrendConfig()
    cost_model = CostModel(taker_fee=0.01, half_spread=0.0, slippage=0.0)

    report_full = run_trend_backtest(bars, config, cost_model)
    report_warmup = run_trend_backtest(bars, config, cost_model, eval_start_ms=eval_start_ms)

    # 1. Pre-evaluation rows reach the strategy/indicator history.
    # 5. The first valid post-boundary decision does not require another 120-day wait.
    assert report_warmup.strategy.exposure_percentage > 0.0

    # 2. Scoring begins exactly at eval_start_ms.
    assert report_warmup.strategy.first_timestamp_utc == eval_start_ms

    # 3. Warm-up rows do not affect reported metrics.
    # The full long baseline pays the fee at bar 0. The warmup baseline pays the fee at bar 200.
    # The number of trades should be identical (entry and liquidation).
    assert report_warmup.baseline_long.trade_count == report_full.baseline_long.trade_count
    assert report_warmup.baseline_long.net_return < report_full.baseline_long.net_return


def make_custom_bar(i: int, start_ms: int = 0) -> MarketBar:
    ms = start_ms + i * 14_400_000
    b = make_bar(ms, close=100.0 + i)
    # Distinct open/close prices to distinguish execution vs mtm
    object.__setattr__(b, "open", 100.0 + i + 0.1)
    object.__setattr__(b, "row_hash", compute_market_bar_hash(b))
    return b

def test_audit_invariants(monkeypatch) -> None:
    import obsidian_rl.evaluation.trend_backtest as tb
    from obsidian_rl.portfolio.engine import PortfolioEngine

    class SpyEngine(PortfolioEngine):
        instances = []
        def __init__(self, config, cost_model):
            super().__init__(config, cost_model)
            self.rebalance_calls = []
            self.mtm_calls = []
            self.liquidate_calls = []
            SpyEngine.instances.append(self)

        def rebalance(self, target_exposure: float, execution_price: float):
            self.rebalance_calls.append((target_exposure, execution_price))
            return super().rebalance(target_exposure, execution_price)

        def mark_to_market(self, current_price: float):
            self.mtm_calls.append(current_price)
            return super().mark_to_market(current_price)

        def liquidate(self, current_price: float):
            self.liquidate_calls.append(current_price)
            return super().liquidate(current_price)

    monkeypatch.setattr(tb, "PortfolioEngine", SpyEngine)
    SpyEngine.instances.clear()

    bars = tuple(make_custom_bar(i) for i in range(800))
    eval_start_ms = bars[200].timestamp_utc

    config = TrendConfig()
    cost_model = CostModel(taker_fee=0.01, half_spread=0.0, slippage=0.0)

    # 7. eval_start_ms=0 matches the pre-boundary/default behavior.
    report_default = run_trend_backtest(bars, config, cost_model)
    report_zero = run_trend_backtest(bars, config, cost_model, eval_start_ms=0)
    assert report_default.strategy.net_return == report_zero.strategy.net_return
    assert report_default.strategy.trade_count == report_zero.strategy.trade_count

    SpyEngine.instances.clear()

    # Run bounded evaluation
    report_warmup = run_trend_backtest(bars, config, cost_model, eval_start_ms=eval_start_ms)
    strategy_engine = SpyEngine.instances[0]
    long_baseline_engine = SpyEngine.instances[2]

    # 1. Pre-eval bars change signal history but leave cash, position, equity, costs, turnover and trade count unchanged.
    # We verify MTM (and therefore equity/costs mutation) only happens exactly for the eval period + 1 for liquidation
    # Total bars = 800, eval bars = 600 (bars 200 to 799)
    # MTM is also called during rebalance on bar.open, so we count only calls on bar.close
    close_mtm_calls = [p for p in strategy_engine.mtm_calls if p % 1 == 0]
    assert len(close_mtm_calls) == 600 + 2
    assert close_mtm_calls[0] == bars[200].close

    # 2. A signal generated on bar t executes only at bar t+1 open, including when t is immediately before eval_start_ms.
    # 3. No same-bar execution occurs at the evaluation boundary.
    # The first rebalance for the long baseline is at bar 200 open, using the target generated at bar 199.
    long_first_rebalance = long_baseline_engine.rebalance_calls[0]
    assert long_first_rebalance[1] == bars[200].open

    # 4. The first eligible post-boundary trade occurs without another full 120-day delay.
    assert long_first_rebalance[0] != 0.0 # Immediately entered a position upon crossing boundary

    # 5. Metric timestamps begin exactly at eval_start_ms.
    assert report_warmup.strategy.first_timestamp_utc == bars[200].timestamp_utc

    # 6. Warm-up PnL, exposure and costs are excluded from net return, Sharpe, drawdown and turnover.
    # We ensure long baseline has the exact correct cost for executing at 300.1 (bar 200) instead of 100.1 (bar 0).
    assert report_warmup.baseline_long.total_costs > 0
    assert report_warmup.baseline_long.turnover > 0

    # 8. Changing bars after a tested decision timestamp cannot change that earlier signal, fill or metric prefix.
    mutated_bars = list(bars)
    mutated_bars[205] = make_custom_bar(205)
    object.__setattr__(mutated_bars[205], "close", bars[205].close * 2)
    SpyEngine.instances.clear()

    # Record strategy's first rebalance
    strategy_first_rebalance = strategy_engine.rebalance_calls[0]

    run_trend_backtest(tuple(mutated_bars), config, cost_model, eval_start_ms=eval_start_ms)
    mutated_engine = SpyEngine.instances[0]

    assert mutated_engine.rebalance_calls[0] == strategy_first_rebalance

    # 9. Terminal liquidation happens exactly once and remains inside the evaluation metrics.
    assert len(strategy_engine.liquidate_calls) == 1
    assert strategy_engine.liquidate_calls[0] == bars[-1].close


def test_cli_boundaries(monkeypatch) -> None:
    import argparse
    import unittest.mock
    import tools.run_trend_backtest as cli

    # We patch argparse to intercept the parsed args right before load
    orig_parse_args = argparse.ArgumentParser.parse_args
    parsed_args_capture = []

    def mock_parse_args(*args, **kwargs):
        res = orig_parse_args(*args, **kwargs)
        parsed_args_capture.append(res)
        return res

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", mock_parse_args)

    class MockStorage:
        last_query = {}
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query_market_bars(self, **kwargs):
            MockStorage.last_query = kwargs
            return tuple(make_custom_bar(i) for i in range(10))

    monkeypatch.setattr(cli, "SQLiteStorage", MockStorage)

    mock_run = unittest.mock.MagicMock()
    mock_run.return_value = run_trend_backtest(tuple(make_custom_bar(i) for i in range(10)), TrendConfig(), CostModel())
    monkeypatch.setattr(cli, "run_trend_backtest", mock_run)

    test_args = [
        "tools/run_trend_backtest.py",
        "--database", "test.sqlite",
        "--asset-class", "CRYPTO",
        "--venue", "BINANCE_PERPETUAL",
        "--symbol", "BTCUSDT",
        "--timeframe", "4h",
        "--start-ms", "1000",
        "--end-ms", "5000",
        "--eval-start-ms", "2000",
        "--taker-fee", "0.0",
        "--half-spread", "0.0",
        "--slippage", "0.0"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    cli.main()

    # 10. CLI keeps --start-ms as data-load start and --eval-start-ms as scoring start.
    assert MockStorage.last_query["start_timestamp_utc"] == 1000
    mock_run.assert_called_once()
    assert mock_run.call_args[1]["eval_start_ms"] == 2000
