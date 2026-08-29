"""Secure TradingView webhook receiver with strict validation and replay protection.

This module implements the Python-side ingestion for TradingView alerts.
Key invariants:
- FAIL-CLOSED: Any validation error rejects the payload with 400/401
- INFORMATIONAL ONLY: Returns parsed signal proposal; NEVER executes orders or mutates portfolio state
- REPLAY PROTECTION: event_id deduplication + timestamp freshness check
- ZERO EXECUTION: No imports of exchange clients, PortfolioEngine, or PaperTrader
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError as PydanticValidationError


class SignalDirection(Enum):
    """Valid signal directions from TradingView."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class ValidationError(Exception):
    """Raised when payload validation fails."""

    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        self.code = code
        super().__init__(message)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, message: str, code: str = "AUTHENTICATION_FAILED"):
        self.code = code
        super().__init__(message)


class ReplayDetected(Exception):
    """Raised when a duplicate event_id is detected."""

    def __init__(self, message: str, code: str = "REPLAY_DETECTED"):
        self.code = code
        super().__init__(message)


# Configuration constants
MAX_TIMESTAMP_SKEW_SECONDS = 60
MAX_EVENT_ID_LENGTH = 256
MAX_SYMBOL_LENGTH = 64
MAX_PAYLOAD_SIZE_BYTES = 16 * 1024  # 16KB

# Regex patterns for validation
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
TIMEFRAME_PATTERN = re.compile(r"^(4h|1d|240|D)$")
CONFIG_IDENTITY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ENGINE_VERSION_PREFIX = "TrendEngineV1"


# In-memory replay cache (production would use Redis with TTL)
_replay_cache: set[str] = set()


class TradingViewPayload(BaseModel):
    """Strict Pydantic model for TradingView webhook payload.

    All fields required. No optional fields. Extra fields forbidden.
    """

    schema_version: str = Field(..., description="Must be '1'")
    event_id: str = Field(..., min_length=1, max_length=MAX_EVENT_ID_LENGTH)
    symbol: str = Field(..., min_length=1, max_length=MAX_SYMBOL_LENGTH)
    timeframe: str = Field(..., pattern="^(4h|1d|240|D)$")
    bar_timestamp_utc: int = Field(..., gt=0)
    signal: SignalDirection
    score: float
    volatility_20d: float
    latest_close: float
    engine_version: str
    config_identity: str = Field(..., pattern="^[a-f0-9]{64}$")

    model_config = {
        "extra": "forbid",  # Reject any unexpected fields
        "use_enum_values": True,
    }

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != "1":
            raise ValidationError(f"schema_version must be '1', got '{v}'", "INVALID_SCHEMA_VERSION")
        return v

    @field_validator("engine_version")
    @classmethod
    def validate_engine_version(cls, v: str) -> str:
        if ENGINE_VERSION_PREFIX not in v:
            raise ValidationError(
                f"engine_version must contain '{ENGINE_VERSION_PREFIX}', got '{v}'",
                "INVALID_ENGINE_VERSION",
            )
        return v

    @field_validator("score", "volatility_20d", "latest_close")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        if not isinstance(v, (int, float)) or not (v == v and abs(v) != float("inf")):
            raise ValidationError(f"value must be finite, got {v}", "NON_FINITE_VALUE")
        return float(v)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        if not v or len(v) > MAX_EVENT_ID_LENGTH:
            raise ValidationError(
                f"event_id must be non-empty and <= {MAX_EVENT_ID_LENGTH} chars",
                "INVALID_EVENT_ID",
            )
        return v

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        if not SYMBOL_PATTERN.match(v):
            raise ValidationError(
                f"symbol must match pattern [A-Za-z0-9_.-] and be <= {MAX_SYMBOL_LENGTH} chars",
                "INVALID_SYMBOL",
            )
        return v

    @field_validator("config_identity")
    @classmethod
    def validate_config_identity(cls, v: str) -> str:
        if not CONFIG_IDENTITY_PATTERN.match(v):
            raise ValidationError(
                "config_identity must be 64-char lowercase hex SHA256",
                "INVALID_CONFIG_IDENTITY",
            )
        return v

    @model_validator(mode="after")
    def validate_signal_specifics(self) -> "TradingViewPayload":
        """Validate signal-specific constraints."""
        # use_enum_values=True converts enums to their string values
        signal_str = self.signal
        if signal_str in ("LONG", "SHORT"):
            if abs(self.score) < 1e-10:
                raise ValidationError(
                    f"LONG/SHORT signals require non-zero score, got {self.score}",
                    "INVALID_SCORE_FOR_DIRECTION",
                )
            if self.volatility_20d <= 0:
                raise ValidationError(
                    f"LONG/SHORT signals require positive volatility, got {self.volatility_20d}",
                    "INVALID_VOLATILITY",
                )
        elif signal_str == "FLAT":
            if abs(self.score) > 1e-10:
                raise ValidationError(
                    f"FLAT signal requires near-zero score, got {self.score}",
                    "INVALID_SCORE_FOR_FLAT",
                )
        return self


@dataclass(frozen=True)
class ValidatedSignal:
    """Parsed and validated signal proposal from TradingView.

    This is an INFORMATIONAL object only. It does NOT execute any trading action.
    """

    event_id: str
    symbol: str
    timeframe: str
    bar_timestamp_utc: int
    signal: SignalDirection
    score: float
    volatility_20d: float
    latest_close: float
    engine_version: str
    config_identity: str
    received_at_utc: int


def clear_replay_cache() -> None:
    """Clear the in-memory replay cache (for testing)."""
    _replay_cache.clear()


def _check_replay(event_id: str) -> bool:
    """Check if event_id is a replay. Returns True if duplicate."""
    if event_id in _replay_cache:
        return True
    _replay_cache.add(event_id)
    return False


def _validate_timestamp(bar_timestamp_utc: int, received_at_utc: Optional[int] = None) -> None:
    """Validate timestamp freshness (within skew bounds)."""
    now = received_at_utc or int(time.time() * 1000)
    skew = abs(now - bar_timestamp_utc)

    if skew > MAX_TIMESTAMP_SKEW_SECONDS * 1000:
        raise ValidationError(
            f"Timestamp skew {skew}ms exceeds limit {MAX_TIMESTAMP_SKEW_SECONDS}s",
            "TIMESTAMP_STALE" if bar_timestamp_utc < now else "TIMESTAMP_FUTURE",
        )


def _verify_trusted_ingress(headers: dict[str, str]) -> None:
    """Verify request comes through trusted reverse proxy with mTLS.

    Production requirement: Reverse proxy must inject verified client certificate headers.
    """
    cert_verified = headers.get("X-Client-Cert-Verified")
    cert_subject = headers.get("X-Client-Cert-Subject")

    if cert_verified != "SUCCESS":
        raise AuthenticationError(
            "Missing or invalid X-Client-Cert-Verified header (must be 'SUCCESS')",
            "MISSING_CERT_VERIFIED",
        )

    if not cert_subject or not cert_subject.startswith("CN="):
        raise AuthenticationError(
            "Missing or invalid X-Client-Cert-Subject header",
            "INVALID_CERT_SUBJECT",
        )

    # Additional: verify subject contains expected TradingView CN
    if "TradingView" not in cert_subject and "TV-" not in cert_subject:
        raise AuthenticationError(
            f"Client certificate subject does not appear to be TradingView: {cert_subject}",
            "UNTRUSTED_CERT_SUBJECT",
        )


def receive_tradingview_alert(
    payload: dict,
    headers: dict[str, str],
    received_at_utc: Optional[int] = None,
) -> ValidatedSignal:
    """Main entry point for receiving TradingView webhook alerts.

    Args:
        payload: Parsed JSON body from TradingView webhook
        headers: HTTP headers (must include X-Client-Cert-Verified and X-Client-Cert-Subject)
        received_at_utc: Optional receipt timestamp for testing (ms since epoch)

    Returns:
        ValidatedSignal: Parsed, validated, replay-protected signal proposal

    Raises:
        ValidationError: Payload schema/format validation failed (400)
        AuthenticationError: Trusted ingress verification failed (401)
        ReplayDetected: Duplicate event_id (409)
    """
    # 1. Verify trusted ingress authentication (fail-closed)
    _verify_trusted_ingress(headers)

    # 2. Strict payload validation via Pydantic (fail-closed, extra fields forbidden)
    try:
        tv_payload = TradingViewPayload(**payload)
    except PydanticValidationError as e:
        # Extract first error detail for fail-closed reporting
        errors = e.errors()
        if errors:
            first_error = errors[0]
            loc = ".".join(str(x) for x in first_error["loc"])
            msg = first_error["msg"]
            # Map Pydantic error types to our error codes
            if "extra_forbidden" in first_error["type"]:
                raise ValidationError(f"Extra field '{loc}' not allowed", "PAYLOAD_VALIDATION_FAILED")
            elif "missing" in first_error["type"]:
                raise ValidationError(f"Missing required field: {loc}", "PAYLOAD_VALIDATION_FAILED")
            elif "string_too_short" in first_error["type"]:
                raise ValidationError(f"{loc}: {msg}", "INVALID_EVENT_ID")
            elif "greater_than" in first_error["type"]:
                raise ValidationError(f"{loc}: {msg}", "PAYLOAD_VALIDATION_FAILED")
            elif "string_pattern_mismatch" in first_error["type"]:
                if loc == "symbol":
                    raise ValidationError(f"symbol must match pattern [A-Za-z0-9_.-] and be <= {MAX_SYMBOL_LENGTH} chars", "INVALID_SYMBOL")
                elif loc == "timeframe":
                    raise ValidationError(f"timeframe must be one of 4h, 1d, 240, D", "PAYLOAD_VALIDATION_FAILED")
                elif loc == "config_identity":
                    raise ValidationError(f"config_identity must be 64-char lowercase hex SHA256", "INVALID_CONFIG_IDENTITY")
                else:
                    raise ValidationError(f"{loc}: {msg}", "PAYLOAD_VALIDATION_FAILED")
            else:
                raise ValidationError(f"{loc}: {msg}", "PAYLOAD_VALIDATION_FAILED")
        else:
            raise ValidationError("Payload validation failed", "PAYLOAD_VALIDATION_FAILED")
    except ValidationError:
        raise

    # 3. Timestamp freshness check
    _validate_timestamp(tv_payload.bar_timestamp_utc, received_at_utc)

    # 4. Replay protection: event_id deduplication
    if _check_replay(tv_payload.event_id):
        raise ReplayDetected(
            f"Duplicate event_id detected: {tv_payload.event_id}",
            "DUPLICATE_EVENT_ID",
        )

    # 5. Construct validated signal proposal (informational only)
    received_at = received_at_utc or int(time.time() * 1000)

    # tv_payload.signal is a string due to use_enum_values=True; convert to enum
    signal_enum = SignalDirection(tv_payload.signal)

    return ValidatedSignal(
        event_id=tv_payload.event_id,
        symbol=tv_payload.symbol,
        timeframe=tv_payload.timeframe,
        bar_timestamp_utc=tv_payload.bar_timestamp_utc,
        signal=signal_enum,
        score=tv_payload.score,
        volatility_20d=tv_payload.volatility_20d,
        latest_close=tv_payload.latest_close,
        engine_version=tv_payload.engine_version,
        config_identity=tv_payload.config_identity,
        received_at_utc=received_at,
    )