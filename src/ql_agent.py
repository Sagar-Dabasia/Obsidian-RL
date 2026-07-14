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
import numpy as np


class QLearningAgent:
    """Tabular Q-Learning Agent for financial market trading environments.

    Discretizes a rolling window of recent price returns into a binary index
    representing the market state and learns an optimal trading policy over a
    discrete action space using Temporal Difference (TD) Q-learning. Includes
    a dynamic, volatility-adjusted Expected Value (EV) threshold filter to
    eliminate low-margin trades.

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

        # Q-Table initialized to zeros with shape (8, 3):
        # 8 discrete states (2^3 binary lookback returns), 3 discrete actions (0=Short, 1=Flat, 2=Long)
        self.q_table = np.zeros((8, 3), dtype=np.float64)
        self.current_position: int = 1  # 0: Short, 1: Flat, 2: Long
        self.returns_history: list[float] = []

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

    def get_state_index(self, price_history: list[Any]) -> int:
        """Computes a discrete state index (0 to 7) from recent price history.

        Calculates 3 sequential returns from the last 4 prices in `price_history`,
        converts each return sign (positive=1, non-positive=0) to a binary bit,
        and packs the 3 bits into a base-2 integer index.

        Parameters
        ----------
        price_history : list
            Sequence containing historical prices. Must have length >= 4.

        Returns
        -------
        int
            Integer state index in the range [0, 7].

        Raises
        ------
        ValueError
            If `price_history` contains fewer than 4 elements or invalid values.
        """
        try:
            if len(price_history) < 4:
                raise ValueError(
                    f"price_history must contain at least 4 prices to compute 3 sequential returns, got {len(price_history)}."
                )
            window = [float(p) for p in price_history[-4:]]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "price_history must be a sequence of at least 4 numerical prices."
            ) from exc

        returns = [window[i] - window[i - 1] for i in range(1, 4)]
        bits = [1 if r > 0.0 else 0 for r in returns]
        state_index = (bits[0] << 2) | (bits[1] << 1) | bits[2]
        return state_index

    def choose_action(self, state_index: int) -> int:
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
        state_index : int
            Discrete state index in the range [0, 7].

        Returns
        -------
        int
            Selected action: 0 (Short), 1 (Flat), or 2 (Long).

        Raises
        ------
        ValueError
            If `state_index` is outside valid bounds [0, 7].
        """
        if not (0 <= state_index < self.q_table.shape[0]):
            raise ValueError(
                f"state_index must be an integer in [0, 7], got {state_index}."
            )

        if np.random.random() < self.epsilon:
            action = int(np.random.randint(0, self.q_table.shape[1]))
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

        # 3. If exploiting, identify the action with the maximum Q-value for the current state
        best_action = int(np.argmax(self.q_table[state_index]))
        q_max = float(self.q_table[state_index, best_action])

        # 4. Compare Q_max of the new action against Q_current of self.current_position
        q_current = float(self.q_table[state_index, self.current_position])

        # 5. If (Q_max - Q_current) > dynamic_ev, update self.current_position to the new action and return it
        if (q_max - q_current) > dynamic_ev:
            self.current_position = best_action
            return best_action

        # 6. Otherwise, maintain and return self.current_position
        return self.current_position

    def learn(
        self, state: int, action: int, reward: float, next_state: int
    ) -> None:
        """Updates the Q-table using the standard Temporal Difference (TD) learning rule.

        Q(s, a) <- Q(s, a) + alpha * [reward + gamma * max_a' Q(s', a') - Q(s, a)]

        Parameters
        ----------
        state : int
            Current state index in [0, 7].
        action : int
            Action executed in [0, 2].
        reward : float
            Observed reward signal.
        next_state : int
            Resulting state index in [0, 7].

        Raises
        ------
        ValueError
            If state, action, or next_state indices are out of bounds.
        """
        if not (0 <= state < self.q_table.shape[0]):
            raise ValueError(f"state must be in [0, 7], got {state}.")
        if not (0 <= action < self.q_table.shape[1]):
            raise ValueError(f"action must be in [0, 2], got {action}.")
        if not (0 <= next_state < self.q_table.shape[0]):
            raise ValueError(f"next_state must be in [0, 7], got {next_state}.")

        current_q = self.q_table[state, action]
        max_next_q = np.max(self.q_table[next_state])
        td_target = float(reward) + self.gamma * max_next_q
        td_error = td_target - current_q

        self.q_table[state, action] += self.alpha * td_error

    def decay_epsilon(self) -> float:
        """Decays exploration probability epsilon multiplicatively toward min_epsilon.

        Returns
        -------
        float
            Updated epsilon value.
        """
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
        return self.epsilon


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
        f"Initialized Q-Table shape: {agent.q_table.shape} | "
        f"Initial Position Index: {agent.current_position}"
    )

    # Test state discretization
    prices = [100.0, 101.5, 99.0, 102.0]
    state = agent.get_state_index(prices)
    print(f"Price history: {prices} -> Computed State Index: {state} (expected 5)")

    # Test action selection (random exploration)
    action = agent.choose_action(state)
    print(
        f"Selected action for state {state}: {action} "
        f"({['Short', 'Flat', 'Long'][action]}) | Current Position: {agent.current_position}"
    )

    # Test dynamic EV threshold filtering in exploitation mode (epsilon=0.0)
    agent.epsilon = 0.0
    agent.current_position = 1  # Flat
    agent.q_table[state, 1] = 1.0   # Q-value for Flat
    agent.q_table[state, 2] = 1.25  # Q-value for Long (+0.25 improvement)

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
    next_prices = [101.5, 99.0, 102.0, 103.0]
    next_state = agent.get_state_index(next_prices)
    reward = 2.5

    print(f"\nQ-Table row {state} before learn: {agent.q_table[state]}")
    agent.learn(state=state, action=action_high_vol, reward=reward, next_state=next_state)
    print(f"Q-Table row {state} after learn:  {agent.q_table[state]}")
    agent.decay_epsilon()
    print(f"Updated epsilon: {agent.epsilon:.4f}")

    # Test error handling on insufficient price history
    try:
        agent.get_state_index([100.0, 101.0, 102.0])
    except ValueError as err:
        print(f"\nCaught expected ValueError for short list: {err}")
