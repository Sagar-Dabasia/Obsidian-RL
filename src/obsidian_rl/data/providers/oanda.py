"""OANDA Practice Forex market-data provider adapter (`MarketDataProvider`).

Reads completed OHLCV candles from:
`https://api-fxpractice.oanda.com/v3/instruments/{symbol}/candles`.
Requires authentication token via `api_token` argument or `OANDA_API_TOKEN` env var.
Never logs or prints tokens. Enforces `AssetClass.FOREX`, `Venue: OANDA_PRACTICE`,
`QuoteStatus.OBSERVED`, and `VolumeType.TICK`.
"""

import math
import os
from datetime import UTC, datetime
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
    AuthenticationError,
    MalformedResponseError,
    UnsupportedSymbolTimeframeError,
)


class OandaPracticeProvider(BaseRestProvider, MarketDataProvider):
    """Canonical read-only provider for OANDA Practice fx kline data."""

    provider_name: str = "OANDA"
    adapter_version: str = "1.0.0"

    _GRANULARITY_MAP: ClassVar[dict[Timeframe, str]] = {
        Timeframe.M1: "M1",
        Timeframe.M5: "M5",
        Timeframe.M15: "M15",
        Timeframe.M30: "M30",
        Timeframe.H1: "H1",
        Timeframe.H2: "H2",
        Timeframe.H4: "H4",
        Timeframe.D1: "D",
    }

    _TIMEFRAME_MS: ClassVar[dict[Timeframe, int]] = {
        Timeframe.M1: 60_000,
        Timeframe.M5: 300_000,
        Timeframe.M15: 900_000,
        Timeframe.M30: 1_800_000,
        Timeframe.H1: 3_600_000,
        Timeframe.H2: 7_200_000,
        Timeframe.H4: 14_400_000,
        Timeframe.D1: 86_400_000,
    }

    def __init__(
        self,
        base_url: str = "https://api-fxpractice.oanda.com",
        api_token: str | None = None,
        **kwargs: Any,
    ) -> None:
        token = api_token or os.environ.get("OANDA_API_TOKEN")
        if not token or not isinstance(token, str) or not token.strip():
            raise AuthenticationError(
                "OANDA API token is missing. Must be supplied via constructor api_token "
                "or OANDA_API_TOKEN environment variable."
            )
        self._api_token = token.strip()

        # Register token in secrets tuple so BaseRestProvider / errors scrub it everywhere
        existing_secrets = kwargs.pop("secrets", ())
        secrets_tuple = (self._api_token, *tuple(existing_secrets))

        super().__init__(base_url=base_url, secrets=secrets_tuple, **kwargs)

    @staticmethod
    def _ms_to_rfc3339(ms: int) -> str:
        """Convert UTC milliseconds integer to OANDA-compatible RFC3339 string."""
        dt = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")

    @staticmethod
    def _parse_timestamp_ms(ts: Any) -> int:
        """Parse OANDA timestamp string (RFC3339 or UNIX seconds) into UTC milliseconds."""
        if not isinstance(ts, str) or not ts.strip():
            raise MalformedResponseError(f"Invalid OANDA timestamp format: {ts!r}")
        ts_str = ts.strip()
        try:
            if ts_str.replace(".", "", 1).isdigit() or (
                ts_str.startswith("-") and ts_str[1:].replace(".", "", 1).isdigit()
            ):
                return int(float(ts_str) * 1000)
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts_str)
            return int(dt.timestamp() * 1000)
        except Exception as exc:
            raise MalformedResponseError(f"Could not parse OANDA timestamp string: {ts!r}") from exc

    def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[MarketBar, ...]:
        """Fetch completed OANDA Practice candles for symbol within [start_ms, end_ms)."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")

        tf_enum = self._validate_timeframe(timeframe)
        if tf_enum not in self._GRANULARITY_MAP:
            raise UnsupportedSymbolTimeframeError(
                f"Timeframe {tf_enum.value} (granularity not mapped) is not supported "
                "by OandaPracticeProvider"
            )
        granularity = self._GRANULARITY_MAP[tf_enum]
        tf_ms = self._TIMEFRAME_MS[tf_enum]

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
        headers = {"Authorization": f"Bearer {self._api_token}"}

        while cursor_ms < end_ms:
            params: dict[str, Any] = {
                "price": "MBA",
                "granularity": granularity,
                "from": self._ms_to_rfc3339(cursor_ms),
                "to": self._ms_to_rfc3339(end_ms),
            }
            if granularity == "D":
                # For daily candles, explicitly request UTC alignment without silent defaults
                params["dailyAlignment"] = 0
                params["alignmentTimezone"] = "UTC"

            url = f"{self._base_url}/v3/instruments/{symbol}/candles"
            payload = self._request("GET", url, params=params, headers=headers)

            if not isinstance(payload, dict) or "candles" not in payload:
                raise MalformedResponseError(
                    f"Expected dict with 'candles' key from OANDA, got: {type(payload).__name__}"
                )
            candles = payload.get("candles", [])
            if not isinstance(candles, list):
                raise MalformedResponseError(
                    f"Expected list for OANDA 'candles' field, got: {type(candles).__name__}"
                )
            if not candles:
                break

            for row in candles:
                if not isinstance(row, dict):
                    raise MalformedResponseError(
                        f"Expected dict for OANDA candle item, got: {type(row).__name__}"
                    )

                is_complete = row.get("complete") in (True, "true", "True")
                timestamp_utc = self._parse_timestamp_ms(row.get("time"))
                observed_at_utc = timestamp_utc + tf_ms

                if not is_complete or observed_at_utc > current_time_ms:
                    # Skip forming or future candles cleanly
                    continue

                mid = row.get("mid")
                bid_dict = row.get("bid")
                ask_dict = row.get("ask")
                if (
                    not isinstance(mid, dict)
                    or not isinstance(bid_dict, dict)
                    or not isinstance(ask_dict, dict)
                ):
                    raise MalformedResponseError(
                        f"OANDA candle missing required mid, bid, or ask dicts: {row!r}"
                    )

                try:
                    open_val = float(mid["o"])
                    high_val = float(mid["h"])
                    low_val = float(mid["l"])
                    close_val = float(mid["c"])
                    bid_val = float(bid_dict["c"])
                    ask_val = float(ask_dict["c"])
                    vol_val = float(row.get("volume", 0))
                except (ValueError, TypeError, KeyError) as exc:
                    raise MalformedResponseError(
                        f"Malformed OANDA numerical component or missing key: {row!r}"
                    ) from exc

                if not (
                    math.isfinite(open_val)
                    and math.isfinite(high_val)
                    and math.isfinite(low_val)
                    and math.isfinite(close_val)
                    and math.isfinite(bid_val)
                    and math.isfinite(ask_val)
                    and math.isfinite(vol_val)
                ):
                    raise MalformedResponseError(
                        f"Non-finite price or volume values detected in OANDA candle: {row!r}"
                    )

                if ask_val < bid_val:
                    raise MalformedResponseError(
                        f"Crossed bid/ask quotes detected: bid={bid_val}, ask={ask_val}"
                    )

                bar = MarketBar(
                    asset_class=AssetClass.FOREX,
                    venue="OANDA_PRACTICE",
                    symbol=symbol,
                    timeframe=tf_enum,
                    timestamp_utc=timestamp_utc,
                    observed_at_utc=observed_at_utc,
                    open=open_val,
                    high=high_val,
                    low=low_val,
                    close=close_val,
                    quote_status=QuoteStatus.OBSERVED,
                    bid=bid_val,
                    ask=ask_val,
                    volume_type=VolumeType.TICK,
                    volume=vol_val,
                    data_source="OANDA_PRACTICE_REST",
                    schema_version=SCHEMA_VERSION_V2,
                )
                collected_bars.append(bar)

            if len(candles) < 5000:
                break

            last_ts = self._parse_timestamp_ms(candles[-1].get("time"))
            next_cursor = last_ts + tf_ms
            if next_cursor <= cursor_ms:
                raise MalformedResponseError(
                    f"OANDA pagination stalled: last timestamp {last_ts} <= cursor {cursor_ms}"
                )
            cursor_ms = next_cursor

        return self._finalize_bars(collected_bars, start_ms, end_ms)
