"""Binance Spot public market-data provider adapter (`MarketDataProvider`).

Reads completed OHLCV candles from `https://data-api.binance.vision/api/v3/klines`.
Requires no authentication or credentials. Enforces `AssetClass.CRYPTO`, `Venue: BINANCE_SPOT`,
`QuoteStatus.UNAVAILABLE`, and `VolumeType.BASE`.
"""

import math
from typing import Any, ClassVar

from obsidian_rl.data.contracts import (
    SCHEMA_VERSION_V2,
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.providers.base import BaseRestProvider, MarketDataProvider
from obsidian_rl.data.providers.errors import (
    MalformedResponseError,
    UnsupportedSymbolTimeframeError,
)


class BinanceSpotProvider(BaseRestProvider, MarketDataProvider):
    """Canonical read-only provider for Binance Spot public kline data."""

    provider_name: str = "BINANCE"
    adapter_version: str = "1.0.0"

    _SUPPORTED_TIMEFRAMES: ClassVar[set[Timeframe]] = {
        Timeframe.M1,
        Timeframe.M3,
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.M30,
        Timeframe.H1,
        Timeframe.H2,
        Timeframe.H4,
        Timeframe.D1,
    }

    def __init__(
        self,
        base_url: str = "https://data-api.binance.vision",
        **kwargs: Any,
    ) -> None:
        super().__init__(base_url=base_url, **kwargs)

    def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[MarketBar, ...]:
        """Fetch completed Binance Spot klines for symbol within [start_ms, end_ms)."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")

        tf_enum = self._validate_timeframe(timeframe)
        if tf_enum not in self._SUPPORTED_TIMEFRAMES:
            raise UnsupportedSymbolTimeframeError(
                f"Timeframe {tf_enum.value} is not supported by BinanceSpotProvider"
            )

        # Validate boundary inputs before making network calls
        if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
            raise TypeError("start_ms must be a non-negative integer")
        if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms < 0:
            raise TypeError("end_ms must be a non-negative integer")
        if end_ms <= start_ms:
            raise ValueError(
                f"end_ms ({end_ms}) must be strictly greater than start_ms ({start_ms})"
            )

        collected_bars: list[MarketBar] = []
        cursor_ms = start_ms
        current_time_ms = self._current_time_provider()

        while cursor_ms < end_ms:
            params = {
                "symbol": symbol,
                "interval": tf_enum.value,
                "startTime": cursor_ms,
                "endTime": end_ms - 1,
                "limit": 1000,
            }
            url = f"{self._base_url}/api/v3/klines"
            payload = self._request("GET", url, params=params)

            if not isinstance(payload, list):
                raise MalformedResponseError(
                    f"Expected list from Binance /api/v3/klines, got {type(payload).__name__}"
                )
            if not payload:
                break

            for row in payload:
                if not isinstance(row, (list, tuple)) or len(row) != 12:
                    actual_len = len(row) if isinstance(row, (list, tuple)) else type(row).__name__
                    raise MalformedResponseError(
                        f"Malformed Binance row: expected exactly 12 items, got {actual_len}"
                    )

                try:
                    open_time = int(row[0])
                    close_time = int(row[6])
                except (ValueError, TypeError) as exc:
                    raise MalformedResponseError(
                        f"Malformed Binance timestamps: openTime={row[0]!r}, closeTime={row[6]!r}"
                    ) from exc

                observed_at_utc = close_time + 1
                if observed_at_utc > current_time_ms:
                    # Candle is incomplete (forming after current_time_ms); reject cleanly
                    continue

                try:
                    open_val = float(row[1])
                    high_val = float(row[2])
                    low_val = float(row[3])
                    close_val = float(row[4])
                    vol_val = float(row[5])
                except (ValueError, TypeError) as exc:
                    raise MalformedResponseError(
                        f"Malformed Binance numerical values: {row[1:6]!r}"
                    ) from exc

                if not (
                    math.isfinite(open_val)
                    and math.isfinite(high_val)
                    and math.isfinite(low_val)
                    and math.isfinite(close_val)
                    and math.isfinite(vol_val)
                ):
                    raise MalformedResponseError(
                        f"Non-finite price or volume values detected in Binance row: {row[1:6]!r}"
                    )

                bar = MarketBar(
                    asset_class=AssetClass.CRYPTO,
                    venue="BINANCE_SPOT",
                    symbol=symbol,
                    timeframe=tf_enum,
                    timestamp_utc=open_time,
                    observed_at_utc=observed_at_utc,
                    open=open_val,
                    high=high_val,
                    low=low_val,
                    close=close_val,
                    quote_status=QuoteStatus.UNAVAILABLE,
                    bid=None,
                    ask=None,
                    volume_type=VolumeType.BASE,
                    volume=vol_val,
                    data_source="BINANCE_SPOT_REST",
                    schema_version=SCHEMA_VERSION_V2,
                )
                collected_bars.append(bar)

            if len(payload) < 1000:
                break

            last_open_time = int(payload[-1][0])
            next_cursor = last_open_time + 1
            if next_cursor <= cursor_ms:
                raise MalformedResponseError(
                    f"Binance pagination stalled: last open {last_open_time} <= cursor {cursor_ms}"
                )
            cursor_ms = next_cursor

        return self._finalize_bars(collected_bars, start_ms, end_ms)
