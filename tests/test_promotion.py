"""Champion/challenger promotion tests: gates, explicit promotion, rollback."""

from pathlib import Path

import pytest

from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.training.ppo import PpoHyperparams, TrainConfig, train_ppo
from obsidian_rl.training.promotion import (
    PromotionThresholds,
    current_champion,
    evaluate_candidate,
    promote,
    rollback,
)
from obsidian_rl.training.registry import load_record
from tests.conftest import make_candles

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)
CFG = TrainConfig(
    total_timesteps=192,
    n_envs=1,
    seed=1,
    device="cpu",
    episode_length=32,
    checkpoint_freq=96,
    eval_freq=96,
    hyperparams=PpoHyperparams(n_steps=48, batch_size=24, net_arch=(8, 8)),
    costs=CM,
)


@pytest.fixture(scope="module")
def models_with_two_candidates(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    models_dir = tmp_path_factory.mktemp("models")
    train = make_candles(350, seed=1)
    evalc = make_candles(250, seed=2, start_ms=int(train["open_time"].iloc[-1]) + 900_000)
    a = train_ppo(train, evalc, CFG, models_dir, model_id="cand-a")
    b = train_ppo(train, evalc, CFG, models_dir, model_id="cand-b")
    return models_dir, a.record.model_id, b.record.model_id


def test_promote_and_retire(models_with_two_candidates: tuple[Path, str, str]) -> None:
    models_dir, a, b = models_with_two_candidates
    assert current_champion(models_dir) is None
    promote(models_dir, a)
    assert current_champion(models_dir) == a
    assert load_record(models_dir / a).metadata["promotion"] == "champion"
    promote(models_dir, b)
    assert current_champion(models_dir) == b
    assert load_record(models_dir / a).metadata["promotion"] == "retired"

    restored = rollback(models_dir)
    assert restored == a
    assert current_champion(models_dir) == a
    assert load_record(models_dir / a).metadata["promotion"] == "champion"
    assert load_record(models_dir / b).metadata["promotion"] == "retired"


def test_multi_step_rollback_walks_strictly_back(
    models_with_two_candidates: tuple[Path, str, str],
) -> None:
    """Regression (review): a second rollback must walk further back (C->B->A), never
    reinstate the just-abandoned champion."""
    models_dir, a, b = models_with_two_candidates
    (models_dir / "CHAMPION.json").unlink(missing_ok=True)  # fresh lineage for this test
    train = make_candles(350, seed=1)
    evalc = make_candles(250, seed=2, start_ms=int(train["open_time"].iloc[-1]) + 900_000)
    c = train_ppo(train, evalc, CFG, models_dir, model_id="cand-c").record.model_id

    promote(models_dir, a)
    promote(models_dir, b)
    promote(models_dir, c)
    assert current_champion(models_dir) == c

    assert rollback(models_dir) == b
    assert current_champion(models_dir) == b
    assert rollback(models_dir) == a  # must reach A, NOT bounce back to C
    assert current_champion(models_dir) == a
    assert load_record(models_dir / c).metadata["promotion"] == "retired"

    with pytest.raises(RuntimeError, match="no previous champion"):
        rollback(models_dir)  # nothing before A


def test_candidate_evaluation_gates(models_with_two_candidates: tuple[Path, str, str]) -> None:
    models_dir, a, _ = models_with_two_candidates
    val = make_candles(WARMUP_ROWS + 200, seed=9)
    report = evaluate_candidate(models_dir, a, val, cost_model=CM)
    assert "candidate" in report["metrics"]
    assert "always-flat" in report["metrics"]
    # an impossible threshold must fail the candidate
    strict = evaluate_candidate(
        models_dir,
        a,
        val,
        cost_model=CM,
        thresholds=PromotionThresholds(max_drawdown_limit=-1.0),
    )
    assert strict["passes"] is False and strict["failures"]


def test_unknown_candidate_rejected(models_with_two_candidates: tuple[Path, str, str]) -> None:
    models_dir, _, _ = models_with_two_candidates
    val = make_candles(WARMUP_ROWS + 150, seed=3)
    with pytest.raises(Exception, match="refusing to load|No such|not found|missing"):
        evaluate_candidate(models_dir, "nonexistent-model", val, cost_model=CM)
