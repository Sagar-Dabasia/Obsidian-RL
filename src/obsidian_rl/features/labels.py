"""Forward labels for supervised models (Alpha Gate).

The label at row t uses ONLY future information from rows t+1..t+horizon — proven by
hand-calculated tests. Rows whose horizon extends past the end of data get NaN and must
be dropped by the caller, never filled.
"""

import math

import numpy as np
import pandas as pd

SIGNED_DIRECTIONAL_NET_EDGE_VERSION = "signed-directional-net-edge-v1"


def _validate_horizon_cost(horizon: int, round_trip_cost: float) -> None:
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a non-bool integer >= 1")
    if (
        isinstance(round_trip_cost, bool)
        or not isinstance(round_trip_cost, (int, float))
        or not math.isfinite(round_trip_cost)
        or round_trip_cost < 0
    ):
        raise ValueError("round_trip_cost must be a finite non-bool numeric >= 0")


def _validate_prices(prices: pd.Series, name: str) -> None:
    if prices.isna().any():
        raise ValueError(f"{name} contains NaN")
    if not np.isfinite(prices.values).all():
        raise ValueError(f"{name} contains non-finite values")
    if (prices <= 0).any():
        raise ValueError(f"{name} must be strictly positive")


def forward_log_return(close: pd.Series, horizon: int) -> pd.Series:
    """log(close[t+horizon] / close[t]). NaN for the last `horizon` rows.

    Kept for compatibility; do NOT use as the Alpha Gate training target.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a non-bool integer >= 1")
    result: pd.Series = np.log(close.shift(-horizon) / close)
    return result


def forward_executable_net_return(
    open_: pd.Series, horizon: int, round_trip_cost: float
) -> pd.Series:
    """LEGACY long-only label: log(open[t+1+h] / open[t+1]) - cost.

    Kept for compatibility only; the signed directional label below is the
    correct Alpha Gate training target.
    """
    _validate_horizon_cost(horizon, round_trip_cost)
    entry = open_.shift(-1)
    exit_ = open_.shift(-1 - horizon)
    result: pd.Series = np.log(exit_ / entry) - round_trip_cost
    return result


def signed_directional_net_edge(
    open_: pd.Series, horizon: int, round_trip_cost: float
) -> pd.Series:
    """Signed executable directional edge.

    For a decision made after candle t closes:
      entry = open[t+1], exit = open[t+1+horizon]
      gross = log(exit / entry)
      label = sign(gross) * max(abs(gross) - round_trip_cost, 0)

    This correctly represents both long and short edge net of costs:
      long net return:  +gross - cost
      short net return: -gross - cost
    NaN for the last (horizon+1) rows (no valid entry or exit).
    """
    _validate_horizon_cost(horizon, round_trip_cost)
    # Validate non-NaN, finite, positive prices before computing
    known = open_.dropna()
    _validate_prices(known, "open_")
    entry = open_.shift(-1)
    exit_ = open_.shift(-1 - horizon)
    gross = np.log(exit_ / entry)
    result: pd.Series = np.sign(gross) * np.maximum(np.abs(gross) - round_trip_cost, 0.0)
    return result
