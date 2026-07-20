# Codex handoff

Updated: 2026-07-20

## Current branch and commit
- Branch: `wip/phase2-terminal-accounting`
- Commit: `b06a3f2eff22178d2474f8d3fec683d8c4f0c525` (starting point; working tree contains Phase 2 terminal liquidation and final accounting implementation)

## Status
Phase 2 terminal liquidation persistence, final ledger accounting, closed-run dashboard accounting, terminal liquidation backtest curves, & replay parity — **COMPLETE (verified)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-20T211000Z-phase2-terminal-accounting.md](agent-runs/2026-07-20T211000Z-phase2-terminal-accounting.md)

## What was fixed in this session (Phase 2: Terminal Accounting)
- **Terminal Liquidation Persistence (`ledger.py` & `paper_trader.py`)**:
  - Added `run_closures` table to SQLite (`1:1` with `runs(run_id)`), storing full terminal snapshot metrics (`terminal_ts_ms`, `mark_price`, `delta_qty`, `net_equity`, `realized_pnl_total`, `fees_total`, `turnover_total`, `trade_count`, `closure_reason`, etc.).
  - Added `record_closure` (raising `DuplicateClosureError` on duplicate insert) and `get_closure` to `Ledger`.
  - Updated `PaperTrader.close_session(mark_price)` to check upfront whether the session is already closed/ended before liquidating. Validates `mark_price` (>0 and finite), liquidates via `engine.liquidate`, records closure snapshot, and marks the run ended only upon successful DB write.
- **Closed-Session Replay Restoration (`paper_trader.py`)**:
  - `PaperTrader.__init__` now inspects `runs.ended_at_ms` and `run_closures`. When initializing from an already-closed run, `PaperTrader` restores `engine.state` directly from `run_closures` (`qty=0.0`, terminal cash, exact P&L and cost totals).
  - `replay_candles` returns early (`0` decisions replayed) if `ended_at_ms is not None`, preventing any accidental re-liquidation or state mutation.
- **Dashboard Closed-Run Accounting (`queries.py` & `app.py`)**:
  - Added `get_run_closure` to fetch terminal closure records.
  - Updated `kpis`, `equity_and_drawdown`, and `closed_trade_events` to accept `closure`. When `closure` is provided, `kpis` returns exact terminal figures (`position_qty=0.0`, closed P&L), `equity_and_drawdown` appends the final liquidation point to the equity/drawdown curves, and `closed_trade_events` includes the terminal realized P&L trade event.
  - Updated `app.py` to fetch `closure` and pass it across queries.
- **Backtest Terminal Equity Curve & Replay Parity (`backtest.py` & tests)**:
  - `run_backtest` now appends the final liquidation state to `records` with columns `is_terminal=True` and `event='terminal_liquidation'`. Policy `n_decisions` remains unchanged.
  - Verified exact (`abs=1e-9`) parity across backtest `final_state_summary`, `PaperTrader.engine.state` after `close_session`, and the persisted SQLite closure snapshot.

## Files changed (Phase 2)
- `src/obsidian_rl/ledger/ledger.py`
- `src/obsidian_rl/live/paper_trader.py`
- `src/obsidian_rl/evaluation/backtest.py`
- `src/obsidian_rl/dashboard/queries.py`
- `src/obsidian_rl/dashboard/app.py`
- `tests/test_ledger.py`
- `tests/test_paper_trader.py`
- `tests/test_backtest_baselines.py`
- `tests/test_dashboard_queries.py`
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-20T211000Z-phase2-terminal-accounting.md`

## Verification Commands Run
- `.venv\Scripts\python.exe -m pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_dashboard_queries.py tests/test_backtest_baselines.py -q`: **35 passed in 0.58s**, 0 failed.
- `python -m pytest -q` (full suite across repository): **223 passed, 1 skipped in 51s**, 0 failed.
- `python -m compileall -q src tests`: **Clean (0 errors)**.
- `.venv\Scripts\python.exe -m ruff check src tests`: **All checks passed! (0 errors)**.
- `.venv\Scripts\python.exe -m ruff format --check src tests`: **Clean (9 files already formatted)**.
- `.venv\Scripts\python.exe -m mypy src`: **Success (no issues found in 44 source files)**.
- `git diff --check`: **Clean (0 whitespace errors)**.

## Next steps
Review and commit Phase 2 when requested by user.
