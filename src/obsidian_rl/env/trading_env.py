"""Standards-compliant Gymnasium trading environment.

Uses the centralized feature pipeline and portfolio engine — it owns NO position state
of its own. Timing matches the backtest runner exactly: observe candle t at its close,
execute the chosen target at open[t+1], receive reward from the equity change between
close[t] and close[t+1].

Reward = log net-equity return
         - turnover_weight  * (traded notional / equity)
         - drawdown_weight  * current drawdown
         - exposure_weight  * |exposure|
Every component is exposed in `info["reward_components"]` and has a dedicated test.

The env never downloads data, never trains or mutates models, never fabricates prices.
"""

import math
from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from obsidian_rl.evaluation.backtest import DEFAULT_TARGETS, PortfolioFeatureTracker
from obsidian_rl.features.observation import build_observation
from obsidian_rl.features.pipeline import WARMUP_ROWS, compute_market_features
from obsidian_rl.features.schema import OBSERVATION_DIM, OBSERVATION_DTYPE
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine


@dataclass(frozen=True)
class RewardConfig:
    """Weights for reward shaping. Purposes:

    - turnover_weight: discourages churn beyond what explicit costs already charge,
      pushing the policy toward parsimonious position changes.
    - drawdown_weight: penalizes sitting in drawdown, encouraging capital preservation.
    - exposure_weight: optional risk-aversion term on absolute exposure (default off).
    - turnover_penalty_bps: additional training regularizer charged on absolute target change.
    """

    turnover_weight: float = 0.02
    drawdown_weight: float = 0.005
    exposure_weight: float = 0.0
    turnover_penalty_bps: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.turnover_penalty_bps, bool) or not isinstance(
            self.turnover_penalty_bps, (int, float)
        ):
            raise ValueError(
                f"turnover_penalty_bps={self.turnover_penalty_bps!r} must be int or float, not {type(self.turnover_penalty_bps).__name__}"
            )
        if not math.isfinite(self.turnover_penalty_bps):
            raise ValueError(f"turnover_penalty_bps={self.turnover_penalty_bps!r} must be finite")
        if self.turnover_penalty_bps < 0:
            raise ValueError(
                f"turnover_penalty_bps={self.turnover_penalty_bps} must be non-negative"
            )


class TradingEnv(gym.Env):
    metadata: dict[str, Any] = {"render_modes": []}

    def __init__(
        self,
        candles: pd.DataFrame,
        *,
        portfolio_config: PortfolioConfig | None = None,
        cost_model: CostModel | None = None,
        reward_config: RewardConfig | None = None,
        episode_length: int | None = 2048,
        random_start: bool = True,
        allowed_targets: tuple[float, ...] = DEFAULT_TARGETS,
    ) -> None:
        super().__init__()
        if len(candles) < WARMUP_ROWS + 3:
            raise ValueError(f"need at least {WARMUP_ROWS + 3} candles, got {len(candles)}")
        self._candles = candles.reset_index(drop=True)
        self._features = compute_market_features(self._candles).to_numpy(dtype=np.float32)
        self._open = self._candles["open"].to_numpy(dtype=np.float64)
        self._close = self._candles["close"].to_numpy(dtype=np.float64)
        self._open_time = self._candles["open_time"].to_numpy(dtype=np.int64)

        self.portfolio_config = portfolio_config or PortfolioConfig()
        self.cost_model = cost_model or CostModel()
        self.reward_config = reward_config or RewardConfig()
        self.episode_length = episode_length
        self.random_start = random_start
        self.allowed_targets = allowed_targets

        self.action_space = spaces.Discrete(len(allowed_targets))
        # Every feature is clipped/bounded upstream (pipeline CLIP=10, portfolio obs
        # clipped to at most [-3, 10]); 16 is a safe hard bound.
        self.observation_space = spaces.Box(
            low=-16.0, high=16.0, shape=(OBSERVATION_DIM,), dtype=np.float32
        )

        self._engine: PortfolioEngine | None = None
        self._tracker = PortfolioFeatureTracker()
        self._t = 0
        self._steps = 0
        self._previous_target = 0.0

    # ------------------------------------------------------------------ internals
    def _max_start(self) -> int:
        last_decidable = len(self._candles) - 2  # need candle t+1 to execute
        if self.episode_length is None:
            return WARMUP_ROWS
        return max(WARMUP_ROWS, last_decidable - self.episode_length)

    def _obs(self) -> np.ndarray:
        assert self._engine is not None
        market_row = self._features[self._t]
        if np.isnan(market_row).any():
            raise RuntimeError(f"NaN features at row {self._t}; data/warm-up bug")
        port = self._tracker.observe(self._engine, self._close[self._t])
        return build_observation(market_row, port)

    # ------------------------------------------------------------------ gym API
    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        self._engine = PortfolioEngine(self.portfolio_config, self.cost_model)
        self._tracker.reset()
        self._steps = 0
        if self.random_start:
            self._t = int(self.np_random.integers(WARMUP_ROWS, self._max_start() + 1))
        else:
            self._t = WARMUP_ROWS
        self._previous_target = 0.0
        return self._obs(), {"start_index": self._t, "open_time": int(self._open_time[self._t])}

    def step(
        self, action: int | np.integer
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        assert self._engine is not None, "call reset() first"
        action_idx = int(action)
        if not 0 <= action_idx < len(self.allowed_targets):
            raise ValueError(f"invalid action {action_idx}")
        target = self.allowed_targets[action_idx]

        t = self._t
        equity_before = self._engine.state.net_equity(self._close[t])
        exec_price = self._open[t + 1]
        result = self._engine.rebalance(target, exec_price)

        next_close = self._close[t + 1]
        equity_after = self._engine.state.net_equity(next_close)
        self._engine.mark_to_market(next_close)
        self._tracker.update_after_step(self._engine.state.qty, result.traded_notional)

        terminated = equity_after <= 0
        self._steps += 1
        self._t += 1
        out_of_data = self._t >= len(self._candles) - 1
        budget_spent = self.episode_length is not None and self._steps >= self.episode_length
        truncated = (out_of_data or budget_spent) and not terminated

        if terminated or truncated:
            liq = self._engine.liquidate(next_close)
            equity_after = self._engine.state.net_equity(next_close)
            result_notional = result.traded_notional + liq.traded_notional
        else:
            result_notional = result.traded_notional

        safe_before = max(equity_before, 1e-9)
        equity_return = (
            math.log(max(equity_after, 1e-9) / safe_before) if equity_before > 0 else -1.0
        )
        turnover_pen = self.reward_config.turnover_weight * (result_notional / safe_before)
        drawdown_pen = self.reward_config.drawdown_weight * self._engine.state.drawdown(next_close)
        exposure_pen = self.reward_config.exposure_weight * abs(
            self._engine.state.exposure(next_close)
        )
        existing_reward = equity_return - turnover_pen - drawdown_pen - exposure_pen

        turnover_reg_pen = (self.reward_config.turnover_penalty_bps / 10000.0) * abs(
            target - self._previous_target
        )
        self._previous_target = target
        reward = existing_reward - turnover_reg_pen

        info: dict[str, Any] = {
            "reward_components": {
                "equity_log_return": equity_return,
                "turnover_penalty": -turnover_pen,
                "drawdown_penalty": -drawdown_pen,
                "exposure_penalty": -exposure_pen,
                "turnover_regularization_penalty": -turnover_reg_pen,
            },
            "raw_reward": existing_reward,
            "penalty": turnover_reg_pen,
            "final_reward": reward,
            "proposed_target": target,
            "executed_target": result.executed_target,
            "execution": {
                "delta_qty": result.delta_qty,
                "exec_price": result.exec_price,
                "traded_notional": result.traded_notional,
                "total_cost": result.total_cost,
                "rejection_reason": result.rejection_reason,
            },
            "net_equity": equity_after,
            "drawdown": self._engine.state.drawdown(next_close),
            "open_time": int(self._open_time[self._t]),
        }

        if terminated or truncated:
            obs = np.zeros(OBSERVATION_DIM, dtype=np.float32) if out_of_data else self._obs()
        else:
            obs = self._obs()
        return obs, float(reward), bool(terminated), bool(truncated), info
