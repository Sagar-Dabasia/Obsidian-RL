"""Performance metrics computed from a backtest equity curve and final state summary.

Sharpe here is annualized from per-candle net-equity log returns (96 candles/day * 365);
it assumes i.i.d. returns, which crypto violates — reported with that caveat, never alone.
Win rate is per rebalance-with-realized-P&L, not per round trip; stated in reports.
"""

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

CANDLES_PER_YEAR_15M = 96 * 365


@dataclass(frozen=True)
class Metrics:
    strategy_id: str
    net_return: float
    gross_return: float
    fees: float
    spread: float
    slippage: float
    funding: float
    turnover: float
    trade_count: int
    mean_abs_exposure: float
    max_drawdown: float
    sharpe: float
    n_candles: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compute_metrics(
    strategy_id: str,
    equity_curve: pd.DataFrame,
    summary: dict[str, float],
    *,
    candles_per_year: int = CANDLES_PER_YEAR_15M,
) -> Metrics:
    eq = equity_curve["equity"].to_numpy(dtype=np.float64)
    initial = float(summary["initial_cash"])
    final = float(summary["final_equity"])
    total_costs = summary["fees"] + summary["spread"] + summary["slippage"] + summary["funding"]

    net_return = final / initial - 1.0
    gross_return = (final + total_costs) / initial - 1.0

    with np.errstate(divide="ignore", invalid="ignore"):
        log_eq = np.log(np.maximum(eq, 1e-9))
    rets = np.diff(log_eq)
    if len(rets) > 1 and float(np.std(rets)) > 0:
        sharpe = float(np.mean(rets) / np.std(rets) * math.sqrt(candles_per_year))
    else:
        sharpe = 0.0

    return Metrics(
        strategy_id=strategy_id,
        net_return=net_return,
        gross_return=gross_return,
        fees=summary["fees"],
        spread=summary["spread"],
        slippage=summary["slippage"],
        funding=summary["funding"],
        turnover=summary["turnover"],
        trade_count=int(summary["trade_count"]),
        mean_abs_exposure=float(equity_curve["exposure"].abs().mean()),
        max_drawdown=float(equity_curve["drawdown"].max()),
        sharpe=sharpe,
        n_candles=len(equity_curve),
    )


def trade_stats(realized_deltas: list[float]) -> dict[str, float]:
    """Win rate and profit factor over realized P&L events (limitations documented)."""
    events = [d for d in realized_deltas if d != 0.0]
    if not events:
        return {"win_rate": float("nan"), "profit_factor": float("nan"), "n_events": 0.0}
    wins = [d for d in events if d > 0]
    losses = [-d for d in events if d < 0]
    win_rate = len(wins) / len(events)
    profit_factor = (sum(wins) / sum(losses)) if losses and sum(losses) > 0 else float("inf")
    return {"win_rate": win_rate, "profit_factor": profit_factor, "n_events": float(len(events))}
