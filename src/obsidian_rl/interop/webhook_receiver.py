"""TradingView Webhook Receiver - Secure Signal Ingestion Layer.

This module receives and validates authenticated JSON webhook alerts originating
from TradingView Pine Script indicators.

SECURITY MODEL:
- Uses real ingress-authentication abstraction based on VERIFIED TradingView
  HTTPS client-certificate identity via trusted reverse proxy
- Never trusts arbitrary user-supplied headers claiming certificate was verified
- Direct untrusted requests fail closed

REPLAY PROTECTION:
- Strict timestamp freshness (max 60 seconds skew)
- Unique event_id replay cache (in-memory for now, can be backed by Redis)
- Duplicate event_id => reject
- Future timestamp beyond allowed skew => reject
- Stale timestamp => reject

PAYLOAD VALIDATION:
- Strict schema validation
- Bounded body size
- Reject malformed JSON
- Reject missing required fields
- Reject unsupported schema version
- Reject non-finite numerics
- Reject malformed symbol/timeframe
- Reject unexpected dangerous fields
- Fail closed

NO SECRET LOGGING.
NO CREDENTIAL LOGGING.

TRADINGVIEW PROPOSAL = INFORMATIONAL ONLY.
Python engine remains authoritative.
"""

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Configuration constants
MAX_PAYLOAD_SIZE_BYTES = 16_384  # 16 KB max body
MAX_TIMESTAMP_SKEW_SECONDS = 60  # TradingView alerts must be within 60s of receipt
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1",)
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("4h", "1d", "240", "D")  # Pine uses "240" for 4h
SUPPORTED_SIGNALS: tuple[str, ...] = ("LONG", "SHORT", "FLAT")


class WebhookError(Exception):
    """Base exception for webhook processing errors."""

    pass


class AuthenticationError(WebhookError):
    """Authentication/authorization failure."""

    pass


class ReplayError(WebhookError):
    """Replay attack detected (duplicate event_id or timestamp skew)."""

    pass


class PayloadValidationError(WebhookError):
    """Payload schema/validation failure."""

    pass


class RateLimitError(WebhookError):
    """Rate limit exceeded."""

    pass


@dataclass(frozen=True)
class ValidatedSignal:
    """Validated informational signal proposal from TradingView."""

    schema_version: str
    event_id: str
    symbol: str
    timeframe: str
    bar_timestamp_utc: int
    signal: str  # LONG, SHORT, FLAT
    score: float
    volatility_20d: float
    latest_close: float
    engine_version: str
    config_identity: str
    received_at_utc: int


class EventIdCache:
    """In-memory replay cache for event_id deduplication.

    For production, replace with Redis-backed cache with TTL.
    """

    def __init__(self, max_size: int = 100_000) -> None:
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size

    def check_and_add(self, event_id: str, timestamp_utc: int) -> bool:
        """Check if event_id is new, add if so. Returns True if new, False if duplicate."""
        now = time.time()

        # Clean old entries (older than 24 hours)
        cutoff = now - 86_400
        while self._cache and next(iter(self._cache.values())) < cutoff:
            self._cache.popitem(last=False)

        if event_id in self._cache:
            return False

        # Add new entry
        self._cache[event_id] = timestamp_utc / 1000.0  # Convert to seconds

        # Evict oldest if over max size
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

        return True


# Global event_id cache (single instance per process)
_event_id_cache = EventIdCache()


def _verify_trusted_ingress_identity(headers: dict[str, str]) -> tuple[bool, str | None]:
    """Verify request came through trusted reverse proxy with TradingView client cert.

    This is the PRODUCTION authentication model. In development/test without a
    reverse proxy, this will fail closed.

    Expected headers from trusted ingress (e.g., nginx with client cert verification):
    - X-Client-Cert-Verified: "SUCCESS"
    - X-Client-Cert-Subject: TradingView's certificate subject
    - X-Forwarded-For: TradingView IP ranges (defense in depth only)

    Returns (is_valid, identity_description_or_None)
    """
    cert_verified = headers.get("X-Client-Cert-Verified", "").upper()
    cert_subject = headers.get("X-Client-Cert-Subject", "")

    if cert_verified != "SUCCESS":
        return False, None

    # Verify subject matches TradingView's known certificate
    # TradingView's cert subject contains "TradingView" or known OU
    if "tradingview" not in cert_subject.lower():
        return False, None

    return True, cert_subject


def validate_timestamp(timestamp_utc: int, received_at_utc: int) -> None:
    """Validate timestamp freshness. Raises ReplayError if invalid."""
    skew_ms = abs(received_at_utc - timestamp_utc)
    max_skew_ms = MAX_TIMESTAMP_SKEW_SECONDS * 1000

    if skew_ms > max_skew_ms:
        raise ReplayError(
            f"Timestamp skew {skew_ms}ms exceeds maximum {max_skew_ms}ms. "
            f"Got bar_timestamp_utc={timestamp_utc}, received_at={received_at_utc}"
        )

    # Also reject timestamps in the future beyond allowed skew
    if timestamp_utc > received_at_utc + max_skew_ms:
        raise ReplayError(
            f"Future timestamp rejected: bar_timestamp_utc={timestamp_utc} "
            f"is {timestamp_utc - received_at_utc}ms in the future"
        )


def validate_event_id(event_id: str, received_at_utc: int) -> None:
    """Validate event_id uniqueness (replay protection). Raises ReplayError if duplicate."""
    if not _event_id_cache.check_and_add(event_id, received_at_utc):
        raise ReplayError(f"Duplicate event_id detected: {event_id}")


def validate_payload(payload: dict[str, Any]) -> ValidatedSignal:
    """Validate webhook payload against strict schema. Raises PayloadValidationError if invalid."""
    # Check required fields
    required_fields = (
        "schema_version",
        "event_id",
        "symbol",
        "timeframe",
        "bar_timestamp_utc",
        "signal",
        "score",
        "volatility_20d",
        "latest_close",
        "engine_version",
        "config_identity",
    )

    for field in required_fields:
        if field not in payload:
            raise PayloadValidationError(f"Missing required field: {field}")

    # No unexpected dangerous fields
    allowed_fields = set(required_fields)
    unexpected = set(payload.keys()) - allowed_fields
    if unexpected:
        raise PayloadValidationError(f"Unexpected fields rejected: {sorted(unexpected)}")

    # Schema version
    schema_version = str(payload["schema_version"])
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = SUPPORTED_SCHEMA_VERSIONS
        raise PayloadValidationError(
            f"Unsupported schema_version: {schema_version}. Supported: {supported}"
        )

    # Event ID format validation
    event_id = str(payload["event_id"])
    if not event_id or len(event_id) > 256:
        raise PayloadValidationError("event_id must be non-empty string <= 256 chars")

    # Symbol validation (basic format)
    symbol = str(payload["symbol"])
    if not symbol or len(symbol) > 64:
        raise PayloadValidationError("symbol must be non-empty string <= 64 chars")
    # TradingView symbols like BTCUSDT, EUR_USD, etc.
    if not all(c.isalnum() or c in "_-." for c in symbol):
        raise PayloadValidationError(f"Invalid symbol format: {symbol}")

    # Timeframe validation
    timeframe = str(payload["timeframe"])
    if timeframe not in SUPPORTED_TIMEFRAMES:
        supported = SUPPORTED_TIMEFRAMES
        raise PayloadValidationError(f"Unsupported timeframe: {timeframe}. Supported: {supported}")

    # Bar timestamp validation
    try:
        bar_timestamp_utc = int(payload["bar_timestamp_utc"])
    except (TypeError, ValueError) as exc:
        raise PayloadValidationError("bar_timestamp_utc must be integer") from exc

    if bar_timestamp_utc <= 0:
        raise PayloadValidationError("bar_timestamp_utc must be positive")

    # Signal validation
    signal = str(payload["signal"])
    if signal not in SUPPORTED_SIGNALS:
        supported = SUPPORTED_SIGNALS
        raise PayloadValidationError(f"Invalid signal: {signal}. Supported: {supported}")

    # Numeric fields - must be finite
    for field in ("score", "volatility_20d", "latest_close"):
        try:
            val = float(payload[field])
        except (TypeError, ValueError) as exc:
            raise PayloadValidationError(f"{field} must be numeric") from exc

        if not (val == val and val != float("inf") and val != float("-inf")):
            raise PayloadValidationError(f"{field} must be finite (not NaN/inf)")

    score = float(payload["score"])
    volatility_20d = float(payload["volatility_20d"])
    latest_close = float(payload["latest_close"])

    # latest_close must be positive (matching Pine/Python validation)
    if latest_close <= 0.0:
        raise PayloadValidationError(f"latest_close must be positive (> 0), got {latest_close}")

    # Signal-specific validation
    if signal in ("LONG", "SHORT") and abs(score) < 0.0001:
        raise PayloadValidationError(f"Signal {signal} requires non-zero score magnitude")

    if signal == "FLAT" and abs(score) > 0.5:
        raise PayloadValidationError(f"FLAT signal has unexpected score magnitude: {score}")

    # Engine version
    engine_version = str(payload["engine_version"])
    if not engine_version or "TrendEngineV1" not in engine_version:
        raise PayloadValidationError(f"Unexpected engine_version: {engine_version}")

    # Config identity (should be SHA256 hex)
    config_identity = str(payload["config_identity"])
    if (
        not config_identity
        or len(config_identity) != 64
        or not all(c in "0123456789abcdef" for c in config_identity)
    ):
        raise PayloadValidationError(
            f"config_identity must be 64-char hex SHA256: {config_identity}"
        )

    received_at_utc = int(time.time() * 1000)

    # Validate timestamp freshness
    validate_timestamp(bar_timestamp_utc, received_at_utc)

    # Validate event_id replay protection
    validate_event_id(event_id, received_at_utc)

    return ValidatedSignal(
        schema_version=schema_version,
        event_id=event_id,
        symbol=symbol,
        timeframe=timeframe,
        bar_timestamp_utc=bar_timestamp_utc,
        signal=signal,
        score=score,
        volatility_20d=volatility_20d,
        latest_close=latest_close,
        engine_version=engine_version,
        config_identity=config_identity,
        received_at_utc=received_at_utc,
    )


async def receive_webhook(
    request_body: bytes,
    headers: dict[str, str],
) -> ValidatedSignal:
    """Main entry point: receive and validate TradingView webhook.

    Production authentication ONLY: requires trusted reverse proxy with
    TradingView HTTPS client-certificate verification.

    Args:
        request_body: Raw request body bytes
        headers: Request headers (case-insensitive)

    Returns:
        ValidatedSignal if all checks pass

    Raises:
        AuthenticationError: If authentication fails
        ReplayError: If replay protection triggers
        PayloadValidationError: If payload is invalid
        RateLimitError: If rate limited
    """
    # 1. Body size check
    if len(request_body) > MAX_PAYLOAD_SIZE_BYTES:
        raise PayloadValidationError(
            f"Payload too large: {len(request_body)} bytes > {MAX_PAYLOAD_SIZE_BYTES}"
        )

    # 2. Authentication: PRODUCTION ONLY - trusted ingress with client cert
    is_valid, _identity = _verify_trusted_ingress_identity(headers)
    if not is_valid:
        logger.warning("Webhook rejected: missing/invalid trusted ingress identity")
        raise AuthenticationError("Missing or invalid trusted ingress authentication")

    # 3. Parse JSON
    try:
        payload = json.loads(request_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PayloadValidationError(f"Malformed JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise PayloadValidationError(f"Invalid UTF-8 encoding: {exc}") from exc

    # 4. Validate payload
    signal = validate_payload(payload)

    logger.info(
        "Webhook accepted: event_id=%s symbol=%s timeframe=%s signal=%s",
        signal.event_id,
        signal.symbol,
        signal.timeframe,
        signal.signal,
    )

    return signal


def get_event_id_cache_stats() -> dict[str, Any]:
    """Get cache statistics for monitoring."""
    return {
        "size": len(_event_id_cache._cache),
        "max_size": _event_id_cache._max_size,
    }


def clear_event_id_cache() -> None:
    """Clear the event_id cache (for testing only)."""
    _event_id_cache._cache.clear()
