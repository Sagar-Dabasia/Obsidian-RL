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


def _load_champion_data(path: Path) -> dict[str, Any]:
    """Load CHAMPION.json, back-filling `lineage` for files written before it existed.

    `lineage` is the undo stack of champions in promotion order (current is last);
    `history` remains an append-only audit log.
    """
    if not path.exists():
        return {"model_id": None, "lineage": [], "history": []}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if "lineage" not in data:
        # Legacy file (promotes only, no rollbacks yet): the only reliable champion is
        # the current one, so seed the stack with it.
        data["lineage"] = [data["model_id"]] if data.get("model_id") else []
    return data


def _write_champion_data(path: Path, data: dict[str, Any], action: str) -> None:
    data.setdefault("history", []).append(
        {
            "model_id": data.get("model_id"),
            "lineage": list(data.get("lineage", [])),
            "changed_at_utc_ms": int(time.time() * 1000),
            "action": action,
        }
    )
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
    path = _champion_path(models_dir)
    data = _load_champion_data(path)
    old = data.get("model_id")
    if old == model_id:
        return
    if old:
        set_promotion(Path(models_dir) / old, "retired")
    set_promotion(Path(models_dir) / model_id, "champion")
    data["model_id"] = model_id
    data["lineage"] = [*data.get("lineage", []), model_id]  # push onto the undo stack
    _write_champion_data(path, data, action=f"promote:{model_id}")


def rollback(models_dir: Path) -> str:
    """Pop the current champion off the lineage stack and restore the one beneath it.

    Repeated rollbacks walk strictly further back (C -> B -> A), never bouncing back to
    an already-abandoned champion. Returns the restored model_id.
    """
    path = _champion_path(models_dir)
    if not path.exists():
        raise RuntimeError("no champion history to roll back")
    data = _load_champion_data(path)
    lineage: list[str] = list(data.get("lineage", []))
    if len(lineage) < 2:
        raise RuntimeError("no previous champion to roll back to")
    current = lineage[-1]
    previous = lineage[-2]
    load_record(Path(models_dir) / previous)  # must still validate
    set_promotion(Path(models_dir) / current, "retired")
    set_promotion(Path(models_dir) / previous, "champion")
    data["model_id"] = previous
    data["lineage"] = lineage[:-1]  # pop the abandoned champion
    _write_champion_data(path, data, action=f"rollback:{current}->{previous}")
    return previous
