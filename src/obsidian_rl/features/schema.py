"""Obsidian-RL versioned feature schema contract.

This module is the single authoritative source of truth for:
  - schema version identifier
  - required candle column names and types
  - ordered market features with formula/semantic identifiers
  - lags and rolling windows for each feature
  - warm-up rows required before any feature is valid
  - clipping constants applied to unbounded features
  - ordered portfolio features with normalization bounds
  - complete observation vector layout (market then portfolio), dtype and dim
  - a canonical JSON serialisation and SHA-256 fingerprint

Any change to values in this file changes the schema SHA-256, invalidating all
legacy model, gate and holdout artifacts and requiring retraining/reevaluation.

Do NOT hash Python source text. The descriptor is an explicit semantic contract
serialised with sorted compact JSON and allow_nan=False.
"""

import copy
import hashlib
import json
from types import MappingProxyType
from typing import Any

# ── Version ───────────────────────────────────────────────────────────────────
SCHEMA_VERSION = "fs-v2"

# ── Candle columns (required, in order) ───────────────────────────────────────
REQUIRED_CANDLE_COLUMNS: list[str] = [
    "open_time",  # int64 milliseconds UTC
    "open",  # float64 positive
    "high",  # float64 >= open and close
    "low",  # float64 <= open and close
    "close",  # float64 positive
    "volume",  # float64 >= 0
    "close_time",  # int64 milliseconds UTC; >= open_time
]

# ── Market features (stable ordered list) ─────────────────────────────────────
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

# Formula/semantic identifier for each feature
MARKET_FEATURE_FORMULAS: MappingProxyType[str, str] = MappingProxyType(
    {
        "logret_1": "log(close[t] / close[t-1])",
        "logret_4": "log(close[t] / close[t-4])",
        "logret_16": "log(close[t] / close[t-16])",
        "logret_96": "log(close[t] / close[t-96])",
        "vol_16": "rolling_std(logret_1, window=16)",
        "vol_96": "rolling_std(logret_1, window=96)",
        "range_1": "(high[t] - low[t]) / close[t]",
        "range_16": "rolling_mean(range_1, window=16)",
        "vol_z_96": "(volume[t] - rolling_mean(volume, 96)) / rolling_std(volume, 96)",
        "trend_96": "(close[t] - rolling_mean(close, 96)) / rolling_mean(close, 96)",
        "sma_ratio_16_96": "rolling_mean(close, 16) / rolling_mean(close, 96) - 1",
        "breakout_96": (
            "(close[t] - rolling_min(low, 96)) / "
            "(rolling_max(high, 96) - rolling_min(low, 96)); 0.5 when range=0"
        ),
    }
)

# Lags used for log-return features (must match formula)
LOG_RETURN_LAGS: list[int] = [1, 4, 16, 96]

# Rolling windows used for volatility, range, volume-z, trend, sma-ratio, breakout
ROLLING_WINDOWS: list[int] = [16, 96]

#: Warm-up rows at the start of any series where features are NaN
#: (equals the longest window = 96; the 96-period features need 96 prior candles)
WARMUP_ROWS: int = 96

# ── Outlier clipping (deterministic, causal, applied after computation) ────────
# Applied to all unbounded features (all except "breakout_96")
CLIP: float = 10.0
CLIPPED_FEATURES: list[str] = [f for f in MARKET_FEATURES if f != "breakout_96"]
UNCLIPPED_FEATURES: list[str] = ["breakout_96"]

# ── Portfolio features (ordered) ──────────────────────────────────────────────
PORTFOLIO_FEATURES: list[str] = [
    "exposure",
    "unrealized_return",
    "time_in_position",
    "recent_turnover",
    "drawdown",
]

# Normalization windows, bounds and semantics for each portfolio feature
PORTFOLIO_BOUNDS: MappingProxyType[str, dict[str, Any]] = MappingProxyType(
    {
        "exposure": {
            "description": "signed qty * mark / equity; clipped to [-3, 3]",
            "clip_low": -3.0,
            "clip_high": 3.0,
            "norm_window": None,
        },
        "unrealized_return": {
            "description": "unrealized_pnl / net_equity; clipped to [-3, 3]",
            "clip_low": -3.0,
            "clip_high": 3.0,
            "norm_window": None,
        },
        "time_in_position": {
            "description": "steps_in_current_position / 96, capped at 1.0",
            "clip_low": 0.0,
            "clip_high": 1.0,
            "norm_window": 96,
        },
        "recent_turnover": {
            "description": "sum of notional traded over last 96 steps / net_equity; clipped to [0, 10]",
            "clip_low": 0.0,
            "clip_high": 10.0,
            "norm_window": 96,
        },
        "drawdown": {
            "description": "1 - equity / peak_equity; in [0, 1]",
            "clip_low": 0.0,
            "clip_high": 1.0,
            "norm_window": None,
        },
    }
)

# ── Observation layout ─────────────────────────────────────────────────────────
ALL_FEATURES: list[str] = MARKET_FEATURES + PORTFOLIO_FEATURES
OBSERVATION_DIM: int = len(ALL_FEATURES)
OBSERVATION_DTYPE: str = "float32"

# ── Candle validation rules (documented, not enforced here) ───────────────────
CANDLE_VALIDATION_RULES: MappingProxyType[str, str] = MappingProxyType(
    {
        "open_time_type": "int64, not bool, strictly increasing, unique",
        "close_time_type": "int64, not bool, >= open_time",
        "ohlc": "finite, strictly positive",
        "volume": "finite, >= 0",
        "high_constraint": "high >= max(open, close)",
        "low_constraint": "low <= min(open, close)",
    }
)


# ── Canonical descriptor and hash ─────────────────────────────────────────────


def _build_descriptor() -> dict[str, Any]:
    """Build the complete ordered schema descriptor used for hashing."""
    return {
        "schema_version": SCHEMA_VERSION,
        "version": SCHEMA_VERSION,
        "required_candle_columns": list(REQUIRED_CANDLE_COLUMNS),
        "market_features": list(MARKET_FEATURES),
        "market_feature_formulas": dict(MARKET_FEATURE_FORMULAS),
        "log_return_lags": list(LOG_RETURN_LAGS),
        "rolling_windows": list(ROLLING_WINDOWS),
        "warmup_rows": WARMUP_ROWS,
        "clip": CLIP,
        "clipped_features": list(CLIPPED_FEATURES),
        "unclipped_features": list(UNCLIPPED_FEATURES),
        "portfolio_features": list(PORTFOLIO_FEATURES),
        "portfolio_bounds": copy.deepcopy(dict(PORTFOLIO_BOUNDS)),
        "observation_order": list(ALL_FEATURES),
        "observation_dim": OBSERVATION_DIM,
        "observation_dtype": OBSERVATION_DTYPE,
        "candle_validation_rules": dict(CANDLE_VALIDATION_RULES),
    }


def schema_descriptor() -> dict[str, Any]:
    """Return the complete versioned schema descriptor (not hashed yet)."""
    return copy.deepcopy(_build_descriptor())


def _canonical_json(descriptor: dict[str, Any]) -> bytes:
    """Serialise a descriptor as canonical sorted-keys compact JSON with allow_nan=False."""
    return json.dumps(descriptor, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def schema_sha256(descriptor: dict[str, Any] | None = None) -> str:
    """Compute the lowercase 64-char SHA-256 of the canonical schema descriptor.

    If `descriptor` is None the current descriptor is used.
    """
    if descriptor is None:
        descriptor = _build_descriptor()
    return hashlib.sha256(_canonical_json(descriptor)).hexdigest()


def schema_fingerprint() -> dict[str, Any]:
    """Return the complete versioned schema descriptor along with its SHA-256.

    This binds both the complete descriptor and hash in model/gate/holdout metadata.
    """
    desc = schema_descriptor()
    desc["schema_sha256"] = schema_sha256(desc)
    return copy.deepcopy(desc)


def validate_fingerprint(stored: object) -> None:
    """Validate a stored schema fingerprint against the current schema contract.

    Raises ModelCompatibilityError or RuntimeError on any mismatch:
      - legacy schema versions
      - missing or extra schema fields
      - malformed schema hashes
      - descriptor/hash disagreement
      - reordered features
      - changed constants, bounds or normalization
    """
    current = schema_fingerprint()
    if not isinstance(stored, dict):
        raise RuntimeError(f"stored feature_schema must be a dict, got {type(stored).__name__}")

    # Legacy or mismatched schema version
    stored_ver = stored.get("schema_version") or stored.get("version")
    if stored_ver != SCHEMA_VERSION:
        raise RuntimeError(
            f"legacy schema version: expected {SCHEMA_VERSION!r}, "
            f"got {stored_ver!r} — retrain required"
        )

    # Malformed schema hash
    stored_sha = stored.get("schema_sha256")
    if (
        not isinstance(stored_sha, str)
        or len(stored_sha) != 64
        or not stored_sha.islower()
        or not all(c in "0123456789abcdef" for c in stored_sha)
    ):
        raise RuntimeError(f"malformed schema hash: {stored_sha!r}")

    # Missing or extra schema fields (relative to complete fingerprint keys)
    expected_keys = frozenset(current.keys())
    actual_keys = frozenset(stored.keys())
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    if missing or extra:
        raise RuntimeError(
            f"missing or extra schema fields: missing={sorted(missing)}, extra={sorted(extra)}"
        )

    # Descriptor/hash disagreement (stored hash must match hash of stored descriptor fields)
    stored_desc = {k: v for k, v in stored.items() if k != "schema_sha256"}
    try:
        computed_sha = schema_sha256(stored_desc)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"stored schema descriptor cannot be canonically hashed: {exc}") from exc
    if computed_sha != stored_sha:
        raise RuntimeError(
            f"descriptor/hash disagreement: computed {computed_sha} vs stored {stored_sha}"
        )

    # Specific check for reordered features
    if (
        stored.get("market_features") != MARKET_FEATURES
        or stored.get("portfolio_features") != PORTFOLIO_FEATURES
        or stored.get("observation_order") != ALL_FEATURES
    ):
        raise RuntimeError("reordered features or changed feature definitions — retrain required")

    # Specific check for bounds/normalization
    if stored.get("portfolio_bounds") != dict(PORTFOLIO_BOUNDS):
        raise RuntimeError("changed bounds or normalization — retrain required")

    # Exact equality against current schema
    if stored_sha != current["schema_sha256"] or stored != current:
        raise RuntimeError("changed constants or schema mismatch — retrain required")
