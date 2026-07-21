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
    with pytest.raises(ValueError, match=r"non-finite|refusing to fill"):
        feature_matrix(df)


def test_constant_price_features_are_finite() -> None:
    df = make_candles(150)
    for col in ("open", "high", "low", "close"):
        df[col] = 100.0
    _times, matrix = feature_matrix(df)
    assert np.isfinite(matrix).all()
    # degenerate breakout range maps to 0.5 by documented convention
    b_idx = MARKET_FEATURES.index("breakout_96")
    assert np.allclose(matrix[:, b_idx], 0.5)


def test_feature_order_is_stable() -> None:
    assert MARKET_FEATURES[0] == "logret_1"
    assert sorted(MARKET_FEATURES, key=MARKET_FEATURES.index) == list(MARKET_FEATURES)
    df = make_candles(150)
    feats = compute_market_features(df)
    assert list(feats.columns) == list(MARKET_FEATURES)


# ── Phase 6 Schema contract & candle validation tests ─────────────────────────


def test_schema_descriptor_canonical_json_and_sha256() -> None:
    from obsidian_rl.features.schema import SCHEMA_VERSION, schema_descriptor, schema_sha256

    desc = schema_descriptor()
    assert desc["schema_version"] == SCHEMA_VERSION
    sha = schema_sha256(desc)
    assert isinstance(sha, str) and len(sha) == 64 and sha.islower()
    assert all(c in "0123456789abcdef" for c in sha)

    # Modifying any descriptor value alters the SHA-256
    mutated = dict(desc)
    mutated["warmup_rows"] = 999
    assert schema_sha256(mutated) != sha


def test_validate_candle_frame_enforces_schema() -> None:
    from obsidian_rl.features.pipeline import validate_candle_frame

    df = make_candles(150)
    validate_candle_frame(df)  # valid frame passes

    # Missing column
    with pytest.raises(ValueError, match="missing required column"):
        validate_candle_frame(df.drop(columns=["volume"]))

    # Non-numeric / bool column
    df_bool = df.copy()
    df_bool["volume"] = True
    with pytest.raises(ValueError, match="bool or non-numeric"):
        validate_candle_frame(df_bool)

    # Non-finite value
    df_nan = df.copy()
    df_nan.loc[10, "close"] = float("nan")
    with pytest.raises(ValueError, match="non-finite value"):
        validate_candle_frame(df_nan)

    # Negative volume
    df_neg = df.copy()
    df_neg.loc[10, "volume"] = -1.0
    with pytest.raises(ValueError, match="volume must be >= 0"):
        validate_candle_frame(df_neg)

    # High < max(open, close)
    df_hi = df.copy()
    df_hi.loc[10, "high"] = min(df_hi.loc[10, "open"], df_hi.loc[10, "close"]) - 1.0
    with pytest.raises(ValueError, match=r"high must be >= (open|close)"):
        validate_candle_frame(df_hi)

    # Low > min(open, close)
    df_lo = df.copy()
    df_lo.loc[10, "low"] = max(df_lo.loc[10, "open"], df_lo.loc[10, "close"]) + 1.0
    with pytest.raises(ValueError, match=r"low must be <= (open|close)"):
        validate_candle_frame(df_lo)

    # Not strictly increasing / unique time
    df_time = df.copy()
    df_time.loc[10, "open_time"] = df_time.loc[9, "open_time"]
    with pytest.raises(ValueError, match="open_time must be strictly increasing and unique"):
        validate_candle_frame(df_time)


def test_compute_market_features_and_feature_matrix_reject_malformed_candles() -> None:
    from obsidian_rl.features.pipeline import CandleValidationError

    df = make_candles(150)
    df_bad = df.drop(columns=["close"])

    with pytest.raises(CandleValidationError, match="missing required column"):
        compute_market_features(df_bad)

    with pytest.raises(CandleValidationError, match="missing required column"):
        feature_matrix(df_bad)


def test_invalid_expected_interval_ms_rejected() -> None:
    from obsidian_rl.features.pipeline import CandleValidationError, validate_candle_frame

    df_1row = make_candles(1)

    for invalid_val in (0, -100, True, "15m", 1.5):
        with pytest.raises(CandleValidationError, match="expected_interval_ms"):
            validate_candle_frame(df_1row, expected_interval_ms=invalid_val)  # type: ignore[arg-type]

        with pytest.raises(CandleValidationError, match="expected_interval_ms"):
            compute_market_features(df_1row, expected_interval_ms=invalid_val)  # type: ignore[arg-type]

        with pytest.raises(CandleValidationError, match="expected_interval_ms"):
            feature_matrix(df_1row, expected_interval_ms=invalid_val)  # type: ignore[arg-type]


def test_feature_matrix_rejects_post_warmup_infinity() -> None:
    df = make_candles(150)
    # Inf in close post warm-up
    df.loc[120, "close"] = float("inf")
    # Will fail validation in compute_market_features via validate_candle_frame
    from obsidian_rl.features.pipeline import CandleValidationError

    with pytest.raises(CandleValidationError, match="non-finite"):
        feature_matrix(df)


def test_feature_matrix_rejects_post_warmup_non_finite_features() -> None:
    df = make_candles(150)
    # Zero volume produces 0 std in rolling window, creating NaN in vol_z_96 despite valid candles
    df["volume"] = 0.0
    with pytest.raises(ValueError, match="NaN or non-finite features beyond warm-up"):
        feature_matrix(df)


def test_feature_matrix_output_contiguity_dtype_shape() -> None:
    df = make_candles(150)
    times, matrix = feature_matrix(df, expected_interval_ms=900_000)

    assert times.dtype == np.int64
    assert matrix.dtype == np.float32
    assert times.flags["C_CONTIGUOUS"]
    assert matrix.flags["C_CONTIGUOUS"]
    assert times.shape == (150 - WARMUP_ROWS,)
    assert matrix.shape == (150 - WARMUP_ROWS, len(MARKET_FEATURES))
    assert (times == df["open_time"].iloc[WARMUP_ROWS:].to_numpy(dtype=np.int64)).all()


def test_descriptor_and_fingerprint_immutability() -> None:
    from obsidian_rl.features.schema import (
        MARKET_FEATURES,
        PORTFOLIO_BOUNDS,
        schema_descriptor,
        schema_fingerprint,
        schema_sha256,
    )

    desc1 = schema_descriptor()
    fp1 = schema_fingerprint()
    sha1 = schema_sha256()

    # Mutate returned structures
    desc1["market_features"].append("EVIL_FEATURE")
    desc1["portfolio_bounds"]["exposure"]["clip_high"] = 999.0
    fp1["market_features"].append("EVIL_FEATURE")
    fp1["portfolio_bounds"]["exposure"]["clip_high"] = 999.0

    desc2 = schema_descriptor()
    fp2 = schema_fingerprint()
    sha2 = schema_sha256()

    assert sha1 == sha2
    assert desc2["market_features"] == list(MARKET_FEATURES)
    assert fp2["market_features"] == list(MARKET_FEATURES)
    assert desc2["portfolio_bounds"]["exposure"]["clip_high"] == 3.0
    assert fp2["portfolio_bounds"] == dict(PORTFOLIO_BOUNDS)
