"""Live-paper trader tests: replay/backtest parity, idempotency, gaps, restart recovery,
fail-flat, websocket event parsing."""

import copy
from pathlib import Path

import numpy as np
import pytest

from obsidian_rl.evaluation.backtest import run_backtest
from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.ledger.ledger import EventConflictError, Ledger
from obsidian_rl.live.paper_trader import (
    BUFFER_SIZE,
    CandleSequenceError,
    PaperTrader,
    replay_candles,
)
from obsidian_rl.live.stream import parse_kline_event
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.baselines import ThresholdMomentum
from tests.conftest import make_candles

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)


def make_trader(tmp_path: Path, run_suffix: str = "a") -> tuple[PaperTrader, Ledger, str]:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("threshold-momentum", "replay", 10_000.0, {})
    trader = PaperTrader(
        ThresholdMomentum(0.002), ledger, run.run_id, cost_model=CM, data_source="replay"
    )
    return trader, ledger, run.run_id


def test_replay_matches_backtest_exactly(tmp_path: Path) -> None:
    """THE parity gate: identical candles + strategy => identical accounting."""
    candles = make_candles(WARMUP_ROWS + 250, seed=5)

    bt = run_backtest(candles, ThresholdMomentum(0.002), cost_model=CM)

    trader, ledger, run_id = make_trader(tmp_path)
    n = replay_candles(trader, candles)
    trader.close_session(float(candles["close"].iloc[-1]))

    assert n == bt.n_decisions
    s = trader.engine.state
    bs = bt.final_state_summary
    assert s.qty == 0.0
    assert s.net_equity(float(candles["close"].iloc[-1])) == pytest.approx(
        bs["final_equity"], abs=1e-9
    )
    assert s.realized_pnl == pytest.approx(bs["realized_pnl"], abs=1e-9)
    assert s.fees_paid == pytest.approx(bs["fees"], abs=1e-9)
    assert s.spread_paid == pytest.approx(bs["spread"], abs=1e-9)
    assert s.turnover == pytest.approx(bs["turnover"], abs=1e-9)
    assert s.trade_count == int(bs["trade_count"])
    assert len(ledger.decisions(run_id)) == n

    closure = ledger.get_closure(run_id)
    assert closure is not None
    assert closure["position_qty"] == 0.0
    assert closure["net_equity"] == pytest.approx(bs["final_equity"], abs=1e-9)
    assert closure["realized_pnl_total"] == pytest.approx(bs["realized_pnl"], abs=1e-9)
    assert closure["fees_total"] == pytest.approx(bs["fees"], abs=1e-9)
    assert closure["turnover_total"] == pytest.approx(bs["turnover"], abs=1e-9)
    assert closure["trade_count"] == int(bs["trade_count"])


def test_duplicate_candles_ignored(tmp_path: Path) -> None:
    candles = make_candles(WARMUP_ROWS + 10)
    trader, ledger, run_id = make_trader(tmp_path)
    replay_candles(trader, candles)
    rows_before = len(ledger.decisions(run_id))
    # feed the last candle again: duplicate must be ignored, no new ledger row
    last = {c: candles.iloc[-1][c] for c in candles.columns}
    assert trader.on_finalized_candle(last) is None
    assert len(ledger.decisions(run_id)) == rows_before


def test_gap_raises_for_backfill(tmp_path: Path) -> None:
    candles = make_candles(WARMUP_ROWS + 10)
    trader, _, _ = make_trader(tmp_path)
    replay_candles(trader, candles.iloc[:-3])
    skipped = {c: candles.iloc[-1][c] for c in candles.columns}  # skips two candles
    with pytest.raises(CandleSequenceError, match="gap"):
        trader.on_finalized_candle(skipped)


def test_restart_recovery_matches_uninterrupted_run(tmp_path: Path) -> None:
    candles = make_candles(WARMUP_ROWS + 200, seed=8)
    split = WARMUP_ROWS + 120

    # uninterrupted reference
    ref_trader, _, _ = make_trader(tmp_path / "ref")
    replay_candles(ref_trader, candles)

    # interrupted run: process first part, then restore into a NEW trader
    ledger_path = tmp_path / "live" / "ledger.sqlite3"
    ledger = Ledger(ledger_path)
    run = ledger.start_run("threshold-momentum", "live-paper", 10_000.0, {})
    t1 = PaperTrader(
        ThresholdMomentum(0.002), ledger, run.run_id, cost_model=CM, data_source="replay"
    )
    replay_candles(t1, candles.iloc[:split])
    ledger.close()

    ledger2 = Ledger(ledger_path)
    t2 = PaperTrader(
        ThresholdMomentum(0.002), ledger2, run.run_id, cost_model=CM, data_source="replay"
    )
    state = ledger2.restore_state(run.run_id)
    assert state is not None
    t2.restore(state, candles.iloc[:split])
    # NOTE: replay includes already-processed candles; idempotency must skip them
    replay_candles(t2, candles)

    price = float(candles["close"].iloc[-1])
    assert t2.engine.state.net_equity(price) == pytest.approx(
        ref_trader.engine.state.net_equity(price), rel=1e-6
    )
    assert t2.engine.state.qty == pytest.approx(ref_trader.engine.state.qty, rel=1e-6)
    assert len(ledger2.decisions(run.run_id)) == WARMUP_ROWS + 200 - 1 - WARMUP_ROWS


def test_carried_pending_executes_after_backfill_batch(tmp_path: Path) -> None:
    """Regression (review, CRITICAL): a decision made for candle c_L, carried into a
    backfill batch that STARTS at c_{L+1}, must still execute at open[L+1] — not be
    overwritten by the first on_finalized_candle of the batch."""
    candles = make_candles(WARMUP_ROWS + 60, seed=8)
    split = WARMUP_ROWS + 40

    # Uninterrupted reference.
    ref, _, _ = make_trader(tmp_path / "ref")
    replay_candles(ref, candles)
    ref_price = float(candles["close"].iloc[-1])

    # Interrupted: process a prefix, then simulate crash-after-decision by restoring and
    # feeding the remaining candles as a fresh batch that begins at the execution candle.
    ledger_path = tmp_path / "live" / "ledger.sqlite3"
    ledger = Ledger(ledger_path)
    run = ledger.start_run("threshold-momentum", "live-paper", 10_000.0, {})
    t1 = PaperTrader(ThresholdMomentum(0.002), ledger, run.run_id, cost_model=CM)
    replay_candles(t1, candles.iloc[:split])
    ledger.close()

    ledger2 = Ledger(ledger_path)
    t2 = PaperTrader(ThresholdMomentum(0.002), ledger2, run.run_id, cost_model=CM)
    state = ledger2.restore_state(run.run_id)
    assert state is not None
    t2.restore(state, candles.iloc[:split])
    # restore recomputes the pending decision for candle split-1 (never executed by t1)
    assert t2.pending is not None
    assert t2.pending.candle_open_ms == int(candles["open_time"].iloc[split - 1])
    # feed ONLY the remaining candles (a backfill batch beginning at the execution candle)
    replay_candles(t2, candles.iloc[split:])

    assert t2.engine.state.qty == pytest.approx(ref.engine.state.qty, rel=1e-6)
    assert t2.engine.state.net_equity(ref_price) == pytest.approx(
        ref.engine.state.net_equity(ref_price), rel=1e-6
    )
    # the carried decision for candle split-1 produced a ledger row (no missing trade)
    assert ledger2.has_processed(run.run_id, int(candles["open_time"].iloc[split - 1]))


def test_strategy_failure_fails_flat(tmp_path: Path) -> None:
    class ExplodingStrategy:
        strategy_id = "exploding"

        def reset(self) -> None:
            return None

        def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
            raise RuntimeError("model file corrupted")

    ledger = Ledger(tmp_path / "ledger.sqlite3")
    run = ledger.start_run("exploding", "replay", 10_000.0, {})
    trader = PaperTrader(ExplodingStrategy(), ledger, run.run_id, cost_model=CM)
    candles = make_candles(WARMUP_ROWS + 5)
    replay_candles(trader, candles)
    assert trader.engine.state.qty == 0.0  # stayed flat, never crashed
    rows = ledger.decisions(run.run_id)
    assert all(r["proposed_target"] == 0.0 for r in rows)


def test_parse_kline_event_official_payload() -> None:
    raw = (
        '{"e":"kline","E":1607443058651,"s":"BTCUSDT","k":{'
        '"t":1607443020000,"T":1607443079999,"s":"BTCUSDT","i":"1m",'
        '"f":116467658886,"L":116468012423,"o":"18787.00","c":"18804.04",'
        '"h":"18804.04","l":"18786.54","v":"197.664","n":543,"x":false,'
        '"q":"3715253.19494","V":"184.769","Q":"3472925.84746","B":"0"}}'
    )
    event = parse_kline_event(raw)
    assert event is not None
    assert event.open_time == 1607443020000
    assert event.is_closed is False
    assert event.open == 18787.00
    assert event.trades == 543
    assert parse_kline_event('{"result":null,"id":1}') is None


def test_ledger_survives_full_replay_twice(tmp_path: Path) -> None:
    candles = make_candles(WARMUP_ROWS + 30)
    trader, ledger, run_id = make_trader(tmp_path)
    n1 = replay_candles(trader, candles)
    rows1 = len(ledger.decisions(run_id))
    # a second full replay through the same trader adds nothing
    n2 = replay_candles(trader, candles)
    assert n2 == 0
    assert len(ledger.decisions(run_id)) == rows1 == n1


def test_close_session_idempotence(tmp_path: Path) -> None:
    candles = make_candles(WARMUP_ROWS + 30)
    trader, ledger, run_id = make_trader(tmp_path)
    replay_candles(trader, candles)
    mark = float(candles["close"].iloc[-1])
    trader.close_session(mark)
    fees1 = trader.engine.state.fees_paid
    trades1 = trader.engine.state.trade_count
    c1 = dict(ledger.get_closure(run_id))  # type: ignore[arg-type]

    # second call with same or different price must not double-charge or duplicate closure
    trader.close_session(mark + 10.0)
    assert trader.engine.state.fees_paid == pytest.approx(fees1)
    assert trader.engine.state.trade_count == trades1
    c2 = dict(ledger.get_closure(run_id))  # type: ignore[arg-type]
    assert c1["terminal_ts_ms"] == c2["terminal_ts_ms"]
    assert c1["net_equity"] == c2["net_equity"]


def test_close_session_invalid_mark_price(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    for bad_price in (float("nan"), float("inf"), -10.0, 0.0):
        with pytest.raises(ValueError, match="invalid mark_price"):
            trader.close_session(bad_price)
    assert ledger.get_closure(run_id) is None
    run_row = ledger.get_run(run_id)
    assert run_row is not None
    assert run_row["ended_at_ms"] is None


def test_close_session_already_flat(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 2)
    replay_candles(trader, candles)
    # force portfolio flat if not already
    if trader.engine.state.qty != 0.0:
        trader.engine.rebalance(0.0, 100.0)
    assert trader.engine.state.qty == 0.0
    trader.close_session(100.0)
    closure = ledger.get_closure(run_id)
    assert closure is not None
    assert closure["position_qty"] == 0.0
    assert closure["fee"] == 0.0
    assert closure["spread_cost"] == 0.0
    assert closure["slippage_cost"] == 0.0


def test_close_session_persistence_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 10)
    replay_candles(trader, candles)

    def _fail(*args: object, **kwargs: object) -> object:
        raise RuntimeError("db error")

    monkeypatch.setattr(ledger, "finalize_run", _fail)
    pre_state = copy.copy(trader.engine.state)
    pre_pending = copy.copy(trader.pending)
    with pytest.raises(RuntimeError, match="db error"):
        trader.close_session(100.0)
    assert trader.engine.state == copy.copy(pre_state)
    assert trader.pending == pre_pending
    run_row = ledger.get_run(run_id)
    assert run_row is not None and run_row["ended_at_ms"] is None


def test_close_session_retry_after_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 10)
    replay_candles(trader, candles)

    orig_finalize = ledger.finalize_run

    def _fail(*args: object, **kwargs: object) -> object:
        raise RuntimeError("db error")

    monkeypatch.setattr(ledger, "finalize_run", _fail)
    with pytest.raises(RuntimeError, match="db error"):
        trader.close_session(100.0)

    monkeypatch.setattr(ledger, "finalize_run", orig_finalize)
    trader.close_session(100.0)
    closure = ledger.get_closure(run_id)
    assert closure is not None
    assert closure["position_qty"] == 0.0
    run_row = ledger.get_run(run_id)
    assert run_row is not None and run_row["ended_at_ms"] is not None


def test_closed_run_restore_and_replay_no_op(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 10)
    replay_candles(trader, candles)
    trader.close_session(100.0)

    # Re-instantiate and restore closed run
    trader2 = PaperTrader(trader.strategy, ledger, run_id)
    state = ledger.restore_state(run_id)
    assert state is not None
    assert state.qty == 0.0
    trader2.restore(state, candles)
    assert trader2.pending is None

    n = replay_candles(trader2, candles)
    assert n == 0
    assert trader2.pending is None
    assert trader2.engine.state.qty == 0.0


def test_replay_candles_inconsistent_state_raises(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 10)
    replay_candles(trader, candles)

    # Manually set ended_at_ms without creating a closure
    ledger._conn.execute("UPDATE runs SET ended_at_ms = 12345 WHERE run_id = ?", (run_id,))
    with pytest.raises(RuntimeError, match="inconsistent closure/ended state"):
        replay_candles(trader, candles)


def test_ingest_observation_and_expire_pending(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 5)
    for i in range(len(candles)):
        c = dict(candles.iloc[i])
        trader.ingest_observation(c)

    assert len(trader.buffer) == min(len(candles), BUFFER_SIZE)
    assert trader.pending is None
    assert trader.last_finalized_ms == int(candles["open_time"].iloc[-1])
    assert trader.engine.state.trade_count == 0

    # Now create a pending decision via on_finalized_candle
    next_c = dict(make_candles(1, start_ms=trader.last_finalized_ms + trader.interval_ms).iloc[0])
    trader.on_finalized_candle(next_c)
    assert trader.pending is not None

    # Expire pending
    expired = trader.expire_pending("missed_test_window", now_ms=1700000000000)
    assert expired is True
    assert trader.pending is None
    assert ledger.has_event(f"{run_id}:pending_expired:{int(next_c['open_time'])}") is True


def test_restore_stale_pending_expiration(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 5)
    replay_candles(trader, candles)
    # Replay left trader.pending set or processed up to last candle
    last_ms = int(candles["open_time"].iloc[-1])
    if trader.pending is None:
        trader.pending = trader._decide(dict(candles.iloc[-1]))

    # Restore with now_ms well past the execution window + max_live_open_lag_ms
    state = trader.engine.state
    trader2 = PaperTrader(trader.strategy, ledger, run_id, max_live_open_lag_ms=5000)
    stale_now = last_ms + trader.interval_ms + 10_000
    trader2.restore(state, candles, now_ms=stale_now)
    assert trader2.pending is None
    assert ledger.has_event(f"{run_id}:pending_expired:{last_ms}") is True


def test_expire_pending_failure_or_conflict_leaves_pending_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 5)
    replay_candles(trader, candles)
    if trader.pending is None:
        trader.pending = trader._decide(dict(candles.iloc[-1]))
    assert trader.pending is not None
    pending_backup = copy.deepcopy(trader.pending)

    # 1. DB persistence failure leaves pending unchanged and re-raises
    def _raise(*args: object, **kwargs: object) -> object:
        raise RuntimeError("db persistence error")

    monkeypatch.setattr(ledger, "record_event", _raise)
    with pytest.raises(RuntimeError, match="db persistence error"):
        trader.expire_pending("test_reason")
    assert trader.pending == pending_backup

    monkeypatch.undo()

    # 2. Conflicting existing event raises EventConflictError and leaves pending unchanged
    idempotency_key = f"{run_id}:pending_expired:{trader.pending.candle_open_ms}"
    ledger.record_event(
        run_id=run_id,
        event_type="pending_execution_expired",
        event_ts_ms=1700000000000,
        idempotency_key=idempotency_key,
        details={"conflicting": "details"},
    )
    with pytest.raises(EventConflictError, match="already exists with different contents"):
        trader.expire_pending("test_reason", now_ms=1700000000000)
    assert trader.pending == pending_backup
    ledger.close()


def test_expire_pending_identical_retry_clears_pending(tmp_path: Path) -> None:
    trader, ledger, run_id = make_trader(tmp_path)
    candles = make_candles(WARMUP_ROWS + 5)
    replay_candles(trader, candles)
    if trader.pending is None:
        trader.pending = trader._decide(dict(candles.iloc[-1]))
    assert trader.pending is not None

    expected_open = trader.pending.candle_open_ms + trader.interval_ms
    idempotency_key = f"{run_id}:pending_expired:{trader.pending.candle_open_ms}"
    details = {
        "pending_source_open_ms": trader.pending.candle_open_ms,
        "expected_execution_open_ms": expected_open,
        "expiration_reason": "retry_reason",
        "proposed_target": trader.pending.proposed_target,
    }
    # Pre-insert exact identical event
    ledger.record_event(
        run_id=run_id,
        event_type="pending_execution_expired",
        event_ts_ms=1700000000000,
        idempotency_key=idempotency_key,
        details=details,
        created_at_ms=1700000000000,
    )

    # Now expire_pending should see identical existing event and clear pending without raising
    success = trader.expire_pending("retry_reason", now_ms=1700000000000)
    assert success is True
    assert trader.pending is None
    ledger.close()
