"""Forward-label correctness: label at t uses exactly t+1..t+h."""

import math

import numpy as np
import pandas as pd
import pytest

from obsidian_rl.features.labels import forward_executable_net_return, forward_log_return


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


def test_executable_net_return_entry_exit_prices() -> None:
    open_ = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0])
    lbl = forward_executable_net_return(open_, horizon=2, round_trip_cost=0.001)
    # decision after candle 0 closes: entry open[1]=102, exit open[3]=106
    assert lbl.iloc[0] == pytest.approx(math.log(106.0 / 102.0) - 0.001)
    assert np.isnan(lbl.iloc[2])  # exit would be open[5], beyond data


def test_horizon_validation() -> None:
    s = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        forward_log_return(s, 0)
    with pytest.raises(ValueError):
        forward_executable_net_return(s, 0, 0.0)
