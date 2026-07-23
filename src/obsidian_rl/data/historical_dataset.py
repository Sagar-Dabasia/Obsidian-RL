"""Historical dataset builder.

Supports downloading and validating large bounded historical datasets
safely with idempotency and interrupted-run resume.
"""

import hashlib
from datetime import UTC, datetime

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.providers.base import MarketDataProvider
from obsidian_rl.data.providers.binance import BinanceSpotProvider
from obsidian_rl.data.providers.oanda import OandaPracticeProvider
from obsidian_rl.data.storage import DatasetManifest, SQLiteStorage

CHUNK_SIZE_MS = 30 * 24 * 60 * 60 * 1000  # 30 days


def _get_provider(asset_class: AssetClass) -> MarketDataProvider:
    if asset_class == AssetClass.CRYPTO:
        return BinanceSpotProvider()
    elif asset_class == AssetClass.FOREX:
        return OandaPracticeProvider()
    raise ValueError(f"No provider mapping for {asset_class}")


def _get_venue(asset_class: AssetClass) -> str:
    if asset_class == AssetClass.CRYPTO:
        return "BINANCE_SPOT"
    elif asset_class == AssetClass.FOREX:
        return "OANDA_PRACTICE"
    raise ValueError("Venue map error")


def ingest_historical_range(
    asset_class: AssetClass,
    symbol: str,
    timeframe: Timeframe,
    start_ms: int,
    end_ms: int,
    storage: SQLiteStorage,
) -> DatasetManifest:
    """Ingest a historical range chunk by chunk into SQLite."""
    provider = _get_provider(asset_class)
    venue = _get_venue(asset_class)

    # Smart resume: find latest timestamp in DB for this symbol
    existing_bars = storage.query_market_bars(
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        start_timestamp_utc=start_ms,
        end_timestamp_utc=end_ms,
    )
    cursor_ms = start_ms
    if existing_bars:
        last_ts = existing_bars[-1].timestamp_utc
        # Move cursor past the last completely stored bar
        cursor_ms = last_ts + _tf_to_ms(timeframe)

    while cursor_ms < end_ms:
        chunk_end = min(end_ms, cursor_ms + CHUNK_SIZE_MS)

        try:
            bars = provider.fetch_bars(symbol, timeframe, cursor_ms, chunk_end)
            if bars:
                storage.insert_market_bars(bars)
        except Exception as e:
            # We fail on missing crypto quotes or other issues, but allow retry from script layer.
            raise RuntimeError(f"Ingestion failed for {symbol} at {cursor_ms}: {e}") from e

        cursor_ms = chunk_end

    # Validation: Query back from DB
    stored_bars = storage.query_market_bars(
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        start_timestamp_utc=start_ms,
        end_timestamp_utc=end_ms,
    )

    if not stored_bars:
        raise ValueError(f"No data ingested for {symbol}")

    # Validate and recover crypto gaps
    if asset_class == AssetClass.CRYPTO:
        expected_interval = _tf_to_ms(timeframe)
        eval_start_ms = 1577836800000  # 2020-01-01T00:00:00Z

        while True:
            gaps_found = False
            stored_bars.sort(key=lambda b: b.timestamp_utc)
            for i in range(1, len(stored_bars)):
                diff = stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc
                if diff > expected_interval:
                    gap_start = stored_bars[i - 1].timestamp_utc + expected_interval
                    gap_end = stored_bars[i].timestamp_utc

                    is_eval = gap_end > eval_start_ms
                    period_name = "EVALUATION" if is_eval else "WARM-UP"
                    print(f"Gap detected [{period_name}] in {symbol}: {gap_start} to {gap_end}")

                    # Refetch attempt
                    recovered = False
                    for attempt in range(3):
                        print(f"Refetch attempt {attempt + 1}/3 for {symbol} at {gap_start}...")
                        try:
                            recovered_bars = provider.fetch_bars(
                                symbol, timeframe, gap_start, gap_end
                            )
                            if recovered_bars:
                                print(
                                    f"Binance returned {len(recovered_bars)} candles on attempt {attempt + 1}."
                                )
                                storage.insert_market_bars(recovered_bars)
                                stored_bars.extend(recovered_bars)
                                recovered = True
                                break
                        except Exception as e:
                            print(f"Refetch error: {e}")

                    if not recovered:
                        print("Binance returned NO candles after 3 attempts.")

                    if recovered:
                        gaps_found = True
                        break  # break the for loop to re-sort and re-evaluate

                    # Unrecoverable gap
                    if gap_end > eval_start_ms:
                        print(f"Unrecoverable evaluation gap in {symbol} at {gap_start}")
                        # We don't raise immediately to allow auditing all gaps, but we mark it to fail later.

            if not gaps_found:
                break

        # Check if we had any evaluation gaps
        eval_gaps = []
        for i in range(1, len(stored_bars)):
            if stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc > expected_interval:
                if stored_bars[i].timestamp_utc > eval_start_ms:
                    eval_gaps.append(stored_bars[i - 1].timestamp_utc + expected_interval)

        if eval_gaps:
            raise ValueError(f"Unrecoverable evaluation gaps in {symbol}: {eval_gaps}")

        # After all refetches, find the last gap
        stored_bars.sort(key=lambda b: b.timestamp_utc)
        last_gap_ts = -1
        for i in range(1, len(stored_bars)):
            if stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc > expected_interval:
                last_gap_ts = stored_bars[i - 1].timestamp_utc

        if last_gap_ts != -1:
            # We have a warm-up gap. Find the continuous segment after the last gap.
            continuous_bars = [b for b in stored_bars if b.timestamp_utc > last_gap_ts]
            warmup_bars_before_eval = [
                b for b in continuous_bars if b.timestamp_utc < eval_start_ms
            ]

            if len(warmup_bars_before_eval) < 721:
                print(
                    f"Continuous bars available before evaluation: {len(warmup_bars_before_eval)} (Failed, need 721)"
                )
                raise ValueError(
                    f"Insufficient continuous warm-up bars after gap in {symbol}. "
                    f"Needed 721, got {len(warmup_bars_before_eval)}."
                )
            print(
                f"Continuous bars available before evaluation: {len(warmup_bars_before_eval)} (Passed)"
            )
            # Truncate dataset to only include the continuous segment
            stored_bars = continuous_bars

    # Create deterministic manifest
    row_hashes = [b.row_hash for b in stored_bars]
    h = hashlib.sha256()
    for row_hash in row_hashes:
        h.update(row_hash.encode("utf-8"))
    combined_digest = h.hexdigest()

    manifest = DatasetManifest(
        dataset_id=f"TREND_PILOT_01_{symbol}_{start_ms}_{end_ms}",
        source=provider.provider_name,
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        row_count=len(stored_bars),
        start_timestamp_utc=stored_bars[0].timestamp_utc,
        end_timestamp_utc=stored_bars[-1].timestamp_utc + _tf_to_ms(timeframe),
        start_observed_at_utc=stored_bars[0].observed_at_utc,
        end_observed_at_utc=stored_bars[-1].observed_at_utc,
        digest=combined_digest,
        created_at_utc=int(datetime.now(UTC).timestamp() * 1000),
    )
    return manifest


def _tf_to_ms(tf: Timeframe) -> int:
    if tf == Timeframe.H4:
        return 4 * 60 * 60 * 1000
    if tf == Timeframe.D1:
        return 24 * 60 * 60 * 1000
    raise ValueError(f"Unsupported tf {tf}")
