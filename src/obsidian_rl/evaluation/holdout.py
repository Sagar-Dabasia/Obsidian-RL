"""Final holdout evaluation: single-use, frozen champion, immutable evidence.

Enforces central reserved-period policy, global single-use state guarantees under
cross-process locks, exact frozen champion matching, clean Git provenance, and
zero information leakage before durable completion.
"""

import hashlib
import logging
import math
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from obsidian_rl.config import Settings, get_settings
from obsidian_rl.data.store import CandleStore
from obsidian_rl.evaluation.walkforward import evaluate_strategies_on_slice
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.base import Strategy
from obsidian_rl.strategies.baselines import default_baselines
from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy
from obsidian_rl.training.promotion import (
    _compute_report_hash,
    _json_dumps,
    _json_loads_strict,
    _report_filename,
    _utc_ms,
    _utc_timestamp,
    _write_atomically,
    _write_exclusive_file,
    get_verified_champion_info,
)
from obsidian_rl.training.registry import get_git_source_state, validate_model_id

logger = logging.getLogger(__name__)

HOLDOUT_DIR = Path("artifacts/holdout")
HOLDOUT_STATE_PATH = HOLDOUT_DIR / "HOLDOUT_STATE.json"
HOLDOUT_LOCK_PATH = HOLDOUT_DIR / ".holdout.lock"


def _parse_utc_date(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def get_holdout_start_ms(settings: Settings | None = None) -> int:
    if settings is None:
        settings = get_settings()
    return _parse_utc_date(settings.holdout_start_utc)


def check_reserved_period_overlap(
    start_ms: int | None,
    end_ms: int | None,
    loaded_df: pd.DataFrame | None = None,
    *,
    purpose: str = "evaluation",
    settings: Settings | None = None,
) -> None:
    """Enforce central reserved holdout boundary across evaluation, walkforward, and replay."""
    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise ValueError(f"reversed range: start_ms={start_ms} > end_ms={end_ms}")

    if loaded_df is not None:
        if loaded_df.empty:
            raise ValueError(f"loaded dataset for {purpose} is empty")
        first_open = int(loaded_df["open_time"].iloc[0])
        last_open = int(loaded_df["open_time"].iloc[-1])
        if first_open > last_open:
            raise ValueError(f"loaded dataset for {purpose} has reversed open_time values")
        if start_ms is not None and first_open < start_ms:
            raise ValueError(
                f"loaded dataset open_time ({first_open}) precedes requested start ({start_ms})"
            )
        if end_ms is not None and last_open > end_ms:
            raise ValueError(
                f"loaded dataset open_time ({last_open}) exceeds requested end ({end_ms})"
            )

    holdout_ms = get_holdout_start_ms(settings)
    if purpose != "holdout":
        overlaps = False
        if end_ms is not None and end_ms >= holdout_ms:
            overlaps = True
        if start_ms is not None and start_ms >= holdout_ms:
            overlaps = True
        if loaded_df is not None and int(loaded_df["open_time"].iloc[-1]) >= holdout_ms:
            overlaps = True
        if overlaps:
            st = settings.holdout_start_utc if settings else "2025-07-01"
            raise ValueError(f"{purpose} range overlaps reserved holdout period starting at {st}")


@contextmanager
def _holdout_lock(holdout_dir: Path = HOLDOUT_DIR, timeout_sec: float = 10.0) -> Iterator[None]:
    """Cross-process lock covering check state -> exclusive create -> eval -> persist."""
    holdout_dir.mkdir(parents=True, exist_ok=True)
    lock_path = holdout_dir / ".holdout.lock"
    start_time = time.monotonic()
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    acquired = False
    while time.monotonic() - start_time < timeout_sec:
        try:
            with open(lock_path, "xb") as fh:
                fh.write(token.encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
    if not acquired:
        raise RuntimeError("timed out waiting for holdout lock; holdout currently running")
    try:
        yield
    finally:
        if acquired and lock_path.exists():
            try:
                if lock_path.read_text(encoding="utf-8").strip() == token:
                    lock_path.unlink()
            except OSError:
                pass


def _validate_finite_nested(val: Any, path: str) -> None:
    if isinstance(val, bool):
        return
    if isinstance(val, (int, float)):
        if isinstance(val, float) and not math.isfinite(val):
            raise ValueError(f"non-finite value inside {path}: {val!r}")
        return
    if isinstance(val, dict):
        for k, v in val.items():
            _validate_finite_nested(v, f"{path}.{k}")
    elif isinstance(val, list):
        for idx, item in enumerate(val):
            _validate_finite_nested(item, f"{path}[{idx}]")


def _verify_report_file(rep_path: Path, expected_hash: str) -> dict[str, Any]:
    """Verify an immutable holdout report file strictly."""
    if rep_path.is_symlink():
        raise RuntimeError("holdout report file must not be a symlink")
    resolved = rep_path.resolve()
    holdout_resolved = HOLDOUT_DIR.resolve()
    if holdout_resolved not in resolved.parents and resolved != holdout_resolved:
        raise RuntimeError(f"path traversal detected for holdout report: {rep_path}")
    if not rep_path.is_file():
        raise RuntimeError(f"holdout report file missing or not a file: {rep_path}")

    text = rep_path.read_text(encoding="utf-8")
    report_data = _json_loads_strict(text, f"report {rep_path.name!r}")
    if not isinstance(report_data, dict):
        raise RuntimeError("holdout report root must be an object")

    _validate_finite_nested(report_data, f"report {rep_path.name!r}")
    stored_hash = report_data.get("report_sha256")
    if (
        not isinstance(stored_hash, str)
        or len(stored_hash) != 64
        or stored_hash != stored_hash.lower()
    ):
        raise RuntimeError("holdout report missing valid 64-char lowercase report_sha256")
    if stored_hash != expected_hash:
        raise RuntimeError(
            f"holdout report_sha256 ({stored_hash}) does not match expected ({expected_hash})"
        )
    actual_hash = _compute_report_hash(report_data)
    if actual_hash != stored_hash:
        raise RuntimeError("holdout report hash mismatch; content does not match report_sha256")
    return report_data


def load_holdout_state(path: Path = HOLDOUT_STATE_PATH) -> dict[str, Any]:
    """Strictly load and validate HOLDOUT_STATE.json."""
    if path.is_symlink():
        raise RuntimeError("HOLDOUT_STATE.json must not be a symlink")
    resolved = path.resolve()
    holdout_resolved = HOLDOUT_DIR.resolve()
    if holdout_resolved not in resolved.parents and resolved != holdout_resolved:
        raise RuntimeError(f"path traversal detected for holdout state: {path}")

    if not path.exists():
        if HOLDOUT_DIR.exists():
            for child in HOLDOUT_DIR.iterdir():
                if child.name in ("HOLDOUT_STATE.json", ".holdout.lock"):
                    continue
                if child.name.startswith("walkforward-") or child.name.startswith("holdout"):
                    raise RuntimeError("legacy holdout artifacts require manual review")
        return {}

    text = path.read_text(encoding="utf-8")
    data = _json_loads_strict(text, f"holdout state {path.name!r}")
    if not isinstance(data, dict):
        raise RuntimeError("HOLDOUT_STATE.json root must be an object")

    _validate_finite_nested(data, "HOLDOUT_STATE.json")

    schema_version = data.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != 1
    ):
        raise RuntimeError(f"HOLDOUT_STATE.json unsupported schema_version {schema_version!r}")

    required = (
        "consumption_id",
        "started_at_utc",
        "status",
        "reserved_start_utc",
        "fixed_end_utc",
        "symbol",
        "interval",
        "model_id",
        "model_artifact_sha256",
        "feature_schema",
        "source_commit",
        "source_tree_clean",
        "costs",
        "baselines",
        "scenarios",
    )
    for field in required:
        if field not in data:
            raise RuntimeError(f"HOLDOUT_STATE.json missing required field {field!r}")

    status = data.get("status")
    if status not in ("started", "completed", "failed"):
        raise RuntimeError(f"HOLDOUT_STATE.json unknown status {status!r}")

    if data.get("source_tree_clean") is not True and not isinstance(
        data.get("source_tree_clean"), bool
    ):
        raise RuntimeError("HOLDOUT_STATE.json source_tree_clean must be a boolean")

    sha = data.get("model_artifact_sha256")
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or sha != sha.lower()
        or not all(c in "0123456789abcdef" for c in sha)
    ):
        raise RuntimeError("HOLDOUT_STATE.json model_artifact_sha256 must be valid SHA-256")

    if status == "completed":
        rep_name = data.get("report_filename")
        rep_sha = data.get("report_sha256")
        if not isinstance(rep_name, str) or not rep_name or "/" in rep_name or "\\" in rep_name:
            raise RuntimeError("completed state report_filename must be a clean basename")
        if not isinstance(rep_sha, str) or len(rep_sha) != 64 or rep_sha != rep_sha.lower():
            raise RuntimeError("completed state report_sha256 must be valid SHA-256")
        rep_path = HOLDOUT_DIR / rep_name
        _verify_report_file(rep_path, rep_sha)
    else:
        if data.get("report_filename") is not None or data.get("report_sha256") is not None:
            raise RuntimeError(
                f"state status {status!r} must not claim report_filename/report_sha256"
            )

    return data


def _dataset_sha256(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(str(list(df.columns)).encode("utf-8"))
    for col in df.columns:
        h.update(str(df[col].dtype).encode("utf-8"))
    h.update(str(len(df)).encode("utf-8"))
    if not df.empty:
        h.update(str(int(df["open_time"].iloc[0])).encode("utf-8"))
        h.update(str(int(df["open_time"].iloc[-1])).encode("utf-8"))
    for row in df.itertuples(index=False):
        h.update(str(tuple(row)).encode("utf-8"))
    return h.hexdigest()


def run_final_holdout(
    settings: Settings,
    model_id: str,
    end_utc: str,
    models_dir: Path | None = None,
) -> tuple[Path, str]:
    """Run the untouched final holdout ONCE for the frozen champion under strict isolation."""
    if models_dir is None:
        models_dir = settings.models_dir

    with _holdout_lock(HOLDOUT_DIR):
        existing_state = load_holdout_state(HOLDOUT_STATE_PATH)
        if existing_state:
            raise RuntimeError(
                f"holdout already consumed: status is {existing_state['status']}. "
                f"see {HOLDOUT_STATE_PATH}"
            )

        model_id = validate_model_id(model_id)
        champion_info = get_verified_champion_info(models_dir)
        if model_id != champion_info["model_id"]:
            raise RuntimeError(
                f"requested model {model_id!r} differs from verified champion "
                f"{champion_info['model_id']!r}"
            )

        git_state = get_git_source_state()
        if not git_state.is_clean:
            raise RuntimeError("holdout evaluation refused: project source tree is dirty")
        if git_state.commit != champion_info["source_commit"]:
            raise RuntimeError(
                f"source commit ({git_state.commit}) does not match champion promotion commit "
                f"({champion_info['source_commit']})"
            )

        end_ms = _parse_utc_date(end_utc)
        holdout_start_ms = get_holdout_start_ms(settings)
        if end_ms < holdout_start_ms:
            raise ValueError(
                f"requested end_utc ({end_utc}) precedes holdout start "
                f"({settings.holdout_start_utc})"
            )

        strat = PpoPolicyStrategy.from_dir(champion_info["model_dir"])
        if strat.strategy_id != f"ppo:{model_id}":
            raise RuntimeError(
                f"loaded strategy ID mismatch: {strat.strategy_id} vs ppo:{model_id}"
            )

        baselines = default_baselines()
        baseline_ids = [str(cast(Strategy, b).strategy_id) for b in baselines]
        costs = cast(CostModel, champion_info["cost_model"])
        scenarios_list = [
            ("base", costs, 0),
            (
                "costs2x",
                CostModel(
                    taker_fee=costs.taker_fee * 2,
                    half_spread=costs.half_spread * 2,
                    slippage=costs.slippage * 2,
                ),
                0,
            ),
            ("delay1", costs, 1),
        ]
        scenario_names = [s[0] for s in scenarios_list]

        consumption_id = uuid.uuid4().hex
        started_at = _utc_timestamp()
        started_state: dict[str, Any] = {
            "schema_version": 1,
            "consumption_id": consumption_id,
            "started_at_utc": started_at,
            "status": "started",
            "reserved_start_utc": settings.holdout_start_utc,
            "fixed_end_utc": end_utc,
            "symbol": settings.symbol,
            "interval": settings.interval,
            "model_id": model_id,
            "model_artifact_sha256": champion_info["model_artifact_sha256"],
            "feature_schema": champion_info["feature_schema"],
            "source_commit": git_state.commit,
            "source_tree_clean": True,
            "costs": asdict(costs),
            "baselines": baseline_ids,
            "scenarios": scenario_names,
            "report_filename": None,
            "report_sha256": None,
        }

        started_bytes = (_json_dumps(started_state) + "\n").encode("utf-8")
        if HOLDOUT_STATE_PATH.is_symlink():
            raise RuntimeError("HOLDOUT_STATE.json must not be a symlink")
        _write_exclusive_file(HOLDOUT_STATE_PATH, started_bytes)

        temp_files: list[Path] = []
        try:
            store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
            candles = store.read(holdout_start_ms, end_ms)
            check_reserved_period_overlap(
                holdout_start_ms,
                end_ms,
                candles,
                purpose="holdout",
                settings=settings,
            )

            dataset_hash = _dataset_sha256(candles)
            strategies: list[tuple[str, Any, int | None]] = [
                (str(cast(Strategy, b).strategy_id), b, None) for b in baselines
            ]
            strategies.append((strat.strategy_id, strat, None))

            rows = evaluate_strategies_on_slice(
                candles,
                strategies,
                fold_id=-1,
                cost_model=costs,
            )

            for r in rows:
                _validate_finite_nested(r.to_dict(), f"row({r.strategy_id},{r.scenario})")

            ts_ms = _utc_ms()
            report_data: dict[str, Any] = {
                "schema_version": 1,
                "consumption_id": consumption_id,
                "created_at_utc": _utc_timestamp(),
                "symbol": settings.symbol,
                "interval": settings.interval,
                "reserved_start_utc": settings.holdout_start_utc,
                "fixed_end_utc": end_utc,
                "first_open_ms": int(candles["open_time"].iloc[0]),
                "last_open_ms": int(candles["open_time"].iloc[-1]),
                "row_count": len(candles),
                "dataset_sha256": dataset_hash,
                "model_id": model_id,
                "model_artifact_sha256": champion_info["model_artifact_sha256"],
                "source_commit": git_state.commit,
                "source_tree_clean": True,
                "costs": asdict(costs),
                "rows": [r.to_dict() for r in rows],
            }

            report_hash = _compute_report_hash(report_data)
            report_with_hash = {**report_data, "report_sha256": report_hash}
            payload = (_json_dumps(report_with_hash) + "\n").encode("utf-8")

            rep_filename = _report_filename(ts_ms, report_hash)
            rep_path = HOLDOUT_DIR / rep_filename
            if rep_path.is_symlink():
                raise RuntimeError("holdout report must not be a symlink")
            _write_exclusive_file(rep_path, payload)
            _verify_report_file(rep_path, report_hash)

            completed_state = {
                **started_state,
                "status": "completed",
                "report_filename": rep_filename,
                "report_sha256": report_hash,
            }
            completed_bytes = (_json_dumps(completed_state) + "\n").encode("utf-8")
            _write_atomically(HOLDOUT_STATE_PATH, completed_bytes)

            return rep_path, report_hash

        except Exception as exc:
            try:
                if HOLDOUT_STATE_PATH.exists():
                    current = _json_loads_strict(
                        HOLDOUT_STATE_PATH.read_text(encoding="utf-8"), "state"
                    )
                    if isinstance(current, dict) and current.get("status") == "started":
                        failed_state = {
                            **started_state,
                            "status": "failed",
                            "failure_class": type(exc).__name__,
                            "reason": str(exc)[:200],
                            "failed_at_utc": _utc_timestamp(),
                            "report_filename": None,
                            "report_sha256": None,
                        }
                        failed_bytes = (_json_dumps(failed_state) + "\n").encode("utf-8")
                        _write_atomically(HOLDOUT_STATE_PATH, failed_bytes)
            except Exception as inner_exc:
                logger.error(f"failed to transition holdout state to failed: {inner_exc}")
            raise
        finally:
            for p in temp_files:
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
