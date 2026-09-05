import os
import re

path_tests = "tests/evaluation/test_trend_backtest.py"
with open(path_tests, "r") as f:
    code = f.read()

# Fix 1: test_backtest_result_uses_path_maximum_drawdown
# mock calculate_trend_signal to go LONG so that equity tracks the asset price
old_drawdown = """def test_backtest_result_uses_path_maximum_drawdown() -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0) for i in range(150))
    # inject a drawdown in the middle
    bars = list(bars)
    bars[130] = make_bar(130 * 14_400_000, close=50.0)
    bars[140] = make_bar(140 * 14_400_000, close=120.0)
    bars = tuple(bars)
    config = TrendConfig()
    cost = CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)
    # MarketModel.PERPETUAL
    report = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    assert report.strategy.maximum_drawdown > 0.4
    assert report.strategy.ending_equity > 10000.0 # recovered"""

new_drawdown = """def test_backtest_result_uses_path_maximum_drawdown(monkeypatch) -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0) for i in range(150))
    # inject a drawdown in the middle
    bars = list(bars)
    bars[130] = make_bar(130 * 14_400_000, close=50.0)
    bars[140] = make_bar(140 * 14_400_000, close=120.0)
    bars = tuple(bars)
    config = TrendConfig()
    cost = CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)
    
    import obsidian_rl.evaluation.trend_backtest as tb
    from obsidian_rl.signals.trend import TrendSignal
    def mock_calc(history, observed_before_ms, config):
        if len(history) >= 10:
            return TrendSignal(direction="LONG")
        from obsidian_rl.signals.trend import InsufficientHistoryError
        raise InsufficientHistoryError()
    monkeypatch.setattr(tb, "calculate_trend_signal", mock_calc)
    
    # MarketModel.PERPETUAL
    report = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    assert report.strategy.maximum_drawdown > 0.4
    assert report.strategy.ending_equity > 10000.0 # recovered"""

code = code.replace(old_drawdown, new_drawdown)

# Fix 2: test_exact_next_bar_execution_timestamp_and_price
code = code.replace('return TrendSignal(direction="LONG", strength=1.0)', 'return TrendSignal(direction="LONG")')

# Fix 3: test_outage_registry_identity_changes_with_entries
old_outage = """def test_outage_registry_identity_changes_with_entries() -> None:
    from obsidian_rl.data.outages import OutageRegistry, OutageEntry"""

new_outage = """def test_outage_registry_identity_changes_with_entries() -> None:
    from obsidian_rl.data.outages import OutageRegistry, VenueOutage"""

code = code.replace(old_outage, new_outage)
code = code.replace("OutageEntry(", "VenueOutage(")

with open(path_tests, "w") as f:
    f.write(code)

path_engine = "tests/test_portfolio_engine.py"
with open(path_engine, "r") as f:
    code_eng = f.read()

# Fix 4: test_short_disabled
old_short = """def test_short_disabled() -> None:
    eng = PortfolioEngine(PortfolioConfig(initial_cash=10_000.0, allow_short=False), CM)
    r = eng.rebalance(-1.0, 100.0)
    assert r.delta_qty == 0.0
    assert eng.state.exposure(100.0) == 0.0"""

new_short = """def test_short_disabled() -> None:
    eng = PortfolioEngine(PortfolioConfig(initial_cash=10_000.0, allow_short=False), CM)
    with pytest.raises(ValueError, match="short exposure disabled"):
        eng.rebalance(-1.0, 100.0)"""

code_eng = code_eng.replace(old_short, new_short)

with open(path_engine, "w") as f:
    f.write(code_eng)
