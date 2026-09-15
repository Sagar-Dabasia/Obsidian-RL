"""Comprehensive test suite for MarketBar data quality validation pipeline."""

import pytest

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.quality import (
    is_forex_weekend_gap,
    timeframe_to_ms,
    validate_market_bars,
)


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


def test_timeframe_to_ms() -> None:
    """Test timeframe string / enum millisecond conversion."""
    assert timeframe_to_ms(Timeframe.M1) == 60_000
    assert timeframe_to_ms("4h") == 14_400_000
    assert timeframe_to_ms("1d") == 86_400_000
    with pytest.raises(ValueError):
        timeframe_to_ms("10h")


def test_validate_valid_crypto_series() -> None:
    """Test clean contiguous 24/7 crypto series passes validation."""
    t0 = 1784750400000
    step = 14_400_000
    bars = [make_bar(t0 + i * step) for i in range(5)]

    report = validate_market_bars(bars)
    assert report.passed is True
    assert report.rows_checked == 5
    assert report.duplicates == 0
    assert len(report.missing_intervals) == 0
    assert report.unexpected_intervals == 0
    assert report.hash_failures == 0
    assert report.observation_failures == 0


def test_crypto_missing_bar_detection() -> None:
    """Test missing bar in 24/7 crypto series is flagged."""
    t0 = 1784750400000
    step = 14_400_000
    # Skip bar index 2 (t0 + 2*step)
    bars = [
        make_bar(t0),
        make_bar(t0 + step),
        make_bar(t0 + 3 * step),
    ]

    report = validate_market_bars(bars)
    assert report.passed is False
    assert len(report.missing_intervals) == 1
    assert report.missing_intervals[0] == (t0 + 2 * step, 2 * step)


def test_forex_weekend_gap_handling() -> None:
    """Test Forex series across weekend market closure passes validation cleanly."""
    # Friday 2026-07-24 20:00 UTC (1784932800000 ms) - Friday close
    # Sunday 2026-07-26 20:00 UTC (1785105600000 ms) - Sunday open (~48h gap)
    t_fri = 1784932800000
    t_sun = 1785105600000

    assert is_forex_weekend_gap(t_fri, t_sun) is True

    bar_fri = make_bar(
        t_fri,
        symbol="EUR_USD",
        venue="OANDA",
        asset_class=AssetClass.FOREX,
        timeframe=Timeframe.H4,
    )
    bar_sun = make_bar(
        t_sun,
        symbol="EUR_USD",
        venue="OANDA",
        asset_class=AssetClass.FOREX,
        timeframe=Timeframe.H4,
    )

    report = validate_market_bars([bar_fri, bar_sun])
    assert report.passed is True
    assert len(report.missing_intervals) == 0


def test_forex_configurable_session() -> None:
    """Test Forex session configuration can be customized."""
    from obsidian_rl.data.quality import ForexSessionConfig

    # Shift standard open/close by 1 hour backwards
    # Close: Friday 19:00 UTC
    # Open: Sunday 19:00 UTC
    config = ForexSessionConfig(
        close_weekday=4,
        close_hour=19,
        open_weekday=6,
        open_hour=19,
        open_next_day_max_hour=3,
        min_gap_ms=144_000_000,
        max_gap_ms=201_600_000,
    )

    # Friday 2026-07-24 19:00 UTC (1784919600000 ms) - Custom close
    # Sunday 2026-07-26 19:00 UTC (1785092400000 ms) - Custom open (~48h gap)
    t_fri = 1784919600000
    t_sun = 1785092400000

    assert is_forex_weekend_gap(t_fri, t_sun, config) is True

    # Check that a gap before 19:00 UTC fails (e.g., Friday 18:00 UTC)
    t_fri_early = 1784916000000
    assert is_forex_weekend_gap(t_fri_early, t_sun, config) is False

    bar_fri = make_bar(
        t_fri, symbol="EUR_USD", venue="OANDA", asset_class=AssetClass.FOREX, timeframe=Timeframe.H4
    )
    bar_sun = make_bar(
        t_sun, symbol="EUR_USD", venue="OANDA", asset_class=AssetClass.FOREX, timeframe=Timeframe.H4
    )

    report = validate_market_bars([bar_fri, bar_sun], forex_session_config=config)
    assert report.passed is True


def test_duplicate_timestamp_detection() -> None:
    """Test duplicate timestamp in bar series is flagged."""
    t0 = 1784750400000
    bar1 = make_bar(t0, close=100.0)
    bar2 = make_bar(t0, close=101.0)  # Duplicate timestamp

    report = validate_market_bars([bar1, bar2])
    assert report.passed is False
    assert report.duplicates == 1


def test_out_of_order_series() -> None:
    """Test out-of-order timestamps fail validation."""
    t0 = 1784750400000
    step = 14_400_000
    bar1 = make_bar(t0 + step)
    bar2 = make_bar(t0)  # Earlier timestamp

    report = validate_market_bars([bar1, bar2])
    assert report.passed is False
    assert report.unexpected_intervals > 0


def test_mixed_series_rejection() -> None:
    """Test series containing mixed symbols or timeframes fails validation."""
    t0 = 1784750400000
    step = 14_400_000
    bar1 = make_bar(t0, symbol="BTCUSDT")
    bar2 = make_bar(t0 + step, symbol="ETHUSDT")  # Mixed symbol

    report = validate_market_bars([bar1, bar2])
    assert report.passed is False
    assert "errors" in report.details


def test_hash_failure_detection() -> None:
    """Test bar with tampered row_hash fails quality validation."""
    t0 = 1784750400000
    bar = make_bar(t0)
    object.__setattr__(bar, "row_hash", "d" * 64)

    report = validate_market_bars([bar])
    assert report.passed is False
    assert report.hash_failures == 1


def test_observation_time_violation() -> None:
    """Test observed_at_utc < timestamp_utc fails validation."""
    t0 = 1784750400000
    bar = make_bar(t0)
    object.__setattr__(bar, "observed_at_utc", t0 - 1000)

    report = validate_market_bars([bar])
    assert report.passed is False
    assert report.observation_failures == 1
