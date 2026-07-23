"""Alpha Gate Historical Pilot 01 research tool.

Trains Alpha Gate (LightGBM signed directional net-edge model) on each of the 4
nested chronological training folds, saves artifacts with SHA-256 metadata, and
evaluates gate-direct, gated-regime, and baseline strategies on untouched outer
validation slices under base, costs2x, and delay1 scenarios.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from obsidian_rl.config import get_settings
from obsidian_rl.data.store import CandleStore
from obsidian_rl.evaluation.walkforward import (
    EvalRow,
    evaluate_strategies_on_slice,
    make_folds,
    slice_candles,
)
from obsidian_rl.gate.alpha_gate import (
    load_gate,
    save_gate,
    train_gate,
)
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.baselines import RegimeFilteredMomentum, default_baselines
from obsidian_rl.strategies.gated import GateDirectStrategy, GatedStrategy


@dataclass
class PilotResult:
    verdict: str
    fold_eval_rows: list[dict[str, Any]]
    summary_by_strategy: dict[str, dict[str, Any]]


def check_strategy_eligibility(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_rows = [r for r in rows if r["scenario"] == "base"]
    c2x_rows = [r for r in rows if r["scenario"] == "costs2x"]
    d1_rows = [r for r in rows if r["scenario"] == "delay1"]

    base_rets = [r["net_return"] for r in base_rows]
    c2x_rets = [r["net_return"] for r in c2x_rows]
    d1_rets = [r["net_return"] for r in d1_rows]
    dds = [r["max_drawdown"] for r in base_rows]
    sharpes = [r["sharpe"] for r in base_rows]

    pos_folds = sum(1 for r in base_rets if r > 0)
    worst_fold = min(base_rets) if base_rets else -1.0
    mean_base = float(np.mean(base_rets)) if base_rets else -1.0
    mean_c2x = float(np.mean(c2x_rets)) if c2x_rets else -1.0
    mean_d1 = float(np.mean(d1_rets)) if d1_rets else -1.0
    mean_dd = float(np.mean(dds)) if dds else 1.0
    mean_sharpe = float(np.mean(sharpes)) if sharpes else -99.0

    all_finite = bool(all(math.isfinite(x) for x in base_rets + c2x_rets + d1_rets + dds + sharpes))

    c1 = pos_folds >= 3
    c2 = worst_fold > -0.05
    c3 = mean_base > 0.0
    c4 = mean_c2x > 0.0
    c5 = mean_d1 > 0.0
    c6 = mean_dd <= 0.15

    passed = bool(c1 and c2 and c3 and c4 and c5 and c6 and all_finite)

    return {
        "pos_folds": pos_folds,
        "worst_fold": worst_fold,
        "mean_base_return": mean_base,
        "mean_costs2x_return": mean_c2x,
        "mean_delay1_return": mean_d1,
        "mean_max_drawdown": mean_dd,
        "mean_sharpe": mean_sharpe,
        "all_finite": all_finite,
        "passed": passed,
    }


def run_alpha_gate_pilot(
    out_dir: Path | None = None,
) -> PilotResult:
    settings = get_settings()
    store = CandleStore(settings.data_dir, settings.symbol, settings.interval)

    data_start_ms = int(pd.Timestamp("2020-01-01T00:00:00Z").timestamp() * 1000)
    holdout_start_ms = int(pd.Timestamp("2022-11-27T00:00:00Z").timestamp() * 1000)

    candles = store.read(data_start_ms, holdout_start_ms - 1)
    if candles.empty:
        raise RuntimeError("No candles found in 2020-2022 historical range")

    folds = make_folds(
        data_start_ms=data_start_ms,
        holdout_start_ms=holdout_start_ms,
        train_days=365,
        inner_eval_days=60,
        val_days=90,
        step_days=180,
    )

    if out_dir is None:
        out_dir = Path("artifacts/alpha_gate_pilot")
    out_dir.mkdir(parents=True, exist_ok=True)

    cm_base = CostModel()
    all_eval_rows: list[EvalRow] = []

    for fold in folds:
        f_idx = fold.fold_id
        train_slice = slice_candles(candles, fold.train_start_ms, fold.train_end_ms)
        val_slice = slice_candles(candles, fold.val_start_ms, fold.val_end_ms)

        gate = train_gate(train_slice)
        fold_gate_dir = out_dir / f"alpha-gate-f{f_idx}"
        save_gate(gate, fold_gate_dir)
        loaded_gate = load_gate(fold_gate_dir)

        strategies: list[tuple[str, Any, int | None]] = [
            ("gate-direct-m0.0", GateDirectStrategy(loaded_gate, margin=0.0), None),
            (
                "gated-regime-m0.0",
                GatedStrategy(RegimeFilteredMomentum(), loaded_gate, margin=0.0),
                None,
            ),
        ]
        for b in default_baselines():
            strategies.append((b.strategy_id, b, None))

        rows = evaluate_strategies_on_slice(
            val_slice,
            strategies,
            fold_id=f_idx,
            cost_model=cm_base,
            sensitivity=True,
        )
        all_eval_rows.extend(rows)

    raw_rows = [r.to_dict() for r in all_eval_rows]
    summary_by_strat: dict[str, dict[str, Any]] = {}
    strategy_ids = sorted({r["strategy_id"] for r in raw_rows})

    screen_passed = False
    for strat_id in strategy_ids:
        s_rows = [r for r in raw_rows if r["strategy_id"] == strat_id]
        res = check_strategy_eligibility(s_rows)
        summary_by_strat[strat_id] = res
        if res["passed"] and ("gate" in strat_id):
            screen_passed = True

    verdict = (
        "ALPHA GATE DEVELOPMENT SCREEN PASSES"
        if screen_passed
        else "ALPHA GATE DEVELOPMENT SCREEN FAILS"
    )

    report_payload = {
        "verdict": verdict,
        "summary": summary_by_strat,
        "rows": raw_rows,
    }
    (out_dir / "pilot_results.json").write_text(
        json.dumps(report_payload, indent=1), encoding="utf-8"
    )

    return PilotResult(
        verdict=verdict,
        fold_eval_rows=raw_rows,
        summary_by_strategy=summary_by_strat,
    )


if __name__ == "__main__":
    res = run_alpha_gate_pilot()
    print(f"Verdict: {res.verdict}")
