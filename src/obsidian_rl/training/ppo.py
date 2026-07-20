"""PPO training on the TradingEnv (Stable-Baselines3, MLP policy, discrete-5 actions).

Train and eval envs are strictly separated candle ranges supplied by the caller (the
walk-forward evaluator or CLI enforces chronology). Checkpoints, the best-validation
model, and full metadata are written under models/<model_id>/.
"""

import logging
import math
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian_rl.env.trading_env import RewardConfig, TradingEnv
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig
from obsidian_rl.training.device import DeviceReport, detect_device
from obsidian_rl.training.registry import MODEL_FILE, ModelRecord, load_record, register_model

logger = logging.getLogger(__name__)

FINAL_MODEL_FILE = "final_model.zip"
BEST_VALIDATION_MODEL_FILE = "best_model.zip"


@dataclass(frozen=True)
class PpoHyperparams:
    n_steps: int = 2048
    batch_size: int = 256
    learning_rate: float = 3e-4
    gamma: float = 0.999
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    net_arch: tuple[int, ...] = (64, 64)


@dataclass(frozen=True)
class TrainConfig:
    total_timesteps: int = 500_000
    n_envs: int = 4
    seed: int = 42
    device: str = "auto"  # auto | cpu | cuda
    episode_length: int = 2048
    checkpoint_freq: int = 100_000  # in steps per env
    eval_freq: int = 50_000
    hyperparams: PpoHyperparams = field(default_factory=PpoHyperparams)
    reward: RewardConfig = field(default_factory=RewardConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    costs: CostModel = field(default_factory=CostModel)


@dataclass
class TrainResult:
    record: ModelRecord
    device: DeviceReport
    eval_mean_reward: float | None
    wall_seconds: float


def _make_env_fn(candles: pd.DataFrame, cfg: TrainConfig, *, training: bool, seed: int) -> Any:
    def make() -> TradingEnv:
        env = TradingEnv(
            candles,
            portfolio_config=cfg.portfolio,
            cost_model=cfg.costs,
            reward_config=cfg.reward,
            episode_length=cfg.episode_length if training else None,
            random_start=training,
        )
        env.reset(seed=seed)
        return env

    return make


def train_ppo(
    train_candles: pd.DataFrame,
    eval_candles: pd.DataFrame,
    cfg: TrainConfig,
    models_dir: Path,
    *,
    model_id: str | None = None,
    resume_from: Path | None = None,
) -> TrainResult:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    t_start_train = int(train_candles["open_time"].iloc[0])
    t_end_train = int(train_candles["open_time"].iloc[-1])
    t_start_eval = int(eval_candles["open_time"].iloc[0])
    if t_start_eval <= t_end_train:
        raise ValueError(
            f"eval period (starts {t_start_eval}) must be strictly after training period "
            f"(ends {t_end_train}); shuffled or overlapping financial splits are forbidden"
        )

    device_report = detect_device(cfg.device)
    logger.info("device: %s", device_report.to_dict())

    model_id = model_id or f"ppo-{time.strftime('%Y%m%d-%H%M%S')}-seed{cfg.seed}"
    model_dir = Path(models_dir) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    venv = DummyVecEnv(
        [
            _make_env_fn(train_candles, cfg, training=True, seed=cfg.seed + i)
            for i in range(cfg.n_envs)
        ]
    )
    eval_env = DummyVecEnv(
        [lambda: Monitor(_make_env_fn(eval_candles, cfg, training=False, seed=cfg.seed + 10_000)())]
    )

    hp = cfg.hyperparams
    if resume_from is not None:
        record = load_record(resume_from)  # validates schema + checksum
        model = PPO.load(
            record.model_dir / MODEL_FILE,
            env=venv,
            device=device_report.selected_device,
        )
        logger.info("resumed from %s", record.model_id)
    else:
        model = PPO(
            "MlpPolicy",
            venv,
            n_steps=hp.n_steps,
            batch_size=hp.batch_size,
            learning_rate=hp.learning_rate,
            gamma=hp.gamma,
            gae_lambda=hp.gae_lambda,
            clip_range=hp.clip_range,
            ent_coef=hp.ent_coef,
            vf_coef=hp.vf_coef,
            policy_kwargs={"net_arch": list(hp.net_arch)},
            seed=cfg.seed,
            device=device_report.selected_device,
            verbose=0,
        )

    checkpoint_callback = CheckpointCallback(
        save_freq=max(cfg.checkpoint_freq // cfg.n_envs, 1),
        save_path=str(model_dir / "checkpoints"),
        name_prefix="ckpt",
    )

    class TrackingEvalCallback(EvalCallback):
        """Remember the step at which EvalCallback writes its selected checkpoint."""

        best_timestep: int | None = None

        def _on_step(self) -> bool:
            previous_best = self.best_mean_reward
            should_continue = super()._on_step()
            if self.best_mean_reward > previous_best:
                self.best_timestep = self.num_timesteps
            return should_continue

    eval_callback = TrackingEvalCallback(
        eval_env,
        best_model_save_path=str(model_dir / "best"),
        eval_freq=max(cfg.eval_freq // cfg.n_envs, 1),
        n_eval_episodes=1,
        deterministic=True,
        verbose=0,
    )
    callbacks = [
        checkpoint_callback,
        eval_callback,
    ]

    started = time.time()
    model.learn(total_timesteps=cfg.total_timesteps, callback=callbacks, progress_bar=False)
    wall = time.time() - started

    final_checkpoint = model_dir / FINAL_MODEL_FILE
    model.save(final_checkpoint)

    best_checkpoint = model_dir / "best" / BEST_VALIDATION_MODEL_FILE
    if not best_checkpoint.is_file() or best_checkpoint.stat().st_size == 0:
        raise RuntimeError(
            "EvalCallback did not create a valid best validation checkpoint; "
            f"refusing to register the final checkpoint (diagnostic retained at {final_checkpoint})"
        )
    eval_mean = float(eval_callback.best_mean_reward)
    if not math.isfinite(eval_mean):
        raise RuntimeError("EvalCallback selected a checkpoint without a finite validation score")
    shutil.copy2(best_checkpoint, model_dir / MODEL_FILE)

    record = register_model(
        Path(models_dir),
        model_id,
        algorithm="ppo-mlp-discrete5",
        config={
            "hyperparams": asdict(hp),
            "reward": asdict(cfg.reward),
            "portfolio": asdict(cfg.portfolio),
            "costs": asdict(cfg.costs),
            "total_timesteps": cfg.total_timesteps,
            "n_envs": cfg.n_envs,
            "episode_length": cfg.episode_length,
            "device": device_report.to_dict(),
        },
        seeds=[cfg.seed],
        data_info={
            "train_start_ms": t_start_train,
            "train_end_ms": t_end_train,
            "eval_start_ms": t_start_eval,
            "eval_end_ms": int(eval_candles["open_time"].iloc[-1]),
            "n_train_candles": len(train_candles),
            "n_eval_candles": len(eval_candles),
        },
        metrics={
            "eval_mean_reward": eval_mean,
            "best_validation_mean_reward": eval_mean,
            "best_validation_timestep": eval_callback.best_timestep,
            "wall_seconds": wall,
        },
    )
    return TrainResult(record, device_report, eval_mean, wall)


def load_policy(model_dir: Path, *, device: str = "cpu") -> Any:
    """Load a validated model for inference (exploration disabled by the caller)."""
    from stable_baselines3 import PPO

    record = load_record(model_dir)
    return PPO.load(Path(record.model_dir) / MODEL_FILE, device=device)
