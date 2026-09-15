"""Unit tests for shared provider infrastructure (`BaseRestProvider`, errors, secret scrubbing)."""

import logging
from unittest.mock import MagicMock

import pytest
import requests

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.fingerprint import compute_market_bar_hash
from obsidian_rl.data.providers.base import BaseRestProvider
from obsidian_rl.data.providers.errors import (
    AuthenticationError,
    MalformedResponseError,
    RateLimitError,
    TransportError,
    UnsupportedSymbolTimeframeError,
    scrub_secrets,
)


class DummyProvider(BaseRestProvider):
    """Concrete provider harness for testing BaseRestProvider methods."""

    def fetch_bars(
        self, symbol: str, timeframe: Timeframe | str, start_ms: int, end_ms: int
    ) -> tuple[MarketBar, ...]:
        return ()


def test_base_retry_on_transport_error_and_max_retry_exhaustion() -> None:
    """Verify exponential backoff retries on network exception/5xx and final TransportError."""
    mock_session = MagicMock(spec=requests.Session)
    mock_session.request.side_effect = requests.ConnectionError("Connection refused")
    sleep_calls: list[float] = []

    provider = DummyProvider(
        base_url="https://dummy.api",
        session=mock_session,
        max_retries=3,
        sleep_func=sleep_calls.append,
    )

    with pytest.raises(TransportError, match="HTTP request failed after 3 retries"):
        provider._request("GET", "https://dummy.api/test")

    assert mock_session.request.call_count == 3
    assert sleep_calls == [1.0, 2.0]

    mock_session.reset_mock()
    sleep_calls.clear()
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_session.request.side_effect = None
    mock_session.request.return_value = mock_resp

    with pytest.raises(TransportError, match="Server error after 3 retries: HTTP 503"):
        provider._request("GET", "https://dummy.api/test")
    assert mock_session.request.call_count == 3
    assert sleep_calls == [1.0, 2.0]


def test_base_429_rate_limit_retry_with_retry_after() -> None:
    """Verify rate-limit retry respects Retry-After and raises RateLimitError when exhausted."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "5.5"}

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"success": True}

    mock_session.request.side_effect = [mock_resp_429, mock_resp_429, mock_resp_200]
    sleep_calls: list[float] = []

    provider = DummyProvider(
        base_url="https://dummy.api",
        session=mock_session,
        max_retries=5,
        sleep_func=sleep_calls.append,
    )

    result = provider._request("GET", "https://dummy.api/test")
    assert result == {"success": True}
    assert mock_session.request.call_count == 3
    assert sleep_calls == [5.5, 5.5]

    mock_session.reset_mock()
    sleep_calls.clear()
    mock_session.request.side_effect = [mock_resp_429, mock_resp_429, mock_resp_429]
    provider_limited = DummyProvider(
        base_url="https://dummy.api",
        session=mock_session,
        max_retries=3,
        sleep_func=sleep_calls.append,
    )
    with pytest.raises(RateLimitError, match="Rate limit exceeded after 3 retries: HTTP 429"):
        provider_limited._request("GET", "https://dummy.api/test")
    assert mock_session.request.call_count == 3


def test_base_permanent_4xx_no_retry() -> None:
    """Verify permanent HTTP 4xx errors immediately fail without retry."""
    mock_session = MagicMock(spec=requests.Session)
    sleep_calls: list[float] = []
    provider = DummyProvider(
        base_url="https://dummy.api",
        session=mock_session,
        max_retries=5,
        sleep_func=sleep_calls.append,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_session.request.return_value = mock_resp
    with pytest.raises(AuthenticationError, match="Authentication failed: HTTP 401"):
        provider._request("GET", "https://dummy.api/auth")
    assert mock_session.request.call_count == 1
    assert sleep_calls == []

    mock_session.reset_mock()
    mock_resp.status_code = 400
    mock_resp.text = "Invalid symbol requested: INVALID_USD"
    with pytest.raises(UnsupportedSymbolTimeframeError, match="Unsupported symbol or timeframe"):
        provider._request("GET", "https://dummy.api/data")
    assert mock_session.request.call_count == 1
    assert sleep_calls == []

    mock_session.reset_mock()
    mock_resp.status_code = 422
    mock_resp.text = "Malformed query parameter"
    with pytest.raises(
        MalformedResponseError, match=r"Client request error \(no retry\): HTTP 422"
    ):
        provider._request("GET", "https://dummy.api/data")
    assert mock_session.request.call_count == 1
    assert sleep_calls == []


def test_base_secret_scrubbing_in_exceptions_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify secrets and tokens are scrubbed from exception strings and log output."""
    secret_token = "super_secret_token_abc123"
    assert (
        scrub_secrets(f"Authorization: Bearer {secret_token}") == "Authorization: Bearer [REDACTED]"
    )
    assert (
        scrub_secrets(f"Token is {secret_token} here", (secret_token,))
        == "Token is [REDACTED] here"
    )

    mock_session = MagicMock(spec=requests.Session)
    mock_session.request.side_effect = requests.ConnectionError(
        f"Failed to connect using token={secret_token}"
    )
    caplog.set_level(logging.WARNING)

    provider = DummyProvider(
        base_url="https://dummy.api",
        session=mock_session,
        max_retries=2,
        sleep_func=lambda _: None,
        secrets=(secret_token,),
    )

    with pytest.raises(TransportError) as exc_info:
        provider._request("GET", "https://dummy.api/test")

    assert secret_token not in str(exc_info.value)
    assert secret_token not in repr(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)

    for record in caplog.records:
        assert secret_token not in record.getMessage()


def test_base_bar_filtering_sorting_and_deduplication() -> None:
    """Verify start-inclusive/end-exclusive filtering, exact deduplication, and sorting."""
    provider = DummyProvider(base_url="https://dummy.api")

    def make_bar(ts: int) -> MarketBar:
        return MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.M15,
            timestamp_utc=ts,
            observed_at_utc=ts + 900_000,
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            quote_status=QuoteStatus.UNAVAILABLE,
            bid=None,
            ask=None,
            volume_type=VolumeType.BASE,
            volume=10.0,
            data_source="TEST",
        )

    bars = [
        make_bar(3000),
        make_bar(900),
        make_bar(2000),
        make_bar(1000),
        make_bar(2000),
        make_bar(3100),
    ]

    result = provider._finalize_bars(bars, start_ms=1000, end_ms=3100)
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert [b.timestamp_utc for b in result] == [1000, 2000, 3000]

    with pytest.raises(ValueError, match="strictly greater than start_ms"):
        provider._finalize_bars(bars, start_ms=2000, end_ms=2000)


def test_existing_phase_1_hashes_remain_deterministic() -> None:
    """Verify Phase 1 canonical SHA-256 computation is unchanged and exact."""
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
    )
    assert (
        compute_market_bar_hash(fixed_bar)
        == "3bdb80912e6333efd5d0dde92897c0b97b0bc54969d9230af121cd41d5835693"
    )
