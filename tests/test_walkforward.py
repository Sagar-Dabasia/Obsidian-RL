"""Walk-forward evaluator tests: fold chronology, purge gaps, holdout isolation,
identical evaluation conditions, delay sensitivity."""

import pandas as pd
import pytest

from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.evaluation.backtest import run_backtest
from obsidian_rl.evaluation.walkforward import (
    DAY_MS,
    evaluate_strategies_on_slice,
    make_folds,
    slice_candles,
    summarize,
)
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.baselines import AlwaysFlat, BuyAndHold, ThresholdMomentum
from tests.conftest import make_candles

MS15 = interval_to_ms("15m")
CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)


def test_folds_are_chronological_with_purge_gap() -> None:
    data_start = 0
    holdout = 1_000 * DAY_MS
    folds = make_folds(
        data_start, holdout, train_days=300, val_days=100, step_days=100, purge_candles=96
    )
    assert len(folds) >= 3
    for f in folds:
        assert f.train_start_ms < f.train_end_ms < f.val_start_ms < f.val_end_ms
        assert f.val_start_ms - f.train_end_ms - 1 == 96 * MS15  # purge gap
        assert f.val_end_ms < holdout  # holdout untouched
    starts = [f.train_start_ms for f in folds]
    assert starts == sorted(starts)


def test_no_folds_raises() -> None:
    with pytest.raises(ValueError, match="no folds"):
        make_folds(0, 10 * DAY_MS, train_days=300, val_days=100, step_days=100)


def test_identical_conditions_across_strategies() -> None:
    candles = make_candles(WARMUP_ROWS + 300)
    rows = evaluate_strategies_on_slice(
        candles,
        [("flat", AlwaysFlat(), None), ("bh", BuyAndHold(), None)],
        fold_id=0,
        cost_model=CM,
        sensitivity=True,
    )
    # 2 strategies x 3 scenarios
    assert len(rows) == 6
    scenarios = {r.scenario for r in rows}
    assert scenarios == {"base", "costs2x", "delay1"}
    # identical regime descriptor => identical evaluation slice
    assert len({r.val_buy_hold_return for r in rows}) == 1
    # doubled costs must not improve buy&hold
    bh = {r.scenario: r.metrics.net_return for r in rows if r.strategy_id == "bh"}
    assert bh["costs2x"] <= bh["base"] + 1e-12


def test_signal_delay_changes_decisions() -> None:
    candles = make_candles(WARMUP_ROWS + 400, seed=5)
    base = run_backtest(candles, ThresholdMomentum(0.002), cost_model=CM, signal_delay=0)
    delayed = run_backtest(candles, ThresholdMomentum(0.002), cost_model=CM, signal_delay=1)
    assert base.n_decisions == delayed.n_decisions + 1  # one fewer decidable candle
    # equity paths must differ if the signal ever changed between adjacent candles
    assert (
        not base.equity_curve["equity"].iloc[-50:].equals(delayed.equity_curve["equity"].iloc[-50:])
    )


def test_slice_and_summarize() -> None:
    candles = make_candles(WARMUP_ROWS + 300)
    lo = int(candles["open_time"].iloc[10])
    hi = int(candles["open_time"].iloc[100])
    piece = slice_candles(candles, lo, hi)
    assert len(piece) == 91
    rows = evaluate_strategies_on_slice(
        candles,
        [("flat", AlwaysFlat(), None), ("bh", BuyAndHold(), None)],
        fold_id=0,
        cost_model=CM,
        sensitivity=False,
    )
    table = summarize(rows)
    assert set(table.index) == {"flat", "bh"}
    assert table.loc["flat", "mean_net_return"] == pytest.approx(0.0)
    assert isinstance(table, pd.DataFrame)
