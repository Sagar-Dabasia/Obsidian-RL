"""Comprehensive offline tests for the provider data ingestion pipeline."""

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.ingestion import ingest_provider_market_data
from obsidian_rl.data.storage import SQLiteStorage


def make_bar(
    timestamp_utc: int,
    observed_at_utc: int | None = None,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE_SPOT",
    asset_class: AssetClass = AssetClass.CRYPTO,
    timeframe: Timeframe = Timeframe.H4,
    close: float = 100.0,
) -> MarketBar:
    obs = observed_at_utc if observed_at_utc is not None else timestamp_utc + 14_400_000
    is_forex = asset_class == AssetClass.FOREX
    return MarketBar(
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc=timestamp_utc,
        observed_at_utc=obs,
        open=100.0,
        high=105.0,
        low=95.0,
        close=close,
        quote_status=QuoteStatus.OBSERVED if is_forex else QuoteStatus.UNAVAILABLE,
        bid=99.9 if is_forex else None,
        ask=100.1 if is_forex else None,
        volume_type=VolumeType.TICK if is_forex else VolumeType.BASE,
        volume=1000.0,
        data_source="TEST",
    )


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Provide a temporary database path for tests."""
    return tmp_path / "test_ingestion.sqlite"


@pytest.fixture
def mock_binance() -> Any:
    with mock.patch("obsidian_rl.data.ingestion.BinanceSpotProvider.fetch_bars") as m:
        yield m


@pytest.fixture
def mock_oanda() -> Any:
    with mock.patch("obsidian_rl.data.ingestion.OandaPracticeProvider.fetch_bars") as m:
        yield m


def test_binance_successful_ingestion(temp_db: Path, mock_binance: Any) -> None:
    """Test full successful Binance ingestion to storage."""
    t0 = 1784750400000
    step = 14_400_000
    bars = tuple(make_bar(t0 + i * step) for i in range(5))
    mock_binance.return_value = bars

    result = ingest_provider_market_data(
        provider_name="BINANCE",
        symbol="BTCUSDT",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=True,
        current_time_ms=t0 + 6 * step,
    )

    assert result.final_status == "SUCCESS"
    assert result.fetched_bars == 5
    assert result.rows_inserted == 5
    assert result.dry_run is False

    storage = SQLiteStorage(temp_db)
    stored_bars = storage.query_market_bars(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.H4,
        start_timestamp_utc=t0,
        end_timestamp_utc=t0 + 6 * step,
    )
    assert len(stored_bars) == 5
    storage.close()


def test_oanda_successful_ingestion(temp_db: Path, mock_oanda: Any) -> None:
    """Test full successful OANDA ingestion to storage."""
    t0 = 1784750400000
    step = 14_400_000
    bars = tuple(
        make_bar(
            t0 + i * step,
            symbol="EUR_USD",
            venue="OANDA_PRACTICE",
            asset_class=AssetClass.FOREX,
        )
        for i in range(5)
    )
    mock_oanda.return_value = bars

    result = ingest_provider_market_data(
        provider_name="OANDA",
        symbol="EUR_USD",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=True,
        api_token="FAKE_TOKEN",
        current_time_ms=t0 + 6 * step,
    )

    assert result.final_status == "SUCCESS"
    assert result.rows_inserted == 5


def test_oanda_weekend_expansion(temp_db: Path, mock_oanda: Any) -> None:
    """Test that OANDA request expands lookback across weekends to fulfill requested bars."""
    t_fri = 1784932800000  # Friday 20:00 UTC
    t_sun = 1785105600000  # Sunday 20:00 UTC
    step = 14_400_000  # 4h

    # We simulate a situation where the first fetch (the most recent period) only returns 2 bars
    # and the second fetch (the older period) returns 3 bars, fulfilling the 5 requested bars.
    chunk1 = tuple(
        make_bar(
            t_fri - (2 - i) * step,
            symbol="EUR_USD",
            venue="OANDA_PRACTICE",
            asset_class=AssetClass.FOREX,
        )
        for i in range(3)
    )
    chunk2 = tuple(
        make_bar(
            t_sun + i * step,
            symbol="EUR_USD",
            venue="OANDA_PRACTICE",
            asset_class=AssetClass.FOREX,
        )
        for i in range(2)
    )

    # mock_oanda will return chunk2 on the first call (most recent),
    # then chunk1 on the second call (older).
    # The logic fetches backwards in time.
    mock_oanda.side_effect = [chunk2, chunk1]

    result = ingest_provider_market_data(
        provider_name="OANDA",
        symbol="EUR_USD",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=True,
        api_token="FAKE_TOKEN",
        current_time_ms=t_sun + 3 * step,
    )

    assert result.final_status == "SUCCESS"
    assert result.fetched_bars == 5
    assert result.rows_inserted == 5
    assert mock_oanda.call_count == 2


def test_dry_run_performs_no_writes(temp_db: Path, mock_binance: Any) -> None:
    """Test dry_run does not write anything to database."""
    t0 = 1784750400000
    step = 14_400_000
    bars = tuple(make_bar(t0 + i * step) for i in range(5))
    mock_binance.return_value = bars

    result = ingest_provider_market_data(
        provider_name="BINANCE",
        symbol="BTCUSDT",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=False,
        current_time_ms=t0 + 6 * step,
    )

    assert result.final_status == "SUCCESS_DRY_RUN"
    assert result.fetched_bars == 5
    assert result.rows_inserted == 0
    assert result.manifest_id is not None
    assert "dry_manifest_" in result.manifest_id

    storage = SQLiteStorage(temp_db)
    stored_bars = storage.query_market_bars(
        AssetClass.CRYPTO, "BINANCE_SPOT", "BTCUSDT", Timeframe.H4, 0, 9999999999999
    )
    assert len(stored_bars) == 0
    storage.close()


def test_live_required_for_network_calls(temp_db: Path, mock_binance: Any) -> None:
    """Test --live is required."""
    with pytest.raises(ValueError, match="--live is required"):
        ingest_provider_market_data(
            provider_name="BINANCE",
            symbol="BTCUSDT",
            timeframe="4h",
            bars=5,
            db_path=temp_db,
            is_live=False,
            is_write=False,
        )
    assert not mock_binance.called


def test_idempotent_repeated_ingestion(temp_db: Path, mock_binance: Any) -> None:
    """Test inserting the exact same data twice properly ignores duplicates."""
    t0 = 1784750400000
    step = 14_400_000
    bars = tuple(make_bar(t0 + i * step) for i in range(5))
    mock_binance.return_value = bars

    res1 = ingest_provider_market_data(
        provider_name="BINANCE",
        symbol="BTCUSDT",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=True,
        current_time_ms=t0 + 6 * step,
    )
    assert res1.rows_inserted == 5
    assert res1.duplicates_ignored == 0

    res2 = ingest_provider_market_data(
        provider_name="BINANCE",
        symbol="BTCUSDT",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=True,
        current_time_ms=t0 + 6 * step,
    )
    assert res2.rows_inserted == 0
    assert res2.duplicates_ignored == 5


def test_quality_failure_blocks_writes(temp_db: Path, mock_binance: Any) -> None:
    """Test bad quality data fails validation and blocks writing."""
    t0 = 1784750400000
    step = 14_400_000
    # Missing bar 2
    bars = (
        make_bar(t0),
        make_bar(t0 + step),
        make_bar(t0 + 3 * step),
    )
    mock_binance.return_value = bars

    result = ingest_provider_market_data(
        provider_name="BINANCE",
        symbol="BTCUSDT",
        timeframe="4h",
        bars=5,
        db_path=temp_db,
        is_live=True,
        is_write=True,
        current_time_ms=t0 + 6 * step,
    )

    assert result.final_status == "FAILED_QUALITY"
    assert result.rows_inserted == 0

    storage = SQLiteStorage(temp_db)
    stored_bars = storage.query_market_bars(
        AssetClass.CRYPTO, "BINANCE_SPOT", "BTCUSDT", Timeframe.H4, 0, 9999999999999
    )
    assert len(stored_bars) == 0

    run_log = storage.get_ingestion_run(result.ingestion_run_id)
    assert run_log is not None
    assert run_log.status == "FAILED"
    assert "Quality validation failed" in str(run_log.error_message)
    storage.close()


def test_point_in_time_observation_enforcement(temp_db: Path, mock_binance: Any) -> None:
    """Test observation timestamps from future are rejected."""
    t0 = 1784750400000
    step = 14_400_000
    bars = tuple(make_bar(t0 + i * step, observed_at_utc=t0 + 10 * step) for i in range(2))
    mock_binance.return_value = bars

    with pytest.raises(ValueError, match="is in the future relative to current ingestion time"):
        ingest_provider_market_data(
            provider_name="BINANCE",
            symbol="BTCUSDT",
            timeframe="4h",
            bars=2,
            db_path=temp_db,
            is_live=True,
            is_write=True,
            current_time_ms=t0 + 5 * step,
        )


def test_invalid_bars_rejection(temp_db: Path) -> None:
    """Test bar limits."""
    with pytest.raises(ValueError, match="Invalid bars count"):
        ingest_provider_market_data(
            provider_name="BINANCE",
            symbol="BTCUSDT",
            timeframe="4h",
            bars=25,
            db_path=temp_db,
        )
    with pytest.raises(ValueError, match="Invalid bars count"):
        ingest_provider_market_data(
            provider_name="BINANCE",
            symbol="BTCUSDT",
            timeframe="4h",
            bars=0,
            db_path=temp_db,
        )


def test_unsupported_provider(temp_db: Path) -> None:
    """Test unknown provider rejection."""
    with pytest.raises(ValueError, match="Unsupported provider: FAKE"):
        ingest_provider_market_data(
            provider_name="FAKE",
            symbol="BTCUSDT",
            timeframe="4h",
            bars=5,
            db_path=temp_db,
        )
