"""Training Orchestration Module for Institutional Reinforcement Learning Systems.

This module orchestrates interaction between the synthetic financial market
environment (`SyntheticMarketEnv`) and the tabular Q-learning agent
(`QLearningAgent`), running an institutional training pipeline over discrete
episodes and logging performance metrics.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np

# Ensure project root is accessible on sys.path for robust module execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.ql_agent import QLearningAgent
from src.synthetic_market import SyntheticMarketEnv


def train(
    episodes: int = 2000,
    steps: int = 1000,
    seed: int | None = 42,
    log_interval: int = 200,
) -> tuple[QLearningAgent, list[float]]:
    """Runs the reinforcement learning training loop.

    Instantiates the synthetic market environment and Q-learning agent, then
    iterates through training episodes. Tracks discrete price returns, updates
    agent policy via Temporal Difference Q-learning, decays exploration rates
    across the expanded horizon, and logs periodic performance metrics.

    Parameters
    ----------
    episodes : int, default=2000
        Total number of training episodes to execute for convergence.
    steps : int, default=1000
        Maximum number of discrete time steps per episode.
    seed : int | None, default=42
        Random seed for reproducible environment trajectories.
    log_interval : int, default=200
        Frequency (in episodes) at which training metrics are printed.

    Returns
    -------
    agent : QLearningAgent
        Trained Q-learning agent containing the learned Q-table.
    episode_rewards : list[float]
        History of total accumulated rewards per episode.
    """
    env = SyntheticMarketEnv(steps=steps, seed=seed)
    # Stretch epsilon decay across the 2000-episode horizon so epsilon reaches ~0.01 around episode 1900
    agent = QLearningAgent(epsilon_decay=0.99758)

    episode_rewards: list[float] = []

    for episode in range(1, episodes + 1):
        initial_state: dict[str, Any] = env.reset()
        initial_price: float = float(initial_state["price"])

        # Initialize tracking list for the last 4 prices
        price_history: list[float] = [initial_price] * 4
        total_reward: float = 0.0
        done: bool = False

        while not done:
            state_index: int = agent.get_state_index(price_history)
            action: int = agent.choose_action(state_index)

            next_state_dict, reward, done = env.step(action)

            price_change: float = float(next_state_dict["price"]) - price_history[-1]
            agent.update_volatility(price_change)

            # Update tracking list with observed price and keep last 4 prices
            price_history.append(float(next_state_dict["price"]))
            price_history = price_history[-4:]

            next_state_index: int = agent.get_state_index(price_history)
            agent.learn(
                state=state_index,
                action=action,
                reward=reward,
                next_state=next_state_index,
            )

            total_reward += reward

        # Decay agent epsilon at the end of each episode
        agent.decay_epsilon()
        episode_rewards.append(total_reward)

        if episode % log_interval == 0:
            print(
                f"Episode {episode:4d}/{episodes} | "
                f"Total Reward: {total_reward:10.2f} | "
                f"Ending Epsilon: {agent.epsilon:.4f}"
            )

    return agent, episode_rewards


if __name__ == "__main__":
    print("=== Institutional Reinforcement Learning Pipeline ===")
    trained_agent, rewards_history = train(episodes=2000, steps=1000, seed=42)
    print("=== Training Complete ===")
