"""Tests for TradingView Webhook Receiver - Phase 6 Signal Layer."""

import json
import time
from typing import Any

import pytest

from obsidian_rl.interop.webhook_receiver import (
    AuthenticationError,
    PayloadValidationError,
    RateLimitError,
    ReplayError,
    ValidatedSignal,
    WebhookError,
    _verify_trusted_ingress_identity,
    clear_event_id_cache,
    receive_webhook,
    validate_event_id,
    validate_payload,
    validate_timestamp,
)


def make_valid_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid webhook payload with optional overrides."""
    base = {
        "schema_version": "1",
        "event_id": f"test_{int(time.time() * 1000)}",
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "bar_timestamp_utc": int(time.time() * 1000) - 1_000,  # 1 second ago
        "signal": "LONG",
        "score": 1.0,
        "volatility_20d": 0.02,
        "latest_close": 50000.0,
        "engine_version": "TrendEngineV1",
        "config_identity": "a" * 64,
    }
    base.update(overrides)
    return base


class TestTrustedIngressIdentity:
    """Test trusted reverse proxy authentication."""

    def test_valid_ingress(self):
        headers = {
            "X-Client-Cert-Verified": "SUCCESS",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }
        valid, identity = _verify_trusted_ingress_identity(headers)
        assert valid is True
        assert identity == "CN=TradingView Alerting"

    def test_invalid_cert_verified(self):
        headers = {
            "X-Client-Cert-Verified": "FAILED",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }
        valid, identity = _verify_trusted_ingress_identity(headers)
        assert valid is False
        assert identity is None

    def test_missing_cert_verified(self):
        headers = {
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }
        valid, _identity = _verify_trusted_ingress_identity(headers)
        assert valid is False

    def test_wrong_subject(self):
        headers = {
            "X-Client-Cert-Verified": "SUCCESS",
            "X-Client-Cert-Subject": "CN=Evil Attacker",
        }
        valid, _identity = _verify_trusted_ingress_identity(headers)
        assert valid is False


class TestTimestampValidation:
    """Test timestamp freshness validation."""

    def test_valid_recent_timestamp(self):
        now = int(time.time() * 1000)
        # 30 seconds ago - valid
        validate_timestamp(now - 30_000, now)

    def test_valid_exact_now(self):
        now = int(time.time() * 1000)
        validate_timestamp(now, now)

    def test_valid_future_within_skew(self):
        now = int(time.time() * 1000)
        # 30 seconds in future - within 60s skew
        validate_timestamp(now + 30_000, now)

    def test_stale_timestamp_rejected(self):
        now = int(time.time() * 1000)
        # 2 minutes ago - exceeds 60s skew
        with pytest.raises(ReplayError, match="Timestamp skew"):
            validate_timestamp(now - 120_000, now)

    def test_excessive_future_rejected(self):
        now = int(time.time() * 1000)
        # 2 minutes in future - exceeds 60s skew
        # The first check (abs skew) catches this, so match that message
        with pytest.raises(ReplayError, match="Timestamp skew"):
            validate_timestamp(now + 120_000, now)

    def test_zero_timestamp_rejected(self):
        now = int(time.time() * 1000)
        with pytest.raises(ReplayError):
            validate_timestamp(0, now)


class TestEventIdReplayProtection:
    """Test event_id duplicate detection."""

    def setup_method(self):
        clear_event_id_cache()

    def test_first_event_accepted(self):
        now = int(time.time() * 1000)
        event_id = "unique_event_123"
        assert validate_event_id(event_id, now) is None  # No exception = accepted

    def test_duplicate_rejected(self):
        now = int(time.time() * 1000)
        event_id = "duplicate_event"
        validate_event_id(event_id, now)  # First time
        with pytest.raises(ReplayError, match="Duplicate event_id"):
            validate_event_id(event_id, now)  # Second time

    def test_cache_persistence_across_calls(self):
        now = int(time.time() * 1000)
        event_id = "persist_test"
        validate_event_id(event_id, now)
        # Cache should still have it
        with pytest.raises(ReplayError):
            validate_event_id(event_id, now)


class TestPayloadValidation:
    """Test strict payload schema validation."""

    def setup_method(self):
        clear_event_id_cache()

    def test_valid_payload_accepted(self):
        payload = make_valid_payload()
        signal = validate_payload(payload)
        assert isinstance(signal, ValidatedSignal)
        assert signal.signal == "LONG"
        assert signal.symbol == "BTCUSDT"

    def test_missing_required_field_rejected(self):
        payload = make_valid_payload()
        del payload["symbol"]
        with pytest.raises(PayloadValidationError, match="Missing required field: symbol"):
            validate_payload(payload)

    def test_unexpected_field_rejected(self):
        payload = make_valid_payload(dangerous_field="evil")
        with pytest.raises(PayloadValidationError, match="Unexpected fields rejected"):
            validate_payload(payload)

    def test_unsupported_schema_version_rejected(self):
        payload = make_valid_payload(schema_version="2")
        with pytest.raises(PayloadValidationError, match="Unsupported schema_version"):
            validate_payload(payload)

    def test_invalid_event_id_rejected(self):
        payload = make_valid_payload(event_id="")
        with pytest.raises(PayloadValidationError, match="event_id must be non-empty"):
            validate_payload(payload)

    def test_invalid_symbol_rejected(self):
        payload = make_valid_payload(symbol="INVALID@SYMBOL")
        with pytest.raises(PayloadValidationError, match="Invalid symbol format"):
            validate_payload(payload)

    def test_unsupported_timeframe_rejected(self):
        payload = make_valid_payload(timeframe="15m")
        with pytest.raises(PayloadValidationError, match="Unsupported timeframe"):
            validate_payload(payload)

    def test_non_finite_score_rejected(self):
        for bad_val in [float("nan"), float("inf"), float("-inf")]:
            payload = make_valid_payload(score=bad_val)
            with pytest.raises(PayloadValidationError, match="score must be finite"):
                validate_payload(payload)

    def test_non_finite_volatility_rejected(self):
        payload = make_valid_payload(volatility_20d=float("nan"))
        with pytest.raises(PayloadValidationError, match="volatility_20d must be finite"):
            validate_payload(payload)

    def test_non_finite_close_rejected(self):
        payload = make_valid_payload(latest_close=float("inf"))
        with pytest.raises(PayloadValidationError, match="latest_close must be finite"):
            validate_payload(payload)

    def test_zero_close_rejected(self):
        payload = make_valid_payload(latest_close=0.0)
        with pytest.raises(PayloadValidationError, match="latest_close must be positive"):
            validate_payload(payload)

    def test_negative_close_rejected(self):
        payload = make_valid_payload(latest_close=-100.0)
        with pytest.raises(PayloadValidationError, match="latest_close must be positive"):
            validate_payload(payload)

    def test_long_signal_requires_nonzero_score(self):
        payload = make_valid_payload(signal="LONG", score=0.0)
        with pytest.raises(PayloadValidationError, match="Signal LONG requires non-zero"):
            validate_payload(payload)

    def test_short_signal_requires_nonzero_score(self):
        payload = make_valid_payload(signal="SHORT", score=0.0)
        with pytest.raises(PayloadValidationError, match="Signal SHORT requires non-zero"):
            validate_payload(payload)

    def test_flat_signal_unexpected_magnitude_rejected(self):
        payload = make_valid_payload(signal="FLAT", score=1.0)
        with pytest.raises(PayloadValidationError, match="FLAT signal has unexpected"):
            validate_payload(payload)

    def test_invalid_engine_version_rejected(self):
        payload = make_valid_payload(engine_version="EvilEngineV99")
        with pytest.raises(PayloadValidationError, match="Unexpected engine_version"):
            validate_payload(payload)

    def test_invalid_config_identity_rejected(self):
        # Not 64 chars
        payload = make_valid_payload(config_identity="abc")
        with pytest.raises(PayloadValidationError, match="config_identity must be 64-char"):
            validate_payload(payload)

        # Not hex
        payload = make_valid_payload(config_identity="g" * 64)
        with pytest.raises(PayloadValidationError, match="config_identity must be 64-char"):
            validate_payload(payload)


class TestReceiveWebhookIntegration:
    """Integration tests for the main receive_webhook function."""

    def setup_method(self):
        clear_event_id_cache()

    @pytest.mark.asyncio
    async def test_valid_webhook_accepted_with_ingress_auth(self):
        payload = make_valid_payload()
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "X-Client-Cert-Verified": "SUCCESS",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }

        signal = await receive_webhook(body, headers)
        assert isinstance(signal, ValidatedSignal)
        assert signal.signal == "LONG"

    @pytest.mark.asyncio
    async def test_invalid_ingress_auth_rejected(self):
        payload = make_valid_payload()
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "X-Client-Cert-Verified": "FAILED",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }

        with pytest.raises(AuthenticationError, match="Missing or invalid trusted ingress"):
            await receive_webhook(body, headers)

    @pytest.mark.asyncio
    async def test_missing_ingress_headers_rejected(self):
        payload = make_valid_payload()
        body = json.dumps(payload).encode("utf-8")
        headers = {}

        with pytest.raises(AuthenticationError):
            await receive_webhook(body, headers)

    @pytest.mark.asyncio
    async def test_oversized_payload_rejected(self):
        # Create payload > 16KB
        large_payload = make_valid_payload()
        large_payload["padding"] = "x" * 20000
        body = json.dumps(large_payload).encode("utf-8")
        headers = {
            "X-Client-Cert-Verified": "SUCCESS",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }

        with pytest.raises(PayloadValidationError, match="Payload too large"):
            await receive_webhook(body, headers)

    @pytest.mark.asyncio
    async def test_malformed_json_rejected(self):
        body = b'{"invalid": json}'
        headers = {
            "X-Client-Cert-Verified": "SUCCESS",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }

        with pytest.raises(PayloadValidationError, match="Malformed JSON"):
            await receive_webhook(body, headers)

    @pytest.mark.asyncio
    async def test_receiver_cannot_invoke_execution_routes(self):
        """Verify webhook receiver has no execution capabilities."""
        import inspect

        import obsidian_rl.interop.webhook_receiver as wr

        # Check module doesn't import execution modules
        source = inspect.getsource(wr)
        assert "PaperTrader" not in source
        assert "PortfolioEngine" not in source
        assert "RiskEngine" not in source
        assert "BinanceFuturesRest" not in source
        assert "execute" not in source.lower() or "execution" not in source.lower()

    @pytest.mark.asyncio
    async def test_receiver_cannot_mutate_portfolio_state(self):
        """Verify webhook receiver doesn't have portfolio mutation methods."""
        import inspect

        import obsidian_rl.interop.webhook_receiver as wr

        source = inspect.getsource(wr)
        assert "rebalance" not in source
        assert "liquidate" not in source
        assert "apply_funding" not in source
        assert "engine.state" not in source


class TestNoSecretLogging:
    """Verify no secrets are logged."""

    def setup_method(self):
        clear_event_id_cache()

    @pytest.mark.asyncio
    async def test_payload_not_logged_in_full(self, caplog):
        """Full payload with all fields should not be logged verbatim."""
        import logging

        caplog.set_level(logging.DEBUG)

        payload = make_valid_payload()
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "X-Client-Cert-Verified": "SUCCESS",
            "X-Client-Cert-Subject": "CN=TradingView Alerting",
        }

        await receive_webhook(body, headers)

        # Should log summary, not full payload
        for record in caplog.records:
            msg = record.getMessage()
            # Should not contain the full JSON
            assert "volatility_20d" not in msg or len(msg) < 200


class TestRateLimiting:
    """Test rate limiting (placeholder for future implementation)."""

    def setup_method(self):
        clear_event_id_cache()

    @pytest.mark.asyncio
    async def test_rate_limit_not_implemented_yet(self):
        """Rate limiting is not yet implemented but framework exists."""
        # Currently no rate limit enforcement in receive_webhook
        # This test documents expected future behavior
        pass


class TestConstants:
    """Verify configuration constants match requirements."""

    def test_max_skew_60_seconds(self):
        from obsidian_rl.interop.webhook_receiver import MAX_TIMESTAMP_SKEW_SECONDS

        assert MAX_TIMESTAMP_SKEW_SECONDS == 60

    def test_max_payload_16kb(self):
        from obsidian_rl.interop.webhook_receiver import MAX_PAYLOAD_SIZE_BYTES

        assert MAX_PAYLOAD_SIZE_BYTES == 16_384

    def test_supported_timeframes(self):
        from obsidian_rl.interop.webhook_receiver import SUPPORTED_TIMEFRAMES

        assert "4h" in SUPPORTED_TIMEFRAMES
        assert "1d" in SUPPORTED_TIMEFRAMES
        assert "240" in SUPPORTED_TIMEFRAMES  # Pine's 4h
        assert "D" in SUPPORTED_TIMEFRAMES  # Pine's 1d

    def test_supported_signals(self):
        from obsidian_rl.interop.webhook_receiver import SUPPORTED_SIGNALS

        assert SUPPORTED_SIGNALS == ("LONG", "SHORT", "FLAT")


class TestErrorHierarchy:
    """Test exception hierarchy for proper catching."""

    def test_all_inherit_from_webhook_error(self):
        assert issubclass(AuthenticationError, WebhookError)
        assert issubclass(ReplayError, WebhookError)
        assert issubclass(PayloadValidationError, WebhookError)
        assert issubclass(RateLimitError, WebhookError)
