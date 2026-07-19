"""Ledger tests: idempotency, restart recovery, session separation."""

from pathlib import Path

import pytest

from obsidian_rl.ledger.ledger import DuplicateDecisionError, Ledger
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)


def make_ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite3")


def record_one(ledger: Ledger, run_id: str, engine: PortfolioEngine, open_ms: int) -> None:
    result = engine.rebalance(1.0, 100.0)
    ledger.record_decision(
        run_id,
        candle_open_ms=open_ms,
        candle_close_ms=open_ms + 899_999,
        decision_ts_ms=open_ms + 900_000,
        data_source="test",
        result=result,
        state=engine.state,
        mark_price=100.0,
    )


def test_duplicate_candle_rejected(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path)
    run = ledger.start_run("s1", "backtest", 10_000.0, {"taker_fee": 0.001})
    eng = PortfolioEngine(PortfolioConfig(), CM)
    record_one(ledger, run.run_id, eng, 900_000)
    with pytest.raises(DuplicateDecisionError):
        record_one(ledger, run.run_id, eng, 900_000)
    assert ledger.has_processed(run.run_id, 900_000)
    assert not ledger.has_processed(run.run_id, 1_800_000)


def test_restart_recovery_restores_exact_state(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = Ledger(path)
    run = ledger.start_run("s1", "live-paper", 10_000.0, {})
    eng = PortfolioEngine(PortfolioConfig(), CM)
    eng.rebalance(1.0, 100.0)
    eng.apply_funding(100.0, 0.0001)
    result = eng.rebalance(-0.5, 110.0)
    ledger.record_decision(
        run.run_id,
        candle_open_ms=900_000,
        candle_close_ms=1_799_999,
        decision_ts_ms=1_800_000,
        data_source="test",
        result=result,
        state=eng.state,
        mark_price=110.0,
    )
    ledger.close()

    reopened = Ledger(path)
    restored = reopened.restore_state(run.run_id)
    assert restored is not None
    assert restored.cash == pytest.approx(eng.state.cash)
    assert restored.qty == pytest.approx(eng.state.qty)
    assert restored.avg_entry_price == pytest.approx(eng.state.avg_entry_price)
    assert restored.realized_pnl == pytest.approx(eng.state.realized_pnl)
    assert restored.funding_paid == pytest.approx(eng.state.funding_paid)
    assert restored.turnover == pytest.approx(eng.state.turnover)
    assert restored.trade_count == eng.state.trade_count
    assert restored.peak_equity == pytest.approx(eng.state.peak_equity)
    # equity identical after restore
    assert restored.net_equity(110.0) == pytest.approx(eng.state.net_equity(110.0))


def test_sessions_are_separate(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path)
    run_a = ledger.start_run("s1", "live-paper", 10_000.0, {})
    run_b = ledger.start_run("s1", "live-paper", 10_000.0, {})
    eng_a = PortfolioEngine(PortfolioConfig(), CM)
    eng_b = PortfolioEngine(PortfolioConfig(), CM)
    record_one(ledger, run_a.run_id, eng_a, 900_000)
    record_one(ledger, run_b.run_id, eng_b, 900_000)  # same candle, different run => fine
    assert len(ledger.decisions(run_a.run_id)) == 1
    assert len(ledger.decisions(run_b.run_id)) == 1
    assert ledger.restore_state("nonexistent") is None


def test_run_metadata_persisted(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path)
    run = ledger.start_run(
        "momentum-v1",
        "backtest",
        10_000.0,
        {"taker_fee": 0.0005},
        model_id="ppo-001",
        git_commit="abc123",
    )
    row = ledger.get_run(run.run_id)
    assert row is not None
    assert row["strategy_id"] == "momentum-v1"
    assert row["model_id"] == "ppo-001"
    assert row["git_commit"] == "abc123"
    ledger.end_run(run.run_id)
    row2 = ledger.get_run(run.run_id)
    assert row2 is not None and row2["ended_at_ms"] is not None
