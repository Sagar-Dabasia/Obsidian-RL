"""Public Binance USD-M futures REST client (ADR-003).

Market data only. No credentials, no authenticated endpoints, no order capability.
Failures raise DataFetchError explicitly — synthetic data is never substituted.
"""

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import pandas as pd
import requests

from obsidian_rl.data.schema import interval_to_ms, klines_to_frame
from obsidian_rl.data.research_access import validate_temporal_access

logger = logging.getLogger(__name__)

MAX_LIMIT = 1500


class DataFetchError(RuntimeError):
    """Market data could not be retrieved. Callers must not fall back to synthetic data."""
    pass


class MarketDataSource(Protocol):
    def fetch_klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None
    ) -> pd.DataFrame: ...


class BinanceFuturesRest:
    """Paginated public kline fetcher for GET /fapi/v1/klines."""

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        *,
        session: requests.Session | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = timeout_s
        self._max_retries = max_retries
        self._sleep = sleep

    def _get_klines_page(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None, limit: int
    ) -> list[list[Any]]:
        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "limit": limit,
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        url = f"{self._base}/fapi/v1/klines"
        last_error: str = "no attempts made"
        for attempt in range(self._max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                last_error = f"request error: {exc}"
            else:
                if resp.status_code == 200:
                    payload = resp.json()
                    if not isinstance(payload, list):
                        raise DataFetchError(f"unexpected klines payload type {type(payload)}")
                    return payload
                if resp.status_code in (429, 418):
                    retry_after = float(resp.headers.get("Retry-After", "0") or 0)
                    wait = max(retry_after, 2.0 ** (attempt + 1))
                    logger.warning("rate limited (%s); backing off %.1fs", resp.status_code, wait)
                    self._sleep(wait)
                    last_error = f"HTTP {resp.status_code}"
                    continue
                if 500 <= resp.status_code < 600:
                    last_error = f"HTTP {resp.status_code}"
                else:
                    raise DataFetchError(
                        f"klines request failed: HTTP {resp.status_code}: {resp.text[:200]}"
                    )
            self._sleep(min(2.0**attempt, 30.0))
        raise DataFetchError(
            f"klines request failed after {self._max_retries} retries: {last_error}"
        )

    def fetch_klines(
        self, symbol: str, interval: str, start_ms: int, end_ms: int | None = None
    ) -> pd.DataFrame:
        """Fetch [start_ms, end_ms] inclusive, paginating past the 1500-candle limit."""
        # Cycle 2 research temporal access guard
        effective_end = end_ms if end_ms is not None else (1 << 63) - 1
        validate_temporal_access(start_ms, effective_end)

        ms = interval_to_ms(interval)
        rows: list[list[Any]] = []
        cursor = start_ms
        while True:
            page = self._get_klines_page(symbol, interval, cursor, end_ms, MAX_LIMIT)
            if not page:
                break
            rows.extend(page)
            last_open = int(page[-1][0])
            next_cursor = last_open + ms
            if len(page) < MAX_LIMIT or (end_ms is not None and next_cursor > end_ms):
                break
            if next_cursor <= cursor:
                raise DataFetchError("pagination cursor did not advance; aborting")
            cursor = next_cursor
        return klines_to_frame(rows)

    def fetch_funding_rates(
        self, symbol: str, start_ms: int, end_ms: int | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Fetch funding rate history from GET /fapi/v1/fundingRate."""
        # Cycle 2 research temporal access guard
        effective_end = end_ms if end_ms is not None else (1 << 63) - 1
        validate_temporal_access(start_ms, effective_end)

        url = f"{self._base}/fapi/v1/fundingRate"
        params: dict[str, str | int] = {
            "symbol": symbol,
            "startTime": start_ms,
            "limit": limit,
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        last_error: str = "no attempts made"
        for attempt in range(self._max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                last_error = f"request error: {exc}"
            else:
                if resp.status_code == 200:
                    payload = resp.json()
                    if not isinstance(payload, list):
                        raise DataFetchError(f"unexpected fundingRate payload type {type(payload)}")
                    out: list[dict[str, Any]] = []
                    for item in payload:
                        if not isinstance(item, dict):
                            raise DataFetchError("fundingRate item must be a dict")
                        out.append(
                            {
                                "symbol": str(item["symbol"]),
                                "funding_time_ms": int(item["fundingTime"]),
                                "funding_rate": float(item["fundingRate"]),
                                "mark_price": float(item.get("markPrice", 0.0) or 0.0),
                            }
                        )
                    return out
                if resp.status_code in (429, 418):
                    retry_after = float(resp.headers.get("Retry-After", "0") or 0)
                    wait = max(retry_after, 2.0 ** (attempt + 1))
                    logger.warning("rate limited (%s); backing off %.1fs", resp.status_code, wait)
                    self._sleep(wait)
                    last_error = f"HTTP {resp.status_code}"
                    continue
                if 500 <= resp.status_code < 600:
                    last_error = f"HTTP {resp.status_code}"
                else:
                    raise DataFetchError(
                        f"fundingRate request failed: HTTP {resp.status_code}: {resp.text[:200]}"
                    )
            self._sleep(min(2.0**attempt, 30.0))
        raise DataFetchError(
            f"fundingRate request failed after {self._max_retries} retries: {last_error}"
        )