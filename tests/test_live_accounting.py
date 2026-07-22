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
