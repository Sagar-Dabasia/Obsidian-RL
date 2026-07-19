"""Strategy interface: propose a target exposure from the shared observation inputs."""

from typing import Protocol

import numpy as np

from obsidian_rl.features.observation import PortfolioObs


class Strategy(Protocol):
    strategy_id: str

    def reset(self) -> None: ...

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        """Return a target exposure (will be snapped/clamped by the runner)."""
        ...


def feature(market_row: np.ndarray, name: str) -> float:
    from obsidian_rl.features.pipeline import MARKET_FEATURES

    return float(market_row[MARKET_FEATURES.index(name)])
