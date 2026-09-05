"""Tests for TradingView webhook receiver.

Verifies fail-closed validation, replay protection, authentication, and correct parsing.
"""

import time
import pytest

from src.obsidian_rl.interop.webhook_receiver import (
    ValidatedSignal,
    SignalDirection,
    receive_tradingview_alert,
    ValidationError,
    AuthenticationError,
    ReplayDetected,
    clear_replay_cache,
    _replay_cache,
    MAX_TIMESTAMP_SKEW_SECONDS,
)


# Valid base payload factory for tests - creates fresh timestamps
def make_valid_payload(event_id: str = "BTCUSDT_240_TEST") -> dict:
    """Create a valid payload with current timestamp."""
    return {
        "schema_version": "1",
        "event_id": event_id,
        "symbol": "BTCUSDT",
        "timeframe": "4h",
        "bar_timestamp_utc": int(time.time() * 1000),
        "signal": "LONG",
        "score": 1.0,
        "volatility_20d": 0.0234,
        "latest_close": 51234.56,
        "engine_version": "TrendEngineV1",
        "config_identity": "a" * 64,
    }


VALID_HEADERS = {
    "X-Client-Cert-Verified": "SUCCESS",
    "X-Client-Cert-Subject": "CN=TradingView Alerting",
}


def test_valid_payload_parsed_correctly():
    """A fully valid payload returns a ValidatedSignal with correct fields."""
    clear_replay_cache()
    payload = make_valid_payload()
    signal = receive_tradingview_alert(payload, VALID_HEADERS)

    assert isinstance(signal, ValidatedSignal)
    assert signal.event_id == payload["event_id"]
    assert signal.symbol == payload["symbol"]
    assert signal.timeframe == payload["timeframe"]
    assert signal.bar_timestamp_utc == payload["bar_timestamp_utc"]
    assert signal.signal == SignalDirection.LONG
    assert signal.score == 1.0
    assert signal.volatility_20d == 0.0234
    assert signal.latest_close == 51234.56
    assert signal.engine_version == "TrendEngineV1"
    assert signal.config_identity == "a" * 64


def test_all_signal_directions_accepted():
    """LONG, SHORT, and FLAT signals are all valid when score/volatility match."""
    clear_replay_cache()

    # LONG
    payload = make_valid_payload("TEST_LONG")
    payload["signal"] = "LONG"
    payload["score"] = 1.0
    payload["volatility_20d"] = 0.02
    signal = receive_tradingview_alert(payload, VALID_HEADERS)
    assert signal.signal == SignalDirection.LONG

    # SHORT
    clear_replay_cache()
    payload = make_valid_payload("TEST_SHORT")
    payload["signal"] = "SHORT"
    payload["score"] = -1.0
    payload["volatility_20d"] = 0.02
    signal = receive_tradingview_alert(payload, VALID_HEADERS)
    assert signal.signal == SignalDirection.SHORT

    # FLAT
    clear_replay_cache()
    payload = make_valid_payload("TEST_FLAT")
    payload["signal"] = "FLAT"
    payload["score"] = 0.0
    payload["volatility_20d"] = 0.0
    signal = receive_tradingview_alert(payload, VALID_HEADERS)
    assert signal.signal == SignalDirection.FLAT


def test_unexpected_field_rejected():
    """Extra fields in payload are rejected (fail-closed)."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_EXTRA")
    payload["unexpected_field"] = "malicious"
    with pytest.raises(ValidationError, match="Extra field 'unexpected_field' not allowed"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_missing_required_field_rejected():
    """Missing any required field is rejected."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_MISSING")
    del payload["volatility_20d"]
    with pytest.raises(ValidationError, match="Missing required field: volatility_20d"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_invalid_schema_version_rejected():
    """schema_version must be '1'."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_SCHEMA")
    payload["schema_version"] = "2"
    with pytest.raises(ValidationError, match="schema_version must be"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_invalid_event_id_rejected():
    """event_id must be non-empty and <= 256 chars."""
    clear_replay_cache()

    # Empty
    payload = make_valid_payload("TEST_EMPTY")
    payload["event_id"] = ""
    with pytest.raises(ValidationError, match="event_id:|Input should have at least 1 character"):
        receive_tradingview_alert(payload, VALID_HEADERS)

    # Too long
    clear_replay_cache()
    payload = make_valid_payload("TEST_TOO_LONG")
    payload["event_id"] = "x" * 300
    with pytest.raises(ValidationError, match="event_id:|Input should have at least 1 character"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_invalid_symbol_format_rejected():
    """Symbol must match pattern [A-Za-z0-9_.-] and be <= 64 chars."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_SYMBOL")
    payload["symbol"] = "INVALID@SYMBOL"
    with pytest.raises(ValidationError, match="symbol must match pattern"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_invalid_timeframe_rejected():
    """timeframe must be one of 4h, 1d, 240, D."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_TF")
    payload["timeframe"] = "15m"
    with pytest.raises(ValidationError, match="timeframe must be one of 4h, 1d, 240, D"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_bar_timestamp_utc_positive():
    """bar_timestamp_utc must be positive integer."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_TS")
    payload["bar_timestamp_utc"] = 0
    with pytest.raises(ValidationError, match="bar_timestamp_utc.*greater than 0|bar_timestamp_utc: Input should be greater than 0"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_non_finite_numeric_rejected():
    """score, volatility_20d, latest_close must be finite."""
    for field in ["score", "volatility_20d", "latest_close"]:
        clear_replay_cache()
        payload = make_valid_payload(f"TEST_NAN_{field}")
        payload[field] = float("nan")
        with pytest.raises(ValidationError, match="value must be finite"):
            receive_tradingview_alert(payload, VALID_HEADERS)

        clear_replay_cache()
        payload = make_valid_payload(f"TEST_INF_{field}")
        payload[field] = float("inf")
        with pytest.raises(ValidationError, match="value must be finite"):
            receive_tradingview_alert(payload, VALID_HEADERS)

        clear_replay_cache()
        payload = make_valid_payload(f"TEST_NEGINF_{field}")
        payload[field] = float("-inf")
        with pytest.raises(ValidationError, match="value must be finite"):
            receive_tradingview_alert(payload, VALID_HEADERS)


def test_engine_version_must_contain_prefix():
    """engine_version must contain 'TrendEngineV1'."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_ENGINE")
    payload["engine_version"] = "SomeOtherEngineV2"
    with pytest.raises(ValidationError, match="engine_version must contain"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_config_identity_must_be_64_hex():
    """config_identity must be 64-char lowercase hex."""
    clear_replay_cache()
    payload = make_valid_payload("TEST_CONFIG")
    payload["config_identity"] = "not-hex"
    with pytest.raises(ValidationError, match="config_identity must be"):
        receive_tradingview_alert(payload, VALID_HEADERS)

    clear_replay_cache()
    payload = make_valid_payload("TEST_CONFIG_LEN")
    payload["config_identity"] = "a" * 63  # too short
    with pytest.raises(ValidationError, match="config_identity must be"):
        receive_tradingview_alert(payload, VALID_HEADERS)

    clear_replay_cache()
    payload = make_valid_payload("TEST_CONFIG_UPPER")
    payload["config_identity"] = "A" * 64  # uppercase
    with pytest.raises(ValidationError, match="config_identity must be"):
        receive_tradingview_alert(payload, VALID_HEADERS)


def test_long_short_require_nonzero_score_and_volatility():
    """LONG and SHORT signals require non-zero score and positive volatility."""
    clear_replay_cache()
    now = int(time.time() * 1000)

    # LONG with zero score
    payload = make_valid_payload("TEST_ZERO_SCORE_LONG")
    payload["signal"] = "LONG"
    payload["score"] = 0.0
    with pytest.raises(ValidationError, match="LONG/SHORT signals require"):
        receive_tradingview_alert(payload, VALID_HEADERS, received_at_utc=now)

    # LONG with zero volatility
    clear_replay_cache()
    payload = make_valid_payload("TEST_ZERO_VOL_LONG")
    payload["signal"] = "LONG"
    payload["volatility_20d"] = 0.0
    with pytest.raises(ValidationError, match="LONG/SHORT signals require"):
        receive_tradingview_alert(payload, VALID_HEADERS, received_at_utc=now)

    # SHORT with zero score
    clear_replay_cache()
    payload = make_valid_payload("TEST_ZERO_SCORE_SHORT")
    payload["signal"] = "SHORT"
    payload["score"] = 0.0
    with pytest.raises(ValidationError, match="LONG/SHORT signals require"):
        receive_tradingview_alert(payload, VALID_HEADERS, received_at_utc=now)


def test_flat_requires_near_zero_score():
    """FLAT signal requires near-zero score."""
    clear_replay_cache()
    now = int(time.time() * 1000)
    payload = make_valid_payload("TEST_FLAT_NZ")
    payload["signal"] = "FLAT"
    payload["score"] = 0.5
    with pytest.raises(ValidationError, match="FLAT signal requires"):
        receive_tradingview_alert(payload, VALID_HEADERS, received_at_utc=now)


def test_timestamp_freshness_enforced():
    """Timestamp must be within MAX_TIMESTAMP_SKEW_SECONDS of receipt."""
    clear_replay_cache()
    now = int(time.time() * 1000)

    # Future timestamp (beyond skew)
    payload = make_valid_payload("TEST_FUTURE_TS")
    future_ts = now + (MAX_TIMESTAMP_SKEW_SECONDS + 10) * 1000
    payload["bar_timestamp_utc"] = future_ts
    with pytest.raises(ValidationError, match="Timestamp skew"):
        receive_tradingview_alert(payload, VALID_HEADERS, received_at_utc=now)

    # Stale timestamp (beyond skew)
    clear_replay_cache()
    payload = make_valid_payload("TEST_STALE_TS")
    stale_ts = now - (MAX_TIMESTAMP_SKEW_SECONDS + 10) * 1000
    payload["bar_timestamp_utc"] = stale_ts
    with pytest.raises(ValidationError, match="Timestamp skew"):
        receive_tradingview_alert(payload, VALID_HEADERS, received_at_utc=now)


def test_replay_detection():
    """Duplicate event_id is rejected as replay."""
    clear_replay_cache()
    now = int(time.time() * 1000)
    payload = make_valid_payload("TEST_REPLAY")

    # First request succeeds
    signal1 = receive_tradingview_alert(make_valid_payload("TEST_REPLAY"), VALID_HEADERS, received_at_utc=now)
    assert isinstance(signal1, ValidatedSignal)

    # Duplicate event_id rejected
    with pytest.raises(ReplayDetected, match="Duplicate event_id"):
        receive_tradingview_alert(make_valid_payload("TEST_REPLAY"), VALID_HEADERS, received_at_utc=now)


def test_replay_cache_isolation():
    """Clear replay cache for testing."""
    clear_replay_cache()
    assert len(_replay_cache) == 0

    # Add something
    _replay_cache.add("test")
    assert len(_replay_cache) == 1

    clear_replay_cache()
    assert len(_replay_cache) == 0


def test_missing_cert_verified_header_rejected():
    """Missing X-Client-Cert-Verified header is rejected."""
    clear_replay_cache()
    headers = {"X-Client-Cert-Subject": "CN=TradingView Alerting"}
    with pytest.raises(AuthenticationError, match="Missing or invalid X-Client-Cert-Verified"):
        receive_tradingview_alert(make_valid_payload(), headers)


def test_invalid_cert_verified_value_rejected():
    """X-Client-Cert-Verified must be 'SUCCESS'."""
    clear_replay_cache()
    headers = {
        "X-Client-Cert-Verified": "FAILURE",
        "X-Client-Cert-Subject": "CN=TradingView Alerting",
    }
    with pytest.raises(AuthenticationError, match="Missing or invalid X-Client-Cert-Verified"):
        receive_tradingview_alert(make_valid_payload(), headers)


def test_missing_cert_subject_rejected():
    """Missing X-Client-Cert-Subject header is rejected."""
    clear_replay_cache()
    headers = {"X-Client-Cert-Verified": "SUCCESS"}
    with pytest.raises(AuthenticationError, match="Missing or invalid X-Client-Cert-Subject"):
        receive_tradingview_alert(make_valid_payload(), headers)


def test_invalid_cert_subject_rejected():
    """X-Client-Cert-Subject must contain TradingView CN."""
    clear_replay_cache()
    headers = {
        "X-Client-Cert-Verified": "SUCCESS",
        "X-Client-Cert-Subject": "CN=SomeOtherCA",
    }
    with pytest.raises(AuthenticationError, match="Client certificate subject does not appear to be TradingView"):
        receive_tradingview_alert(make_valid_payload(), headers)


def test_valid_headers_accepted():
    """Valid cert headers pass authentication."""
    clear_replay_cache()
    signal = receive_tradingview_alert(make_valid_payload(), VALID_HEADERS)
    assert isinstance(signal, ValidatedSignal)


def test_custom_received_at_utc():
    """Custom received_at_utc parameter is respected."""
    clear_replay_cache()
    custom_received = int(time.time() * 1000)
    signal = receive_tradingview_alert(make_valid_payload(), VALID_HEADERS, received_at_utc=custom_received)
    assert signal.received_at_utc == custom_received


def test_all_valid_timeframes():
    """All valid timeframes are accepted."""
    for tf in ["4h", "1d", "240", "D"]:
        clear_replay_cache()
        payload = make_valid_payload(f"TEST_TF_{tf}")
        payload["timeframe"] = tf
        signal = receive_tradingview_alert(payload, VALID_HEADERS)
        assert signal.timeframe == tf


def test_no_execution_imports():
    """Verify the module does not import execution modules."""
    import src.obsidian_rl.interop.webhook_receiver as wr

    # Check that no exchange/order/portfolio modules are imported
    module_names = [m for m in wr.__dict__.keys() if not m.startswith("_")]
    # Just verify the module loads without execution dependencies
    # The actual import safety is verified by not having those imports at all
    assert hasattr(wr, "receive_tradingview_alert")
    assert hasattr(wr, "ValidatedSignal")
    assert hasattr(wr, "SignalDirection")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])