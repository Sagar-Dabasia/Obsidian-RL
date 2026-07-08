"""Synthetic Market Environment for Reinforcement Learning Trading Systems.

This module provides a standalone, production-ready synthetic financial market
environment (`SyntheticMarketEnv`) implemented purely with NumPy. It models
price dynamics using a deterministic sinusoidal trend combined with stochastic
Gaussian noise, enabling controlled experimentation for RL trading agents.

Mathematical Specification
--------------------------
Price Process:
    P_t = P_{t-1} + \alpha \cdot \sin(\omega \cdot t) + \epsilon_t
    where \epsilon_t \sim \mathcal{N}(0, \sigma^2)

Action Space:
    - 0: Short (-1 position)
    - 1: Flat  ( 0 position)
    - 2: Long  (+1 position)

Reward Function:
    R_t = \text{pos}_{t-1} \cdot (P_t - P_{t-1})
"""

from __future__ import annotations

from typing import Any
import numpy as np


class SyntheticMarketEnv:
    """Synthetic Financial Market Environment for Reinforcement Learning.

    Simulates price trajectories using an additive sinusoidal trend and
    Gaussian noise. Tracks agent positions and computes raw Profit-and-Loss
    (PnL) rewards across discrete time steps.

    Parameters
    ----------
    steps : int, default=1000
        Maximum number of steps per episode.
    alpha : float, default=1.5
        Amplitude scaling factor for the sinusoidal price trend.
    omega : float, default=0.1
        Angular frequency of the sinusoidal price trend.
    sigma : float, default=0.5
        Standard deviation of the Gaussian noise term \epsilon_t ~ N(0, \sigma^2).
    start_price : float, default=100.0
        Initial asset price P_0 at episode reset.
    seed : int | None, default=None
        Random seed for reproducible Gaussian noise generation.
    """

    ACTION_MAP: dict[int, int] = {
        0: -1,  # Short
        1: 0,   # Flat
        2: 1,   # Long
    }

    def __init__(
        self,
        steps: int = 1000,
        alpha: float = 1.5,
        omega: float = 0.1,
        sigma: float = 0.5,
        start_price: float = 100.0,
        seed: int | None = None,
    ) -> None:
        if steps <= 0:
            raise ValueError(f"Steps must be a positive integer, got {steps}.")
        if sigma < 0.0:
            raise ValueError(f"Sigma must be non-negative, got {sigma}.")

        self.steps: int = int(steps)
        self.alpha: float = float(alpha)
        self.omega: float = float(omega)
        self.sigma: float = float(sigma)
        self.start_price: float = float(start_price)
        self.rng: np.random.Generator = np.random.default_rng(seed)

        self.current_step: int = 0
        self.current_price: float = self.start_price
        self.position: int = 0

    def _get_state(self) -> dict[str, Any]:
        """Constructs the current observation state dictionary.

        Returns
        -------
        dict[str, Any]
            State dictionary containing current price, step index, and agent position.
        """
        return {
            "price": float(self.current_price),
            "step": int(self.current_step),
            "position": int(self.position),
        }

    def reset(self) -> dict[str, Any]:
        """Re-initializes the environment to its starting state.

        Resets the price to `start_price`, step counter to 0, and agent
        position to 0 (Flat).

        Returns
        -------
        dict[str, Any]
            Initial state dictionary.
        """
        self.current_step = 0
        self.current_price = float(self.start_price)
        self.position = 0
        return self._get_state()

    def step(self, action: int) -> tuple[dict[str, Any], float, bool]:
        """Advances the market environment by one time step.

        Generates the next price tick according to:
            P_t = P_{t-1} + \alpha \cdot \sin(\omega \cdot t) + \epsilon_t

        Calculates raw PnL reward based on the previous position and the
        observed price change \Delta P = P_t - P_{t-1}.

        Parameters
        ----------
        action : int
            Discrete trading action: 0 (Short), 1 (Flat), 2 (Long).

        Returns
        -------
        next_state : dict[str, Any]
            Observation state after the step transition.
        reward : float
            Raw Profit-and-Loss (PnL) reward from the price transition.
        done : bool
            True if terminal step `steps` is reached, False otherwise.

        Raises
        ------
        ValueError
            If an invalid action code is provided.
        """
        if action not in self.ACTION_MAP:
            raise ValueError(
                f"Invalid action {action}. Valid actions are 0 (Short), 1 (Flat), 2 (Long)."
            )

        prev_price: float = self.current_price
        prev_position: int = self.position

        self.current_step += 1
        t: int = self.current_step
        noise: float = float(self.rng.normal(0.0, self.sigma))

        self.current_price = prev_price + self.alpha * np.sin(self.omega * t) + noise
        price_change: float = self.current_price - prev_price
        reward: float = float(prev_position * price_change)

        self.position = self.ACTION_MAP[action]
        done: bool = self.current_step >= self.steps

        return self._get_state(), reward, done


if __name__ == "__main__":
    env = SyntheticMarketEnv(steps=1000, seed=42)
    state = env.reset()
    print(f"INITIAL STATE: {state}")

    rng = np.random.default_rng(42)
    random_actions = rng.integers(0, 3, size=5)
    for step_idx, act in enumerate(random_actions, start=1):
        action = int(act)
        next_state, reward, done = env.step(action)
        print(
            f"Step {step_idx} | Action: {action} | "
            f"Next State: {next_state} | Reward: {reward:+.4f} | Done: {done}"
        )
