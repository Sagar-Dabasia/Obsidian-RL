"""Backtest runner + baseline tests, including hand-verified accounting."""

import numpy as np
import pandas as pd
import pytest

from obsidian_rl.evaluation.backtest import run_backtest, snap_target
from obsidian_rl.evaluation.metrics import compute_metrics, trade_stats
from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig
from obsidian_rl.strategies.baselines import (
    AlwaysFlat,
    BuyAndHold,
    CooldownMomentum,
    FixedHolding,
    RegimeFilteredMomentum,
    ThresholdMomentum,
    default_baselines,
)
from tests.conftest import make_candles

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)
PORT = PortfolioObs(0.0, 0.0, 0.0, 0.0, 0.0)


def test_snap_target() -> None:
    allowed = (-1.0, -0.5, 0.0, 0.5, 1.0)
    assert snap_target(0.7, allowed) == 0.5
    assert snap_target(0.8, allowed) == 1.0
    assert snap_target(-0.3, allowed) == -0.5
    assert snap_target(0.0, allowed) == 0.0


def test_always_flat_preserves_cash_exactly() -> None:
    candles = make_candles(200)
    res = run_backtest(candles, AlwaysFlat(), cost_model=CM)
    assert res.final_state_summary["final_equity"] == pytest.approx(10_000.0)
    assert res.final_state_summary["trade_count"] == 0
    assert (res.equity_curve["equity"] == 10_000.0).all()


def test_buy_and_hold_hand_verified() -> None:
    candles = make_candles(WARMUP_ROWS + 4)
    res = run_backtest(
        candles,
        BuyAndHold(),
        cost_model=CM,
        portfolio_config=PortfolioConfig(initial_cash=10_000.0),
    )
    # entry at open[W+1]: qty = 10000/open, costs 0.2% of 10000 = 20
    entry_px = float(candles["open"].iloc[WARMUP_ROWS + 1])
    final_px = float(candles["close"].iloc[-1])
    qty = 10_000.0 / entry_px
    exit_notional = qty * final_px
    expected = 10_000.0 - 20.0 + qty * (final_px - entry_px) - exit_notional * 0.002
    assert res.final_state_summary["final_equity"] == pytest.approx(expected, rel=1e-6)
    # one entry trade + terminal liquidation
    assert res.final_state_summary["trade_count"] == 2


def test_backtest_is_deterministic() -> None:
    candles = make_candles(400)
    a = run_backtest(candles, ThresholdMomentum(0.002), cost_model=CM)
    b = run_backtest(candles, ThresholdMomentum(0.002), cost_model=CM)
    pd.testing.assert_frame_equal(a.equity_curve, b.equity_curve)


def test_all_baselines_run_on_shared_stack() -> None:
    candles = make_candles(400)
    for strat in default_baselines():
        res = run_backtest(candles, strat, cost_model=CM)  # type: ignore[arg-type]
        m = compute_metrics(res.strategy_id, res.equity_curve, res.final_state_summary)
        assert np.isfinite(m.net_return)
        assert m.n_candles == res.n_decisions


def test_regime_momentum_goes_long_in_uptrend() -> None:
    n = 400
    candles = make_candles(n, seed=1)
    # impose a strong monotonic uptrend (fixture manipulation, test-only)
    trend = np.linspace(0, 0.5, n)
    for col in ("open", "high", "low", "close"):
        candles[col] = candles[col] * np.exp(trend)
    res = run_backtest(candles, RegimeFilteredMomentum(), cost_model=CM)
    assert res.equity_curve["exposure"].iloc[-50:].mean() > 0.5


def test_fixed_holding_respects_duration() -> None:
    strat = FixedHolding(threshold=0.0, hold_steps=5)  # threshold 0 => enters immediately
    row = np.zeros(12, dtype=np.float32)
    row[2] = 0.01  # logret_16 positive
    first = strat.propose(row, PORT)
    assert first == 1.0
    neutral = np.zeros(12, dtype=np.float32)
    holds = [strat.propose(neutral, PORT) for _ in range(4)]
    assert holds == [1.0, 1.0, 1.0, 1.0]
    after = strat.propose(neutral, PORT)
    assert after == 0.0  # hold expired, no new signal


def test_cooldown_blocks_reentry() -> None:
    strat = CooldownMomentum(enter_threshold=0.005, exit_threshold=0.001, cooldown=3)
    up = np.zeros(12, dtype=np.float32)
    up[2] = 0.01
    down = np.zeros(12, dtype=np.float32)
    down[2] = -0.01
    assert strat.propose(up, PORT) == 1.0
    assert strat.propose(down, PORT) == 0.0  # exit triggers cooldown
    assert [strat.propose(up, PORT) for _ in range(3)] == [0.0, 0.0, 0.0]  # cooldown
    assert strat.propose(up, PORT) == 1.0  # re-entry allowed


def test_funding_events_applied() -> None:
    candles = make_candles(WARMUP_ROWS + 10)
    t = WARMUP_ROWS + 2
    funding = pd.DataFrame(
        {
            "funding_time_ms": [int(candles["open_time"].iloc[t]) + 1000],
            "funding_rate": [0.0001],
        }
    )
    res_with = run_backtest(candles, BuyAndHold(), cost_model=CM, funding_rates=funding)
    res_without = run_backtest(candles, BuyAndHold(), cost_model=CM)
    assert res_with.final_state_summary["funding"] > 0
    assert res_without.final_state_summary["funding"] == 0.0


def test_trade_stats() -> None:
    stats = trade_stats([10.0, -5.0, 20.0, 0.0, -5.0])
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["profit_factor"] == pytest.approx(3.0)
    assert stats["n_events"] == 4
