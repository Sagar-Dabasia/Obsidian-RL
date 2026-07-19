"""Canonical candle schema shared by training, evaluation, replay, and live paper trading.

Timestamps are UTC epoch milliseconds. `open_time` is the canonical key; for a candle of
interval I, close_time == open_time + I - 1 ms (Binance convention).
"""

from collections.abc import Sequence

import pandas as pd

CANDLE_DTYPES: dict[str, str] = {
    "open_time": "int64",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "close_time": "int64",
    "quote_volume": "float64",
    "trades": "int64",
    "taker_buy_volume": "float64",
    "taker_buy_quote_volume": "float64",
}
CANDLE_COLUMNS: list[str] = list(CANDLE_DTYPES)

INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class SchemaError(ValueError):
    """Raised when data does not conform to the canonical candle schema."""


def interval_to_ms(interval: str) -> int:
    try:
        return INTERVAL_MS[interval]
    except KeyError as exc:
        raise SchemaError(f"unsupported interval {interval!r}") from exc


def empty_candle_frame() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=d) for c, d in CANDLE_DTYPES.items()})


def klines_to_frame(raw: Sequence[Sequence[object]]) -> pd.DataFrame:
    """Convert Binance 12-field kline arrays (REST or Vision CSV rows) to the canonical frame.

    Field order per official docs: openTime, open, high, low, close, volume, closeTime,
    quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore.
    """
    if len(raw) == 0:
        return empty_candle_frame()
    for row in raw:
        if len(row) < 11:
            raise SchemaError(f"kline row has {len(row)} fields, expected >= 11")
    df = pd.DataFrame(
        [list(row[:11]) for row in raw],
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_volume",
            "taker_buy_quote_volume",
        ],
    )
    df = df[CANDLE_COLUMNS].astype(CANDLE_DTYPES)
    return df


def coerce_candle_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Validate columns and coerce dtypes; raise SchemaError on mismatch."""
    missing = [c for c in CANDLE_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"missing candle columns: {missing}")
    out = df[CANDLE_COLUMNS].astype(CANDLE_DTYPES)
    return out.reset_index(drop=True)


def open_time_to_utc(open_time_ms: "pd.Series[int]") -> pd.Series:
    return pd.to_datetime(open_time_ms, unit="ms", utc=True)
