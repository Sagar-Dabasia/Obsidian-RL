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

FEATURE_SCHEMA_VERSION = "fs-v1"

MARKET_FEATURES: list[str] = [
    "logret_1",
    "logret_4",
    "logret_16",
    "logret_96",
    "vol_16",
    "vol_96",
    "range_1",
    "range_16",
    "vol_z_96",
    "trend_96",
    "sma_ratio_16_96",
    "breakout_96",
]

PORTFOLIO_FEATURES: list[str] = [
    "exposure",
    "unrealized_return",
    "time_in_position",
    "recent_turnover",
    "drawdown",
]

ALL_FEATURES: list[str] = MARKET_FEATURES + PORTFOLIO_FEATURES

#: rows at the start of a series whose features are NaN (longest window + 1 return lag)
WARMUP_ROWS = 96

#: deterministic, documented outlier clip applied to unbounded features
CLIP = 10.0


def compute_market_features(candles: pd.DataFrame) -> pd.DataFrame:
    """Compute the versioned market feature frame, index-aligned with `candles`.

    The first WARMUP_ROWS rows contain NaN by design.
    """
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

    out = out[MARKET_FEATURES]
    # Deterministic outlier clip on unbounded features (documented; causal).
    unbounded = [f for f in MARKET_FEATURES if f != "breakout_96"]
    out[unbounded] = out[unbounded].clip(-CLIP, CLIP)
    return out


def feature_matrix(candles: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return (open_time_ms, features) for all rows past warm-up, as float32.

    Raises if any non-warm-up row still contains NaN (stale/missing data must fail
    explicitly, never be filled).
    """
    feats = compute_market_features(candles)
    trimmed = feats.iloc[WARMUP_ROWS:]
    if trimmed.isna().any().any():
        bad = trimmed.index[trimmed.isna().any(axis=1)][:5].tolist()
        raise ValueError(f"NaN features beyond warm-up at rows {bad}; refusing to fill")
    open_times = candles["open_time"].iloc[WARMUP_ROWS:].to_numpy(dtype=np.int64)
    return open_times, trimmed.to_numpy(dtype=np.float32)
