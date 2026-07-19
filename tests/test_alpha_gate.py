"""Alpha Gate tests: chronological ES split with purge, artifact safety, gating logic."""

from pathlib import Path

import numpy as np
import pytest

from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.features.pipeline import MARKET_FEATURES, WARMUP_ROWS
from obsidian_rl.gate.alpha_gate import (
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
    return AlphaGate(StubBooster(value), 16, 0.0013, "fs-v1")


def test_training_frame_drops_warmup_and_tail() -> None:
    candles = make_candles(WARMUP_ROWS + 200)
    x, y = build_training_frame(candles, horizon=16, round_trip_cost=0.001)
    # warm-up rows and the last horizon+1 rows (NaN labels) are excluded
    assert x.index[0] >= WARMUP_ROWS
    assert x.index[-1] <= len(candles) - 16 - 2
    assert not x.isna().any().any() and not y.isna().any()
    assert list(x.columns) == MARKET_FEATURES


def test_train_save_load_roundtrip(tmp_path: Path) -> None:
    candles = make_candles(1200, seed=3)
    gate = train_gate(candles, horizon=8, num_boost_round=20, early_stopping_rounds=5)
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    pred = gate.predict_row(row)
    save_gate(gate, tmp_path)
    loaded = load_gate(tmp_path)
    assert loaded.predict_row(row) == pytest.approx(pred)
    assert loaded.horizon == 8


def test_tampered_artifact_rejected(tmp_path: Path) -> None:
    candles = make_candles(1200, seed=3)
    gate = train_gate(candles, horizon=8, num_boost_round=10, early_stopping_rounds=5)
    save_gate(gate, tmp_path)
    model_path = tmp_path / "gate.txt"
    model_path.write_text(model_path.read_text() + "\ntampered", encoding="utf-8")
    with pytest.raises(GateCompatibilityError, match="checksum"):
        load_gate(tmp_path)


def test_insufficient_data_refused() -> None:
    with pytest.raises(ValueError, match="insufficient"):
        train_gate(make_candles(WARMUP_ROWS + 100), horizon=8)


def test_gated_strategy_clamps_directions() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    long_gate = GatedStrategy(BuyAndHold(), stub_gate(0.01), margin=0.001)
    assert long_gate.propose(row, PORT) == 1.0  # gate agrees with long base
    short_gate = GatedStrategy(BuyAndHold(), stub_gate(-0.01), margin=0.001)
    assert short_gate.propose(row, PORT) == 0.0  # long base clamped to flat
    neutral = GatedStrategy(BuyAndHold(), stub_gate(0.0), margin=0.001)
    assert neutral.propose(row, PORT) == 0.0


def test_gate_direct_strategy() -> None:
    row = np.zeros(len(MARKET_FEATURES), dtype=np.float32)
    assert GateDirectStrategy(stub_gate(0.01), 0.001).propose(row, PORT) == 1.0
    assert GateDirectStrategy(stub_gate(-0.01), 0.001).propose(row, PORT) == -1.0
    assert GateDirectStrategy(stub_gate(0.0005), 0.001).propose(row, PORT) == 0.0
