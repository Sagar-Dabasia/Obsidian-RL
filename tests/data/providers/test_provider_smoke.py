"""Unit tests for live provider smoke test tool CLI and safety interlocks (offline)."""

from unittest.mock import MagicMock, patch

import pytest

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from tools.provider_smoke_test import main


def make_smoke_bar(ts: int, venue: str = "BINANCE_SPOT") -> MarketBar:
    return MarketBar(
        asset_class=AssetClass.CRYPTO if venue == "BINANCE_SPOT" else AssetClass.FOREX,
        venue=venue,
        symbol="BTCUSDT" if venue == "BINANCE_SPOT" else "EUR_USD",
        timeframe=Timeframe.H4,
        timestamp_utc=ts,
        observed_at_utc=ts + 14_400_000,
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        quote_status=QuoteStatus.UNAVAILABLE if venue == "BINANCE_SPOT" else QuoteStatus.OBSERVED,
        bid=None if venue == "BINANCE_SPOT" else 101.9,
        ask=None if venue == "BINANCE_SPOT" else 102.1,
        volume_type=VolumeType.BASE if venue == "BINANCE_SPOT" else VolumeType.TICK,
        volume=10.0,
        data_source="SMOKE_TEST",
    )


def test_smoke_tool_requires_live_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify missing --live flag triggers safety interlock and returns code 1."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--provider", "binance"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Safety interlock triggered" in captured.err


def test_smoke_tool_bar_limit_enforcement(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify --bars limit enforcement (1 <= bars <= 10)."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--bars", "0"])
    assert exc_info.value.code == 1
    assert "--bars must be >= 1" in capsys.readouterr().err

    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--bars", "11"])
    assert exc_info.value.code == 1
    assert "exceeds hard maximum limit of 10" in capsys.readouterr().err


def test_smoke_tool_invalid_provider_rejection(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify unsupported provider returns code 1."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--provider", "invalid_provider"])
    assert exc_info.value.code == 1
    assert "Invalid provider 'invalid_provider'" in capsys.readouterr().err


def test_smoke_tool_oanda_missing_token_skipped(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify OANDA skips cleanly when OANDA_API_TOKEN is absent."""
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--provider", "oanda"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Status: SKIPPED_TOKEN_MISSING" in captured.out


@patch("tools.provider_smoke_test.BinanceSpotProvider")
def test_smoke_tool_binance_successful_summary(
    mock_binance_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify mock Binance smoke run outputs sanitized summary."""
    mock_instance = MagicMock()
    mock_binance_cls.return_value = mock_instance
    mock_instance.fetch_bars.return_value = (
        make_smoke_bar(1000),
        make_smoke_bar(2000),
        make_smoke_bar(3000),
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--provider", "binance", "--symbol", "BTCUSDT", "--bars", "3"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "=== LIVE PROVIDER SMOKE TEST: BINANCE ===" in captured.out
    assert "Status: SUCCESS" in captured.out
    assert "Bars Returned: 3" in captured.out


@patch("tools.provider_smoke_test.OandaPracticeProvider")
def test_smoke_tool_token_never_printed_on_error(
    mock_oanda_cls: MagicMock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify OANDA secret token is scrubbed from error output if provider fails."""
    secret_token = "secret_oanda_token_999"
    monkeypatch.setenv("OANDA_API_TOKEN", secret_token)

    mock_instance = MagicMock()
    mock_oanda_cls.return_value = mock_instance
    mock_instance.fetch_bars.side_effect = RuntimeError(
        f"Connection failed with token={secret_token}"
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--provider", "oanda"])
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert secret_token not in captured.err
    assert secret_token not in captured.out
    assert "[REDACTED]" in captured.err


@patch("tools.provider_smoke_test.BinanceSpotProvider")
def test_smoke_tool_non_zero_exit_on_invalid_data(
    mock_binance_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify non-zero exit when returned bars fail contract validation."""
    mock_instance = MagicMock()
    mock_binance_cls.return_value = mock_instance
    # Timestamps not increasing
    mock_instance.fetch_bars.return_value = (
        make_smoke_bar(3000),
        make_smoke_bar(2000),
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["--live", "--provider", "binance"])
    assert exc_info.value.code == 1
    assert "Binance data validation failed" in capsys.readouterr().err
