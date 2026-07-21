"""Alpha Gate tests: chronological ES split with purge, artifact safety, gating logic."""

import json
from pathlib import Path

import numpy as np
import pytest

from obsidian_rl.features.labels import SIGNED_DIRECTIONAL_NET_EDGE_VERSION
from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.features.pipeline import FEATURE_SCHEMA_VERSION, MARKET_FEATURES, WARMUP_ROWS
from obsidian_rl.features.schema import schema_fingerprint, schema_sha256
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
    with pytest.raises(GateCompatibilityError, match="missing"):
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
    with pytest.raises(GateCompatibilityError, match="non-finite"):
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


# ── predict_row — shape / length / prediction-count hardening ─────────────────


def test_predict_row_wrong_feature_length() -> None:
    gate = stub_gate(0.0)
    short_row = np.zeros(len(MARKET_FEATURES) - 1, dtype=np.float64)
    with pytest.raises(ValueError, match=r"exactly \d+ values"):
        gate.predict_row(short_row)


def test_predict_row_two_dimensional_input() -> None:
    gate = stub_gate(0.0)
    matrix = np.zeros((1, len(MARKET_FEATURES)), dtype=np.float64)
    with pytest.raises(ValueError, match="1-dimensional"):
        gate.predict_row(matrix)


def test_predict_row_empty_prediction_rejected() -> None:
    class EmptyBooster:
        def predict(self, arr: np.ndarray) -> np.ndarray:
            return np.array([])

    gate = AlphaGate(EmptyBooster(), 16, 0.001, FEATURE_SCHEMA_VERSION)
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float64)
    with pytest.raises(ValueError, match="empty"):
        gate.predict_row(row)


def test_predict_row_multi_value_prediction_rejected() -> None:
    class MultiBooster:
        def predict(self, arr: np.ndarray) -> np.ndarray:
            return np.array([0.1, 0.2])

    gate = AlphaGate(MultiBooster(), 16, 0.001, FEATURE_SCHEMA_VERSION)
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float64)
    with pytest.raises(ValueError, match=r"2 values.*exactly 1"):
        gate.predict_row(row)


# ── _load_and_validate_meta — metadata hardening ──────────────────────────────


def _write_meta(tmp_path: Path, meta: dict) -> None:
    """Write gate.txt stub and gate_meta.json with the given meta (allow_nan=True)."""
    (tmp_path / "gate.txt").write_bytes(b"stub")
    sha = __import__("hashlib").sha256(b"stub").hexdigest()
    meta.setdefault("artifact_sha256", sha)
    (tmp_path / "gate_meta.json").write_text(json.dumps(meta, allow_nan=True), encoding="utf-8")


def _base_meta() -> dict:
    return {
        "gate_schema_version": GATE_SCHEMA_VERSION,
        "target_name": SIGNED_DIRECTIONAL_NET_EDGE_VERSION,
        "created_utc_ms": 1_000_000,
        "horizon": 16,
        "round_trip_cost": 0.0013,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": list(MARKET_FEATURES),
        "feature_schema": schema_fingerprint(),
    }


def test_metadata_root_is_list_rejected(tmp_path: Path) -> None:
    (tmp_path / "gate.txt").write_bytes(b"stub")
    (tmp_path / "gate_meta.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(GateCompatibilityError, match="JSON object"):
        load_gate(tmp_path)


def test_metadata_malformed_json_rejected(tmp_path: Path) -> None:
    (tmp_path / "gate.txt").write_bytes(b"stub")
    (tmp_path / "gate_meta.json").write_text("{not: valid json", encoding="utf-8")
    with pytest.raises(GateCompatibilityError, match="malformed JSON"):
        load_gate(tmp_path)


def test_metadata_nan_json_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["round_trip_cost"] = float("nan")
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="non-finite"):
        load_gate(tmp_path)


def test_metadata_infinity_json_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["round_trip_cost"] = float("inf")
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="non-finite"):
        load_gate(tmp_path)


def test_metadata_extra_field_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["unexpected_extra"] = "bad"
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="extra"):
        load_gate(tmp_path)


def test_metadata_created_utc_ms_bool_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["created_utc_ms"] = True  # bool is subtype of int — must be rejected
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="created_utc_ms"):
        load_gate(tmp_path)


def test_metadata_created_utc_ms_negative_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["created_utc_ms"] = -1
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="created_utc_ms"):
        load_gate(tmp_path)


def test_metadata_created_utc_ms_missing_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta.pop("created_utc_ms", None)
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="missing"):
        load_gate(tmp_path)


def test_metadata_sha256_uppercase_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    # Uppercase hex is not valid for our lowercase-only constraint
    sha_bytes = b"stub"
    meta["artifact_sha256"] = __import__("hashlib").sha256(sha_bytes).hexdigest().upper()
    (tmp_path / "gate.txt").write_bytes(sha_bytes)
    (tmp_path / "gate_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(GateCompatibilityError, match="artifact_sha256"):
        load_gate(tmp_path)


def test_metadata_sha256_non_hex_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["artifact_sha256"] = "g" * 64  # 'g' is not hex
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="artifact_sha256"):
        load_gate(tmp_path)


def test_metadata_sha256_wrong_length_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["artifact_sha256"] = "a" * 32  # too short
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="artifact_sha256"):
        load_gate(tmp_path)


# ── save_gate — pre-save field validation ─────────────────────────────────────


def test_save_gate_rejects_invalid_horizon(tmp_path: Path) -> None:
    gate = stub_gate(0.0)
    gate.horizon = 0  # type: ignore[assignment]
    with pytest.raises(GateCompatibilityError, match="horizon"):
        save_gate(gate, tmp_path)


def test_save_gate_rejects_invalid_cost(tmp_path: Path) -> None:
    gate = stub_gate(0.0)
    gate.round_trip_cost = -0.01  # type: ignore[assignment]
    with pytest.raises(GateCompatibilityError, match="round_trip_cost"):
        save_gate(gate, tmp_path)


def test_save_gate_rejects_wrong_schema_version(tmp_path: Path) -> None:
    gate = stub_gate(0.0)
    gate.schema_version = "old-version"  # type: ignore[assignment]
    with pytest.raises(GateCompatibilityError, match="schema_version"):
        save_gate(gate, tmp_path)


# ── Phase 6 feature_schema strict validation tests ────────────────────────────


def test_gate_legacy_feature_schema_version_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["feature_schema"]["schema_version"] = "fs-v1"
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="legacy schema version"):
        load_gate(tmp_path)


def test_gate_missing_feature_schema_field_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    del meta["feature_schema"]["warmup_rows"]
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="missing or extra schema fields"):
        load_gate(tmp_path)


def test_gate_extra_feature_schema_field_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["feature_schema"]["unexpected_field"] = 123
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="missing or extra schema fields"):
        load_gate(tmp_path)


def test_gate_changed_feature_schema_constants_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["feature_schema"]["warmup_rows"] = 999
    desc = {k: v for k, v in meta["feature_schema"].items() if k != "schema_sha256"}
    meta["feature_schema"]["schema_sha256"] = schema_sha256(desc)
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="changed constants or schema mismatch"):
        load_gate(tmp_path)


def test_gate_reordered_feature_schema_features_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["feature_schema"]["market_features"] = list(reversed(MARKET_FEATURES))
    desc = {k: v for k, v in meta["feature_schema"].items() if k != "schema_sha256"}
    meta["feature_schema"]["schema_sha256"] = schema_sha256(desc)
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="reordered features"):
        load_gate(tmp_path)


def test_gate_changed_feature_schema_bounds_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    bounds = dict(meta["feature_schema"]["portfolio_bounds"])
    bounds["exposure"] = dict(bounds["exposure"])
    bounds["exposure"]["clip_high"] = 99.0
    meta["feature_schema"]["portfolio_bounds"] = bounds
    desc = {k: v for k, v in meta["feature_schema"].items() if k != "schema_sha256"}
    meta["feature_schema"]["schema_sha256"] = schema_sha256(desc)
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="changed bounds or normalization"):
        load_gate(tmp_path)


def test_gate_malformed_feature_schema_hash_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["feature_schema"]["schema_sha256"] = "invalid_hash"
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="malformed schema hash"):
        load_gate(tmp_path)


def test_gate_feature_schema_descriptor_hash_disagreement_rejected(tmp_path: Path) -> None:
    meta = _base_meta()
    meta["feature_schema"]["warmup_rows"] = 999  # descriptor altered, but hash not updated
    _write_meta(tmp_path, meta)
    with pytest.raises(GateCompatibilityError, match="descriptor/hash disagreement"):
        load_gate(tmp_path)
