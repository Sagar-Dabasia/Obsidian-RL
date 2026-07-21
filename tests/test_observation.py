"""Observation and portfolio feature schema contract tests."""

import numpy as np
import pytest

from obsidian_rl.features.observation import (
    OBSERVATION_DIM,
    PortfolioObs,
    build_observation,
    validate_portfolio_obs,
)
from obsidian_rl.features.schema import MARKET_FEATURES, PORTFOLIO_BOUNDS, schema_fingerprint


def test_portfolio_obs_validation_and_bounds() -> None:
    valid = PortfolioObs(
        exposure=1.0,
        unrealized_return=0.05,
        time_in_position=0.5,
        recent_turnover=2.0,
        drawdown=0.1,
    )
    validate_portfolio_obs(valid)  # must not raise

    # Reject bool
    with pytest.raises(ValueError, match="numeric \\(not bool\\)"):
        validate_portfolio_obs(
            PortfolioObs(
                exposure=True,  # type: ignore[arg-type]
                unrealized_return=0.0,
                time_in_position=0.0,
                recent_turnover=0.0,
                drawdown=0.0,
            )
        )

    # Reject non-finite
    with pytest.raises(ValueError, match="finite"):
        validate_portfolio_obs(
            PortfolioObs(
                exposure=float("nan"),
                unrealized_return=0.0,
                time_in_position=0.0,
                recent_turnover=0.0,
                drawdown=0.0,
            )
        )

    # Reject out-of-bounds exposure (> 3.0)
    with pytest.raises(ValueError, match="out of bounds"):
        validate_portfolio_obs(
            PortfolioObs(
                exposure=3.5,
                unrealized_return=0.0,
                time_in_position=0.0,
                recent_turnover=0.0,
                drawdown=0.0,
            )
        )

    # Reject out-of-bounds drawdown (< 0.0)
    with pytest.raises(ValueError, match="out of bounds"):
        validate_portfolio_obs(
            PortfolioObs(
                exposure=0.0,
                unrealized_return=0.0,
                time_in_position=0.0,
                recent_turnover=0.0,
                drawdown=-0.1,
            )
        )


def test_build_observation_contract() -> None:
    market_row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    portfolio = PortfolioObs(0.5, 0.01, 0.2, 1.0, 0.05)

    obs = build_observation(market_row, portfolio)
    assert obs.shape == (OBSERVATION_DIM,)
    assert obs.dtype == np.float32
    assert obs.flags["C_CONTIGUOUS"]
    assert np.isfinite(obs).all()

    # Exact market followed by portfolio order
    assert np.allclose(obs[: len(MARKET_FEATURES)], market_row)
    assert np.allclose(obs[len(MARKET_FEATURES) :], portfolio.to_array())


def test_build_observation_rejects_malformed_market_row() -> None:
    portfolio = PortfolioObs(0.0, 0.0, 0.0, 0.0, 0.0)

    # Wrong dimension
    with pytest.raises(ValueError, match="market feature row has shape"):
        build_observation(np.zeros((3, 4), dtype=np.float32), portfolio)

    # Wrong length
    with pytest.raises(ValueError, match="market feature row has shape"):
        build_observation(np.zeros(len(MARKET_FEATURES) - 1, dtype=np.float32), portfolio)

    # Non-finite values inside market row
    bad_market = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    bad_market[0] = float("nan")
    with pytest.raises(ValueError, match="contains non-finite values"):
        build_observation(bad_market, portfolio)


def test_schema_fingerprint_contains_descriptor_and_hash() -> None:
    fp = schema_fingerprint()
    assert "schema_version" in fp
    assert "schema_sha256" in fp
    assert "market_features" in fp
    assert "portfolio_features" in fp
    assert fp["portfolio_bounds"] == PORTFOLIO_BOUNDS
