"""Canonical data contracts (`MarketBar`, `EventNewsItem`) for Cycle 02 cross-asset engines.

Enforces strict string enums, point-in-time timestamp discipline (`observed_at_utc`),
look-ahead prevention (`validate_ingestion_time`), schema versioning, automatic SHA-256
fingerprinting (`row_hash` / `record_hash`), and rejection of NaN/Infinity/bool values.
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from obsidian_rl.data.fingerprint import (
    compute_event_news_hash,
    compute_funding_rate_hash,
    compute_market_bar_hash,
)

SCHEMA_VERSION_V2: str = "SCHEMA_V2"
DEFAULT_MAX_SKEW_MS: int = 300_000


class AssetClass(StrEnum):
    """Strict string enum of supported institutional asset classes."""

    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    EQUITY = "EQUITY"
    COMMODITY = "COMMODITY"


class Timeframe(StrEnum):
    """Strict string enum of supported market bar intervals."""

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    D1 = "1d"


class QuoteStatus(StrEnum):
    """Strict string enum representing bid/ask quote availability."""

    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    UNAVAILABLE = "UNAVAILABLE"


class VolumeType(StrEnum):
    """Strict string enum representing volume reporting mode."""

    NONE = "NONE"
    BASE = "BASE"
    QUOTE = "QUOTE"
    TICK = "TICK"


class EventType(StrEnum):
    """Strict string enum of economic and market news event types."""

    INTEREST_RATE = "INTEREST_RATE"
    CPI = "CPI"
    NEWS_ARTICLE = "NEWS_ARTICLE"
    COT_REPORT = "COT_REPORT"
    GDP = "GDP"
    EMPLOYMENT = "EMPLOYMENT"
    INFLATION = "INFLATION"
    CENTRAL_BANK = "CENTRAL_BANK"
    OTHER = "OTHER"


class RevisionStatus(StrEnum):
    """Strict string enum representing economic release revision states."""

    INITIAL = "INITIAL"
    REVISED = "REVISED"
    FINAL = "FINAL"


@dataclass(frozen=True)
class MarketBar:
    """Canonical multi-asset OHLCV market bar data contract.

    Enforces strict enums, rejection of boolean/non-finite values, and SHA-256
    fingerprinting via `row_hash`.
    """

    asset_class: AssetClass
    venue: str
    symbol: str
    timeframe: Timeframe
    timestamp_utc: int
    observed_at_utc: int
    open: float
    high: float
    low: float
    close: float
    quote_status: QuoteStatus
    bid: float | None
    ask: float | None
    volume_type: VolumeType
    volume: float | None
    data_source: str
    schema_version: str = SCHEMA_VERSION_V2
    row_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.asset_class, AssetClass):
            raise TypeError(
                "asset_class must be an instance of AssetClass enum "
                f"(no silent enum conversion), got {type(self.asset_class).__name__}"
            )
        if not isinstance(self.timeframe, Timeframe):
            raise TypeError(
                "timeframe must be an instance of Timeframe enum "
                f"(no silent enum conversion), got {type(self.timeframe).__name__}"
            )
        if not isinstance(self.quote_status, QuoteStatus):
            raise TypeError(
                "quote_status must be an instance of QuoteStatus enum "
                f"(no silent enum conversion), got {type(self.quote_status).__name__}"
            )
        if not isinstance(self.volume_type, VolumeType):
            raise TypeError(
                "volume_type must be an instance of VolumeType enum "
                f"(no silent enum conversion), got {type(self.volume_type).__name__}"
            )

        for field_name in ("venue", "symbol", "data_source", "schema_version"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"MarketBar.{field_name} must be a non-empty string, got {val!r}")

        if self.schema_version != SCHEMA_VERSION_V2:
            raise ValueError(
                f"Unsupported schema_version: expected {SCHEMA_VERSION_V2!r}, "
                f"got {self.schema_version!r}"
            )

        for field_name in ("timestamp_utc", "observed_at_utc"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(
                    f"MarketBar.{field_name} must be an integer (ms UTC), got {type(val).__name__}"
                )
            if val < 0:
                raise ValueError(f"MarketBar.{field_name} cannot be negative, got {val}")

        if self.observed_at_utc < self.timestamp_utc:
            raise ValueError(
                f"MarketBar.observed_at_utc ({self.observed_at_utc}) cannot be "
                f"earlier than timestamp_utc ({self.timestamp_utc})"
            )

        for field_name in ("open", "high", "low", "close"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise TypeError(
                    f"MarketBar.{field_name} must be float or int, got {type(val).__name__}"
                )
            fval = float(val)
            if not math.isfinite(fval):
                raise ValueError(
                    f"MarketBar.{field_name} must be finite (rejecting NaN/Infinity), got {fval}"
                )
            object.__setattr__(self, field_name, fval)

        if self.open <= 0.0 or self.high <= 0.0 or self.low <= 0.0 or self.close <= 0.0:
            raise ValueError("MarketBar OHLC prices must be strictly positive (> 0)")

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

        if (self.bid is None) != (self.ask is None):
            raise ValueError("bid and ask must either both exist or both be None")

        if self.quote_status == QuoteStatus.UNAVAILABLE and (
            self.bid is not None or self.ask is not None
        ):
            raise ValueError("QuoteStatus.UNAVAILABLE requires both bid and ask to be None")
        elif self.quote_status in (QuoteStatus.OBSERVED, QuoteStatus.DERIVED) and (
            self.bid is None or self.ask is None
        ):
            raise ValueError(
                f"QuoteStatus.{self.quote_status.name} requires bid and ask to be present"
            )

        if self.bid is not None and self.ask is not None:
            for field_name, val in (("bid", self.bid), ("ask", self.ask)):
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    raise TypeError(
                        f"MarketBar.{field_name} must be float or int, got {type(val).__name__}"
                    )
            f_bid = float(self.bid)
            f_ask = float(self.ask)
            if not math.isfinite(f_bid) or not math.isfinite(f_ask):
                raise ValueError("MarketBar bid and ask must be finite (rejecting NaN/Infinity)")
            if f_bid <= 0.0 or f_ask <= 0.0:
                raise ValueError("MarketBar bid and ask quotes must be strictly positive (> 0)")
            if f_ask < f_bid:
                raise ValueError(f"MarketBar.ask ({f_ask}) must be >= bid ({f_bid})")
            object.__setattr__(self, "bid", f_bid)
            object.__setattr__(self, "ask", f_ask)

        if self.volume_type == VolumeType.NONE and self.volume is not None:
            raise ValueError("VolumeType.NONE requires volume=None")
        elif self.volume_type in (VolumeType.BASE, VolumeType.QUOTE, VolumeType.TICK):
            if self.volume is None:
                raise ValueError(
                    f"VolumeType.{self.volume_type.name} requires finite volume >= 0, got None"
                )
            if isinstance(self.volume, bool) or not isinstance(self.volume, (int, float)):
                raise TypeError(
                    f"MarketBar.volume must be float or int, got {type(self.volume).__name__}"
                )
            f_vol = float(self.volume)
            if not math.isfinite(f_vol):
                raise ValueError("MarketBar.volume must be finite (rejecting NaN/Infinity)")
            if f_vol < 0.0:
                raise ValueError("MarketBar volume cannot be negative")
            object.__setattr__(self, "volume", f_vol)

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize MarketBar to dictionary with stable enum string values."""
        return {
            "asset_class": self.asset_class.value,
            "venue": self.venue,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp_utc": self.timestamp_utc,
            "observed_at_utc": self.observed_at_utc,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "quote_status": self.quote_status.value,
            "bid": self.bid,
            "ask": self.ask,
            "volume_type": self.volume_type.value,
            "volume": self.volume,
            "data_source": self.data_source,
            "schema_version": self.schema_version,
            "row_hash": self.row_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], verify_hash: bool = True) -> "MarketBar":
        """Reconstruct MarketBar from dict, enforcing exact boundaries and tamper check."""
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        expected_keys = {
            "asset_class",
            "venue",
            "symbol",
            "timeframe",
            "timestamp_utc",
            "observed_at_utc",
            "open",
            "high",
            "low",
            "close",
            "quote_status",
            "bid",
            "ask",
            "volume_type",
            "volume",
            "data_source",
            "schema_version",
            "row_hash",
        }
        actual_keys = set(data.keys())
        unknown = actual_keys - expected_keys
        if unknown:
            raise ValueError(f"Unknown fields rejected during deserialization: {sorted(unknown)}")
        missing = expected_keys - actual_keys
        if missing:
            raise ValueError(f"Missing fields rejected during deserialization: {sorted(missing)}")

        if verify_hash:
            row_hash = data.get("row_hash")
            if not isinstance(row_hash, str) or len(row_hash) != 64:
                raise ValueError(
                    "Tamper rejection: serialized MarketBar missing valid 64-char row_hash"
                )

        try:
            asset_class = (
                AssetClass(data["asset_class"])
                if isinstance(data["asset_class"], str)
                else data["asset_class"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid AssetClass: {data['asset_class']!r}") from exc

        try:
            timeframe = (
                Timeframe(data["timeframe"])
                if isinstance(data["timeframe"], str)
                else data["timeframe"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid Timeframe: {data['timeframe']!r}") from exc

        try:
            quote_status = (
                QuoteStatus(data["quote_status"])
                if isinstance(data["quote_status"], str)
                else data["quote_status"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid QuoteStatus: {data['quote_status']!r}") from exc

        try:
            volume_type = (
                VolumeType(data["volume_type"])
                if isinstance(data["volume_type"], str)
                else data["volume_type"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid VolumeType: {data['volume_type']!r}") from exc

        return cls(
            asset_class=asset_class,
            venue=data["venue"],
            symbol=data["symbol"],
            timeframe=timeframe,
            timestamp_utc=data["timestamp_utc"],
            observed_at_utc=data["observed_at_utc"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            quote_status=quote_status,
            bid=data["bid"],
            ask=data["ask"],
            volume_type=volume_type,
            volume=data["volume"],
            data_source=data["data_source"],
            schema_version=data["schema_version"],
            row_hash=data["row_hash"],
        )


@dataclass(frozen=True)
class EventNewsItem:
    """Canonical economic event and news item data contract.

    Enforces strict enums, revision tracking (`first_observed_at` vs `updated_at`),
    separation of `raw_content_hash` and `record_hash`, and rejection of NaN/Infinity/bool.
    """

    event_id: str
    source: str
    source_reliability: float
    original_published_at: int
    first_observed_at: int
    updated_at: int
    affected_assets: tuple[str, ...]
    event_type: EventType
    expected_value: float | None
    actual_value: float | None
    surprise_value: float | None
    raw_content_hash: str
    sentiment_score: float = 0.0
    revision_status: RevisionStatus = RevisionStatus.INITIAL
    schema_version: str = SCHEMA_VERSION_V2
    record_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise TypeError(
                "event_type must be an instance of EventType enum "
                f"(no silent enum conversion), got {type(self.event_type).__name__}"
            )
        if not isinstance(self.revision_status, RevisionStatus):
            raise TypeError(
                "revision_status must be an instance of RevisionStatus enum "
                f"(no silent enum conversion), got {type(self.revision_status).__name__}"
            )

        for field_name in ("event_id", "source", "schema_version"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"EventNewsItem.{field_name} must be a non-empty string, got {val!r}"
                )

        if self.schema_version != SCHEMA_VERSION_V2:
            raise ValueError(
                f"Unsupported schema_version: expected {SCHEMA_VERSION_V2!r}, "
                f"got {self.schema_version!r}"
            )

        if (
            not isinstance(self.raw_content_hash, str)
            or len(self.raw_content_hash) != 64
            or not all(c in "0123456789abcdef" for c in self.raw_content_hash)
        ):
            raise ValueError(
                "EventNewsItem.raw_content_hash must be a 64-char lowercase hex string, "
                f"got {self.raw_content_hash!r}"
            )

        for field_name in ("original_published_at", "first_observed_at", "updated_at"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(
                    f"EventNewsItem.{field_name} must be an integer (ms UTC), "
                    f"got {type(val).__name__}"
                )
            if val < 0:
                raise ValueError(f"EventNewsItem.{field_name} cannot be negative, got {val}")

        if self.first_observed_at < self.original_published_at:
            raise ValueError(
                f"EventNewsItem.first_observed_at ({self.first_observed_at}) cannot be "
                f"earlier than original_published_at ({self.original_published_at})"
            )
        if self.updated_at < self.first_observed_at:
            raise ValueError(
                f"EventNewsItem.updated_at ({self.updated_at}) cannot be earlier than "
                f"first_observed_at ({self.first_observed_at})"
            )

        if not isinstance(self.affected_assets, tuple):
            raise TypeError(
                "EventNewsItem.affected_assets must be a tuple of unique strings "
                f"(rejecting list/set coercion), got {type(self.affected_assets).__name__}"
            )
        if not self.affected_assets:
            raise ValueError("EventNewsItem.affected_assets must be a non-empty tuple")

        seen = set()
        for item in self.affected_assets:
            if isinstance(item, bool) or not isinstance(item, str) or not item.strip():
                raise ValueError(
                    "EventNewsItem.affected_assets elements must be non-empty strings, "
                    f"got {item!r}"
                )
            if item in seen:
                raise ValueError(
                    f"EventNewsItem.affected_assets elements must be unique, duplicate: {item!r}"
                )
            seen.add(item)

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
                f"EventNewsItem.source_reliability must be finite and in [0.0, 1.0], got {f_rel}"
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
                f"EventNewsItem.sentiment_score must be finite and in [-1.0, 1.0], got {f_sent}"
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

        if self.record_hash:
            if (
                not isinstance(self.record_hash, str)
                or len(self.record_hash) != 64
                or not all(c in "0123456789abcdef" for c in self.record_hash)
            ):
                raise ValueError(
                    "EventNewsItem.record_hash must be a 64-char lowercase hex string, "
                    f"got {self.record_hash!r}"
                )
            computed = compute_event_news_hash(self)
            if self.record_hash != computed:
                raise RuntimeError(
                    f"EventNewsItem hash mismatch: computed {computed} "
                    f"!= provided {self.record_hash}"
                )
        else:
            computed = compute_event_news_hash(self)
            object.__setattr__(self, "record_hash", computed)

    def to_dict(self) -> dict[str, Any]:
        """Serialize EventNewsItem to dictionary with stable enum string values."""
        return {
            "event_id": self.event_id,
            "source": self.source,
            "source_reliability": self.source_reliability,
            "original_published_at": self.original_published_at,
            "first_observed_at": self.first_observed_at,
            "updated_at": self.updated_at,
            "affected_assets": list(self.affected_assets),
            "event_type": self.event_type.value,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "surprise_value": self.surprise_value,
            "raw_content_hash": self.raw_content_hash,
            "sentiment_score": self.sentiment_score,
            "revision_status": self.revision_status.value,
            "schema_version": self.schema_version,
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], verify_hash: bool = True) -> "EventNewsItem":
        """Reconstruct EventNewsItem from dict, enforcing boundaries and tamper check."""
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        expected_keys = {
            "event_id",
            "source",
            "source_reliability",
            "original_published_at",
            "first_observed_at",
            "updated_at",
            "affected_assets",
            "event_type",
            "expected_value",
            "actual_value",
            "surprise_value",
            "raw_content_hash",
            "sentiment_score",
            "revision_status",
            "schema_version",
            "record_hash",
        }
        actual_keys = set(data.keys())
        unknown = actual_keys - expected_keys
        if unknown:
            raise ValueError(f"Unknown fields rejected during deserialization: {sorted(unknown)}")
        missing = expected_keys - actual_keys
        if missing:
            raise ValueError(f"Missing fields rejected during deserialization: {sorted(missing)}")

        if verify_hash:
            record_hash = data.get("record_hash")
            if not isinstance(record_hash, str) or len(record_hash) != 64:
                raise ValueError(
                    "Tamper rejection: serialized EventNewsItem missing valid 64-char record_hash"
                )

        try:
            event_type = (
                EventType(data["event_type"])
                if isinstance(data["event_type"], str)
                else data["event_type"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid EventType: {data['event_type']!r}") from exc

        try:
            revision_status = (
                RevisionStatus(data["revision_status"])
                if isinstance(data["revision_status"], str)
                else data["revision_status"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid RevisionStatus: {data['revision_status']!r}") from exc

        affected_assets = data["affected_assets"]
        if isinstance(affected_assets, list):
            affected_assets = tuple(affected_assets)

        return cls(
            event_id=data["event_id"],
            source=data["source"],
            source_reliability=data["source_reliability"],
            original_published_at=data["original_published_at"],
            first_observed_at=data["first_observed_at"],
            updated_at=data["updated_at"],
            affected_assets=affected_assets,
            event_type=event_type,
            expected_value=data["expected_value"],
            actual_value=data["actual_value"],
            surprise_value=data["surprise_value"],
            raw_content_hash=data["raw_content_hash"],
            sentiment_score=data["sentiment_score"],
            revision_status=revision_status,
            schema_version=data["schema_version"],
            record_hash=data["record_hash"],
        )


@dataclass(frozen=True)
class FundingRate:
    """Canonical point-in-time funding rate contract for perpetual swaps.

    Enforces finite rates, matching UTC timestamps for validity, and SHA-256 fingerprinting.
    """

    asset_class: AssetClass
    venue: str
    symbol: str
    timestamp_utc: int
    observed_at_utc: int
    rate: float
    data_source: str
    schema_version: str = SCHEMA_VERSION_V2
    row_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.asset_class, AssetClass):
            raise TypeError(
                "asset_class must be an instance of AssetClass enum "
                f"(no silent enum conversion), got {type(self.asset_class).__name__}"
            )

        for field_name in ("venue", "symbol", "data_source", "schema_version"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"FundingRate.{field_name} must be a non-empty string, got {val!r}"
                )

        if self.schema_version != SCHEMA_VERSION_V2:
            raise ValueError(
                f"Unsupported schema_version: expected {SCHEMA_VERSION_V2!r}, "
                f"got {self.schema_version!r}"
            )

        for field_name in ("timestamp_utc", "observed_at_utc"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(
                    f"FundingRate.{field_name} must be an integer (ms UTC), "
                    f"got {type(val).__name__}"
                )
            if val < 0:
                raise ValueError(f"FundingRate.{field_name} cannot be negative, got {val}")

        if self.observed_at_utc < self.timestamp_utc:
            raise ValueError(
                f"FundingRate.observed_at_utc ({self.observed_at_utc}) cannot be "
                f"earlier than timestamp_utc ({self.timestamp_utc})"
            )

        if isinstance(self.rate, bool) or not isinstance(self.rate, (int, float)):
            raise TypeError(
                f"FundingRate.rate must be float or int, got {type(self.rate).__name__}"
            )
        f_rate = float(self.rate)
        if not math.isfinite(f_rate):
            raise ValueError("FundingRate.rate must be finite (rejecting NaN/Infinity)")
        object.__setattr__(self, "rate", f_rate)

        if self.row_hash:
            if (
                not isinstance(self.row_hash, str)
                or len(self.row_hash) != 64
                or not all(c in "0123456789abcdef" for c in self.row_hash)
            ):
                raise ValueError(
                    "FundingRate.row_hash must be a 64-character lowercase hex string, "
                    f"got {self.row_hash!r}"
                )
            computed = compute_funding_rate_hash(self)
            if self.row_hash != computed:
                raise RuntimeError(
                    f"FundingRate hash mismatch: computed {computed} != provided {self.row_hash}"
                )
        else:
            computed = compute_funding_rate_hash(self)
            object.__setattr__(self, "row_hash", computed)

    def to_dict(self) -> dict[str, Any]:
        """Serialize FundingRate to dictionary."""
        return {
            "asset_class": self.asset_class.value,
            "venue": self.venue,
            "symbol": self.symbol,
            "timestamp_utc": self.timestamp_utc,
            "observed_at_utc": self.observed_at_utc,
            "rate": self.rate,
            "data_source": self.data_source,
            "schema_version": self.schema_version,
            "row_hash": self.row_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], verify_hash: bool = True) -> "FundingRate":
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        expected_keys = {
            "asset_class",
            "venue",
            "symbol",
            "timestamp_utc",
            "observed_at_utc",
            "rate",
            "data_source",
            "schema_version",
            "row_hash",
        }
        actual_keys = set(data.keys())
        unknown = actual_keys - expected_keys
        if unknown:
            raise ValueError(f"Unknown fields rejected during deserialization: {sorted(unknown)}")
        missing = expected_keys - actual_keys
        if missing:
            raise ValueError(f"Missing fields rejected during deserialization: {sorted(missing)}")

        if verify_hash:
            row_hash = data.get("row_hash")
            if not isinstance(row_hash, str) or len(row_hash) != 64:
                raise ValueError(
                    "Tamper rejection: serialized FundingRate missing valid 64-char row_hash"
                )

        try:
            asset_class = (
                AssetClass(data["asset_class"])
                if isinstance(data["asset_class"], str)
                else data["asset_class"]
            )
        except ValueError as exc:
            raise ValueError(f"Invalid AssetClass: {data['asset_class']!r}") from exc

        return cls(
            asset_class=asset_class,
            venue=data["venue"],
            symbol=data["symbol"],
            timestamp_utc=data["timestamp_utc"],
            observed_at_utc=data["observed_at_utc"],
            rate=data["rate"],
            data_source=data["data_source"],
            schema_version=data["schema_version"],
            row_hash=data["row_hash"],
        )


def validate_ingestion_time(
    contract: MarketBar | EventNewsItem | FundingRate,
    current_time_ms: int,
    max_clock_skew_ms: int = DEFAULT_MAX_SKEW_MS,
) -> None:
    """Validate data receipt timestamp is deterministic and within allowed clock skew.

    For `MarketBar`, checks `observed_at_utc <= current_time_ms + max_clock_skew_ms`.
    For `EventNewsItem`, checks `first_observed_at <= current_time_ms + max_clock_skew_ms`
    and `updated_at <= current_time_ms + max_clock_skew_ms`.

    Raises RuntimeError on future timestamp violations.
    """
    if (
        isinstance(current_time_ms, bool)
        or not isinstance(current_time_ms, int)
        or current_time_ms < 0
    ):
        raise TypeError("current_time_ms must be a non-negative integer")
    if (
        isinstance(max_clock_skew_ms, bool)
        or not isinstance(max_clock_skew_ms, int)
        or max_clock_skew_ms < 0
    ):
        raise TypeError("max_clock_skew_ms must be a non-negative integer")

    max_allowed = current_time_ms + max_clock_skew_ms

    if isinstance(contract, MarketBar):
        if contract.observed_at_utc > max_allowed:
            raise RuntimeError(
                "Ingestion time validation failed for MarketBar: observed_at_utc "
                f"({contract.observed_at_utc}) exceeds current_time_ms ({current_time_ms}) "
                f"plus max_clock_skew_ms ({max_clock_skew_ms})"
            )
    elif isinstance(contract, EventNewsItem):
        if contract.first_observed_at > max_allowed:
            raise RuntimeError(
                "Ingestion time validation failed for EventNewsItem: first_observed_at "
                f"({contract.first_observed_at}) exceeds current_time_ms ({current_time_ms}) "
                f"plus max_clock_skew_ms ({max_clock_skew_ms})"
            )
        if contract.updated_at > max_allowed:
            raise RuntimeError(
                "Ingestion time validation failed for EventNewsItem: updated_at "
                f"({contract.updated_at}) exceeds current_time_ms ({current_time_ms}) "
                f"plus max_clock_skew_ms ({max_clock_skew_ms})"
            )
    elif isinstance(contract, FundingRate):
        if contract.observed_at_utc > max_allowed:
            raise RuntimeError(
                "Ingestion time validation failed for FundingRate: observed_at_utc "
                f"({contract.observed_at_utc}) exceeds current_time_ms ({current_time_ms}) "
                f"plus max_clock_skew_ms ({max_clock_skew_ms})"
            )
    else:
        raise TypeError(
            f"Expected MarketBar, EventNewsItem, or FundingRate, got {type(contract).__name__}"
        )


def to_dict(contract: MarketBar | EventNewsItem | FundingRate) -> dict[str, Any]:
    """Serialize a MarketBar, EventNewsItem, or FundingRate contract to a dict."""
    if hasattr(contract, "to_dict") and callable(contract.to_dict):
        return contract.to_dict()
    raise TypeError(
        f"Expected MarketBar, EventNewsItem, or FundingRate, got {type(contract).__name__}"
    )


def from_dict(
    cls: type[MarketBar] | type[EventNewsItem] | type[FundingRate],
    data: dict[str, Any],
    verify_hash: bool = True,
) -> MarketBar | EventNewsItem | FundingRate:
    """Reconstruct a MarketBar, EventNewsItem, or FundingRate contract from a dictionary."""
    if hasattr(cls, "from_dict") and callable(cls.from_dict):
        return cls.from_dict(data, verify_hash=verify_hash)
    raise TypeError(f"Expected class MarketBar, EventNewsItem, or FundingRate, got {cls!r}")
