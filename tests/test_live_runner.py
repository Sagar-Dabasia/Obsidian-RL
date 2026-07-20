"""Live paper runner tests: closed run verification and safeguard against processing ended runs."""

from pathlib import Path

import pytest

from obsidian_rl.config import Settings
from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.live.runner import LivePaperRunner
from obsidian_rl.live.stream import KlineEvent
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine
from obsidian_rl.strategies.baselines import ThresholdMomentum

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)


def test_runner_refuses_closed_run(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(settings.ledger_path)
    run = ledger.start_run("threshold-momentum", "live-paper", 10_000.0, {})
    eng = PortfolioEngine(PortfolioConfig(), CM)
    res = eng.liquidate(100.0)
    ledger.finalize_run(
        run.run_id,
        terminal_ts_ms=100_000,
        mark_price=100.0,
        result=res,
        state=eng.state,
    )
    ledger.close()

    strategy = ThresholdMomentum()
    with pytest.raises(ValueError, match="is already closed and cannot be resumed"):
        LivePaperRunner(settings, strategy, run_id=run.run_id)


def test_runner_refuses_inconsistent_run(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(settings.ledger_path)
    run = ledger.start_run("threshold-momentum", "live-paper", 10_000.0, {})
    eng = PortfolioEngine(PortfolioConfig(), CM)
    res = eng.liquidate(100.0)
    ledger.record_closure(
        run.run_id,
        terminal_ts_ms=100_000,
        mark_price=100.0,
        result=res,
        state=eng.state,
    )
    ledger.close()

    strategy = ThresholdMomentum()
    with pytest.raises(RuntimeError, match="inconsistent closure/ended state"):
        LivePaperRunner(settings, strategy, run_id=run.run_id)


def test_runner_backfill_and_handle_event_on_closed_run(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    strategy = ThresholdMomentum()
    runner = LivePaperRunner(settings, strategy)

    # Close the run right after starting
    runner.trader.close_session(100.0)

    with pytest.raises(ValueError, match="is already closed and cannot be resumed"):
        runner.backfill()

    event = KlineEvent(
        open_time=200_000,
        close_time=899_999,
        is_closed=True,
        open=100.0,
        high=105.0,
        low=95.0,
        close=101.0,
        volume=10.0,
        quote_volume=1000.0,
        trades=5,
        taker_buy_volume=5.0,
        taker_buy_quote_volume=500.0,
    )
    with pytest.raises(ValueError, match="is already closed and cannot be resumed"):
        runner.handle_event(event)
