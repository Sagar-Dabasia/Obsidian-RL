"""Controlled model promotion: candidate -> champion via explicit command, with rollback.

The deployed policy stays frozen; nothing here trains or self-modifies. Candidates are
evaluated on predefined validation slices against the current champion and deterministic
baselines, checked against risk thresholds, and promoted only by an explicit CLI call.
The previous champion is preserved (promotion state 'retired') for rollback.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian_rl.evaluation.walkforward import EvalRow, evaluate_strategies_on_slice
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.baselines import default_baselines
from obsidian_rl.training.registry import load_record, set_promotion

CHAMPION_FILE = "CHAMPION.json"


@dataclass(frozen=True)
class PromotionThresholds:
    """Risk gates a candidate must pass on the validation slice (base cost scenario)."""

    max_drawdown_limit: float = 0.35
    min_net_return_vs_flat: float = -0.05  # cannot lose >5% where flat loses ~0
    must_not_trail_champion_by: float = 0.02  # net-return margin vs current champion


def _champion_path(models_dir: Path) -> Path:
    return Path(models_dir) / CHAMPION_FILE


def current_champion(models_dir: Path) -> str | None:
    path = _champion_path(models_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    model_id = data.get("model_id")
    return str(model_id) if model_id else None


def _write_champion(models_dir: Path, model_id: str | None, action: str) -> None:
    path = _champion_path(models_dir)
    data: dict[str, Any] = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"model_id": None, "history": []}
    )
    data["history"].append(
        {
            "model_id": data.get("model_id"),
            "replaced_at_utc_ms": int(time.time() * 1000),
            "action": action,
        }
    )
    data["model_id"] = model_id
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def evaluate_candidate(
    models_dir: Path,
    candidate_id: str,
    val_candles: pd.DataFrame,
    *,
    thresholds: PromotionThresholds | None = None,
    cost_model: CostModel | None = None,
) -> dict[str, Any]:
    """Compare candidate vs champion vs baselines on a predefined validation slice."""
    from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy

    thresholds = thresholds or PromotionThresholds()
    cost_model = cost_model or CostModel()
    load_record(Path(models_dir) / candidate_id)  # hard gate: schema + checksum

    strategies: list[tuple[str, Any, int | None]] = [
        (b.strategy_id, b, None)  # type: ignore[attr-defined]
        for b in default_baselines()
    ]
    strategies.append(
        ("candidate", PpoPolicyStrategy.from_dir(Path(models_dir) / candidate_id), None)
    )
    champion_id = current_champion(models_dir)
    if champion_id:
        strategies.append(
            ("champion", PpoPolicyStrategy.from_dir(Path(models_dir) / champion_id), None)
        )

    rows: list[EvalRow] = evaluate_strategies_on_slice(
        val_candles, strategies, fold_id=0, cost_model=cost_model, sensitivity=False
    )
    by_id = {r.strategy_id: r.metrics for r in rows}
    cand = by_id["candidate"]

    failures: list[str] = []
    if cand.max_drawdown > thresholds.max_drawdown_limit:
        failures.append(
            f"max drawdown {cand.max_drawdown:.3f} > limit {thresholds.max_drawdown_limit}"
        )
    if cand.net_return < thresholds.min_net_return_vs_flat:
        failures.append(
            f"net return {cand.net_return:.4f} below floor {thresholds.min_net_return_vs_flat}"
        )
    if champion_id:
        champ = by_id["champion"]
        if cand.net_return < champ.net_return - thresholds.must_not_trail_champion_by:
            failures.append(
                f"trails champion by {champ.net_return - cand.net_return:.4f} "
                f"(> {thresholds.must_not_trail_champion_by})"
            )

    return {
        "candidate_id": candidate_id,
        "champion_id": champion_id,
        "passes": not failures,
        "failures": failures,
        "metrics": {sid: m.to_dict() for sid, m in by_id.items()},
    }


def promote(models_dir: Path, model_id: str) -> None:
    """Explicitly promote a validated candidate to champion; retire the old champion."""
    load_record(Path(models_dir) / model_id)  # must validate
    old = current_champion(models_dir)
    if old == model_id:
        return
    if old:
        set_promotion(Path(models_dir) / old, "retired")
    set_promotion(Path(models_dir) / model_id, "champion")
    _write_champion(models_dir, model_id, action=f"promote:{model_id}")


def rollback(models_dir: Path) -> str:
    """Restore the most recent previous champion. Returns the restored model_id."""
    path = _champion_path(models_dir)
    if not path.exists():
        raise RuntimeError("no champion history to roll back")
    data = json.loads(path.read_text(encoding="utf-8"))
    history = [h for h in data.get("history", []) if h.get("model_id")]
    if not history:
        raise RuntimeError("no previous champion recorded")
    previous = str(history[-1]["model_id"])
    load_record(Path(models_dir) / previous)  # must still validate
    current = data.get("model_id")
    if current:
        set_promotion(Path(models_dir) / current, "retired")
    set_promotion(Path(models_dir) / previous, "champion")
    _write_champion(models_dir, previous, action=f"rollback:{previous}")
    return previous
