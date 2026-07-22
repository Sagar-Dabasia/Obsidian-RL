# Agent Run Report — Phase 2: Terminal Liquidation and Final Accounting

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-20 |
| **Branch** | `wip/phase2-terminal-accounting` |
| **Starting commit** | `b06a3f2eff22178d2474f8d3fec683d8c4f0c525` |
| **Task** | Phase 2: Terminal liquidation persistence, final ledger accounting, closed-run dashboard accounting, terminal liquidation in backtest equity curves, and replay/backtest terminal-accounting parity |

---

## Working-tree status

**Before**:
```
git status --short
(clean)
```

**After** (this session, allowed source/test files and docs):
```
 M src/obsidian_rl/dashboard/app.py
 M src/obsidian_rl/dashboard/queries.py
 M src/obsidian_rl/evaluation/backtest.py
 M src/obsidian_rl/ledger/ledger.py
 M src/obsidian_rl/live/paper_trader.py
 M tests/test_backtest_baselines.py
 M tests/test_dashboard_queries.py
 M tests/test_ledger.py
 M tests/test_paper_trader.py
?? docs/agent-runs/2026-07-20T211000Z-phase2-terminal-accounting.md
```

---

## Files inspected & modified

### Production Files Modified
- `src/obsidian_rl/ledger/ledger.py`
- `src/obsidian_rl/live/paper_trader.py`
- `src/obsidian_rl/evaluation/backtest.py`
- `src/obsidian_rl/dashboard/queries.py`
- `src/obsidian_rl/dashboard/app.py`

### Test Files Modified
- `tests/test_ledger.py`
- `tests/test_paper_trader.py`
- `tests/test_backtest_baselines.py`
- `tests/test_dashboard_queries.py`

---

## Defects & Resolution Summary

### Defect 1 — Terminal liquidation state is unrecorded and vulnerable to duplicate execution
- **Root cause**: `PaperTrader.close_session` ran `self.engine.liquidate(mark_price)` and immediately called `end_run`, but never saved the final liquidation trades, cash, or portfolio snapshot to the ledger. If `close_session` was called again, or if a run was restarted/re-liquidated, `liquidate` would re-run and double-charge fees/slippage.
- **Resolution**:
  - Created `run_closures` table (`1:1` with `runs(run_id)`) in `Ledger.__init__`, storing `terminal_ts_ms`, `mark_price`, `delta_qty`, `exec_price`, `traded_notional`, `fee`, `spread_cost`, `slippage_cost`, `position_qty`, `cash`, `unrealized_pnl`, `net_equity`, `realized_pnl_total`, `fees_total`, `spread_total`, `slippage_total`, `funding_total`, `turnover_total`, `trade_count`, `peak_equity`, `closure_reason`, and `created_at_ms`.
  - Added `record_closure(run_id, ...)` using `INSERT` (raising `DuplicateClosureError` on duplicate) and `get_closure(run_id)` in `Ledger`.
  - Updated `PaperTrader.close_session(mark_price, *, terminal_ts_ms=None, closure_reason='close_session')`:
    - Checks `get_closure(run_id)` and `get_run(run_id)['ended_at_ms']` upfront. Returns early without liquidating or double-charging if already closed/ended.
    - Validates `mark_price` (`isfinite` and `> 0`).
    - Executes `self.engine.liquidate(mark_price)` and persists the exact post-liquidation snapshot to `run_closures`.
    - Only calls `self.ledger.end_run(run_id)` after successful closure persistence.

### Defect 2 — Replaying a closed session restores pre-liquidation state
- **Root cause**: `replay_candles` only replayed rows from `decisions`. When `PaperTrader` was constructed and `replay_candles` ran on a closed run (`runs.ended_at_ms is not None`), `self.engine.state` ended up at the last policy decision (`t_N`) instead of the final liquidated state (`qty = 0.0`), allowing accidental re-liquidation on post-ended runs.
- **Resolution**:
  - Updated `PaperTrader.__init__` to check `run_info["ended_at_ms"] is not None` and `self.ledger.get_closure(run_id)`. When loading an ended/closed run, `PaperTrader` restores `self.engine.state` directly from `run_closures` (setting `qty = closure['position_qty']`, `cash = closure['cash']`, `trade_count = closure['trade_count']`, etc.) so that the in-memory state precisely equals the terminal flat state (`qty = 0.0`).
  - Updated `replay_candles`: if `trader.ledger.get_run(trader.run_id)['ended_at_ms'] is not None`, `replay_candles` logs and returns `0` without replaying or altering `trader.engine.state`.

### Defect 3 — Dashboard shows pre-liquidation state for closed sessions
- **Root cause**: Dashboard queries (`run_frame`, `kpis`, `equity_and_drawdown`, `closed_trade_events`) only queried the `decisions` table. For closed sessions, `kpis` and charts missed the final liquidation P&L, fees, and flat position (`qty = 0.0`), showing open exposure instead.
- **Resolution**:
  - Added `get_run_closure(ledger_path, run_id)` to `queries.py`.
  - Updated `kpis(frame, initial_cash, closure=None)`: when `closure` is present, `kpis` returns exact terminal metrics from `closure` (`position_qty`, `net_equity`, `realized_pnl`, `fees`, `trade_count`, etc.).
  - Updated `equity_and_drawdown(frame, closure=None)`: appends the terminal liquidation point `(terminal_ts_ms, closure['net_equity'])` to the equity curve and recalculates peak drawdown across all points.
  - Updated `closed_trade_events(frame, closure=None)`: appends the terminal liquidation trade event if `closure['realized_pnl_delta'] != 0.0`.
  - Updated `app.py` to fetch `closure = get_run_closure(...)` and pass it down to `kpis`, `equity_and_drawdown`, and `closed_trade_events`.

### Defect 4 — Backtest equity curves exclude terminal liquidation point
- **Root cause**: `run_backtest` executed `engine.liquidate(close_px[-1])` to calculate `final_state_summary`, but the returned `equity_curve` DataFrame ended at candle `N-1` (`t_N`). The final equity point (`summary['final_equity']`) and the transition to flat (`exposure = 0.0`) were missing from `equity_curve`.
- **Resolution**:
  - Updated `run_backtest` (`backtest.py`): after loop completion and `engine.liquidate(close_px[-1])`, appends a terminal row `(close_time[-1], close_px[-1], engine.state.net_equity(close_px[-1]), 0.0, engine.state.drawdown(close_px[-1]), True, 'terminal_liquidation')` to `records`.
  - Added columns `is_terminal` (`bool`) and `event` (`str`) (`'decision'` vs `'terminal_liquidation'`) to `BacktestResult.equity_curve`.
  - Maintained policy decision count (`n_decisions` counts policy decisions only and excludes terminal liquidation).
  - Updated baseline metric calculations (`compute_metrics` across tests) to account for the terminal row (`m.n_candles == res.n_decisions + (1 if 'is_terminal' in res.equity_curve.columns else 0)`).

### Defect 5 — Replay vs. backtest parity broken at session end
- **Root cause**: Because backtest summaries included terminal liquidation while ledger `decisions` and `replay_candles` excluded it, `PaperTrader` equity after `close_session` did not match backtest terminal state or persisted ledger state.
- **Resolution**:
  - With `close_session` persisting exact terminal state to `run_closures`, `test_replay_matches_backtest_exactly` (`test_paper_trader.py`) verifies exact equality (`abs=1e-9`) between backtest `final_state_summary`, in-memory `trader.engine.state` after `close_session`, and the ledger (`ledger.get_closure(run_id)`).

---

## Verification & Command Results

| Command | Exit Code | Result |
|---|---|---|
| `.venv\Scripts\python.exe -m pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_dashboard_queries.py tests/test_backtest_baselines.py -q` | 0 | **35 passed in 0.58s** |
| `python -m pytest -q` (full suite across repository) | 0 | **223 passed, 1 skipped in 51s** |
| `python -m compileall -q src tests` | 0 | **Clean (0 compile errors)** |
| `.venv\Scripts\python.exe -m ruff check src tests` | 0 | **All checks passed! (0 errors)** |
| `.venv\Scripts\python.exe -m ruff format --check src tests` | 0 | **9 files already formatted (Clean)** |
| `.venv\Scripts\python.exe -m mypy src` | 0 | **Success: no issues found in 44 source files** |
| `git diff --check` | 0 | **Clean (0 whitespace or conflict marker errors)** |

---

## Verdict

**ACCEPTED**

All Phase 2 requirements (`terminal liquidation persistence`, `final ledger accounting`, `closed-run dashboard accounting`, `terminal liquidation in backtest equity curves`, and `replay/backtest terminal-accounting parity`) are fully implemented and verified against 223 passing repository tests.
