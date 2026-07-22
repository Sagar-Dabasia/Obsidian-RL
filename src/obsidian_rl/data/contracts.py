"""Canonical data contracts (`MarketBar`, `EventNewsItem`) for Cycle 02 cross-asset engines.

Enforces strict point-in-time ordering, look-ahead prevention (`observed_at_utc`),
schema versioning, automatic SHA-256 fingerprinting, and rejection of NaN/Infinity values.
"""

import math
import time
from dataclasses import dataclass

from obsidian_rl.data.fingerprint import (
    compute_event_news_hash,
    compute_market_bar_hash,
)

SCHEMA_VERSION_V2: str = "SCHEMA_V2"
DEFAULT_MAX_SKEW_MS: int = 300_000


@dataclass(frozen=True)
class MarketBar:
    """Canonical multi-asset OHLCV market bar data contract.

    Guarantees strict point-in-time timestamp discipline (`observed_at_utc` vs `timestamp_utc`),
    rejection of non-finite/bool values, and automatic SHA-256 fingerprinting via `row_hash`.
    """

    asset_class: str
    venue: str
    symbol: str
    timeframe: str
    timestamp_utc: int
    observed_at_utc: int
    open: float
    high: float
    low: float
    close: float
    bid: float
    ask: float
    volume: float
    data_source: str
    data_version: str = SCHEMA_VERSION_V2
    row_hash: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "asset_class",
            "venue",
            "symbol",
            "timeframe",
            "data_source",
            "data_version",
        ):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"MarketBar.{field_name} must be a non-empty string, got {val!r}"
                )

        for field_name in ("timestamp_utc", "observed_at_utc"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(
                    f"MarketBar.{field_name} must be an integer (ms UTC), "
                    f"got {type(val).__name__}"
                )
            if val < 0:
                raise ValueError(
                    f"MarketBar.{field_name} cannot be negative, got {val}"
                )

        max_allowed_ms = int(time.time() * 1000) + DEFAULT_MAX_SKEW_MS
        if self.observed_at_utc > max_allowed_ms:
            raise RuntimeError(
                f"Future timestamp rejection: observed_at_utc ({self.observed_at_utc}) "
                f"exceeds current wall-clock plus skew allowance ({max_allowed_ms})"
            )
        if self.observed_at_utc < self.timestamp_utc:
            raise ValueError(
                f"MarketBar.observed_at_utc ({self.observed_at_utc}) cannot be earlier than "
                f"timestamp_utc ({self.timestamp_utc})"
            )

        for field_name in ("open", "high", "low", "close", "bid", "ask", "volume"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise TypeError(
                    f"MarketBar.{field_name} must be float or int, "
                    f"got {type(val).__name__}"
                )
            fval = float(val)
            if not math.isfinite(fval):
                raise ValueError(
                    f"MarketBar.{field_name} must be finite (rejecting NaN/Infinity), "
                    f"got {fval}"
                )
            object.__setattr__(self, field_name, fval)

        if self.open <= 0.0 or self.high <= 0.0 or self.low <= 0.0 or self.close <= 0.0:
            raise ValueError("MarketBar OHLC prices must be strictly positive (> 0)")
        if self.bid <= 0.0 or self.ask <= 0.0:
            raise ValueError(
                "MarketBar bid and ask quotes must be strictly positive (> 0)"
            )
        if self.volume < 0.0:
            raise ValueError("MarketBar volume cannot be negative")

        if self.high < self.open or self.high < self.low or self.high < self.close:
            raise ValueError(
                f"MarketBar.high ({self.high}) must be >= open, low, and close "
                f"({self.open}, {self.low}, {self.close})"
            )
        if self.low > self.open or self.low > self.high or self.low > self.close:
            raise ValueError(
                f"MarketBar.low ({self.low}) must be <= open, high, and close "
                f"({self.open}, {self.high}, {self.close})"
            )
        if self.ask < self.bid:
            raise ValueError(f"MarketBar.ask ({self.ask}) must be >= bid ({self.bid})")

        if self.row_hash:
            if (
                not isinstance(self.row_hash, str)
                or len(self.row_hash) != 64
                or not all(c in "0123456789abcdef" for c in self.row_hash)
            ):
                raise ValueError(
                    "MarketBar.row_hash must be a 64-character lowercase hex string, "
                    f"got {self.row_hash!r}"
                )
            computed = compute_market_bar_hash(self)
            if self.row_hash != computed:
                raise RuntimeError(
                    f"MarketBar hash mismatch: computed {computed} != provided {self.row_hash}"
                )
        else:
            computed = compute_market_bar_hash(self)
            object.__setattr__(self, "row_hash", computed)


@dataclass(frozen=True)
class EventNewsItem:
    """Canonical economic event and news item data contract.

    Enforces revision tracking (`first_observed_at` vs `updated_at`),
    rejection of non-finite/bool values (`allow_nan=False`), and deterministic SHA-256
    fingerprinting via `raw_content_hash`.
    """

    event_id: str
    source: str
    source_reliability: float
    original_published_at: int
    first_observed_at: int
    updated_at: int
    affected_assets: tuple[str, ...]
    event_type: str
    expected_value: float | None
    actual_value: float | None
    surprise_value: float | None
    raw_content_hash: str = ""
    sentiment_score: float = 0.0
    revision_status: str = "INITIAL"

    def __post_init__(self) -> None:
        for field_name in ("event_id", "source", "event_type", "revision_status"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"EventNewsItem.{field_name} must be a non-empty string, got {val!r}"
                )

        for field_name in ("original_published_at", "first_observed_at", "updated_at"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(
                    f"EventNewsItem.{field_name} must be an integer (ms UTC), "
                    f"got {type(val).__name__}"
                )
            if val < 0:
                raise ValueError(
                    f"EventNewsItem.{field_name} cannot be negative, got {val}"
                )

        max_allowed_ms = int(time.time() * 1000) + DEFAULT_MAX_SKEW_MS
        if self.first_observed_at > max_allowed_ms:
            raise RuntimeError(
                f"Future timestamp rejection: first_observed_at ({self.first_observed_at}) "
                f"exceeds current wall-clock plus skew allowance ({max_allowed_ms})"
            )
        if self.updated_at > max_allowed_ms:
            raise RuntimeError(
                f"Future timestamp rejection: updated_at ({self.updated_at}) "
                f"exceeds current wall-clock plus skew allowance ({max_allowed_ms})"
            )
        if self.updated_at < self.first_observed_at:
            raise ValueError(
                f"EventNewsItem.updated_at ({self.updated_at}) cannot be earlier than "
                f"first_observed_at ({self.first_observed_at})"
            )

        if isinstance(self.affected_assets, str) or not isinstance(
            self.affected_assets, (tuple, list, set)
        ):
            raise TypeError(
                "EventNewsItem.affected_assets must be a sequence of strings, "
                f"got {type(self.affected_assets).__name__}"
            )
        normalized_assets = []
        for item in self.affected_assets:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    "EventNewsItem.affected_assets elements must be non-empty strings, "
                    f"got {item!r}"
                )
            normalized_assets.append(item.strip())
        object.__setattr__(self, "affected_assets", tuple(normalized_assets))

        if isinstance(self.source_reliability, bool) or not isinstance(
            self.source_reliability, (int, float)
        ):
            raise TypeError(
                "EventNewsItem.source_reliability must be float or int, "
                f"got {type(self.source_reliability).__name__}"
            )
        f_rel = float(self.source_reliability)
        if not math.isfinite(f_rel) or not (0.0 <= f_rel <= 1.0):
            raise ValueError(
                "EventNewsItem.source_reliability must be finite and in [0.0, 1.0], "
                f"got {f_rel}"
            )
        object.__setattr__(self, "source_reliability", f_rel)

        if isinstance(self.sentiment_score, bool) or not isinstance(
            self.sentiment_score, (int, float)
        ):
            raise TypeError(
                "EventNewsItem.sentiment_score must be float or int, "
                f"got {type(self.sentiment_score).__name__}"
            )
        f_sent = float(self.sentiment_score)
        if not math.isfinite(f_sent) or not (-1.0 <= f_sent <= 1.0):
            raise ValueError(
                "EventNewsItem.sentiment_score must be finite and in [-1.0, 1.0], "
                f"got {f_sent}"
            )
        object.__setattr__(self, "sentiment_score", f_sent)

        for field_name in ("expected_value", "actual_value", "surprise_value"):
            val = getattr(self, field_name)
            if val is not None:
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    raise TypeError(
                        f"EventNewsItem.{field_name} must be float, int, or None, "
                        f"got {type(val).__name__}"
                    )
                fval = float(val)
                if not math.isfinite(fval):
                    raise ValueError(
                        f"EventNewsItem.{field_name} must be finite (rejecting NaN/Infinity), "
                        f"got {fval}"
                    )
                object.__setattr__(self, field_name, fval)

        if self.raw_content_hash:
            if (
                not isinstance(self.raw_content_hash, str)
                or len(self.raw_content_hash) != 64
                or not all(c in "0123456789abcdef" for c in self.raw_content_hash)
            ):
                raise ValueError(
                    "EventNewsItem.raw_content_hash must be a 64-char lowercase hex string, "
                    f"got {self.raw_content_hash!r}"
                )
            computed = compute_event_news_hash(self)
            if self.raw_content_hash != computed:
                raise RuntimeError(
                    f"EventNewsItem hash mismatch: computed {computed} "
                    f"!= provided {self.raw_content_hash}"
                )
        else:
            computed = compute_event_news_hash(self)
            object.__setattr__(self, "raw_content_hash", computed)
