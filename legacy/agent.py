"""Agent Module for Institutional Reinforcement Learning Trading Systems.

Re-exports QLearningAgent to ensure compatibility across module namespaces.
"""

from __future__ import annotations

from src.ql_agent import QLearningAgent

__all__ = ["QLearningAgent"]
