# Codex handoff

Updated: 2026-07-21

## Current branch and commit
- Branch: `wip/phase7-live-accounting`
- Starting commit: `33911ac61821ed884e43d8bb1b03016682067a00`

## Status
Phase 7 Live-Paper Funding, Run Metadata & Durable Failure Evidence — **COMPLETE (verified)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-21T193500Z-phase7-live-accounting.md](agent-runs/2026-07-21T193500Z-phase7-live-accounting.md)

## What was implemented in Phase 7
- **Authoritative Run Configuration**: `LivePaperRunner` constructs single validated `PortfolioConfig` and `CostModel` instances, persisting canonical sorted compact JSON in `runs` (`cost_model_json`, `config_json`). Verifies runtime vs stored configuration on resume.
- **Funding-Event Accounting**: Added public funding rate retrieval in `BinanceFuturesRest` (`GET /fapi/v1/fundingRate`), `funding_events` table in SQLite ledger with exact idempotency checking, state restoration including post-decision funding events, atomic rollback on write failures, and rejection of funding on closed runs.
- **Replay / Backtest Funding Parity**: Updated `replay_candles` to accept optional `funding_rates` DataFrame and verified exact accounting parity with `run_backtest`.
- **Durable Failure Evidence**: Added `failure_event` to `ALLOWED_EVENT_TYPES` and `record_failure` method to log sanitized failure events (max 200 chars). Integrated with `PaperTrader._decide` (fail-flat target 0 with rejection_reason) and `LivePaperRunner` before re-raising.

## Verification
- Focused tests (`pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_backtest_baselines.py tests/test_live_accounting.py -q`): **74 passed**
- Full suite (`pytest -q`): **359 passed, 1 skipped**
- `compileall`, `mypy`, `ruff check`, `ruff format --check`, `git diff --check`: **All clean**
