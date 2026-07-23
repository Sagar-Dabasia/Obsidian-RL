"""Data-quality validation pipeline for cross-asset market bar series."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from obsidian_rl.data.contracts import AssetClass, MarketBar, Timeframe
from obsidian_rl.data.fingerprint import compute_market_bar_hash
from obsidian_rl.data.outages import OutageRegistry


@dataclass(frozen=True)
class DataQualityReport:
    """Structured report detailing market data quality validation results."""

    rows_checked: int
    first_timestamp_utc: int | None
    last_timestamp_utc: int | None
    duplicates: int
    missing_intervals: list[tuple[int, int]]
    unexpected_intervals: int
    hash_failures: int
    observation_failures: int
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def timeframe_to_ms(tf: Timeframe | str) -> int:
    """Convert Timeframe enum or string representation to exact duration in milliseconds."""
    tf_str = tf.value if isinstance(tf, Timeframe) else str(tf)
    mapping = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "2h": 7_200_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }
    if tf_str not in mapping:
        raise ValueError(f"Unsupported timeframe for millisecond conversion: {tf_str!r}")
    return mapping[tf_str]


@dataclass(frozen=True)
class ForexSessionConfig:
    """Configurable hours and rules for Forex market weekend closures."""

    close_weekday: int = 4  # Friday (weekday 4)
    close_hour: int = 20  # 20:00 UTC
    open_weekday: int = 6  # Sunday (weekday 6)
    open_hour: int = 20  # 20:00 UTC
    open_next_day_max_hour: int = 4  # Monday (weekday 0) 04:00 UTC
    min_gap_ms: int = 144_000_000  # 40 hours
    max_gap_ms: int = 201_600_000  # 56 hours


def is_forex_weekend_gap(
    ts_start_ms: int, ts_end_ms: int, config: ForexSessionConfig | None = None
) -> bool:
    """Check if the gap between two timestamps represents a standard Forex weekend closure."""
    config = config or ForexSessionConfig()
    dt_start = datetime.fromtimestamp(ts_start_ms / 1000.0, tz=UTC)
    dt_end = datetime.fromtimestamp(ts_end_ms / 1000.0, tz=UTC)

    # Allow closure to happen on the close day at or after close_hour, or the following day
    start_is_weekend_close = (
        dt_start.weekday() == config.close_weekday and dt_start.hour >= config.close_hour
    ) or (dt_start.weekday() == (config.close_weekday + 1) % 7)

    # Allow open to happen on the open day at or after open_hour,
    # or the following day before next_day_max
    end_is_weekend_open = (
        dt_end.weekday() == config.open_weekday and dt_end.hour >= config.open_hour
    ) or (
        dt_end.weekday() == (config.open_weekday + 1) % 7
        and dt_end.hour <= config.open_next_day_max_hour
    )

    gap_duration_ms = ts_end_ms - ts_start_ms
    is_valid_duration = config.min_gap_ms <= gap_duration_ms <= config.max_gap_ms

    return start_is_weekend_close and end_is_weekend_open and is_valid_duration


def validate_market_bars(
    bars: Sequence[MarketBar],
    expected_timeframe: Timeframe | str | None = None,
    expected_symbol: str | None = None,
    expected_venue: str | None = None,
    is_forex: bool | None = None,
    forex_session_config: ForexSessionConfig | None = None,
    outage_registry: OutageRegistry | None = None,
) -> DataQualityReport:
    """Inspect a sequence of MarketBar objects for data quality violations."""
    if not bars:
        return DataQualityReport(
            rows_checked=0,
            first_timestamp_utc=None,
            last_timestamp_utc=None,
            duplicates=0,
            missing_intervals=[],
            unexpected_intervals=0,
            hash_failures=0,
            observation_failures=0,
            passed=True,
            details={"info": "Empty bar sequence provided"},
        )

    rows_checked = len(bars)
    first_ts = bars[0].timestamp_utc
    last_ts = bars[-1].timestamp_utc

    duplicates = 0
    missing_intervals: list[tuple[int, int]] = []
    unexpected_intervals = 0
    hash_failures = 0
    observation_failures = 0
    errors: list[str] = []

    # Check series consistency
    first_bar = bars[0]
    target_symbol = expected_symbol or first_bar.symbol
    target_venue = expected_venue or first_bar.venue
    target_tf_str = (
        expected_timeframe.value
        if isinstance(expected_timeframe, Timeframe)
        else (expected_timeframe or first_bar.timeframe.value)
    )

    is_forex_series = (
        is_forex if is_forex is not None else (first_bar.asset_class == AssetClass.FOREX)
    )
    step_ms = timeframe_to_ms(target_tf_str)

    # Perform per-bar checks
    for idx, bar in enumerate(bars):
        if bar.symbol != target_symbol:
            errors.append(
                f"Mixed symbol at index {idx}: expected {target_symbol!r}, got {bar.symbol!r}"
            )
        if bar.venue != target_venue:
            errors.append(
                f"Mixed venue at index {idx}: expected {target_venue!r}, got {bar.venue!r}"
            )
        if bar.timeframe.value != target_tf_str:
            err_msg = (
                f"Mixed timeframe at index {idx}: "
                f"expected {target_tf_str!r}, got {bar.timeframe.value!r}"
            )
            errors.append(err_msg)

        # Cryptographic hash verification
        if bar.row_hash != compute_market_bar_hash(bar):
            hash_failures += 1

        # Point-in-time observation check
        if bar.observed_at_utc < bar.timestamp_utc:
            observation_failures += 1

    # Perform sequence timestamp checks
    for idx in range(len(bars) - 1):
        b1, b2 = bars[idx], bars[idx + 1]
        ts1, ts2 = b1.timestamp_utc, b2.timestamp_utc

        if ts2 == ts1:
            duplicates += 1
            errors.append(f"Duplicate timestamp detected at index {idx}: {ts1}")
            continue

        if ts2 < ts1:
            unexpected_intervals += 1
            errors.append(f"Out-of-order timestamps at index {idx}: {ts1} > {ts2}")
            continue

        diff = ts2 - ts1
        if diff % step_ms != 0:
            unexpected_intervals += 1
            err_msg = (
                f"Inconsistent timeframe spacing between index {idx} ({ts1}) "
                f"and {idx + 1} ({ts2}): gap {diff} ms not multiple of {step_ms} ms"
            )
            errors.append(err_msg)
        elif diff > step_ms:
            if is_forex_series and is_forex_weekend_gap(ts1, ts2, forex_session_config):
                # Expected Forex weekend closure - ignore
                pass
            elif outage_registry and outage_registry.covers_gap(target_venue, ts1 + step_ms, ts2):
                # Expected venue outage - ignore
                pass
            else:
                missing_intervals.append((ts1 + step_ms, diff))

    has_errors = (
        len(errors) > 0
        or duplicates > 0
        or unexpected_intervals > 0
        or len(missing_intervals) > 0
        or hash_failures > 0
        or observation_failures > 0
    )

    return DataQualityReport(
        rows_checked=rows_checked,
        first_timestamp_utc=first_ts,
        last_timestamp_utc=last_ts,
        duplicates=duplicates,
        missing_intervals=missing_intervals,
        unexpected_intervals=unexpected_intervals,
        hash_failures=hash_failures,
        observation_failures=observation_failures,
        passed=not has_errors,
        details={"errors": errors} if errors else {},
    )
