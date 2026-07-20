"""Parquet candle store tests: partitioning, idempotent merge, conflict refusal."""

from pathlib import Path

import pandas as pd
import pytest

from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.data.store import CandleStore, StoreConflictError
from tests.conftest import make_candles

MS15 = interval_to_ms("15m")
MONTH_MS = 31 * 24 * 3600 * 1000


def test_write_read_roundtrip(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(50)
    result = store.write(df, source="test")
    assert result.rows_new == 50
    out = store.read()
    pd.testing.assert_frame_equal(out, df.reset_index(drop=True), check_exact=False)


def test_idempotent_rewrite(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(50)
    store.write(df, source="a")
    result = store.write(df, source="b")
    assert result.rows_new == 0
    assert len(store.read()) == 50


def test_incremental_merge_and_max_open_time(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(100)
    store.write(df.iloc[:60], source="part1")
    store.write(df.iloc[60:], source="part2")
    out = store.read()
    assert len(out) == 100
    assert store.max_open_time() == int(df["open_time"].iloc[-1])


def test_conflicting_rows_raise(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(10)
    store.write(df, source="orig")
    tampered = df.copy()
    tampered.loc[4, "close"] = tampered.loc[4, "close"] + 123.0
    with pytest.raises(StoreConflictError):
        store.write(tampered, source="tampered")


def test_conflict_raised_on_new_partition(tmp_path: Path) -> None:
    """Regression (review): conflicting rows for the same open_time must raise even when
    the partition does not yet exist (not be silently dropped by drop_duplicates)."""
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(10)
    conflicting = df.iloc[[4]].copy()
    conflicting.loc[conflicting.index[0], "close"] += 500.0  # same open_time, diff close
    tampered = pd.concat([df, conflicting], ignore_index=True)
    with pytest.raises(StoreConflictError):
        store.write(tampered, source="new-partition-conflict")


def test_exact_duplicate_rows_ok_on_new_partition(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(10)
    dup = pd.concat([df, df.iloc[[4]]], ignore_index=True)  # identical row => dedupe, no raise
    result = store.write(dup, source="new-partition-dup")
    assert result.rows_new == 10
    assert len(store.read()) == 10


def test_cross_month_partitioning(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    jan = make_candles(10, start_ms=1_704_067_200_000)  # 2024-01-01 UTC
    feb = make_candles(10, start_ms=1_706_745_600_000)  # 2024-02-01 UTC
    store.write(pd.concat([jan, feb], ignore_index=True), source="two-months")
    files = list(store.base.rglob("*.parquet"))
    assert len(files) == 2
    assert store.summary()["rows"] == 20


def test_read_range_filter(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    df = make_candles(50)
    store.write(df, source="test")
    mid = int(df["open_time"].iloc[25])
    out = store.read(start_ms=mid, end_ms=mid + 5 * MS15)
    assert len(out) == 6
    assert int(out["open_time"].iloc[0]) == mid


def test_metadata_records_sources(tmp_path: Path) -> None:
    store = CandleStore(tmp_path, "BTCUSDT", "15m")
    store.write(make_candles(5), source="vision:2024-01")
    meta = store._load_meta()
    writes = meta["writes"]
    assert isinstance(writes, list) and writes[0]["source"] == "vision:2024-01"
    assert writes[0]["downloaded_at_utc_ms"] > 0
