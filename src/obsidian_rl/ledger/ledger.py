"""Session-aware SQLite ledger: every decision, cost component, and P&L snapshot.

Idempotency keys make candle processing exactly-once per run; restart recovery rebuilds
portfolio state from the last recorded decision of a run.
"""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from obsidian_rl.portfolio.engine import ExecutionResult, PortfolioState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    model_id TEXT,
    mode TEXT NOT NULL,              -- backtest | replay | live-paper
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER,
    initial_cash REAL NOT NULL,
    cost_model_json TEXT NOT NULL,
    config_json TEXT,
    git_commit TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    candle_open_ms INTEGER NOT NULL,
    candle_close_ms INTEGER NOT NULL,
    decision_ts_ms INTEGER NOT NULL,
    data_source TEXT NOT NULL,
    proposed_target REAL NOT NULL,
    approved_target REAL NOT NULL,
    executed_target REAL NOT NULL,
    delta_qty REAL NOT NULL,
    exec_price REAL NOT NULL,
    traded_notional REAL NOT NULL,
    fee REAL NOT NULL,
    spread_cost REAL NOT NULL,
    slippage_cost REAL NOT NULL,
    funding REAL NOT NULL DEFAULT 0.0,
    realized_pnl_delta REAL NOT NULL,
    rejection_reason TEXT,
    position_qty REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    cash REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    net_equity REAL NOT NULL,
    gross_equity REAL NOT NULL,
    realized_pnl_total REAL NOT NULL,
    fees_total REAL NOT NULL,
    spread_total REAL NOT NULL,
    slippage_total REAL NOT NULL,
    funding_total REAL NOT NULL,
    turnover_total REAL NOT NULL,
    trade_count INTEGER NOT NULL,
    peak_equity REAL NOT NULL,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decisions_run_candle ON decisions(run_id, candle_open_ms);
"""


class DuplicateDecisionError(RuntimeError):
    """The same candle was already processed for this run."""


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    strategy_id: str
    model_id: str | None
    mode: str
    initial_cash: float


class Ledger:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) != "":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ runs
    def start_run(
        self,
        strategy_id: str,
        mode: str,
        initial_cash: float,
        cost_model: dict[str, float],
        *,
        model_id: str | None = None,
        config: dict[str, object] | None = None,
        git_commit: str | None = None,
        run_id: str | None = None,
    ) -> RunInfo:
        run_id = run_id or uuid.uuid4().hex[:16]
        self._conn.execute(
            "INSERT INTO runs (run_id, strategy_id, model_id, mode, started_at_ms,"
            " initial_cash, cost_model_json, config_json, git_commit)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                strategy_id,
                model_id,
                mode,
                int(time.time() * 1000),
                initial_cash,
                json.dumps(cost_model),
                json.dumps(config or {}),
                git_commit,
            ),
        )
        self._conn.commit()
        return RunInfo(run_id, strategy_id, model_id, mode, initial_cash)

    def end_run(self, run_id: str) -> None:
        self._conn.execute(
            "UPDATE runs SET ended_at_ms=? WHERE run_id=?", (int(time.time() * 1000), run_id)
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,))
        row: sqlite3.Row | None = cur.fetchone()
        return row

    def list_runs(self) -> list[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        return list(self._conn.execute("SELECT * FROM runs ORDER BY started_at_ms"))

    # ------------------------------------------------------------------ decisions
    @staticmethod
    def idempotency_key(run_id: str, candle_open_ms: int) -> str:
        return f"{run_id}:{candle_open_ms}"

    def record_decision(
        self,
        run_id: str,
        *,
        candle_open_ms: int,
        candle_close_ms: int,
        decision_ts_ms: int,
        data_source: str,
        result: ExecutionResult,
        state: PortfolioState,
        mark_price: float,
        funding: float = 0.0,
    ) -> None:
        key = self.idempotency_key(run_id, candle_open_ms)
        try:
            self._conn.execute(
                "INSERT INTO decisions (run_id, idempotency_key, candle_open_ms,"
                " candle_close_ms, decision_ts_ms, data_source, proposed_target,"
                " approved_target, executed_target, delta_qty, exec_price, traded_notional,"
                " fee, spread_cost, slippage_cost, funding, realized_pnl_delta,"
                " rejection_reason, position_qty, avg_entry_price, cash, unrealized_pnl,"
                " net_equity, gross_equity, realized_pnl_total, fees_total, spread_total,"
                " slippage_total, funding_total, turnover_total, trade_count, peak_equity,"
                " created_at_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    key,
                    candle_open_ms,
                    candle_close_ms,
                    decision_ts_ms,
                    data_source,
                    result.proposed_target,
                    result.approved_target,
                    result.executed_target,
                    result.delta_qty,
                    result.exec_price,
                    result.traded_notional,
                    result.fee,
                    result.spread_cost,
                    result.slippage_cost,
                    funding,
                    result.realized_pnl_delta,
                    result.rejection_reason,
                    state.qty,
                    state.avg_entry_price,
                    state.cash,
                    state.unrealized_pnl(mark_price),
                    state.net_equity(mark_price),
                    state.gross_equity(mark_price),
                    state.realized_pnl,
                    state.fees_paid,
                    state.spread_paid,
                    state.slippage_paid,
                    state.funding_paid,
                    state.turnover,
                    state.trade_count,
                    state.peak_equity,
                    int(time.time() * 1000),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateDecisionError(key) from exc
        self._conn.commit()

    def last_decision(self, run_id: str) -> sqlite3.Row | None:
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute(
            "SELECT * FROM decisions WHERE run_id=? ORDER BY candle_open_ms DESC LIMIT 1",
            (run_id,),
        )
        row: sqlite3.Row | None = cur.fetchone()
        return row

    def decisions(self, run_id: str) -> list[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        return list(
            self._conn.execute(
                "SELECT * FROM decisions WHERE run_id=? ORDER BY candle_open_ms", (run_id,)
            )
        )

    def recent_decisions(self, run_id: str, limit: int) -> list[sqlite3.Row]:
        """Most recent `limit` decisions, returned in chronological order."""
        self._conn.row_factory = sqlite3.Row
        rows = list(
            self._conn.execute(
                "SELECT * FROM decisions WHERE run_id=? ORDER BY candle_open_ms DESC LIMIT ?",
                (run_id, limit),
            )
        )
        return list(reversed(rows))

    def has_processed(self, run_id: str, candle_open_ms: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM decisions WHERE idempotency_key=?",
            (self.idempotency_key(run_id, candle_open_ms),),
        )
        return cur.fetchone() is not None

    def restore_state(self, run_id: str) -> PortfolioState | None:
        """Rebuild PortfolioState from the last recorded decision of a run."""
        row = self.last_decision(run_id)
        if row is None:
            return None
        return PortfolioState(
            cash=row["cash"],
            qty=row["position_qty"],
            avg_entry_price=row["avg_entry_price"],
            realized_pnl=row["realized_pnl_total"],
            fees_paid=row["fees_total"],
            spread_paid=row["spread_total"],
            slippage_paid=row["slippage_total"],
            funding_paid=row["funding_total"],
            turnover=row["turnover_total"],
            trade_count=row["trade_count"],
            peak_equity=row["peak_equity"],
        )
