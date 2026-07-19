"""Gate-composed strategies for ablation: base+gate, and gate-only direct policy."""

import numpy as np

from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.gate.alpha_gate import AlphaGate
from obsidian_rl.strategies.base import Strategy


class GatedStrategy:
    """Clamp a base strategy's proposal to directions the gate permits.

    Gate prediction > +margin: long only. < -margin: short only. Otherwise flat.
    """

    def __init__(self, base: Strategy, gate: AlphaGate, margin: float = 0.0) -> None:
        self.base = base
        self.gate = gate
        self.margin = margin
        self.strategy_id = f"gated({base.strategy_id})-m{margin}"

    def reset(self) -> None:
        self.base.reset()

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        proposal = float(self.base.propose(market_row, portfolio))
        pred = self.gate.predict_row(market_row)
        if pred > self.margin:
            return max(proposal, 0.0)
        if pred < -self.margin:
            return min(proposal, 0.0)
        return 0.0


class GateDirectStrategy:
    """Direct supervised target-position policy: full long/short beyond the margin."""

    def __init__(self, gate: AlphaGate, margin: float = 0.0) -> None:
        self.gate = gate
        self.margin = margin
        self.strategy_id = f"gate-direct-m{margin}"

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        pred = self.gate.predict_row(market_row)
        if pred > self.margin:
            return 1.0
        if pred < -self.margin:
            return -1.0
        return 0.0
