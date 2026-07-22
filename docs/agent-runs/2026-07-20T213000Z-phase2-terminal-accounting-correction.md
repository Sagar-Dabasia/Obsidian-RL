# Agent Run Report — Phase 2 Correction: Atomic Terminal Accounting & Live Runner Safeguards

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-20 |
| **Branch** | `wip/phase2-terminal-accounting` |
| **Starting commit** | `9f5d5cadf5eb037fab9891b8656ec40f9b1eb348` |
| **Task** | Phase 2 Correction: Atomic transaction for `record_closure` & `end_run`, `close_session` fail-flat pre-liquidation preservation, closed-run consistency guards across `PaperTrader` & `LivePaperRunner` |

---

## Working-tree status

**Before**:
```
git status --short
(clean at commit 9f5d5cadf5eb037fab9891b8656ec40f9b1eb348)
```

**After** (allowed production/test files & documentation):
```
 M docs/AGENT_RUN_REPORT.md
 M docs/CODEX_HANDOFF.md
?? docs/agent-runs/2026-07-20T213000Z-phase2-terminal-accounting-correction.md
 M src/obsidian_rl/ledger/ledger.py
 M src/obsidian_rl/live/paper_trader.py
 M src/obsidian_rl/live/runner.py
 M tests/test_ledger.py
?? tests/test_live_runner.py
 M tests/test_paper_trader.py
```

---

## Files inspected & modified

### Production Files Modified
- `src/obsidian_rl/ledger/ledger.py`
- `src/obsidian_rl/live/paper_trader.py`
- `src/obsidian_rl/live/runner.py`

### Test Files Modified & Created
- `tests/test_ledger.py`
- `tests/test_paper_trader.py`
- `tests/test_live_runner.py` (New)

---

## Defects & Resolution Summary

### Problem 1 — Closure and ended status are separate transactions
- **Root cause**: Previously, `PaperTrader.close_session` mutated in-memory engine state via `engine.liquidate()`, committed `record_closure()`, and then separately committed `end_run()`. A failure during `end_run()` left `run_closures` populated without `ended_at_ms` in `runs`, breaking the invariant `(closure is not None) == (ended_at is not None)`.
- **Resolution**:
  - Created `Ledger.finalize_run(self, run_id: str, *, terminal_ts_ms: int, mark_price: float, result: RebalanceResult, state: PortfolioState, closure_reason: str = "close_session") -> sqlite3.Row`.
  - Performs both the insertion into `run_closures` and the update of `runs.ended_at_ms` inside a single `BEGIN ... COMMIT` transaction.
  - On any database exception during insertion or update, both operations roll back (`self._conn.rollback()`).
  - Idempotent: repeated `finalize_run` calls on a consistently closed run return the existing `run_closures` row without inserting duplicates.
  - Raises explicit `RuntimeError` if closure and `ended_at_ms` disagree (`(closure is not None) != (ended_at is not None)`).

### Problem 2 — Liquidation can fail after engine state has already been flattened
- **Root cause**: If database persistence failed during session closure, `self.engine.state` had already been mutated to flat (`qty = 0.0`) and `self.pending` cleared (`None`), leaving the trader flat in memory while active in the database.
- **Resolution**:
  - Updated `PaperTrader.close_session`: takes exact copies (`copy.copy(self.engine.state)` and `orig_pending = self.pending`) right before clearing `pending` and calling `self.engine.liquidate(mark_price)`.
  - Calls `self.ledger.finalize_run(...)`. If `finalize_run` raises any exception, `close_session` restores `self.engine.state = orig_state` and `self.pending = orig_pending` before re-raising.
  - Preserves exact pre-liquidation cash, quantity, average entry price, realized P&L, turnover, trade count, and peak equity upon failure, allowing clean retry without double-liquidation.

### Problem 3 — Replaying and loading closed sessions can bypass terminal state checks
- **Root cause**: `PaperTrader.restore`, `on_finalized_candle`, `on_next_open`, and `replay_candles` lacked strict checks ensuring `(closure is not None) == (ended_at is not None)` and refusing active state modification on ended runs.
- **Resolution**:
  - Updated `PaperTrader.restore`, `on_finalized_candle`, `on_next_open`, and `replay_candles` to check closure/ended consistency.
  - If a run is consistently closed (`closure is not None and ended_at is not None`), `replay_candles`, `on_finalized_candle`, and `on_next_open` return `0` / `None` immediately without executing policy proposals or mutating terminal state.

### Problem 4 — Live runner can be pointed at an already ended run
- **Root cause**: `LivePaperRunner.__init__`, `backfill`, `handle_event`, and `run` allowed processing or resuming ended runs.
- **Resolution**:
  - Updated `LivePaperRunner.__init__` when resuming: verifies `run_info["ended_at_ms"] is None` and raises `ValueError("run <id> is already closed and cannot be resumed")` if ended.
  - Added `_check_not_closed` checks at the entry of `backfill`, `handle_event`, and `run` to immediately refuse streaming or backfilling on closed runs.
  - Created comprehensive test suite `tests/test_live_runner.py`.

---

## Verification & Command Results

| Command | Exit Code | Result |
|---|---|---|
| `.venv\Scripts\python.exe -m pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py -q` | 0 | **30 passed in 0.65s** |
| `.venv\Scripts\python.exe -m ruff check src/obsidian_rl/ledger/ledger.py src/obsidian_rl/live/paper_trader.py src/obsidian_rl/live/runner.py tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py` | 0 | **All checks passed! (0 errors)** |
| `.venv\Scripts\python.exe -m mypy src/obsidian_rl/ledger/ledger.py src/obsidian_rl/live/paper_trader.py src/obsidian_rl/live/runner.py tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py` | 0 | **Success: no issues found in 6 source files** |
