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

    # Validate crypto gaps (no weekends)
    if asset_class == AssetClass.CRYPTO:
        expected_interval = _tf_to_ms(timeframe)
        for i in range(1, len(stored_bars)):
            diff = stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc
            if diff != expected_interval:
                raise ValueError(
                    f"Gap detected in crypto data {symbol} at {stored_bars[i].timestamp_utc}"
                )

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
