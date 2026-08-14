"""Session-aware SQLite ledger: every decision, cost component, and P&L snapshot.

Idempotency keys make candle processing exactly-once per run; restart recovery rebuilds
portfolio state from the last recorded decision of a run.
"""

import contextlib
import json
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from obsidian_rl.portfolio.costs import CostModel
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
    path_maximum_drawdown_pct REAL NOT NULL DEFAULT 0.0,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decisions_run_candle ON decisions(run_id, candle_open_ms);
CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    event_type TEXT NOT NULL,
    event_ts_ms INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    details_json TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_run_events_run_id ON run_events(run_id);
CREATE TABLE IF NOT EXISTS funding_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    funding_time_ms INTEGER NOT NULL,
    rate REAL NOT NULL,
    mark_price REAL NOT NULL,
    position_qty REAL NOT NULL,
    cash_flow REAL NOT NULL,
    resulting_cash REAL NOT NULL,
    resulting_equity REAL NOT NULL,
    funding_total REAL NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_funding_events_run_time ON funding_events(run_id, funding_time_ms);
CREATE TABLE IF NOT EXISTS run_closures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
    terminal_ts_ms INTEGER NOT NULL,
    mark_price REAL NOT NULL,
    proposed_target REAL NOT NULL,
    approved_target REAL NOT NULL,
    executed_target REAL NOT NULL,
    delta_qty REAL NOT NULL,
    exec_price REAL NOT NULL,
    traded_notional REAL NOT NULL,
    fee REAL NOT NULL,
    spread_cost REAL NOT NULL,
    slippage_cost REAL NOT NULL,
    realized_pnl_delta REAL NOT NULL,
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
    path_maximum_drawdown_pct REAL NOT NULL DEFAULT 0.0,
    closure_reason TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL
);
"""


class DuplicateDecisionError(RuntimeError):
    """The same candle was already processed for this run."""


class DuplicateClosureError(RuntimeError):
    """A terminal closure record already exists for this run."""


class EventConflictError(RuntimeError):
    """Audit event with this idempotency key already exists with conflicting contents."""


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
        with contextlib.suppress(sqlite3.OperationalError):
            self._conn.execute(
                "ALTER TABLE decisions ADD COLUMN "
                "path_maximum_drawdown_pct REAL NOT NULL DEFAULT 0.0"
            )
        with contextlib.suppress(sqlite3.OperationalError):
            self._conn.execute(
                "ALTER TABLE run_closures ADD COLUMN "
                "path_maximum_drawdown_pct REAL NOT NULL DEFAULT 0.0"
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ runs
    def start_run(
        self,
        strategy_id: str,
        mode: str,
        initial_cash: float,
        cost_model: CostModel | dict[str, float],
        *,
        model_id: str | None = None,
        config: dict[str, object] | None = None,
        git_commit: str | None = None,
        run_id: str | None = None,
    ) -> RunInfo:
        if isinstance(initial_cash, bool) or not isinstance(initial_cash, (int, float)):
            raise ValueError(f"initial_cash must be float > 0, got {type(initial_cash).__name__}")
        if not math.isfinite(initial_cash) or initial_cash <= 0:
            raise ValueError(f"initial_cash must be positive and finite, got {initial_cash}")

        if isinstance(cost_model, dict):
            if not cost_model:
                cm = CostModel()
            else:
                for k, v in cost_model.items():
                    if (
                        isinstance(v, bool)
                        or not isinstance(v, (int, float))
                        or not math.isfinite(v)
                    ):
                        raise ValueError(f"invalid cost_model field {k}={v!r}")
                cm = CostModel(**cost_model)
        elif isinstance(cost_model, CostModel):
            cm = cost_model
        else:
            raise ValueError(f"invalid cost_model: {type(cost_model).__name__}")

        cost_dict = {
            "half_spread": float(cm.half_spread),
            "slippage": float(cm.slippage),
            "taker_fee": float(cm.taker_fee),
        }
        try:
            cost_model_json = json.dumps(
                cost_dict, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            config_payload = dict(config or {})
            config_json = json.dumps(
                config_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (ValueError, TypeError) as exc:
            raise ValueError(f"canonical JSON serialization failed: {exc}") from exc

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
                float(initial_cash),
                cost_model_json,
                config_json,
                git_commit,
            ),
        )
        self._conn.commit()
        return RunInfo(run_id, strategy_id, model_id, mode, float(initial_cash))

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
                " path_maximum_drawdown_pct,"
                " created_at_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    state.path_maximum_drawdown_pct,
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
        """Rebuild PortfolioState from the last recorded decision, funding, or terminal closure."""
        run_row = self.get_run(run_id)
        if run_row is None:
            return None
        ended_at = run_row["ended_at_ms"]
        closure_row = self.get_closure(run_id)

        if (closure_row is not None) != (ended_at is not None):
            msg = (
                f"inconsistent closure/ended state for run {run_id}: "
                f"closure={closure_row is not None}, ended={ended_at is not None}"
            )
            raise RuntimeError(msg)
        if closure_row is not None and ended_at is not None:
            return PortfolioState(
                cash=closure_row["cash"],
                qty=closure_row["position_qty"],
                avg_entry_price=closure_row["avg_entry_price"],
                realized_pnl=closure_row["realized_pnl_total"],
                fees_paid=closure_row["fees_total"],
                spread_paid=closure_row["spread_total"],
                slippage_paid=closure_row["slippage_total"],
                funding_paid=closure_row["funding_total"],
                turnover=closure_row["turnover_total"],
                trade_count=closure_row["trade_count"],
                peak_equity=closure_row["peak_equity"],
                path_maximum_drawdown_pct=closure_row["path_maximum_drawdown_pct"],
            )

        dec_row = self.last_decision(run_id)
        funding_rows = self.funding_events(run_id)

        if dec_row is None and not funding_rows:
            return None

        if dec_row is not None:
            state = PortfolioState(
                cash=dec_row["cash"],
                qty=dec_row["position_qty"],
                avg_entry_price=dec_row["avg_entry_price"],
                realized_pnl=dec_row["realized_pnl_total"],
                fees_paid=dec_row["fees_total"],
                spread_paid=dec_row["spread_total"],
                slippage_paid=dec_row["slippage_total"],
                funding_paid=dec_row["funding_total"],
                turnover=dec_row["turnover_total"],
                trade_count=dec_row["trade_count"],
                peak_equity=dec_row["peak_equity"],
                path_maximum_drawdown_pct=dec_row["path_maximum_drawdown_pct"],
            )
            dec_ms = int(dec_row["candle_open_ms"])
        else:
            init_cash = float(run_row["initial_cash"])
            state = PortfolioState(cash=init_cash, peak_equity=init_cash)
            dec_ms = -1

        for fe in funding_rows:
            if int(fe["funding_time_ms"]) > dec_ms:
                state.cash = float(fe["resulting_cash"])
                state.funding_paid = float(fe["funding_total"])
                eq = state.net_equity(float(fe["mark_price"]))
                if eq > state.peak_equity:
                    state.peak_equity = eq

        return state

    # ------------------------------------------------------------------ funding
    def record_funding(
        self,
        run_id: str,
        *,
        funding_time_ms: int,
        rate: float,
        mark_price: float,
        position_qty: float,
        cash_flow: float,
        resulting_cash: float,
        resulting_equity: float,
        funding_total: float,
        idempotency_key: str | None = None,
        created_at_ms: int | None = None,
    ) -> bool:
        """Persist a funding event for a run.

        Returns True if inserted, False if identical existing event verified.
        Raises ValueError if validation fails or run is closed.
        Raises EventConflictError if conflict detected.
        """
        if self.get_closure(run_id) is not None:
            raise ValueError(f"closed run {run_id} cannot receive funding")

        for name, val in [
            ("funding_time_ms", funding_time_ms),
            ("rate", rate),
            ("mark_price", mark_price),
            ("position_qty", position_qty),
            ("cash_flow", cash_flow),
            ("resulting_cash", resulting_cash),
            ("resulting_equity", resulting_equity),
            ("funding_total", funding_total),
        ]:
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(f"invalid {name}: {val!r}")
            if not math.isfinite(val):
                raise ValueError(f"non-finite {name}: {val!r}")

        if funding_time_ms <= 0:
            raise ValueError(f"funding_time_ms must be positive, got {funding_time_ms}")
        if mark_price <= 0:
            raise ValueError(f"mark_price must be positive, got {mark_price}")

        key = idempotency_key or f"{run_id}:funding:{funding_time_ms}"
        created_at = created_at_ms if created_at_ms is not None else int(time.time() * 1000)

        try:
            self._conn.execute(
                "INSERT INTO funding_events (run_id, funding_time_ms, rate, mark_price,"
                " position_qty, cash_flow, resulting_cash, resulting_equity, funding_total,"
                " idempotency_key, created_at_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    funding_time_ms,
                    rate,
                    mark_price,
                    position_qty,
                    cash_flow,
                    resulting_cash,
                    resulting_equity,
                    funding_total,
                    key,
                    created_at,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError as exc:
            with contextlib.suppress(Exception):
                self._conn.rollback()

            self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(
                "SELECT * FROM funding_events WHERE idempotency_key=?",
                (key,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise exc

            if (
                existing["run_id"] == run_id
                and existing["funding_time_ms"] == funding_time_ms
                and abs(float(existing["rate"]) - rate) < 1e-12
                and abs(float(existing["mark_price"]) - mark_price) < 1e-12
                and abs(float(existing["position_qty"]) - position_qty) < 1e-12
                and abs(float(existing["cash_flow"]) - cash_flow) < 1e-12
                and abs(float(existing["resulting_cash"]) - resulting_cash) < 1e-12
                and abs(float(existing["resulting_equity"]) - resulting_equity) < 1e-12
                and abs(float(existing["funding_total"]) - funding_total) < 1e-12
            ):
                return False

            raise EventConflictError(
                f"funding event idempotency key {key!r} conflict with differing contents"
            ) from exc

    def funding_events(self, run_id: str) -> list[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        return list(
            self._conn.execute(
                "SELECT * FROM funding_events WHERE run_id=? ORDER BY funding_time_ms ASC",
                (run_id,),
            )
        )

    def last_funding(self, run_id: str) -> sqlite3.Row | None:
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute(
            "SELECT * FROM funding_events WHERE run_id=? ORDER BY funding_time_ms DESC LIMIT 1",
            (run_id,),
        )
        row: sqlite3.Row | None = cur.fetchone()
        return row

    def record_closure(
        self,
        run_id: str,
        *,
        terminal_ts_ms: int,
        mark_price: float,
        result: ExecutionResult,
        state: PortfolioState,
        closure_reason: str = "close_session",
    ) -> sqlite3.Row:
        try:
            self._conn.execute(
                "INSERT INTO run_closures (run_id, terminal_ts_ms, mark_price,"
                " proposed_target, approved_target, executed_target, delta_qty,"
                " exec_price, traded_notional, fee, spread_cost, slippage_cost,"
                " realized_pnl_delta, position_qty, avg_entry_price, cash,"
                " unrealized_pnl, net_equity, gross_equity, realized_pnl_total,"
                " fees_total, spread_total, slippage_total, funding_total,"
                " turnover_total, trade_count, peak_equity, path_maximum_drawdown_pct,"
                " closure_reason, created_at_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    terminal_ts_ms,
                    mark_price,
                    result.proposed_target,
                    result.approved_target,
                    result.executed_target,
                    result.delta_qty,
                    result.exec_price,
                    result.traded_notional,
                    result.fee,
                    result.spread_cost,
                    result.slippage_cost,
                    result.realized_pnl_delta,
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
                    state.path_maximum_drawdown_pct,
                    closure_reason,
                    int(time.time() * 1000),
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "run_closures" in str(exc) or "run_id" in str(exc) or "UNIQUE" in str(exc).upper():
                msg = f"terminal closure already recorded for run {run_id}"
                raise DuplicateClosureError(msg) from exc
            raise
        self._conn.commit()
        row = self.get_closure(run_id)
        assert row is not None
        return row

    def finalize_run(
        self,
        run_id: str,
        *,
        terminal_ts_ms: int,
        mark_price: float,
        result: ExecutionResult,
        state: PortfolioState,
        closure_reason: str = "close_session",
    ) -> sqlite3.Row:
        """Atomically record terminal closure and update runs.ended_at_ms inside one transaction."""
        run_row = self.get_run(run_id)
        if run_row is None:
            raise KeyError(f"run {run_id} not found in ledger")

        closure_row = self.get_closure(run_id)
        ended_at = run_row["ended_at_ms"]

        if (closure_row is not None) != (ended_at is not None):
            msg = (
                f"inconsistent closure/ended state for run {run_id}: "
                f"closure={closure_row is not None}, ended={ended_at is not None}"
            )
            raise RuntimeError(msg)
        if closure_row is not None and ended_at is not None:
            return closure_row

        created_at = int(time.time() * 1000)
        in_tx = self._conn.in_transaction
        if not in_tx:
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute("BEGIN")

        try:
            try:
                self._conn.execute(
                    "INSERT INTO run_closures (run_id, terminal_ts_ms, mark_price,"
                    " proposed_target, approved_target, executed_target, delta_qty,"
                    " exec_price, traded_notional, fee, spread_cost, slippage_cost,"
                    " realized_pnl_delta, position_qty, avg_entry_price, cash,"
                    " unrealized_pnl, net_equity, gross_equity, realized_pnl_total,"
                    " fees_total, spread_total, slippage_total, funding_total,"
                    " turnover_total, trade_count, peak_equity, path_maximum_drawdown_pct,"
                    " closure_reason, created_at_ms)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        terminal_ts_ms,
                        mark_price,
                        result.proposed_target,
                        result.approved_target,
                        result.executed_target,
                        result.delta_qty,
                        result.exec_price,
                        result.traded_notional,
                        result.fee,
                        result.spread_cost,
                        result.slippage_cost,
                        result.realized_pnl_delta,
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
                        state.path_maximum_drawdown_pct,
                        closure_reason,
                        created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                exc_str = str(exc).upper()
                if "RUN_CLOSURES" in exc_str or "RUN_ID" in exc_str or "UNIQUE" in exc_str:
                    msg = f"terminal closure already recorded for run {run_id}"
                    raise DuplicateClosureError(msg) from exc
                raise
            cur = self._conn.execute(
                "UPDATE runs SET ended_at_ms = ? WHERE run_id = ? AND ended_at_ms IS NULL",
                (terminal_ts_ms, run_id),
            )
            if cur.rowcount != 1:
                msg = (
                    f"failed to update ended_at_ms exactly once for run {run_id} "
                    f"(rowcount={cur.rowcount})"
                )
                raise RuntimeError(msg)
            self._conn.commit()
        except Exception:
            with contextlib.suppress(Exception):
                self._conn.rollback()
            raise

        row = self.get_closure(run_id)
        assert row is not None
        return row

    def get_closure(self, run_id: str) -> sqlite3.Row | None:
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute("SELECT * FROM run_closures WHERE run_id=?", (run_id,))
        row: sqlite3.Row | None = cur.fetchone()
        return row

    # ------------------------------------------------------------------ events
    ALLOWED_EVENT_TYPES: ClassVar[set[str]] = {
        "market_data_gap",
        "pending_execution_expired",
        "backfill_observation_completed",
        "failure_event",
    }

    def record_failure(
        self,
        run_id: str,
        failure_type: str,
        reason: str,
        *,
        event_ts_ms: int,
        idempotency_key: str | None = None,
        details: dict[str, Any] | None = None,
        created_at_ms: int | None = None,
    ) -> bool:
        """Record a sanitized durable failure event.

        Raises if persistence fails.
        """
        sanitized_reason = str(reason).replace("\n", " ").strip()[:200]
        key = idempotency_key or f"{run_id}:failure:{failure_type}:{event_ts_ms}"
        payload: dict[str, Any] = {
            "failure_type": failure_type,
            "reason": sanitized_reason,
        }
        if details:
            payload.update(details)
        return self.record_event(
            run_id=run_id,
            event_type="failure_event",
            event_ts_ms=event_ts_ms,
            idempotency_key=key,
            details=payload,
            created_at_ms=created_at_ms,
        )

    def record_event(
        self,
        run_id: str,
        event_type: str,
        event_ts_ms: int,
        idempotency_key: str,
        details: dict[str, Any],
        created_at_ms: int | None = None,
    ) -> bool:
        """Persist a durable audit event (e.g. gap, expiration, backfill).

        Returns True if inserted, False if identical existing event verified.
        Raises ValueError if validation fails, EventConflictError if idempotency key
        conflict detected, or re-raises unrelated integrity errors.
        """
        if not isinstance(run_id, str) or not run_id:
            raise ValueError(f"invalid run_id: {run_id!r}")
        if not isinstance(event_type, str) or event_type not in self.ALLOWED_EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event_type!r}")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError(f"invalid idempotency_key: {idempotency_key!r}")
        if not isinstance(event_ts_ms, int) or isinstance(event_ts_ms, bool) or event_ts_ms < 0:
            raise ValueError(f"invalid event_ts_ms: {event_ts_ms!r}")
        created_at = created_at_ms if created_at_ms is not None else int(time.time() * 1000)
        if not isinstance(created_at, int) or isinstance(created_at, bool) or created_at < 0:
            raise ValueError(f"invalid created_at_ms: {created_at!r}")
        if not isinstance(details, dict):
            raise ValueError(f"details must be a dictionary, got {type(details)}")

        try:
            details_json = json.dumps(
                details, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid details JSON: {exc}") from exc

        try:
            self._conn.execute(
                "INSERT INTO run_events (run_id, event_type, event_ts_ms, idempotency_key,"
                " details_json, created_at_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, event_type, event_ts_ms, idempotency_key, details_json, created_at),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError as exc:
            with contextlib.suppress(Exception):
                self._conn.rollback()

            cur = self._conn.execute(
                "SELECT run_id, event_type, event_ts_ms, details_json"
                " FROM run_events WHERE idempotency_key=?",
                (idempotency_key,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise exc

            ex_run_id = existing["run_id"] if isinstance(existing, sqlite3.Row) else existing[0]
            ex_event = existing["event_type"] if isinstance(existing, sqlite3.Row) else existing[1]
            ex_ts = existing["event_ts_ms"] if isinstance(existing, sqlite3.Row) else existing[2]
            ex_details = (
                existing["details_json"] if isinstance(existing, sqlite3.Row) else existing[3]
            )

            if (
                ex_run_id == run_id
                and ex_event == event_type
                and ex_ts == event_ts_ms
                and ex_details == details_json
            ):
                return False

            raise EventConflictError(
                f"event with idempotency_key {idempotency_key!r} already exists with"
                " different contents"
            ) from exc
        except Exception:
            with contextlib.suppress(Exception):
                self._conn.rollback()
            raise

    def has_event(self, idempotency_key: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM run_events WHERE idempotency_key=?",
            (idempotency_key,),
        )
        return cur.fetchone() is not None

    def get_events(self, run_id: str) -> list[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        return list(
            self._conn.execute(
                "SELECT * FROM run_events WHERE run_id=? ORDER BY id ASC",
                (run_id,),
            )
        )
