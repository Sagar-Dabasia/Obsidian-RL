"""Walk-forward evaluation: chronological folds, purge gaps, multi-seed PPO, fixed holdout.

Rules enforced here:
- nested chronological folds: training period -> purge gap -> inner selection/evaluation -> purge gap -> untouched outer validation;
- outer-validation candles must never be passed to `train_ppo`, `EvalCallback`, fitting, or selection;
- folds never touch data at/after `holdout_start_ms` (the untouched final test period);
- a purge gap of `purge_candles` separates each fold's training end from inner eval start, and inner eval end from outer validation start;
- every strategy (baselines and each PPO seed) is evaluated on identical outer validation slices with identical costs and timing;
- the holdout is run once, explicitly, for one selected configuration (`run_holdout`), never inside fold iteration.
"""

import hashlib
import json
import logging
import time
import uuid
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


def create_experiment_id() -> str:
    """Create a collision-resistant walk-forward experiment ID."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    us = int(time.time() * 1_000_000) % 1_000_000
    return f"wf-{stamp}-{us:06d}-{uuid.uuid4().hex[:8]}"


def slice_sha256(df: pd.DataFrame) -> str:
    """Compute exact, deterministic SHA-256 digest of dataframe contents."""
    if df.empty:
        return hashlib.sha256(b"").hexdigest()
    h = hashlib.sha256()
    for col in df.columns:
        h.update(col.encode("utf-8"))
        arr = df[col].to_numpy()
        h.update(arr.dtype.str.encode("utf-8"))
        h.update(arr.tobytes())
    return h.hexdigest()


@dataclass(frozen=True)
class FoldSlice:
    name: str  # "train", "purge_1", "inner_eval", "purge_2", "outer_val"
    start_ms: int
    end_ms: int
    rows: int
    sha256: str
    inclusive_bounds: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "rows": self.rows,
            "sha256": self.sha256,
            "inclusive_bounds": self.inclusive_bounds,
        }


@dataclass(frozen=True)
class FoldSpec:
    fold_id: int
    interval: str
    purge_candles: int
    warmup_rows: int
    train_days: int
    inner_eval_days: int
    val_days: int
    train: FoldSlice
    purge_1: FoldSlice
    inner_eval: FoldSlice
    purge_2: FoldSlice
    outer_val: FoldSlice

    @property
    def train_start_ms(self) -> int:
        return self.train.start_ms

    @property
    def train_end_ms(self) -> int:
        return self.train.end_ms

    @property
    def val_start_ms(self) -> int:
        return self.outer_val.start_ms

    @property
    def val_end_ms(self) -> int:
        return self.outer_val.end_ms

    @property
    def inner_eval_start_ms(self) -> int:
        return self.inner_eval.start_ms

    @property
    def inner_eval_end_ms(self) -> int:
        return self.inner_eval.end_ms

    def populate_and_validate(self, candles: pd.DataFrame) -> "FoldSpec":
        """Slice `candles`, compute exact row counts and sha256 digests, and verify all invariants."""
        tr_df = slice_candles(candles, self.train.start_ms, self.train.end_ms)
        p1_df = slice_candles(candles, self.purge_1.start_ms, self.purge_1.end_ms)
        ie_df = slice_candles(candles, self.inner_eval.start_ms, self.inner_eval.end_ms)
        p2_df = slice_candles(candles, self.purge_2.start_ms, self.purge_2.end_ms)
        ov_df = slice_candles(candles, self.outer_val.start_ms, self.outer_val.end_ms)

        if (
            len(tr_df) == 0
            or len(p1_df) == 0
            or len(ie_df) == 0
            or len(p2_df) == 0
            or len(ov_df) == 0
        ):
            raise ValueError(f"empty slice detected in fold {self.fold_id}")
        if len(p1_df) != self.purge_candles or len(p2_df) != self.purge_candles:
            raise ValueError(
                f"purge gap size mismatch in fold {self.fold_id}: expected {self.purge_candles} candles"
            )

        from obsidian_rl.evaluation.holdout import get_holdout_start_ms

        h_ms = get_holdout_start_ms()
        if not ov_df.empty and int(ov_df["open_time"].max()) >= h_ms:
            raise ValueError(
                f"outer validation candle touches or exceeds holdout start in fold {self.fold_id}"
            )
        if (
            tr_df["open_time"].max() >= p1_df["open_time"].min()
            or p1_df["open_time"].max() >= ie_df["open_time"].min()
            or ie_df["open_time"].max() >= p2_df["open_time"].min()
            or p2_df["open_time"].max() >= ov_df["open_time"].min()
        ):
            raise ValueError(f"overlapping slices detected in fold {self.fold_id}")
        if (
            (tr_df["open_time"] < self.train.start_ms).any()
            or (tr_df["open_time"] > self.train.end_ms).any()
            or (p1_df["open_time"] < self.purge_1.start_ms).any()
            or (p1_df["open_time"] > self.purge_1.end_ms).any()
            or (ie_df["open_time"] < self.inner_eval.start_ms).any()
            or (ie_df["open_time"] > self.inner_eval.end_ms).any()
            or (p2_df["open_time"] < self.purge_2.start_ms).any()
            or (p2_df["open_time"] > self.purge_2.end_ms).any()
            or (ov_df["open_time"] < self.outer_val.start_ms).any()
            or (ov_df["open_time"] > self.outer_val.end_ms).any()
        ):
            raise ValueError(f"rows outside declared intervals detected in fold {self.fold_id}")

        return FoldSpec(
            fold_id=self.fold_id,
            interval=self.interval,
            purge_candles=self.purge_candles,
            warmup_rows=self.warmup_rows,
            train_days=self.train_days,
            inner_eval_days=self.inner_eval_days,
            val_days=self.val_days,
            train=FoldSlice(
                "train", self.train.start_ms, self.train.end_ms, len(tr_df), slice_sha256(tr_df)
            ),
            purge_1=FoldSlice(
                "purge_1",
                self.purge_1.start_ms,
                self.purge_1.end_ms,
                len(p1_df),
                slice_sha256(p1_df),
            ),
            inner_eval=FoldSlice(
                "inner_eval",
                self.inner_eval.start_ms,
                self.inner_eval.end_ms,
                len(ie_df),
                slice_sha256(ie_df),
            ),
            purge_2=FoldSlice(
                "purge_2",
                self.purge_2.start_ms,
                self.purge_2.end_ms,
                len(p2_df),
                slice_sha256(p2_df),
            ),
            outer_val=FoldSlice(
                "outer_val",
                self.outer_val.start_ms,
                self.outer_val.end_ms,
                len(ov_df),
                slice_sha256(ov_df),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "interval": self.interval,
            "purge_candles": self.purge_candles,
            "warmup_rows": self.warmup_rows,
            "train_days": self.train_days,
            "inner_eval_days": self.inner_eval_days,
            "val_days": self.val_days,
            "train": self.train.to_dict(),
            "purge_1": self.purge_1.to_dict(),
            "inner_eval": self.inner_eval.to_dict(),
            "purge_2": self.purge_2.to_dict(),
            "outer_val": self.outer_val.to_dict(),
            "train_duration_ms": self.train.end_ms
            - self.train.start_ms
            + interval_to_ms(self.interval),
            "inner_eval_duration_ms": self.inner_eval.end_ms
            - self.inner_eval.start_ms
            + interval_to_ms(self.interval),
            "outer_val_duration_ms": self.outer_val.end_ms
            - self.outer_val.start_ms
            + interval_to_ms(self.interval),
            "boundaries_description": (
                "All slice start_ms and end_ms boundaries are inclusive "
                "(open_time >= start_ms and open_time <= end_ms)."
            ),
        }


def make_folds(
    data_start_ms: int,
    holdout_start_ms: int,
    *,
    candles: pd.DataFrame | None = None,
    interval: str = "15m",
    train_days: int = 540,
    inner_eval_days: int = 60,
    val_days: int = 120,
    step_days: int = 120,
    purge_candles: int = WARMUP_ROWS,
) -> list[FoldSpec]:
    """Rolling chronological folds; inner/outer validation slices never overlap holdout."""
    from obsidian_rl.evaluation.holdout import get_holdout_start_ms

    canonical_holdout = get_holdout_start_ms()
    if holdout_start_ms > canonical_holdout:
        raise ValueError(
            f"holdout_start_ms ({holdout_start_ms}) exceeds central reserved boundary "
            f"({canonical_holdout})"
        )
    if data_start_ms >= canonical_holdout:
        raise ValueError(
            f"data_start_ms ({data_start_ms}) overlaps central reserved boundary "
            f"({canonical_holdout})"
        )

    ms = interval_to_ms(interval)
    purge_ms = purge_candles * ms
    folds: list[FoldSpec] = []
    fold_id = 0
    train_start = data_start_ms
    while True:
        train_end = train_start + train_days * DAY_MS - ms
        purge1_start = train_end + ms
        purge1_end = purge1_start + (purge_candles - 1) * ms
        inner_start = purge1_end + ms
        inner_end = inner_start + inner_eval_days * DAY_MS - ms
        purge2_start = inner_end + ms
        purge2_end = purge2_start + (purge_candles - 1) * ms
        outer_start = purge2_end + ms
        outer_end = outer_start + val_days * DAY_MS - ms

        if outer_end >= holdout_start_ms:
            break

        if (
            train_start > train_end
            or train_end >= purge1_start
            or purge1_start > purge1_end
            or purge1_end >= inner_start
            or inner_start > inner_end
            or inner_end >= purge2_start
            or purge2_start > purge2_end
            or purge2_end >= outer_start
            or outer_start > outer_end
        ):
            raise ValueError(f"overlapping or invalid declared bounds in fold {fold_id}")

        tr_slice = FoldSlice("train", train_start, train_end, 0, "")
        p1_slice = FoldSlice("purge_1", purge1_start, purge1_end, 0, "")
        ie_slice = FoldSlice("inner_eval", inner_start, inner_end, 0, "")
        p2_slice = FoldSlice("purge_2", purge2_start, purge2_end, 0, "")
        ov_slice = FoldSlice("outer_val", outer_start, outer_end, 0, "")

        spec = FoldSpec(
            fold_id=fold_id,
            interval=interval,
            purge_candles=purge_candles,
            warmup_rows=WARMUP_ROWS,
            train_days=train_days,
            inner_eval_days=inner_eval_days,
            val_days=val_days,
            train=tr_slice,
            purge_1=p1_slice,
            inner_eval=ie_slice,
            purge_2=p2_slice,
            outer_val=ov_slice,
        )

        if candles is not None:
            spec = spec.populate_and_validate(candles)

        folds.append(spec)
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
    if val_candles.empty or len(val_candles) <= WARMUP_ROWS:
        raise ValueError("validation candles must have more rows than WARMUP_ROWS")
    bh_return = float(
        val_candles["close"].iloc[-1] / val_candles["close"].iloc[WARMUP_ROWS] - 1.0
    )
    scenarios = _scenarios(cost_model) if sensitivity else [("base", cost_model, 0)]
    rows: list[EvalRow] = []
    for label, strategy, seed in strategies:
        for scenario_name, costs, delay in scenarios:
            res = run_backtest(val_candles, strategy, cost_model=costs, signal_delay=delay)
            m = compute_metrics(label, res.equity_curve, res.final_state_summary)
            rows.append(EvalRow(fold_id, label, seed, scenario_name, m, bh_return))
    return rows


def save_results(
    rows: list[EvalRow],
    out_dir: Path,
    extra: dict[str, Any] | None = None,
    experiment_id: str | None = None,
) -> Path:
    from obsidian_rl.features.schema import schema_fingerprint
    from obsidian_rl.training.registry import get_git_source_state

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if experiment_id is None:
        experiment_id = (extra or {}).get("experiment_id") or create_experiment_id()
    path = out_dir / f"{experiment_id}.json"
    if path.exists():
        raise FileExistsError(f"walkforward artifact {path} already exists; refusing to overwrite")
    try:
        git_state = get_git_source_state()
        git_commit = git_state.commit
        git_is_clean = git_state.is_clean
        dirty_paths = git_state.dirty_paths
    except Exception:
        git_commit = "unknown"
        git_is_clean = False
        dirty_paths = []

    payload = {
        "experiment_id": experiment_id,
        "created": stamp,
        "git_commit": git_commit,
        "git_is_clean": git_is_clean,
        "dirty_paths": dirty_paths,
        "feature_schema": schema_fingerprint(),
        "cost_model": (extra or {}).get("cost_model", {}),
        "seeds": (extra or {}).get("seeds", []),
        "timesteps": (extra or {}).get("timesteps", 0),
        "n_envs": (extra or {}).get("n_envs", 0),
        "folds": (extra or {}).get("fold_specs", []),
        "extra": extra or {},
        "rows": [r.to_dict() for r in rows],
    }
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    frame = pd.DataFrame([r.to_dict() for r in rows])
    frame.to_csv(path.with_suffix(".csv"), index=False)
    return path


def summarize(rows: list[EvalRow]) -> pd.DataFrame:
    """Aggregate across folds/seeds: mean/std of net return, Sharpe, max DD per strategy."""
    if not rows:
        return pd.DataFrame()
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
