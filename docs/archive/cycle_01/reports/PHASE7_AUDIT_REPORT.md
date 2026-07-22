# Phase 7 Audit Report — Live-Paper Funding, Run Metadata & Durable Failure Evidence

## Branch and Commit
- **Branch**: `wip/phase7-live-accounting`
- **Commit**: `e90b8e4914cf9b5888a683f9d1a1458186f60ecb`

## Changed Files
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-21T193500Z-phase7-live-accounting.md`
- `src/obsidian_rl/dashboard/queries.py`
- `src/obsidian_rl/data/binance_client.py`
- `src/obsidian_rl/ledger/ledger.py`
- `src/obsidian_rl/live/paper_trader.py`
- `src/obsidian_rl/live/runner.py`
- `tests/test_live_accounting.py`

---

## Audit Checklist & Verdicts

### 1. Run Metadata
| Requirement | Status | Evidence |
|---|---|---|
| Ledger receives exact `PortfolioConfig` and `CostModel` used by `PaperTrader` | **PASS** | `LivePaperRunner.__init__` (`runner.py:102-124`) builds `PortfolioConfig` and `CostModel` once and passes identical instances to `Ledger.start_run` (`runner.py:126`) and `PaperTrader` (`runner.py:141`). |
| No hardcoded initial cash or independently created default costs remain | **PASS** | `LivePaperRunner` (`runner.py:128,143`) directly forwards `self.portfolio_config.initial_cash` and `self.cost_model` rather than instantiating ad-hoc costs or hardcoded `$10,000`. |
| Resume rejects configuration mismatch and incomplete legacy metadata | **PASS** | `LivePaperRunner.__init__` (`runner.py:116-124`) checks existing run metadata during resume, rejecting empty (`cost_model_json == {}`) or non-matching config with `ValueError`. |
| JSON metadata is canonical and rejects bool/NaN/Infinity | **PASS** | `Ledger.start_run` (`ledger.py:270-322`) uses sorted compact JSON serialization (`sort_keys=True, separators=(",", ":")`) with `allow_nan=False` and rejects `bool` inputs for numeric fields. |

### 2. Funding
| Requirement | Status | Evidence |
|---|---|---|
| Long pays positive funding; short receives it; signs reverse for negative rate | **PASS** | `funding_cash_flow` (`costs.py:62`) returns `-funding_rate * position_qty * price`. `PortfolioEngine.apply_funding` (`engine.py:224-228`) adds flow to cash and `-flow` to `funding_paid`. |
| Funding is chronological, exactly once and uses its supplied mark price | **PASS** | `replay_candles` (`paper_trader.py:532-560`) processes funding events chronologically alongside candles using explicit mark price and exact idempotency verification. |
| Funding does not create decisions, trades, turnover or trade-count changes | **PASS** | `PaperTrader.apply_funding_event` (`paper_trader.py:156-184`) invokes `engine.apply_funding` and records to `funding_events` table without creating decision rows, trade rows, or modifying trade count/turnover. |
| Persistence failure restores the complete previous `PortfolioState` | **PASS** | `PaperTrader.apply_funding_event` (`paper_trader.py:161,180`) copies state (`orig_state = copy.copy(self.engine.state)`) and atomically restores it (`self.engine.state = orig_state`) if DB writing fails. |
| Duplicate identical events are idempotent; conflicting duplicates fail | **PASS** | `Ledger.record_funding` (`ledger.py:476-515`) catches `sqlite3.IntegrityError`, queries existing row, and verifies all fields match within `1e-12` (returning `False`), or raises `EventConflictError`. |
| Closed runs reject funding | **PASS** | `Ledger.record_funding` (`ledger.py:443-444`) and `PaperTrader.apply_funding_event` (`paper_trader.py:158-159`) raise `ValueError` if `get_closure(run_id)` is not `None`. |
| Restore uses a funding event newer than the latest decision | **PASS** | `Ledger.restore_state` (`ledger.py:417-425`) iterates through `funding_events(run_id)` and applies cash, `funding_paid`, and `peak_equity` updates for any event where `funding_time_ms > dec_ms`. |
| Replay and backtest apply funding at the same chronological point | **PASS** | `replay_candles` (`paper_trader.py:555-559`) applies funding events where `f_time <= close_time` and `f_time >= open_time`, ensuring full parity with backtest engine mechanics. |

### 3. Failure Evidence
| Requirement | Status | Evidence |
|---|---|---|
| Decision, feature, prediction, target, runner and funding failures are durable | **PASS** | `PaperTrader._decide` (`paper_trader.py:298-350`) records `feature_construction_failure`, `observation_construction_failure`, and `strategy_prediction_failure` durable ledger events. `LivePaperRunner` (`runner.py:192,238,340`) records `runner_failure`. |
| Reasons are sanitized and length-limited | **PASS** | `Ledger.record_failure` (`ledger.py:733`) formats string reason as `sanitized_reason = str(reason).replace("\n", " ").strip()[:200]`. |
| No traceback, credentials, secret URLs or full market rows are stored | **PASS** | Only the brief exception message is captured in `sanitized_reason` (`ledger.py:733`), stripping tracebacks or raw row structures. |
| Failure-event persistence failure stops processing | **PASS** | `Ledger.record_failure` (`ledger.py:733-748`) delegates to `record_event`, which raises any SQLite persistence error without swallowing. |
| Fail-flat decisions contain the durable rejection reason | **PASS** | `PaperTrader._decide` (`paper_trader.py:313,326,344`) populates `rejection_reason = f"fail-flat: {reason}"` in `PendingDecision`, carried into decision records. |
| Runner failures are recorded before being re-raised | **PASS** | `LivePaperRunner` (`runner.py:190-197,236-244,337-345`) catches exceptions in `backfill`, `handle_event`, and `run`, calls `record_failure`, and immediately re-raises (`raise`). |
| Failures do not falsely mark runs normally closed | **PASS** | `LivePaperRunner` error handlers re-raise without calling `close_session()`, preserving active open status or exact crash evidence. |

### 4. Database Integrity
| Requirement | Status | Evidence |
|---|---|---|
| New tables migrate old ledgers safely | **PASS** | `Ledger._init_db` (`ledger.py:133-156`) creates `funding_events` using `CREATE TABLE IF NOT EXISTS`, preserving schema compatibility on pre-existing ledgers. |
| Transactions cannot leave funding/accounting state partially written | **PASS** | SQLite queries execute under active transactions with rollback (`self._conn.rollback()`) on failure (`ledger.py:480-481`) combined with in-memory state restoration. |
| `IntegrityError` handling distinguishes exact duplicates from unrelated errors | **PASS** | `record_funding` (`ledger.py:476-515`) intercepts `IntegrityError`, inspects conflicting row, and either returns `False` (idempotent) or raises `EventConflictError` (conflict). Unrelated DB errors raise naturally. |
| Session isolation and foreign keys are enforced | **PASS** | SQLite connection sets `PRAGMA foreign_keys = ON;` (`ledger.py:112`), and table schema explicitly defines `FOREIGN KEY(run_id) REFERENCES runs(run_id)` (`ledger.py:155`). |

---

## Verification Commands & Exit Codes

| Command | Exit Code | Summary Output |
|---|---|---|
| `.venv\Scripts\python -m pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_backtest_baselines.py -q` | `0` | `59 passed` |
| `.venv\Scripts\python -m pytest -q` | `0` | `359 passed, 1 skipped` |
| `.venv\Scripts\python -m compileall -q src tests` | `0` | Clean (no syntax issues across 103 files) |
| `.venv\Scripts\python -m mypy src` | `0` | `Success: no issues found in 46 source files` |
| `git diff --check` | `0` | Clean (no whitespace or conflict marker errors) |
| `git status --short` | `0` | Clean working tree |
| `.venv\Scripts\python -m ruff check ...` | `0` | `All checks passed!` |
| `.venv\Scripts\python -m ruff format --check ...` | `0` | `6 files already formatted` |

---

## Confirmed Defects
- **None**. All requirements across Run Metadata, Funding, Failure Evidence, and Database Integrity are cleanly implemented, verified, and passing all test suites.

---

## Final Verdict
PHASE 7 VERIFIED
