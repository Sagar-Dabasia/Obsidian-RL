from unittest.mock import Mock

import pytest

from obsidian_rl.data.contracts import AssetClass, MarketBar, QuoteStatus, Timeframe, VolumeType
from obsidian_rl.data.historical_dataset import ingest_historical_range
from obsidian_rl.data.storage import SQLiteStorage


def test_historical_dataset_rejects_empty(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"

    with SQLiteStorage(db_path) as storage, pytest.raises(RuntimeError):
        ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="FAKECOIN",
            timeframe=Timeframe.H4,
            start_ms=1000000000000,
            end_ms=1000000000001,
            storage=storage,
        )


def make_bar(ts: int) -> MarketBar:
    return MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.H4,
        timestamp_utc=ts,
        observed_at_utc=ts + 1,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.BASE,
        volume=1.0,
        data_source="MOCK",
        schema_version="SCHEMA_V2",
    )


def test_eval_gap_fails(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "eval.sqlite"
    eval_start_ms = 1577836800000  # 2020-01-01

    # 4h = 14400000 ms
    bars = []
    # Gen bars with a gap at eval_start_ms + 14400000
    for i in range(10):
        if i == 5:
            continue  # Skip to create gap
        bars.append(make_bar(eval_start_ms + i * 14400000))

    mock_provider = Mock()

    def mock_fetch_bars(sym, tf, start, end):
        return [b for b in bars if start <= b.timestamp_utc < end]

    mock_provider.fetch_bars.side_effect = mock_fetch_bars
    monkeypatch.setattr(
        "obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider
    )

    with (
        SQLiteStorage(db_path) as storage,
        pytest.raises(ValueError, match="Unrecoverable evaluation gap"),
    ):
        ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_ms=eval_start_ms,
            end_ms=eval_start_ms + 10 * 14400000,
            storage=storage,
        )


def test_warmup_gap_success_721_bars(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "warmup_ok.sqlite"
    eval_start_ms = 1577836800000  # 2020-01-01

    # Gap at eval_start_ms - 800 * 4h.
    # So we have 800 continuous bars before eval.
    bars = []
    start_ts = eval_start_ms - 800 * 14400000

    bars.append(make_bar(start_ts - 2 * 14400000))
    bars.append(make_bar(start_ts - 1 * 14400000))
    # GAP at start_ts
    for i in range(1, 801):
        bars.append(make_bar(start_ts + i * 14400000))

    mock_provider = Mock()

    def mock_fetch_bars(sym, tf, start, end):
        return [b for b in bars if start <= b.timestamp_utc < end]

    mock_provider.fetch_bars.side_effect = mock_fetch_bars
    monkeypatch.setattr(
        "obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider
    )

    with SQLiteStorage(db_path) as storage:
        manifest = ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_ms=start_ts - 2 * 14400000,
            end_ms=eval_start_ms + 14400000,  # one bar into eval
            storage=storage,
        )
        assert manifest.row_count == 800


def test_warmup_gap_fails_short(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "warmup_fail.sqlite"
    eval_start_ms = 1577836800000  # 2020-01-01

    # Gap at eval_start_ms - 700 * 4h.
    bars = []
    start_ts = eval_start_ms - 700 * 14400000

    bars.append(make_bar(start_ts - 2 * 14400000))
    bars.append(make_bar(start_ts - 1 * 14400000))
    # GAP at start_ts
    for i in range(1, 701):
        bars.append(make_bar(start_ts + i * 14400000))

    mock_provider = Mock()

    def mock_fetch_bars(sym, tf, start, end):
        return [b for b in bars if start <= b.timestamp_utc < end]

    mock_provider.fetch_bars.side_effect = mock_fetch_bars
    monkeypatch.setattr(
        "obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider
    )

    with (
        SQLiteStorage(db_path) as storage,
        pytest.raises(ValueError, match="Insufficient continuous warm-up bars"),
    ):
        ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_ms=start_ts - 2 * 14400000,
            end_ms=eval_start_ms + 14400000,
            storage=storage,
            min_warmup_bars=721,
        )
