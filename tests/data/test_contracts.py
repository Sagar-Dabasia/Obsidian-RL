"""Unit tests for canonical data contracts (`MarketBar`, `EventNewsItem`)."""

import dataclasses
import time

import pytest

from obsidian_rl.data.contracts import (
    DEFAULT_MAX_SKEW_MS,
    SCHEMA_VERSION_V2,
    EventNewsItem,
    MarketBar,
)
from obsidian_rl.data.fingerprint import (
    compute_event_news_hash,
    compute_market_bar_hash,
)


def sample_market_bar(**kwargs: object) -> MarketBar:
    """Helper to create a valid sample MarketBar, allowing field overrides."""
    now_ms = int(time.time() * 1000) - 60_000
    defaults: dict[str, object] = {
        "asset_class": "CRYPTO",
        "venue": "BINANCE",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "timestamp_utc": now_ms - 900_000,
        "observed_at_utc": now_ms,
        "open": 100000.0,
        "high": 101000.0,
        "low": 99500.0,
        "close": 100500.0,
        "bid": 100490.0,
        "ask": 100510.0,
        "volume": 25.5,
        "data_source": "BINANCE_WS",
        "data_version": SCHEMA_VERSION_V2,
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
        "event_type": "INTEREST_RATE",
        "expected_value": 4.50,
        "actual_value": 4.75,
        "surprise_value": 1.25,
        "raw_content_hash": "",
        "sentiment_score": 0.35,
        "revision_status": "INITIAL",
    }
    defaults.update(kwargs)
    return EventNewsItem(**defaults)  # type: ignore[arg-type]


def test_market_bar_valid_construction_and_immutability() -> None:
    """Verify valid construction, auto-hash generation, and frozen attributes."""
    bar = sample_market_bar()
    assert bar.asset_class == "CRYPTO"
    assert bar.symbol == "BTCUSDT"
    assert bar.data_version == SCHEMA_VERSION_V2
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


def test_market_bar_timestamp_ordering_and_future_rejection() -> None:
    """Verify observed_at_utc vs timestamp_utc ordering and future timestamp rejection."""
    now_ms = int(time.time() * 1000)
    with pytest.raises(ValueError, match="cannot be earlier than timestamp_utc"):
        sample_market_bar(timestamp_utc=now_ms - 1000, observed_at_utc=now_ms - 5000)

    future_ms = now_ms + DEFAULT_MAX_SKEW_MS + 60_000
    with pytest.raises(RuntimeError, match="exceeds current wall-clock plus skew allowance"):
        sample_market_bar(timestamp_utc=now_ms, observed_at_utc=future_ms)


def test_market_bar_hash_verification_on_construction() -> None:
    """Verify that providing an explicit row_hash validates or raises RuntimeError."""
    bar = sample_market_bar()
    valid_hash = bar.row_hash

    bar2 = sample_market_bar(row_hash=valid_hash)
    assert bar2.row_hash == valid_hash

    invalid_hash = "a" * 64
    with pytest.raises(RuntimeError, match="MarketBar hash mismatch"):
        sample_market_bar(row_hash=invalid_hash)


def test_event_news_valid_construction_and_immutability() -> None:
    """Verify valid EventNewsItem construction and automatic hashing."""
    item = sample_event_news()
    assert item.event_id == "evt-2026-001"
    assert item.affected_assets == ("EUR_USD", "BTCUSDT")
    assert len(item.raw_content_hash) == 64
    assert item.raw_content_hash == compute_event_news_hash(item)

    with pytest.raises(dataclasses.FrozenInstanceError):
        item.sentiment_score = 0.0  # type: ignore[misc]


def test_event_news_rejects_bools_and_non_finite_values() -> None:
    """Verify bool rejection and finite value enforcement for reliability/sentiment/expectations."""
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


def test_event_news_optional_values_and_affected_assets_coercion() -> None:
    """Verify that None is allowed for N/A expectations, and sequence coercion works for assets."""
    item = sample_event_news(expected_value=None, actual_value=None, surprise_value=None)
    assert item.expected_value is None
    assert item.actual_value is None
    assert item.surprise_value is None

    item2 = sample_event_news(affected_assets=["AUD_USD", "ETHUSDT"])
    assert item2.affected_assets == ("AUD_USD", "ETHUSDT")


def test_event_news_timestamp_discipline_and_hash_verification() -> None:
    """Verify revision timestamp ordering, future rejection, and content hash verification."""
    now_ms = int(time.time() * 1000)
    with pytest.raises(ValueError, match="cannot be earlier than first_observed_at"):
        sample_event_news(first_observed_at=now_ms, updated_at=now_ms - 100)

    future_ms = now_ms + DEFAULT_MAX_SKEW_MS + 60_000
    with pytest.raises(RuntimeError, match="exceeds current wall-clock plus skew allowance"):
        sample_event_news(first_observed_at=future_ms, updated_at=future_ms)

    item = sample_event_news()
    valid_hash = item.raw_content_hash
    assert sample_event_news(raw_content_hash=valid_hash).raw_content_hash == valid_hash

    with pytest.raises(RuntimeError, match="EventNewsItem hash mismatch"):
        sample_event_news(raw_content_hash="f" * 64)
