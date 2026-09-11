"""Unit tests for OANDA Practice Forex adapter (`OandaPracticeProvider`)."""

from unittest.mock import MagicMock

import pytest
import requests

from obsidian_rl.data.contracts import AssetClass, QuoteStatus, Timeframe, VolumeType
from obsidian_rl.data.providers.errors import (
    AuthenticationError,
    MalformedResponseError,
    UnsupportedSymbolTimeframeError,
)
from obsidian_rl.data.providers.oanda import OandaPracticeProvider


def test_oanda_valid_conversion_and_daily_alignment() -> None:
    """Verify exact midpoint OHLC, closing bid/ask, daily UTC alignment, and VolumeType.TICK."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "instrument": "EUR_USD",
        "granularity": "D",
        "candles": [
            {
                "complete": True,
                "volume": 12500,
                "time": "2026-01-01T00:00:00.000000000Z",
                "mid": {"o": "1.0850", "h": "1.0890", "l": "1.0820", "c": "1.0875"},
                "bid": {"o": "1.0849", "h": "1.0889", "l": "1.0819", "c": "1.0874"},
                "ask": {"o": "1.0851", "h": "1.0891", "l": "1.0821", "c": "1.0876"},
            }
        ],
    }
    mock_session.request.return_value = mock_resp

    provider = OandaPracticeProvider(
        base_url="https://api-fxpractice.oanda.com",
        api_token="test_oanda_token_123",
        session=mock_session,
        current_time_provider=lambda: 1767312000000,  # 2026-01-03
    )

    start_ms = 1767225600000
    end_ms = start_ms + 86_400_000 * 2
    bars = provider.fetch_bars("EUR_USD", Timeframe.D1, start_ms=start_ms, end_ms=end_ms)
    assert len(bars) == 1
    assert mock_session.request.call_count == 1

    call_kwargs = mock_session.request.call_args.kwargs
    assert call_kwargs["params"]["dailyAlignment"] == 0
    assert call_kwargs["params"]["alignmentTimezone"] == "UTC"
    assert call_kwargs["headers"] == {"Authorization": "Bearer test_oanda_token_123"}

    bar = bars[0]
    assert bar.asset_class == AssetClass.FOREX
    assert bar.venue == "OANDA_PRACTICE"
    assert bar.symbol == "EUR_USD"
    assert bar.timeframe == Timeframe.D1
    assert bar.timestamp_utc == start_ms
    assert bar.observed_at_utc == start_ms + 86_400_000
    assert bar.open == 1.0850 and bar.high == 1.0890 and bar.low == 1.0820 and bar.close == 1.0875
    assert bar.quote_status == QuoteStatus.OBSERVED
    assert bar.bid == 1.0874 and bar.ask == 1.0876
    assert bar.volume_type == VolumeType.TICK
    assert bar.volume == 12500.0
    assert bar.data_source == "OANDA_PRACTICE_REST"


def test_oanda_token_loading_and_scrubbing_and_missing_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify environment-token loading, missing token rejection, and complete scrubbing."""
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    with pytest.raises(AuthenticationError, match="OANDA API token is missing"):
        OandaPracticeProvider(api_token=None)

    token = "secret_env_token_xyz"
    monkeypatch.setenv("OANDA_API_TOKEN", token)
    provider = OandaPracticeProvider()
    assert provider._api_token == token

    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = f"Invalid Bearer token: {token}"
    mock_session.request.return_value = mock_resp
    provider._session = mock_session

    with pytest.raises(AuthenticationError) as exc_info:
        provider._request("GET", "https://api-fxpractice.oanda.com/test")

    assert token not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_oanda_crossed_quotes_and_incomplete_candle_rejection() -> None:
    """Verify crossed quotes (ask < bid) raise MalformedResponseError and incomplete skipped."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_session.request.return_value = mock_resp

    provider = OandaPracticeProvider(
        api_token="test_token",
        session=mock_session,
        current_time_provider=lambda: 2000000,
    )

    # 1. Crossed quote (ask < bid)
    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": True,
                "volume": 100,
                "time": "1970-01-01T00:00:01.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
            }
        ]
    }
    with pytest.raises(MalformedResponseError, match="Crossed bid/ask quotes detected"):
        provider.fetch_bars("EUR_USD", Timeframe.M1, start_ms=0, end_ms=100000)

    # 2. Incomplete candle (complete=False) and future observed time skipped cleanly
    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": False,
                "volume": 100,
                "time": "1970-01-01T00:00:01.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            },
            {
                "complete": True,
                "volume": 100,
                # 1,800,000 ms -> observed at 1,860,000 <= 2,000,000
                "time": "1970-01-01T00:30:00.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            },
            {
                "complete": True,
                "volume": 100,
                # 2,100,000 ms -> observed at 2,160,000 > 2,000,000 (future)
                "time": "1970-01-01T00:35:00.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            },
        ]
    }
    bars = provider.fetch_bars("EUR_USD", Timeframe.M1, start_ms=0, end_ms=3000000)
    assert len(bars) == 1
    assert bars[0].timestamp_utc == 1800000

    # 3. Invalid complete type (string)
    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": "true",
                "volume": 100,
                "time": "1970-01-01T00:00:01.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            }
        ]
    }
    with pytest.raises(MalformedResponseError, match="OANDA 'complete' must be a boolean"):
        provider.fetch_bars("EUR_USD", Timeframe.M1, start_ms=0, end_ms=100000)

    # 4. Missing volume
    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": True,
                "time": "1970-01-01T00:00:01.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            }
        ]
    }
    with pytest.raises(MalformedResponseError, match="OANDA candle missing 'volume' field"):
        provider.fetch_bars("EUR_USD", Timeframe.M1, start_ms=0, end_ms=100000)

    # 5. Invalid volume type (boolean)
    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": True,
                "volume": True,
                "time": "1970-01-01T00:00:01.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            }
        ]
    }
    with pytest.raises(MalformedResponseError, match="OANDA volume cannot be boolean"):
        provider.fetch_bars("EUR_USD", Timeframe.M1, start_ms=0, end_ms=100000)

    # 6. Negative volume
    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": True,
                "volume": -100,
                "time": "1970-01-01T00:00:01.000000000Z",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            }
        ]
    }
    with pytest.raises(MalformedResponseError, match="Non-finite price or invalid volume detected"):
        provider.fetch_bars("EUR_USD", Timeframe.M1, start_ms=0, end_ms=100000)


def test_oanda_unsupported_granularity_rejection() -> None:
    """Verify Timeframe.M3 is rejected by OANDA adapter with UnsupportedSymbolTimeframeError."""
    provider = OandaPracticeProvider(api_token="dummy")
    with pytest.raises(
        UnsupportedSymbolTimeframeError,
        match=r"Timeframe 3m \(granularity not mapped\) is not supported",
    ):
        provider.fetch_bars("EUR_USD", Timeframe.M3, start_ms=0, end_ms=100)


def test_oanda_malformed_timestamp_and_missing_components() -> None:
    """Verify malformed timestamps or missing mid/bid/ask raise MalformedResponseError."""
    mock_session = MagicMock(spec=requests.Session)
    provider = OandaPracticeProvider(api_token="dummy", session=mock_session)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_session.request.return_value = mock_resp

    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": True,
                "time": "2026-01-01T00:00:00.000Z",
                "bid": {"c": "1.0"},
                "ask": {"c": "1.1"},
            }
        ]
    }
    with pytest.raises(
        MalformedResponseError,
        match="OANDA candle missing required mid, bid, or ask dicts",
    ):
        provider.fetch_bars("EUR_USD", Timeframe.M15, start_ms=0, end_ms=1000000000000)

    mock_resp.json.return_value = {
        "candles": [
            {
                "complete": True,
                "time": "NOT_A_VALID_TIMESTAMP",
                "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"},
                "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.04"},
                "ask": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.06"},
            }
        ]
    }
    with pytest.raises(MalformedResponseError, match="Could not parse OANDA timestamp string"):
        provider.fetch_bars("EUR_USD", Timeframe.M15, start_ms=0, end_ms=1000000000000)
