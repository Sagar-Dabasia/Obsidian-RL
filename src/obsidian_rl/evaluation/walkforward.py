"""Walk-forward evaluation: chronological folds, purge gaps, multi-seed PPO, fixed holdout.

Rules enforced here:
- folds never touch data at/after `holdout_start_ms` (the untouched final test period);
- a purge gap of `purge_candles` separates each fold's training end from its validation
  start (feature warm-up and any forward-label horizon cannot straddle the boundary);
- every strategy (baselines and each PPO seed) is evaluated on identical validation
  slices with identical costs and timing;
- the holdout is run once, explicitly, for one selected configuration
  (`run_holdout`), never inside fold iteration.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.evaluation.backtest import run_backtest
from obsidian_rl.evaluation.metrics import Metrics, compute_metrics
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.base import Strategy

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000


@dataclass(frozen=True)
class FoldSpec:
    fold_id: int
    train_start_ms: int
    train_end_ms: int
    val_start_ms: int
    val_end_ms: int


def make_folds(
    data_start_ms: int,
    holdout_start_ms: int,
    *,
    interval: str = "15m",
    train_days: int = 540,
    val_days: int = 120,
    step_days: int = 120,
    purge_candles: int = WARMUP_ROWS,
) -> list[FoldSpec]:
    """Rolling chronological folds; validation slices never overlap the holdout."""
    ms = interval_to_ms(interval)
    purge_ms = purge_candles * ms
    folds: list[FoldSpec] = []
    fold_id = 0
    train_start = data_start_ms
    while True:
        train_end = train_start + train_days * DAY_MS
        val_start = train_end + purge_ms
        val_end = val_start + val_days * DAY_MS
        if val_end > holdout_start_ms:
            break
        folds.append(FoldSpec(fold_id, train_start, train_end - 1, val_start, val_end - 1))
        fold_id += 1
        train_start += step_days * DAY_MS
    if not folds:
        raise ValueError("no folds fit between data start and holdout start")
    return folds


def slice_candles(candles: pd.DataFrame, start_ms: int, end_ms: int) -> pd.DataFrame:
    out = candles[(candles["open_time"] >= start_ms) & (candles["open_time"] <= end_ms)]
    return out.reset_index(drop=True)


@dataclass
class EvalRow:
    fold_id: int
    strategy_id: str
    seed: int | None
    scenario: str  # base | costs2x | delay1
    metrics: Metrics
    val_buy_hold_return: float  # regime descriptor for the fold's validation period

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "fold_id": self.fold_id,
            "strategy_id": self.strategy_id,
            "seed": self.seed,
            "scenario": self.scenario,
            "val_buy_hold_return": self.val_buy_hold_return,
        }
        d.update(self.metrics.to_dict())
        return d


def _scenarios(base_costs: CostModel) -> list[tuple[str, CostModel, int]]:
    doubled = CostModel(
        taker_fee=base_costs.taker_fee * 2,
        half_spread=base_costs.half_spread * 2,
        slippage=base_costs.slippage * 2,
    )
    return [("base", base_costs, 0), ("costs2x", doubled, 0), ("delay1", base_costs, 1)]


def evaluate_strategies_on_slice(
    val_candles: pd.DataFrame,
    strategies: list[tuple[str, Strategy, int | None]],
    *,
    fold_id: int,
    cost_model: CostModel,
    sensitivity: bool = True,
) -> list[EvalRow]:
    """Evaluate (label, strategy, seed) tuples under identical conditions + scenarios."""
    bh_return = float(val_candles["close"].iloc[-1] / val_candles["close"].iloc[WARMUP_ROWS] - 1.0)
    scenarios = _scenarios(cost_model) if sensitivity else [("base", cost_model, 0)]
    rows: list[EvalRow] = []
    for label, strategy, seed in strategies:
        for scenario_name, costs, delay in scenarios:
            res = run_backtest(val_candles, strategy, cost_model=costs, signal_delay=delay)
            m = compute_metrics(label, res.equity_curve, res.final_state_summary)
            rows.append(EvalRow(fold_id, label, seed, scenario_name, m, bh_return))
    return rows


def save_results(rows: list[EvalRow], out_dir: Path, extra: dict[str, Any] | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"walkforward-{stamp}.json"
    payload = {"created": stamp, "extra": extra or {}, "rows": [r.to_dict() for r in rows]}
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    frame = pd.DataFrame([r.to_dict() for r in rows])
    frame.to_csv(path.with_suffix(".csv"), index=False)
    return path


def summarize(rows: list[EvalRow]) -> pd.DataFrame:
    """Aggregate across folds/seeds: mean/std of net return, Sharpe, max DD per strategy."""
    frame = pd.DataFrame([r.to_dict() for r in rows])
    base = frame[frame["scenario"] == "base"]
    agg = base.groupby("strategy_id").agg(
        folds=("fold_id", "nunique"),
        runs=("net_return", "size"),
        mean_net_return=("net_return", "mean"),
        std_net_return=("net_return", "std"),
        min_net_return=("net_return", "min"),
        mean_sharpe=("sharpe", "mean"),
        mean_max_dd=("max_drawdown", "mean"),
        mean_turnover=("turnover", "mean"),
        mean_trades=("trade_count", "mean"),
    )
    return agg.sort_values("mean_net_return", ascending=False)
