"""PPO Seed Ensemble Screen: evaluate median-of-5 seed ensembles.

Loads already-trained models from the registry, forms deterministic 5-seed
median ensembles per fold/penalty, and evaluates on outer-validation slices
under base, costs2x, and delay1 scenarios.  Does NOT train, tune, promote,
or access the reserved holdout.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from obsidian_rl.evaluation.backtest import DEFAULT_TARGETS
from obsidian_rl.evaluation.walkforward import (
    evaluate_strategies_on_slice,
    make_folds,
    slice_candles,
    slice_sha256,
)
from obsidian_rl.features.observation import PortfolioObs
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy
from obsidian_rl.training.registry import load_record


SEEDS: list[int] = [42, 7, 23, 101, 202]
FOLDS: list[int] = [0, 1, 2]
PENALTIES: list[float] = [0.0, 2.5, 5.0]


class PpoSeedEnsembleStrategy:
    """Deterministic 5-seed median ensemble strategy."""

    def __init__(
        self,
        members: list[PpoPolicyStrategy],
        strategy_id: str = "ppo-ensemble-5seed",
        allowed_targets: tuple[float, ...] = DEFAULT_TARGETS,
    ) -> None:
        if len(members) != 5:
            raise ValueError(
                f"Ensemble requires exactly 5 members, got {len(members)}"
            )
        self.members = members
        self.strategy_id = strategy_id
        self.allowed_targets = allowed_targets

    def reset(self) -> None:
        for member in self.members:
            member.reset()

    def propose(self, market_row: np.ndarray, portfolio: PortfolioObs) -> float:
        targets: list[float] = []
        for m in self.members:
            t = m.propose(market_row, portfolio)
            if not math.isfinite(t):
                raise ValueError(
                    f"Non-finite target {t} from member {m.strategy_id}"
                )
            targets.append(t)
        med = float(np.median(targets))
        # With 5 members and targets from allowed_targets, the median is
        # always one of the permitted targets.  Snap defensively anyway.
        if med not in self.allowed_targets:
            med = float(min(self.allowed_targets, key=lambda a: abs(a - med)))
        return med


def resolve_model(
    models_dir: Path,
    penalty: float,
    fold_id: int,
    seed: int,
) -> tuple[Path, str]:
    """Find the registered model directory for a (penalty, fold, seed) triple."""
    for child in sorted(models_dir.iterdir()):
        meta_path = child / "METADATA.json"
        if not meta_path.exists():
            continue
        try:
            rec = load_record(child)
        except Exception:
            continue
        cfg = rec.metadata.get("config", {})
        reward = cfg.get("reward", {})
        m_pen = reward.get("turnover_penalty_bps", 0.0)
        m_seeds = rec.metadata.get("seeds", [])
        m_id = rec.model_id
        if m_pen == penalty and seed in m_seeds:
            if f"-f{fold_id}-" in m_id or m_id.endswith(f"-f{fold_id}"):
                return child, m_id
    raise FileNotFoundError(
        f"Model not found for penalty={penalty}, fold={fold_id}, seed={seed}"
    )


@dataclass
class EnsembleFoldResult:
    """Results for one ensemble on one fold under all 3 scenarios."""

    fold_id: int
    penalty: float
    base_net_return: float
    base_max_drawdown: float
    base_sharpe: float
    base_turnover: float
    base_trades: float
    costs2x_net_return: float
    delay1_net_return: float


def evaluate_ensemble_on_fold(
    candles: pd.DataFrame,
    models_dir: Path,
    penalty: float,
    fold_id: int,
    val_start_ms: int,
    val_end_ms: int,
    cost_model: CostModel,
) -> EnsembleFoldResult:
    """Build and evaluate a 5-seed ensemble on one fold's outer validation."""
    val_slice = slice_candles(candles, val_start_ms, val_end_ms)
    members = [
        PpoPolicyStrategy.from_dir(
            resolve_model(models_dir, penalty, fold_id, s)[0], device="cpu"
        )
        for s in SEEDS
    ]
    ensemble = PpoSeedEnsembleStrategy(
        members, strategy_id=f"ppo-ensemble-p{penalty}"
    )
    rows = evaluate_strategies_on_slice(
        val_slice,
        [(ensemble.strategy_id, ensemble, None)],
        fold_id=fold_id,
        cost_model=cost_model,
        sensitivity=True,
    )
    row_dict = {r.scenario: r.to_dict() for r in rows}
    return EnsembleFoldResult(
        fold_id=fold_id,
        penalty=penalty,
        base_net_return=row_dict["base"]["net_return"],
        base_max_drawdown=row_dict["base"]["max_drawdown"],
        base_sharpe=row_dict["base"]["sharpe"],
        base_turnover=row_dict["base"]["turnover"],
        base_trades=row_dict["base"]["trade_count"],
        costs2x_net_return=row_dict["costs2x"]["net_return"],
        delay1_net_return=row_dict["delay1"]["net_return"],
    )


def check_eligibility(
    fold_results: list[EnsembleFoldResult],
    indiv_seed_median_turnover: float,
) -> tuple[bool, dict[str, bool]]:
    """Check all 7 eligibility criteria.  Returns (eligible, checks_dict)."""
    base_rets = [r.base_net_return for r in fold_results]
    pos_folds = sum(1 for r in base_rets if r > 0)
    worst = min(base_rets)
    mean_base = sum(base_rets) / len(base_rets)
    mean_c2x = sum(r.costs2x_net_return for r in fold_results) / len(fold_results)
    mean_d1 = sum(r.delay1_net_return for r in fold_results) / len(fold_results)
    mean_dd = sum(r.base_max_drawdown for r in fold_results) / len(fold_results)
    mean_to = sum(r.base_turnover for r in fold_results) / len(fold_results)

    checks = {
        "pos_folds_ge_2": pos_folds >= 2,
        "worst_fold_above_neg5pct": worst > -0.05,
        "mean_base_positive": mean_base > 0.0,
        "mean_c2x_positive": mean_c2x > 0.0,
        "mean_d1_positive": mean_d1 > 0.0,
        "mean_dd_le_15pct": mean_dd <= 0.15,
        "turnover_le_indiv": mean_to <= indiv_seed_median_turnover,
    }
    return all(checks.values()), checks


if __name__ == "__main__":
    import sys

    from obsidian_rl.config import get_settings
    from obsidian_rl.data.store import CandleStore

    settings = get_settings()
    models_dir = settings.models_dir

    def parse_utc(dt_str: str) -> int:
        return int(pd.Timestamp(dt_str).timestamp() * 1000)

    data_start_ms = parse_utc("2023-01-01T00:00:00Z")
    holdout_start_ms = parse_utc("2025-07-01T00:00:00Z")

    store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
    candles = store.read(data_start_ms, holdout_start_ms - 1)

    folds = make_folds(
        data_start_ms=data_start_ms,
        holdout_start_ms=holdout_start_ms,
        train_days=365,
        inner_eval_days=60,
        val_days=90,
        step_days=180,
    )

    cm = CostModel()

    # Individual-seed turnover from walk-forward artifacts
    wf_files: dict[float, list[Path]] = {
        0.0: [
            Path("artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.json"),
            Path("artifacts/walkforward/wf-20260722-161119-636691-02223b83.json"),
        ],
        2.5: [
            Path("artifacts/walkforward/wf-20260722-170718-091601-tp2.5-5eaff12a.json"),
        ],
        5.0: [
            Path("artifacts/walkforward/wf-20260722-172239-240346-tp5.0-8d04a46e.json"),
        ],
    }

    def indiv_median_turnover(penalty: float) -> float:
        rows: list[dict[str, Any]] = []
        for p in wf_files[penalty]:
            with open(p) as fh:
                rows.extend(json.load(fh)["rows"])
        df = pd.DataFrame(rows)
        ppo = df[(df["scenario"] == "base") & df["strategy_id"].str.startswith("ppo-")]
        return float(ppo.groupby("seed")["turnover"].mean().median())

    # Evaluate all penalties
    all_results: dict[float, list[EnsembleFoldResult]] = {}
    for penalty in PENALTIES:
        fold_results = []
        for fold in folds:
            r = evaluate_ensemble_on_fold(
                candles, models_dir, penalty, fold.fold_id,
                fold.val_start_ms, fold.val_end_ms, cm,
            )
            fold_results.append(r)
        all_results[penalty] = fold_results

    # Check eligibility
    eligible_penalties: list[float] = []
    for penalty in PENALTIES:
        med_to = indiv_median_turnover(penalty)
        ok, checks = check_eligibility(all_results[penalty], med_to)
        print(f"Penalty {penalty} bps: eligible={ok}, checks={checks}")
        if ok:
            eligible_penalties.append(penalty)

    # Select best
    selected = None
    if eligible_penalties:
        def sort_key(p: float) -> tuple[float, float, float]:
            fr = all_results[p]
            worst = min(r.base_net_return for r in fr)
            mean_to = sum(r.base_turnover for r in fr) / len(fr)
            return (-worst, mean_to, p)

        eligible_penalties.sort(key=sort_key)
        selected = eligible_penalties[0]

    print(f"\nEligible: {eligible_penalties}")
    print(f"Selected: {selected}")

    # Confirmation
    if selected is not None:
        conf_start_ms = parse_utc("2025-05-27T00:00:00Z")
        conf_end_ms = parse_utc("2025-06-30T23:45:00Z")
        conf_candles = store.read(conf_start_ms, conf_end_ms)
        conf_sha = slice_sha256(conf_candles)
        print(f"\nConfirmation SHA-256: {conf_sha}")

        members = [
            PpoPolicyStrategy.from_dir(
                resolve_model(models_dir, selected, 2, s)[0], device="cpu"
            )
            for s in SEEDS
        ]
        ens = PpoSeedEnsembleStrategy(members, strategy_id="ppo-ensemble-confirmation")
        rows = evaluate_strategies_on_slice(
            conf_candles,
            [(ens.strategy_id, ens, None)],
            fold_id=2,
            cost_model=cm,
            sensitivity=True,
        )
        for r in rows:
            d = r.to_dict()
            print(f"  {d['scenario']}: ret={d['net_return']:+.6f}, dd={d['max_drawdown']:.4f}")
    else:
        print("\nNo penalty eligible, skipping confirmation.")
