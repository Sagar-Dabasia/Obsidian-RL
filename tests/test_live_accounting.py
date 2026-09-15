"""Phase 7 tests: live-paper funding, run metadata, and durable failure evidence."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from obsidian_rl.config import Settings
from obsidian_rl.data.binance_client import DataFetchError
from obsidian_rl.evaluation.backtest import run_backtest
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.ledger.ledger import EventConflictError, Ledger
from obsidian_rl.live.paper_trader import PaperTrader, replay_candles
from obsidian_rl.live.runner import LivePaperRunner
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig
from obsidian_rl.strategies.base import Strategy
from obsidian_rl.strategies.baselines import AlwaysFlat, ThresholdMomentum
from tests.conftest import make_candles


class FaultyStrategy(Strategy):
    strategy_id = "faulty-strategy"

    def propose(self, market_features: np.ndarray, portfolio_obs: np.ndarray) -> float:
        raise RuntimeError("simulated model inference failure")


class NonFiniteTargetStrategy(Strategy):
    strategy_id = "non-finite-strategy"

    def propose(self, market_features: np.ndarray, portfolio_obs: np.ndarray) -> float:
        return float("nan")


class BoolTargetStrategy(Strategy):
    strategy_id = "bool-target-strategy"

    def propose(self, market_features: np.ndarray, portfolio_obs: np.ndarray) -> Any:
        return True  # type: ignore


def make_dummy_candles(n: int = WARMUP_ROWS + 20) -> pd.DataFrame:
    return make_candles(n)


def test_runner_metadata_equals_engine_configuration(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    strategy = ThresholdMomentum()
    pc = PortfolioConfig(initial_cash=20_000.0, max_abs_exposure=0.8, min_trade_notional=15.0)
    cm = CostModel(taker_fee=0.0008, half_spread=0.0001, slippage=0.0002)

    runner = LivePaperRunner(
        settings,
        strategy,
        portfolio_config=pc,
        cost_model=cm,
        initial_cash=20_000.0,
    )

    assert runner.trader.engine.config.initial_cash == 20_000.0
    assert runner.trader.engine.config.max_abs_exposure == 0.8
    assert runner.trader.engine.costs.taker_fee == 0.0008

    run_info = runner.ledger.get_run(runner.run_id)
    assert run_info is not None
    assert run_info["initial_cash"] == 20_000.0


def test_empty_incomplete_cost_metadata_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(settings.ledger_path)

    ledger._conn.execute(
        "INSERT INTO runs (run_id, strategy_id, mode, started_at_ms, initial_cash, cost_model_json)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("legacy-1", "s1", "live-paper", 1000, 10000.0, "{}"),
    )
    ledger._conn.commit()

    strategy = AlwaysFlat()
    with pytest.raises(ValueError, match="empty or incomplete cost metadata"):
        LivePaperRunner(settings, strategy, run_id="legacy-1")


def test_resume_configuration_mismatch_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    strategy = AlwaysFlat()

    runner1 = LivePaperRunner(settings, strategy)
    run_id = runner1.run_id

    diff_settings = Settings(
        symbol="ETHUSDT", data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3"
    )
    with pytest.raises(ValueError, match="resume configuration mismatch"):
        LivePaperRunner(diff_settings, strategy, run_id=run_id)


def test_canonical_json_rejects_non_finite_values(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    with pytest.raises(ValueError, match="invalid cost_model field"):
        ledger.start_run("s1", "live-paper", 10_000.0, {"taker_fee": float("nan")})

    with pytest.raises(ValueError, match="initial_cash must be positive and finite"):
        ledger.start_run("s1", "live-paper", float("inf"), CostModel())


def test_funding_calculations_long_short_flat(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("s1", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(AlwaysFlat(), ledger, run.run_id)

    flow = trader.apply_funding_event(100_000, 0.001, 100.0)
    assert flow == 0.0
    assert trader.engine.state.cash == 10_000.0

    trader.engine.state.qty = 1.0
    flow_long_pos = trader.apply_funding_event(200_000, 0.001, 100.0)
    assert pytest.approx(flow_long_pos) == -0.1
    assert pytest.approx(trader.engine.state.cash) == 9999.9

    flow_long_neg = trader.apply_funding_event(300_000, -0.001, 100.0)
    assert pytest.approx(flow_long_neg) == 0.1
    assert pytest.approx(trader.engine.state.cash) == 10_000.0

    trader.engine.state.qty = -1.0
    flow_short_pos = trader.apply_funding_event(400_000, 0.001, 100.0)
    assert pytest.approx(flow_short_pos) == 0.1
    assert pytest.approx(trader.engine.state.cash) == 10_000.1


def test_duplicate_and_conflicting_funding_events(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("s1", "live-paper", 10_000.0, CostModel())

    key = f"{run.run_id}:funding:1000"
    res1 = ledger.record_funding(
        run.run_id,
        funding_time_ms=1000,
        rate=0.001,
        mark_price=100.0,
        position_qty=1.0,
        cash_flow=-0.1,
        resulting_cash=9999.9,
        resulting_equity=10099.9,
        funding_total=0.1,
        idempotency_key=key,
    )
    assert res1 is True

    res2 = ledger.record_funding(
        run.run_id,
        funding_time_ms=1000,
        rate=0.001,
        mark_price=100.0,
        position_qty=1.0,
        cash_flow=-0.1,
        resulting_cash=9999.9,
        resulting_equity=10099.9,
        funding_total=0.1,
        idempotency_key=key,
    )
    assert res2 is False

    with pytest.raises(EventConflictError, match="conflict with differing contents"):
        ledger.record_funding(
            run.run_id,
            funding_time_ms=1000,
            rate=0.002,
            mark_price=100.0,
            position_qty=1.0,
            cash_flow=-0.2,
            resulting_cash=9999.8,
            resulting_equity=10099.8,
            funding_total=0.2,
            idempotency_key=key,
        )


def test_funding_persistence_failure_restores_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("s1", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(AlwaysFlat(), ledger, run.run_id)
    trader.engine.state.qty = 1.0

    orig_cash = trader.engine.state.cash

    def mock_record_funding(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated ledger write failure")

    monkeypatch.setattr(ledger, "record_funding", mock_record_funding)

    with pytest.raises(RuntimeError, match="simulated ledger write failure"):
        trader.apply_funding_event(1000, 0.001, 100.0)

    assert trader.engine.state.cash == orig_cash


def test_funding_during_backfill_creates_no_trades(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("s1", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(AlwaysFlat(), ledger, run.run_id)

    trader.apply_funding_event(1000, 0.001, 100.0)

    assert trader.engine.state.trade_count == 0
    assert trader.engine.state.turnover == 0.0
    assert len(ledger.decisions(run.run_id)) == 0
    assert len(ledger.funding_events(run.run_id)) == 1


def test_restore_uses_funding_state_newer_than_last_decision(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("s1", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(AlwaysFlat(), ledger, run.run_id)

    candles = make_dummy_candles(WARMUP_ROWS + 5)
    replay_candles(trader, candles)

    last_dec = ledger.last_decision(run.run_id)
    assert last_dec is not None
    last_ms = int(last_dec["candle_open_ms"])

    trader.engine.state.qty = 1.0
    trader.apply_funding_event(last_ms + 1000, 0.001, 100.0)

    restored = ledger.restore_state(run.run_id)
    assert restored is not None
    assert pytest.approx(restored.funding_paid) == trader.engine.state.funding_paid
    assert pytest.approx(restored.cash) == trader.engine.state.cash


def test_closed_run_rejects_funding(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("s1", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(AlwaysFlat(), ledger, run.run_id)

    trader.close_session(100.0)

    with pytest.raises(ValueError, match=r"closed run .* cannot receive funding"):
        trader.apply_funding_event(1000, 0.001, 100.0)


def test_replay_backtest_funding_parity(tmp_path: Path) -> None:
    candles = make_dummy_candles(WARMUP_ROWS + 10)
    cm = CostModel(taker_fee=0.0005, half_spread=0.00005, slippage=0.0001)

    f_time = int(candles.iloc[WARMUP_ROWS + 2]["close_time"])
    funding_rates = pd.DataFrame(
        [
            {
                "funding_time_ms": f_time,
                "funding_rate": 0.001,
                "mark_price": float(candles.iloc[WARMUP_ROWS + 2]["close"]),
            }
        ]
    )

    strategy = ThresholdMomentum()
    bt_res = run_backtest(candles, strategy, cost_model=cm, funding_rates=funding_rates)

    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("threshold-momentum", "replay", 10_000.0, cm)
    trader = PaperTrader(strategy, ledger, run.run_id, cost_model=cm)

    replay_candles(trader, candles, funding_rates=funding_rates)
    trader.close_session(float(candles.iloc[-1]["close"]))

    assert pytest.approx(trader.engine.state.cash) == bt_res.final_state_summary["final_equity"]
    assert pytest.approx(trader.engine.state.funding_paid) == bt_res.final_state_summary["funding"]
    assert (
        pytest.approx(trader.engine.state.realized_pnl)
        == bt_res.final_state_summary["realized_pnl"]
    )
    assert trader.engine.state.trade_count == int(bt_res.final_state_summary["trade_count"])


def test_decision_exception_persists_sanitized_reason_and_fails_flat(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("faulty", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(FaultyStrategy(), ledger, run.run_id)

    candles = make_dummy_candles(WARMUP_ROWS + 2)
    replay_candles(trader, candles)

    failures = [row for row in ledger.decisions(run.run_id) if row["rejection_reason"]]
    assert len(failures) > 0
    assert "fail-flat: strategy prediction failure" in failures[0]["rejection_reason"]


def test_invalid_non_finite_strategy_target_is_recorded(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("non-finite", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(NonFiniteTargetStrategy(), ledger, run.run_id)

    candles = make_dummy_candles(WARMUP_ROWS + 2)
    replay_candles(trader, candles)

    failures = [row for row in ledger.decisions(run.run_id) if row["rejection_reason"]]
    assert len(failures) > 0
    assert "non-finite strategy target" in failures[0]["rejection_reason"]


def test_failure_event_write_failure_stops_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("faulty", "live-paper", 10_000.0, CostModel())
    trader = PaperTrader(FaultyStrategy(), ledger, run.run_id)

    def mock_record_failure(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("ledger failure store down")

    monkeypatch.setattr(ledger, "record_failure", mock_record_failure)

    candles = make_dummy_candles(WARMUP_ROWS + 2)
    with pytest.raises(RuntimeError, match="ledger failure store down"):
        replay_candles(trader, candles)


def test_runner_exception_recorded_then_reraised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    strategy = AlwaysFlat()

    runner = LivePaperRunner(settings, strategy)

    def mock_fetch_klines(*args: Any, **kwargs: Any) -> None:
        raise DataFetchError("simulated REST connection timeout")

    monkeypatch.setattr(runner.rest, "fetch_klines", mock_fetch_klines)

    with pytest.raises(DataFetchError, match="simulated REST connection timeout"):
        runner.backfill()

    events = runner.ledger._conn.execute(
        "SELECT * FROM run_events WHERE run_id=? AND event_type='failure_event'",
        (runner.run_id,),
    ).fetchall()
    assert len(events) == 1
    assert runner.ledger.get_closure(runner.run_id) is None


# =============================================================================
# RT004 Regression: funding restart recovery with decision -> funding -> close -> reopen
# =============================================================================


def test_restart_recovery_decision_funding_close_reopen(tmp_path: Path) -> None:
    """RT004: Verify exact persistence/reopen path for funding after decision."""
    from obsidian_rl.portfolio.costs import CostModel
    from obsidian_rl.strategies.baselines import AlwaysFlat

    db_path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(db_path)

    run = ledger.start_run("rt004-test", "live-paper", 10_000.0, CostModel())
    run_id = run.run_id

    # Step 1: Create PaperTrader to get engine
    trader = PaperTrader(AlwaysFlat(), ledger, run_id, cost_model=CostModel())
    eng = trader.engine

    # Step 1: Record a portfolio decision with nonzero position
    # Manually build state to avoid warm-up complexity
    result = eng.rebalance(1.0, 100.0)  # long 100% at price 100 -> qty = 100
    ledger.record_decision(
        run_id,
        candle_open_ms=900_000,
        candle_close_ms=1_799_999,
        decision_ts_ms=1_800_000,
        data_source="test",
        result=result,
        state=eng.state,
        mark_price=100.0,
    )

    # Step 2: Apply funding event AFTER the decision (funding_time_ms > dec_ms) via trader
    # This applies to BOTH engine and ledger, simulating real workflow
    funding_time_ms = 1_800_500  # strictly after decision close_ms (1_799_999)
    rate = 0.001
    mark_price = 100.0
    trader.apply_funding_event(funding_time_ms, rate, mark_price)

    # Capture expected state AFTER funding applied to engine
    expected_cash = eng.state.cash
    expected_funding_paid = eng.state.funding_paid
    expected_qty = eng.state.qty
    expected_avg_entry = eng.state.avg_entry_price
    expected_equity_at_100 = eng.state.net_equity(100.0)

    # Step 3: Close the ledger (simulate process exit)
    ledger.close()

    # Step 4: NEW Ledger instance against same DB
    reopened = Ledger(db_path)

    # Step 5: Call restore_state
    restored = reopened.restore_state(run_id)

    # Step 6: Assert exact match
    assert restored is not None, "restore_state should return a state"
    assert restored.cash == pytest.approx(expected_cash), (
        f"cash mismatch: {restored.cash} vs {expected_cash}"
    )
    assert restored.funding_paid == pytest.approx(expected_funding_paid), (
        f"funding_paid mismatch: {restored.funding_paid} vs {expected_funding_paid}"
    )
    assert restored.qty == pytest.approx(expected_qty), (
        f"qty mismatch: {restored.qty} vs {expected_qty}"
    )
    assert restored.avg_entry_price == pytest.approx(expected_avg_entry), (
        f"avg_entry_price mismatch: {restored.avg_entry_price} vs {expected_avg_entry}"
    )
    assert restored.net_equity(100.0) == pytest.approx(expected_equity_at_100), (
        f"equity mismatch: {restored.net_equity(100.0)} vs {expected_equity_at_100}"
    )
    assert restored.turnover == pytest.approx(eng.state.turnover)
    assert restored.trade_count == eng.state.trade_count
    assert restored.peak_equity == pytest.approx(eng.state.peak_equity)


# =============================================================================
# RT004 Multi-asset Persistence Regression Tests
# =============================================================================


def test_decision_restart_multi_asset_exact_equality(tmp_path: Path) -> None:
    """RT004: BTCUSDT + ETHUSDT populated, persist -> close Ledger -> NEW Ledger -> restore_state, exact per-symbol equality."""  # noqa: E501
    from obsidian_rl.portfolio.costs import CostModel
    from obsidian_rl.strategies.baselines import AlwaysFlat

    db_path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(db_path)

    run = ledger.start_run("rt004-multi-asset-decision", "live-paper", 10_000.0, CostModel())
    run_id = run.run_id

    # Create PaperTrader to get engine
    trader = PaperTrader(AlwaysFlat(), ledger, run_id, cost_model=CostModel())
    eng = trader.engine

    # Manually set up multi-asset positions (BTCUSDT + ETHUSDT)
    marks = {"BTCUSDT": 100.0, "ETHUSDT": 2000.0}

    # Rebalance BTCUSDT
    eng.rebalance(0.5, 100.0, symbol="BTCUSDT", marks=marks)

    # Rebalance ETHUSDT
    eng.rebalance(0.3, 2000.0, symbol="ETHUSDT", marks=marks)

    # Record a decision with multi-asset state
    result = eng.rebalance(0.0, 100.0, symbol="BTCUSDT", marks=marks)  # no-op decision
    ledger.record_decision(
        run_id,
        candle_open_ms=1_000_000,
        candle_close_ms=1_059_999,
        decision_ts_ms=1_060_000,
        data_source="test",
        result=result,
        state=eng.state,
        mark_price=100.0,
    )

    # Capture expected multi-asset state
    expected_cash = eng.state.cash
    expected_funding = eng.state.funding_paid
    expected_realized = eng.state.realized_pnl
    expected_fees = eng.state.fees_paid
    expected_spread = eng.state.spread_paid
    expected_slippage = eng.state.slippage_paid
    expected_turnover = eng.state.turnover
    expected_trade_count = eng.state.trade_count
    expected_peak = eng.state.peak_equity
    expected_dd = eng.state.path_maximum_drawdown_pct
    expected_btc = {
        "qty": eng.state.positions["BTCUSDT"].qty,
        "avg": eng.state.positions["BTCUSDT"].avg_entry_price,
        "realized": eng.state.positions["BTCUSDT"].realized_pnl,
        "fees": eng.state.positions["BTCUSDT"].fees_paid,
        "spread": eng.state.positions["BTCUSDT"].spread_paid,
        "slippage": eng.state.positions["BTCUSDT"].slippage_paid,
        "funding": eng.state.positions["BTCUSDT"].funding_paid,
        "turnover": eng.state.positions["BTCUSDT"].turnover,
        "trades": eng.state.positions["BTCUSDT"].trade_count,
    }
    expected_eth = {
        "qty": eng.state.positions["ETHUSDT"].qty,
        "avg": eng.state.positions["ETHUSDT"].avg_entry_price,
        "realized": eng.state.positions["ETHUSDT"].realized_pnl,
        "fees": eng.state.positions["ETHUSDT"].fees_paid,
        "spread": eng.state.positions["ETHUSDT"].spread_paid,
        "slippage": eng.state.positions["ETHUSDT"].slippage_paid,
        "funding": eng.state.positions["ETHUSDT"].funding_paid,
        "turnover": eng.state.positions["ETHUSDT"].turnover,
        "trades": eng.state.positions["ETHUSDT"].trade_count,
    }

    # Close and reopen ledger
    ledger.close()
    reopened = Ledger(db_path)

    # Restore state
    restored = reopened.restore_state(run_id)
    assert restored is not None

    # Assert portfolio-level exact equality
    assert restored.cash == pytest.approx(expected_cash)
    assert restored.funding_paid == pytest.approx(expected_funding)
    assert restored.realized_pnl == pytest.approx(expected_realized)
    assert restored.fees_paid == pytest.approx(expected_fees)
    assert restored.spread_paid == pytest.approx(expected_spread)
    assert restored.slippage_paid == pytest.approx(expected_slippage)
    assert restored.turnover == pytest.approx(expected_turnover)
    assert restored.trade_count == expected_trade_count
    assert restored.peak_equity == pytest.approx(expected_peak)
    assert restored.path_maximum_drawdown_pct == pytest.approx(expected_dd)

    # Assert per-symbol exact equality for BTCUSDT
    assert "BTCUSDT" in restored.positions
    btc = restored.positions["BTCUSDT"]
    assert btc.qty == pytest.approx(expected_btc["qty"])
    assert btc.avg_entry_price == pytest.approx(expected_btc["avg"])
    assert btc.realized_pnl == pytest.approx(expected_btc["realized"])
    assert btc.fees_paid == pytest.approx(expected_btc["fees"])
    assert btc.spread_paid == pytest.approx(expected_btc["spread"])
    assert btc.slippage_paid == pytest.approx(expected_btc["slippage"])
    assert btc.funding_paid == pytest.approx(expected_btc["funding"])
    assert btc.turnover == pytest.approx(expected_btc["turnover"])
    assert btc.trade_count == expected_btc["trades"]

    # Assert per-symbol exact equality for ETHUSDT
    assert "ETHUSDT" in restored.positions
    eth = restored.positions["ETHUSDT"]
    assert eth.qty == pytest.approx(expected_eth["qty"])
    assert eth.avg_entry_price == pytest.approx(expected_eth["avg"])
    assert eth.realized_pnl == pytest.approx(expected_eth["realized"])
    assert eth.fees_paid == pytest.approx(expected_eth["fees"])
    assert eth.spread_paid == pytest.approx(expected_eth["spread"])
    assert eth.slippage_paid == pytest.approx(expected_eth["slippage"])
    assert eth.funding_paid == pytest.approx(expected_eth["funding"])
    assert eth.turnover == pytest.approx(expected_eth["turnover"])
    assert eth.trade_count == expected_eth["trades"]

    # Ensure no DEFAULT ghost position
    assert "DEFAULT" not in restored.positions


def test_closure_restart_multi_asset_exact_equality(tmp_path: Path) -> None:
    """RT004: multi-asset state persisted in closure, close/reopen/restore exact equality."""
    from obsidian_rl.portfolio.costs import CostModel
    from obsidian_rl.strategies.baselines import AlwaysFlat

    db_path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(db_path)

    run = ledger.start_run("rt004-multi-asset-closure", "live-paper", 10_000.0, CostModel())
    run_id = run.run_id

    trader = PaperTrader(AlwaysFlat(), ledger, run_id, cost_model=CostModel())
    eng = trader.engine

    marks = {"BTCUSDT": 100.0, "ETHUSDT": 2000.0}

    # Build multi-asset positions
    eng.rebalance(0.5, 100.0, symbol="BTCUSDT", marks=marks)
    eng.rebalance(0.3, 2000.0, symbol="ETHUSDT", marks=marks)

    # Record terminal closure
    result = eng.rebalance(0.0, 100.0, symbol="BTCUSDT", marks=marks)
    ledger.record_closure(
        run_id,
        terminal_ts_ms=2_000_000,
        mark_price=100.0,
        result=result,
        state=eng.state,
        closure_reason="close_session",
    )
    ledger.end_run(run_id)

    # Capture expected state AFTER closure (post-liquidation)
    expected_cash = eng.state.cash
    expected_funding = eng.state.funding_paid
    expected_realized = eng.state.realized_pnl
    expected_fees = eng.state.fees_paid
    expected_spread = eng.state.spread_paid
    expected_slippage = eng.state.slippage_paid
    expected_turnover = eng.state.turnover
    expected_trade_count = eng.state.trade_count
    expected_peak = eng.state.peak_equity
    expected_dd = eng.state.path_maximum_drawdown_pct
    expected_btc = {
        "qty": eng.state.positions["BTCUSDT"].qty,
        "avg": eng.state.positions["BTCUSDT"].avg_entry_price,
        "realized": eng.state.positions["BTCUSDT"].realized_pnl,
        "fees": eng.state.positions["BTCUSDT"].fees_paid,
        "spread": eng.state.positions["BTCUSDT"].spread_paid,
        "slippage": eng.state.positions["BTCUSDT"].slippage_paid,
        "funding": eng.state.positions["BTCUSDT"].funding_paid,
        "turnover": eng.state.positions["BTCUSDT"].turnover,
        "trades": eng.state.positions["BTCUSDT"].trade_count,
    }
    expected_eth = {
        "qty": eng.state.positions["ETHUSDT"].qty,
        "avg": eng.state.positions["ETHUSDT"].avg_entry_price,
        "realized": eng.state.positions["ETHUSDT"].realized_pnl,
        "fees": eng.state.positions["ETHUSDT"].fees_paid,
        "spread": eng.state.positions["ETHUSDT"].spread_paid,
        "slippage": eng.state.positions["ETHUSDT"].slippage_paid,
        "funding": eng.state.positions["ETHUSDT"].funding_paid,
        "turnover": eng.state.positions["ETHUSDT"].turnover,
        "trades": eng.state.positions["ETHUSDT"].trade_count,
    }

    # Close and reopen
    ledger.close()
    reopened = Ledger(db_path)

    # Restore from closure
    restored = reopened.restore_state(run_id)
    assert restored is not None

    # Assert portfolio-level exact equality
    assert restored.cash == pytest.approx(expected_cash)
    assert restored.funding_paid == pytest.approx(expected_funding)
    assert restored.realized_pnl == pytest.approx(expected_realized)
    assert restored.fees_paid == pytest.approx(expected_fees)
    assert restored.spread_paid == pytest.approx(expected_spread)
    assert restored.slippage_paid == pytest.approx(expected_slippage)
    assert restored.turnover == pytest.approx(expected_turnover)
    assert restored.trade_count == expected_trade_count
    assert restored.peak_equity == pytest.approx(expected_peak)
    assert restored.path_maximum_drawdown_pct == pytest.approx(expected_dd)

    # Assert per-symbol exact equality for BTCUSDT
    assert "BTCUSDT" in restored.positions
    btc = restored.positions["BTCUSDT"]
    assert btc.qty == pytest.approx(expected_btc["qty"])
    assert btc.avg_entry_price == pytest.approx(expected_btc["avg"])
    assert btc.realized_pnl == pytest.approx(expected_btc["realized"])
    assert btc.fees_paid == pytest.approx(expected_btc["fees"])
    assert btc.spread_paid == pytest.approx(expected_btc["spread"])
    assert btc.slippage_paid == pytest.approx(expected_btc["slippage"])
    assert btc.funding_paid == pytest.approx(expected_btc["funding"])
    assert btc.turnover == pytest.approx(expected_btc["turnover"])
    assert btc.trade_count == expected_btc["trades"]

    # Assert per-symbol exact equality for ETHUSDT
    assert "ETHUSDT" in restored.positions
    eth = restored.positions["ETHUSDT"]
    assert eth.qty == pytest.approx(expected_eth["qty"])
    assert eth.avg_entry_price == pytest.approx(expected_eth["avg"])
    assert eth.realized_pnl == pytest.approx(expected_eth["realized"])
    assert eth.fees_paid == pytest.approx(expected_eth["fees"])
    assert eth.spread_paid == pytest.approx(expected_eth["spread"])
    assert eth.slippage_paid == pytest.approx(expected_eth["slippage"])
    assert eth.funding_paid == pytest.approx(expected_eth["funding"])
    assert eth.turnover == pytest.approx(expected_eth["turnover"])
    assert eth.trade_count == expected_eth["trades"]

    # Ensure no DEFAULT ghost position
    assert "DEFAULT" not in restored.positions


def test_legacy_schema_no_multi_asset_restores_correctly(tmp_path: Path) -> None:
    """RT004: old schema/no multi-asset snapshot still restores correctly."""
    from obsidian_rl.portfolio.costs import CostModel

    db_path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(db_path)

    run = ledger.start_run("rt004-legacy", "live-paper", 10_000.0, CostModel())
    run_id = run.run_id

    # Manually insert a decision WITHOUT positions_json column (simulate old DB)
    # Note: current schema has positions_json column, so we must include it as NULL
    ledger._conn.execute(
        "INSERT INTO decisions (run_id, idempotency_key, candle_open_ms, candle_close_ms,"
        " decision_ts_ms, data_source, proposed_target, approved_target, executed_target,"
        " delta_qty, exec_price, traded_notional, fee, spread_cost, slippage_cost, funding,"
        " realized_pnl_delta, rejection_reason, position_qty, avg_entry_price, cash,"
        " unrealized_pnl, net_equity, gross_equity, realized_pnl_total, fees_total,"
        " spread_total, slippage_total, funding_total, turnover_total, trade_count,"
        " peak_equity, path_maximum_drawdown_pct, positions_json, created_at_ms)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            f"{run_id}:500000",
            500_000,
            559_999,
            560_000,
            "test",
            1.0,
            1.0,
            1.0,
            100.0,
            100.0,
            10_000.0,
            5.0,
            1.0,
            2.0,
            0.0,
            0.0,
            None,
            100.0,
            100.0,
            9992.0,
            0.0,
            9992.0,
            9997.0,
            0.0,
            5.0,
            1.0,
            2.0,
            0.0,
            10_000.0,
            1,
            10_000.0,
            0.0,
            None,  # positions_json = NULL for legacy compatibility
            1_000_000,
        ),
    )
    ledger._conn.commit()

    # Restore should work and produce correct single-asset state
    restored = ledger.restore_state(run_id)
    assert restored is not None
    assert restored.cash == pytest.approx(9992.0)
    assert restored.qty == pytest.approx(100.0)
    assert restored.avg_entry_price == pytest.approx(100.0)
    assert restored.realized_pnl == pytest.approx(0.0)
    assert restored.fees_paid == pytest.approx(5.0)
    assert restored.spread_paid == pytest.approx(1.0)
    assert restored.slippage_paid == pytest.approx(2.0)
    assert restored.funding_paid == pytest.approx(0.0)
    assert restored.turnover == pytest.approx(10_000.0)
    assert restored.trade_count == 1
    assert restored.peak_equity == pytest.approx(10_000.0)
    assert restored.path_maximum_drawdown_pct == pytest.approx(0.0)

    # But DEFAULT may exist as legacy single-asset - check it's not in positions dict
    # since we excluded DEFAULT from serialization
    assert "DEFAULT" not in restored.positions


def test_malformed_nonfinite_snapshot_fails_closed(tmp_path: Path) -> None:
    """RT004: malformed/non-finite snapshot fails closed."""
    from obsidian_rl.portfolio.costs import CostModel

    db_path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(db_path)

    run = ledger.start_run("rt004-malformed", "live-paper", 10_000.0, CostModel())
    run_id = run.run_id

    # Test 1: non-finite qty in positions_json
    ledger._conn.execute(
        "INSERT INTO decisions (run_id, idempotency_key, candle_open_ms, candle_close_ms,"
        " decision_ts_ms, data_source, proposed_target, approved_target, executed_target,"
        " delta_qty, exec_price, traded_notional, fee, spread_cost, slippage_cost, funding,"
        " realized_pnl_delta, rejection_reason, position_qty, avg_entry_price, cash,"
        " unrealized_pnl, net_equity, gross_equity, realized_pnl_total, fees_total,"
        " spread_total, slippage_total, funding_total, turnover_total, trade_count,"
        " peak_equity, path_maximum_drawdown_pct, positions_json, created_at_ms)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            f"{run_id}:1000000",
            1_000_000,
            1_059_999,
            1_060_000,
            "test",
            1.0,
            1.0,
            1.0,
            100.0,
            100.0,
            10_000.0,
            5.0,
            1.0,
            2.0,
            0.0,
            0.0,
            None,
            100.0,
            100.0,
            9992.0,
            0.0,
            9992.0,
            9997.0,
            0.0,
            5.0,
            1.0,
            2.0,
            0.0,
            10_000.0,
            1,
            10_000.0,
            0.0,
            (
                '{"BTCUSDT": {"qty": NaN, "avg_entry_price": 100.0, "realized_pnl": 0.0, "fees_paid": 0.0, "spread_paid": 0.0, "slippage_paid": 0.0, "funding_paid": 0.0, "turnover": 0.0, "trade_count": 0}}'  # noqa: E501
            ),
            1_000_000,
        ),
    )
    ledger._conn.commit()

    with pytest.raises(ValueError, match="non-finite qty in positions_json for BTCUSDT"):
        ledger.restore_state(run_id)

    # Test 2: malformed JSON
    ledger._conn.execute(
        "INSERT INTO decisions (run_id, idempotency_key, candle_open_ms, candle_close_ms,"
        " decision_ts_ms, data_source, proposed_target, approved_target, executed_target,"
        " delta_qty, exec_price, traded_notional, fee, spread_cost, slippage_cost, funding,"
        " realized_pnl_delta, rejection_reason, position_qty, avg_entry_price, cash,"
        " unrealized_pnl, net_equity, gross_equity, realized_pnl_total, fees_total,"
        " spread_total, slippage_total, funding_total, turnover_total, trade_count,"
        " peak_equity, path_maximum_drawdown_pct, positions_json, created_at_ms)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            f"{run_id}:2000000",
            2_000_000,
            2_059_999,
            2_060_000,
            "test",
            1.0,
            1.0,
            1.0,
            100.0,
            100.0,
            10_000.0,
            5.0,
            1.0,
            2.0,
            0.0,
            0.0,
            None,
            100.0,
            100.0,
            9992.0,
            0.0,
            9992.0,
            9997.0,
            0.0,
            5.0,
            1.0,
            2.0,
            0.0,
            10_000.0,
            1,
            10_000.0,
            0.0,
            "{invalid json}",
            1_000_000,
        ),
    )
    ledger._conn.commit()

    with pytest.raises(RuntimeError, match="malformed positions_json in decision"):
        ledger.restore_state(run_id)

    # Test 3: invalid trade_count
    ledger._conn.execute(
        "INSERT INTO decisions (run_id, idempotency_key, candle_open_ms, candle_close_ms,"
        " decision_ts_ms, data_source, proposed_target, approved_target, executed_target,"
        " delta_qty, exec_price, traded_notional, fee, spread_cost, slippage_cost, funding,"
        " realized_pnl_delta, rejection_reason, position_qty, avg_entry_price, cash,"
        " unrealized_pnl, net_equity, gross_equity, realized_pnl_total, fees_total,"
        " spread_total, slippage_total, funding_total, turnover_total, trade_count,"
        " peak_equity, path_maximum_drawdown_pct, positions_json, created_at_ms)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            f"{run_id}:3000000",
            3_000_000,
            3_059_999,
            3_060_000,
            "test",
            1.0,
            1.0,
            1.0,
            100.0,
            100.0,
            10_000.0,
            5.0,
            1.0,
            2.0,
            0.0,
            0.0,
            None,
            100.0,
            100.0,
            9992.0,
            0.0,
            9992.0,
            9997.0,
            0.0,
            5.0,
            1.0,
            2.0,
            0.0,
            10_000.0,
            1,
            10_000.0,
            0.0,
            (
                '{"BTCUSDT": {"qty": 1.0, "avg_entry_price": 100.0, "realized_pnl": 0.0, "fees_paid": 0.0, "spread_paid": 0.0, "slippage_paid": 0.0, "funding_paid": 0.0, "turnover": 0.0, "trade_count": -1}}'  # noqa: E501
            ),
            1_000_000,
        ),
    )
    ledger._conn.commit()

    with pytest.raises(ValueError, match="invalid trade_count in positions_json for BTCUSDT"):
        ledger.restore_state(run_id)

    # Test 4: non-finite avg_entry_price
    ledger._conn.execute(
        "INSERT INTO decisions (run_id, idempotency_key, candle_open_ms, candle_close_ms,"
        " decision_ts_ms, data_source, proposed_target, approved_target, executed_target,"
        " delta_qty, exec_price, traded_notional, fee, spread_cost, slippage_cost, funding,"
        " realized_pnl_delta, rejection_reason, position_qty, avg_entry_price, cash,"
        " unrealized_pnl, net_equity, gross_equity, realized_pnl_total, fees_total,"
        " spread_total, slippage_total, funding_total, turnover_total, trade_count,"
        " peak_equity, path_maximum_drawdown_pct, positions_json, created_at_ms)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            f"{run_id}:4000000",
            4_000_000,
            4_059_999,
            4_060_000,
            "test",
            1.0,
            1.0,
            1.0,
            100.0,
            100.0,
            10_000.0,
            5.0,
            1.0,
            2.0,
            0.0,
            0.0,
            None,
            100.0,
            100.0,
            9992.0,
            0.0,
            9992.0,
            9997.0,
            0.0,
            5.0,
            1.0,
            2.0,
            0.0,
            10_000.0,
            1,
            10_000.0,
            0.0,
            (
                '{"BTCUSDT": {"qty": 1.0, "avg_entry_price": Infinity, "realized_pnl": 0.0, "fees_paid": 0.0, "spread_paid": 0.0, "slippage_paid": 0.0, "funding_paid": 0.0, "turnover": 0.0, "trade_count": 0}}'  # noqa: E501
            ),
            1_000_000,
        ),
    )
    ledger._conn.commit()

    with pytest.raises(
        ValueError, match="non-finite avg_entry_price in positions_json for BTCUSDT"
    ):
        ledger.restore_state(run_id)
