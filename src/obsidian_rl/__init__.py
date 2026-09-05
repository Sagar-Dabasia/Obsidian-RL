"""Obsidian-RL: deep-RL cryptocurrency research and live-paper-trading platform.

Experimental research software. No profit guarantee. Paper execution only.
"""

__version__ = "0.1.0"

# Expose submodules
from obsidian_rl import data, portfolio, engines, signals, strategies, training, evaluation, live, gate, interop, ledger, features, env

__all__ = [
    "data",
    "portfolio",
    "engines",
    "signals",
    "strategies",
    "training",
    "evaluation",
    "live",
    "gate",
    "interop",
    "ledger",
    "features",
    "env",
]