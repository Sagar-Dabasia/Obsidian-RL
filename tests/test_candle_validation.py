"""Candle schema + validation tests."""

import pandas as pd
import pytest

from obsidian_rl.data.schema import (
    SchemaError,
    interval_to_ms,
    klines_to_frame,
)
from obsidian_rl.data.validation import (
    CandleValidationError,
    drop_unfinalized,
    require_valid,
    validate_candles,
)
from tests.conftest import make_candles

MS15 = interval_to_ms("15m")


def test_klines_to_frame_maps_rest_field_order() -> None:
    raw = [
        [
            1000 * MS15,
            "100.0",
            "101.0",
            "99.5",
            "100.5",
            "12.5",
            1000 * MS15 + MS15 - 1,
            "1256.25",
            42,
            "6.25",
            "628.12",
            "0",
        ],
    ]
    df = klines_to_frame(raw)
    row = df.iloc[0]
    assert row["open_time"] == 1000 * MS15
    assert row["open"] == 100.0
    assert row["high"] == 101.0
    assert row["low"] == 99.5
    assert row["close"] == 100.5
    assert row["volume"] == 12.5
    assert row["close_time"] == 1000 * MS15 + MS15 - 1
    assert row["trades"] == 42


def test_klines_to_frame_rejects_short_rows() -> None:
    with pytest.raises(SchemaError):
        klines_to_frame([[1, 2, 3]])


def test_valid_frame_passes(candles_100: pd.DataFrame) -> None:
    rep = validate_candles(candles_100, "15m")
    assert rep.ok and rep.n_rows == 100 and not rep.gaps


def test_duplicate_open_time_fails(candles_100: pd.DataFrame) -> None:
    df = pd.concat([candles_100, candles_100.iloc[[10]]], ignore_index=True)
    df = df.sort_values("open_time").reset_index(drop=True)
    rep = validate_candles(df, "15m")
    assert not rep.ok and rep.n_duplicates == 1


def test_gap_detected_and_counted(candles_100: pd.DataFrame) -> None:
    df = candles_100.drop(index=[50, 51]).reset_index(drop=True)
    rep = validate_candles(df, "15m")
    assert rep.ok  # gaps are not errors by default
    assert len(rep.gaps) == 1 and rep.n_missing_candles == 2
    strict = validate_candles(df, "15m", gaps_are_errors=True)
    assert not strict.ok


def test_unsorted_fails(candles_100: pd.DataFrame) -> None:
    df = candles_100.iloc[::-1].reset_index(drop=True)
    assert not validate_candles(df, "15m").ok


def test_bad_high_low_fails(candles_100: pd.DataFrame) -> None:
    df = candles_100.copy()
    df.loc[5, "high"] = df.loc[5, "low"] - 1.0
    assert not validate_candles(df, "15m").ok


def test_negative_price_fails(candles_100: pd.DataFrame) -> None:
    df = candles_100.copy()
    df.loc[3, "close"] = -1.0
    assert not validate_candles(df, "15m").ok


def test_misaligned_open_time_fails(candles_100: pd.DataFrame) -> None:
    df = candles_100.copy()
    df.loc[0, "open_time"] += 1
    df.loc[0, "close_time"] += 1
    assert not validate_candles(df, "15m").ok


def test_wrong_close_time_fails(candles_100: pd.DataFrame) -> None:
    df = candles_100.copy()
    df.loc[7, "close_time"] += 5
    assert not validate_candles(df, "15m").ok


def test_unfinalized_final_candle_fails_and_is_droppable(candles_100: pd.DataFrame) -> None:
    now_ms = int(candles_100["close_time"].iloc[-1])  # equal => not yet finalized
    rep = validate_candles(candles_100, "15m", now_ms=now_ms)
    assert not rep.ok
    trimmed = drop_unfinalized(candles_100, now_ms)
    assert len(trimmed) == 99
    assert validate_candles(trimmed, "15m", now_ms=now_ms).ok


def test_require_valid_raises() -> None:
    df = make_candles(10)
    df.loc[2, "volume"] = -5.0
    with pytest.raises(CandleValidationError):
        require_valid(df, "15m")


def test_nan_fails(candles_100: pd.DataFrame) -> None:
    df = candles_100.copy()
    df.loc[9, "close"] = float("nan")
    assert not validate_candles(df, "15m").ok
