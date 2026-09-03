"""Local cross-asset SQLite storage engine for MarketBars, EventNewsItems, and manifests."""

import contextlib
import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from obsidian_rl.data.contracts import (
    SCHEMA_VERSION_V2,
    AssetClass,
    EventNewsItem,
    EventType,
    MarketBar,
    QuoteStatus,
    RevisionStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.fingerprint import verify_contract_hash
from obsidian_rl.data.migrations import run_migrations
from obsidian_rl.data.research_access import validate_temporal_access


class StorageError(Exception):
    """Base exception for all storage engine errors."""


class DuplicateConflictError(StorageError):
    """Raised when record identity exists with a differing hash or incompatible fields."""


class InvalidHashError(StorageError):
    """Raised when a contract hash fails verification prior to storage."""


class UnsupportedSchemaError(StorageError):
    """Raised when an unknown or unsupported schema version is encountered."""


@dataclass(frozen=True)
class IngestionRun:
    """Audit log entry for tracking data ingestion executions."""

    run_id: str
    provider: str
    symbol: str
    timeframe: str
    started_at_utc: int
    completed_at_utc: int | None = None
    status: str = "RUNNING"
    bars_inserted: int = 0
    events_inserted: int = 0
    error_message: str | None = None
    schema_version: str = SCHEMA_VERSION_V2

    def __post_init__(self) -> None:
        if isinstance(self.started_at_utc, bool) or not isinstance(self.started_at_utc, int):
            raise TypeError("started_at_utc must be integer ms UTC")
        if self.schema_version != SCHEMA_VERSION_V2:
            raise UnsupportedSchemaError(f"Unsupported schema version: {self.schema_version}")


@dataclass(frozen=True)
class DatasetManifest:
    """Immutable manifest for validating frozen historical datasets."""

    dataset_id: str
    source: str
    asset_class: AssetClass
    venue: str
    symbol: str
    timeframe: Timeframe
    row_count: int
    start_timestamp_utc: int
    end_timestamp_utc: int
    start_observed_at_utc: int
    end_observed_at_utc: int
    digest: str
    created_at_utc: int
    schema_version: str = SCHEMA_VERSION_V2

    def __post_init__(self) -> None:
        if not isinstance(self.asset_class, AssetClass):
            raise TypeError("asset_class must be an instance of AssetClass enum")
        if not isinstance(self.timeframe, Timeframe):
            raise TypeError("timeframe must be an instance of Timeframe enum")
        for f in (
            "row_count",
            "start_timestamp_utc",
            "end_timestamp_utc",
            "start_observed_at_utc",
            "end_observed_at_utc",
            "created_at_utc",
        ):
            val = getattr(self, f)
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(f"{f} must be integer")
        if self.schema_version != SCHEMA_VERSION_V2:
            raise UnsupportedSchemaError(f"Unsupported schema version: {self.schema_version}")


class SQLiteStorage:
    """Transactional, point-in-time SQLite storage engine for cross-asset market data."""

    def __init__(self, db_path: str | Path | None = ":memory:", wal_mode: bool = True) -> None:
        self.db_path_str = str(db_path) if db_path is not None else ":memory:"
        if self.db_path_str != ":memory:":
            path = Path(self.db_path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path))
            if wal_mode:
                with contextlib.suppress(sqlite3.Error):
                    self.conn.execute("PRAGMA journal_mode = WAL;")
        else:
            self.conn = sqlite3.connect(":memory:")

        self.conn.row_factory = sqlite3.Row
        run_migrations(self.conn)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> "SQLiteStorage":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def insert_market_bars(self, bars: Sequence[MarketBar]) -> int:
        """Insert market bars transactionally with idempotent duplicate skip and conflict checks."""
        if not bars:
            return 0

        inserted_count = 0
        with self.conn:
            cursor = self.conn.cursor()
            for bar in bars:
                if bar.schema_version != SCHEMA_VERSION_V2:
                    raise UnsupportedSchemaError(
                        f"MarketBar schema version {bar.schema_version!r} not supported"
                    )
                try:
                    verify_contract_hash(bar)
                except RuntimeError as exc:
                    raise InvalidHashError(
                        f"MarketBar row_hash verification failed: {exc}"
                    ) from exc

                # Check identity match
                cursor.execute(
                    """
                    SELECT row_hash FROM market_bars
                    WHERE asset_class = ? AND venue = ? AND symbol = ?
                      AND timeframe = ? AND timestamp_utc = ? AND data_source = ?
                    """,
                    (
                        bar.asset_class.value,
                        bar.venue,
                        bar.symbol,
                        bar.timeframe.value,
                        bar.timestamp_utc,
                        bar.data_source,
                    ),
                )
                identity_row = cursor.fetchone()
                if identity_row is not None:
                    if identity_row["row_hash"] == bar.row_hash:
                        # Idempotent duplicate: identical hash -> ignore safely
                        continue
                    else:
                        raise DuplicateConflictError(
                            f"Conflict detected for MarketBar identity ({bar.symbol}, "
                            f"{bar.timeframe}, {bar.timestamp_utc}): stored hash "
                            f"{identity_row['row_hash']} != new hash {bar.row_hash}"
                        )

                # Check hash conflict with different identity
                cursor.execute(
                    "SELECT timestamp_utc FROM market_bars WHERE row_hash = ?", (bar.row_hash,)
                )
                hash_row = cursor.fetchone()
                if hash_row is not None:
                    raise DuplicateConflictError(
                        f"Conflict detected: row_hash {bar.row_hash} already exists in storage"
                    )

                cursor.execute(
                    """
                    INSERT INTO market_bars (
                        asset_class, venue, symbol, timeframe, timestamp_utc, observed_at_utc,
                        open, high, low, close, quote_status, bid, ask, volume_type, volume,
                        data_source, schema_version, row_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bar.asset_class.value,
                        bar.venue,
                        bar.symbol,
                        bar.timeframe.value,
                        bar.timestamp_utc,
                        bar.observed_at_utc,
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.quote_status.value,
                        bar.bid,
                        bar.ask,
                        bar.volume_type.value,
                        bar.volume,
                        bar.data_source,
                        bar.schema_version,
                        bar.row_hash,
                    ),
                )
                inserted_count += 1

        return inserted_count

    def insert_event_news_items(self, items: Sequence[EventNewsItem]) -> int:
        """Insert event news items transactionally with idempotent skip and conflict checks."""
        if not items:
            return 0

        inserted_count = 0
        with self.conn:
            cursor = self.conn.cursor()
            for item in items:
                if item.schema_version != SCHEMA_VERSION_V2:
                    raise UnsupportedSchemaError(
                        f"EventNewsItem schema version {item.schema_version!r} not supported"
                    )
                try:
                    verify_contract_hash(item)
                except RuntimeError as exc:
                    raise InvalidHashError(
                        f"EventNewsItem record_hash verification failed: {exc}"
                    ) from exc

                cursor.execute(
                    """
                    SELECT record_hash FROM event_news_items
                    WHERE event_id = ? AND source = ? AND original_published_at = ?
                      AND revision_status = ?
                    """,
                    (
                        item.event_id,
                        item.source,
                        item.original_published_at,
                        item.revision_status.value,
                    ),
                )
                identity_row = cursor.fetchone()
                if identity_row is not None:
                    if identity_row["record_hash"] == item.record_hash:
                        continue
                    else:
                        raise DuplicateConflictError(
                            f"Conflict detected for EventNewsItem identity ({item.event_id}, "
                            f"{item.source}, {item.revision_status}): stored hash "
                            f"{identity_row['record_hash']} != new hash {item.record_hash}"
                        )

                cursor.execute(
                    "SELECT event_id FROM event_news_items WHERE record_hash = ?",
                    (item.record_hash,),
                )
                hash_row = cursor.fetchone()
                if hash_row is not None:
                    raise DuplicateConflictError(
                        f"Conflict detected: record_hash {item.record_hash} "
                        "already exists in storage"
                    )

                cursor.execute(
                    """
                    INSERT INTO event_news_items (
                        event_id, source, source_reliability, original_published_at,
                        first_observed_at, updated_at, affected_assets, event_type,
                        expected_value, actual_value, surprise_value, raw_content_hash,
                        sentiment_score, revision_status, schema_version, record_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.event_id,
                        item.source,
                        item.source_reliability,
                        item.original_published_at,
                        item.first_observed_at,
                        item.updated_at,
                        json.dumps(item.affected_assets),
                        item.event_type.value,
                        item.expected_value,
                        item.actual_value,
                        item.surprise_value,
                        item.raw_content_hash,
                        item.sentiment_score,
                        item.revision_status.value,
                        item.schema_version,
                        item.record_hash,
                    ),
                )
                inserted_count += 1

        return inserted_count

    def query_market_bars(
        self,
        asset_class: AssetClass | str,
        venue: str,
        symbol: str,
        timeframe: Timeframe | str,
        start_timestamp_utc: int,
        end_timestamp_utc: int,
        observed_before_ms: int | None = None,
    ) -> list[MarketBar]:
        """Query market bars with point-in-time filtering and chronological ordering."""
        if isinstance(start_timestamp_utc, bool) or not isinstance(start_timestamp_utc, int):
            raise TypeError("start_timestamp_utc must be integer ms UTC")
        if isinstance(end_timestamp_utc, bool) or not isinstance(end_timestamp_utc, int):
            raise TypeError("end_timestamp_utc must be integer ms UTC")
        if observed_before_ms is not None and (
            isinstance(observed_before_ms, bool) or not isinstance(observed_before_ms, int)
        ):
            raise TypeError("observed_before_ms must be integer ms UTC")

        # Cycle 2 research temporal access guard
        validate_temporal_access(start_timestamp_utc, end_timestamp_utc)

        ac_str = asset_class.value if isinstance(asset_class, AssetClass) else str(asset_class)
        tf_str = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)

        query = """
            SELECT asset_class, venue, symbol, timeframe, timestamp_utc, observed_at_utc,
                   open, high, low, close, quote_status, bid, ask, volume_type, volume,
                   data_source, schema_version, row_hash
            FROM market_bars
            WHERE asset_class = ? AND venue = ? AND symbol = ? AND timeframe = ?
              AND timestamp_utc >= ? AND timestamp_utc < ?
        """
        params: list[Any] = [ac_str, venue, symbol, tf_str, start_timestamp_utc, end_timestamp_utc]

        if observed_before_ms is not None:
            query += " AND observed_at_utc <= ?"
            params.append(observed_before_ms)

        query += " ORDER BY timestamp_utc ASC"

        cursor = self.conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        results: list[MarketBar] = []
        for row in rows:
            results.append(
                MarketBar(
                    asset_class=AssetClass(row["asset_class"]),
                    venue=row["venue"],
                    symbol=row["symbol"],
                    timeframe=Timeframe(row["timeframe"]),
                    timestamp_utc=row["timestamp_utc"],
                    observed_at_utc=row["observed_at_utc"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    quote_status=QuoteStatus(row["quote_status"]),
                    bid=row["bid"],
                    ask=row["ask"],
                    volume_type=VolumeType(row["volume_type"]),
                    volume=row["volume"],
                    data_source=row["data_source"],
                    schema_version=row["schema_version"],
                    row_hash=row["row_hash"],
                )
            )

        return results

    def query_event_news_items(
        self,
        event_id: str | None = None,
        source: str | None = None,
        start_timestamp_utc: int | None = None,
        end_timestamp_utc: int | None = None,
        observed_before_ms: int | None = None,
    ) -> list[EventNewsItem]:
        """Query event news items with optional filtering and point-in-time cutoff."""
        query = """
            SELECT event_id, source, source_reliability, original_published_at,
                   first_observed_at, updated_at, affected_assets, event_type,
                   expected_value, actual_value, surprise_value, raw_content_hash,
                   sentiment_score, revision_status, schema_version, record_hash
            FROM event_news_items
            WHERE 1=1
        """
        params: list[Any] = []

        if event_id is not None:
            query += " AND event_id = ?"
            params.append(event_id)
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if start_timestamp_utc is not None:
            query += " AND original_published_at >= ?"
            params.append(start_timestamp_utc)
        if end_timestamp_utc is not None:
            query += " AND original_published_at < ?"
            params.append(end_timestamp_utc)
        if observed_before_ms is not None:
            query += " AND first_observed_at <= ?"
            params.append(observed_before_ms)

        query += " ORDER BY original_published_at ASC"

        cursor = self.conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        results: list[EventNewsItem] = []
        for row in rows:
            results.append(
                EventNewsItem(
                    event_id=row["event_id"],
                    source=row["source"],
                    source_reliability=row["source_reliability"],
                    original_published_at=row["original_published_at"],
                    first_observed_at=row["first_observed_at"],
                    updated_at=row["updated_at"],
                    affected_assets=tuple(json.loads(row["affected_assets"])),
                    event_type=EventType(row["event_type"]),
                    expected_value=row["expected_value"],
                    actual_value=row["actual_value"],
                    surprise_value=row["surprise_value"],
                    raw_content_hash=row["raw_content_hash"],
                    sentiment_score=row["sentiment_score"],
                    revision_status=RevisionStatus(row["revision_status"]),
                    schema_version=row["schema_version"],
                    record_hash=row["record_hash"],
                )
            )

        return results

    def create_dataset_manifest(
        self,
        dataset_id: str,
        source: str,
        asset_class: AssetClass | str,
        venue: str,
        symbol: str,
        timeframe: Timeframe | str,
        bars: Sequence[MarketBar],
        created_at_utc: int,
    ) -> DatasetManifest:
        """Construct a deterministic dataset manifest from an ordered list of bars."""
        if not bars:
            raise ValueError("Cannot create DatasetManifest from empty bar sequence")
        if isinstance(created_at_utc, bool) or not isinstance(created_at_utc, int):
            raise TypeError("created_at_utc must be integer ms UTC")

        ac_enum = (
            asset_class if isinstance(asset_class, AssetClass) else AssetClass(str(asset_class))
        )
        tf_enum = timeframe if isinstance(timeframe, Timeframe) else Timeframe(str(timeframe))

        sorted_bars = sorted(bars, key=lambda b: b.timestamp_utc)
        ordered_hashes = "".join(b.row_hash for b in sorted_bars)
        digest = hashlib.sha256(ordered_hashes.encode("utf-8")).hexdigest()

        return DatasetManifest(
            dataset_id=dataset_id,
            source=source,
            asset_class=ac_enum,
            venue=venue,
            symbol=symbol,
            timeframe=tf_enum,
            row_count=len(sorted_bars),
            start_timestamp_utc=sorted_bars[0].timestamp_utc,
            end_timestamp_utc=sorted_bars[-1].timestamp_utc,
            start_observed_at_utc=min(b.observed_at_utc for b in sorted_bars),
            end_observed_at_utc=max(b.observed_at_utc for b in sorted_bars),
            digest=digest,
            created_at_utc=created_at_utc,
            schema_version=SCHEMA_VERSION_V2,
        )

    def save_dataset_manifest(self, manifest: DatasetManifest) -> None:
        """Store or replace a dataset manifest record."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO dataset_manifests (
                    dataset_id, source, asset_class, venue, symbol, timeframe,
                    row_count, start_timestamp_utc, end_timestamp_utc,
                    start_observed_at_utc, end_observed_at_utc, digest,
                    schema_version, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.dataset_id,
                    manifest.source,
                    manifest.asset_class.value,
                    manifest.venue,
                    manifest.symbol,
                    manifest.timeframe.value,
                    manifest.row_count,
                    manifest.start_timestamp_utc,
                    manifest.end_timestamp_utc,
                    manifest.start_observed_at_utc,
                    manifest.end_observed_at_utc,
                    manifest.digest,
                    manifest.schema_version,
                    manifest.created_at_utc,
                ),
            )

    def get_dataset_manifest(self, dataset_id: str) -> DatasetManifest | None:
        """Retrieve a stored dataset manifest by dataset_id."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM dataset_manifests WHERE dataset_id = ?", (dataset_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        return DatasetManifest(
            dataset_id=row["dataset_id"],
            source=row["source"],
            asset_class=AssetClass(row["asset_class"]),
            venue=row["venue"],
            symbol=row["symbol"],
            timeframe=Timeframe(row["timeframe"]),
            row_count=row["row_count"],
            start_timestamp_utc=row["start_timestamp_utc"],
            end_timestamp_utc=row["end_timestamp_utc"],
            start_observed_at_utc=row["start_observed_at_utc"],
            end_observed_at_utc=row["end_observed_at_utc"],
            digest=row["digest"],
            created_at_utc=row["created_at_utc"],
            schema_version=row["schema_version"],
        )

    def record_ingestion_run(self, run: IngestionRun) -> None:
        """Record an ingestion run entry."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ingestion_runs (
                    run_id, provider, symbol, timeframe, started_at_utc,
                    completed_at_utc, status, bars_inserted, events_inserted,
                    error_message, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.provider,
                    run.symbol,
                    run.timeframe,
                    run.started_at_utc,
                    run.completed_at_utc,
                    run.status,
                    run.bars_inserted,
                    run.events_inserted,
                    run.error_message,
                    run.schema_version,
                ),
            )

    def get_ingestion_run(self, run_id: str) -> IngestionRun | None:
        """Retrieve an ingestion run audit entry by run_id."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ingestion_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        return IngestionRun(
            run_id=row["run_id"],
            provider=row["provider"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            started_at_utc=row["started_at_utc"],
            completed_at_utc=row["completed_at_utc"],
            status=row["status"],
            bars_inserted=row["bars_inserted"],
            events_inserted=row["events_inserted"],
            error_message=row["error_message"],
            schema_version=row["schema_version"],
        )
