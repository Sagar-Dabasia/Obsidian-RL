"""Provider-to-storage market data ingestion pipeline."""

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from obsidian_rl.data.contracts import Timeframe
from obsidian_rl.data.providers.base import MarketDataProvider
from obsidian_rl.data.providers.binance import BinanceSpotProvider
from obsidian_rl.data.providers.oanda import OandaPracticeProvider
from obsidian_rl.data.quality import (
    ForexSessionConfig,
    timeframe_to_ms,
    validate_market_bars,
)
from obsidian_rl.data.storage import (
    DuplicateConflictError,
    IngestionRun,
    SQLiteStorage,
    StorageError,
)


@dataclass(frozen=True)
class IngestionResult:
    """Immutable result from a provider market-data ingestion run."""

    provider: str
    symbol: str
    timeframe: str
    requested_bars: int
    fetched_bars: int
    rows_inserted: int
    duplicates_ignored: int
    quality_status: str
    manifest_id: str | None
    ingestion_run_id: str
    dry_run: bool
    final_status: str


def ingest_provider_market_data(
    provider_name: str,
    symbol: str,
    timeframe: Timeframe | str,
    bars: int,
    db_path: str | Path,
    is_live: bool = False,
    is_write: bool = False,
    forex_session_config: ForexSessionConfig | None = None,
    api_token: str | None = None,
    current_time_ms: int | None = None,
) -> IngestionResult:
    """Fetch, validate, and securely store market data from a provider."""
    run_id = f"run_{uuid.uuid4().hex}"

    if isinstance(timeframe, str):
        timeframe = Timeframe(timeframe)

    tf_str = timeframe.value
    provider_name = provider_name.upper()

    if current_time_ms is None:
        current_time_ms = int(time.time() * 1000)

    # Initialize provider
    provider: MarketDataProvider
    if provider_name == "BINANCE":
        provider = BinanceSpotProvider()
    elif provider_name == "OANDA":
        provider = OandaPracticeProvider(api_token=api_token)
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")

    if bars <= 0 or bars > 20:
        raise ValueError(f"Invalid bars count: {bars}. Must be between 1 and 20.")

    # Calculate time window
    step_ms = timeframe_to_ms(timeframe)
    end_ms = current_time_ms - (current_time_ms % step_ms)
    start_ms = end_ms - (bars * step_ms)

    # 1. Fetch data
    if not is_live:
        raise ValueError("--live is required before any network calls are allowed.")

    try:
        if provider_name == "OANDA":
            collected_bars: list = []
            current_end = end_ms
            missing = bars
            attempts = 0
            # 5 attempts with 3 days padding covers ~15 days gaps
            while missing > 0 and attempts < 5:
                # Add 3 days padding each attempt to jump over weekends
                lookback = (missing * step_ms) + 259_200_000
                current_start = current_end - lookback

                chunk = provider.fetch_bars(
                    symbol=symbol, timeframe=timeframe, start_ms=current_start, end_ms=current_end
                )

                if chunk:
                    collected_bars = list(chunk) + collected_bars

                missing = bars - len(collected_bars)
                current_end = current_start
                attempts += 1

            fetched_bars_tuple = tuple(collected_bars[-bars:])
        else:
            # Crypto behaves identically
            start_ms = end_ms - (bars * step_ms)
            fetched_bars_tuple = provider.fetch_bars(
                symbol=symbol, timeframe=timeframe, start_ms=start_ms, end_ms=end_ms
            )
    except Exception as exc:
        # Wrap safely without exposing secrets
        # Providers already scrub secrets from ProviderError
        raise RuntimeError(f"Provider fetch failed: {exc}") from exc

    fetched_count = len(fetched_bars_tuple)

    # 2. Point-in-time protection check
    for b in fetched_bars_tuple:
        if b.observed_at_utc > current_time_ms:
            raise ValueError(
                f"Observation time {b.observed_at_utc} is in the future relative to "
                f"current ingestion time {current_time_ms}."
            )

    # 3. Quality Validation
    report = validate_market_bars(
        bars=fetched_bars_tuple,
        expected_timeframe=timeframe,
        expected_symbol=symbol,
        is_forex=(provider_name == "OANDA"),
        forex_session_config=forex_session_config,
    )

    quality_status = "PASSED" if report.passed else "FAILED"

    if not is_write:
        # Dry Run Preview
        preview_manifest_id = None
        if report.passed and fetched_count > 0:
            preview_manifest_id = f"dry_manifest_{uuid.uuid4().hex}"

        return IngestionResult(
            provider=provider_name,
            symbol=symbol,
            timeframe=tf_str,
            requested_bars=bars,
            fetched_bars=fetched_count,
            rows_inserted=0,
            duplicates_ignored=0,
            quality_status=quality_status,
            manifest_id=preview_manifest_id,
            ingestion_run_id=run_id,
            dry_run=True,
            final_status="SUCCESS_DRY_RUN" if report.passed else "FAILED_QUALITY_DRY_RUN",
        )

    # 4. Write Mode (Transactional)
    if not report.passed:
        final_status = "FAILED_QUALITY"
        _record_failed_run(
            run_id,
            provider_name,
            symbol,
            tf_str,
            current_time_ms,
            db_path,
            "Quality validation failed",
        )
        return IngestionResult(
            provider=provider_name,
            symbol=symbol,
            timeframe=tf_str,
            requested_bars=bars,
            fetched_bars=fetched_count,
            rows_inserted=0,
            duplicates_ignored=0,
            quality_status=quality_status,
            manifest_id=None,
            ingestion_run_id=run_id,
            dry_run=False,
            final_status=final_status,
        )

    if fetched_count == 0:
        _record_success_run(run_id, provider_name, symbol, tf_str, current_time_ms, db_path, 0)
        return IngestionResult(
            provider=provider_name,
            symbol=symbol,
            timeframe=tf_str,
            requested_bars=bars,
            fetched_bars=0,
            rows_inserted=0,
            duplicates_ignored=0,
            quality_status=quality_status,
            manifest_id=None,
            ingestion_run_id=run_id,
            dry_run=False,
            final_status="SUCCESS_EMPTY",
        )

    # Perform the transaction
    storage = SQLiteStorage(db_path=db_path)
    try:
        inserted_count = 0
        duplicates_ignored = 0
        dataset_id = f"manifest_{uuid.uuid4().hex}"

        with storage.conn:
            inserted_count = storage.insert_market_bars(fetched_bars_tuple)
            duplicates_ignored = fetched_count - inserted_count

            manifest = storage.create_dataset_manifest(
                dataset_id=dataset_id,
                source=provider_name,
                asset_class=fetched_bars_tuple[0].asset_class,
                venue=fetched_bars_tuple[0].venue,
                symbol=symbol,
                timeframe=timeframe,
                bars=fetched_bars_tuple,
                created_at_utc=current_time_ms,
            )
            storage.save_dataset_manifest(manifest)

            run = IngestionRun(
                run_id=run_id,
                provider=provider_name,
                symbol=symbol,
                timeframe=tf_str,
                started_at_utc=current_time_ms,
                completed_at_utc=current_time_ms,
                status="SUCCESS",
                bars_inserted=inserted_count,
            )
            storage.record_ingestion_run(run)

        return IngestionResult(
            provider=provider_name,
            symbol=symbol,
            timeframe=tf_str,
            requested_bars=bars,
            fetched_bars=fetched_count,
            rows_inserted=inserted_count,
            duplicates_ignored=duplicates_ignored,
            quality_status=quality_status,
            manifest_id=dataset_id,
            ingestion_run_id=run_id,
            dry_run=False,
            final_status="SUCCESS",
        )

    except DuplicateConflictError as exc:
        _record_failed_run(
            run_id,
            provider_name,
            symbol,
            tf_str,
            current_time_ms,
            db_path,
            f"Duplicate conflict: {exc}",
        )
        raise
    except StorageError as exc:
        _record_failed_run(
            run_id, provider_name, symbol, tf_str, current_time_ms, db_path, f"Storage error: {exc}"
        )
        raise
    except Exception:
        _record_failed_run(
            run_id,
            provider_name,
            symbol,
            tf_str,
            current_time_ms,
            db_path,
            "Unknown transaction error",
        )
        raise
    finally:
        storage.close()


def _record_failed_run(
    run_id: str,
    provider: str,
    symbol: str,
    timeframe: str,
    started_at_utc: int,
    db_path: str | Path,
    error_msg: str,
) -> None:
    try:
        storage = SQLiteStorage(db_path=db_path)
        run = IngestionRun(
            run_id=run_id,
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            started_at_utc=started_at_utc,
            completed_at_utc=int(time.time() * 1000),
            status="FAILED",
            error_message=error_msg,
        )
        storage.record_ingestion_run(run)
        storage.close()
    except Exception:
        pass


def _record_success_run(
    run_id: str,
    provider: str,
    symbol: str,
    timeframe: str,
    started_at_utc: int,
    db_path: str | Path,
    inserted_count: int,
) -> None:
    try:
        storage = SQLiteStorage(db_path=db_path)
        run = IngestionRun(
            run_id=run_id,
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            started_at_utc=started_at_utc,
            completed_at_utc=int(time.time() * 1000),
            status="SUCCESS",
            bars_inserted=inserted_count,
        )
        storage.record_ingestion_run(run)
        storage.close()
    except Exception:
        pass
