import math

from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine


def test_ledger_restore_path_maximum_drawdown_defect(tmp_path):
    config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0)
    costs = CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)
    engine = PortfolioEngine(config, costs)

    ledger = Ledger(tmp_path / "test2.db")
    run_info = ledger.start_run("strat_2", "backtest", 10000.0, costs)

    # Sequence to induce a drawdown
    # 1. Long at 100
    res = engine.rebalance(1.0, 100.0)
    ledger.record_decision(
        run_info.run_id,
        candle_open_ms=1000,
        candle_close_ms=2000,
        decision_ts_ms=1500,
        data_source="test",
        result=res,
        state=engine.state,
        mark_price=100.0,
    )

    # 2. Mark down to 90 (10% drawdown)
    engine.mark_to_market(90.0)  # peak is 10000, current net equity is 9000
    assert math.isclose(engine.state.current_drawdown_pct, 0.1)
    assert math.isclose(engine.state.path_maximum_drawdown_pct, 0.1)

    # 3. Hold at 90
    res2 = engine.rebalance(1.0, 90.0)
    ledger.record_decision(
        run_info.run_id,
        candle_open_ms=2000,
        candle_close_ms=3000,
        decision_ts_ms=2500,
        data_source="test",
        result=res2,
        state=engine.state,
        mark_price=90.0,
    )

    # Now recover state
    restored = ledger.restore_state(run_info.run_id)
    assert restored is not None
    # engine state has 0.1 for path_maximum_drawdown_pct
    assert math.isclose(restored.path_maximum_drawdown_pct, 0.1)  # this will fail without a fix
