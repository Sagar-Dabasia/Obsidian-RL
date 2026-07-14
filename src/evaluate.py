"""Evaluation Module for Institutional Reinforcement Learning Systems.

This module provides deterministic evaluation capabilities (`evaluate`) for a
trained `QLearningAgent` operating within a `SyntheticMarketEnv`. It forces
pure exploitation mode (`epsilon = 0.0`), tracks institutional trading metrics,
and outputs a summary report.
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


def evaluate(
    agent: QLearningAgent,
    env: SyntheticMarketEnv,
) -> dict[str, float]:
    """Evaluates a trained Q-learning agent in a deterministic exploitation mode.

    Sets agent exploration probability `epsilon` to 0.0 and executes a full
    episode in `env`. Computes cumulative Profit-and-Loss (PnL), total active
    trading steps executed, and the percentage of active trades with positive PnL.

    Parameters
    ----------
    agent : QLearningAgent
        The trained Q-learning agent to evaluate.
    env : SyntheticMarketEnv
        The market environment instance for evaluation.

    Returns
    -------
    dict[str, float]
        Dictionary containing:
            - "total_pnl": Cumulative PnL achieved over the episode.
            - "total_trades": Total number of active trade exposures executed.
            - "win_rate": Percentage of active trades yielding positive PnL.
    """
    # Force purely deterministic exploitation mode
    agent.epsilon = 0.0

    initial_state: dict[str, Any] = env.reset()
    price_history: list[float] = [float(initial_state["price"])] * 4

    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    done: bool = False

    while not done:
        prev_position: int = env.position
        state_index: int = agent.get_state_index(price_history)
        action: int = agent.choose_action(state_index)

        next_state_dict, reward, done = env.step(action)

        price_change: float = float(next_state_dict["price"]) - price_history[-1]
        agent.update_volatility(price_change)

        price_history.append(float(next_state_dict["price"]))
        price_history = price_history[-4:]

        total_pnl += reward

        # Track trade execution metrics whenever an active position was held
        if prev_position != 0:
            total_trades += 1
            if reward > 0.0:
                winning_trades += 1

    win_rate: float = (
        (winning_trades / total_trades) * 100.0 if total_trades > 0 else 0.0
    )

    metrics: dict[str, float] = {
        "total_pnl": float(total_pnl),
        "total_trades": float(total_trades),
        "win_rate": float(win_rate),
    }

    print("==================================================")
    print("        QLearningAgent Evaluation Summary         ")
    print("==================================================")
    print(f"Total Cumulative PnL : {metrics['total_pnl']:+14.2f}")
    print(f"Total Trades Executed: {int(metrics['total_trades']):14d}")
    print(f"Win Rate             : {metrics['win_rate']:13.2f}%")
    print("==================================================")

    return metrics


if __name__ == "__main__":
    print("=== Institutional QLearningAgent Evaluation ===")

    eval_env = SyntheticMarketEnv(steps=1000, seed=42)
    eval_agent = QLearningAgent()

    # Mock a trained agent's Q-table favoring trend-following actions
    # States 0-3 (mostly non-positive returns) -> Action 0 (Short)
    # States 4-7 (mostly positive returns)     -> Action 2 (Long)
    eval_agent.q_table[0:4, 0] = 1.0
    eval_agent.q_table[4:8, 2] = 1.0

    evaluate(agent=eval_agent, env=eval_env)
