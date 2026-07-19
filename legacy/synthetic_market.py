"""Synthetic Market Environment for Reinforcement Learning Trading Systems.

This module provides a standalone, production-ready synthetic financial market
environment (`SyntheticMarketEnv`) implemented purely with NumPy. It models
price dynamics using a deterministic sinusoidal trend combined with stochastic
Gaussian noise, featuring a mid-episode regime shift and a Volatility-Adjusted
Circuit Breaker with proportional drawdown penalties.
"""

from __future__ import annotations

from typing import Any
import numpy as np


class SyntheticMarketEnv:
    """Synthetic Financial Market Environment for Reinforcement Learning.

    Simulates price trajectories using an additive sinusoidal trend and
    Gaussian noise. Features a mid-episode market regime shift at step 500
    and a Volatility-Adjusted Circuit Breaker that dynamically scales stop-loss
    thresholds based on rolling return volatility, forcing emergency exits and
    applying dynamic proportional drawdown penalties upon catastrophic drawdowns.

    Parameters
    ----------
    steps : int, default=1000
        Maximum number of steps per episode.
    alpha : float, default=1.5
        Amplitude scaling factor for the sinusoidal price trend.
    omega : float, default=0.1
        Base angular frequency of the sinusoidal price trend in Regime 1.
    sigma : float, default=0.5
        Base standard deviation of the Gaussian noise term in Regime 1.
    start_price : float, default=100.0
        Initial asset price P_0 at episode reset.
    transaction_cost : float, default=0.1
        Cost incurred whenever the trading position changes between steps.
    base_stop_dist : float, default=0.2
        Base adverse price distance from peak/trough for the circuit breaker.
    vol_multiplier : float, default=2.0
        Multiplier scaling the base stop distance by rolling return volatility.
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
        transaction_cost: float = 0.1,
        base_stop_dist: float = 0.2,
        vol_multiplier: float = 2.0,
        seed: int | None = None,
    ) -> None:
        if steps <= 0:
            raise ValueError(f"Steps must be a positive integer, got {steps}.")
        if sigma < 0.0:
            raise ValueError(f"Sigma must be non-negative, got {sigma}.")
        if transaction_cost < 0.0:
            raise ValueError(
                f"Transaction cost must be non-negative, got {transaction_cost}."
            )
        if base_stop_dist < 0.0:
            raise ValueError(
                f"Base stop distance must be non-negative, got {base_stop_dist}."
            )

        self.steps: int = int(steps)
        self.alpha: float = float(alpha)
        self.omega: float = float(omega)
        self.sigma: float = float(sigma)
        self.start_price: float = float(start_price)
        self.transaction_cost: float = float(transaction_cost)
        self.base_stop_dist: float = float(base_stop_dist)
        self.vol_multiplier: float = float(vol_multiplier)
        self.rng: np.random.Generator = np.random.default_rng(seed)

        self.current_step: int = 0
        self.current_price: float = self.start_price
        self.current_position: int = 1  # 0: Short, 1: Flat, 2: Long
        self.peak_price: float = 0.0
        self.trough_price: float = float("inf")
        self.entry_price: float = 0.0
        self.returns_history: list[float] = []

    @property
    def position(self) -> int:
        """The signed integer representation of the current position (-1, 0, or 1)."""
        return self.ACTION_MAP[self.current_position]

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

        Resets the price to `start_price`, step counter to 0, agent position
        to 1 (Flat), clears circuit breaker bounds, and resets returns history.

        Returns
        -------
        dict[str, Any]
            Initial state dictionary.
        """
        self.current_step = 0
        self.current_price = float(self.start_price)
        self.current_position = 1
        self.peak_price = 0.0
        self.trough_price = float("inf")
        self.entry_price = 0.0
        self.returns_history = []
        return self._get_state()

    def step(self, action: int) -> tuple[dict[str, Any], float, bool]:
        """Advances the market environment by one time step and calculates reward.

        Enforces a mid-episode market regime shift and Volatility-Adjusted Circuit Breaker:
            1. Calculates rolling return volatility over `returns_history` (or 0.0 if len < 5).
            2. Computes `dynamic_stop = base_stop_dist * (1.0 + vol_multiplier * vol)`.
            3. Tracks `peak_price` (Longs) or `trough_price` (Shorts).
            4. CIRCUIT BREAKER CHECK: Forces emergency exit to Flat (`action = 1`) if
               exceeded by `dynamic_stop`.
            5. Applies dynamic proportional drawdown penalty ONLY if circuit breaker trips:
               - Long trip: `actual_loss = current_price - self.entry_price`
               - Short trip: `actual_loss = self.entry_price - current_price`
               - `reward += (actual_loss * 2.0)`
            6. Appends latest return to `returns_history` (max capacity 10).

        Parameters
        ----------
        action : int
            Discrete trading action: 0 (Short), 1 (Flat), 2 (Long).

        Returns
        -------
        next_state : dict[str, Any]
            Observation state after the step transition.
        reward : float
            Net Profit-and-Loss (PnL) reward including transaction costs and penalties.
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

        self.current_step += 1
        t: int = self.current_step

        if t <= 500:
            current_sigma: float = self.sigma
            current_omega: float = self.omega
            phase: float = current_omega * t
        else:
            current_sigma = self.sigma * 2.0
            current_omega = self.omega * 2.0
            phase = (self.omega * 500.0) + current_omega * (t - 500)

        noise: float = float(self.rng.normal(0.0, current_sigma))
        self.current_price = prev_price + self.alpha * np.sin(phase) + noise
        price_change: float = self.current_price - prev_price

        # 1. Calculate rolling standard deviation of self.returns_history
        if len(self.returns_history) < 5:
            vol: float = 0.0
        else:
            vol = float(np.std(self.returns_history))

        # 2. Compute dynamic_stop
        dynamic_stop: float = float(
            self.base_stop_dist * (1.0 + self.vol_multiplier * vol)
        )

        # 3. Track peak_price and trough_price & 4. CIRCUIT BREAKER CHECK
        penalty: float = 0.0
        if self.current_position == 2:  # Long
            self.peak_price = max(self.peak_price, self.current_price)
            if self.current_price < self.peak_price - dynamic_stop:
                action = 1  # Force emergency exit to Flat
                actual_loss: float = float(self.current_price - self.entry_price)
                penalty = actual_loss * 2.0
        elif self.current_position == 0:  # Short
            self.trough_price = min(self.trough_price, self.current_price)
            if self.current_price > self.trough_price + dynamic_stop:
                action = 1  # Force emergency exit to Flat
                actual_loss = float(self.entry_price - self.current_price)
                penalty = actual_loss * 2.0

        # 6. Append latest return to self.returns_history
        self.returns_history.append(price_change)
        if len(self.returns_history) > 10:
            self.returns_history = self.returns_history[-10:]

        # Calculate baseline PnL and finalized reward
        baseline_pnl: float = float(self.ACTION_MAP[action] * price_change)
        if action != self.current_position:
            reward: float = baseline_pnl - self.transaction_cost + penalty
        else:
            reward = baseline_pnl + penalty

        # Update entry price if entering a new active position
        if action != self.current_position and action != 1:
            self.entry_price = self.current_price

        self.current_position = action
        if self.current_position == 1:
            self.peak_price = 0.0
            self.trough_price = float("inf")
            self.entry_price = 0.0

        done: bool = self.current_step >= self.steps

        return self._get_state(), reward, done


if __name__ == "__main__":
    env = SyntheticMarketEnv(
        steps=1000,
        transaction_cost=0.1,
        base_stop_dist=0.2,
        vol_multiplier=2.0,
        seed=42,
    )
    state = env.reset()
    print(f"INITIAL STATE: {state} | Current Position Index: {env.current_position}")

    print("\n--- Testing Volatility-Adjusted Circuit Breaker on Long Position ---")
    env.step(action=2)
    print(
        f"Entered Long at step {env.current_step} | Price: {env.current_price:.4f} | "
        f"entry_price: {env.entry_price:.4f} | peak_price: {env.peak_price:.4f}"
    )

    for _ in range(15):
        prev_pos = env.current_position
        next_state, reward, done = env.step(action=2)
        vol_std = float(np.std(env.returns_history)) if len(env.returns_history) >= 5 else 0.0
        dyn_stop = env.base_stop_dist * (1.0 + env.vol_multiplier * vol_std)
        print(
            f"Step {env.current_step:3d} | Price: {next_state['price']:8.4f} | "
            f"peak: {env.peak_price:8.4f} | dyn_stop: {dyn_stop:.4f} | Reward: {reward:+.4f} | "
            f"Pos: {env.current_position} (was {prev_pos})"
        )
        if env.current_position == 1 and prev_pos == 2:
            print(">>> Circuit Breaker tripped! Emergency exit to Flat (1).")
            break
