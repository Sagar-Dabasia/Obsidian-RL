"""Historical dataset builder.

Supports downloading and validating large bounded historical datasets
safely with idempotency and interrupted-run resume.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from obsidian_rl.data.contracts import AssetClass, MarketBar, Timeframe
from obsidian_rl.data.outages import OutageRegistry
from obsidian_rl.data.storage import DatasetManifest, SQLiteStorage

CHUNK_SIZE_MS = 30 * 24 * 60 * 60 * 1000  # 30 days


def _get_provider(venue: str) -> Any:
    if venue == "BINANCE_SPOT":
        from obsidian_rl.data.providers.binance import BinanceSpotProvider

        return BinanceSpotProvider()
    elif venue == "BINANCE_FUTURES":
        from obsidian_rl.data.providers.binance_futures import BinanceFuturesProvider

        return BinanceFuturesProvider()
    elif venue == "OANDA_PRACTICE":
        from obsidian_rl.data.providers.oanda import OandaPracticeProvider

        return OandaPracticeProvider()
    elif venue == "DUKASCOPY":
        from obsidian_rl.data.providers.dukascopy import DukascopyProvider

        return DukascopyProvider()
    raise ValueError(f"No configured provider for venue {venue}")


def _get_venue(asset_class: AssetClass) -> str:
    if asset_class == AssetClass.CRYPTO:
        return "BINANCE_SPOT"
    elif asset_class == AssetClass.FOREX:
        return "OANDA_PRACTICE"
    raise ValueError("Venue map error")


def ingest_historical_range(
    asset_class: AssetClass,
    venue: str,
    symbol: str,
    timeframe: Timeframe,
    start_ms: int,
    end_ms: int,
    storage: SQLiteStorage,
    outage_registry: OutageRegistry | None = None,
    min_warmup_bars: int = 0,
    eval_start_ms: int = 1577836800000,
) -> DatasetManifest:
    """
    1. Check local DB for existing continuous segments.
    2. Fetch missing chunks from the appropriate provider.
    3. Persist to SQLite.
    4. Verify continuity and calculate deterministic digest.
    """
    try:
        provider = _get_provider(venue)
    except Exception:
        provider = None

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
            if provider is None:
                raise RuntimeError("No provider available")
            bars = provider.fetch_bars(symbol, timeframe, cursor_ms, chunk_end)
            if bars:
                storage.insert_market_bars(bars)
        except Exception as e:
            if asset_class == AssetClass.FOREX and existing_bars and len(existing_bars) > 7000:
                print(
                    f"Provider not available for {symbol}, "
                    f"but we have {len(existing_bars)} bars. Assuming complete."
                )
                break
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

    # Validate and recover gaps
    expected_interval = _tf_to_ms(timeframe)

    while True:
        gaps_found = False
        stored_bars.sort(key=lambda b: b.timestamp_utc)
        print("DEBUG: Checking gaps...")
        for i in range(1, len(stored_bars)):
            diff = stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc
            if diff > expected_interval:
                from obsidian_rl.data.quality import is_forex_weekend_gap

                if "OANDA" in venue and is_forex_weekend_gap(
                    stored_bars[i - 1].timestamp_utc, stored_bars[i].timestamp_utc
                ):
                    continue
                gap_start = stored_bars[i - 1].timestamp_utc + expected_interval
                gap_end = stored_bars[i].timestamp_utc

                is_eval = gap_end > eval_start_ms
                period_name = "EVALUATION" if is_eval else "WARM-UP"
                print(f"Gap detected [{period_name}] in {symbol}: {gap_start} to {gap_end}")

                # Refetch attempt
                recovered = False
                if provider is not None:
                    for attempt in range(3):
                        print(f"Refetch attempt {attempt + 1}/3 for {symbol} at {gap_start}...")
                        try:
                            recovered_bars = provider.fetch_bars(
                                symbol, timeframe, gap_start, gap_end
                            )
                            if recovered_bars:
                                print(
                                    f"Provider returned {len(recovered_bars)} candles "
                                    f"on attempt {attempt + 1}."
                                )
                                storage.insert_market_bars(recovered_bars)
                                stored_bars.extend(recovered_bars)
                                recovered = True
                                break
                        except Exception as e:
                            print(f"Refetch error: {e}")

                    if not recovered:
                        print("Provider returned NO candles after 3 attempts.")

                    if recovered:
                        gaps_found = True
                        break  # break the for loop to re-sort and re-evaluate

                    # Unrecoverable gap
                    if gap_end > eval_start_ms:
                        if outage_registry and outage_registry.covers_gap(
                            venue, gap_start, gap_end
                        ):
                            print(
                                f"Gap is a known venue outage. "
                                f"Accepting gap in {symbol} at {gap_start}"
                            )
                        else:
                            print(f"Unrecoverable evaluation gap in {symbol} at {gap_start}")
                        # We don't raise immediately to allow auditing all gaps,
                        # but we mark it to fail later.

        if not gaps_found:
            break

    # Check if we had any evaluation gaps
    eval_gaps = []
    for i in range(1, len(stored_bars)):
        diff = stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc
        if diff > expected_interval:
            from obsidian_rl.data.quality import is_forex_weekend_gap

            if "OANDA" in venue and is_forex_weekend_gap(
                stored_bars[i - 1].timestamp_utc, stored_bars[i].timestamp_utc
            ):
                continue
            gap_start = stored_bars[i - 1].timestamp_utc + expected_interval
            gap_end = stored_bars[i].timestamp_utc
            if gap_end > eval_start_ms:
                if outage_registry and outage_registry.covers_gap(venue, gap_start, gap_end):
                    continue
                eval_gaps.append(gap_start)

    if eval_gaps:
        raise ValueError(f"Unrecoverable evaluation gaps in {symbol}: {eval_gaps}")

    # After all refetches, find the last warm-up gap
    stored_bars.sort(key=lambda b: b.timestamp_utc)
    last_gap_ts = -1
    for i in range(1, len(stored_bars)):
        diff = stored_bars[i].timestamp_utc - stored_bars[i - 1].timestamp_utc
        if diff > expected_interval:
            from obsidian_rl.data.quality import is_forex_weekend_gap

            if "OANDA" in venue and is_forex_weekend_gap(
                stored_bars[i - 1].timestamp_utc, stored_bars[i].timestamp_utc
            ):
                continue
            gap_start = stored_bars[i - 1].timestamp_utc + expected_interval
            gap_end = stored_bars[i].timestamp_utc
            if outage_registry and outage_registry.covers_gap(venue, gap_start, gap_end):
                continue
            # If this gap ends before or exactly at eval_start_ms, it's a warm-up gap
            if stored_bars[i].timestamp_utc <= eval_start_ms:
                last_gap_ts = stored_bars[i - 1].timestamp_utc

    print(f"DEBUG: last_gap_ts = {last_gap_ts}")
    if last_gap_ts != -1:
        # We have a warm-up gap. Find the continuous segment after the last gap.
        continuous_bars = [b for b in stored_bars if b.timestamp_utc > last_gap_ts]

        # Truncate dataset to only include the continuous segment
        stored_bars = continuous_bars

    # Create deterministic manifest and verify integrity
    combined_digest = verify_and_digest_continuous_bars(
        stored_bars,
        eval_start_ms,
        timeframe,
        venue,
        outage_registry,
        min_warmup_bars=min_warmup_bars,
    )

    manifest = DatasetManifest(
        dataset_id=f"TREND_PILOT_01_{symbol}_{start_ms}_{end_ms}",
        source=f"{venue}_SOURCE",
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


def verify_and_digest_continuous_bars(
    bars: list[MarketBar],
    eval_start_ms: int,
    timeframe: Timeframe,
    venue: str,
    outage_registry: OutageRegistry | None = None,
    min_warmup_bars: int = 0,
) -> str:
    """
    Verifies that the provided sequence of bars is continuous (with allowed venue outages),
    contains sufficient warm-up, and returns the computed SHA-256 digest.
    """
    if not bars:
        raise ValueError("Cannot verify empty bars sequence.")

    warmup_bars = [b for b in bars if b.timestamp_utc < eval_start_ms]
    if len(warmup_bars) < min_warmup_bars:
        raise ValueError(
            f"Insufficient continuous warm-up bars. Needed {min_warmup_bars}, "
            f"got {len(warmup_bars)}."
        )

    expected_interval = _tf_to_ms(timeframe)

    from obsidian_rl.data.quality import is_forex_weekend_gap

    for i in range(1, len(bars)):
        diff = bars[i].timestamp_utc - bars[i - 1].timestamp_utc
        if diff > expected_interval:
            if "OANDA" in venue and is_forex_weekend_gap(
                bars[i - 1].timestamp_utc, bars[i].timestamp_utc
            ):
                continue
            gap_start = bars[i - 1].timestamp_utc + expected_interval
            gap_end = bars[i].timestamp_utc
            if outage_registry and outage_registry.covers_gap(venue, gap_start, gap_end):
                continue
            raise ValueError(
                f"Unregistered gap found between {bars[i - 1].timestamp_utc} "
                f"and {bars[i].timestamp_utc}"
            )

    row_hashes = [b.row_hash for b in bars]
    h = hashlib.sha256()
    for row_hash in row_hashes:
        h.update(row_hash.encode("utf-8"))
    return h.hexdigest()


def _tf_to_ms(tf: Timeframe) -> int:
    if tf == Timeframe.H4:
        return 4 * 60 * 60 * 1000
    if tf == Timeframe.D1:
        return 24 * 60 * 60 * 1000
    raise ValueError(f"Unsupported tf {tf}")
