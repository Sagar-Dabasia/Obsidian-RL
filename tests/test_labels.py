"""Forward-label correctness: label at t uses exactly t+1..t+h."""

import math

import numpy as np
import pandas as pd
import pytest

from obsidian_rl.features.labels import (
    forward_executable_net_return,
    forward_log_return,
    signed_directional_net_edge,
)

# ── forward_log_return ────────────────────────────────────────────────────────


def test_forward_log_return_hand_calculated() -> None:
    close = pd.Series([100.0, 110.0, 121.0, 133.1, 146.41])
    lbl = forward_log_return(close, horizon=2)
    # label[0] = log(close[2]/close[0]) = log(1.21)
    assert lbl.iloc[0] == pytest.approx(math.log(1.21))
    assert lbl.iloc[2] == pytest.approx(math.log(146.41 / 121.0))
    assert np.isnan(lbl.iloc[3]) and np.isnan(lbl.iloc[4])  # horizon exceeds data


def test_label_uses_only_future_values() -> None:
    """Changing any candle at <= t must not change the label at t (given fixed close[t])."""
    close = pd.Series([100.0, 105.0, 110.0, 120.0, 125.0, 130.0])
    base = forward_log_return(close, horizon=2)
    tampered = close.copy()
    tampered.iloc[0] = 999.0  # strictly past value relative to t=1
    after = forward_log_return(tampered, horizon=2)
    assert after.iloc[1] == pytest.approx(base.iloc[1])


def test_label_changes_with_future_values() -> None:
    close = pd.Series([100.0, 105.0, 110.0, 120.0, 125.0, 130.0])
    base = forward_log_return(close, horizon=2)
    tampered = close.copy()
    tampered.iloc[3] = 200.0  # inside t=1's horizon window
    after = forward_log_return(tampered, horizon=2)
    assert after.iloc[1] != pytest.approx(base.iloc[1])


# ── signed_directional_net_edge ────────────────────────────────────────────────


def test_signed_directional_net_edge_rising_prices() -> None:
    """Rising open prices → positive gross → positive net edge."""
    # entry=open[1]=102, exit=open[3]=106 (horizon=2)
    # gross = log(106/102), label = gross - cost  (positive case)
    open_ = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0])
    cost = 0.002
    lbl = signed_directional_net_edge(open_, horizon=2, round_trip_cost=cost)
    gross = math.log(106.0 / 102.0)
    expected = gross - cost  # sign(gross)=+1, abs(gross)-cost > 0
    assert lbl.iloc[0] == pytest.approx(expected)


def test_signed_directional_net_edge_falling_prices() -> None:
    """Falling open prices → negative gross → negative net edge."""
    # entry=open[1]=98, exit=open[3]=94 (horizon=2)
    open_ = pd.Series([100.0, 98.0, 96.0, 94.0, 92.0])
    cost = 0.002
    lbl = signed_directional_net_edge(open_, horizon=2, round_trip_cost=cost)
    gross = math.log(94.0 / 98.0)  # negative
    expected = gross + cost  # sign=-1: -1 * (abs(gross) - cost) = gross + cost
    assert lbl.iloc[0] == pytest.approx(expected)


def test_signed_directional_equal_and_opposite_moves() -> None:
    """Equal magnitude up and down moves should produce equal and opposite edge values."""
    # Rise: open[1]=100 -> open[3]=105
    # Fall: open[1]=105 -> open[3]=100
    cost = 0.001
    open_up = pd.Series([99.0, 100.0, 102.0, 105.0, 106.0])
    open_dn = pd.Series([106.0, 105.0, 102.0, 100.0, 99.0])
    lbl_up = signed_directional_net_edge(open_up, horizon=2, round_trip_cost=cost)
    lbl_dn = signed_directional_net_edge(open_dn, horizon=2, round_trip_cost=cost)
    assert lbl_up.iloc[0] == pytest.approx(-lbl_dn.iloc[0])


def test_signed_directional_sub_cost_move_returns_zero() -> None:
    """A gross move smaller than the cost in either direction returns exactly zero."""
    cost = 0.01
    # tiny up move: gross = log(101/100) ≈ 0.00995 < cost=0.01
    open_tiny_up = pd.Series([99.0, 100.0, 100.5, 101.0, 101.5])
    lbl = signed_directional_net_edge(open_tiny_up, horizon=2, round_trip_cost=cost)
    gross = math.log(101.0 / 100.0)
    assert abs(gross) < cost  # precondition check
    assert lbl.iloc[0] == pytest.approx(0.0)


def test_signed_directional_zero_cost() -> None:
    """With zero cost the net edge equals the gross log-return (signed)."""
    open_ = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0])
    lbl = signed_directional_net_edge(open_, horizon=2, round_trip_cost=0.0)
    gross = math.log(106.0 / 102.0)
    assert lbl.iloc[0] == pytest.approx(gross)


def test_signed_directional_trailing_nan_rows() -> None:
    """Last (horizon+1) rows must be NaN; earlier rows must be finite."""
    open_ = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0, 110.0])
    horizon = 2
    lbl = signed_directional_net_edge(open_, horizon=horizon, round_trip_cost=0.001)
    # rows 0..len-horizon-2 should be finite
    # rows len-horizon-1..end should be NaN
    n = len(open_)
    for i in range(n - horizon - 1):
        assert math.isfinite(lbl.iloc[i]), f"row {i} should be finite"
    for i in range(n - horizon - 1, n):
        assert math.isnan(lbl.iloc[i]), f"row {i} should be NaN"


def test_signed_directional_index_alignment() -> None:
    """Output index must match input index exactly."""
    idx = pd.RangeIndex(10, 17)
    open_ = pd.Series([100.0 + i for i in range(7)], index=idx)
    lbl = signed_directional_net_edge(open_, horizon=2, round_trip_cost=0.001)
    assert list(lbl.index) == list(idx)


def test_signed_directional_invalid_horizon_bool() -> None:
    s = pd.Series([100.0, 102.0, 104.0])
    with pytest.raises(ValueError, match="horizon"):
        signed_directional_net_edge(s, True, 0.001)  # type: ignore[arg-type]


def test_signed_directional_invalid_horizon_zero() -> None:
    s = pd.Series([100.0, 102.0, 104.0])
    with pytest.raises(ValueError, match="horizon"):
        signed_directional_net_edge(s, 0, 0.001)


def test_signed_directional_invalid_cost_negative() -> None:
    s = pd.Series([100.0, 102.0, 104.0])
    with pytest.raises(ValueError, match="round_trip_cost"):
        signed_directional_net_edge(s, 1, -0.001)


def test_signed_directional_invalid_cost_nan() -> None:
    s = pd.Series([100.0, 102.0, 104.0])
    with pytest.raises(ValueError, match="round_trip_cost"):
        signed_directional_net_edge(s, 1, float("nan"))


def test_signed_directional_invalid_cost_bool() -> None:
    s = pd.Series([100.0, 102.0, 104.0])
    with pytest.raises(ValueError, match="round_trip_cost"):
        signed_directional_net_edge(s, 1, True)  # type: ignore[arg-type]


def test_signed_directional_invalid_prices_non_positive() -> None:
    s = pd.Series([100.0, 0.0, 104.0])
    with pytest.raises(ValueError, match="strictly positive"):
        signed_directional_net_edge(s, 1, 0.001)


def test_signed_directional_invalid_prices_nonfinite() -> None:
    s = pd.Series([100.0, float("inf"), 104.0])
    with pytest.raises(ValueError, match="non-finite"):
        signed_directional_net_edge(s, 1, 0.001)


# ── horizon validation (forward_log_return + forward_executable_net_return) ──


def test_horizon_validation() -> None:
    s = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        forward_log_return(s, 0)
    with pytest.raises(ValueError):
        forward_log_return(s, True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        forward_executable_net_return(s, 0, 0.0)


def test_executable_net_return_entry_exit_prices() -> None:
    open_ = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0])
    lbl = forward_executable_net_return(open_, horizon=2, round_trip_cost=0.001)
    # decision after candle 0 closes: entry open[1]=102, exit open[3]=106
    assert lbl.iloc[0] == pytest.approx(math.log(106.0 / 102.0) - 0.001)
    assert np.isnan(lbl.iloc[2])  # exit would be open[5], beyond data
