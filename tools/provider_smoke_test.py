"""CLI tool for live provider smoke validation (`BinanceSpotProvider`, `OandaPracticeProvider`)."""

import argparse
import os
import sys
import time
from collections.abc import Sequence

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.fingerprint import compute_market_bar_hash
from obsidian_rl.data.providers.binance import BinanceSpotProvider
from obsidian_rl.data.providers.errors import scrub_secrets
from obsidian_rl.data.providers.oanda import OandaPracticeProvider

_TIMEFRAME_MAP: dict[str, Timeframe] = {
    "1m": Timeframe.M1,
    "3m": Timeframe.M3,
    "5m": Timeframe.M5,
    "15m": Timeframe.M15,
    "30m": Timeframe.M30,
    "1h": Timeframe.H1,
    "2h": Timeframe.H2,
    "4h": Timeframe.H4,
    "1d": Timeframe.D1,
}

_TIMEFRAME_MS: dict[Timeframe, int] = {
    Timeframe.M1: 60_000,
    Timeframe.M3: 180_000,
    Timeframe.M5: 300_000,
    Timeframe.M15: 900_000,
    Timeframe.M30: 1_800_000,
    Timeframe.H1: 3_600_000,
    Timeframe.H2: 7_200_000,
    Timeframe.H4: 14_400_000,
    Timeframe.D1: 86_400_000,
}


def validate_smoke_bars(
    bars: Sequence[MarketBar],
    expected_venue: str,
    expected_asset_class: AssetClass,
    expected_quote_status: QuoteStatus,
    expected_volume_type: VolumeType,
    current_time_ms: int,
) -> None:
    """Validate chronological ordering, hash integrity, contract invariants, and timestamps."""
    if not bars:
        raise ValueError("No bars returned from provider")

    prev_ts = -1
    for bar in bars:
        if bar.venue != expected_venue:
            raise ValueError(f"Unexpected venue: {bar.venue} != {expected_venue}")
        if bar.asset_class != expected_asset_class:
            raise ValueError(f"Unexpected asset class: {bar.asset_class} != {expected_asset_class}")
        if bar.quote_status != expected_quote_status:
            raise ValueError(
                f"Unexpected quote status: {bar.quote_status} != {expected_quote_status}"
            )
        if bar.volume_type != expected_volume_type:
            raise ValueError(f"Unexpected volume type: {bar.volume_type} != {expected_volume_type}")
        if bar.timestamp_utc <= prev_ts:
            raise ValueError(
                f"Timestamps not strictly increasing: {bar.timestamp_utc} <= {prev_ts}"
            )
        prev_ts = bar.timestamp_utc

        if bar.observed_at_utc > current_time_ms + 60_000:
            raise ValueError(
                f"Future observed timestamp: {bar.observed_at_utc} > {current_time_ms}"
            )
        if bar.observed_at_utc <= bar.timestamp_utc:
            raise ValueError(
                f"Observed timestamp <= start timestamp: {bar.observed_at_utc} <= "
                f"{bar.timestamp_utc}"
            )

        computed_hash = compute_market_bar_hash(bar)
        if bar.row_hash != computed_hash:
            raise ValueError(f"Bar row_hash mismatch: {bar.row_hash} != {computed_hash}")


def run_smoke_test(args: argparse.Namespace) -> int:
    """Run live provider smoke test with safety interlocks."""
    if not args.live:
        print(
            "ERROR: Safety interlock triggered. The --live flag is required to perform live "
            "provider network requests.",
            file=sys.stderr,
        )
        return 1

    if args.bars < 1:
        print(f"ERROR: --bars must be >= 1, got {args.bars}", file=sys.stderr)
        return 1
    if args.bars > 10:
        print(f"ERROR: --bars exceeds hard maximum limit of 10, got {args.bars}", file=sys.stderr)
        return 1

    provider_name = args.provider.lower()
    if provider_name not in ("binance", "oanda"):
        print(
            f"ERROR: Invalid provider '{args.provider}'. Must be 'binance' or 'oanda'.",
            file=sys.stderr,
        )
        return 1

    tf_str = args.timeframe.lower()
    if tf_str not in _TIMEFRAME_MAP:
        print(f"ERROR: Invalid timeframe '{args.timeframe}'.", file=sys.stderr)
        return 1
    tf_enum = _TIMEFRAME_MAP[tf_str]
    tf_ms = _TIMEFRAME_MS[tf_enum]

    current_time_ms = int(time.time() * 1000)

    if provider_name == "binance":
        symbol = args.symbol or "BTCUSDT"
        end_ms = current_time_ms
        start_ms = end_ms - (tf_ms * (args.bars + 3))

        binance_provider = BinanceSpotProvider()
        try:
            bars = binance_provider.fetch_bars(symbol, tf_enum, start_ms, end_ms)
        except Exception as exc:
            err_msg = scrub_secrets(str(exc))
            print(f"ERROR: Binance live request failed: {err_msg}", file=sys.stderr)
            return 1

        selected_bars = bars[-args.bars :] if len(bars) >= args.bars else bars
        try:
            validate_smoke_bars(
                selected_bars,
                expected_venue="BINANCE_SPOT",
                expected_asset_class=AssetClass.CRYPTO,
                expected_quote_status=QuoteStatus.UNAVAILABLE,
                expected_volume_type=VolumeType.BASE,
                current_time_ms=current_time_ms,
            )
        except ValueError as exc:
            print(f"ERROR: Binance data validation failed: {exc}", file=sys.stderr)
            return 1

        print("=== LIVE PROVIDER SMOKE TEST: BINANCE ===")
        print("Status: SUCCESS")
        print(
            f"Symbol: {symbol} | Timeframe: {tf_enum.value} | Bars Returned: {len(selected_bars)}"
        )
        for i, b in enumerate(selected_bars, 1):
            hash_short = b.row_hash[:16]
            print(
                f"  Bar {i}: ts={b.timestamp_utc} obs={b.observed_at_utc} O={b.open} "
                f"H={b.high} L={b.low} C={b.close} Vol={b.volume} Hash={hash_short}..."
            )
        return 0

    elif provider_name == "oanda":
        token = os.environ.get("OANDA_API_TOKEN")
        if not token or not token.strip():
            print("=== LIVE PROVIDER SMOKE TEST: OANDA ===")
            print("Status: SKIPPED_TOKEN_MISSING")
            print(
                "Message: OANDA_API_TOKEN environment variable not found. "
                "Skipping live OANDA test without error."
            )
            return 0

        clean_token = token.strip()
        symbol = args.symbol or "EUR_USD"
        end_ms = current_time_ms
        start_ms = end_ms - (tf_ms * (args.bars + 3))

        try:
            oanda_provider = OandaPracticeProvider(api_token=clean_token)
            bars = oanda_provider.fetch_bars(symbol, tf_enum, start_ms, end_ms)
        except Exception as exc:
            err_msg = scrub_secrets(str(exc), secrets=(clean_token,))
            print(f"ERROR: OANDA live request failed: {err_msg}", file=sys.stderr)
            return 1

        selected_bars = bars[-args.bars :] if len(bars) >= args.bars else bars
        try:
            validate_smoke_bars(
                selected_bars,
                expected_venue="OANDA_PRACTICE",
                expected_asset_class=AssetClass.FOREX,
                expected_quote_status=QuoteStatus.OBSERVED,
                expected_volume_type=VolumeType.TICK,
                current_time_ms=current_time_ms,
            )
        except ValueError as exc:
            print(f"ERROR: OANDA data validation failed: {exc}", file=sys.stderr)
            return 1

        print("=== LIVE PROVIDER SMOKE TEST: OANDA ===")
        print("Status: SUCCESS")
        print(
            f"Symbol: {symbol} | Timeframe: {tf_enum.value} | Bars Returned: {len(selected_bars)}"
        )
        for i, b in enumerate(selected_bars, 1):
            hash_short = b.row_hash[:16]
            print(
                f"  Bar {i}: ts={b.timestamp_utc} obs={b.observed_at_utc} O={b.open} "
                f"H={b.high} L={b.low} C={b.close} Bid={b.bid} Ask={b.ask} Vol={b.volume} "
                f"Hash={hash_short}..."
            )
        return 0

    return 1


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point for provider smoke test tool."""
    parser = argparse.ArgumentParser(description="Live Market Data Provider Smoke Test Tool")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicit interlock flag required for network requests",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="binance",
        help="Provider to test ('binance' or 'oanda')",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Trading symbol (e.g. BTCUSDT, EUR_USD)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="4h",
        help="Candle timeframe (e.g. 15m, 1h, 4h, 1d)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=3,
        help="Number of completed bars to request (default: 3, max: 10)",
    )

    args = parser.parse_args(argv)
    sys.exit(run_smoke_test(args))


if __name__ == "__main__":
    main()
