"""Tests for the outage registry."""

import pytest

from obsidian_rl.data.outages import OutageRegistry, VenueOutage


def test_venue_outage_validation() -> None:
    # Invalid end <= start
    with pytest.raises(ValueError, match="must be < end_ms"):
        VenueOutage(
            venue="BINANCE_SPOT",
            start_ms=1000,
            end_ms=1000,
            source_id="test",
            verification_timestamp_ms=2000,
            source_content_hash="0" * 64,
            reason="test",
            affected_symbols=("BTCUSDT",),
            venue_wide=True,
        )

    # Invalid hash length
    with pytest.raises(ValueError, match="must be 64-char hex"):
        VenueOutage(
            venue="BINANCE_SPOT",
            start_ms=1000,
            end_ms=2000,
            source_id="test",
            verification_timestamp_ms=2000,
            source_content_hash="short",
            reason="test",
            affected_symbols=("BTCUSDT",),
            venue_wide=True,
        )

    # Empty symbols
    with pytest.raises(ValueError, match="affected_symbols must be non-empty"):
        VenueOutage(
            venue="BINANCE_SPOT",
            start_ms=1000,
            end_ms=2000,
            source_id="test",
            verification_timestamp_ms=2000,
            source_content_hash="0" * 64,
            reason="test",
            affected_symbols=(),
            venue_wide=True,
        )


def test_registry_methods() -> None:
    outage1 = VenueOutage(
        venue="BINANCE_SPOT",
        start_ms=1000,
        end_ms=2000,
        source_id="test",
        verification_timestamp_ms=2000,
        source_content_hash="0" * 64,
        reason="test",
        affected_symbols=("BTCUSDT", "ETHUSDT"),
        venue_wide=True,
    )
    registry = OutageRegistry(outages=(outage1,))

    assert registry.is_known_outage("BINANCE_SPOT", 1000)
    assert registry.is_known_outage("BINANCE_SPOT", 1500)
    assert not registry.is_known_outage("BINANCE_SPOT", 2000)
    assert not registry.is_known_outage("OANDA_PRACTICE", 1500)

    o = registry.get_outage("BINANCE_SPOT", 1500)
    assert o is not None
    assert o.venue == "BINANCE_SPOT"
    assert o.start_ms == 1000

    assert registry.is_venue_wide("BINANCE_SPOT", 1500)
    assert not registry.is_venue_wide("BINANCE_SPOT", 2000)

    # covers_gap logic
    assert registry.covers_gap("BINANCE_SPOT", 1000, 2000)
    assert registry.covers_gap("BINANCE_SPOT", 1200, 1800)
    assert not registry.covers_gap("BINANCE_SPOT", 500, 1500)
    assert not registry.covers_gap("BINANCE_SPOT", 1500, 2500)
    assert not registry.covers_gap("OANDA_PRACTICE", 1000, 2000)
