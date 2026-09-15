# Phase 03B: Provider-to-Storage Ingestion Pipeline

## Objective
Implement a pipeline that fetches market data from network providers and inserts it into local SQLite storage, with full integration of data-quality checks, transactional persistence, and detailed auditing.

## Implementation Details

### Pipeline (`src/obsidian_rl/data/ingestion.py`)
- Created `ingest_provider_market_data()` orchestrator function mapping user inputs to provider calls and storage procedures.
- Integrated `validate_market_bars()` from the quality module immediately after network fetches.
- Established a transactional write model mapping validated `fetched_bars_tuple` to row insertions.
- Automated creation of `DatasetManifest` logs mapping data back to the `ingestion_run_id`.
- Handled point-in-time constraints (rejected bars with `observed_at_utc` in the future relative to the current invocation time).

### CLI (`tools/ingest_market_data.py`)
- Created Python executable script with `argparse`.
- Added required strict explicit safety checks:
  - `--live`: Defaults to False. If not provided, network execution is aborted.
  - `--write`: Defaults to False. If not provided, database execution is aborted and only a memory preview/manifest is shown (`dry_run=True`).
- Secure CLI error handling implemented to use `scrub_secrets` on output preventing accidental exposure of tokens if stack traces escape.

### Verification (`tests/data/test_ingestion.py`)
- Built extensive offline tests mocking provider interfaces.
- Included edge-case checking (idempotent writes ignoring duplicates, bad-data abortion preventing database insertions, point-in-time validation).
- Live validation successfully carried out against both Binance (`BTCUSDT`, 4h) and OANDA (`EUR_USD`, 4h) storing locally into `.gitignore` protected paths.

## Live Smoke Test Validation

| Provider | Symbol | Timeframe | Requested Bars | Fetched Bars | Result | Quality Status | Rows Inserted |
|---|---|---|---|---|---|---|---|
| BINANCE | BTCUSDT | 4h | 5 | 5 | SUCCESS | PASSED | 5 |
| OANDA | EUR_USD | 4h | 5 | 5 | SUCCESS | PASSED | 5 |

*Note: OANDA dynamically expanded its backward lookback across the Forex weekend market gap to successfully return the requested 5 completed candles, which were cleanly validated by `ForexSessionConfig`.*

## Status
- **Success**: Code written, validated by mypy/ruff/pytest, and successfully run live without errors.
- **Git Protections**: `.db` and `data/` are firmly inside `.gitignore` from project conception.

No holdouts accessed. No paper or live trades placed. No cloud databases utilized.
