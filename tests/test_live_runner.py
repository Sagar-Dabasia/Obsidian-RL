"""Live paper runner tests: closed run verification and safeguard against processing ended runs."""

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
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
        event_time_ms=899_999,
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


def test_handle_event_gap_recovery_and_expiration(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", ledger_path=tmp_path / "ledger.sqlite3")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    strategy = ThresholdMomentum()
    runner = LivePaperRunner(settings, strategy)

    # Set last finalized ms to 900_000 (15m aligned)
    runner.trader.last_finalized_ms = 900_000
    # Mock rest client returning missing candle 1_800_000
    missing_df = pd.DataFrame(
        [
            {
                "open_time": 1_800_000,
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 101.0,
                "volume": 10.0,
                "close_time": 2_699_999,
                "quote_volume": 1000.0,
                "trades": 5,
                "taker_buy_volume": 5.0,
                "taker_buy_quote_volume": 500.0,
            }
        ]
    )
    mock_rest = MagicMock()
    mock_rest.fetch_klines.return_value = missing_df
    runner.rest = mock_rest

    # Send event for candle 2_700_000 (gap detected because 2_700_000 > 900_000 + 900_000)
    event = KlineEvent(
        event_time_ms=2_700_050,
        open_time=2_700_000,
        close_time=3_599_999,
        is_closed=False,
        open=101.0,
        high=102.0,
        low=100.0,
        close=101.5,
        volume=1.0,
        quote_volume=101.5,
        trades=1,
        taker_buy_volume=0.5,
        taker_buy_quote_volume=50.75,
    )
    runner.handle_event(event)

    # Verify backfill triggered and events recorded
    mock_rest.fetch_klines.assert_called_once()
    assert runner.trader.last_finalized_ms == 1_800_000
    events = runner.ledger.get_events(runner.run_id)
    event_types = {row["event_type"] for row in events}
    assert "market_data_gap" in event_types
    assert "backfill_observation_completed" in event_types
