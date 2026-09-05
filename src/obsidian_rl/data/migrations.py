"""Database schema definitions and migration scripts for SQLite storage."""

import sqlite3
from typing import Final

SCHEMA_VERSION_V2: Final[str] = "SCHEMA_V2"

CREATE_MARKET_BARS_TABLE = """
CREATE TABLE IF NOT EXISTS market_bars (
    asset_class TEXT NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp_utc INTEGER NOT NULL,
    observed_at_utc INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    quote_status TEXT NOT NULL,
    bid REAL,
    ask REAL,
    volume_type TEXT NOT NULL,
    volume REAL,
    data_source TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    row_hash TEXT PRIMARY KEY NOT NULL,
    UNIQUE (asset_class, venue, symbol, timeframe, timestamp_utc, data_source)
);
"""

CREATE_MARKET_BARS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_market_bars_query
ON market_bars (asset_class, venue, symbol, timeframe, timestamp_utc, observed_at_utc);
"""

CREATE_EVENT_NEWS_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS event_news_items (
    event_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_reliability REAL NOT NULL,
    original_published_at INTEGER NOT NULL,
    first_observed_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    affected_assets TEXT NOT NULL,
    event_type TEXT NOT NULL,
    expected_value REAL,
    actual_value REAL,
    surprise_value REAL,
    raw_content_hash TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    revision_status TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    record_hash TEXT PRIMARY KEY NOT NULL,
    UNIQUE (event_id, source, original_published_at, revision_status)
);
"""

CREATE_EVENT_NEWS_ITEMS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_event_news_query
ON event_news_items (event_id, source, original_published_at, first_observed_at);
"""

CREATE_INGESTION_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    started_at_utc INTEGER NOT NULL,
    completed_at_utc INTEGER,
    status TEXT NOT NULL,
    bars_inserted INTEGER NOT NULL DEFAULT 0,
    events_inserted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    schema_version TEXT NOT NULL
);
"""

CREATE_DATASET_MANIFESTS_TABLE = """
CREATE TABLE IF NOT EXISTS dataset_manifests (
    dataset_id TEXT PRIMARY KEY NOT NULL,
    source TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    start_timestamp_utc INTEGER NOT NULL,
    end_timestamp_utc INTEGER NOT NULL,
    start_observed_at_utc INTEGER NOT NULL,
    end_observed_at_utc INTEGER NOT NULL,
    digest TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at_utc INTEGER NOT NULL
);
"""

CREATE_FUNDING_RATES_TABLE = """
CREATE TABLE IF NOT EXISTS funding_rates (
    asset_class TEXT NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp_utc INTEGER NOT NULL,
    observed_at_utc INTEGER NOT NULL,
    rate REAL NOT NULL,
    data_source TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    row_hash TEXT PRIMARY KEY NOT NULL,
    UNIQUE (asset_class, venue, symbol, timestamp_utc, data_source)
);
"""

CREATE_FUNDING_RATES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_funding_rates_query
ON funding_rates (asset_class, venue, symbol, timestamp_utc, observed_at_utc);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    """Initialize database schema idempotently and configure pragmas."""
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.execute(CREATE_MARKET_BARS_TABLE)
        conn.execute(CREATE_MARKET_BARS_INDEX)
        conn.execute(CREATE_EVENT_NEWS_ITEMS_TABLE)
        conn.execute(CREATE_EVENT_NEWS_ITEMS_INDEX)
        conn.execute(CREATE_INGESTION_RUNS_TABLE)
        conn.execute(CREATE_DATASET_MANIFESTS_TABLE)
        conn.execute(CREATE_FUNDING_RATES_TABLE)
        conn.execute(CREATE_FUNDING_RATES_INDEX)
