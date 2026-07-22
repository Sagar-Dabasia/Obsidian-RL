"""LightGBM Alpha Gate: signed executable directional net edge over a fixed horizon.

Target: sign(gross) * max(abs(gross) - round_trip_cost, 0), where
  gross = log(open[t+1+h] / open[t+1]).

This correctly captures both long and short edge net of round-trip costs.
A positive prediction permits long; a negative prediction permits short; near-zero is flat.
The gate never subtracts cost again — the label already encodes it.

Time-aware training: the caller supplies a TRAINING slice only; internally the last
`val_fraction` (chronologically) is used for early stopping, separated by a purge gap
of `horizon` candles so no label straddles the boundary. Artifacts are saved as
LightGBM text boosters (never pickle) with JSON metadata + sha256.
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from obsidian_rl.features.labels import (
    SIGNED_DIRECTIONAL_NET_EDGE_VERSION,
    signed_directional_net_edge,
)
from obsidian_rl.features.pipeline import (
    FEATURE_SCHEMA_VERSION,
    MARKET_FEATURES,
    WARMUP_ROWS,
    compute_market_features,
)
from obsidian_rl.features.schema import schema_fingerprint, validate_fingerprint

GATE_MODEL_FILE = "gate.txt"
GATE_META_FILE = "gate_meta.json"
GATE_SCHEMA_VERSION = "gate-schema-v2"

_REQUIRED_META_KEYS = frozenset(
    {
        "gate_schema_version",
        "target_name",
        "created_utc_ms",
        "horizon",
        "round_trip_cost",
        "feature_schema_version",
        "features",
        "feature_schema",
        "artifact_sha256",
    }
)

_N_FEATURES = len(MARKET_FEATURES)


class GateCompatibilityError(RuntimeError):
    pass


@dataclass
class AlphaGate:
    booster: Any  # lightgbm.Booster
    horizon: int
    round_trip_cost: float
    schema_version: str  # feature schema version (kept for compat)

    def predict_row(self, market_row: np.ndarray) -> float:
        arr = np.asarray(market_row, dtype=np.float64)
        if arr.ndim != 1:
            raise ValueError(f"market_row must be 1-dimensional, got shape {arr.shape}")
        if arr.shape[0] != _N_FEATURES:
            raise ValueError(
                f"market_row must have exactly {_N_FEATURES} values, got {arr.shape[0]}"
            )
        if not np.isfinite(arr).all():
            raise ValueError("market_row contains non-finite values")
        raw = self.booster.predict(arr.reshape(1, -1))
        raw_arr = np.asarray(raw)
        if raw_arr.size == 0:
            raise ValueError("booster.predict() returned an empty array")
        if raw_arr.size != 1:
            raise ValueError(
                f"booster.predict() returned {raw_arr.size} values; expected exactly 1"
            )
        pred = float(raw_arr.flat[0])
        if not math.isfinite(pred):
            raise ValueError(f"gate prediction is non-finite: {pred!r}")
        return pred

    def decide(self, market_row: np.ndarray, margin: float) -> int:
        """Return +1 (long), -1 (short), or 0 (flat) based on signed edge vs margin.

        Args:
            market_row: feature vector, length == len(MARKET_FEATURES).
            margin: non-negative minimum edge threshold; must be finite.
        """
        if (
            isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(margin)
            or margin < 0
        ):
            raise ValueError("margin must be a finite non-bool numeric >= 0")
        pred = self.predict_row(market_row)
        if pred > margin:
            return 1
        if pred < -margin:
            return -1
        return 0


def build_training_frame(
    candles: pd.DataFrame, horizon: int, round_trip_cost: float
) -> tuple[pd.DataFrame, pd.Series]:
    feats = compute_market_features(candles)
    label = signed_directional_net_edge(candles["open"], horizon, round_trip_cost)
    mask = feats.notna().all(axis=1) & label.notna()
    mask.iloc[:WARMUP_ROWS] = False
    return feats[mask], label[mask]


def train_gate(
    train_candles: pd.DataFrame,
    *,
    horizon: int = 16,
    round_trip_cost: float = 0.0013,
    val_fraction: float = 0.15,
    num_boost_round: int = 500,
    early_stopping_rounds: int = 50,
    params: dict[str, Any] | None = None,
) -> "AlphaGate":
    """Train on a chronological prefix; early-stop on the purged chronological tail."""
    import lightgbm as lgb

    x, y = build_training_frame(train_candles, horizon, round_trip_cost)
    n = len(x)
    if n < 500:
        raise ValueError(f"insufficient training rows for the gate: {n}")
    split = int(n * (1.0 - val_fraction))
    # purge: labels at the end of train reach `horizon` candles forward
    x_train, y_train = x.iloc[: split - horizon], y.iloc[: split - horizon]
    x_val, y_val = x.iloc[split:], y.iloc[split:]

    lgb_params = {
        "objective": "regression",
        "metric": "l2",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "seed": 42,
        "verbosity": -1,
    }
    lgb_params.update(params or {})
    booster = lgb.train(
        lgb_params,
        lgb.Dataset(x_train, label=y_train),
        num_boost_round=num_boost_round,
        valid_sets=[lgb.Dataset(x_val, label=y_val)],
        callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
    )
    return AlphaGate(booster, horizon, round_trip_cost, FEATURE_SCHEMA_VERSION)


def _validate_gate_fields_for_save(gate: "AlphaGate") -> None:
    """Raise GateCompatibilityError if gate fields are invalid before serialising."""
    if isinstance(gate.horizon, bool) or not isinstance(gate.horizon, int) or gate.horizon < 1:
        raise GateCompatibilityError(f"gate.horizon invalid before save: {gate.horizon!r}")
    if (
        isinstance(gate.round_trip_cost, bool)
        or not isinstance(gate.round_trip_cost, (int, float))
        or not math.isfinite(gate.round_trip_cost)
        or gate.round_trip_cost < 0
    ):
        raise GateCompatibilityError(
            f"gate.round_trip_cost invalid before save: {gate.round_trip_cost!r}"
        )
    if gate.schema_version != FEATURE_SCHEMA_VERSION:
        raise GateCompatibilityError(
            f"gate.schema_version mismatch before save: {gate.schema_version!r}"
        )


def save_gate(gate: "AlphaGate", out_dir: Path) -> None:
    _validate_gate_fields_for_save(gate)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / GATE_MODEL_FILE
    gate.booster.save_model(str(model_path))
    meta: dict[str, Any] = {
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "target_name": SIGNED_DIRECTIONAL_NET_EDGE_VERSION,
        "created_utc_ms": int(time.time() * 1000),
        "horizon": gate.horizon,
        "round_trip_cost": gate.round_trip_cost,
        "feature_schema_version": gate.schema_version,
        "features": list(MARKET_FEATURES),
        "feature_schema": schema_fingerprint(),
        "artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
    }
    # Fail fast if any non-finite values were somehow constructed
    try:
        serialised = json.dumps(meta, indent=1, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise GateCompatibilityError(
            f"gate metadata contains non-serialisable value: {exc}"
        ) from exc
    (out_dir / GATE_META_FILE).write_text(serialised, encoding="utf-8")


def _load_and_validate_meta(meta_path: Path, model_path: Path) -> dict[str, Any]:
    """Load gate_meta.json and validate all required fields, checksum, and schema."""
    raw_text = meta_path.read_text(encoding="utf-8")

    # Parse JSON, rejecting malformed text
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GateCompatibilityError(f"gate metadata is malformed JSON: {exc}") from exc

    # Root must be an object, not a list or scalar
    if not isinstance(parsed, dict):
        raise GateCompatibilityError(
            f"gate metadata root must be a JSON object, got {type(parsed).__name__}"
        )

    # Reject NaN/Infinity that Python's json.loads() silently accepts
    try:
        json.dumps(parsed, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise GateCompatibilityError(
            f"gate metadata contains non-finite JSON value: {exc}"
        ) from exc

    meta: dict[str, Any] = parsed

    # Exact key set — no missing, no extra
    actual_keys = frozenset(meta.keys())
    missing = _REQUIRED_META_KEYS - actual_keys
    extra = actual_keys - _REQUIRED_META_KEYS
    if missing or extra:
        raise GateCompatibilityError(
            f"gate metadata key mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
        )

    if meta.get("gate_schema_version") != GATE_SCHEMA_VERSION:
        raise GateCompatibilityError(
            f"gate schema version mismatch: expected {GATE_SCHEMA_VERSION!r}, "
            f"got {meta.get('gate_schema_version')!r} — retrain required"
        )

    if meta.get("target_name") != SIGNED_DIRECTIONAL_NET_EDGE_VERSION:
        raise GateCompatibilityError(
            f"gate target mismatch: expected {SIGNED_DIRECTIONAL_NET_EDGE_VERSION!r}, "
            f"got {meta.get('target_name')!r} — retrain required"
        )

    if meta.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise GateCompatibilityError(
            f"gate feature schema mismatch: expected {FEATURE_SCHEMA_VERSION!r}, "
            f"got {meta.get('feature_schema_version')!r}"
        )

    if meta.get("features") != list(MARKET_FEATURES):
        raise GateCompatibilityError(
            "gate feature list mismatch (reordered or changed) — retrain required"
        )

    try:
        validate_fingerprint(meta.get("feature_schema"))
    except (RuntimeError, ValueError) as exc:
        raise GateCompatibilityError(f"gate feature schema mismatch: {exc}") from exc

    horizon = meta.get("horizon")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise GateCompatibilityError(f"gate metadata horizon invalid: {horizon!r}")

    cost = meta.get("round_trip_cost")
    if (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise GateCompatibilityError(f"gate metadata round_trip_cost invalid: {cost!r}")

    ts = meta.get("created_utc_ms")
    if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
        raise GateCompatibilityError(
            f"gate metadata created_utc_ms must be a non-bool int >= 0, got {ts!r}"
        )

    expected_sha = meta.get("artifact_sha256")
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or not expected_sha.islower()
        or not all(c in "0123456789abcdef" for c in expected_sha)
    ):
        raise GateCompatibilityError(
            f"gate metadata artifact_sha256 must be 64 lowercase hex chars, got {expected_sha!r}"
        )

    actual_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise GateCompatibilityError("gate artifact checksum mismatch")

    return meta


def load_gate(model_dir: Path) -> "AlphaGate":
    """Load a text-format booster after validating metadata, checksum, and schema."""
    import lightgbm as lgb

    meta_path = Path(model_dir) / GATE_META_FILE
    model_path = Path(model_dir) / GATE_MODEL_FILE
    if not meta_path.exists() or not model_path.exists():
        raise GateCompatibilityError(f"missing gate artifact/metadata in {model_dir}")

    meta = _load_and_validate_meta(meta_path, model_path)
    booster = lgb.Booster(model_file=str(model_path))
    return AlphaGate(
        booster,
        int(meta["horizon"]),
        float(meta["round_trip_cost"]),
        str(meta["feature_schema_version"]),
    )
