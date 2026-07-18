"""Evaluation Module for Institutional Reinforcement Learning Trading Systems.

This module provides deterministic evaluation capabilities (`evaluate`) for a
trained `QLearningAgent` operating within a `RealMarketEnv`. It forces
pure exploitation mode (`epsilon = 0.0`), tracks cumulative returns of the agent
and a Buy & Hold baseline, and plots the performance comparison.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure project root is accessible on sys.path for robust module execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import matplotlib.pyplot as plt
from src.ql_agent import QLearningAgent
from src.real_market import RealMarketEnv
from src.train import train


def evaluate_agent(
    agent: QLearningAgent,
    env: RealMarketEnv,
) -> tuple[list[float], list[float]]:
    """Evaluates a trained Q-learning agent in a deterministic exploitation mode.

    Sets agent exploration probability `epsilon` to 0.0 and executes a full
    episode in `env` tracking the cumulative return of the agent and Buy & Hold.

    Parameters
    ----------
    agent : QLearningAgent
        The trained Q-learning agent to evaluate.
    env : RealMarketEnv
        The real market environment instance for evaluation.

    Returns
    -------
    tuple[list[float], list[float]]
        A tuple containing:
            - agent_cumulative: Cumulative returns of the agent.
            - buy_and_hold_cumulative: Cumulative returns of Buy & Hold.
    """
    # Force purely deterministic exploitation mode
    agent.epsilon = 0.0
    agent.returns_history.clear()

    state = env.reset()
    initial_price: float = float(env.current_price)

    agent_cumulative: list[float] = [0.0]
    buy_and_hold_cumulative: list[float] = [0.0]
    current_agent_return: float = 0.0

    done: bool = False
    while not done:
        prev_price = float(env.current_price)
        action: int = agent.choose_action(state)

        next_state, reward, done, _ = env.step(action)
        price_change = float(env.current_price) - prev_price
        agent.update_volatility(price_change)

        state = next_state
        current_agent_return += reward
        agent_cumulative.append(current_agent_return)
        buy_and_hold_cumulative.append(float(env.current_price) - initial_price)

    return agent_cumulative, buy_and_hold_cumulative


def main() -> None:
    """Orchestrates agent training, evaluation, and chart generation."""
    print("=== Training Agent on Real Market Data ===")
    trained_agent, _ = train(episodes=2000, steps=1000, seed=42)

    print("=== Evaluating Agent against Buy & Hold Baseline ===")
    eval_env = RealMarketEnv(ticker="ETH-USD", period="1mo", interval="15m")
    agent_cumulative, buy_and_hold = evaluate_agent(trained_agent, eval_env)

    print("=== Generating Performance Chart ===")
    plt.figure(figsize=(12, 6))
    plt.plot(agent_cumulative, label="Q-Learning Agent (Epsilon = 0.0)", color="blue", linewidth=1.5)
    plt.plot(buy_and_hold, label="Buy & Hold Baseline", color="orange", linewidth=1.5)
    plt.title("Out-of-Sample Performance: Q-Learning Agent vs. Buy & Hold (ETH-USD)")
    plt.xlabel("Step Index")
    plt.ylabel("Cumulative Absolute Return (ETH-USD Price Difference)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)

    # Save to the root directory as oos_performance.png
    output_path = Path(_project_root) / "oos_performance.png"
    plt.savefig(str(output_path), dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Evaluation Complete. Performance chart saved to: {output_path}")


if __name__ == "__main__":
    main()
