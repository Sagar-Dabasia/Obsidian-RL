"""Final holdout evaluation: single-use, frozen champion, immutable evidence.

Enforces central reserved-period policy, global single-use state guarantees under
cross-process locks, exact frozen champion matching, clean Git provenance, and
zero information leakage before durable completion.
"""

import hashlib
import logging
import math
import os
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from obsidian_rl.config import Settings, get_settings
from obsidian_rl.data.store import CandleStore
from obsidian_rl.evaluation.walkforward import evaluate_strategies_on_slice
from obsidian_rl.features.observation import schema_fingerprint
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
    _write_atomically,
    _write_exclusive_file,
    get_verified_champion_info,
)
from obsidian_rl.training.registry import (
    get_git_source_state,
    resolve_repo_root,
    validate_model_id,
)

logger = logging.getLogger(__name__)

HOLDOUT_DIR = Path("artifacts/holdout")
HOLDOUT_STATE_PATH = HOLDOUT_DIR / "HOLDOUT_STATE.json"
HOLDOUT_LOCK_PATH = HOLDOUT_DIR / ".holdout.lock"


def get_holdout_dir(repo_root: Path | None = None) -> Path:
    if Path("artifacts/holdout") != HOLDOUT_DIR:
        return HOLDOUT_DIR.resolve()
    return resolve_repo_root(repo_root) / "artifacts" / "holdout"


def get_holdout_state_path(repo_root: Path | None = None) -> Path:
    if (
        HOLDOUT_STATE_PATH != HOLDOUT_DIR / "HOLDOUT_STATE.json"
        and Path("artifacts/holdout") / "HOLDOUT_STATE.json" != HOLDOUT_STATE_PATH
    ):
        return HOLDOUT_STATE_PATH.resolve()
    return get_holdout_dir(repo_root) / "HOLDOUT_STATE.json"


def get_holdout_lock_path(repo_root: Path | None = None) -> Path:
    if (
        HOLDOUT_LOCK_PATH != HOLDOUT_DIR / ".holdout.lock"
        and Path("artifacts/holdout") / ".holdout.lock" != HOLDOUT_LOCK_PATH
    ):
        return HOLDOUT_LOCK_PATH.resolve()
    return get_holdout_dir(repo_root) / ".holdout.lock"


def parse_utc_boundary(value: str) -> tuple[int, str]:
    """Parse UTC boundary strictly, returning (timestamp_ms, canonical UTC string ending in Z)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp boundary must be a non-empty string")
    val = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        try:
            dt = datetime.strptime(val, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise ValueError(f"malformed YYYY-MM-DD date: {val!r}") from exc
        if dt.strftime("%Y-%m-%d") != val:
            raise ValueError(f"malformed or non-canonical YYYY-MM-DD date: {val!r}")
    elif val.endswith("Z") or val.endswith("+00:00"):
        iso_val = val[:-1] + "+00:00" if val.endswith("Z") else val
        try:
            dt = datetime.fromisoformat(iso_val)
        except ValueError as exc:
            raise ValueError(f"malformed ISO timestamp: {val!r}") from exc
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError(f"timestamp offset must be exactly UTC: {val!r}")
    else:
        raise ValueError(
            f"naive timestamp or non-UTC offset rejected: {val!r}; "
            "must be YYYY-MM-DD, ending in Z, or ending in +00:00"
        )
    ms = int(dt.timestamp() * 1000)
    dt_check = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    if dt_check != dt:
        raise ValueError(
            f"timestamp {val!r} does not round-trip accurately to millisecond precision"
        )
    if ms % 1000 == 0:
        canonical = dt_check.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        canonical = dt_check.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return ms, canonical


def _parse_utc_date(value: str) -> int:
    ms, _ = parse_utc_boundary(value)
    return ms


def _utc_timestamp_canonical() -> str:
    now = datetime.now(UTC)
    ms = int(now.timestamp() * 1000)
    dt = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    if ms % 1000 == 0:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def get_holdout_start_ms(settings: Settings | None = None) -> int:
    if settings is None:
        settings = get_settings()
    return _parse_utc_date(settings.holdout_start_utc)


def compute_dataset_identity(
    df: pd.DataFrame,
    start_ms: int | None = None,
    end_ms: int | None = None,
    purpose: str = "evaluation",
) -> dict[str, Any]:
    """Verify unique/increasing integer open_time values and compute deterministic identity."""
    if df.empty:
        raise ValueError(f"loaded dataset for {purpose} is empty")
    if "open_time" not in df.columns:
        raise ValueError(f"loaded dataset for {purpose} missing open_time column")

    open_times = df["open_time"]
    if open_times.dtype == bool or not (
        pd.api.types.is_integer_dtype(open_times.dtype)
        or all(isinstance(x, (int, np.integer)) and not isinstance(x, bool) for x in open_times)
    ):
        raise ValueError(
            f"loaded dataset for {purpose} open_time values must be integers "
            "(not bool or float/object)"
        )

    ot_array = open_times.to_numpy(dtype=np.int64)
    if len(ot_array) > 1 and not (ot_array[1:] > ot_array[:-1]).all():
        raise ValueError(
            f"loaded dataset for {purpose} open_time values must be unique and strictly increasing"
        )

    first_open = int(ot_array[0])
    last_open = int(ot_array[-1])

    if start_ms is not None and (ot_array < start_ms).any():
        raise ValueError(
            f"loaded dataset open_time ({ot_array.min()}) precedes requested start ({start_ms})"
        )
    if end_ms is not None and (ot_array > end_ms).any():
        raise ValueError(
            f"loaded dataset open_time ({ot_array.max()}) exceeds requested end ({end_ms})"
        )

    h = hashlib.sha256()
    cols = list(df.columns)
    h.update(f"columns:{cols}\n".encode())
    dtypes = [str(df[c].dtype) for c in cols]
    h.update(f"dtypes:{dtypes}\n".encode())
    h.update(f"index_type:{type(df.index).__name__}\n".encode())
    h.update(f"index_values:{list(df.index)}\n".encode())
    row_count = len(df)
    h.update(f"row_count:{row_count}\n".encode())
    h.update(f"first_open:{first_open}\n".encode())
    h.update(f"last_open:{last_open}\n".encode())
    for row in df.itertuples(index=False):
        h.update(f"row:{tuple(row)}\n".encode())
    dataset_sha = h.hexdigest()

    return {
        "dataset_sha256": dataset_sha,
        "row_count": row_count,
        "first_open_ms": first_open,
        "last_open_ms": last_open,
        "columns": cols,
        "dtypes": dtypes,
    }


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
        compute_dataset_identity(loaded_df, start_ms, end_ms, purpose=purpose)

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
def _holdout_lock(holdout_dir: Path | None = None, timeout_sec: float = 10.0) -> Iterator[None]:
    """Cross-process lock covering check state -> exclusive create -> eval -> persist."""
    if holdout_dir is None:
        holdout_dir = get_holdout_dir()
    if holdout_dir.is_symlink():
        raise RuntimeError("holdout directory must not be a symlink")
    holdout_dir.mkdir(parents=True, exist_ok=True)
    if holdout_dir.is_symlink():
        raise RuntimeError("holdout directory must not be a symlink")
    lock_path = holdout_dir / ".holdout.lock"
    if lock_path.is_symlink():
        raise RuntimeError("holdout lock file must not be a symlink")

    start_time = time.monotonic()
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    acquired = False
    while time.monotonic() - start_time < timeout_sec:
        if lock_path.is_symlink():
            raise RuntimeError("holdout lock file must not be a symlink")
        try:
            with open(lock_path, "xb") as fh:
                fh.write(token.encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
        except OSError as exc:
            raise RuntimeError(
                f"unexpected filesystem error creating lock file {lock_path}: {exc}"
            ) from exc
    if not acquired:
        raise RuntimeError("timed out waiting for holdout lock; holdout currently running")
    try:
        yield
    finally:
        if acquired and lock_path.exists():
            if lock_path.is_symlink():
                raise RuntimeError(
                    "holdout lock file turned into a symlink during holdout execution"
                )
            try:
                content = lock_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise RuntimeError(
                    f"unexpected filesystem error reading lock file {lock_path}: {exc}"
                ) from exc
            if content == token:
                try:
                    lock_path.unlink()
                except OSError as exc:
                    raise RuntimeError(
                        f"unexpected filesystem error removing lock file {lock_path}: {exc}"
                    ) from exc
            else:
                raise RuntimeError(
                    f"holdout lock ownership mismatch: expected {token!r}, found {content!r}"
                )


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


def _verify_report_file(
    rep_path: Path, expected_hash: str, holdout_dir: Path | None = None
) -> dict[str, Any]:
    """Verify an immutable holdout report file strictly."""
    if holdout_dir is None:
        holdout_dir = get_holdout_dir()
    if rep_path.is_symlink():
        raise RuntimeError("holdout report file must not be a symlink")
    resolved = rep_path.resolve()
    holdout_resolved = holdout_dir.resolve()
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
        or not all(c in "0123456789abcdef" for c in stored_hash)
    ):
        raise RuntimeError("holdout report missing valid 64-char lowercase report_sha256")
    if stored_hash != expected_hash:
        raise RuntimeError(
            f"holdout report_sha256 ({stored_hash}) does not match expected ({expected_hash})"
        )
    actual_hash = _compute_report_hash(report_data)
    if actual_hash != stored_hash:
        raise RuntimeError("holdout report hash mismatch; content does not match report_sha256")

    # Revalidate dataset identity fields where present or where dataset metadata is included
    if any(
        k in report_data
        for k in (
            "first_open_ms",
            "last_open_ms",
            "row_count",
            "dataset_sha256",
            "dataset_identity",
            "rows",
        )
    ):
        for field in ("first_open_ms", "last_open_ms", "row_count"):
            if not isinstance(report_data.get(field), int):
                raise RuntimeError(f"holdout report missing or invalid integer field {field!r}")
        if report_data["first_open_ms"] > report_data["last_open_ms"]:
            raise RuntimeError("holdout report dataset has reversed first_open_ms/last_open_ms")
        if report_data["row_count"] <= 0:
            raise RuntimeError("holdout report row_count must be positive")
        dsha = report_data.get("dataset_sha256")
        if (
            not isinstance(dsha, str)
            or len(dsha) != 64
            or dsha != dsha.lower()
            or not all(c in "0123456789abcdef" for c in dsha)
        ):
            raise RuntimeError("holdout report missing valid 64-char lowercase dataset_sha256")

        ident = report_data.get("dataset_identity")
        if ident is not None:
            if not isinstance(ident, dict):
                raise RuntimeError("holdout report dataset_identity must be an object")
            if (
                ident.get("dataset_sha256") != dsha
                or ident.get("row_count") != report_data["row_count"]
                or ident.get("first_open_ms") != report_data["first_open_ms"]
                or ident.get("last_open_ms") != report_data["last_open_ms"]
            ):
                raise RuntimeError("holdout report dataset_identity inconsistent with metadata")

    return report_data


def load_holdout_state(
    path: Path | None = None,
    holdout_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Strictly load and validate HOLDOUT_STATE.json."""
    if path is None:
        path = get_holdout_state_path(repo_root)
        if holdout_dir is None:
            holdout_dir = get_holdout_dir(repo_root)
    else:
        if holdout_dir is None:
            holdout_dir = path.parent
    if path.is_symlink():
        raise RuntimeError("HOLDOUT_STATE.json must not be a symlink")
    resolved = path.resolve()
    holdout_resolved = holdout_dir.resolve()
    if holdout_resolved not in resolved.parents and resolved != holdout_resolved:
        raise RuntimeError(f"path traversal detected for holdout state: {path}")

    if not path.exists():
        if holdout_dir.exists():
            for child in holdout_dir.iterdir():
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

    cid = data.get("consumption_id")
    if not isinstance(cid, str) or not re.match(r"^[0-9a-f]{32}$", cid):
        raise RuntimeError("HOLDOUT_STATE.json consumption_id must be a 32-char hex UUID")

    status = data.get("status")
    if status not in ("started", "completed", "failed"):
        raise RuntimeError(f"HOLDOUT_STATE.json unknown status {status!r}")

    try:
        start_ms, can_start = parse_utc_boundary(data["reserved_start_utc"])
        end_ms, can_end = parse_utc_boundary(data["fixed_end_utc"])
        _, can_started = parse_utc_boundary(data["started_at_utc"])
    except ValueError as exc:
        raise RuntimeError(f"HOLDOUT_STATE.json boundary validation failed: {exc}") from exc

    if (
        can_start != data["reserved_start_utc"]
        or can_end != data["fixed_end_utc"]
        or can_started != data["started_at_utc"]
    ):
        raise RuntimeError(
            "HOLDOUT_STATE.json timestamps must be stored in canonical UTC ending in Z"
        )
    if end_ms < start_ms:
        raise RuntimeError(
            "HOLDOUT_STATE.json boundaries reversed: fixed_end_utc < reserved_start_utc"
        )

    sym = data.get("symbol")
    inv = data.get("interval")
    if not isinstance(sym, str) or not sym.strip() or not isinstance(inv, str) or not inv.strip():
        raise RuntimeError("HOLDOUT_STATE.json symbol and interval must be non-empty strings")

    try:
        validate_model_id(data["model_id"])
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"HOLDOUT_STATE.json invalid model_id: {exc}") from exc

    sha = data.get("model_artifact_sha256")
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or sha != sha.lower()
        or not all(c in "0123456789abcdef" for c in sha)
    ):
        raise RuntimeError(
            "HOLDOUT_STATE.json model_artifact_sha256 must be valid lowercase SHA-256"
        )

    commit = data.get("source_commit")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or commit != commit.lower()
        or not all(c in "0123456789abcdef" for c in commit)
    ):
        raise RuntimeError("HOLDOUT_STATE.json source_commit must be lowercase 40-char hex")

    if data.get("source_tree_clean") is not True:
        raise RuntimeError("HOLDOUT_STATE.json source_tree_clean must be exactly True")

    if data.get("feature_schema") != schema_fingerprint():
        raise RuntimeError(
            "HOLDOUT_STATE.json feature_schema does not match current complete schema fingerprint"
        )

    costs = data.get("costs")
    if not isinstance(costs, dict) or set(costs.keys()) != {"taker_fee", "half_spread", "slippage"}:
        raise RuntimeError(
            "HOLDOUT_STATE.json costs must be a dict with exactly taker_fee, half_spread, slippage"
        )
    for k, v in costs.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise RuntimeError(f"HOLDOUT_STATE.json costs[{k!r}] must be a finite number")

    baselines = data.get("baselines")
    if (
        not isinstance(baselines, list)
        or len(baselines) == 0
        or not all(isinstance(b, str) and b.strip() for b in baselines)
        or len(set(baselines)) != len(baselines)
    ):
        raise RuntimeError(
            "HOLDOUT_STATE.json baselines must be a non-empty list of unique non-empty strings"
        )

    scenarios = data.get("scenarios")
    if scenarios != ["base", "costs2x", "delay1"]:
        raise RuntimeError(
            "HOLDOUT_STATE.json scenarios must exactly equal ['base', 'costs2x', 'delay1']"
        )

    base_keys = set(required) | {"schema_version"}
    if status == "started" or status == "completed":
        allowed_keys = base_keys | {"report_filename", "report_sha256"}
    elif status == "failed":
        allowed_keys = base_keys | {
            "failure_class",
            "reason",
            "failed_at_utc",
            "report_filename",
            "report_sha256",
        }
    else:
        allowed_keys = base_keys

    if status == "failed":
        fc = data.get("failure_class")
        reason = data.get("reason")
        failed_at = data.get("failed_at_utc")
        if (
            not isinstance(fc, str)
            or not fc.strip()
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise RuntimeError("failed state must include valid failure_class and reason")
        if not isinstance(failed_at, str):
            raise RuntimeError("failed state must include failed_at_utc")
        parse_utc_boundary(failed_at)
        for forbidden_key in (
            "metrics",
            "dataset_sha256",
            "dataset_identity",
            "rows",
            "first_open_ms",
            "last_open_ms",
            "row_count",
        ):
            if forbidden_key in data:
                raise RuntimeError(f"failed state must not contain {forbidden_key}")

    extra_keys = set(data.keys()) - allowed_keys
    if extra_keys:
        raise RuntimeError(f"unknown or extra fields in HOLDOUT_STATE.json: {sorted(extra_keys)}")

    if status == "completed":
        rep_name = data.get("report_filename")
        rep_sha = data.get("report_sha256")
        if not isinstance(rep_name, str) or not rep_name or "/" in rep_name or "\\" in rep_name:
            raise RuntimeError("completed state report_filename must be a clean basename")
        if (
            not isinstance(rep_sha, str)
            or len(rep_sha) != 64
            or rep_sha != rep_sha.lower()
            or not all(c in "0123456789abcdef" for c in rep_sha)
        ):
            raise RuntimeError("completed state report_sha256 must be valid lowercase SHA-256")
        rep_path = holdout_dir / rep_name
        report = _verify_report_file(rep_path, rep_sha, holdout_dir=holdout_dir)
        if report.get("consumption_id") != data["consumption_id"]:
            raise RuntimeError("report consumption_id does not match state")
        if report.get("model_id") != data["model_id"]:
            raise RuntimeError("report model_id does not match state")
        if report.get("model_artifact_sha256") != data["model_artifact_sha256"]:
            raise RuntimeError("report model_artifact_sha256 does not match state")
        if report.get("source_commit") != data["source_commit"]:
            raise RuntimeError("report source_commit does not match state")
        if report.get("symbol") != data["symbol"]:
            raise RuntimeError("report symbol does not match state")
        if report.get("interval") != data["interval"]:
            raise RuntimeError("report interval does not match state")
        if report.get("reserved_start_utc") != data["reserved_start_utc"]:
            raise RuntimeError("report reserved_start_utc does not match state")
        if report.get("fixed_end_utc") != data["fixed_end_utc"]:
            raise RuntimeError("report fixed_end_utc does not match state")
        if report.get("costs") != data["costs"]:
            raise RuntimeError("report costs does not match state")
        if report.get("report_sha256") != data["report_sha256"]:
            raise RuntimeError("report report_sha256 does not match state")
    else:
        if data.get("report_filename") is not None or data.get("report_sha256") is not None:
            raise RuntimeError(
                f"state status {status!r} must not claim report_filename/report_sha256"
            )
    return data


def run_final_holdout(
    settings: Settings,
    model_id: str,
    end_utc: str,
    models_dir: Path | None = None,
) -> tuple[Path, str]:
    """Run the untouched final holdout ONCE for the frozen champion under strict isolation."""
    if models_dir is None:
        models_dir = settings.models_dir

    holdout_dir = get_holdout_dir()
    state_path = get_holdout_state_path()

    with _holdout_lock(holdout_dir):
        existing_state = load_holdout_state(state_path, holdout_dir=holdout_dir)
        if existing_state:
            raise RuntimeError(
                f"holdout already consumed: status is {existing_state['status']}. see {state_path}"
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

        start_ms, canonical_start = parse_utc_boundary(settings.holdout_start_utc)
        end_ms, canonical_end = parse_utc_boundary(end_utc)
        if end_ms < start_ms:
            raise ValueError(
                f"requested fixed_end ({canonical_end}) precedes holdout start ({canonical_start})"
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
        started_at = _utc_timestamp_canonical()
        started_state: dict[str, Any] = {
            "schema_version": 1,
            "consumption_id": consumption_id,
            "started_at_utc": started_at,
            "status": "started",
            "reserved_start_utc": canonical_start,
            "fixed_end_utc": canonical_end,
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
        if state_path.is_symlink():
            raise RuntimeError("HOLDOUT_STATE.json must not be a symlink")
        _write_exclusive_file(state_path, started_bytes)

        temp_files: list[Path] = []
        try:
            store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
            candles = store.read(start_ms, end_ms)
            check_reserved_period_overlap(
                start_ms,
                end_ms,
                candles,
                purpose="holdout",
                settings=settings,
            )

            identity = compute_dataset_identity(candles, start_ms, end_ms, purpose="holdout")
            dataset_hash = identity["dataset_sha256"]

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
                "created_at_utc": _utc_timestamp_canonical(),
                "symbol": settings.symbol,
                "interval": settings.interval,
                "reserved_start_utc": canonical_start,
                "fixed_end_utc": canonical_end,
                "first_open_ms": identity["first_open_ms"],
                "last_open_ms": identity["last_open_ms"],
                "row_count": identity["row_count"],
                "dataset_sha256": dataset_hash,
                "dataset_identity": identity,
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
            rep_path = holdout_dir / rep_filename
            if rep_path.is_symlink():
                raise RuntimeError("holdout report must not be a symlink")
            _write_exclusive_file(rep_path, payload)
            _verify_report_file(rep_path, report_hash, holdout_dir=holdout_dir)

            completed_state = {
                **started_state,
                "status": "completed",
                "report_filename": rep_filename,
                "report_sha256": report_hash,
            }
            completed_bytes = (_json_dumps(completed_state) + "\n").encode("utf-8")
            _write_atomically(state_path, completed_bytes)

            return rep_path, report_hash

        except Exception as exc:
            try:
                if state_path.exists():
                    current = _json_loads_strict(state_path.read_text(encoding="utf-8"), "state")
                    if isinstance(current, dict) and current.get("status") == "started":
                        failed_state = {
                            **started_state,
                            "status": "failed",
                            "failure_class": type(exc).__name__,
                            "reason": str(exc)[:200],
                            "failed_at_utc": _utc_timestamp_canonical(),
                            "report_filename": None,
                            "report_sha256": None,
                        }
                        failed_bytes = (_json_dumps(failed_state) + "\n").encode("utf-8")
                        _write_atomically(state_path, failed_bytes)
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
