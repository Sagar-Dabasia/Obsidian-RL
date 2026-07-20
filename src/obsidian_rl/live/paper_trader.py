"""The single live-paper decision path, shared verbatim by replay and live streaming.

Two-phase protocol per candle:
  1. on_finalized_candle(candle_t)  — validate, dedupe, buffer, build the observation,
     propose a target (frozen policy, no exploration, no training).
  2. on_next_open(open_time, open_price) — execute the pending decision at the open of
     candle t+1 (the first traded price after the decision; never the price that formed
     the observation), record everything in the ledger.

Replay drives these with recorded candles; live mode drives them with websocket events.
Identical inputs produce identical decisions and accounting (proven by parity tests).

Failure policy: invalid data or model state => fail FLAT (target 0 proposal with a
rejection reason) or refuse the event explicitly. Prices are never fabricated; models
are never trained here.
"""

import logging
from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

from obsidian_rl.data.schema import CANDLE_COLUMNS, interval_to_ms
from obsidian_rl.evaluation.backtest import (
    DEFAULT_TARGETS,
    PortfolioFeatureTracker,
    snap_target,
)
from obsidian_rl.features.pipeline import WARMUP_ROWS, compute_market_features
from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine, PortfolioState
from obsidian_rl.strategies.base import Strategy

logger = logging.getLogger(__name__)

BUFFER_SIZE = WARMUP_ROWS + 8  # feature window + slack


class CandleSequenceError(RuntimeError):
    """Out-of-order, duplicate-conflicting, or gap-preceded candle; caller must backfill."""


@dataclass
class PendingDecision:
    candle_open_ms: int
    candle_close_ms: int
    decision_ts_ms: int
    proposed_target: float


class PaperTrader:
    """Owns one run's decision loop. Portfolio state lives ONLY in the engine + ledger."""

    def __init__(
        self,
        strategy: Strategy,
        ledger: Ledger,
        run_id: str,
        *,
        interval: str = "15m",
        portfolio_config: PortfolioConfig | None = None,
        cost_model: CostModel | None = None,
        allowed_targets: tuple[float, ...] = DEFAULT_TARGETS,
        data_source: str = "replay",
    ) -> None:
        self.strategy = strategy
        self.ledger = ledger
        self.run_id = run_id
        self.interval_ms = interval_to_ms(interval)
        self.engine = PortfolioEngine(
            portfolio_config or PortfolioConfig(), cost_model or CostModel()
        )
        self.tracker = PortfolioFeatureTracker()
        self.allowed_targets = allowed_targets
        self.data_source = data_source
        self.buffer: deque[dict[str, float | int]] = deque(maxlen=BUFFER_SIZE)
        self.last_finalized_ms: int | None = None
        self.pending: PendingDecision | None = None

    # ------------------------------------------------------------------ recovery
    def restore(self, state: PortfolioState, buffer_candles: pd.DataFrame) -> None:
        """Rebuild engine, feature buffer, tracker, and any pre-crash pending decision."""
        self.engine.state = state
        self.buffer.clear()
        for row in buffer_candles.tail(BUFFER_SIZE).itertuples(index=False):
            self.buffer.append({c: getattr(row, c) for c in CANDLE_COLUMNS})
        if self.buffer:
            self.last_finalized_ms = int(self.buffer[-1]["open_time"])
        last = self.ledger.last_decision(self.run_id)
        if last is not None and self.last_finalized_ms is not None:
            ledger_ms = int(last["candle_open_ms"])
            if ledger_ms > self.last_finalized_ms:
                raise CandleSequenceError(
                    f"ledger is ahead of candle buffer ({ledger_ms} > {self.last_finalized_ms});"
                    " backfill candles before resuming"
                )

        # Rebuild tracker state (time in position, recent turnover) from the ledger so
        # portfolio observations do not jump across restarts.
        self.tracker.reset()
        for row in self.ledger.recent_decisions(self.run_id, 96):
            self.tracker.update_after_step(
                float(row["position_qty"]), float(row["traded_notional"])
            )

        # A decision made for the last buffered candle but never executed (crash between
        # the two phases) is not in the ledger: recompute it so on_next_open resumes it.
        if (
            self.last_finalized_ms is not None
            and not self.ledger.has_processed(self.run_id, self.last_finalized_ms)
            and len(self.buffer) >= WARMUP_ROWS + 1
        ):
            last_candle = self.buffer[-1]
            self.pending = self._decide(last_candle)
            logger.info(
                "recovered pre-crash pending decision for candle %s", self.last_finalized_ms
            )
        logger.info(
            "restored run %s: qty=%.6f cash=%.2f last_candle=%s",
            self.run_id,
            state.qty,
            state.cash,
            self.last_finalized_ms,
        )

    # ------------------------------------------------------------------ phase 1
    def on_finalized_candle(self, candle: dict[str, float | int]) -> PendingDecision | None:
        """Ingest one FINALIZED candle; propose a target. Returns None while warming up
        or when the candle is a duplicate."""
        open_ms = int(candle["open_time"])
        if self.last_finalized_ms is not None:
            if open_ms <= self.last_finalized_ms:
                logger.info("duplicate/stale candle %s ignored", open_ms)
                return None
            if open_ms != self.last_finalized_ms + self.interval_ms:
                raise CandleSequenceError(
                    f"gap: expected {self.last_finalized_ms + self.interval_ms}, got {open_ms}"
                )
        if self.ledger.has_processed(self.run_id, open_ms):
            logger.info("candle %s already in ledger; skipping", open_ms)
            self.last_finalized_ms = open_ms
            self.buffer.append(dict(candle))
            return None

        self.buffer.append(dict(candle))
        self.last_finalized_ms = open_ms

        close_px = float(candle["close"])
        self.engine.mark_to_market(close_px)

        if len(self.buffer) < WARMUP_ROWS + 1:
            logger.info("warming up: %d/%d candles", len(self.buffer), WARMUP_ROWS + 1)
            return None

        self.pending = self._decide(candle)
        return self.pending

    def _decide(self, candle: dict[str, float | int]) -> PendingDecision:
        """Build the observation from the buffer and propose a target (fail flat)."""
        open_ms = int(candle["open_time"])
        close_px = float(candle["close"])
        proposed = 0.0
        try:
            frame = pd.DataFrame(list(self.buffer), columns=CANDLE_COLUMNS)
            market_row = compute_market_features(frame).iloc[-1].to_numpy(dtype=np.float32)
            if np.isnan(market_row).any():
                raise ValueError("NaN in market features")
            port = self.tracker.observe(self.engine, close_px)
            proposed = float(self.strategy.propose(market_row, port))
        except Exception:
            logger.exception("decision failure at candle %s; failing FLAT", open_ms)
            proposed = 0.0
        return PendingDecision(
            candle_open_ms=open_ms,
            candle_close_ms=int(candle["close_time"]),
            decision_ts_ms=int(candle["close_time"]) + 1,
            proposed_target=snap_target(proposed, self.allowed_targets),
        )

    # ------------------------------------------------------------------ phase 2
    def on_next_open(self, next_open_ms: int, next_open_price: float) -> None:
        """Execute the pending decision at the open of the following candle."""
        if self.pending is None:
            return
        expected = self.pending.candle_open_ms + self.interval_ms
        if next_open_ms != expected:
            raise CandleSequenceError(
                f"execution candle mismatch: expected open_time {expected}, got {next_open_ms}"
            )
        pending, self.pending = self.pending, None
        result = self.engine.rebalance(pending.proposed_target, next_open_price)
        self.tracker.update_after_step(self.engine.state.qty, result.traded_notional)
        self.ledger.record_decision(
            self.run_id,
            candle_open_ms=pending.candle_open_ms,
            candle_close_ms=pending.candle_close_ms,
            decision_ts_ms=pending.decision_ts_ms,
            data_source=self.data_source,
            result=result,
            state=self.engine.state,
            mark_price=next_open_price,
        )
        logger.info(
            "candle %s: proposed=%.2f approved=%.2f executed=%.3f qty=%.6f equity=%.2f%s",
            pending.candle_open_ms,
            result.proposed_target,
            result.approved_target,
            result.executed_target,
            self.engine.state.qty,
            self.engine.state.net_equity(next_open_price),
            f" [{result.rejection_reason}]" if result.rejection_reason else "",
        )

    def close_session(
        self,
        mark_price: float,
        *,
        terminal_ts_ms: int | None = None,
        closure_reason: str = "close_session",
    ) -> None:
        """Terminal liquidation at the given mark and run closure (explicit, logged)."""
        import math
        import time

        if not math.isfinite(mark_price) or mark_price <= 0:
            raise ValueError(f"invalid mark_price for session closure: {mark_price}")

        existing_closure = self.ledger.get_closure(self.run_id)
        if existing_closure is not None:
            logger.info("session %s is already closed; no action taken", self.run_id)
            return

        run_info = self.ledger.get_run(self.run_id)
        if run_info is not None and run_info["ended_at_ms"] is not None:
            logger.info("session %s is already ended; no action taken", self.run_id)
            return

        self.pending = None
        if terminal_ts_ms is None:
            last = self.ledger.last_decision(self.run_id)
            if last is not None:
                terminal_ts_ms = int(last["candle_close_ms"])
            elif self.buffer:
                terminal_ts_ms = int(self.buffer[-1]["close_time"])
            else:
                terminal_ts_ms = int(time.time() * 1000)

        result = self.engine.liquidate(mark_price)
        self.ledger.record_closure(
            self.run_id,
            terminal_ts_ms=terminal_ts_ms,
            mark_price=mark_price,
            result=result,
            state=self.engine.state,
            closure_reason=closure_reason,
        )
        logger.info(
            "session closed: liquidated %.6f @ %.2f, final equity %.2f",
            result.delta_qty,
            mark_price,
            self.engine.state.net_equity(mark_price),
        )
        self.ledger.end_run(self.run_id)


def replay_candles(trader: PaperTrader, candles: pd.DataFrame) -> int:
    """Drive the live-paper decision path over recorded candles. Returns decisions made.

    Ordering mirrors the live handle_event path EXACTLY: for each row, first execute any
    pending decision whose execution candle is THIS row (phase 2, at this row's open),
    THEN ingest the finalized candle (phase 1, which may set a new pending). This means a
    pending decision carried in from restore() or from a prior backfill batch — whose
    execution candle is the FIRST row of `candles` — is executed before it can be
    overwritten. (The previous look-ahead ordering lost that carried decision because the
    first on_finalized_candle overwrote `pending` before it executed.)
    """
    n = 0
    rows = candles.reset_index(drop=True)
    for i in range(len(rows)):
        open_ms = int(rows.at[i, "open_time"])
        if (
            trader.pending is not None
            and open_ms == trader.pending.candle_open_ms + trader.interval_ms
        ):
            trader.on_next_open(open_ms, float(rows.at[i, "open"]))
            n += 1
        candle = {c: rows.at[i, c] for c in CANDLE_COLUMNS}
        trader.on_finalized_candle(candle)
    return n
