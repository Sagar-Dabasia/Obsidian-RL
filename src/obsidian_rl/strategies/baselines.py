"""Deterministic baselines. All consume the same market feature row and portfolio state
as the RL policy — no private data paths. Thresholds are conservative defaults; tuning,
if any, happens on training/validation periods only (never the final test period).
"""

import numpy as np

from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.strategies.base import feature


class AlwaysFlat:
    strategy_id = "always-flat"

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        return 0.0


class BuyAndHold:
    strategy_id = "buy-and-hold"

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        return 1.0


class ThresholdMomentum:
    """Long/short when the 16-candle log return exceeds a threshold; else flat."""

    def __init__(self, threshold: float = 0.005) -> None:
        self.strategy_id = f"threshold-momentum-{threshold}"
        self.threshold = threshold

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        mom = feature(market_row, "logret_16")
        if mom > self.threshold:
            return 1.0
        if mom < -self.threshold:
            return -1.0
        return 0.0


class RegimeFilteredMomentum:
    """The core research-hypothesis baseline: momentum only in a trending regime.

    Regime filter: |trend_96| must exceed `regime_threshold` (price meaningfully away
    from its 24h mean). Direction from the 16/96 SMA ratio. Flat in choppy regimes.
    """

    def __init__(self, regime_threshold: float = 0.01, direction_threshold: float = 0.002) -> None:
        self.strategy_id = f"regime-momentum-{regime_threshold}-{direction_threshold}"
        self.regime_threshold = regime_threshold
        self.direction_threshold = direction_threshold

    def reset(self) -> None:
        return None

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        trend = feature(market_row, "trend_96")
        ratio = feature(market_row, "sma_ratio_16_96")
        if abs(trend) < self.regime_threshold:
            return 0.0
        if ratio > self.direction_threshold:
            return 1.0
        if ratio < -self.direction_threshold:
            return -1.0
        return 0.0


class FixedHolding:
    """Enter on a momentum signal, hold exactly `hold_steps` candles, then go flat."""

    def __init__(self, threshold: float = 0.005, hold_steps: int = 16) -> None:
        self.strategy_id = f"fixed-holding-{threshold}-{hold_steps}"
        self.threshold = threshold
        self.hold_steps = hold_steps
        self._remaining = 0
        self._direction = 0.0

    def reset(self) -> None:
        self._remaining = 0
        self._direction = 0.0

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        if self._remaining > 0:
            self._remaining -= 1
            return self._direction
        mom = feature(market_row, "logret_16")
        if mom > self.threshold:
            self._direction, self._remaining = 1.0, self.hold_steps - 1
            return 1.0
        if mom < -self.threshold:
            self._direction, self._remaining = -1.0, self.hold_steps - 1
            return -1.0
        return 0.0


class CooldownMomentum:
    """Hysteresis policy: enter on momentum, exit only on opposite signal, then cooldown."""

    def __init__(
        self, enter_threshold: float = 0.005, exit_threshold: float = 0.001, cooldown: int = 8
    ) -> None:
        self.strategy_id = f"cooldown-momentum-{enter_threshold}-{exit_threshold}-{cooldown}"
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.cooldown = cooldown
        self._position = 0.0
        self._cooldown_left = 0

    def reset(self) -> None:
        self._position = 0.0
        self._cooldown_left = 0

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        mom = feature(market_row, "logret_16")
        if self._cooldown_left > 0:
            self._cooldown_left -= 1
            return 0.0
        if self._position == 0.0:
            if mom > self.enter_threshold:
                self._position = 1.0
            elif mom < -self.enter_threshold:
                self._position = -1.0
        elif (self._position > 0 and mom < -self.exit_threshold) or (self._position < 0 and mom > self.exit_threshold):
            self._position = 0.0
            self._cooldown_left = self.cooldown
        return self._position


def default_baselines() -> list[object]:
    return [
        AlwaysFlat(),
        BuyAndHold(),
        ThresholdMomentum(),
        RegimeFilteredMomentum(),
        FixedHolding(),
        CooldownMomentum(),
    ]
