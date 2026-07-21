"""Market feature computation. Used identically by training, evaluation, replay, and live.

Causality contract: every value at row t derives exclusively from candles at rows <= t
(rolling windows ending at t). This is enforced by truncation-invariance tests.

All features are scale-free (returns, ratios, z-scores), so no preprocessing is fitted.
If fitted preprocessing is ever added, it must be fitted on training periods only and
versioned with the schema. Warm-up rows are explicit NaN; consumers must drop or refuse
them — silently filling is forbidden.
"""

import numpy as np
import pandas as pd

from obsidian_rl.features.schema import (
    ALL_FEATURES,
    CLIP,
    CLIPPED_FEATURES,
    MARKET_FEATURES,
    OBSERVATION_DIM,
    PORTFOLIO_FEATURES,
    REQUIRED_CANDLE_COLUMNS,
    SCHEMA_VERSION,
    WARMUP_ROWS,
    schema_fingerprint,
    schema_sha256,
)

# Re-export for callers that imported from pipeline previously
FEATURE_SCHEMA_VERSION = SCHEMA_VERSION

__all__ = [
    "ALL_FEATURES",
    "CLIP",
    "FEATURE_SCHEMA_VERSION",
    "MARKET_FEATURES",
    "OBSERVATION_DIM",
    "PORTFOLIO_FEATURES",
    "WARMUP_ROWS",
    "compute_market_features",
    "feature_matrix",
    "schema_fingerprint",
    "schema_sha256",
    "validate_candle_frame",
]


class CandleValidationError(ValueError):
    """Raised when a candle DataFrame does not satisfy the schema contract."""


def validate_candle_frame(
    candles: pd.DataFrame,
    *,
    expected_interval_ms: int | None = None,
) -> None:
    """Validate a candle DataFrame against the schema contract.

    Raises CandleValidationError for any violation.
    Does NOT mutate the caller's frame.

    Checks (in order):
      - expected_interval_ms if provided: int > 0, not bool
      - DataFrame input
      - Required columns present exactly once
      - Non-empty
      - open_time: int64, not bool, unique, strictly increasing
      - close_time: int64, not bool, >= open_time
      - open/high/low/close: finite and strictly positive
      - volume: finite and >= 0
      - high >= max(open, close)
      - low <= min(open, close)
      - optional interval continuity (open_time diffs == expected_interval_ms)
    """
    if expected_interval_ms is not None:
        if isinstance(expected_interval_ms, bool) or not isinstance(expected_interval_ms, int):
            raise CandleValidationError(
                f"expected_interval_ms must be an integer, "
                f"got {type(expected_interval_ms).__name__}"
            )
        if expected_interval_ms <= 0:
            raise CandleValidationError(
                f"expected_interval_ms must be > 0, got {expected_interval_ms}"
            )

    if not isinstance(candles, pd.DataFrame):
        raise CandleValidationError(f"candles must be a DataFrame, got {type(candles).__name__}")
    # Required columns — exactly once each
    for col in REQUIRED_CANDLE_COLUMNS:
        if col not in candles.columns:
            raise CandleValidationError(f"candles missing required column {col!r}")
        if (candles.columns == col).sum() > 1:
            raise CandleValidationError(f"candles has duplicate column {col!r}")
    if len(candles) == 0:
        raise CandleValidationError("candles DataFrame is empty")

    ot = candles["open_time"]
    ct = candles["close_time"]
    o = candles["open"]
    h = candles["high"]
    lo = candles["low"]
    c = candles["close"]
    v = candles["volume"]

    # open_time: integer type, not bool
    if ot.dtype.kind not in ("i", "u"):
        raise CandleValidationError(f"open_time must be integer dtype, got {ot.dtype}")
    if ot.isna().any():
        raise CandleValidationError("open_time contains NaN")
    ot_vals = ot.to_numpy(dtype=np.int64)
    if len(ot_vals) > 1 and not np.all(np.diff(ot_vals) > 0):
        raise CandleValidationError("open_time must be strictly increasing and unique")

    # close_time: integer type
    if ct.dtype.kind not in ("i", "u"):
        raise CandleValidationError(f"close_time must be integer dtype, got {ct.dtype}")
    if ct.isna().any():
        raise CandleValidationError("close_time contains NaN")
    ct_vals = ct.to_numpy(dtype=np.int64)
    if not np.all(ct_vals >= ot_vals):
        raise CandleValidationError("close_time must be >= open_time in every row")

    # OHLCV: numeric dtype (not bool), finite, positive prices, non-negative volume
    for name, series in [("open", o), ("high", h), ("low", lo), ("close", c), ("volume", v)]:
        if series.dtype.kind == "b" or series.dtype.kind not in ("f", "i", "u"):
            raise CandleValidationError(
                f"{name} column must be numeric float/int "
                f"(not bool or non-numeric), got {series.dtype}"
            )
    for name, series in [("open", o), ("high", h), ("low", lo), ("close", c)]:
        arr = series.to_numpy(dtype=np.float64)
        if not np.isfinite(arr).all():
            raise CandleValidationError(f"{name} contains non-finite values")
        if not (arr > 0).all():
            raise CandleValidationError(f"{name} must be strictly positive")

    v_arr = v.to_numpy(dtype=np.float64)
    if not np.isfinite(v_arr).all():
        raise CandleValidationError("volume contains non-finite values")
    if not (v_arr >= 0).all():
        raise CandleValidationError("volume must be >= 0")

    # OHLC consistency
    h_arr = h.to_numpy(dtype=np.float64)
    lo_arr = lo.to_numpy(dtype=np.float64)
    o_arr = o.to_numpy(dtype=np.float64)
    c_arr = c.to_numpy(dtype=np.float64)

    if not np.all(h_arr >= o_arr):
        raise CandleValidationError("high must be >= open in every row")
    if not np.all(h_arr >= c_arr):
        raise CandleValidationError("high must be >= close in every row")
    if not np.all(lo_arr <= o_arr):
        raise CandleValidationError("low must be <= open in every row")
    if not np.all(lo_arr <= c_arr):
        raise CandleValidationError("low must be <= close in every row")

    # Optional interval continuity
    if expected_interval_ms is not None and len(ot_vals) > 1:
        diffs = np.diff(ot_vals)
        if not np.all(diffs == expected_interval_ms):
            bad_idx = int(np.argmax(diffs != expected_interval_ms))
            raise CandleValidationError(
                f"open_time interval gap at index {bad_idx}: "
                f"expected {expected_interval_ms} ms, got {int(diffs[bad_idx])} ms"
            )


def compute_market_features(
    candles: pd.DataFrame,
    *,
    expected_interval_ms: int | None = None,
) -> pd.DataFrame:
    """Compute the versioned market feature frame, index-aligned with `candles`.

    The first WARMUP_ROWS rows contain NaN by design.
    Output index exactly matches input; columns exactly equal MARKET_FEATURES in order.
    """
    validate_candle_frame(candles, expected_interval_ms=expected_interval_ms)

    c = candles["close"].astype("float64")
    h = candles["high"].astype("float64")
    lo = candles["low"].astype("float64")
    v = candles["volume"].astype("float64")

    logc = np.log(c)
    logret_1 = logc.diff(1)

    out = pd.DataFrame(index=candles.index)
    out["logret_1"] = logret_1
    out["logret_4"] = logc.diff(4)
    out["logret_16"] = logc.diff(16)
    out["logret_96"] = logc.diff(96)
    out["vol_16"] = logret_1.rolling(16).std()
    out["vol_96"] = logret_1.rolling(96).std()
    out["range_1"] = (h - lo) / c
    out["range_16"] = out["range_1"].rolling(16).mean()

    vol_mean = v.rolling(96).mean()
    vol_std = v.rolling(96).std()
    out["vol_z_96"] = (v - vol_mean) / vol_std.where(vol_std > 0)

    sma_16 = c.rolling(16).mean()
    sma_96 = c.rolling(96).mean()
    out["trend_96"] = (c - sma_96) / sma_96
    out["sma_ratio_16_96"] = sma_16 / sma_96 - 1.0

    hi_96 = h.rolling(96).max()
    lo_96 = lo.rolling(96).min()
    span = hi_96 - lo_96
    out["breakout_96"] = (
        ((c - lo_96) / span.where(span > 0)).fillna(0.5).where(span.notna(), np.nan)
    )

    out = out[list(MARKET_FEATURES)]
    # Deterministic outlier clip on unbounded features (documented; causal).
    out[list(CLIPPED_FEATURES)] = out[list(CLIPPED_FEATURES)].clip(-CLIP, CLIP)
    return out


def feature_matrix(
    candles: pd.DataFrame,
    *,
    expected_interval_ms: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (open_time_ms, features) for all rows past warm-up, as float32.

    Raises if any non-warm-up row still contains NaN or non-finite values (stale/missing
    data must fail explicitly, never be filled).
    """
    feats = compute_market_features(candles, expected_interval_ms=expected_interval_ms)
    trimmed = feats.iloc[WARMUP_ROWS:]
    mat = np.ascontiguousarray(trimmed.to_numpy(dtype=np.float32), dtype=np.float32)
    if not np.isfinite(mat).all():
        raise ValueError("NaN or non-finite features beyond warm-up; refusing to fill")
    open_times = np.ascontiguousarray(
        candles["open_time"].iloc[WARMUP_ROWS:].to_numpy(dtype=np.int64),
        dtype=np.int64,
    )
    return open_times, mat
