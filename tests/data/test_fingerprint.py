"""Unit tests for canonical JSON and deterministic fingerprinting (`fingerprint.py`)."""

import time

import pytest

from obsidian_rl.data.contracts import EventNewsItem, MarketBar
from obsidian_rl.data.fingerprint import (
    canonical_json,
    compute_canonical_sha256,
    compute_event_news_hash,
    compute_market_bar_hash,
    verify_contract_hash,
)


def test_canonical_json_deterministic_ordering_and_nan_rejection() -> None:
    """Verify key sorting, compact formatting, and NaN rejection in canonical JSON bytes."""
    payload = {"c": 3, "a": 1, "b": [2, 1]}
    encoded = canonical_json(payload)
    assert encoded == b'{"a":1,"b":[2,1],"c":3}'

    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_compute_canonical_sha256_excludes_specified_fields() -> None:
    """Verify that compute_canonical_sha256 strips excluded fields before hashing."""
    data = {"open": 100.0, "close": 105.0, "row_hash": "dummy_hash_to_be_ignored"}
    data_no_hash = {"open": 100.0, "close": 105.0}

    hash1 = compute_canonical_sha256(data, exclude_keys=("row_hash",))
    hash2 = compute_canonical_sha256(data_no_hash, exclude_keys=("row_hash",))
    assert hash1 == hash2
    assert len(hash1) == 64
    assert hash1.islower()


def test_compute_market_bar_hash_consistency_with_dict_and_instance() -> None:
    """Verify that compute_market_bar_hash produces identical hashes for dict and MarketBar."""
    now_ms = int(time.time() * 1000) - 60_000
    bar = MarketBar(
        asset_class="FOREX",
        venue="OANDA",
        symbol="EUR_USD",
        timeframe="1h",
        timestamp_utc=now_ms - 3600_000,
        observed_at_utc=now_ms,
        open=1.0850,
        high=1.0880,
        low=1.0840,
        close=1.0875,
        bid=1.0874,
        ask=1.0876,
        volume=12500.0,
        data_source="OANDA_API",
    )

    bar_dict = {
        "asset_class": bar.asset_class,
        "venue": bar.venue,
        "symbol": bar.symbol,
        "timeframe": bar.timeframe,
        "timestamp_utc": bar.timestamp_utc,
        "observed_at_utc": bar.observed_at_utc,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "bid": bar.bid,
        "ask": bar.ask,
        "volume": bar.volume,
        "data_source": bar.data_source,
        "data_version": bar.data_version,
        "row_hash": bar.row_hash,
    }

    hash_instance = compute_market_bar_hash(bar)
    hash_dict = compute_market_bar_hash(bar_dict)
    assert hash_instance == hash_dict
    assert bar.row_hash == hash_instance


def test_compute_event_news_hash_consistency() -> None:
    """Verify compute_event_news_hash produces identical hashes regardless of raw_content_hash."""
    now_ms = int(time.time() * 1000) - 60_000
    item = EventNewsItem(
        event_id="evt-macro-001",
        source="REUTERS",
        source_reliability=0.9,
        original_published_at=now_ms - 5000,
        first_observed_at=now_ms,
        updated_at=now_ms,
        affected_assets=("USD_JPY", "EQUITY_SPX"),
        event_type="CPI",
        expected_value=3.1,
        actual_value=3.2,
        surprise_value=0.1,
        sentiment_score=-0.2,
    )

    item_dict = {
        "event_id": item.event_id,
        "source": item.source,
        "source_reliability": item.source_reliability,
        "original_published_at": item.original_published_at,
        "first_observed_at": item.first_observed_at,
        "updated_at": item.updated_at,
        "affected_assets": list(item.affected_assets),
        "event_type": item.event_type,
        "expected_value": item.expected_value,
        "actual_value": item.actual_value,
        "surprise_value": item.surprise_value,
        "raw_content_hash": "dummy_content_hash",
        "sentiment_score": item.sentiment_score,
        "revision_status": item.revision_status,
    }

    assert compute_event_news_hash(item) == compute_event_news_hash(item_dict)
    assert item.raw_content_hash == compute_event_news_hash(item)


def test_verify_contract_hash_validates_or_raises() -> None:
    """Verify verify_contract_hash on valid instances and forged instances."""
    now_ms = int(time.time() * 1000) - 60_000
    bar = MarketBar(
        asset_class="CRYPTO",
        venue="BINANCE",
        symbol="BTCUSDT",
        timeframe="15m",
        timestamp_utc=now_ms - 900_000,
        observed_at_utc=now_ms,
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        bid=101.9,
        ask=102.1,
        volume=10.0,
        data_source="BINANCE_WS",
    )
    assert verify_contract_hash(bar) is True

    # Force an invalid hash bypassing post_init using object.__setattr__
    object.__setattr__(bar, "row_hash", "0" * 64)
    with pytest.raises(RuntimeError, match="MarketBar hash mismatch"):
        verify_contract_hash(bar)
