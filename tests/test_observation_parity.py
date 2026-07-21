"""Train/live observation parity: identical inputs => identical observation vectors."""

import numpy as np
import pytest

from obsidian_rl.features.observation import (
    OBSERVATION_DIM,
    PortfolioObs,
    build_observation,
    schema_fingerprint,
)
from obsidian_rl.features.pipeline import MARKET_FEATURES, compute_market_features
from tests.conftest import make_candles


def test_identical_inputs_identical_observations() -> None:
    """Simulates the training path and the live path building obs from the same candles."""
    candles = make_candles(200)
    port = PortfolioObs(
        exposure=0.5,
        unrealized_return=0.01,
        time_in_position=0.25,
        recent_turnover=0.8,
        drawdown=0.02,
    )
    # "training" path: precomputed matrix row
    feats_train = compute_market_features(candles).iloc[150].to_numpy(dtype=np.float32)
    obs_train = build_observation(feats_train, port)
    # "live" path: features recomputed from the candle window ending at the same candle
    feats_live = (
        compute_market_features(candles.iloc[:151].copy()).iloc[-1].to_numpy(dtype=np.float32)
    )
    obs_live = build_observation(feats_live, port)
    np.testing.assert_array_equal(obs_train, obs_live)
    assert obs_train.shape == (OBSERVATION_DIM,)
    assert obs_train.dtype == np.float32


def test_non_finite_observation_refused() -> None:
    bad = np.full(len(MARKET_FEATURES), np.nan, dtype=np.float32)
    port = PortfolioObs(0.0, 0.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="non-finite"):
        build_observation(bad, port)


def test_wrong_market_shape_refused() -> None:
    port = PortfolioObs(0.0, 0.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="expected"):
        build_observation(np.zeros(3, dtype=np.float32), port)


def test_schema_fingerprint_stable() -> None:
    fp = schema_fingerprint()
    assert fp["version"] == fp["schema_version"] == "fs-v2"
    assert fp["observation_dim"] == OBSERVATION_DIM == 17
    assert fp["market_features"][0] == "logret_1"
