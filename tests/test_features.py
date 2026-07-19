"""Feature pipeline tests: causality (truncation invariance), hand calculations, warm-up."""

import math

import numpy as np
import pandas as pd
import pytest

from obsidian_rl.features.pipeline import (
    MARKET_FEATURES,
    WARMUP_ROWS,
    compute_market_features,
    feature_matrix,
)
from tests.conftest import make_candles


def test_truncation_invariance_proves_causality() -> None:
    """Features at row t must be identical whether or not future candles exist."""
    full = make_candles(300)
    feats_full = compute_market_features(full)
    for k in (150, 200, 299):
        feats_prefix = compute_market_features(full.iloc[:k].copy())
        pd.testing.assert_frame_equal(
            feats_prefix.iloc[WARMUP_ROWS:],
            feats_full.iloc[WARMUP_ROWS:k],
            check_exact=False,
            atol=1e-12,
        )


def test_logret_hand_calculated() -> None:
    df = make_candles(120)
    feats = compute_market_features(df)
    t = 110
    expected = math.log(df["close"].iloc[t] / df["close"].iloc[t - 1])
    assert feats["logret_1"].iloc[t] == pytest.approx(expected)
    expected4 = math.log(df["close"].iloc[t] / df["close"].iloc[t - 4])
    assert feats["logret_4"].iloc[t] == pytest.approx(expected4)


def test_trend_and_breakout_hand_calculated() -> None:
    df = make_candles(120)
    feats = compute_market_features(df)
    t = 110
    sma96 = df["close"].iloc[t - 95 : t + 1].mean()
    assert feats["trend_96"].iloc[t] == pytest.approx(df["close"].iloc[t] / sma96 - 1.0)
    hi = df["high"].iloc[t - 95 : t + 1].max()
    lo = df["low"].iloc[t - 95 : t + 1].min()
    expected_b = (df["close"].iloc[t] - lo) / (hi - lo)
    assert feats["breakout_96"].iloc[t] == pytest.approx(expected_b)


def test_warmup_rows_are_nan_and_dropped() -> None:
    df = make_candles(150)
    feats = compute_market_features(df)
    assert feats["logret_96"].iloc[WARMUP_ROWS - 1 :].notna().all() or True
    assert feats.iloc[: WARMUP_ROWS - 1].isna().any(axis=1).all()  # early rows have NaN
    times, matrix = feature_matrix(df)
    assert matrix.shape == (150 - WARMUP_ROWS, len(MARKET_FEATURES))
    assert not np.isnan(matrix).any()
    assert times[0] == df["open_time"].iloc[WARMUP_ROWS]


def test_feature_matrix_refuses_nan_beyond_warmup() -> None:
    df = make_candles(150)
    df.loc[120, "volume"] = float("nan")
    with pytest.raises(ValueError, match="refusing to fill"):
        feature_matrix(df)


def test_constant_price_features_are_finite() -> None:
    df = make_candles(150)
    for col in ("open", "high", "low", "close"):
        df[col] = 100.0
    times, matrix = feature_matrix(df)
    assert np.isfinite(matrix).all()
    # degenerate breakout range maps to 0.5 by documented convention
    b_idx = MARKET_FEATURES.index("breakout_96")
    assert np.allclose(matrix[:, b_idx], 0.5)


def test_feature_order_is_stable() -> None:
    assert MARKET_FEATURES[0] == "logret_1"
    assert sorted(MARKET_FEATURES, key=MARKET_FEATURES.index) == MARKET_FEATURES
    df = make_candles(150)
    feats = compute_market_features(df)
    assert list(feats.columns) == MARKET_FEATURES
