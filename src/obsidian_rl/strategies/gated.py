"""Gate-composed strategies for ablation: base+gate, and gate-only direct policy.

Gate predictions represent signed directional net edge:
  > +margin -> long permitted
  < -margin -> short permitted
  otherwise -> flat (no position)

Margin must be non-negative. Cost is NOT subtracted again (already encoded in the label).
"""

import math

import numpy as np

from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.gate.alpha_gate import AlphaGate
from obsidian_rl.strategies.base import Strategy


class GatedStrategy:
    """Clamp a base strategy's proposal to directions the gate permits.

    Gate prediction > +margin: long only. < -margin: short only. Otherwise flat.
    """

    def __init__(self, base: Strategy, gate: AlphaGate, margin: float = 0.0) -> None:
        if (
            isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(margin)
            or margin < 0
        ):
            raise ValueError("margin must be a finite non-bool numeric >= 0")
        self.base = base
        self.gate = gate
        self.margin = margin
        self.strategy_id = f"gated({base.strategy_id})-m{margin}"

    def reset(self) -> None:
        self.base.reset()

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        proposal = float(self.base.propose(market_row, portfolio))
        direction = self.gate.decide(market_row, self.margin)
        if direction > 0:
            return max(proposal, 0.0)
        if direction < 0:
            return min(proposal, 0.0)
        return 0.0


class GateDirectStrategy:
    """Direct supervised target-position policy: full long/short beyond the margin."""

    def __init__(self, gate: AlphaGate, margin: float = 0.0) -> None:
        if (
            isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(margin)
            or margin < 0
        ):
            raise ValueError("margin must be a finite non-bool numeric >= 0")
        self.gate = gate
        self.margin = margin
        self.strategy_id = f"gate-direct-m{margin}"

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        direction = self.gate.decide(market_row, self.margin)
        if direction > 0:
            return 1.0
        if direction < 0:
            return -1.0
        return 0.0
