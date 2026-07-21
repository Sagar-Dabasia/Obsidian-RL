"""Alpha Gate tests: chronological ES split with purge, artifact safety, gating logic."""

import json
from pathlib import Path

import numpy as np
import pytest

from obsidian_rl.features.labels import SIGNED_DIRECTIONAL_NET_EDGE_VERSION
from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.features.pipeline import FEATURE_SCHEMA_VERSION, MARKET_FEATURES, WARMUP_ROWS
from obsidian_rl.gate.alpha_gate import (
    GATE_SCHEMA_VERSION,
    AlphaGate,
    GateCompatibilityError,
    build_training_frame,
    load_gate,
    save_gate,
    train_gate,
)
from obsidian_rl.strategies.baselines import BuyAndHold
from obsidian_rl.strategies.gated import GateDirectStrategy, GatedStrategy
from tests.conftest import make_candles

PORT = PortfolioObs(0.0, 0.0, 0.0, 0.0, 0.0)


class StubBooster:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, arr: np.ndarray) -> np.ndarray:
        return np.array([self.value])


def stub_gate(value: float) -> AlphaGate:
    return AlphaGate(StubBooster(value), 16, 0.0013, FEATURE_SCHEMA_VERSION)


# ── Training frame ─────────────────────────────────────────────────────────────


def test_training_frame_drops_warmup_and_tail() -> None:
    candles = make_candles(WARMUP_ROWS + 200)
    x, y = build_training_frame(candles, horizon=16, round_trip_cost=0.001)
    # warm-up rows and the last horizon+1 rows (NaN labels) are excluded
    assert x.index[0] >= WARMUP_ROWS
    assert x.index[-1] <= len(candles) - 16 - 2
    assert not x.isna().any().any() and not y.isna().any()
    assert list(x.columns) == MARKET_FEATURES


def test_training_frame_uses_signed_label() -> None:
    """build_training_frame must use the signed directional label, not legacy."""
    from obsidian_rl.features.labels import signed_directional_net_edge

    candles = make_candles(WARMUP_ROWS + 200, seed=7)
    _, y = build_training_frame(candles, horizon=4, round_trip_cost=0.002)
    expected = signed_directional_net_edge(candles["open"], horizon=4, round_trip_cost=0.002)
    # The y values must come from signed_directional_net_edge (can have negative values)
    # The legacy label always had cost subtracted uniformly; signed label can be exactly 0
    # At minimum: negative labels must appear (indicating valid short edge) OR
    # all valid labeled rows should match sign-based computation exactly.
    expected_aligned = expected[y.index]
    np.testing.assert_allclose(y.values, expected_aligned.values, rtol=1e-10)


# ── Round-trip save / load ─────────────────────────────────────────────────────


def test_train_save_load_roundtrip(tmp_path: Path) -> None:
    candles = make_candles(1200, seed=3)
    gate = train_gate(candles, horizon=8, num_boost_round=20, early_stopping_rounds=5)
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    pred = gate.predict_row(row)
    save_gate(gate, tmp_path)
    loaded = load_gate(tmp_path)
    assert loaded.predict_row(row) == pytest.approx(pred)
    assert loaded.horizon == 8
    assert loaded.round_trip_cost == pytest.approx(gate.round_trip_cost)


def test_save_gate_persists_target_identity(tmp_path: Path) -> None:
    candles = make_candles(1200, seed=5)
    gate = train_gate(candles, horizon=4, num_boost_round=10, early_stopping_rounds=5)
    save_gate(gate, tmp_path)
    meta = json.loads((tmp_path / "gate_meta.json").read_text())
    assert meta["gate_schema_version"] == GATE_SCHEMA_VERSION
    assert meta["target_name"] == SIGNED_DIRECTIONAL_NET_EDGE_VERSION
    assert meta["horizon"] == 4
    assert meta["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert meta["features"] == list(MARKET_FEATURES)
    assert len(meta["artifact_sha256"]) == 64


# ── Checksum & metadata validation ────────────────────────────────────────────


def test_tampered_artifact_rejected(tmp_path: Path) -> None:
    candles = make_candles(1200, seed=3)
    gate = train_gate(candles, horizon=8, num_boost_round=10, early_stopping_rounds=5)
    save_gate(gate, tmp_path)
    model_path = tmp_path / "gate.txt"
    model_path.write_text(model_path.read_text() + "\ntampered", encoding="utf-8")
    with pytest.raises(GateCompatibilityError, match="checksum"):
        load_gate(tmp_path)


def _write_meta(tmp_path: Path, meta: dict) -> None:
    """Write a gate_meta.json with a stub gate.txt to allow path checks."""
    (tmp_path / "gate.txt").write_bytes(b"stub")
    sha = __import__("hashlib").sha256(b"stub").hexdigest()
    meta.setdefault("artifact_sha256", sha)
    (tmp_path / "gate_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _base_meta() -> dict:
    return {
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "target_name": SIGNED_DIRECTIONAL_NET_EDGE_VERSION,
        "created_utc_ms": 1000,
        "horizon": 16,
        "round_trip_cost": 0.0013,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": list(MARKET_FEATURES),
    }


def test_legacy_gate_schema_version_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["gate_schema_version"] = "gate-schema-v1"
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="schema version"):
        load_gate(tmp_path)


def test_legacy_target_name_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["target_name"] = "old-target"
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="target"):
        load_gate(tmp_path)


def test_missing_metadata_fields_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta.pop("horizon")
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="missing fields"):
        load_gate(tmp_path)


def test_reordered_features_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["features"] = list(reversed(MARKET_FEATURES))
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="feature list"):
        load_gate(tmp_path)


def test_malformed_horizon_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["horizon"] = 0  # invalid: must be >= 1
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="horizon"):
        load_gate(tmp_path)


def test_malformed_cost_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["round_trip_cost"] = float("nan")
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="round_trip_cost"):
        load_gate(tmp_path)


# ── predict_row validation ─────────────────────────────────────────────────────


def test_predict_row_non_finite_input_rejected() -> None:
    gate = stub_gate(0.01)
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float64)
    row[0] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        gate.predict_row(row)


def test_predict_row_non_finite_prediction_rejected() -> None:
    class InfBooster:
        def predict(self, arr: np.ndarray) -> np.ndarray:
            return np.array([float("inf")])

    gate = AlphaGate(InfBooster(), 16, 0.001, FEATURE_SCHEMA_VERSION)
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float64)
    with pytest.raises(ValueError, match="non-finite"):
        gate.predict_row(row)


# ── decide() margin logic ─────────────────────────────────────────────────────


def test_gate_decide_long_short_flat() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float64)
    assert stub_gate(0.01).decide(row, 0.005) == 1
    assert stub_gate(-0.01).decide(row, 0.005) == -1
    assert stub_gate(0.003).decide(row, 0.005) == 0
    assert stub_gate(0.0).decide(row, 0.0) == 0


def test_gate_decide_invalid_margin() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float64)
    gate = stub_gate(0.01)
    with pytest.raises(ValueError, match="margin"):
        gate.decide(row, -0.001)
    with pytest.raises(ValueError, match="margin"):
        gate.decide(row, float("nan"))
    with pytest.raises(ValueError, match="margin"):
        gate.decide(row, True)  # type: ignore[arg-type]


# ── GatedStrategy ──────────────────────────────────────────────────────────────


def test_gated_strategy_clamps_directions() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    long_gate = GatedStrategy(BuyAndHold(), stub_gate(0.01), margin=0.001)
    assert long_gate.propose(row, PORT) == 1.0  # gate agrees with long base
    short_gate = GatedStrategy(BuyAndHold(), stub_gate(-0.01), margin=0.001)
    assert short_gate.propose(row, PORT) == 0.0  # long base clamped to flat
    neutral = GatedStrategy(BuyAndHold(), stub_gate(0.0), margin=0.001)
    assert neutral.propose(row, PORT) == 0.0


def test_gated_strategy_invalid_margin() -> None:
    with pytest.raises(ValueError, match="margin"):
        GatedStrategy(BuyAndHold(), stub_gate(0.01), margin=-0.001)


def test_gated_strategy_short_permitted() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    gate = GatedStrategy(BuyAndHold(), stub_gate(-0.02), margin=0.001)
    # BuyAndHold proposes 1.0 (long), gate says short -> clamped to 0 (can't go long)
    assert gate.propose(row, PORT) == 0.0


# ── GateDirectStrategy ─────────────────────────────────────────────────────────


def test_gate_direct_strategy() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    assert GateDirectStrategy(stub_gate(0.01), 0.001).propose(row, PORT) == 1.0
    assert GateDirectStrategy(stub_gate(-0.01), 0.001).propose(row, PORT) == -1.0
    assert GateDirectStrategy(stub_gate(0.0005), 0.001).propose(row, PORT) == 0.0


def test_gate_direct_strategy_invalid_margin() -> None:
    with pytest.raises(ValueError, match="margin"):
        GateDirectStrategy(stub_gate(0.01), margin=float("nan"))


# ── Misc ───────────────────────────────────────────────────────────────────────


def test_insufficient_data_refused() -> None:
    with pytest.raises(ValueError, match="insufficient"):
        train_gate(make_candles(WARMUP_ROWS + 100), horizon=8)
