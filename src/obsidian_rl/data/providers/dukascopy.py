"""Dukascopy public market-data provider adapter.

Reads historical Forex tick data or pre-aggregated OHLCV from Dukascopy.
To avoid implementing a complex Bi5 binary parser, we support reading
the official CSV exports or interacting with an official API if available.
Since Dukascopy provides data primarily as CSV downloads via their tick data suite
or similar tools, this adapter will parse standardized Dukascopy CSVs.
"""

import csv
import math
from datetime import UTC, datetime
from pathlib import Path
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


class DukascopyCSVProvider(BaseRestProvider, MarketDataProvider):
    """Canonical provider for parsing official Dukascopy historical CSV exports."""

    provider_name: str = "DUKASCOPY"
    adapter_version: str = "1.0.0"

    _SUPPORTED_TIMEFRAMES: ClassVar[set[Timeframe]] = {
        Timeframe.M1,
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.M30,
        Timeframe.H1,
        Timeframe.H4,
        Timeframe.D1,
    }

    def __init__(self, data_dir: str = "data/dukascopy", **kwargs: Any) -> None:
        # Dukascopy CSV provider might not use base_url if local
        super().__init__(base_url="local://", **kwargs)
        self.data_dir = Path(data_dir)

    def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[MarketBar, ...]:
        """Fetch Dukascopy bars by parsing local CSV exports for the given symbol and timeframe."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")

        tf_enum = self._validate_timeframe(timeframe)
        if tf_enum not in self._SUPPORTED_TIMEFRAMES:
            raise UnsupportedSymbolTimeframeError(
                f"Timeframe {tf_enum.value} is not supported by DukascopyCSVProvider"
            )

        if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
            raise TypeError("start_ms must be a non-negative integer")
        if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms < 0:
            raise TypeError("end_ms must be a non-negative integer")
        if end_ms <= start_ms:
            raise ValueError(
                f"end_ms ({end_ms}) must be strictly greater than start_ms ({start_ms})"
            )

        # We expect a file named like {symbol}_{timeframe}.csv in self.data_dir
        # The CSV should have headers: time,open,high,low,close,volume
        csv_path = self.data_dir / f"{symbol}_{tf_enum.value}.csv"
        if not csv_path.exists():
            raise MalformedResponseError(f"Local Dukascopy CSV not found: {csv_path}")

        collected_bars: list[MarketBar] = []
        current_time_ms = self._current_time_provider()

        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if headers is None:
                raise MalformedResponseError("Empty CSV file")

            # Identify columns (assuming Dukascopy format like: "Time (UTC)", "Open", "High", "Low", "Close", "Volume")
            # If standard format, index 0 is Time (string), 1 is Open, 2 High, 3 Low, 4 Close, 5 Volume

            for row in reader:
                if not row or len(row) < 6:
                    continue

                try:
                    # Parse timestamp (e.g., '2023-01-01 00:00:00' or ms timestamp)
                    time_str = row[0]
                    if time_str.isdigit():
                        open_time = int(time_str)
                    else:
                        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        dt = dt.replace(tzinfo=UTC)
                        open_time = int(dt.timestamp() * 1000)

                    # Determine close time based on timeframe
                    # A hacky way for now, or just observed_at = open_time + duration
                    # We will assume observed_at_utc is simply open_time + ms_in_timeframe
                    # Let's map duration
                    tf_ms = {
                        Timeframe.M1: 60_000,
                        Timeframe.M5: 300_000,
                        Timeframe.M15: 900_000,
                        Timeframe.M30: 1800_000,
                        Timeframe.H1: 3600_000,
                        Timeframe.H4: 14400_000,
                        Timeframe.D1: 86400_000,
                    }[tf_enum]

                    close_time = open_time + tf_ms - 1
                    observed_at_utc = close_time + 1

                    if open_time < start_ms:
                        continue
                    if open_time >= end_ms:
                        break  # Since CSV is sorted

                    if observed_at_utc > current_time_ms:
                        continue

                    open_val = float(row[1])
                    high_val = float(row[2])
                    low_val = float(row[3])
                    close_val = float(row[4])
                    vol_val = float(row[5])

                except (ValueError, TypeError, KeyError) as exc:
                    raise MalformedResponseError(f"Malformed Dukascopy row: {row}") from exc

                if not (
                    math.isfinite(open_val)
                    and math.isfinite(high_val)
                    and math.isfinite(low_val)
                    and math.isfinite(close_val)
                    and math.isfinite(vol_val)
                ):
                    raise MalformedResponseError(
                        f"Non-finite price or volume values detected in Dukascopy row: {row!r}"
                    )

                bar = MarketBar(
                    asset_class=AssetClass.FOREX,
                    venue="DUKASCOPY",
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
                    volume_type=VolumeType.TICK,  # Dukascopy forex uses tick volume
                    volume=vol_val,
                    data_source="DUKASCOPY_CSV",
                    schema_version=SCHEMA_VERSION_V2,
                )
                collected_bars.append(bar)

        return self._finalize_bars(collected_bars, start_ms, end_ms)
