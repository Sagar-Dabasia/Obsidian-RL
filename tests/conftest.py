"""Shared deterministic test fixtures. No network access anywhere in the test suite."""

import numpy as np
import pandas as pd
import pytest

from obsidian_rl.data.schema import interval_to_ms

BASE_OPEN_MS = 1_700_000_100_000 - (1_700_000_100_000 % 900_000)  # aligned 15m boundary


def make_candles(
    n: int,
    *,
    interval: str = "15m",
    start_ms: int = BASE_OPEN_MS,
    start_price: float = 50_000.0,
    seed: int = 7,
) -> pd.DataFrame:
    """Deterministic, valid candle frame for unit tests (clearly labelled test fixture)."""
    ms = interval_to_ms(interval)
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.002, size=n)
    closes = start_price * np.exp(np.cumsum(steps))
    opens = np.concatenate(([start_price], closes[:-1]))
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.001, size=n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.001, size=n))
    volume = rng.uniform(10, 100, size=n)
    open_time = start_ms + ms * np.arange(n, dtype=np.int64)
    return pd.DataFrame(
        {
            "open_time": open_time,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volume,
            "close_time": open_time + ms - 1,
            "quote_volume": volume * closes,
            "trades": rng.integers(100, 1000, size=n).astype("int64"),
            "taker_buy_volume": volume * 0.5,
            "taker_buy_quote_volume": volume * closes * 0.5,
        }
    )


@pytest.fixture
def candles_100() -> pd.DataFrame:
    return make_candles(100)
