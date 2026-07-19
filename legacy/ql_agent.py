"""Q-Learning Agent for Institutional Reinforcement Learning Trading Systems.

This module implements a tabular Q-learning agent (`QLearningAgent`) designed
for discrete state and action spaces in financial trading environments. It uses
only NumPy for numerical efficiency and adheres to institutional quantitative
software engineering standards, incorporating a dynamic, volatility-adjusted
Expected Value (EV) threshold filter to prevent marginal position changes during
volatile market regimes when transaction costs are present.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
import pickle
import numpy as np


class QLearningAgent:
    """Tabular Q-Learning Agent for financial market trading environments.

    Uses a dictionary-based Q-table to support multi-dimensional state spaces
    and learns an optimal trading policy over a discrete action space using
    Temporal Difference (TD) Q-learning. Includes a dynamic, volatility-adjusted
    Expected Value (EV) threshold filter to eliminate low-margin trades.

    Parameters
    ----------
    alpha : float, default=0.1
        Learning rate (step size) for Temporal Difference updates.
    gamma : float, default=0.95
        Discount factor for future rewards.
    epsilon : float, default=1.0
        Initial exploration probability for epsilon-greedy action selection.
    epsilon_decay : float, default=0.995
        Multiplicative decay rate applied to epsilon after each learning step.
    min_epsilon : float, default=0.01
        Minimum allowable value for exploration probability epsilon.
    ev_threshold : float, default=0.15
        Base minimum expected Q-value improvement required over the current position
        to justify changing the active trading position.
    vol_sensitivity : float, default=2.0
        Sensitivity scaling coefficient that widens the EV threshold linearly
        with rolling return volatility.
    """

    def __init__(
        self,
        alpha: float = 0.1,
        gamma: float = 0.95,
        epsilon: float = 1.0,
        epsilon_decay: float = 0.995,
        min_epsilon: float = 0.01,
        ev_threshold: float = 0.15,
        vol_sensitivity: float = 2.0,
    ) -> None:
        self.alpha = float(alpha)
        self.gamma = float(gamma)
        self.epsilon = float(epsilon)
        self.epsilon_decay = float(epsilon_decay)
        self.min_epsilon = float(min_epsilon)
        self.ev_threshold = float(ev_threshold)
        self.vol_sensitivity = float(vol_sensitivity)

        # Dictionary-based Q-table mapping state string keys to Action-Value numpy arrays
        self.q_table: dict[str, np.ndarray] = {}
        self.current_position: int = 1  # 0: Short, 1: Flat, 2: Long
        self.returns_history: list[float] = []

    def _state_to_key(self, state: tuple[int, ...]) -> str:
        """Converts a state tuple to a string key for the Q-table dictionary.

        Parameters
        ----------
        state : tuple[int, ...]
            6-element or 7-element state tuple.

        Returns
        -------
        str
            String key representation of the state.
        """
        return "_".join(str(s) for s in state)

    def _get_q_values(self, state: tuple[int, ...]) -> np.ndarray:
        """Helper to retrieve or initialize action Q-values for a given state.

        Parameters
        ----------
        state : tuple[int, ...]
            6-element or 7-element state tuple.

        Returns
        -------
        np.ndarray
            1D array of shape (3,) representing Q-values for each action.
        """
        key = self._state_to_key(state)
        if key not in self.q_table:
            self.q_table[key] = np.zeros(3, dtype=np.float64)
        return self.q_table[key]

    def update_volatility(self, current_return: float) -> None:
        """Appends the latest asset return to the rolling history window (`returns_history`).

        Maintains a rolling window with a maximum capacity of 10 return items.

        Parameters
        ----------
        current_return : float
            The observed price return from the latest step.
        """
        self.returns_history.append(float(current_return))
        if len(self.returns_history) > 10:
            self.returns_history = self.returns_history[-10:]

    def choose_action(self, state: tuple[int, ...]) -> int:
        """Selects an action using an epsilon-greedy policy with dynamic EV threshold filtering.

        If exploring, returns a uniformly random action and updates `current_position`.
        If exploiting, computes the rolling return volatility across `returns_history`
        (or `0.0` if fewer than 5 elements exist) and scales the EV threshold:
            `dynamic_ev = ev_threshold * (1.0 + vol_sensitivity * volatility)`

        Compares the maximum Q-value (`Q_max`) against the Q-value of `current_position`
        (`Q_current`). Only updates `current_position` and returns `best_action` if
        `(Q_max - Q_current) > dynamic_ev`. Otherwise, maintains `current_position`.

        Parameters
        ----------
        state : tuple[int, ...]
            State tuple.

        Returns
        -------
        int
            Selected action: 0 (Short), 1 (Flat), or 2 (Long).

        Raises
        ------
        ValueError
            If `state` is not a valid state tuple.
        """
        if not isinstance(state, tuple) or len(state) not in (6, 7):
            raise ValueError(
                f"state must be a 6 or 7-element tuple, got {state}."
            )

        if np.random.random() < self.epsilon:
            action = int(np.random.randint(0, 3))
            self.current_position = action
            return action

        # 1. Calculate rolling volatility
        if len(self.returns_history) < 5:
            volatility: float = 0.0
        else:
            volatility = float(np.std(self.returns_history))

        # 2. Compute dynamic_ev
        dynamic_ev: float = float(
            self.ev_threshold * (1.0 + self.vol_sensitivity * volatility)
        )

        # Get Q-values for the current state
        q_values = self._get_q_values(state)

        # 3. If exploiting, identify the action with the maximum Q-value for the current state
        best_action = int(np.argmax(q_values))
        q_max = float(q_values[best_action])

        # 4. Compare Q_max of the new action against Q_current of self.current_position
        q_current = float(q_values[self.current_position])

        # 5. If (Q_max - Q_current) > dynamic_ev, update self.current_position to the new action and return it
        if (q_max - q_current) > dynamic_ev:
            self.current_position = best_action
            return best_action

        # 6. Otherwise, maintain and return self.current_position
        return self.current_position

    def learn(
        self,
        state: tuple[int, ...],
        action: int,
        reward: float,
        next_state: tuple[int, ...],
    ) -> None:
        """Updates the Q-table using the standard Temporal Difference (TD) learning rule.

        Q(s, a) <- Q(s, a) + alpha * [reward + gamma * max_a' Q(s', a') - Q(s, a)]

        Parameters
        ----------
        state : tuple[int, ...]
            Current state tuple.
        action : int
            Action executed in [0, 2].
        reward : float
            Observed reward signal.
        next_state : tuple[int, ...]
            Resulting state tuple.

        Raises
        ------
        ValueError
            If state, action, or next_state inputs are invalid.
        """
        if not isinstance(state, tuple) or len(state) not in (6, 7):
            raise ValueError(f"state must be a 6 or 7-element tuple, got {state}.")
        if not (0 <= action < 3):
            raise ValueError(f"action must be in [0, 2], got {action}.")
        if not isinstance(next_state, tuple) or len(next_state) not in (6, 7):
            raise ValueError(f"next_state must be a 6 or 7-element tuple, got {next_state}.")

        q_values = self._get_q_values(state)
        next_q_values = self._get_q_values(next_state)

        current_q = q_values[action]
        max_next_q = np.max(next_q_values)
        td_target = float(reward) + self.gamma * max_next_q
        td_error = td_target - current_q

        q_values[action] += self.alpha * td_error

    def decay_epsilon(self) -> float:
        """Decays exploration probability epsilon multiplicatively toward min_epsilon.

        Returns
        -------
        float
            Updated epsilon value.
        """
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
        return self.epsilon

    def save(self, filepath: str | Path) -> None:
        """Saves the agent's Q-table dictionary to disk using pickle.

        Parameters
        ----------
        filepath : str | Path
            Destination path where the Q-table (`q_table`) should be saved.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.q_table, f)

    def load(self, filepath: str | Path) -> None:
        """Loads a saved Q-table dictionary from disk using pickle.

        Parameters
        ----------
        filepath : str | Path
            Path to the saved Q-table (`.pkl`) file.

        Raises
        ------
        FileNotFoundError
            If the specified checkpoint file does not exist.
        ValueError
            If the loaded object is not a dictionary.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint file not found at: {path}")
        with open(path, "rb") as f:
            data = pickle.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected dictionary Q-table, got {type(data)}.")
        self.q_table = data

    def save_checkpoint(self, filepath: str | Path) -> None:
        """Alias for `save` to persist the Q-table checkpoint to disk."""
        self.save(filepath)

    def load_checkpoint(self, filepath: str | Path) -> None:
        """Alias for `load` to load a Q-table checkpoint from disk."""
        self.load(filepath)


if __name__ == "__main__":
    np.random.seed(42)

    print("=== QLearningAgent Verification ===")
    agent = QLearningAgent(
        alpha=0.1,
        gamma=0.95,
        epsilon=0.5,
        ev_threshold=0.15,
        vol_sensitivity=2.0,
    )
    print(
        f"Initialized Q-Table keys count: {len(agent.q_table)} | "
        f"Initial Position Index: {agent.current_position}"
    )

    # Test 6D state representation
    state = (1, 0, 1, 0, 2, 1)

    # Test action selection (random exploration)
    action = agent.choose_action(state)
    print(
        f"Selected action for state {state}: {action} "
        f"({['Short', 'Flat', 'Long'][action]}) | Current Position: {agent.current_position}"
    )

    # Test dynamic EV threshold filtering in exploitation mode (epsilon=0.0)
    agent.epsilon = 0.0
    agent.current_position = 1  # Flat
    
    # Set Q-values for the state
    q_vals = agent._get_q_values(state)
    q_vals[1] = 1.0   # Q-value for Flat
    q_vals[2] = 1.25  # Q-value for Long (+0.25 improvement)

    # Case 1: Low history count (< 5 items) -> volatility = 0.0 -> dynamic_ev = 0.15
    action_low_hist = agent.choose_action(state)
    print(
        f"Exploitation (<5 returns, dynamic_ev=0.15, improvement=0.25) -> "
        f"Action: {action_low_hist} (expected 2, switched)"
    )

    # Case 2: High volatility across 10 returns -> std ≈ 0.50 -> dynamic_ev = 0.15*(1 + 2*0.5) = 0.30
    agent.current_position = 1  # Reset to Flat
    for r in [0.5, -0.5, 0.5, -0.5, 0.5, -0.5, 0.5, -0.5, 0.5, -0.5]:
        agent.update_volatility(r)
    vol = float(np.std(agent.returns_history))
    dyn_ev = agent.ev_threshold * (1.0 + agent.vol_sensitivity * vol)
    action_high_vol = agent.choose_action(state)
    print(
        f"Exploitation (std={vol:.2f}, dynamic_ev={dyn_ev:.2f}, improvement=0.25) -> "
        f"Action: {action_high_vol} (expected 1, filtered due to high volatility)"
    )

    # Test Q-table update via TD learning
    next_state = (1, 1, 0, 1, 1, 0)
    reward = 2.5

    state_key = agent._state_to_key(state)
    print(f"\nQ-Table row key '{state_key}' before learn: {agent._get_q_values(state)}")
    agent.learn(state=state, action=action_high_vol, reward=reward, next_state=next_state)
    print(f"Q-Table row key '{state_key}' after learn:  {agent._get_q_values(state)}")
    agent.decay_epsilon()
    print(f"Updated epsilon: {agent.epsilon:.4f}")

    # Test error handling on invalid state shape
    try:
        agent.choose_action((1, 0, 1))
    except ValueError as err:
        print(f"\nCaught expected ValueError for short state tuple: {err}")
