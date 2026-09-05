"""Tests for Trend Engine V1."""

import dataclasses

import pytest

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
    compute_market_bar_hash,
)
from obsidian_rl.signals.trend import (
    DataQualityError,
    InsufficientHistoryError,
    TrendConfig,
    calculate_trend_signal,
)


def make_bar(
    timestamp_utc: int,
    close: float,
    asset_class: AssetClass = AssetClass.CRYPTO,
    venue: str = "BINANCE_SPOT",
    symbol: str = "BTCUSDT",
    timeframe: Timeframe = Timeframe.D1,
) -> MarketBar:
    bar = MarketBar(
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc=timestamp_utc,
        observed_at_utc=timestamp_utc + 1000,
        open=close,
        high=close,
        low=close,
        close=close,
        quote_status=(
            QuoteStatus.UNAVAILABLE if asset_class == AssetClass.CRYPTO else QuoteStatus.OBSERVED
        ),
        bid=None if asset_class == AssetClass.CRYPTO else close - 0.1,
        ask=None if asset_class == AssetClass.CRYPTO else close + 0.1,
        volume_type=VolumeType.BASE if asset_class == AssetClass.CRYPTO else VolumeType.TICK,
        volume=1.0,
        data_source="TEST",
        row_hash="",
    )
    object.__setattr__(bar, "row_hash", compute_market_bar_hash(bar))
    return bar


def test_trend_config_identity_deterministic() -> None:
    c1 = TrendConfig(20, 60, 120)
    c2 = TrendConfig(20, 60, 120)
    assert c1.identity == c2.identity


def test_frozen_immutability() -> None:
    c1 = TrendConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c1.short_horizon_days = 10  # type: ignore


def test_clear_crypto_uptrend_produces_long() -> None:
    """Test that a strictly increasing series produces LONG."""
    bars = tuple(
        make_bar(i * 86_400_000, close=100.0 + i)
        for i in range(130)  # Need 121 bars for 120-day return
    )
    signal = calculate_trend_signal(bars, observed_before_ms=9999999999999)
    assert signal.direction == "LONG"
    assert signal.score == 1.0


def test_clear_forex_downtrend_produces_short() -> None:
    """Test that a strictly decreasing series produces SHORT."""
    bars = tuple(
        make_bar(
            i * 86_400_000,
            close=1000.0 - i,
            asset_class=AssetClass.FOREX,
            venue="OANDA",
            symbol="EUR_USD",
        )
        for i in range(130)
    )
    signal = calculate_trend_signal(bars, observed_before_ms=9999999999999)
    assert signal.direction == "SHORT"
    assert signal.score == -1.0


def test_mixed_horizons_produce_flat() -> None:
    """Test that mixed returns produce FLAT."""
    bars_list = []
    # Make older prices very high, then dip, then recent high.
    # 120 days ago = high (return negative)
    # 60 days ago = low (return positive)
    # 20 days ago = lower (return positive)
    for i in range(130):
        if i == 130 - 1 - 120:
            price = 200.0
        elif i == 130 - 1 - 60 or i == 130 - 1 - 20:
            price = 50.0
        elif i == 130 - 1:
            price = 100.0
        else:
            price = 100.0
        bars_list.append(make_bar(i * 86_400_000, close=price))

    signal = calculate_trend_signal(tuple(bars_list), observed_before_ms=9999999999999)
    assert signal.direction == "FLAT"


def test_exactly_zero_return_produces_flat() -> None:
    """Test exactly zero return produces FLAT."""
    bars = tuple(make_bar(i * 86_400_000, close=100.0) for i in range(130))
    signal = calculate_trend_signal(bars, observed_before_ms=9999999999999)
    assert signal.direction == "FLAT"
    assert signal.score == 0.0


def test_insufficient_history_rejection() -> None:
    """Test that < 121 bars for daily rejects."""
    bars = tuple(make_bar(i * 86_400_000, close=100.0) for i in range(120))
    with pytest.raises(InsufficientHistoryError):
        calculate_trend_signal(bars, observed_before_ms=9999999999999)


def test_mixed_symbol_timeframe_rejection() -> None:
    bars = [make_bar(i * 86_400_000, close=100.0) for i in range(130)]
    # Corrupt one bar
    object.__setattr__(bars[50], "symbol", "ETHUSDT")
    with pytest.raises(DataQualityError, match="Mixed"):
        calculate_trend_signal(tuple(bars), observed_before_ms=9999999999999)


def test_duplicate_and_out_of_order_rejection() -> None:
    bars = [make_bar(i * 86_400_000, close=100.0) for i in range(130)]
    object.__setattr__(bars[50], "timestamp_utc", bars[49].timestamp_utc)
    with pytest.raises(DataQualityError, match="out of order or contain duplicates"):
        calculate_trend_signal(tuple(bars), observed_before_ms=9999999999999)


def test_tampered_hash_rejection() -> None:
    bars = [make_bar(i * 86_400_000, close=100.0) for i in range(130)]
    object.__setattr__(bars[50], "row_hash", "short")
    with pytest.raises(DataQualityError, match="Invalid row hash"):
        calculate_trend_signal(tuple(bars), observed_before_ms=9999999999999)


def test_point_in_time_cutoff_protection() -> None:
    bars = [make_bar(i * 86_400_000, close=100.0) for i in range(130)]
    # If observed_before_ms excludes latest bar, history might be insufficient
    cutoff = bars[-2].observed_at_utc
    signal = calculate_trend_signal(tuple(bars), observed_before_ms=cutoff)
    assert signal.signal_timestamp_utc <= cutoff


def test_4h_and_daily_horizon_conversion() -> None:
    """Test that 4h requires 6x bars (721)."""
    bars_4h = tuple(
        make_bar(i * 14_400_000, close=100.0 + i, timeframe=Timeframe.H4) for i in range(721)
    )
    signal = calculate_trend_signal(bars_4h, observed_before_ms=9999999999999)
    assert signal.direction == "LONG"

    # 720 should fail
    with pytest.raises(InsufficientHistoryError):
        calculate_trend_signal(bars_4h[:-1], observed_before_ms=9999999999999)


def test_nan_and_infinity_rejection() -> None:
    bars = [make_bar(i * 86_400_000, close=100.0) for i in range(130)]
    object.__setattr__(bars[-1], "close", float("inf"))
    with pytest.raises(DataQualityError, match="Invalid close price"):
        calculate_trend_signal(tuple(bars), observed_before_ms=9999999999999)
