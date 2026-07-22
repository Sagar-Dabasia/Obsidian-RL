# Agent Run Report — Phase 3: Reconnect, Startup Backfill, and Missed-Candle Safety

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase3-reconnect-safety` |
| **Starting commit** | `7351a061b46094317d4bb113e0e8a95648bc505f` |
| **Task** | Phase 3 — Reconnect, startup backfill and missed-candle safety (`run_events` audit table, observation-only `ingest_observation` backfill, `max_live_open_lag_ms` expiration guards, and strict gap recovery ordering) |

---

## Working-tree status

**Before**:
```
git status --short
(clean at commit 7351a061b46094317d4bb113e0e8a95648bc505f on branch wip/phase3-reconnect-safety)
```

**After** (this session, allowed source/test files and docs):
```
 M docs/AGENT_RUN_REPORT.md
 M docs/CODEX_HANDOFF.md
?? docs/agent-runs/2026-07-21T105000Z-phase3-reconnect-safety.md
 M src/obsidian_rl/config.py
 M src/obsidian_rl/ledger/ledger.py
 M src/obsidian_rl/live/paper_trader.py
 M src/obsidian_rl/live/runner.py
 M src/obsidian_rl/live/stream.py
 M tests/test_ledger.py
 M tests/test_live_runner.py
 M tests/test_paper_trader.py
?? tests/test_stream.py
```

---

## Files inspected & modified

### Production Files Modified
- `src/obsidian_rl/config.py`
- `src/obsidian_rl/ledger/ledger.py`
- `src/obsidian_rl/live/stream.py`
- `src/obsidian_rl/live/paper_trader.py`
- `src/obsidian_rl/live/runner.py`

### Test Files Modified & Created
- `tests/test_ledger.py`
- `tests/test_paper_trader.py`
- `tests/test_live_runner.py`
- `tests/test_stream.py` (New)

---

## Defects & Resolution Summary

### Problem 1 — Startup/reconnect backfill executed decisions instead of observation-only ingestion
- **Root cause**: Previously, `LivePaperRunner.backfill()` passed historical REST candles to `replay_candles(self.trader, df)`, which ran both Phase 1 (`on_finalized_candle`) and Phase 2 (`on_next_open`). This caused `PaperTrader` to propose and execute simulated paper trades on historical backfill data before live session resumption or during reconnect recovery.
- **Resolution**:
  - Implemented `PaperTrader.ingest_observation(self, candle: dict[str, float | int]) -> None`.
  - For every finalized backfill candle, `ingest_observation` validates continuity and canonical fields, appends to `self.buffer`, advances `last_finalized_ms`, marks the portfolio to market at the candle close, and advances `self.tracker` time-in-position (`update_after_step(qty, 0.0)`) with zero turnover.
  - `ingest_observation` never creates, rebalances, or overwrites a pending policy decision.
  - Updated `LivePaperRunner.backfill` to use `self.trader.ingest_observation` for all historical/gap candles. Replay and backtest mode (`replay_candles`) remain unchanged.

### Problem 2 & 4 — Missed execution window and late websocket events
- **Root cause**: Pending decisions are valid only for the exact next candle open (`pending.candle_open_ms + interval_ms`). If the live open event was missed or delayed beyond acceptable latency during websocket reconnects or startup recovery, existing logic would either crash (`CandleSequenceError`) or execute stale decisions against late market opens.
- **Resolution**:
  - Added `max_live_open_lag_ms: int = 5000` to `Settings` (`OBSIDIAN_MAX_LIVE_OPEN_LAG_MS`, validated `ge=0`) and propagated to `PaperTrader`.
  - Implemented `PaperTrader.expire_pending(self, reason: str, now_ms: int | None = None, details: dict[str, Any] | None = None) -> bool`, which records a durable audit event `pending_execution_expired` and clears `self.pending` without charging costs or proposing replacement decisions.
  - Updated `PaperTrader.on_next_open`: if `next_open_ms > expected`, or if `event_time_ms - next_open_ms > self.max_live_open_lag_ms`, the pending decision is immediately expired instead of executing or raising an unrecoverable sequence error.
  - Updated `PaperTrader.restore`: if the exact live execution window (`expected + max_live_open_lag_ms`) has passed relative to startup time (`now_ms`), the recovered `pending` decision is expired (`stale_restart_pending`).

### Problem 3 — Gap recovery ordering on reconnects
- **Root cause**: When websocket events resumed after a disconnect, `handle_event` checked Phase 2 execution (`on_next_open`) before detecting if intermediate finalized candles were missing. Furthermore, gap backfills were only triggered when a closed candle (`is_closed=True`) arrived.
- **Resolution**:
  - Enforced strict 6-step ordering in `LivePaperRunner.handle_event`:
    1. Validate event timestamp and candle identity (`event.event_time_ms < event.open_time` or `event.close_time < event.open_time`).
    2. Detect missing candles (`if last is not None and event.open_time > last + self.interval_ms`).
    3. Expire any pending decision whose execution window was missed (`missed_execution_window` or `max_live_open_lag_exceeded`).
    4. Backfill and observation-ingest (`backfill(now_ms=event.event_time_ms, max_open_ms=event.open_time)`) all missing finalized candles before execution.
    5. Consider execution at the current live candle open (`on_next_open`).
    6. Process finalized current candle (`on_finalized_candle`).
  - Gap recovery now occurs on the very first event received after reconnect (`event.open_time > last + interval_ms`), even if `is_closed=False`. The current in-progress candle (`open_time == event.open_time`) is excluded from REST backfills (`max_open_ms=event.open_time`).

### Problem 5 — Durable audit evidence (`run_events` table)
- **Root cause**: No durable audit trail existed for missing data gaps, backfill completions, or expired pending decisions.
- **Resolution**:
  - Added `run_events` table and index `ix_run_events_run_id` to `Ledger._SCHEMA` (`run_id`, `event_type`, `event_ts_ms`, `idempotency_key`, `details_json`, `created_at_ms`).
  - Implemented `Ledger.record_event(self, run_id: str, event_type: str, event_ts_ms: int, idempotency_key: str, details: dict[str, Any], created_at_ms: int | None = None) -> bool`. Duplicate insertions (`idempotency_key`) are cleanly caught and suppressed (`returns False`), ensuring idempotency.
  - Added `Ledger.has_event` and `Ledger.get_events` helper methods.
  - `LivePaperRunner.backfill` records `market_data_gap` and `backfill_observation_completed` events.
  - `PaperTrader.expire_pending` records `pending_execution_expired` events before clearing `pending`.

### Problem 6 — Malformed payload and stream validation (`stream.py`)
- **Root cause**: `KlineEvent` lacked `event_time_ms` tracking, and websocket parsing did not rigorously validate non-finite numbers, negative volumes, or malformed/missing fields before yielding events to the main loop.
- **Resolution**:
  - Added `event_time_ms: int` field to `KlineEvent` dataclass (`to_dict` includes `event_time_ms`).
  - Updated `parse_kline_event(raw: str | bytes) -> KlineEvent | None` with strict validation: returns `None` if `E` or `k` is missing, if `event_time_ms < open_time`, if `close_time < open_time`, if any price/volume field is `nan`/`inf`, if prices `<= 0`, or if volume/quote_volume/trades/taker metrics `< 0`.

---

## Verification Results

### Focused Unit Tests
```
python -m pytest tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_stream.py -q
..................................... [100%]
37 passed in 0.72s
```

### Ruff Linter & Formatting
```
python -m ruff check src/obsidian_rl/config.py src/obsidian_rl/ledger/ledger.py src/obsidian_rl/live/stream.py src/obsidian_rl/live/paper_trader.py src/obsidian_rl/live/runner.py tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_stream.py
All checks passed!

python -m ruff format --check src/obsidian_rl/config.py src/obsidian_rl/ledger/ledger.py src/obsidian_rl/live/stream.py src/obsidian_rl/live/paper_trader.py src/obsidian_rl/live/runner.py tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_stream.py
9 files already formatted
```

### Mypy Static Type Checking
```
python -m mypy src/obsidian_rl/config.py src/obsidian_rl/ledger/ledger.py src/obsidian_rl/live/stream.py src/obsidian_rl/live/paper_trader.py src/obsidian_rl/live/runner.py tests/test_ledger.py tests/test_paper_trader.py tests/test_live_runner.py tests/test_stream.py
Success: no issues found in 9 source files
```

### Complete Test Suite
```
python -m pytest -q
........................................................................ [ 29%]
........................................................................ [ 59%]
....................................................s................... [ 88%]
...........................                                              [100%]
242 passed, 1 skipped in 4.15s
```
