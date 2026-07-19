"""PPO training pipeline tests: CPU smoke training, save/load, compatibility gates,
deterministic inference, GPU detection. All tiny and CPU-only."""

import json
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
