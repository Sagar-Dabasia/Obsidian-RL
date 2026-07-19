"""LightGBM Alpha Gate: expected executable directional net return over a fixed horizon.

Target (corrected from the legacy leaky label): log(open[t+1+h] / open[t+1]) minus the
round-trip cost — the honest 'was entering after candle t worth it net of costs'. The
gate never claims profit; it estimates an expected net return that strategies may use
as a permission filter.

Time-aware training: the caller supplies a TRAINING slice only; internally the last
`val_fraction` (chronologically) is used for early stopping, separated by a purge gap
of `horizon` candles so no label straddles the boundary. Artifacts are saved as
LightGBM text boosters (never pickle) with JSON metadata + sha256.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from obsidian_rl.features.labels import forward_executable_net_return
from obsidian_rl.features.pipeline import (
    FEATURE_SCHEMA_VERSION,
    MARKET_FEATURES,
    WARMUP_ROWS,
    compute_market_features,
)

GATE_MODEL_FILE = "gate.txt"
GATE_META_FILE = "gate_meta.json"


class GateCompatibilityError(RuntimeError):
    pass


@dataclass
class AlphaGate:
    booster: Any  # lightgbm.Booster
    horizon: int
    round_trip_cost: float
    schema_version: str

    def predict_row(self, market_row: np.ndarray) -> float:
        arr = np.asarray(market_row, dtype=np.float64).reshape(1, -1)
        return float(self.booster.predict(arr)[0])


def build_training_frame(
    candles: pd.DataFrame, horizon: int, round_trip_cost: float
) -> tuple[pd.DataFrame, pd.Series]:
    feats = compute_market_features(candles)
    label = forward_executable_net_return(candles["open"], horizon, round_trip_cost)
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
) -> AlphaGate:
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


def save_gate(gate: AlphaGate, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / GATE_MODEL_FILE
    gate.booster.save_model(str(model_path))
    meta = {
        "created_utc_ms": int(time.time() * 1000),
        "horizon": gate.horizon,
        "round_trip_cost": gate.round_trip_cost,
        "schema_version": gate.schema_version,
        "features": list(MARKET_FEATURES),
        "artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
    }
    (out_dir / GATE_META_FILE).write_text(json.dumps(meta, indent=1), encoding="utf-8")


def load_gate(model_dir: Path) -> AlphaGate:
    """Load a text-format booster after validating metadata, checksum, and schema."""
    import lightgbm as lgb

    meta_path = Path(model_dir) / GATE_META_FILE
    model_path = Path(model_dir) / GATE_MODEL_FILE
    if not meta_path.exists() or not model_path.exists():
        raise GateCompatibilityError(f"missing gate artifact/metadata in {model_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if actual != meta.get("artifact_sha256"):
        raise GateCompatibilityError("gate artifact checksum mismatch")
    if meta.get("schema_version") != FEATURE_SCHEMA_VERSION or meta.get("features") != list(
        MARKET_FEATURES
    ):
        raise GateCompatibilityError("gate feature schema mismatch")
    booster = lgb.Booster(model_file=str(model_path))
    return AlphaGate(
        booster,
        int(meta["horizon"]),
        float(meta["round_trip_cost"]),
        str(meta["schema_version"]),
    )
