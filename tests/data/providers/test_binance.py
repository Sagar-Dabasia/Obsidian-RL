"""Unit tests for Binance Spot public kline adapter (`BinanceSpotProvider`)."""

from unittest.mock import MagicMock

import pytest
import requests

from obsidian_rl.data.contracts import AssetClass, QuoteStatus, Timeframe, VolumeType
from obsidian_rl.data.providers.binance import BinanceSpotProvider
from obsidian_rl.data.providers.errors import (
    MalformedResponseError,
    UnsupportedSymbolTimeframeError,
)


def test_binance_valid_conversion_and_pagination() -> None:
    """Verify exact OHLC conversion, QuoteStatus.UNAVAILABLE, and multi-page pagination."""
    mock_session = MagicMock(spec=requests.Session)

    # Page 1 returns 1000 candles so len(payload) == 1000 triggers pagination to Page 2.
    # 2 are completed (openTime 1000 and 2000, closeTime < 3050).
    # 998 filler rows are forming/incomplete (closeTime >= 3050) so observed > current_time (3050).
    # Last openTime is 2998, advancing cursor to 2999 < end_ms (4000).
    page1 = [
        [1000, "100.0", "105.0", "99.0", "102.0", "15.5", 1099, "0", 10, "0", "0", "0"],
        [2000, "102.0", "108.0", "101.0", "107.0", "20.0", 2099, "0", 12, "0", "0", "0"],
    ] + [
        [2001 + i, "100.0", "105.0", "99.0", "102.0", "10.0", 3050 + i, "0", 1, "0", "0", "0"]
        for i in range(998)
    ]
    # Page 2 returns 1 completed candle (openTime 3000, closeTime 3049 -> observed 3050 <= 3050)
    page2 = [
        [3000, "107.0", "110.0", "106.0", "109.0", "12.0", 3049, "0", 8, "0", "0", "0"],
    ]

    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = page1

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = page2

    mock_session.request.side_effect = [mock_resp1, mock_resp2]

    provider = BinanceSpotProvider(
        base_url="https://data-api.binance.vision",
        session=mock_session,
        current_time_provider=lambda: 3050,
    )

    bars = provider.fetch_bars("BTCUSDT", Timeframe.M15, start_ms=1000, end_ms=4000)
    assert len(bars) == 3
    assert mock_session.request.call_count == 2

    first_call_kwargs = mock_session.request.call_args_list[0].kwargs
    assert first_call_kwargs["params"] == {
        "symbol": "BTCUSDT",
        "interval": "15m",
        "startTime": 1000,
        "endTime": 3999,
        "limit": 1000,
    }

    # Verify second page advanced cursor past last openTime + 1 (2999)
    second_call_kwargs = mock_session.request.call_args_list[1].kwargs
    assert second_call_kwargs["params"]["startTime"] == 2999

    bar0 = bars[0]
    assert bar0.asset_class == AssetClass.CRYPTO
    assert bar0.venue == "BINANCE_SPOT"
    assert bar0.symbol == "BTCUSDT"
    assert bar0.timeframe == Timeframe.M15
    assert bar0.timestamp_utc == 1000
    assert bar0.observed_at_utc == 1100
    assert bar0.open == 100.0 and bar0.high == 105.0 and bar0.low == 99.0 and bar0.close == 102.0
    assert bar0.quote_status == QuoteStatus.UNAVAILABLE
    assert bar0.bid is None and bar0.ask is None
    assert bar0.volume_type == VolumeType.BASE
    assert bar0.volume == 15.5
    assert bar0.data_source == "BINANCE_SPOT_REST"


def test_binance_incomplete_candle_rejection() -> None:
    """Verify that candles whose observed_at_utc > current_time_ms are rejected."""
    mock_session = MagicMock(spec=requests.Session)
    payload = [
        [1000, "100.0", "105.0", "99.0", "102.0", "10.0", 1999, "0", 10, "0", "0", "0"],
        # closeTime+1=3000 > current=2500 -> incomplete
        [2000, "102.0", "106.0", "101.0", "104.0", "5.0", 2999, "0", 5, "0", "0", "0"],
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_session.request.return_value = mock_resp

    provider = BinanceSpotProvider(
        session=mock_session,
        current_time_provider=lambda: 2500,
    )

    bars = provider.fetch_bars("ETHUSDT", "15m", start_ms=1000, end_ms=3500)
    assert len(bars) == 1
    assert bars[0].timestamp_utc == 1000


def test_binance_exact_timeframe_mappings_and_unsupported_rejection() -> None:
    """Verify exact interval strings and rejection of unsupported timeframes."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    mock_session.request.return_value = mock_resp

    provider = BinanceSpotProvider(session=mock_session)
    provider.fetch_bars("BTCUSDT", Timeframe.H1, start_ms=0, end_ms=100)
    provider.fetch_bars("BTCUSDT", "1d", start_ms=0, end_ms=100)

    with pytest.raises(
        UnsupportedSymbolTimeframeError, match="Unsupported timeframe string: '10m'"
    ):
        provider.fetch_bars("BTCUSDT", "10m", start_ms=0, end_ms=100)


def test_binance_malformed_payload_and_non_finite_rejection() -> None:
    """Verify invalid response or NaN/Infinity prices raise MalformedResponseError."""
    mock_session = MagicMock(spec=requests.Session)
    provider = BinanceSpotProvider(session=mock_session)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": -1121, "msg": "Invalid symbol"}
    mock_session.request.return_value = mock_resp
    with pytest.raises(MalformedResponseError, match="Expected list from Binance /api/v3/klines"):
        provider.fetch_bars("BTCUSDT", "15m", start_ms=0, end_ms=100)

    # Shorter than 12
    mock_resp.json.return_value = [[1000, "100.0", "105.0", "99.0", "102.0", "10.0", 1999, "0", 10, "0", "0"]]
    with pytest.raises(
        MalformedResponseError,
        match="Malformed Binance row: expected exactly 12 items",
    ):
        provider.fetch_bars("BTCUSDT", "15m", start_ms=0, end_ms=100)

    # Longer than 12
    mock_resp.json.return_value = [[1000, "100.0", "105.0", "99.0", "102.0", "10.0", 1999, "0", 10, "0", "0", "0", "extra"]]
    with pytest.raises(
        MalformedResponseError,
        match="Malformed Binance row: expected exactly 12 items",
    ):
        provider.fetch_bars("BTCUSDT", "15m", start_ms=0, end_ms=100)

    mock_resp.json.return_value = [
        [1000, "nan", "105.0", "99.0", "102.0", "10.0", 1999, "0", 10, "0", "0", "0"],
    ]
    with pytest.raises(MalformedResponseError, match="Non-finite price or volume values detected"):
        provider.fetch_bars("BTCUSDT", "15m", start_ms=0, end_ms=100)
