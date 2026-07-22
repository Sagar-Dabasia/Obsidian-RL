# Adversarial correctness review of the new platform (2026-07-19/20)

Multi-agent review of `src/obsidian_rl/` across 8 dimensions; every non-minor finding was
independently verified (numeric reproduction) before being accepted. Confirmed defects
were fixed with regression tests. Dimensions run: accounting, timing/leakage, ledger/data,
gym-api, live-paper, promotion-gate. (accounting ran first and found the liquidation bug
below; the other dimensions ran in a resumed pass after a session-limit interruption.)

## Confirmed and fixed
1. **Portfolio no-trade band blocked closes** (`portfolio/engine.py`) — a full-close /
   `liquidate()` could be skipped when position notional fell below `min_trade_notional`
   or |exposure| drifted inside the tolerance band, leaving residual positions after
   terminal liquidation. Fix: close requests bypass the band. Commit `167ce7c`.
2. **Funding stale-event drop** (`evaluation/backtest.py`) — a funding event in the
   warm-up region pinned `f_idx` and silently dropped every later in-window event, so
   funding was under-counted (net return overstated). Fix: advance past events before the
   first executed candle, then apply in-window. Regression test added.
3. **Gap detection on non-contiguous index** (`data/validation.py`) — label-based lookups
   produced wrong gap boundaries and missing-candle counts on any filtered/holey frame
   (e.g. via the public `dataset_gap_frame`). Fix: positional access after `reset_index`.
4. **Store conflict bypass on new partitions** (`data/store.py`) — the new-partition
   branch used `drop_duplicates`, silently discarding differing rows for the same
   `open_time` instead of raising `StoreConflictError`. Fix: same conflict detection on
   both branches.
5. **Carried pending decision lost across backfill (CRITICAL)** (`live/paper_trader.py`)
   — a decision made for candle c_L, carried into a backfill/restore batch that starts at
   c_{L+1}, was overwritten by the first `on_finalized_candle` before executing, so one
   trade went missing and live diverged from the uninterrupted/backtest path after any
   gap. Fix: `replay_candles` now executes a due pending decision at the row's open
   BEFORE ingesting it, mirroring the live `handle_event` ordering exactly. The prior
   restart test missed it because a full replay hits the dedup branch (which preserves
   `pending`); a backfill batch does not. New regression test feeds only the post-gap
   candles.
6. **Double rollback bounced to the abandoned champion** (`training/promotion.py`) — a
   second consecutive rollback reinstated the just-rolled-back-from model instead of
   walking further back. Fix: CHAMPION.json now keeps an explicit `lineage` undo stack;
   rollback pops it (C→B→A) and errors when nothing precedes the current champion.

## Not reproduced / rejected
Other candidate findings were refuted during verification (guarded elsewhere, math
correct, or scenario impossible) and were not changed.
