"""Dashboard query-layer tests: session separation, KPIs, warnings, reversal handling."""

from pathlib import Path

import pytest

from obsidian_rl.dashboard.queries import (
    closed_trade_events,
    equity_and_drawdown,
    kpis,
    list_run_summaries,
    run_frame,
    warnings_for_run,
)
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.live.paper_trader import PaperTrader, replay_candles
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.baselines import ThresholdMomentum
from tests.conftest import make_candles

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)


@pytest.fixture()
def populated_ledger(tmp_path: Path) -> tuple[Path, str, str]:
    path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(path)
    candles = make_candles(WARMUP_ROWS + 120, seed=5)
    run_ids = []
    for _ in range(2):  # two independent sessions of the same strategy
        run = ledger.start_run("threshold-momentum", "replay", 10_000.0, {})
        trader = PaperTrader(ThresholdMomentum(0.002), ledger, run.run_id, cost_model=CM)
        replay_candles(trader, candles)
        ledger.end_run(run.run_id)
        run_ids.append(run.run_id)
    ledger.close()
    return path, run_ids[0], run_ids[1]


def test_sessions_never_merged(populated_ledger: tuple[Path, str, str]) -> None:
    path, run_a, run_b = populated_ledger
    runs = list_run_summaries(path)
    assert len(runs) == 2
    frame_a = run_frame(path, run_a)
    frame_b = run_frame(path, run_b)
    assert set(frame_a["run_id"].unique()) == {run_a}
    assert set(frame_b["run_id"].unique()) == {run_b}
    assert len(frame_a) == len(frame_b)  # identical replay, separate sessions


def test_kpis_and_equity_curve(populated_ledger: tuple[Path, str, str]) -> None:
    path, run_a, _ = populated_ledger
    frame = run_frame(path, run_a)
    k = kpis(frame, 10_000.0)
    assert k["net_equity"] == pytest.approx(float(frame["net_equity"].iloc[-1]))
    assert k["trade_count"] >= 1
    curves = equity_and_drawdown(frame)
    assert (curves["drawdown"] >= 0).all()
    assert curves["drawdown"].iloc[0] == pytest.approx(0.0)


def test_reversals_produce_realized_events_without_flat(
    populated_ledger: tuple[Path, str, str],
) -> None:
    path, run_a, _ = populated_ledger
    frame = run_frame(path, run_a)
    events = closed_trade_events(frame)
    # every event corresponds to a realized P&L delta, independent of flat transitions
    assert (events["realized_pnl_delta"] != 0).all()
    reversal_rows = frame[(frame["realized_pnl_delta"] != 0) & (frame["position_qty"].abs() > 1e-9)]
    # at least one direct reversal happened in this fixture (long<->short without flat)
    assert len(reversal_rows) > 0


def test_warnings(populated_ledger: tuple[Path, str, str]) -> None:
    path, run_a, _ = populated_ledger
    frame = run_frame(path, run_a)
    last_candle = int(frame["candle_open_ms"].iloc[-1])
    # fresh (just after last candle): no staleness warning
    fresh = warnings_for_run(frame, now_ms=last_candle + 900_000 + 1000)
    assert not any("stale" in w for w in fresh)
    # hours later on a live run: stale warning
    stale = warnings_for_run(frame, now_ms=last_candle + 20 * 900_000)
    assert any("stale" in w for w in stale)
    # ended runs never warn about staleness
    ended = warnings_for_run(frame, now_ms=last_candle + 20 * 900_000, run_ended=True)
    assert not any("stale" in w for w in ended)
    assert warnings_for_run(frame.iloc[0:0]) == ["no decisions recorded yet"]
