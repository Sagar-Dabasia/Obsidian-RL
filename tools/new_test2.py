from obsidian_rl.evaluation.trend_backtest import run_trend_backtest
from obsidian_rl.signals.trend import TrendConfig
from obsidian_rl.portfolio.costs import CostModel

def test_same_bar_execution_is_impossible() -> None:
    # Verify that the signal generated on bar T does not execute on bar T's open/close.
    # It must execute at the next bar's open.
    # We can verify this by checking that first_exec_ts > first_decision_ts.
    bars = tuple(make_bar(i * 14_400_000, close=100.0 + i) for i in range(800))
    config = TrendConfig(trend_window=50, signal_threshold=0.1)
    cost = CostModel(taker_fee=0.001)
    
    # Run backtest
    report = run_trend_backtest(bars, config, cost)
    
    # We must have made a decision and executed it
    assert report.strategy.first_decision_ts is not None
    assert report.strategy.first_exec_ts is not None
    
    # Execution must happen strictly after the decision bar!
    assert report.strategy.first_exec_ts > report.strategy.first_decision_ts
