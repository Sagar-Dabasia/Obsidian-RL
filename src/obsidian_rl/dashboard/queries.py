"""Ledger query layer for the dashboard (unit-tested; the Streamlit app stays thin).

Sessions (runs) are never merged: every function takes one run_id. Closed trades are
derived from ledger realized-P&L events, which handles direct reversals correctly
(a reversal row realizes the old position's P&L and opens the new one).
"""

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.ledger.ledger import Ledger


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    strategy_id: str
    model_id: str | None
    mode: str
    started_at_ms: int
    ended_at_ms: int | None
    initial_cash: float
    n_decisions: int


def list_run_summaries(ledger_path: Path) -> list[RunSummary]:
    ledger = Ledger(ledger_path)
    try:
        out = []
        for row in ledger.list_runs():
            n = len(ledger.decisions(row["run_id"]))
            out.append(
                RunSummary(
                    run_id=row["run_id"],
                    strategy_id=row["strategy_id"],
                    model_id=row["model_id"],
                    mode=row["mode"],
                    started_at_ms=row["started_at_ms"],
                    ended_at_ms=row["ended_at_ms"],
                    initial_cash=row["initial_cash"],
                    n_decisions=n,
                )
            )
        return out
    finally:
        ledger.close()


def run_frame(ledger_path: Path, run_id: str) -> pd.DataFrame:
    """All decisions of ONE run as a DataFrame (chronological)."""
    ledger = Ledger(ledger_path)
    try:
        rows = ledger.decisions(run_id)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        ledger.close()


def equity_and_drawdown(frame: pd.DataFrame) -> pd.DataFrame:
    """Equity + running-drawdown curves for one session only."""
    if frame.empty:
        return pd.DataFrame(columns=["candle_open_ms", "net_equity", "drawdown"])
    out = frame[["candle_open_ms", "net_equity"]].copy()
    peak = out["net_equity"].cummax()
    out["drawdown"] = 1.0 - out["net_equity"] / peak
    return out


def kpis(frame: pd.DataFrame, initial_cash: float) -> dict[str, float]:
    if frame.empty:
        return {}
    last = frame.iloc[-1]
    return {
        "position_qty": float(last["position_qty"]),
        "executed_target": float(last["executed_target"]),
        "cash": float(last["cash"]),
        "realized_pnl": float(last["realized_pnl_total"]),
        "unrealized_pnl": float(last["unrealized_pnl"]),
        "net_equity": float(last["net_equity"]),
        "net_return_pct": float(last["net_equity"] / initial_cash - 1.0) * 100.0,
        "fees": float(last["fees_total"]),
        "spread": float(last["spread_total"]),
        "slippage": float(last["slippage_total"]),
        "funding": float(last["funding_total"]),
        "turnover": float(last["turnover_total"]),
        "trade_count": float(last["trade_count"]),
        "rejected_actions": float((frame["rejection_reason"].notna()).sum()),
    }


def closed_trade_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Realized-P&L events (including reversals), not flat-transition inference."""
    if frame.empty:
        return pd.DataFrame()
    events = frame[frame["realized_pnl_delta"] != 0.0]
    return events[
        ["candle_open_ms", "exec_price", "delta_qty", "realized_pnl_delta", "position_qty"]
    ].copy()


def warnings_for_run(
    frame: pd.DataFrame,
    *,
    interval: str = "15m",
    now_ms: int | None = None,
    run_ended: bool = False,
) -> list[str]:
    if frame.empty:
        return ["no decisions recorded yet"]
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    ms = interval_to_ms(interval)
    warnings: list[str] = []

    last_candle = int(frame["candle_open_ms"].iloc[-1])
    if not run_ended and now - (last_candle + ms) > 3 * ms:
        age_min = (now - last_candle - ms) / 60_000
        warnings.append(f"stale data: last processed candle is {age_min:.0f} minutes old")

    deltas = frame["candle_open_ms"].diff().iloc[1:]
    n_gaps = int((deltas != ms).sum())
    if n_gaps:
        warnings.append(f"{n_gaps} gap(s) in processed candle sequence")

    rejected = int(frame["rejection_reason"].notna().sum())
    if rejected:
        warnings.append(f"{rejected} decision(s) carried a rejection/clamp reason")

    # restarts: created_at gaps much larger than candle cadence while candles are contiguous
    created_gaps = frame["created_at_ms"].diff().iloc[1:]
    restarts = int(((created_gaps > 3 * ms) & (deltas == ms)).sum())
    if restarts:
        warnings.append(f"{restarts} probable restart(s)/catch-up batch(es)")

    return warnings
