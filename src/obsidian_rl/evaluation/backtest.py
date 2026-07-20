"""Shared backtest runner: the single decision/execution loop for baselines and RL.

Timing model (ADR-003): the policy observes candle t after it closes (features from
candles <= t, portfolio marked at close[t]) and the resulting order executes at the OPEN
of candle t+1 — never at the price that generated the observation. The final open
position is liquidated at the last candle's close (documented terminal convention).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.features.pipeline import WARMUP_ROWS, compute_market_features
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine
from obsidian_rl.strategies.base import Strategy

DEFAULT_TARGETS: tuple[float, ...] = (-1.0, -0.5, 0.0, 0.5, 1.0)

#: window (in candles) for "recent turnover" and "time in position" normalization
ROLLING_WINDOW = 96


@dataclass
class BacktestResult:
    strategy_id: str
    equity_curve: pd.DataFrame  # columns: open_time, close, equity, exposure, drawdown
    final_state_summary: dict[str, float]
    n_decisions: int


def snap_target(target: float, allowed: tuple[float, ...]) -> float:
    return min(allowed, key=lambda a: abs(a - target))


class PortfolioFeatureTracker:
    """Derives the 5 portfolio observation features from engine state (shared logic)."""

    def __init__(self) -> None:
        self.steps_in_position = 0
        self._turnover_history: list[float] = []
        self._last_qty_sign = 0

    def reset(self) -> None:
        self.steps_in_position = 0
        self._turnover_history = []
        self._last_qty_sign = 0

    def update_after_step(self, qty: float, turnover_delta: float) -> None:
        sign = 0 if qty == 0.0 else (1 if qty > 0 else -1)
        if sign == 0 or sign != self._last_qty_sign:
            self.steps_in_position = 0
        if sign != 0:
            self.steps_in_position += 1
        self._last_qty_sign = sign
        self._turnover_history.append(turnover_delta)
        if len(self._turnover_history) > ROLLING_WINDOW:
            self._turnover_history.pop(0)

    def observe(self, engine: PortfolioEngine, mark_price: float) -> PortfolioObs:
        s = engine.state
        equity = s.net_equity(mark_price)
        safe_equity = max(equity, 1e-9)
        return PortfolioObs(
            exposure=float(np.clip(s.exposure(mark_price), -3.0, 3.0)),
            unrealized_return=float(np.clip(s.unrealized_pnl(mark_price) / safe_equity, -3, 3)),
            time_in_position=min(self.steps_in_position / ROLLING_WINDOW, 1.0),
            recent_turnover=float(np.clip(sum(self._turnover_history) / safe_equity, 0, 10)),
            drawdown=s.drawdown(mark_price),
        )


def run_backtest(
    candles: pd.DataFrame,
    strategy: Strategy,
    *,
    portfolio_config: PortfolioConfig | None = None,
    cost_model: CostModel | None = None,
    allowed_targets: tuple[float, ...] = DEFAULT_TARGETS,
    funding_rates: pd.DataFrame | None = None,
    signal_delay: int = 0,
) -> BacktestResult:
    """Run one chronological pass. `candles` must be a validated canonical frame.

    funding_rates: optional frame with columns (funding_time_ms, funding_rate); events
    are applied at the first candle whose span contains the funding timestamp.

    signal_delay: execution-delay sensitivity knob. With delay d, the policy acts on the
    market features of candle t-d (portfolio state stays current) while still executing
    at open[t+1] — i.e. the information-to-execution lag grows by d candles.
    """
    if signal_delay < 0:
        raise ValueError("signal_delay must be >= 0")
    if len(candles) <= WARMUP_ROWS + 1 + signal_delay:
        raise ValueError(f"need more than {WARMUP_ROWS + 1 + signal_delay} candles")

    engine = PortfolioEngine(portfolio_config or PortfolioConfig(), cost_model or CostModel())
    tracker = PortfolioFeatureTracker()
    strategy.reset()

    feats = compute_market_features(candles).to_numpy(dtype=np.float32)
    open_time = candles["open_time"].to_numpy(dtype=np.int64)
    open_px = candles["open"].to_numpy(dtype=np.float64)
    close_px = candles["close"].to_numpy(dtype=np.float64)
    close_time = candles["close_time"].to_numpy(dtype=np.int64)

    funding_events: list[tuple[int, float]] = []
    if funding_rates is not None:
        funding_events = [
            (int(r.funding_time_ms), float(r.funding_rate))
            for r in funding_rates.itertuples(index=False)
        ]
        funding_events.sort()
    f_idx = 0

    records: list[tuple[int, float, float, float, float]] = []
    n_decisions = 0

    for t in range(WARMUP_ROWS + signal_delay, len(candles) - 1):
        mark = close_px[t]
        obs_port = tracker.observe(engine, mark)
        proposed = strategy.propose(feats[t - signal_delay], obs_port)
        target = snap_target(float(proposed), allowed_targets)

        exec_price = open_px[t + 1]
        result = engine.rebalance(target, exec_price)
        n_decisions += 1

        # Drop funding events that fall before the first executed candle's span (the
        # warm-up region, where the book was flat so funding is 0); otherwise a stale
        # head event would pin f_idx and silently block every later in-window event.
        while f_idx < len(funding_events) and funding_events[f_idx][0] < open_time[t + 1]:
            f_idx += 1
        # funding events inside candle t+1's span, applied at its close mark
        while f_idx < len(funding_events) and funding_events[f_idx][0] <= close_time[t + 1]:
            engine.apply_funding(close_px[t + 1], funding_events[f_idx][1])
            f_idx += 1

        tracker.update_after_step(engine.state.qty, result.traded_notional)
        eq = engine.state.net_equity(close_px[t + 1])
        engine.mark_to_market(close_px[t + 1])
        records.append(
            (
                int(open_time[t + 1]),
                float(close_px[t + 1]),
                float(eq),
                float(engine.state.exposure(close_px[t + 1])),
                float(engine.state.drawdown(close_px[t + 1])),
            )
        )

    engine.liquidate(close_px[-1])

    curve = pd.DataFrame(records, columns=["open_time", "close", "equity", "exposure", "drawdown"])
    s = engine.state
    summary = {
        "initial_cash": engine.config.initial_cash,
        "final_equity": s.net_equity(close_px[-1]),
        "realized_pnl": s.realized_pnl,
        "fees": s.fees_paid,
        "spread": s.spread_paid,
        "slippage": s.slippage_paid,
        "funding": s.funding_paid,
        "turnover": s.turnover,
        "trade_count": float(s.trade_count),
    }
    return BacktestResult(
        strategy_id=strategy.strategy_id,
        equity_curve=curve,
        final_state_summary=summary,
        n_decisions=n_decisions,
    )
