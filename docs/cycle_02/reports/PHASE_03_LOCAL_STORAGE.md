# Cycle 02 Phase 3: Local Cross-Asset Data Storage & Quality Validation Report

**Date:** 2026-07-23  
**Status:** COMPLETE (PASSED COMPLIANCE AUDIT)  
**Branch:** `feature/cycle-02-local-data-store`  
**Schema Version:** `SCHEMA_V2`  

---

## 1. Executive Summary

Phase 3 implements local cross-asset data storage, point-in-time access filters, comprehensive data-quality inspection pipelines, and deterministic dataset manifests for Obsidian-RL Research Cycle 02.

**Governance & Compliance Confirmations:**
- **100% Free Local Engine:** Built exclusively using Python standard-library SQLite (`sqlite3`). No paid databases, cloud storage, or commercial APIs were used.
- **Zero Market Data Downloaded:** All testing and verification were performed locally using synthetic fixtures and deterministic test matrices.
- **Zero Holdout Access:** Out-of-sample datasets and confirmation models were not accessed.
- **Zero Trading Executed:** No paper or real exchange orders were placed.
- **Zero Credentials Stored:** Database schemas and audit logs contain zero credential fields or secret parameters.

---

## 2. Schema & Storage Engine Design (`src/obsidian_rl/data/storage.py`, `migrations.py`)

### Database Tables & Identity Rules
The storage engine manages persistence across four core tables:

1. **`market_bars` Table**
   - Stores `MarketBar` records across asset classes (`CRYPTO`, `FOREX`, `EQUITY`, `COMMODITY`).
   - **Identity Constraint:** `UNIQUE (asset_class, venue, symbol, timeframe, timestamp_utc, data_source)`
   - **Primary Key:** `row_hash` (64-character lowercase hex SHA-256 digest).
   - **Performance Index:** `idx_market_bars_query` on `(asset_class, venue, symbol, timeframe, timestamp_utc, observed_at_utc)`.

2. **`event_news_items` Table**
   - Stores `EventNewsItem` economic releases and news events.
   - **Identity Constraint:** `UNIQUE (event_id, source, original_published_at, revision_status)`
   - **Primary Key:** `record_hash` (64-character lowercase hex SHA-256 digest).
   - **Performance Index:** `idx_event_news_query` on `(event_id, source, original_published_at, first_observed_at)`.

3. **`ingestion_runs` Table**
   - Audit tracking for batch ingestion jobs (`run_id`, `provider`, `symbol`, `timeframe`, `started_at_utc`, `completed_at_utc`, `status`, `bars_inserted`, `events_inserted`, `error_message`).

4. **`dataset_manifests` Table**
   - Persistence for deterministic historical dataset manifests (`dataset_id`, `source`, `asset_class`, `venue`, `symbol`, `timeframe`, `row_count`, `start_timestamp_utc`, `end_timestamp_utc`, `start_observed_at_utc`, `end_observed_at_utc`, `digest`, `created_at_utc`).

### Storage Engine Invariants
- **Idempotent Insertion:** Duplicate records with an identical hash are ignored safely (returning `0` inserted rows).
- **Conflict Rejection:** Records matching a stored identity with a differing hash raise `DuplicateConflictError`.
- **Pre-Insertion Hash Verification:** Supplied contract hashes (`row_hash` / `record_hash`) are verified prior to insertion; tampered records raise `InvalidHashError`.
- **Transactional Rollback:** Batch writes execute inside atomic transactions (`with self.conn:`); any failure rolls back the entire batch.
- **WAL & Storage Support:** File-based databases enable WAL journal mode (`PRAGMA journal_mode = WAL;`) and safely create parent directories. In-memory databases (`:memory:`) are supported for isolated testing.

---

## 3. Point-in-Time Access Protections

Historical queries (`query_market_bars`, `query_event_news_items`) enforce strict point-in-time discipline:
- **Boundaries:** `start_timestamp_utc` is inclusive (`>=`), `end_timestamp_utc` is exclusive (`<`).
- **Ordering:** Queries strictly enforce chronological order (`ORDER BY timestamp_utc ASC`).
- **Look-Ahead Prevention:** Queries accept an optional `observed_before_ms` cutoff parameter (`observed_at_utc <= observed_before_ms`).
  - *Example:* A bar with `timestamp_utc = 12:00` and `observed_at_utc = 12:01` is excluded from any replay query executed at `observed_before_ms = 12:00:30`.

---

## 4. Data-Quality Validation Pipeline (`src/obsidian_rl/data/quality.py`)

`validate_market_bars` inspects bar series and produces a structured `DataQualityReport`:
- **Timestamp Monotonicity:** Flags duplicate timestamps (`duplicates`) and out-of-order series (`unexpected_intervals`).
- **Gap Detection:** Calculates expected bar spacing (`step_ms` via `timeframe_to_ms`) and records missing intervals (`missing_intervals`).
- **Forex Weekend Awareness:** `is_forex_weekend_gap` identifies standard Friday 21:00 UTC to Sunday 21:00 UTC market closures for Forex series and excludes them from missing data flags.
- **Cryptographic Hash Validation:** Verifies SHA-256 hashes for every bar (`hash_failures`).
- **Observation Time Verification:** Flags look-ahead violations where `observed_at_utc < timestamp_utc` (`observation_failures`).
- **OHLC & Quote Invariants:** Enforces strictly positive prices and valid `bid`/`ask` quote ordering.
- **No Automatic Filling:** Missing candles are explicitly reported without synthetic interpolation or automatic filling.

---

## 5. Deterministic Dataset Manifests

`create_dataset_manifest` generates reproducible manifests for dataset freezing:
- **Ordered Hash Digest:** Computes `digest = sha256("".join(b.row_hash for b in sorted_bars))` over chronologically sorted bars.
- **Wall-Clock Independence:** Requires `created_at_utc` to be supplied explicitly by the caller, eliminating internal wall-clock calls.

---

## 6. Verification & Test Execution Results

All automated code compilation, type checking, linting, and test suites passed cleanly:

- **Data Package Tests (`pytest tests/data -q`):** `65 passed in 0.44s`
- **Full Project Test Suite (`pytest -q`):** `483 passed, 1 skipped in 10.42s`
- **Python Compilation (`compileall -q src tests`):** Clean exit code `0`
- **Mypy Static Type Checking:** `Success: no issues found in 26 source files`
- **Ruff Linter Check:** `All checks passed!`
- **Ruff Format Check:** `26 files already formatted`
- **Git Diff Check (`git diff --check`):** Clean

---

## 7. Summary Compliance Matrix

| Requirement | Implementation | Status |
| :--- | :--- | :--- |
| **Engine Engine** | Python standard-library `sqlite3` only | **PASS** |
| **Transactional Writes** | Atomic `with self.conn:` with rollback | **PASS** |
| **Idempotent Insertion** | Identical hash duplicate skip | **PASS** |
| **Conflict Detection** | Differing hash raises `DuplicateConflictError` | **PASS** |
| **Hash Verification** | Pre-write validation raises `InvalidHashError` | **PASS** |
| **Point-in-Time Cutoff** | `observed_before_ms` look-ahead prevention | **PASS** |
| **Data Quality Pipeline** | `DataQualityReport` with gap & timestamp checks | **PASS** |
| **Forex Weekend Gaps** | `is_forex_weekend_gap` closure handling | **PASS** |
| **Deterministic Manifest** | Caller-supplied creation timestamp & SHA-256 digest | **PASS** |
| **Zero Credentials** | No secret fields in schema | **PASS** |
