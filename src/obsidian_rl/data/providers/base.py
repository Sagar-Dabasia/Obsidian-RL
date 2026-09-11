"""Shared market-data provider protocol (`MarketDataProvider`) and base REST adapter infrastructure.

Enforces:
- Immutable tuple output of canonical `MarketBar` contracts
- UTC milliseconds with strict chronological sorting and deduplication
- Start inclusive (`>= start_ms`) and end exclusive (`< end_ms`) filtering
- Bounded retries and exponential backoff (`sleep` / `requests.Session` / `current_time` injection)
- Rejection of permanent HTTP 4xx errors without retry (except rate limits HTTP 429/418)
- Complete credentials scrubbing from exceptions and logs
"""

import logging
import time
from collections.abc import Callable, Iterable
from typing import Any, Protocol

import requests

from obsidian_rl.data.contracts import MarketBar, Timeframe
from obsidian_rl.data.providers.errors import (
    AuthenticationError,
    MalformedResponseError,
    ProviderError,
    RateLimitError,
    TransportError,
    UnsupportedSymbolTimeframeError,
    scrub_secrets,
)

logger = logging.getLogger(__name__)


class MarketDataProvider(Protocol):
    """Protocol defining the canonical cross-asset market-data provider interface."""

    @property
    def provider_name(self) -> str:
        """Name of the data provider (e.g., 'BINANCE', 'OANDA')."""
        ...

    @property
    def adapter_version(self) -> str:
        """Version of the provider adapter implementation."""
        ...

    def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[MarketBar, ...]:
        """Fetch completed canonical OHLCV market bars for [start_ms, end_ms).

        Returns:
            tuple[MarketBar, ...]: Immutable chronologically ordered tuple of unique bars.
        """
        ...


class BaseRestProvider:
    """Base infrastructure providing HTTP retries, error mapping, and bar filtering."""

    provider_name: str = "BASE"
    adapter_version: str = "1.0.0"

    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 5,
        sleep_func: Callable[[float], None] = time.sleep,
        current_time_provider: Callable[[], int] | None = None,
        secrets: Iterable[str | None] = (),
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise ValueError("timeout_s must be a positive number")
        self._timeout_s = float(timeout_s)
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError("max_retries must be an integer >= 1")
        self._max_retries = max_retries
        self._sleep = sleep_func
        self._current_time_provider = current_time_provider or (lambda: int(time.time() * 1000))
        self._secrets = tuple(s for s in secrets if s and isinstance(s, str))

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Execute HTTP request with exponential backoff and typed error mapping."""
        last_error: str = "No attempts made"
        for attempt in range(self._max_retries):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout_s,
                )
            except requests.RequestException as exc:
                last_error = scrub_secrets(f"Network transport error: {exc}", self._secrets)
                if attempt < self._max_retries - 1:
                    wait_s = min(2.0**attempt, 30.0)
                    logger.warning(
                        "Transport request exception (attempt %d/%d): %s. Backing off %.1fs",
                        attempt + 1,
                        self._max_retries,
                        last_error,
                        wait_s,
                    )
                    self._sleep(wait_s)
                    continue
                raise TransportError(
                    f"HTTP request failed after {self._max_retries} retries: {last_error}",
                    self._secrets,
                ) from exc

            status = resp.status_code
            if status == 200:
                try:
                    return resp.json()
                except (ValueError, TypeError) as exc:
                    raise MalformedResponseError(
                        f"Provider returned invalid JSON response: {resp.text[:200]}",
                        self._secrets,
                    ) from exc

            if status in (429, 418):
                last_error = f"HTTP {status}: Rate limit exceeded"
                if attempt < self._max_retries - 1:
                    try:
                        retry_after = float(resp.headers.get("Retry-After", "0") or 0.0)
                    except (ValueError, TypeError):
                        retry_after = 0.0
                    wait_s = max(retry_after, min(2.0 ** (attempt + 1), 60.0))
                    logger.warning(
                        "Rate limited (HTTP %d, attempt %d/%d). Backing off %.1fs",
                        status,
                        attempt + 1,
                        self._max_retries,
                        wait_s,
                    )
                    self._sleep(wait_s)
                    continue
                raise RateLimitError(
                    f"Rate limit exceeded after {self._max_retries} retries: HTTP {status}",
                    self._secrets,
                )

            if status in (401, 403):
                body_snippet = scrub_secrets(resp.text[:200], self._secrets)
                raise AuthenticationError(
                    f"Authentication failed: HTTP {status} ({body_snippet})",
                    self._secrets,
                )

            if 400 <= status < 500:
                body_snippet = scrub_secrets(resp.text[:200], self._secrets)
                if status in (400, 404) and any(
                    kw in body_snippet.lower()
                    for kw in (
                        "symbol",
                        "instrument",
                        "interval",
                        "granularity",
                        "not found",
                        "invalid",
                    )
                ):
                    raise UnsupportedSymbolTimeframeError(
                        f"Unsupported symbol or timeframe: HTTP {status} ({body_snippet})",
                        self._secrets,
                    )
                raise MalformedResponseError(
                    f"Client request error (no retry): HTTP {status} ({body_snippet})",
                    self._secrets,
                )

            if 500 <= status < 600:
                last_error = f"HTTP {status} server error"
                if attempt < self._max_retries - 1:
                    wait_s = min(2.0**attempt, 30.0)
                    logger.warning(
                        "Server error (HTTP %d, attempt %d/%d). Backing off %.1fs",
                        status,
                        attempt + 1,
                        self._max_retries,
                        wait_s,
                    )
                    self._sleep(wait_s)
                    continue
                raise TransportError(
                    f"Server error after {self._max_retries} retries: {last_error}",
                    self._secrets,
                )

            raise TransportError(f"Unexpected HTTP response code: {status}", self._secrets)

        raise ProviderError(
            f"HTTP request exhausted {self._max_retries} attempts without outcome",
            self._secrets,
        )

    def _validate_timeframe(self, timeframe: Timeframe | str) -> Timeframe:
        """Ensure timeframe is a valid Timeframe enum instance without silent string conversion."""
        if isinstance(timeframe, Timeframe):
            return timeframe
        if isinstance(timeframe, str):
            try:
                return Timeframe(timeframe)
            except ValueError as exc:
                raise UnsupportedSymbolTimeframeError(
                    f"Unsupported timeframe string: {timeframe!r}"
                ) from exc
        raise TypeError(
            f"timeframe must be Timeframe or valid string, got {type(timeframe).__name__}"
        )

    def _finalize_bars(
        self, bars: Iterable[MarketBar], start_ms: int, end_ms: int
    ) -> tuple[MarketBar, ...]:
        """Filter [start_ms, end_ms), deduplicate by timestamp, and sort chronologically."""
        if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
            raise TypeError("start_ms must be a non-negative integer")
        if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms < 0:
            raise TypeError("end_ms must be a non-negative integer")
        if end_ms <= start_ms:
            raise ValueError(
                f"end_ms ({end_ms}) must be strictly greater than start_ms ({start_ms})"
            )

        seen_ts: set[int] = set()
        unique_bars: list[MarketBar] = []
        for bar in bars:
            if not isinstance(bar, MarketBar):
                raise TypeError(f"Expected MarketBar instance, got {type(bar).__name__}")
            if bar.timestamp_utc < start_ms or bar.timestamp_utc >= end_ms:
                continue
            if bar.timestamp_utc in seen_ts:
                continue
            seen_ts.add(bar.timestamp_utc)
            unique_bars.append(bar)
        unique_bars.sort(key=lambda b: b.timestamp_utc)
        return tuple(unique_bars)
