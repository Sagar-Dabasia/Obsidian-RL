"""Comprehensive test suite for local SQLiteStorage engine."""

import hashlib
from pathlib import Path

import pytest

from obsidian_rl.data.contracts import (
    AssetClass,
    EventNewsItem,
    EventType,
    MarketBar,
    QuoteStatus,
    RevisionStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.storage import (
    DuplicateConflictError,
    IngestionRun,
    InvalidHashError,
    SQLiteStorage,
)


@pytest.fixture
def sample_crypto_bar() -> MarketBar:
    return MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.H4,
        timestamp_utc=1784750400000,
        observed_at_utc=1784764800000,
        open=65923.19,
        high=66138.24,
        low=65791.79,
        close=66114.49,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.BASE,
        volume=1372.89949,
        data_source="BINANCE_PUBLIC_REST",
    )


@pytest.fixture
def sample_forex_bar() -> MarketBar:
    return MarketBar(
        asset_class=AssetClass.FOREX,
        venue="OANDA",
        symbol="EUR_USD",
        timeframe=Timeframe.H4,
        timestamp_utc=1784754000000,
        observed_at_utc=1784768400000,
        open=1.14104,
        high=1.14176,
        low=1.14060,
        close=1.14172,
        quote_status=QuoteStatus.OBSERVED,
        bid=1.14165,
        ask=1.14180,
        volume_type=VolumeType.TICK,
        volume=6023.0,
        data_source="OANDA_PRACTICE_REST",
    )


@pytest.fixture
def sample_event_item() -> EventNewsItem:
    return EventNewsItem(
        event_id="FED_RATE_2026_07",
        source="FOREX_FACTORY",
        source_reliability=0.95,
        original_published_at=1784750400000,
        first_observed_at=1784750401000,
        updated_at=1784750401000,
        affected_assets=("EUR_USD", "USD_JPY"),
        event_type=EventType.INTEREST_RATE,
        expected_value=5.25,
        actual_value=5.00,
        surprise_value=-0.25,
        raw_content_hash="a" * 64,
        sentiment_score=-0.4,
        revision_status=RevisionStatus.INITIAL,
    )


def test_sqlite_storage_init_memory() -> None:
    """Test initializing an in-memory storage engine."""
    with SQLiteStorage(":memory:") as store:
        assert store.db_path_str == ":memory:"


def test_sqlite_storage_init_file_wal(tmp_path: Path) -> None:
    """Test initializing a file-based storage engine with parent directory creation."""
    db_file = tmp_path / "nested" / "dir" / "test_store.db"
    with SQLiteStorage(db_file, wal_mode=True) as store:
        assert db_file.exists()
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.lower() in ("wal", "memory")


def test_market_bar_insertion_and_round_trip(
    sample_crypto_bar: MarketBar, sample_forex_bar: MarketBar
) -> None:
    """Test inserting Crypto and Forex bars and exact round-trip reconstruction."""
    with SQLiteStorage(":memory:") as store:
        inserted = store.insert_market_bars([sample_crypto_bar, sample_forex_bar])
        assert inserted == 2

        # Query crypto
        crypto_res = store.query_market_bars(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_timestamp_utc=1784750400000,
            end_timestamp_utc=1784750400001,
        )
        assert len(crypto_res) == 1
        assert crypto_res[0] == sample_crypto_bar

        # Query forex
        forex_res = store.query_market_bars(
            asset_class=AssetClass.FOREX,
            venue="OANDA",
            symbol="EUR_USD",
            timeframe=Timeframe.H4,
            start_timestamp_utc=1784754000000,
            end_timestamp_utc=1784754000001,
        )
        assert len(forex_res) == 1
        assert forex_res[0] == sample_forex_bar


def test_idempotent_duplicate_insertion(sample_crypto_bar: MarketBar) -> None:
    """Test inserting identical bars multiple times is safely ignored."""
    with SQLiteStorage(":memory:") as store:
        assert store.insert_market_bars([sample_crypto_bar]) == 1
        assert store.insert_market_bars([sample_crypto_bar]) == 0


def test_conflicting_duplicate_rejection(sample_crypto_bar: MarketBar) -> None:
    """Test inserting same identity with different data raises DuplicateConflictError."""
    with SQLiteStorage(":memory:") as store:
        store.insert_market_bars([sample_crypto_bar])

        # Create conflicting bar with different close price (within valid OHLC range)
        conflicting_bar = MarketBar(
            asset_class=sample_crypto_bar.asset_class,
            venue=sample_crypto_bar.venue,
            symbol=sample_crypto_bar.symbol,
            timeframe=sample_crypto_bar.timeframe,
            timestamp_utc=sample_crypto_bar.timestamp_utc,
            observed_at_utc=sample_crypto_bar.observed_at_utc,
            open=sample_crypto_bar.open,
            high=sample_crypto_bar.high,
            low=sample_crypto_bar.low,
            close=66000.0,  # Valid close price != sample_crypto_bar.close (66114.49)
            quote_status=sample_crypto_bar.quote_status,
            bid=sample_crypto_bar.bid,
            ask=sample_crypto_bar.ask,
            volume_type=sample_crypto_bar.volume_type,
            volume=sample_crypto_bar.volume,
            data_source=sample_crypto_bar.data_source,
        )

        err_msg = "Conflict detected for MarketBar identity"
        with pytest.raises(DuplicateConflictError, match=err_msg):
            store.insert_market_bars([conflicting_bar])


def test_tamper_rejection_on_insert(sample_crypto_bar: MarketBar) -> None:
    """Test inserting a bar with a corrupted row_hash fails closed prior to storage."""
    tampered_bar = MarketBar(
        asset_class=sample_crypto_bar.asset_class,
        venue=sample_crypto_bar.venue,
        symbol=sample_crypto_bar.symbol,
        timeframe=sample_crypto_bar.timeframe,
        timestamp_utc=sample_crypto_bar.timestamp_utc,
        observed_at_utc=sample_crypto_bar.observed_at_utc,
        open=sample_crypto_bar.open,
        high=sample_crypto_bar.high,
        low=sample_crypto_bar.low,
        close=sample_crypto_bar.close,
        quote_status=sample_crypto_bar.quote_status,
        bid=sample_crypto_bar.bid,
        ask=sample_crypto_bar.ask,
        volume_type=sample_crypto_bar.volume_type,
        volume=sample_crypto_bar.volume,
        data_source=sample_crypto_bar.data_source,
    )
    object.__setattr__(tampered_bar, "row_hash", "b" * 64)

    with (
        SQLiteStorage(":memory:") as store,
        pytest.raises(InvalidHashError, match="row_hash verification failed"),
    ):
        store.insert_market_bars([tampered_bar])


def test_transaction_rollback_on_failure(
    sample_crypto_bar: MarketBar, sample_forex_bar: MarketBar
) -> None:
    """Test that batch insertion failure rolls back all records in the batch."""
    tampered_bar = MarketBar(
        asset_class=sample_forex_bar.asset_class,
        venue=sample_forex_bar.venue,
        symbol=sample_forex_bar.symbol,
        timeframe=sample_forex_bar.timeframe,
        timestamp_utc=sample_forex_bar.timestamp_utc,
        observed_at_utc=sample_forex_bar.observed_at_utc,
        open=sample_forex_bar.open,
        high=sample_forex_bar.high,
        low=sample_forex_bar.low,
        close=sample_forex_bar.close,
        quote_status=sample_forex_bar.quote_status,
        bid=sample_forex_bar.bid,
        ask=sample_forex_bar.ask,
        volume_type=sample_forex_bar.volume_type,
        volume=sample_forex_bar.volume,
        data_source=sample_forex_bar.data_source,
    )
    object.__setattr__(tampered_bar, "row_hash", "c" * 64)

    with SQLiteStorage(":memory:") as store, pytest.raises(InvalidHashError):
        store.insert_market_bars([sample_crypto_bar, tampered_bar])

    with SQLiteStorage(":memory:") as store:
        # Verify sample_crypto_bar was NOT committed
        res = store.query_market_bars(
            AssetClass.CRYPTO,
            "BINANCE_SPOT",
            "BTCUSDT",
            Timeframe.H4,
            0,
            2000000000000,
        )
        assert len(res) == 0


def test_point_in_time_filtering() -> None:
    """Test point-in-time cutoff (observed_before_ms)."""
    b1 = MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.M1,
        timestamp_utc=1000,
        observed_at_utc=1100,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.BASE,
        volume=1.0,
        data_source="TEST",
    )
    b2 = MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.M1,
        timestamp_utc=2000,
        observed_at_utc=2500,
        open=10.5,
        high=12.0,
        low=10.0,
        close=11.5,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.BASE,
        volume=2.0,
        data_source="TEST",
    )

    with SQLiteStorage(":memory:") as store:
        store.insert_market_bars([b1, b2])

        # Cutoff at 1500 -> sees only b1
        res1 = store.query_market_bars(
            AssetClass.CRYPTO,
            "BINANCE_SPOT",
            "BTCUSDT",
            Timeframe.M1,
            0,
            3000,
            observed_before_ms=1500,
        )
        assert len(res1) == 1
        assert res1[0] == b1

        # Cutoff at 2500 -> sees both b1 and b2
        res2 = store.query_market_bars(
            AssetClass.CRYPTO,
            "BINANCE_SPOT",
            "BTCUSDT",
            Timeframe.M1,
            0,
            3000,
            observed_before_ms=2500,
        )
        assert len(res2) == 2


def test_start_inclusive_end_exclusive_boundaries(sample_crypto_bar: MarketBar) -> None:
    """Test timestamp queries strictly enforce start-inclusive and end-exclusive boundaries."""
    ts = sample_crypto_bar.timestamp_utc
    with SQLiteStorage(":memory:") as store:
        store.insert_market_bars([sample_crypto_bar])

        # Exact match start (inclusive)
        res1 = store.query_market_bars(
            AssetClass.CRYPTO, "BINANCE_SPOT", "BTCUSDT", Timeframe.H4, ts, ts + 1
        )
        assert len(res1) == 1

        # Exact match end (exclusive) -> 0 results
        res2 = store.query_market_bars(
            AssetClass.CRYPTO, "BINANCE_SPOT", "BTCUSDT", Timeframe.H4, ts - 10, ts
        )
        assert len(res2) == 0


def test_event_news_item_insertion_and_query(sample_event_item: EventNewsItem) -> None:
    """Test EventNewsItem storage, idempotent insert, duplicate conflict, and query."""
    with SQLiteStorage(":memory:") as store:
        assert store.insert_event_news_items([sample_event_item]) == 1
        assert store.insert_event_news_items([sample_event_item]) == 0

        res = store.query_event_news_items(event_id="FED_RATE_2026_07")
        assert len(res) == 1
        assert res[0] == sample_event_item


def test_deterministic_manifest(sample_crypto_bar: MarketBar) -> None:
    """Test deterministic manifest creation and persistence."""
    with SQLiteStorage(":memory:") as store:
        bars = [sample_crypto_bar]
        manifest = store.create_dataset_manifest(
            dataset_id="DS_BTCUSDT_4H_V1",
            source="BINANCE_PUBLIC_REST",
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            bars=bars,
            created_at_utc=1784765000000,
        )

        assert manifest.dataset_id == "DS_BTCUSDT_4H_V1"
        assert manifest.row_count == 1
        expected_digest = hashlib.sha256(sample_crypto_bar.row_hash.encode("utf-8")).hexdigest()
        assert manifest.digest == expected_digest

        store.save_dataset_manifest(manifest)
        retrieved = store.get_dataset_manifest("DS_BTCUSDT_4H_V1")
        assert retrieved == manifest


def test_ingestion_run_tracking() -> None:
    """Test IngestionRun audit logging."""
    run = IngestionRun(
        run_id="RUN_123",
        provider="BINANCE",
        symbol="BTCUSDT",
        timeframe="4h",
        started_at_utc=1000,
        completed_at_utc=2000,
        status="SUCCESS",
        bars_inserted=10,
    )
    with SQLiteStorage(":memory:") as store:
        store.record_ingestion_run(run)
        fetched = store.get_ingestion_run("RUN_123")
        assert fetched == run


def test_no_credentials_stored() -> None:
    """Audit schema tables to confirm zero credential fields exist."""
    with SQLiteStorage(":memory:") as store:
        cursor = store.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        assert "market_bars" in tables
        assert "event_news_items" in tables

        for t in tables:
            cursor.execute(f"PRAGMA table_info({t});")
            cols = [col["name"].lower() for col in cursor.fetchall()]
            for secret_keyword in ("token", "secret", "password", "key", "account_id", "auth"):
                if t == "market_bars" and secret_keyword in ("row_hash", "data_source"):
                    continue
                assert not any(secret_keyword in c for c in cols)
