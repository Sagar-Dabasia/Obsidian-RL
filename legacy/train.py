"""Training Orchestration Module for Institutional Reinforcement Learning Systems.

This module orchestrates interaction between the real financial market environment
(`RealMarketEnv`) and the tabular Q-learning agent (`QLearningAgent`), running an
institutional training pipeline over discrete episodes and logging performance metrics.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure project root is accessible on sys.path for robust module execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.ql_agent import QLearningAgent
from src.real_market import RealMarketEnv


def train(
    episodes: int = 2000,
    steps: int = 1000,
    seed: int | None = 42,
    log_interval: int = 200,
) -> tuple[QLearningAgent, list[float]]:
    """Runs the reinforcement learning training loop against historical market data.

    Instantiates the real market environment and Q-learning agent, then iterates
    through training episodes. Tracks discrete price returns from historical bars,
    updates agent policy via Temporal Difference Q-learning, decays exploration
    rates across the horizon, and logs periodic performance metrics.

    Parameters
    ----------
    episodes : int, default=2000
        Total number of training episodes to execute for convergence.
    steps : int, default=1000
        Maximum number of discrete time steps per episode (unused when streaming real data).
    seed : int | None, default=42
        Random seed parameter (retained for signature compatibility).
    log_interval : int, default=200
        Frequency (in episodes) at which training metrics are printed.

    Returns
    -------
    agent : QLearningAgent
        Trained Q-learning agent containing the learned Q-table.
    episode_rewards : list[float]
        History of total accumulated rewards per episode.
    """
    env = RealMarketEnv(ticker="BTC-USD", period="1mo", interval="15m")
    # Stretch epsilon decay across the 2000-episode horizon so epsilon reaches ~0.01 around episode 1900
    agent = QLearningAgent(epsilon_decay=0.99758)

    episode_rewards: list[float] = []

    for episode in range(1, episodes + 1):
        state = env.reset()
        total_reward: float = 0.0
        done: bool = False

        while not done:
            prev_price = float(env.current_price)
            action: int = agent.choose_action(state)

            next_state, reward, done, _ = env.step(action)
            price_change = float(env.current_price) - prev_price
            agent.update_volatility(price_change)

            agent.learn(
                state=state,
                action=action,
                reward=reward,
                next_state=next_state,
            )

            state = next_state
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
    checkpoint_path = Path(_project_root) / "q_table.pkl"
    trained_agent.save_checkpoint(checkpoint_path)
    print(f"=== Training Complete | Checkpoint saved to: {checkpoint_path} ===")

