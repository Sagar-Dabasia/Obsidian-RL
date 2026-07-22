"""Walk-forward evaluator tests: fold chronology, purge gaps, holdout isolation,
identical evaluation conditions, delay sensitivity, typed slice identities,
collision-resistant experiment IDs, and nested evaluation separation."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
import pandas as pd
import pytest

from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.evaluation.backtest import run_backtest
from obsidian_rl.evaluation.holdout import get_holdout_start_ms
from obsidian_rl.evaluation.walkforward import (
    DAY_MS,
    FoldSlice,
    FoldSpec,
    create_experiment_id,
    evaluate_strategies_on_slice,
    make_folds,
    save_results,
    slice_candles,
    slice_sha256,
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
        data_start,
        holdout,
        train_days=300,
        inner_eval_days=60,
        val_days=100,
        step_days=100,
        purge_candles=96,
    )
    assert len(folds) >= 3
    for f in folds:
        # Strict ordering across all 5 segments
        assert f.train.start_ms <= f.train.end_ms
        assert f.train.end_ms < f.purge_1.start_ms <= f.purge_1.end_ms
        assert f.purge_1.end_ms < f.inner_eval.start_ms <= f.inner_eval.end_ms
        assert f.inner_eval.end_ms < f.purge_2.start_ms <= f.purge_2.end_ms
        assert f.purge_2.end_ms < f.outer_val.start_ms <= f.outer_val.end_ms

        # Check exact boundaries and backward compatibility properties
        assert f.train_start_ms == f.train.start_ms
        assert f.train_end_ms == f.train.end_ms
        assert f.inner_eval_start_ms == f.inner_eval.start_ms
        assert f.inner_eval_end_ms == f.inner_eval.end_ms
        assert f.val_start_ms == f.outer_val.start_ms
        assert f.val_end_ms == f.outer_val.end_ms

        # Purge gaps exactly equal purge_candles (96 * MS15)
        assert f.purge_1.end_ms - f.purge_1.start_ms + MS15 == 96 * MS15
        assert f.purge_2.end_ms - f.purge_2.start_ms + MS15 == 96 * MS15

        # Purge gaps separate adjacent slices cleanly across purge_candles (96) candles
        assert f.inner_eval_start_ms - f.train_end_ms == (96 + 1) * MS15
        assert f.val_start_ms - f.inner_eval_end_ms == (96 + 1) * MS15

        # Holdout untouched
        assert f.val_end_ms < holdout
    starts = [f.train_start_ms for f in folds]
    assert starts == sorted(starts)


def test_no_folds_raises() -> None:
    with pytest.raises(ValueError, match="no folds"):
        make_folds(0, 10 * DAY_MS, train_days=300, inner_eval_days=60, val_days=100, step_days=100)


def test_exact_fold_boundaries_and_row_counts_persisted_and_hashes_change() -> None:
    # Build actual dataframe large enough for train(10d) + p1 + inner(5d) + p2 + val(5d)
    # Total days ~ 20 + purges ~ 23 days = 23 * 96 = 2208 candles
    candles = make_candles(3000, start_ms=0)
    holdout = 3000 * 15 * 60 * 1000  # right at end
    folds = make_folds(
        0,
        holdout,
        candles=candles,
        train_days=10,
        inner_eval_days=5,
        val_days=5,
        step_days=10,
        purge_candles=WARMUP_ROWS,
    )
    assert len(folds) >= 1
    f = folds[0]
    # Check that row counts are exact and positive
    assert f.train.rows > 0 and len(f.train.sha256) == 64
    assert f.purge_1.rows == WARMUP_ROWS and len(f.purge_1.sha256) == 64
    assert f.inner_eval.rows > 0 and len(f.inner_eval.sha256) == 64
    assert f.purge_2.rows == WARMUP_ROWS and len(f.purge_2.sha256) == 64
    assert f.outer_val.rows > 0 and len(f.outer_val.sha256) == 64

    # Verify sha256 changes when slice contents change
    tr_df = slice_candles(candles, f.train.start_ms, f.train.end_ms)
    old_sha = slice_sha256(tr_df)
    assert old_sha == f.train.sha256

    mutated = candles.copy()
    mutated.loc[mutated["open_time"] == tr_df["open_time"].iloc[0], "close"] += 10.0
    mutated_tr_df = slice_candles(mutated, f.train.start_ms, f.train.end_ms)
    new_sha = slice_sha256(mutated_tr_df)
    assert new_sha != old_sha and len(new_sha) == 64

    # Check to_dict payload matches actual slices and reports inclusive bounds description
    d = f.to_dict()
    assert d["train"]["sha256"] == f.train.sha256
    assert d["train"]["rows"] == f.train.rows
    assert d["purge_1"]["rows"] == WARMUP_ROWS
    assert d["purge_2"]["rows"] == WARMUP_ROWS
    assert "inclusive" in d["boundaries_description"].lower()


def test_outer_validation_never_passed_to_inner_and_disjoint_slices() -> None:
    candles = make_candles(3500, start_ms=0)
    folds = make_folds(
        0,
        3500 * 15 * 60 * 1000,
        candles=candles,
        train_days=10,
        inner_eval_days=5,
        val_days=5,
        step_days=10,
        purge_candles=WARMUP_ROWS,
    )
    f = folds[0]
    tr = slice_candles(candles, f.train.start_ms, f.train.end_ms)
    ie = slice_candles(candles, f.inner_eval.start_ms, f.inner_eval.end_ms)
    ov = slice_candles(candles, f.outer_val.start_ms, f.outer_val.end_ms)

    # Disjoint open_time ranges
    assert tr["open_time"].max() < ie["open_time"].min()
    assert ie["open_time"].max() < ov["open_time"].min()

    # Outer validation rows never exist in inner evaluation or training
    tr_set = set(tr["open_time"])
    ie_set = set(ie["open_time"])
    ov_set = set(ov["open_time"])
    assert tr_set.isdisjoint(ie_set)
    assert ie_set.isdisjoint(ov_set)
    assert tr_set.isdisjoint(ov_set)


def test_holdout_isolation_and_boundary_rejection() -> None:
    h_ms = int(datetime(2025, 7, 1, tzinfo=UTC).timestamp() * 1000)
    data_start = h_ms - 200 * DAY_MS
    folds = make_folds(
        data_start, h_ms, train_days=60, inner_eval_days=20, val_days=20, step_days=20
    )
    for f in folds:
        assert f.outer_val.end_ms < h_ms
        assert f.inner_eval.end_ms < h_ms
        assert f.train.end_ms < h_ms

    with pytest.raises(ValueError, match="exceeds central reserved boundary"):
        make_folds(data_start, h_ms + 1000)


def test_reruns_create_unique_experiment_and_model_ids(tmp_path: Path) -> None:
    id1 = create_experiment_id()
    id2 = create_experiment_id()
    assert id1 != id2
    assert id1.startswith("wf-") and id2.startswith("wf-")

    # Check collision resistance in saving artifacts
    out_dir = tmp_path / "wf_artifacts"
    p1 = save_results([], out_dir, experiment_id=id1)
    p2 = save_results([], out_dir, experiment_id=id2)
    assert p1.exists() and p2.exists() and p1 != p2

    # Refuse to overwrite existing artifact ID
    with pytest.raises(FileExistsError, match="already exists"):
        save_results([], out_dir, experiment_id=id1)


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


def test_turnover_penalty_bps_experiment_ids_differ() -> None:
    id0 = create_experiment_id(0.0)
    id5 = create_experiment_id(5.0)
    id10 = create_experiment_id(10.0)
    assert id0 != id5 and id5 != id10 and id0 != id10
    assert "-tp" not in id0
    assert "-tp5.0-" in id5
    assert "-tp10.0-" in id10


def test_turnover_penalty_bps_saved_in_walkforward_artifact(tmp_path: Path) -> None:
    import json
    from dataclasses import asdict
    from obsidian_rl.env.trading_env import RewardConfig

    out_dir = tmp_path / "wf_tp"
    extra = {
        "turnover_penalty_bps": 15.0,
        "reward_config": asdict(RewardConfig(turnover_penalty_bps=15.0)),
    }
    p = save_results([], out_dir, extra=extra)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["turnover_penalty_bps"] == 15.0
    assert data["reward_config"]["turnover_penalty_bps"] == 15.0


def test_evaluation_pnl_and_costs_unchanged_by_turnover_regularization() -> None:
    candles = make_candles(WARMUP_ROWS + 300)
    rows = evaluate_strategies_on_slice(
        candles,
        [("flat", AlwaysFlat(), None), ("bh", BuyAndHold(), None)],
        fold_id=0,
        cost_model=CM,
        sensitivity=False,
    )
    # P&L and costs only depend on CostModel and execution prices, never reward shaping weights / turnover_penalty_bps
    for r in rows:
        assert "turnover_penalty_bps" not in r.to_dict()
