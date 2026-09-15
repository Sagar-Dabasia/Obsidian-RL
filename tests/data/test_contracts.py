"""Unit tests for canonical data contracts (`MarketBar`, `EventNewsItem`)."""

import dataclasses
import time

import pytest

from obsidian_rl.data.contracts import (
    SCHEMA_VERSION_V2,
    AssetClass,
    EventNewsItem,
    EventType,
    MarketBar,
    QuoteStatus,
    RevisionStatus,
    Timeframe,
    VolumeType,
    from_dict,
    to_dict,
    validate_ingestion_time,
)
from obsidian_rl.data.fingerprint import (
    compute_event_news_hash,
    compute_market_bar_hash,
)

DUMMY_RAW_HASH = "a" * 64


def sample_market_bar(**kwargs: object) -> MarketBar:
    """Helper to create a valid sample MarketBar, allowing field overrides."""
    now_ms = int(time.time() * 1000) - 60_000
    defaults: dict[str, object] = {
        "asset_class": AssetClass.CRYPTO,
        "venue": "BINANCE",
        "symbol": "BTCUSDT",
        "timeframe": Timeframe.M15,
        "timestamp_utc": now_ms - 900_000,
        "observed_at_utc": now_ms,
        "open": 100000.0,
        "high": 101000.0,
        "low": 99500.0,
        "close": 100500.0,
        "quote_status": QuoteStatus.OBSERVED,
        "bid": 100490.0,
        "ask": 100510.0,
        "volume_type": VolumeType.BASE,
        "volume": 25.5,
        "data_source": "BINANCE_WS",
        "schema_version": SCHEMA_VERSION_V2,
        "row_hash": "",
    }
    defaults.update(kwargs)
    return MarketBar(**defaults)  # type: ignore[arg-type]


def sample_event_news(**kwargs: object) -> EventNewsItem:
    """Helper to create a valid sample EventNewsItem, allowing field overrides."""
    now_ms = int(time.time() * 1000) - 60_000
    defaults: dict[str, object] = {
        "event_id": "evt-2026-001",
        "source": "OANDA_ECO_CAL",
        "source_reliability": 0.95,
        "original_published_at": now_ms - 1000,
        "first_observed_at": now_ms,
        "updated_at": now_ms,
        "affected_assets": ("EUR_USD", "BTCUSDT"),
        "event_type": EventType.INTEREST_RATE,
        "expected_value": 4.50,
        "actual_value": 4.75,
        "surprise_value": 1.25,
        "raw_content_hash": DUMMY_RAW_HASH,
        "sentiment_score": 0.35,
        "revision_status": RevisionStatus.INITIAL,
        "schema_version": SCHEMA_VERSION_V2,
        "record_hash": "",
    }
    defaults.update(kwargs)
    return EventNewsItem(**defaults)  # type: ignore[arg-type]


def test_market_bar_valid_construction_and_immutability() -> None:
    """Verify valid construction, auto-hash generation, and frozen attributes."""
    bar = sample_market_bar()
    assert bar.asset_class == AssetClass.CRYPTO
    assert bar.symbol == "BTCUSDT"
    assert bar.schema_version == SCHEMA_VERSION_V2
    assert len(bar.row_hash) == 64
    assert bar.row_hash == compute_market_bar_hash(bar)

    with pytest.raises(dataclasses.FrozenInstanceError):
        bar.close = 102000.0  # type: ignore[misc]


def test_market_bar_rejects_bools_and_non_numbers() -> None:
    """Verify that bools are rejected for numerical fields where int/float is required."""
    with pytest.raises(TypeError, match="must be float or int"):
        sample_market_bar(open=True)
    with pytest.raises(TypeError, match="must be float or int"):
        sample_market_bar(volume=False)
    with pytest.raises(TypeError, match="must be an integer"):
        sample_market_bar(timestamp_utc=True)
    with pytest.raises(TypeError, match="must be an integer"):
        sample_market_bar(observed_at_utc=False)


def test_market_bar_rejects_nan_and_infinity() -> None:
    """Verify that NaN and Infinity are rejected for all price and volume fields."""
    with pytest.raises(ValueError, match="must be finite"):
        sample_market_bar(open=float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        sample_market_bar(high=float("inf"))
    with pytest.raises(ValueError, match="must be finite"):
        sample_market_bar(low=float("-inf"))
    with pytest.raises(ValueError, match="must be finite"):
        sample_market_bar(volume=float("nan"))


def test_market_bar_price_and_volume_invariants() -> None:
    """Verify OHLC, bid/ask ordering, and non-negative volume enforcement."""
    with pytest.raises(ValueError, match="strictly positive"):
        sample_market_bar(open=-100.0)
    with pytest.raises(ValueError, match="must be >= open, low, and close"):
        sample_market_bar(high=98000.0)
    with pytest.raises(ValueError, match="must be <= open, high, and close"):
        sample_market_bar(high=110000.0, low=105000.0)
    with pytest.raises(ValueError, match="must be >= bid"):
        sample_market_bar(bid=100.0, ask=99.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        sample_market_bar(volume=-1.0)


def test_market_bar_enum_validation() -> None:
    """Verify strict enum instance checks and rejection of silent string conversion."""
    with pytest.raises(TypeError, match="no silent enum conversion"):
        sample_market_bar(asset_class="CRYPTO")
    with pytest.raises(TypeError, match="no silent enum conversion"):
        sample_market_bar(timeframe="15m")
    with pytest.raises(TypeError, match="no silent enum conversion"):
        sample_market_bar(quote_status="OBSERVED")
    with pytest.raises(TypeError, match="no silent enum conversion"):
        sample_market_bar(volume_type="BASE")


def test_market_bar_quote_and_volume_modes() -> None:
    """Verify crypto observed, forex unavailable/tick, and bar-only mode rules."""
    crypto_bar = sample_market_bar(
        asset_class=AssetClass.CRYPTO,
        quote_status=QuoteStatus.OBSERVED,
        bid=100.0,
        ask=100.2,
        volume_type=VolumeType.BASE,
        volume=15.0,
    )
    assert crypto_bar.quote_status == QuoteStatus.OBSERVED
    assert crypto_bar.volume_type == VolumeType.BASE

    forex_bar = sample_market_bar(
        asset_class=AssetClass.FOREX,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.TICK,
        volume=1200.0,
    )
    assert forex_bar.bid is None and forex_bar.ask is None
    assert forex_bar.volume_type == VolumeType.TICK

    bar_only = sample_market_bar(
        asset_class=AssetClass.EQUITY,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.NONE,
        volume=None,
    )
    assert bar_only.bid is None and bar_only.volume is None

    with pytest.raises(ValueError, match="both exist or both be None"):
        sample_market_bar(bid=100.0, ask=None)
    with pytest.raises(ValueError, match="requires both bid and ask to be None"):
        sample_market_bar(quote_status=QuoteStatus.UNAVAILABLE, bid=100.0, ask=100.2)
    with pytest.raises(ValueError, match="requires bid and ask to be present"):
        sample_market_bar(quote_status=QuoteStatus.OBSERVED, bid=None, ask=None)
    with pytest.raises(ValueError, match=r"VolumeType\.NONE requires volume=None"):
        sample_market_bar(volume_type=VolumeType.NONE, volume=10.0)
    with pytest.raises(ValueError, match="requires finite volume >= 0, got None"):
        sample_market_bar(volume_type=VolumeType.BASE, volume=None)


def test_market_bar_timestamp_ordering_and_ingestion_time_check() -> None:
    """Verify observed_at_utc vs timestamp_utc ordering and deterministic ingestion checks."""
    now_ms = int(time.time() * 1000)
    with pytest.raises(ValueError, match="cannot be earlier than timestamp_utc"):
        sample_market_bar(timestamp_utc=now_ms - 1000, observed_at_utc=now_ms - 5000)

    bar = sample_market_bar(timestamp_utc=10000, observed_at_utc=12000)
    validate_ingestion_time(bar, current_time_ms=12000, max_clock_skew_ms=300_000)

    with pytest.raises(RuntimeError, match="Ingestion time validation failed for MarketBar"):
        validate_ingestion_time(bar, current_time_ms=1000, max_clock_skew_ms=5000)


def test_market_bar_serialization_and_tamper_rejection() -> None:
    """Verify round-trip dictionary serialization, unknown/missing field and tamper rejection."""
    bar = sample_market_bar()
    data = to_dict(bar)
    assert isinstance(data, dict)
    assert data["asset_class"] == "CRYPTO"
    assert data["timeframe"] == "15m"

    reconstructed = MarketBar.from_dict(data, verify_hash=True)
    assert reconstructed == bar
    assert from_dict(MarketBar, data) == bar

    data_unknown = dict(data)
    data_unknown["extra_injection"] = 123
    with pytest.raises(ValueError, match="Unknown fields rejected"):
        MarketBar.from_dict(data_unknown)

    data_missing = dict(data)
    del data_missing["open"]
    with pytest.raises(ValueError, match="Missing fields rejected"):
        MarketBar.from_dict(data_missing)

    data_tampered = dict(data)
    data_tampered["volume"] = 999999.0
    with pytest.raises(RuntimeError, match="MarketBar hash mismatch"):
        MarketBar.from_dict(data_tampered, verify_hash=True)


def test_event_news_valid_construction_and_immutability() -> None:
    """Verify valid EventNewsItem construction and automatic record_hash generation."""
    item = sample_event_news()
    assert item.event_id == "evt-2026-001"
    assert item.affected_assets == ("EUR_USD", "BTCUSDT")
    assert len(item.record_hash) == 64
    assert item.record_hash == compute_event_news_hash(item)

    with pytest.raises(dataclasses.FrozenInstanceError):
        item.sentiment_score = 0.0  # type: ignore[misc]


def test_event_news_rejects_bools_and_non_finite_values() -> None:
    """Verify bool rejection and finite value enforcement across parameters."""
    with pytest.raises(TypeError, match="must be float or int"):
        sample_event_news(source_reliability=True)
    with pytest.raises(TypeError, match="must be float or int"):
        sample_event_news(sentiment_score=False)
    with pytest.raises(ValueError, match=r"must be finite and in \[0.0, 1.0\]"):
        sample_event_news(source_reliability=1.5)
    with pytest.raises(ValueError, match=r"must be finite and in \[-1.0, 1.0\]"):
        sample_event_news(sentiment_score=-2.0)
    with pytest.raises(ValueError, match="must be finite"):
        sample_event_news(expected_value=float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        sample_event_news(actual_value=float("inf"))


def test_event_news_optional_values_and_affected_assets_governance() -> None:
    """Verify None expectations, tuple check, unique assets, and list coercion check."""
    item = sample_event_news(expected_value=None, actual_value=None, surprise_value=None)
    assert item.expected_value is None

    with pytest.raises(TypeError, match="rejecting list/set coercion"):
        sample_event_news(affected_assets=["AUD_USD", "ETHUSDT"])
    with pytest.raises(TypeError, match="rejecting list/set coercion"):
        sample_event_news(affected_assets={"AUD_USD"})
    with pytest.raises(ValueError, match="must be a non-empty tuple"):
        sample_event_news(affected_assets=())
    with pytest.raises(ValueError, match="elements must be unique"):
        sample_event_news(affected_assets=("AUD_USD", "AUD_USD"))


def test_event_news_enum_validation() -> None:
    """Verify strict enum check on EventType and RevisionStatus."""
    with pytest.raises(TypeError, match="no silent enum conversion"):
        sample_event_news(event_type="INTEREST_RATE")
    with pytest.raises(TypeError, match="no silent enum conversion"):
        sample_event_news(revision_status="INITIAL")


def test_event_news_timestamp_discipline_and_ingestion_validation() -> None:
    """Verify publication ordering and deterministic ingestion time check."""
    now_ms = int(time.time() * 1000)
    with pytest.raises(ValueError, match="cannot be earlier than original_published_at"):
        sample_event_news(original_published_at=now_ms, first_observed_at=now_ms - 100)
    with pytest.raises(ValueError, match="cannot be earlier than first_observed_at"):
        sample_event_news(first_observed_at=now_ms, updated_at=now_ms - 100)

    item = sample_event_news(original_published_at=1000, first_observed_at=1200, updated_at=1300)
    validate_ingestion_time(item, current_time_ms=1300, max_clock_skew_ms=300_000)

    with pytest.raises(RuntimeError, match="Ingestion time validation failed for EventNewsItem"):
        validate_ingestion_time(item, current_time_ms=100, max_clock_skew_ms=50)


def test_event_news_hash_separation_and_verification() -> None:
    """Verify separation between raw_content_hash and structured record_hash."""
    item1 = sample_event_news(raw_content_hash="1" * 64)
    item2 = sample_event_news(raw_content_hash="2" * 64)
    assert item1.raw_content_hash == "1" * 64
    assert item2.raw_content_hash == "2" * 64
    assert item1.record_hash != item2.record_hash

    with pytest.raises(RuntimeError, match="EventNewsItem hash mismatch"):
        sample_event_news(record_hash="f" * 64)


def test_event_news_serialization_and_tamper_rejection() -> None:
    """Verify round-trip serialization (converting list back to tuple) and tamper rejection."""
    item = sample_event_news()
    data = to_dict(item)
    assert isinstance(data["affected_assets"], list)
    assert data["event_type"] == "INTEREST_RATE"

    reconstructed = EventNewsItem.from_dict(data, verify_hash=True)
    assert reconstructed == item
    assert from_dict(EventNewsItem, data) == item

    data_tampered = dict(data)
    data_tampered["actual_value"] = 10.0
    with pytest.raises(RuntimeError, match="EventNewsItem hash mismatch"):
        EventNewsItem.from_dict(data_tampered, verify_hash=True)


def test_hard_coded_known_sha256_digests() -> None:
    """Verify exact hard-coded SHA-256 digests on fixed canonical fixtures."""
    fixed_bar = MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE",
        symbol="BTCUSDT",
        timeframe=Timeframe.M15,
        timestamp_utc=1700000000000,
        observed_at_utc=1700000001000,
        open=50000.0,
        high=51000.0,
        low=49500.0,
        close=50500.0,
        quote_status=QuoteStatus.OBSERVED,
        bid=50490.0,
        ask=50510.0,
        volume_type=VolumeType.BASE,
        volume=12.5,
        data_source="BINANCE_WS",
        schema_version="SCHEMA_V2",
    )
    assert (
        compute_market_bar_hash(fixed_bar)
        == "3bdb80912e6333efd5d0dde92897c0b97b0bc54969d9230af121cd41d5835693"
    )

    fixed_event = EventNewsItem(
        event_id="evt-fixed-001",
        source="OANDA",
        source_reliability=0.95,
        original_published_at=1700000000000,
        first_observed_at=1700000001000,
        updated_at=1700000002000,
        affected_assets=("EUR_USD", "GBP_USD"),
        event_type=EventType.INTEREST_RATE,
        expected_value=5.25,
        actual_value=5.50,
        surprise_value=0.25,
        raw_content_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        sentiment_score=0.1,
        revision_status=RevisionStatus.INITIAL,
        schema_version="SCHEMA_V2",
    )
    assert (
        compute_event_news_hash(fixed_event)
        == "22f74664005ac9c0897636df196fd5ec96169493a0553c059b3a4ae2694188c3"
    )
