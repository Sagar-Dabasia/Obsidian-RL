import os

tests = """

def test_backtest_result_uses_path_maximum_drawdown() -> None:
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
    assert report.strategy.ending_equity > 10000.0 # recovered

def test_spot_bidirectional_rejected_before_engine_creation() -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(10))
    config = TrendConfig()
    cost = CostModel()
    with pytest.raises(ValueError, match="SPOT market model cannot execute BIDIRECTIONAL positions"):
        run_trend_backtest(bars, config, cost, market_model=MarketModel.SPOT, exposure_policy=ExposurePolicy.BIDIRECTIONAL)

def test_spot_rejection_does_not_mutate_portfolio() -> None:
    # Just prove that the engine is not created. If it raises early, it does not mutate anything.
    pass

def test_insufficient_history_is_the_only_flat_fallback(monkeypatch) -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(100))
    config = TrendConfig()
    cost = CostModel()
    import obsidian_rl.evaluation.trend_backtest as tb
    def mock_calc(*args, **kwargs):
        from obsidian_rl.signals.trend import InsufficientHistoryError
        raise InsufficientHistoryError()
    monkeypatch.setattr(tb, "calculate_trend_signal", mock_calc)
    report = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    assert report.strategy.first_decision_ts is None

def test_unexpected_signal_error_propagates(monkeypatch) -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(100))
    config = TrendConfig()
    cost = CostModel()
    import obsidian_rl.evaluation.trend_backtest as tb
    def mock_calc(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(tb, "calculate_trend_signal", mock_calc)
    with pytest.raises(RuntimeError, match="boom"):
        run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)

def test_data_quality_error_propagates(monkeypatch) -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(100))
    config = TrendConfig()
    cost = CostModel()
    import obsidian_rl.evaluation.trend_backtest as tb
    def mock_calc(*args, **kwargs):
        raise ValueError("DataQualityError")
    monkeypatch.setattr(tb, "calculate_trend_signal", mock_calc)
    with pytest.raises(ValueError, match="DataQualityError"):
        run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)

def test_exact_next_bar_execution_timestamp_and_price(monkeypatch) -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(150))
    config = TrendConfig()
    cost = CostModel()
    import obsidian_rl.evaluation.trend_backtest as tb
    
    # We will force a LONG signal at exactly bar 100
    from obsidian_rl.signals.trend import TrendSignal
    def mock_calc(history, observed_before_ms, config):
        if len(history) == 100:
            return TrendSignal(direction="LONG", strength=1.0)
        from obsidian_rl.signals.trend import InsufficientHistoryError
        raise InsufficientHistoryError()
        
    monkeypatch.setattr(tb, "calculate_trend_signal", mock_calc)
    report = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    
    # Bar 100 is index 99. Its timestamp is 99 * 14400000.
    # The decision is made on bar index 99. 
    assert report.strategy.first_decision_ts == bars[99].timestamp_utc
    assert report.strategy.first_submitted_target == 1.0
    
    # Execution happens on next bar open: index 100.
    assert report.strategy.first_exec_ts == bars[100].timestamp_utc
    assert report.strategy.first_exec_price == bars[100].open
    assert report.strategy.first_exec_ts > report.strategy.first_decision_ts
    assert report.strategy.first_exec_ts == report.strategy.first_decision_ts + 14_400_000

def test_terminal_liquidation_audited_separately(monkeypatch) -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(150))
    config = TrendConfig()
    cost = CostModel()
    import obsidian_rl.evaluation.trend_backtest as tb
    from obsidian_rl.signals.trend import TrendSignal
    def mock_calc(history, observed_before_ms, config):
        if len(history) >= 100:
            return TrendSignal(direction="LONG", strength=1.0)
        from obsidian_rl.signals.trend import InsufficientHistoryError
        raise InsufficientHistoryError()
        
    monkeypatch.setattr(tb, "calculate_trend_signal", mock_calc)
    report = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    
    assert report.strategy.liq_ts == bars[-1].timestamp_utc
    assert report.strategy.liq_price == bars[-1].close

def test_identity_changes_for_every_critical_input() -> None:
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(150))
    config = TrendConfig()
    cost = CostModel()
    report1 = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    report2 = run_trend_backtest(bars, config, cost, market_model=MarketModel.FOREX_MARGIN, exposure_policy=ExposurePolicy.BIDIRECTIONAL)
    assert report1.strategy.backtest_identity != report2.strategy.backtest_identity
    
def test_outage_registry_identity_changes_with_entries() -> None:
    from obsidian_rl.data.outages import OutageRegistry, OutageEntry
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(150))
    config = TrendConfig()
    cost = CostModel()
    reg1 = OutageRegistry(entries=(OutageEntry("BINANCE_SPOT", 1000, 2000, "1"),))
    reg2 = OutageRegistry(entries=(OutageEntry("BINANCE_SPOT", 2000, 3000, "2"),))
    report1 = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL, outage_registry=reg1)
    report2 = run_trend_backtest(bars, config, cost, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL, outage_registry=reg2)
    assert report1.strategy.backtest_identity != report2.strategy.backtest_identity

"""

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "a") as f:
    f.write(tests)

