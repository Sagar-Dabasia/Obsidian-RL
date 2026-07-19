"""Forward labels for supervised models (Alpha Gate).

The label at row t uses ONLY future information from rows t+1..t+horizon — proven by
hand-calculated tests. Rows whose horizon extends past the end of data get NaN and must
be dropped by the caller, never filled.
"""

import numpy as np
import pandas as pd


def forward_log_return(close: pd.Series, horizon: int) -> pd.Series:
    """log(close[t+horizon] / close[t]). NaN for the last `horizon` rows."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    result: pd.Series = np.log(close.shift(-horizon) / close)
    return result


def forward_executable_net_return(
    open_: pd.Series, horizon: int, round_trip_cost: float
) -> pd.Series:
    """Executable directional net log return for a decision made after candle t closes.

    Entry at open[t+1], exit at open[t+1+horizon]; round-trip costs subtracted.
    This is the honest target for 'was entering after candle t worth it, net of costs'.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    entry = open_.shift(-1)
    exit_ = open_.shift(-1 - horizon)
    result: pd.Series = np.log(exit_ / entry) - round_trip_cost
    return result
