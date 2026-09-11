import math
from typing import NamedTuple

from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import (
    PortfolioConfig,
    PortfolioEngine,
    PortfolioState,
)


class ActionStep(NamedTuple):
    target: float
    exec_price: float
    funding_rate: float = 0.0


def _run_engine(engine: PortfolioEngine, steps: list[ActionStep]) -> PortfolioState:
    for step in steps:
        if step.funding_rate != 0.0:
            engine.apply_funding(step.exec_price, step.funding_rate)
        engine.rebalance(step.target, step.exec_price)
    return engine.state


def test_flat_to_long_parity():
    # Setup
    config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0)
    costs = CostModel(taker_fee=0.001, half_spread=0.0, slippage=0.0)  # 10 bps
    engine = PortfolioEngine(config, costs)

    # Action: Flat -> Long at price 100
    res = engine.rebalance(1.0, 100.0)

    # Expected:
    # Target = 1.0
    # Equity = 10000.0
    # Target Qty = 1.0 * 10000 / 100 = 100
    # Notional = 100 * 100 = 10000
    # Fee = 10000 * 0.001 = 10.0
    # Cash = 10000 - 10 = 9990.0

    assert math.isclose(res.executed_target, 10000.0 / 9990.0)
    assert res.delta_qty == 100.0
    assert res.traded_notional == 10000.0
    assert res.fee == 10.0

    state = engine.state
    assert state.qty == 100.0
    assert state.cash == 9990.0
    assert state.avg_entry_price == 100.0
    assert state.realized_pnl == 0.0
    assert state.unrealized_pnl(100.0) == 0.0
    assert state.net_equity(100.0) == 9990.0
    assert state.gross_equity(100.0) == 10000.0


def test_long_to_short_reversal_parity():
    config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0)
    costs = CostModel(taker_fee=0.001, half_spread=0.0, slippage=0.0)
    engine = PortfolioEngine(config, costs)

    # Go long at 100
    engine.rebalance(1.0, 100.0)

    # Reverse to short at 110
    # Equity before trade = 9990 (cash) + 100 * (110 - 100) = 10990
    # Target = -1.0
    # Target Qty = -1.0 * 10990 / 110 = -99.9090909090909
    # Current Qty = 100.0
    # Delta Qty = -199.9090909090909
    # Traded Notional = 199.9090909090909 * 110 = 21990.0
    # Fee = 21.99
    # Realized PNL on the 100 closed = 100 * (110 - 100) = 1000.0

    res = engine.rebalance(-1.0, 110.0)

    assert math.isclose(res.executed_target, -10990.0 / (10990.0 - 21.99))
    assert math.isclose(res.delta_qty, -199.9090909090909)
    assert math.isclose(res.traded_notional, 21990.0)
    assert math.isclose(res.fee, 21.99)
    assert math.isclose(res.realized_pnl_delta, 1000.0)

    state = engine.state
    assert math.isclose(state.qty, -99.9090909090909)
    assert math.isclose(state.avg_entry_price, 110.0)
    assert math.isclose(state.realized_pnl, 1000.0)
    assert math.isclose(state.fees_paid, 31.99)

    expected_cash = 9990.0 + 1000.0 - 21.99
    assert math.isclose(state.cash, expected_cash)

    # Net equity = Cash + UPNL. UPNL at 110 = 0.
    assert math.isclose(state.net_equity(110.0), expected_cash)
    assert math.isclose(state.gross_equity(110.0), expected_cash + 31.99)


def test_terminal_liquidation():
    config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0)
    costs = CostModel(taker_fee=0.001, half_spread=0.0, slippage=0.0)
    engine = PortfolioEngine(config, costs)

    engine.rebalance(1.0, 100.0)
    res = engine.liquidate(120.0)

    assert res.executed_target == 0.0
    assert res.delta_qty == -100.0
    assert engine.state.qty == 0.0
    assert engine.state.exposure(120.0) == 0.0


def test_funding_event():
    config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0)
    costs = CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)
    engine = PortfolioEngine(config, costs)

    engine.rebalance(1.0, 100.0)  # 100 qty

    # Positive funding rate means longs pay
    flow = engine.apply_funding(100.0, 0.01)  # 1% of 10000 = 100 paid
    assert flow == -100.0
    assert engine.state.cash == 9900.0
    assert engine.state.funding_paid == 100.0
    assert engine.state.net_equity(100.0) == 9900.0
    assert engine.state.gross_equity(100.0) == 10000.0


def test_ledger_engine_parity(tmp_path):
    config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0)
    costs = CostModel(taker_fee=0.001, half_spread=0.0, slippage=0.0)
    engine = PortfolioEngine(config, costs)

    ledger = Ledger(tmp_path / "test.db")
    run_info = ledger.start_run("strat_1", "backtest", 10000.0, costs)

    # Sequence: Long -> Hold -> Reverse Short -> Liquidate
    steps = [
        ActionStep(1.0, 100.0),
        ActionStep(1.0, 110.0),
        ActionStep(-1.0, 120.0),
        ActionStep(0.0, 110.0),
    ]

    for i, step in enumerate(steps):
        res = engine.rebalance(step.target, step.exec_price)
        ledger.record_decision(
            run_info.run_id,
            candle_open_ms=i * 1000,
            candle_close_ms=(i + 1) * 1000,
            decision_ts_ms=i * 1000 + 500,
            data_source="test",
            result=res,
            state=engine.state,
            mark_price=step.exec_price,
        )

        # Verify ledger restores exactly to engine state
        restored = ledger.restore_state(run_info.run_id)
        assert restored is not None
        assert math.isclose(restored.cash, engine.state.cash)
        assert math.isclose(restored.qty, engine.state.qty)
        assert math.isclose(restored.avg_entry_price, engine.state.avg_entry_price)
        assert math.isclose(restored.realized_pnl, engine.state.realized_pnl)
        assert math.isclose(restored.turnover, engine.state.turnover)
        assert math.isclose(restored.peak_equity, engine.state.peak_equity)
        # Note: path_maximum_drawdown_pct and current_drawdown_pct are inherently not stored
        # in the ledger, which is a known limitation.

    ledger.close()
