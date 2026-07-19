"""Observation assembly shared by the Gymnasium env, replay, and live paper trading.

One function builds the policy observation from (market features row, portfolio scalars),
guaranteeing train/live parity by construction.
"""

from dataclasses import dataclass

import numpy as np

from obsidian_rl.features.pipeline import (
    ALL_FEATURES,
    FEATURE_SCHEMA_VERSION,
    MARKET_FEATURES,
    PORTFOLIO_FEATURES,
)

OBSERVATION_DIM = len(ALL_FEATURES)


@dataclass(frozen=True)
class PortfolioObs:
    """Portfolio-state inputs to the observation (all scale-free)."""

    exposure: float  # signed, in [-1, 1] under current limits
    unrealized_return: float  # unrealized P&L / net equity
    time_in_position: float  # steps in current position / 96, capped at 1
    recent_turnover: float  # notional traded over last 96 steps / net equity
    drawdown: float  # 1 - equity/peak, in [0, 1]

    def to_array(self) -> np.ndarray:
        return np.array(
            [
                self.exposure,
                self.unrealized_return,
                self.time_in_position,
                self.recent_turnover,
                self.drawdown,
            ],
            dtype=np.float32,
        )


def build_observation(market_row: np.ndarray, portfolio: PortfolioObs) -> np.ndarray:
    """Assemble the versioned observation vector (float32, OBSERVATION_DIM)."""
    market = np.asarray(market_row, dtype=np.float32)
    if market.shape != (len(MARKET_FEATURES),):
        raise ValueError(
            f"market feature row has shape {market.shape}, expected ({len(MARKET_FEATURES)},)"
        )
    obs = np.concatenate([market, portfolio.to_array()])
    if not np.isfinite(obs).all():
        raise ValueError("observation contains non-finite values; refusing to emit")
    return obs


def schema_fingerprint() -> dict[str, object]:
    """Versioned schema descriptor stored with every trained model."""
    return {
        "version": FEATURE_SCHEMA_VERSION,
        "market_features": list(MARKET_FEATURES),
        "portfolio_features": list(PORTFOLIO_FEATURES),
        "observation_dim": OBSERVATION_DIM,
        "dtype": "float32",
    }
