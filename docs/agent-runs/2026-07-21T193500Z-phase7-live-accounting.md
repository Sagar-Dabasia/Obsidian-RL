# Agent Run Report — Phase 7: Live-Paper Funding, Run Metadata & Durable Failure Evidence

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase7-live-accounting` |
| **Starting commit** | `33911ac61821ed884e43d8bb1b03016682067a00` |
| **Task** | Implement Phase 7 live-paper funding events, strict authoritative run configuration & metadata binding, funding event accounting with idempotency and state restoration, replay/backtest funding parity, and durable sanitized failure event logging. |

---

## Working-tree status

```
M  src/obsidian_rl/data/binance_client.py
M  src/obsidian_rl/ledger/ledger.py
M  src/obsidian_rl/live/paper_trader.py
M  src/obsidian_rl/live/runner.py
A  tests/test_live_accounting.py
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
A  docs/agent-runs/2026-07-21T193500Z-phase7-live-accounting.md
```

---

## Fixes & Implementation

### 1. Authoritative Run Configuration (`config.py`, `ledger.py`, `runner.py`)
- Created single validated `PortfolioConfig` and `CostModel` instances in `LivePaperRunner` and passed identical instances to `Ledger.start_run` and `PaperTrader`.
- Persisted canonical, strict run metadata in `runs` (`cost_model_json` and `config_json`) using sorted compact JSON with `allow_nan=False`.
- Validated inputs against `bool` types, `NaN`, `Infinity`, missing/extra fields, and invalid numerical ranges.
- Added strict resume verification: when resuming an existing run, verified that requested configuration matches stored metadata, and rejected legacy/incomplete cost metadata.

### 2. Funding-Event Accounting (`binance_client.py`, `ledger.py`, `paper_trader.py`)
- Added public funding rate retrieval support to `BinanceFuturesRest` (`GET /fapi/v1/fundingRate`).
- Added `funding_events` table to `Ledger` schema with index on `(run_id, funding_time_ms)` and `idempotency_key`.
- Implemented `record_funding` with exact idempotency verification: identical key and data returns `False`, while key reuse with changed fields raises `EventConflictError`.
- Updated `PaperTrader.apply_funding_event` to apply cash flows matching `PortfolioEngine.apply_funding` (positive rate: long pays, short receives; negative rate: long receives, short pays; flat: 0 flow) without creating trades or strategy decisions.
- Transaction safety: on persistence failure in `apply_funding_event`, the pre-funding `PortfolioState` is atomically restored before re-raising.
- Updated `Ledger.restore_state` to incorporate funding events occurring after the latest decision. Closed runs explicitly reject recording new funding.

### 3. Replay / Backtest Funding Parity (`paper_trader.py`, `backtest.py`)
- Updated `replay_candles` to accept optional `funding_rates` DataFrame and apply funding events chronologically within candle spans.
- Verified exact accounting parity between `run_backtest` and `replay_candles` (matching final equity, cash, funding total, realized P&L, fees, spread, slippage, turnover, and trade count).

### 4. Durable Failure Evidence (`ledger.py`, `paper_trader.py`, `runner.py`)
- Added `failure_event` to `Ledger.ALLOWED_EVENT_TYPES` and implemented `record_failure` to log sanitized failure events (max 200 chars, no tracebacks, no secrets or credentials).
- Updated `PaperTrader._decide` to catch feature, observation, or prediction failures, log a durable failure event, and fail FLAT (`target = 0.0`) with `rejection_reason` carried into decision execution records.
- Guaranteed that failure event write failures stop execution rather than silently continuing.
- Updated `LivePaperRunner` (`backfill`, `handle_event`, `run`) to record durable runner failure events before re-raising without falsely marking the run as normally closed.

---

## Verification Results

### Focused Tests
```
python -m pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_backtest_baselines.py tests/test_live_accounting.py -q
........................................................................ [ 97%]
..                                                                       [100%]
74 passed
```

### Full Suite
```
python -m pytest -q
........................................................................ [ 19%]
........................................................................ [ 39%]
........................................................................ [ 59%]
........................................................................ [ 79%]
..................s..................................................... [ 99%]
..                                                                       [100%]
359 passed, 1 skipped
```

### Static Analysis & Linting
```
python -m compileall -q src tests                            -> clean
python -m mypy src                                          -> Success: 46 source files
python -m ruff check src/... tests/...                       -> All checks passed!
python -m ruff format --check src/... tests/...              -> 10 files already formatted
git diff --check                                             -> clean
```
