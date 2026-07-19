"""Adapter exposing a frozen PPO policy through the Strategy protocol.

Used by the shared backtest runner, walk-forward evaluator, replay, and live paper
trading — one inference path everywhere. Exploration is disabled (deterministic=True);
the policy is never trained or mutated here.
"""

from pathlib import Path
from typing import Any

import numpy as np

from obsidian_rl.evaluation.backtest import DEFAULT_TARGETS, PortfolioFeatureTracker
from obsidian_rl.features.observation import PortfolioObs, build_observation


class PpoPolicyStrategy:
    def __init__(
        self,
        model: Any,
        model_id: str,
        allowed_targets: tuple[float, ...] = DEFAULT_TARGETS,
    ) -> None:
        self._model = model
        self.strategy_id = f"ppo:{model_id}"
        self.allowed_targets = allowed_targets

    @classmethod
    def from_dir(cls, model_dir: Path, *, device: str = "cpu") -> "PpoPolicyStrategy":
        from obsidian_rl.training.ppo import load_policy
        from obsidian_rl.training.registry import load_record

        record = load_record(model_dir)
        return cls(load_policy(model_dir, device=device), record.model_id)

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        obs = build_observation(market_row, portfolio)
        action, _ = self._model.predict(obs, deterministic=True)
        return float(self.allowed_targets[int(action)])


__all__ = ["PortfolioFeatureTracker", "PpoPolicyStrategy"]
