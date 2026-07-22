"""Observation assembly shared by the Gymnasium env, replay, and live paper trading.

One function builds the policy observation from (market features row, portfolio scalars),
guaranteeing train/live parity by construction.
"""

import math
from dataclasses import dataclass

import numpy as np

from obsidian_rl.features.schema import (
    MARKET_FEATURES,
    OBSERVATION_DIM,
    PORTFOLIO_BOUNDS,
    PORTFOLIO_FEATURES,
    schema_fingerprint,
    schema_sha256,
)

# Re-export for callers that imported from observation previously
__all__ = [
    "OBSERVATION_DIM",
    "PortfolioObs",
    "validate_portfolio_obs",
    "build_observation",
    "schema_fingerprint",
    "schema_sha256",
]


@dataclass(frozen=True)
class PortfolioObs:
    """Portfolio-state inputs to the observation (all scale-free).

    All fields must be numeric (not bool), finite, and within their documented bounds.
    Use validate_portfolio_obs() or build_observation() to enforce this contract.
    """

    exposure: float  # signed, clipped to [-3, 3]
    unrealized_return: float  # unrealized P&L / net equity, clipped to [-3, 3]
    time_in_position: float  # steps in current position / 96, in [0, 1]
    recent_turnover: float  # notional traded over last 96 steps / net equity, [0, 10]
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


def validate_portfolio_obs(portfolio: PortfolioObs) -> None:
    """Raise ValueError if any PortfolioObs field is invalid.

    Checks:
      - numeric, not bool
      - finite
      - within documented bounds from PORTFOLIO_BOUNDS
    """
    for field_name in PORTFOLIO_FEATURES:
        value = getattr(portfolio, field_name)
        bounds = PORTFOLIO_BOUNDS[field_name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"PortfolioObs.{field_name} must be numeric (not bool), got {type(value).__name__}"
            )
        if not math.isfinite(value):
            raise ValueError(
                f"PortfolioObs.{field_name} must be finite, got {value!r}"
            )
        lo, hi = bounds["clip_low"], bounds["clip_high"]
        if value < lo or value > hi:
            raise ValueError(
                f"PortfolioObs.{field_name}={value!r} out of bounds [{lo}, {hi}]"
            )


def build_observation(market_row: np.ndarray, portfolio: PortfolioObs) -> np.ndarray:
    """Assemble the versioned observation vector (float32, OBSERVATION_DIM).

    Returns a 1-dimensional contiguous float32 array of exactly OBSERVATION_DIM values,
    in market-then-portfolio order, with no non-finite values.

    Raises ValueError on shape, dtype, non-finite, or portfolio bound violations.
    """
    market = np.asarray(market_row, dtype=np.float32)
    if market.ndim != 1 or market.shape[0] != len(MARKET_FEATURES):
        raise ValueError(
            f"market feature row has shape {market.shape}, expected ({len(MARKET_FEATURES)},)"
        )
    validate_portfolio_obs(portfolio)
    obs = np.ascontiguousarray(
        np.concatenate([market, portfolio.to_array()]), dtype=np.float32
    )
    if obs.shape != (OBSERVATION_DIM,):
        raise ValueError(
            f"observation shape {obs.shape} != ({OBSERVATION_DIM},)"
        )
    if not np.isfinite(obs).all():
        raise ValueError("observation contains non-finite values; refusing to emit")
    return obs
