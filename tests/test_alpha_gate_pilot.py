"""Tests for Alpha Gate Historical Pilot 01."""

import math
from pathlib import Path
import numpy as np
import pytest

from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.gate.alpha_gate import load_gate, save_gate, train_gate
from obsidian_rl.strategies.baselines import RegimeFilteredMomentum
from obsidian_rl.strategies.gated import GateDirectStrategy, GatedStrategy
from tests.conftest import make_candles
from tools.alpha_gate_pilot import check_strategy_eligibility


def test_alpha_gate_training_save_load(tmp_path: Path) -> None:
    candles = make_candles(700, seed=42)
    gate = train_gate(candles, num_boost_round=10, early_stopping_rounds=5)
    
    out_dir = tmp_path / "gate_ckpt"
    save_gate(gate, out_dir)
    
    loaded = load_gate(out_dir)
    assert loaded.horizon == gate.horizon
    assert loaded.round_trip_cost == gate.round_trip_cost
    
    row = np.zeros(12, dtype=np.float64)
    pred_orig = gate.predict_row(row)
    pred_load = loaded.predict_row(row)
    assert pred_orig == pytest.approx(pred_load)


def test_gate_strategies_reset_and_propose(tmp_path: Path) -> None:
    candles = make_candles(700, seed=43)
    gate = train_gate(candles, num_boost_round=10, early_stopping_rounds=5)
    
    direct = GateDirectStrategy(gate, margin=0.0)
    direct.reset()
    
    gated = GatedStrategy(RegimeFilteredMomentum(), gate, margin=0.0)
    gated.reset()
    
    dummy_obs = PortfolioObs(0.0, 0.0, 0.0, 0.0, 0.0)
    market_row = np.zeros(12, dtype=np.float32)
    
    p_direct = direct.propose(market_row, dummy_obs)
    p_gated = gated.propose(market_row, dummy_obs)
    
    assert p_direct in (-1.0, 0.0, 1.0)
    assert -1.0 <= p_gated <= 1.0


def test_eligibility_checks_passing() -> None:
    rows = [
        {"scenario": "base", "net_return": 0.10, "max_drawdown": 0.05, "sharpe": 1.0},
        {"scenario": "base", "net_return": 0.05, "max_drawdown": 0.04, "sharpe": 0.8},
        {"scenario": "base", "net_return": 0.02, "max_drawdown": 0.06, "sharpe": 0.5},
        {"scenario": "base", "net_return": -0.01, "max_drawdown": 0.05, "sharpe": -0.1},
        {"scenario": "costs2x", "net_return": 0.08, "max_drawdown": 0.05, "sharpe": 0.9},
        {"scenario": "costs2x", "net_return": 0.04, "max_drawdown": 0.04, "sharpe": 0.7},
        {"scenario": "costs2x", "net_return": 0.01, "max_drawdown": 0.06, "sharpe": 0.4},
        {"scenario": "costs2x", "net_return": -0.02, "max_drawdown": 0.05, "sharpe": -0.2},
        {"scenario": "delay1", "net_return": 0.09, "max_drawdown": 0.05, "sharpe": 0.9},
        {"scenario": "delay1", "net_return": 0.04, "max_drawdown": 0.04, "sharpe": 0.7},
        {"scenario": "delay1", "net_return": 0.01, "max_drawdown": 0.06, "sharpe": 0.4},
        {"scenario": "delay1", "net_return": -0.01, "max_drawdown": 0.05, "sharpe": -0.1},
    ]
    res = check_strategy_eligibility(rows)
    assert res["pos_folds"] == 3
    assert res["worst_fold"] == -0.01
    assert res["passed"] is True


def test_eligibility_checks_failing_worst_fold() -> None:
    rows = [
        {"scenario": "base", "net_return": 0.10, "max_drawdown": 0.05, "sharpe": 1.0},
        {"scenario": "base", "net_return": 0.05, "max_drawdown": 0.04, "sharpe": 0.8},
        {"scenario": "base", "net_return": 0.02, "max_drawdown": 0.06, "sharpe": 0.5},
        {"scenario": "base", "net_return": -0.08, "max_drawdown": 0.05, "sharpe": -0.8},
        {"scenario": "costs2x", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "costs2x", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "costs2x", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "costs2x", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "delay1", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "delay1", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "delay1", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
        {"scenario": "delay1", "net_return": 0.01, "max_drawdown": 0.05, "sharpe": 0.1},
    ]
    res = check_strategy_eligibility(rows)
    assert res["worst_fold"] == -0.08
    assert res["passed"] is False


def test_non_finite_rejection() -> None:
    rows = [
        {"scenario": "base", "net_return": float("nan"), "max_drawdown": 0.05, "sharpe": 1.0},
        {"scenario": "costs2x", "net_return": 0.05, "max_drawdown": 0.04, "sharpe": 0.8},
        {"scenario": "delay1", "net_return": 0.02, "max_drawdown": 0.06, "sharpe": 0.5},
    ]
    res = check_strategy_eligibility(rows)
    assert res["all_finite"] is False
    assert res["passed"] is False
