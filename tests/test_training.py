"""PPO training pipeline tests: CPU smoke training, save/load, compatibility gates,
deterministic inference, GPU detection. All tiny and CPU-only."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from obsidian_rl.env.trading_env import TradingEnv
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.training.device import detect_device
from obsidian_rl.training.ppo import PpoHyperparams, TrainConfig, load_policy, train_ppo
from obsidian_rl.training.registry import (
    METADATA_FILE,
    MODEL_FILE,
    ModelCompatibilityError,
    load_record,
    set_promotion,
)
from tests.conftest import make_candles

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)

SMOKE_CFG = TrainConfig(
    total_timesteps=256,
    n_envs=1,
    seed=7,
    device="cpu",
    episode_length=32,
    checkpoint_freq=128,
    eval_freq=128,
    hyperparams=PpoHyperparams(n_steps=64, batch_size=32, net_arch=(16, 16)),
    costs=CM,
)


from typing import Iterator


@pytest.fixture(scope="module", autouse=True)
def _mock_clean_git_state_module() -> Iterator[None]:
    from unittest.mock import patch
    from obsidian_rl.training.registry import GitSourceState, get_git_source_state as real_get_git_source_state

    clean_state = GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[])

    def fake_get_git_source_state(path: Path | None = None) -> GitSourceState:
        if path is not None:
            return real_get_git_source_state(path)
        return clean_state

    with (
        patch("obsidian_rl.training.registry.get_git_source_state", fake_get_git_source_state),
        patch("obsidian_rl.training.promotion.get_git_source_state", fake_get_git_source_state),
    ):
        yield


@pytest.fixture(scope="module")
def trained_model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    models_dir = tmp_path_factory.mktemp("models")
    train_candles = make_candles(400, seed=3)
    eval_candles = make_candles(
        250, seed=4, start_ms=int(train_candles["open_time"].iloc[-1]) + 900_000
    )
    result = train_ppo(train_candles, eval_candles, SMOKE_CFG, models_dir)
    return result.record.model_dir


def test_gpu_detection_report() -> None:
    report = detect_device("auto")
    assert report.torch_version
    assert report.selected_device in ("cpu", "cuda")
    if report.cuda_available:
        assert report.device_name and report.total_vram_mb
    cpu = detect_device("cpu")
    assert cpu.selected_device == "cpu"


def test_smoke_training_produces_valid_registry_entry(trained_model_dir: Path) -> None:
    record = load_record(trained_model_dir)
    assert record.metadata["algorithm"] == "ppo-mlp-discrete5"
    assert record.metadata["feature_schema"]["version"] == "fs-v1"
    assert record.metadata["data"]["eval_start_ms"] > record.metadata["data"]["train_end_ms"]
    assert record.metadata["promotion"] == "candidate"
    assert (trained_model_dir / MODEL_FILE).exists()
    assert (trained_model_dir / "final_model.zip").exists()
    assert (trained_model_dir / MODEL_FILE).read_bytes() == (
        trained_model_dir / "best" / "best_model.zip"
    ).read_bytes()
    assert record.metadata["metrics"]["best_validation_timestep"] is not None
    assert (
        record.metadata["metrics"]["best_validation_mean_reward"]
        == record.metadata["metrics"]["eval_mean_reward"]
    )


def test_training_requires_a_best_validation_checkpoint(tmp_path: Path) -> None:
    train_candles = make_candles(160, seed=13)
    eval_candles = make_candles(
        120, seed=14, start_ms=int(train_candles["open_time"].iloc[-1]) + 900_000
    )
    no_eval_cfg = replace(SMOKE_CFG, total_timesteps=64, eval_freq=10_000)
    model_id = "no-best-checkpoint"

    with pytest.raises(RuntimeError, match="did not create a valid best validation checkpoint"):
        train_ppo(train_candles, eval_candles, no_eval_cfg, tmp_path, model_id=model_id)

    assert (tmp_path / model_id / "final_model.zip").exists()
    assert not (tmp_path / model_id / MODEL_FILE).exists()


def test_deterministic_inference(trained_model_dir: Path) -> None:
    model = load_policy(trained_model_dir, device="cpu")
    candles = make_candles(300, seed=9)
    env = TradingEnv(candles, cost_model=CM, episode_length=20, random_start=False)
    obs, _ = env.reset(seed=0)
    a1, _ = model.predict(obs, deterministic=True)
    a2, _ = model.predict(obs, deterministic=True)
    assert int(a1) == int(a2)
    actions = []
    for _ in range(10):
        action, _ = model.predict(obs, deterministic=True)
        obs, _, term, trunc, _ = env.step(int(action))
        actions.append(int(action))
        if term or trunc:
            break
    env2 = TradingEnv(candles, cost_model=CM, episode_length=20, random_start=False)
    obs2, _ = env2.reset(seed=0)
    actions2 = []
    for _ in range(len(actions)):
        action, _ = model.predict(obs2, deterministic=True)
        obs2, _, term, trunc, _ = env2.step(int(action))
        actions2.append(int(action))
        if term or trunc:
            break
    assert actions == actions2


def test_checksum_tamper_rejected(trained_model_dir: Path) -> None:
    artifact = trained_model_dir / MODEL_FILE
    original = artifact.read_bytes()
    try:
        artifact.write_bytes(original + b"tampered")
        with pytest.raises(ModelCompatibilityError, match="checksum"):
            load_record(trained_model_dir)
    finally:
        artifact.write_bytes(original)


def test_schema_mismatch_rejected(trained_model_dir: Path) -> None:
    meta_path = trained_model_dir / METADATA_FILE
    original = meta_path.read_text(encoding="utf-8")
    try:
        meta = json.loads(original)
        meta["feature_schema"]["version"] = "fs-v0-legacy"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with pytest.raises(ModelCompatibilityError, match="schema"):
            load_record(trained_model_dir)
    finally:
        meta_path.write_text(original, encoding="utf-8")


def test_missing_metadata_rejected(tmp_path: Path) -> None:
    bare = tmp_path / "legacy-artifact"
    bare.mkdir()
    (bare / MODEL_FILE).write_bytes(b"not a real model")
    with pytest.raises(ModelCompatibilityError, match="refusing to load"):
        load_record(bare)


def test_overlapping_train_eval_rejected() -> None:
    candles = make_candles(400)
    with pytest.raises(ValueError, match="strictly after"):
        train_ppo(candles, candles, SMOKE_CFG, Path("unused"))


def test_promotion_states(trained_model_dir: Path) -> None:
    set_promotion(trained_model_dir, "champion")
    assert load_record(trained_model_dir).metadata["promotion"] == "champion"
    set_promotion(trained_model_dir, "retired")
    with pytest.raises(ValueError):
        set_promotion(trained_model_dir, "bogus")


def test_ppo_strategy_adapter(trained_model_dir: Path) -> None:
    from obsidian_rl.evaluation.backtest import run_backtest
    from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy

    strat = PpoPolicyStrategy.from_dir(trained_model_dir)
    candles = make_candles(300, seed=11)
    res = run_backtest(candles, strat, cost_model=CM)
    assert res.n_decisions > 0
    assert np.isfinite(res.final_state_summary["final_equity"])


def test_invalid_model_id_path_construction_rejected(tmp_path: Path) -> None:
    train_candles = make_candles(160, seed=15)
    eval_candles = make_candles(
        120, seed=16, start_ms=int(train_candles["open_time"].iloc[-1]) + 900_000
    )
    models_dir = tmp_path / "safe_models"
    models_dir.mkdir()
    invalid_ids = [
        "../escape",
        "/abs/path",
        "foo/bar",
        "CON",
    ]
    for bad_id in invalid_ids:
        with pytest.raises(ValueError):
            train_ppo(train_candles, eval_candles, SMOKE_CFG, models_dir, model_id=bad_id)
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "abs").exists()
    assert list(models_dir.iterdir()) == []


def test_load_record_strict_metadata_checks(trained_model_dir: Path, tmp_path: Path) -> None:
    import shutil

    meta_path = trained_model_dir / METADATA_FILE
    original_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # integer model_id rejected
    copy_dir = tmp_path / "int_id_model"
    shutil.copytree(trained_model_dir, copy_dir)
    meta = dict(original_meta)
    meta["model_id"] = 12345
    (copy_dir / METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ModelCompatibilityError, match="must be a string without coercion"):
        load_record(copy_dir)

    # directory/metadata ID mismatch rejected
    copy_dir2 = tmp_path / "mismatch_dir"
    shutil.copytree(trained_model_dir, copy_dir2)
    meta = dict(original_meta)
    meta["model_id"] = "different-id"
    (copy_dir2 / METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ModelCompatibilityError, match="does not match directory name"):
        load_record(copy_dir2)

    # malformed metadata root rejected
    copy_dir3 = tmp_path / "malformed_root"
    shutil.copytree(trained_model_dir, copy_dir3)
    (copy_dir3 / METADATA_FILE).write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(ModelCompatibilityError, match="root must be a JSON object"):
        load_record(copy_dir3)

    # incomplete or reordered feature schema rejected
    copy_dir4 = tmp_path / "reordered_schema"
    shutil.copytree(trained_model_dir, copy_dir4)
    meta = dict(original_meta)
    meta["model_id"] = copy_dir4.name
    fs = dict(meta["feature_schema"])
    fs["market_features"] = list(reversed(fs["market_features"]))
    meta["feature_schema"] = fs
    (copy_dir4 / METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ModelCompatibilityError, match="feature schema mismatch"):
        load_record(copy_dir4)

    # malformed SHA-256 rejected
    copy_dir5 = tmp_path / "malformed_sha"
    shutil.copytree(trained_model_dir, copy_dir5)
    meta = dict(original_meta)
    meta["model_id"] = copy_dir5.name
    meta["artifact_sha256"] = "ABCDEF"
    (copy_dir5 / METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ModelCompatibilityError, match="valid 64-char lowercase SHA-256"):
        load_record(copy_dir5)


def test_git_source_root_resolution_in_temp_repos(tmp_path: Path) -> None:
    import subprocess
    from obsidian_rl.training.registry import (
        _resolve_repo_root,
        current_git_commit,
        get_git_source_state,
    )

    repo_dir = tmp_path / "temp_git_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    (repo_dir / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True)

    sub_dir = repo_dir / "sub" / "folder"
    sub_dir.mkdir(parents=True)
    assert _resolve_repo_root(sub_dir) == repo_dir.resolve()

    commit = current_git_commit(repo_dir)
    assert len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit.lower())

    state = get_git_source_state(repo_dir)
    assert state.commit == commit
    assert state.is_clean is True
    assert state.dirty_paths == []

    (repo_dir / "file.txt").write_text("modified", encoding="utf-8")
    dirty_state = get_git_source_state(repo_dir)
    assert dirty_state.commit == commit
    assert dirty_state.is_clean is False
    assert "file.txt" in dirty_state.dirty_paths
