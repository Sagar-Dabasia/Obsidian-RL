"""Controlled model promotion: candidate -> champion via explicit command, with rollback.

The deployed policy stays frozen; nothing here trains or self-modifies. Candidates are
evaluated on predefined validation slices against the current champion and deterministic
baselines, checked against risk thresholds, and promoted only by an explicit CLI call.
The previous champion is preserved (promotion state 'retired') for rollback.

Evidence design
---------------
* Every evaluation creates an immutable content-addressed report file under
  models/<id>/evaluations/<utc_ms>-<sha256[:12]>.json.
* latest.json points to the most recent report; promotion loads via latest.json only.
* CHAMPION.json is the sole authoritative promotion-state file; promote() and rollback()
  update it with a single tempfile+fsync+os.replace operation.
* set_promotion() on individual model metadata is never called during promotion/rollback;
  those metadata fields remain for backward-compat read-only inspection only.
"""

import hashlib
import json
import math
import os
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian_rl.evaluation.walkforward import EvalRow, evaluate_strategies_on_slice
from obsidian_rl.features.observation import schema_fingerprint
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.baselines import default_baselines
from obsidian_rl.training.registry import (
    MODEL_FILE,
    artifact_sha256,
    get_git_source_state,
    load_record,
    validate_model_id,
)

CHAMPION_FILE = "CHAMPION.json"
EVALUATIONS_DIR = "evaluations"
EVALUATION_REPORT_FILE = "evaluation-v1.json"  # kept for legacy detection only
LATEST_POINTER_FILE = "latest.json"
EVALUATION_REPORT_SCHEMA_VERSION = 2
CHAMPION_SCHEMA_VERSION = 1

_MAX_MODEL_ID_LENGTH = 128  # sanity limit for path-segment validation


class PromotionEvidenceError(ValueError):
    """Candidate evaluation evidence is missing, invalid, or no longer matches."""


@dataclass(frozen=True)
class PromotionThresholds:
    """Risk gates a candidate must pass on the validation slice (base cost scenario)."""

    max_drawdown_limit: float = 0.35
    min_net_return_vs_flat: float = -0.05  # cannot lose >5% where flat loses ~0
    must_not_trail_champion_by: float = 0.02  # net-return margin vs current champion

    def __post_init__(self) -> None:
        for name in ("max_drawdown_limit", "min_net_return_vs_flat", "must_not_trail_champion_by"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{name}={value!r} must be int or float, not {type(value).__name__}"
                )
            if not math.isfinite(value):
                raise ValueError(f"{name}={value!r} must be finite")
        if self.max_drawdown_limit < 0 or self.max_drawdown_limit > 1:
            raise ValueError(f"max_drawdown_limit={self.max_drawdown_limit} must be in [0, 1]")
        if self.must_not_trail_champion_by < 0:
            raise ValueError(
                f"must_not_trail_champion_by={self.must_not_trail_champion_by} must be >= 0"
            )


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _champion_path(models_dir: Path) -> Path:
    return Path(models_dir) / CHAMPION_FILE


def _evaluations_dir(models_dir: Path, candidate_id: str) -> Path:
    candidate_id = validate_model_id(candidate_id)
    return Path(models_dir) / candidate_id / EVALUATIONS_DIR


def _latest_pointer_path(models_dir: Path, candidate_id: str) -> Path:
    candidate_id = validate_model_id(candidate_id)
    return _evaluations_dir(models_dir, candidate_id) / LATEST_POINTER_FILE


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        raise PromotionEvidenceError(
            f"evaluation report field {field!r} must be lowercase 64-char SHA-256"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise PromotionEvidenceError(
            f"evaluation report field {field!r} must be a SHA-256"
        ) from exc
    return value


def _load_and_verify_latest_pointer(
    models_dir: Path, candidate_id: str
) -> tuple[dict[str, Any], Path]:
    candidate_id = validate_model_id(candidate_id)
    ptr_path = _latest_pointer_path(models_dir, candidate_id)
    if ptr_path.is_symlink():
        raise PromotionEvidenceError("latest.json must not be a symlink")
    evals_dir = _evaluations_dir(models_dir, candidate_id).resolve()
    if ptr_path.exists() and ptr_path.resolve() != evals_dir / LATEST_POINTER_FILE:
        raise PromotionEvidenceError("latest.json escapes candidate evaluations directory")
    if not ptr_path.is_file():
        legacy = Path(models_dir) / candidate_id / EVALUATION_REPORT_FILE
        if legacy.is_file():
            raise PromotionEvidenceError(
                f"candidate {candidate_id!r} has only legacy evaluation-v1.json evidence; "
                "reevaluation with the current evaluator is required before promotion"
            )
        raise PromotionEvidenceError(
            f"no evaluation report for {candidate_id}; candidate-eval must pass before promotion"
        )
    ptr_text = ptr_path.read_text(encoding="utf-8")
    ptr_data = _json_loads_strict(ptr_text, "latest.json")
    if not isinstance(ptr_data, dict):
        raise PromotionEvidenceError("latest.json root must be an object")

    for required_key in ("report_filename", "report_sha256", "model_id", "model_artifact_sha256"):
        if required_key not in ptr_data:
            raise PromotionEvidenceError(f"latest.json missing {required_key}")

    if ptr_data.get("model_id") != candidate_id:
        raise PromotionEvidenceError("latest.json model_id does not match requested candidate ID")

    filename = ptr_data.get("report_filename")
    if not isinstance(filename, str) or not filename:
        raise PromotionEvidenceError("latest.json missing or invalid report_filename")
    safe = Path(filename)
    if safe.name != filename or "/" in filename or "\\" in filename or ".." in filename:
        raise PromotionEvidenceError("latest.json report_filename contains illegal path component")

    _require_sha256(ptr_data.get("report_sha256"), "latest.json report_sha256")
    _require_sha256(ptr_data.get("model_artifact_sha256"), "latest.json model_artifact_sha256")

    report_path = _evaluations_dir(models_dir, candidate_id) / filename
    if report_path.is_symlink():
        raise PromotionEvidenceError("immutable evaluation report must not be a symlink")
    if not report_path.is_file():
        raise PromotionEvidenceError(
            f"immutable report file {filename!r} referenced by latest.json does not exist"
        )
    try:
        resolved_report = report_path.resolve()
        resolved_report.relative_to(evals_dir)
    except ValueError as exc:
        raise PromotionEvidenceError(
            "resolved evaluation report path escapes candidate evaluations directory"
        ) from exc
    if resolved_report.parent != evals_dir:
        raise PromotionEvidenceError(
            "resolved evaluation report path is outside candidate evaluations directory"
        )
    return ptr_data, report_path


def evaluation_report_path(models_dir: Path, candidate_id: str) -> Path:
    """Return the *latest* immutable report path via latest.json, or raise."""
    _, report_path = _load_and_verify_latest_pointer(models_dir, candidate_id)
    return report_path


def _validation_data_sha256(candles: pd.DataFrame) -> str:
    """Hash validation data including its column order, dtypes, index, and values."""
    descriptor = {
        "columns": [str(column) for column in candles.columns],
        "dtypes": [str(dtype) for dtype in candles.dtypes],
    }
    digest = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    row_hashes = pd.util.hash_pandas_object(candles, index=True, categorize=True)
    digest.update(row_hashes.to_numpy().tobytes())
    return digest.hexdigest()


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _utc_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Strict numeric validation
# ---------------------------------------------------------------------------


def _require_finite(value: object, field: str) -> float:
    """Require a finite real number (not bool, not NaN, not ±inf).

    Parameters
    ----------
    value:  the raw value from a parsed JSON object
    field:  dot-path label used in error messages
    """
    if isinstance(value, bool):
        raise PromotionEvidenceError(f"evidence field {field!r} must be a finite number, got bool")
    if not isinstance(value, (int, float)):
        raise PromotionEvidenceError(
            f"evidence field {field!r} must be a finite number, got {type(value).__name__}"
        )
    if not math.isfinite(value):
        raise PromotionEvidenceError(f"evidence field {field!r} must be finite, got {value!r}")
    return float(value)


# ---------------------------------------------------------------------------
# JSON helpers — never allow NaN/Infinity
# ---------------------------------------------------------------------------


def _json_dumps(obj: Any) -> str:
    """Canonical JSON serialisation that raises on non-finite floats."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_loads_strict(text: str, label: str) -> Any:
    """Parse JSON and reject Python-extension NaN/Infinity constants.

    Python's json.loads() accepts 'NaN', 'Infinity', '-Infinity' by default;
    we close that gap by re-serialising with allow_nan=False after parsing.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PromotionEvidenceError(f"{label} is malformed JSON") from exc
    # Detect any embedded NaN/Infinity that slipped in
    try:
        json.dumps(obj, allow_nan=False)
    except ValueError as exc:
        raise PromotionEvidenceError(f"{label} contains non-finite JSON value: {exc}") from exc
    return obj


# ---------------------------------------------------------------------------
# Content-addressed report files
# ---------------------------------------------------------------------------


def _canonical_payload(report: dict[str, Any]) -> bytes:
    """Deterministic bytes over the report payload, excluding report_sha256 itself."""
    payload = {k: v for k, v in report.items() if k != "report_sha256"}
    return _json_dumps(payload).encode("utf-8")


def _compute_report_hash(report: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(report)).hexdigest()


def _report_filename(utc_ms: int, report_hash: str) -> str:
    return f"evaluation-v1-{utc_ms}-{uuid.uuid4().hex[:8]}-{report_hash}.json"


def _write_atomically(path: Path, content: bytes) -> None:
    """Write *content* to *path* atomically (temp + fsync + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp = Path(fh.name)
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def _write_exclusive_file(path: Path, content: bytes) -> None:
    """Create *path* exclusively and flush+fsync; fail explicitly on collision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "xb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
    except FileExistsError as exc:
        raise PromotionEvidenceError(
            f"exclusive report file creation failed; report collision at {path.name}"
        ) from exc


@contextmanager
def _evaluation_lock(
    models_dir: Path, candidate_id: str, timeout_sec: float = 10.0
) -> Iterator[None]:
    """Candidate-specific cross-process lock for evaluation updates."""
    evals_dir = _evaluations_dir(models_dir, candidate_id)
    evals_dir.mkdir(parents=True, exist_ok=True)
    lock_path = evals_dir / ".eval.lock"
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
        raise PromotionEvidenceError(
            f"timed out waiting for evaluation lock on {candidate_id}; already running"
        )
    try:
        yield
    finally:
        if acquired and lock_path.exists():
            try:
                if lock_path.read_text(encoding="utf-8").strip() == token:
                    lock_path.unlink()
            except OSError:
                pass


@contextmanager
def _champion_lock(models_dir: Path, timeout_sec: float = 10.0) -> Iterator[None]:
    """Cross-process lock for champion promotion state updates across models_dir."""
    Path(models_dir).mkdir(parents=True, exist_ok=True)
    lock_path = Path(models_dir) / ".champion.lock"
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
        raise PromotionEvidenceError(
            f"timed out waiting for champion lock on {models_dir}; already running"
        )
    try:
        yield
    finally:
        if acquired and lock_path.exists():
            try:
                if lock_path.read_text(encoding="utf-8").strip() == token:
                    lock_path.unlink()
            except OSError:
                pass


def _write_evaluation_report(
    models_dir: Path,
    candidate_id: str,
    report: dict[str, Any],
) -> Path:
    """Persist an immutable content-addressed report with exclusive creation under lock."""
    candidate_id = validate_model_id(candidate_id)
    ts = _utc_ms()
    report_hash = _compute_report_hash(report)
    report_with_hash = {**report, "report_sha256": report_hash}
    payload = (_json_dumps(report_with_hash) + "\n").encode("utf-8")

    with _evaluation_lock(models_dir, candidate_id):
        evals_dir = _evaluations_dir(models_dir, candidate_id)
        filename = _report_filename(ts, report_hash)
        report_path = evals_dir / filename
        if report_path.is_symlink():
            raise PromotionEvidenceError("immutable evaluation report must not be a symlink")
        _write_exclusive_file(report_path, payload)

        if not report_path.is_file() or report_path.is_symlink():
            raise PromotionEvidenceError(f"failed to verify created immutable report {filename!r}")
        verify_data = _json_loads_strict(report_path.read_text(encoding="utf-8"), "verify")
        if _compute_report_hash(verify_data) != report_hash:
            raise PromotionEvidenceError(
                f"newly written report {filename!r} failed hash verification"
            )

        latest_data = {
            "report_filename": filename,
            "report_sha256": report_hash,
            "model_id": candidate_id,
            "model_artifact_sha256": report.get("model_artifact_sha256", ""),
        }
        latest_bytes = (_json_dumps(latest_data) + "\n").encode("utf-8")
        ptr_path = _latest_pointer_path(models_dir, candidate_id)
        if ptr_path.is_symlink():
            raise PromotionEvidenceError("latest.json must not be a symlink")
        _write_atomically(ptr_path, latest_bytes)
    return report_path


# ---------------------------------------------------------------------------
# Evidence loading and validation
# ---------------------------------------------------------------------------


def _load_evaluation_report(models_dir: Path, candidate_id: str) -> dict[str, Any]:
    """Load the latest evaluation report via latest.json, verifying its hash and pointer."""
    candidate_id = validate_model_id(candidate_id)
    ptr_data, report_path = _load_and_verify_latest_pointer(models_dir, candidate_id)

    report_text = report_path.read_text(encoding="utf-8")
    report_with_hash = _json_loads_strict(report_text, f"report {report_path.name!r}")
    if not isinstance(report_with_hash, dict):
        raise PromotionEvidenceError("evaluation report root must be an object")

    stored_hash = report_with_hash.get("report_sha256")
    if (
        not isinstance(stored_hash, str)
        or len(stored_hash) != 64
        or stored_hash != stored_hash.lower()
    ):
        raise PromotionEvidenceError("report missing or invalid lowercase report_sha256")
    payload_fields = {k: v for k, v in report_with_hash.items() if k != "report_sha256"}
    actual_hash = hashlib.sha256(_json_dumps(payload_fields).encode("utf-8")).hexdigest()
    if actual_hash != stored_hash:
        raise PromotionEvidenceError("evaluation report hash mismatch; file has been tampered with")
    if ptr_data["report_sha256"] != stored_hash:
        raise PromotionEvidenceError("latest.json report_sha256 does not match the report file")

    if ptr_data["model_artifact_sha256"] != report_with_hash.get("model_artifact_sha256"):
        raise PromotionEvidenceError(
            "latest.json model_artifact_sha256 does not match embedded report artifact hash"
        )
    candidate_artifact = Path(models_dir) / candidate_id / MODEL_FILE
    if candidate_artifact.exists():
        current_art_hash = artifact_sha256(candidate_artifact)
        if ptr_data["model_artifact_sha256"] != current_art_hash:
            raise PromotionEvidenceError(
                "model artifact checksum differs: latest.json model_artifact_sha256 "
                "does not match current candidate artifact hash"
            )

    return payload_fields


def _require_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PromotionEvidenceError(f"evaluation report field {field!r} must be an object")
    return value


def _validate_evaluation_report(
    report: object,
    *,
    candidate_id: str,
    record_feature_schema: object,
    artifact_checksum: str,
) -> None:
    candidate_id = validate_model_id(candidate_id)
    report_data = _require_mapping(report, "report")
    if report_data.get("schema_version") != EVALUATION_REPORT_SCHEMA_VERSION:
        raise PromotionEvidenceError(
            "evaluation report has an unsupported or missing schema_version; "
            "reevaluation is required"
        )
    if report_data.get("model_id") != candidate_id:
        raise PromotionEvidenceError(
            "evaluation report model_id does not match the promotion candidate"
        )
    if report_data.get("model_artifact_filename") != MODEL_FILE:
        raise PromotionEvidenceError("evaluation report model artifact filename is invalid")
    evaluated_checksum = _require_sha256(
        report_data.get("model_artifact_sha256"), "model_artifact_sha256"
    )
    if evaluated_checksum != artifact_checksum:
        raise PromotionEvidenceError("model artifact checksum differs from the evaluated artifact")

    report_schema = _require_mapping(report_data.get("feature_schema"), "feature_schema")
    current_schema = schema_fingerprint()
    if report_schema != current_schema or record_feature_schema != current_schema:
        raise PromotionEvidenceError(
            "feature schema fingerprint differs from the evaluated candidate"
        )

    validation = _require_mapping(report_data.get("validation"), "validation")
    _require_sha256(validation.get("data_sha256"), "validation.data_sha256")
    for field in ("start_utc_ms", "end_utc_ms"):
        value = validation.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise PromotionEvidenceError(
                f"evaluation report field validation.{field} must be an integer"
            )
    if validation["end_utc_ms"] < validation["start_utc_ms"]:
        raise PromotionEvidenceError("evaluation report validation range is invalid")

    cost_model = _require_mapping(report_data.get("cost_model"), "cost_model")
    if set(cost_model) != set(asdict(CostModel())):
        raise PromotionEvidenceError("evaluation report cost_model configuration is incomplete")
    for key, val in cost_model.items():
        _require_finite(val, f"cost_model.{key}")

    source_commit = report_data.get("source_git_commit")
    eval_commit = report_data.get("evaluation_source_git_commit", source_commit)
    if (
        not isinstance(eval_commit, str)
        or len(eval_commit) != 40
        or not all(c in "0123456789abcdef" for c in eval_commit.lower())
    ):
        raise PromotionEvidenceError(
            "evaluation report source Git commit is missing or not 40-char hex"
        )
    if (
        report_data.get("source_tree_clean") is not True
        or report_data.get("evaluation_source_tree_clean", True) is not True
    ):
        raise PromotionEvidenceError("evaluation report source_tree_clean must be true")
    timestamp = report_data.get("evaluated_at_utc")
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise PromotionEvidenceError("evaluation report UTC timestamp is missing or invalid")

    metrics = _require_mapping(report_data.get("metrics"), "metrics")
    candidate_metrics = _require_mapping(metrics.get("candidate"), "metrics.candidate")
    for field in ("net_return", "max_drawdown"):
        val = candidate_metrics.get(field)
        if val is None:
            raise PromotionEvidenceError(f"evaluation report metrics.candidate.{field} is missing")
        _require_finite(val, f"metrics.candidate.{field}")

    thresholds = _require_mapping(report_data.get("thresholds"), "thresholds")
    if set(thresholds) != set(asdict(PromotionThresholds())):
        raise PromotionEvidenceError("evaluation report threshold configuration is incomplete")
    for key, val in thresholds.items():
        _require_finite(val, f"thresholds.{key}")

    if report_data.get("passes") is not True:
        raise PromotionEvidenceError("evaluation report does not record a passing candidate")


# ---------------------------------------------------------------------------
# CHAMPION.json  — authoritative promotion state
# ---------------------------------------------------------------------------


def validate_champion_state(data: object, models_dir: Path | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("CHAMPION.json root must be an object")
    schema_ver = data.get("schema_version")
    if schema_ver != CHAMPION_SCHEMA_VERSION:
        raise RuntimeError(f"CHAMPION.json unsupported schema_version {schema_ver}")
    gen = data.get("generation")
    if isinstance(gen, bool) or not isinstance(gen, int) or gen < 0:
        raise RuntimeError(f"CHAMPION.json generation must be a non-negative integer, got {gen!r}")
    model_id = data.get("model_id")
    if model_id is not None:
        model_id = validate_model_id(model_id)
    lineage = data.get("lineage")
    if not isinstance(lineage, list):
        raise RuntimeError("CHAMPION.json lineage must be a list")
    for item in lineage:
        validate_model_id(item)
    if len(lineage) != len(set(lineage)):
        raise RuntimeError("CHAMPION.json lineage contains duplicate model IDs")
    if model_id is None:
        if lineage:
            raise RuntimeError("CHAMPION.json model_id is null but lineage is not empty")
        if data.get("model_artifact_sha256") is not None:
            raise RuntimeError(
                "CHAMPION.json model_id is null but model_artifact_sha256 is not null"
            )
    else:
        if not lineage:
            raise RuntimeError("CHAMPION.json champion exists but lineage is empty")
        if lineage[-1] != model_id:
            msg = (
                f"CHAMPION.json lineage[-1] ({lineage[-1]!r}) "
                f"does not match model_id ({model_id!r})"
            )
            raise RuntimeError(msg)
        art_sha = data.get("model_artifact_sha256")
        if models_dir is None and art_sha is None:
            pass
        elif not isinstance(art_sha, str) or len(art_sha) != 64 or art_sha != art_sha.lower():
            raise RuntimeError(
                "CHAMPION.json model_artifact_sha256 must be a valid 64-char lowercase SHA-256"
            )
        if models_dir:
            model_dir = Path(models_dir) / model_id
            if not model_dir.exists() or not (model_dir / MODEL_FILE).exists():
                raise RuntimeError(
                    f"CHAMPION.json referenced model_id {model_id} artifact does not exist"
                )
            record = load_record(model_dir)
            if art_sha != record.metadata.get("artifact_sha256") or art_sha != artifact_sha256(
                model_dir / MODEL_FILE
            ):
                raise RuntimeError(
                    f"CHAMPION.json model_artifact_sha256 mismatch for champion {model_id}"
                )

    history = data.get("history")
    if not isinstance(history, list):
        raise RuntimeError("CHAMPION.json history must be a list")
    return data


def normalize_legacy_champion_state(
    data: dict[str, Any], models_dir: Path | None = None
) -> dict[str, Any]:
    """Explicit tested normalization path for legitimate legacy CHAMPION.json files."""
    if (
        data.get("schema_version") is not None
        and data.get("schema_version") != CHAMPION_SCHEMA_VERSION
    ):
        raise RuntimeError(f"unsupported CHAMPION.json schema_version {data.get('schema_version')}")
    if "schema_version" in data:
        return validate_champion_state(data, models_dir)

    valid_legacy_keys = {"model_id", "lineage", "history", "changed_at_utc_ms", "action"}
    if not set(data.keys()).issubset(valid_legacy_keys):
        raise RuntimeError("malformed legacy CHAMPION.json: unrecognized fields present")
    model_id = data.get("model_id")
    if model_id is not None:
        model_id = validate_model_id(model_id)
        if models_dir and not (Path(models_dir) / model_id).exists():
            raise RuntimeError(f"legacy champion model {model_id} does not exist in {models_dir}")
        lineage = data.get("lineage")
        if lineage is None:
            lineage = [model_id]
        elif not isinstance(lineage, list) or not lineage or lineage[-1] != model_id:
            raise RuntimeError("malformed legacy CHAMPION.json: lineage inconsistent with model_id")
        else:
            lineage = [validate_model_id(m) for m in lineage]
            if len(lineage) != len(set(lineage)):
                raise RuntimeError("malformed legacy CHAMPION.json: duplicate IDs in lineage")
        art_sha = None
        if models_dir and (Path(models_dir) / model_id / MODEL_FILE).exists():
            art_sha = artifact_sha256(Path(models_dir) / model_id / MODEL_FILE)
            load_record(Path(models_dir) / model_id)
    else:
        lineage = data.get("lineage", [])
        if lineage:
            raise RuntimeError(
                "malformed legacy CHAMPION.json: model_id is None but lineage is non-empty"
            )
        art_sha = None
    history = data.get("history", [])
    if not isinstance(history, list):
        raise RuntimeError("malformed legacy CHAMPION.json: history must be a list")
    return {
        "schema_version": CHAMPION_SCHEMA_VERSION,
        "generation": len(history),
        "model_id": model_id,
        "model_artifact_sha256": art_sha,
        "lineage": lineage,
        "history": history,
        "updated_at_utc": _utc_timestamp(),
    }


def current_champion(models_dir: Path) -> str | None:
    """Return the current champion model_id from CHAMPION.json, or None."""
    path = _champion_path(models_dir)
    if not path.exists():
        return None
    data = _load_champion_data(path, models_dir)
    model_id = data.get("model_id")
    return str(model_id) if model_id else None


def _load_champion_data(path: Path, models_dir: Path | None = None) -> dict[str, Any]:
    """Load CHAMPION.json; strictly validate or normalize legacy files; reject malformed files."""
    if not path.exists():
        return {
            "schema_version": CHAMPION_SCHEMA_VERSION,
            "generation": 0,
            "model_id": None,
            "model_artifact_sha256": None,
            "lineage": [],
            "history": [],
            "updated_at_utc": _utc_timestamp(),
        }
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"CHAMPION.json is malformed JSON; manual inspection required: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("CHAMPION.json root is not an object; manual inspection required")
    if "schema_version" not in data:
        data = normalize_legacy_champion_state(data, models_dir)
    return validate_champion_state(data, models_dir)


def _write_champion_atomically(path: Path, data: dict[str, Any], action: str) -> None:
    """Single atomic tempfile+fsync+os.replace write for CHAMPION.json."""
    data.setdefault("history", []).append(
        {
            "model_id": data.get("model_id"),
            "lineage": list(data.get("lineage", [])),
            "generation": data.get("generation", 0),
            "changed_at_utc_ms": _utc_ms(),
            "action": action,
        }
    )
    data["updated_at_utc"] = _utc_timestamp()
    payload = (json.dumps(data, indent=1) + "\n").encode("utf-8")
    _write_atomically(path, payload)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _check_training_provenance(record: Any) -> str:
    if record.metadata.get("training_source_tree_clean") is not True:
        raise PromotionEvidenceError(
            "model metadata lacks clean training provenance (training_source_tree_clean)"
        )
    commit = record.metadata.get("training_source_git_commit")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or not all(c in "0123456789abcdef" for c in commit.lower())
    ):
        raise PromotionEvidenceError(
            "model metadata lacks valid 40-char hex training_source_git_commit"
        )
    return commit.lower()


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

    candidate_id = validate_model_id(candidate_id)
    thresholds = thresholds or PromotionThresholds()
    thresholds.__post_init__()
    cost_model = cost_model or CostModel()
    cost_model.__post_init__()
    candidate_dir = Path(models_dir) / candidate_id
    record = load_record(candidate_dir)  # hard gate: schema + checksum
    _check_training_provenance(record)
    current_schema = schema_fingerprint()
    if record.metadata.get("feature_schema") != current_schema:
        raise PromotionEvidenceError(
            "candidate metadata feature schema is not the complete current schema"
        )
    if val_candles.empty or "open_time" not in val_candles:
        raise ValueError("validation candles must be non-empty and include open_time")
    git_state = get_git_source_state()
    if not git_state.commit or len(git_state.commit) != 40:
        raise PromotionEvidenceError(
            "unable to resolve source Git commit; refusing to write evidence"
        )
    if not git_state.is_clean:
        dirty_summary = ", ".join(git_state.dirty_paths[:5])
        if len(git_state.dirty_paths) > 5:
            dirty_summary += f" (+{len(git_state.dirty_paths) - 5} more)"
        msg = (
            f"working tree is dirty ({dirty_summary}); "
            "refusing to write promotable evaluation evidence"
        )
        raise PromotionEvidenceError(msg)

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

    def _check_metric_finite(val: float, name: str) -> float | None:
        if not math.isfinite(val):
            failures.append(f"candidate metric {name!r} is non-finite ({val!r})")
            return None
        return val

    safe_drawdown = _check_metric_finite(cand.max_drawdown, "max_drawdown")
    safe_net_return = _check_metric_finite(cand.net_return, "net_return")

    if safe_drawdown is not None and safe_drawdown > thresholds.max_drawdown_limit:
        failures.append(
            f"max drawdown {cand.max_drawdown:.3f} > limit {thresholds.max_drawdown_limit}"
        )
    if safe_net_return is not None and safe_net_return < thresholds.min_net_return_vs_flat:
        failures.append(
            f"net return {cand.net_return:.4f} below floor {thresholds.min_net_return_vs_flat}"
        )
    if champion_id and safe_net_return is not None and "champion" in by_id:
        champ = by_id["champion"]
        if (
            math.isfinite(champ.net_return)
            and cand.net_return < champ.net_return - thresholds.must_not_trail_champion_by
        ):
            failures.append(
                f"trails champion by {champ.net_return - cand.net_return:.4f} "
                f"(> {thresholds.must_not_trail_champion_by})"
            )

    def _sanitise(m: Any) -> dict[str, object]:
        raw = m.to_dict()
        return {
            k: (None if isinstance(v, float) and not math.isfinite(v) else v)
            for k, v in raw.items()
        }

    report: dict[str, Any] = {
        "schema_version": EVALUATION_REPORT_SCHEMA_VERSION,
        "model_id": candidate_id,
        "model_artifact_filename": MODEL_FILE,
        "model_artifact_sha256": artifact_sha256(candidate_dir / MODEL_FILE),
        "feature_schema": current_schema,
        "validation": {
            "data_sha256": _validation_data_sha256(val_candles),
            "start_utc_ms": int(val_candles["open_time"].iloc[0]),
            "end_utc_ms": int(val_candles["open_time"].iloc[-1]),
        },
        "cost_model": asdict(cost_model),
        "source_git_commit": git_state.commit,
        "source_tree_clean": git_state.is_clean,
        "evaluation_source_git_commit": git_state.commit,
        "evaluation_source_tree_clean": git_state.is_clean,
        "evaluated_at_utc": _utc_timestamp(),
        "thresholds": asdict(thresholds),
        "champion_id": champion_id,
        "passes": not failures,
        "failures": failures,
        "metrics": {sid: _sanitise(m) for sid, m in by_id.items()},
    }
    _write_evaluation_report(models_dir, candidate_id, report)
    return report


def promote(models_dir: Path, model_id: str) -> None:
    """Explicitly promote a validated candidate to champion; retire the old champion."""
    model_id = validate_model_id(model_id)
    with _champion_lock(models_dir):
        candidate_dir = Path(models_dir) / model_id
        record = load_record(candidate_dir)
        if record.model_id != model_id:
            raise PromotionEvidenceError(
                "candidate metadata model_id does not match the promotion candidate"
            )
        _check_training_provenance(record)
        report = _load_evaluation_report(models_dir, model_id)
        _validate_evaluation_report(
            report,
            candidate_id=model_id,
            record_feature_schema=record.metadata.get("feature_schema"),
            artifact_checksum=artifact_sha256(candidate_dir / MODEL_FILE),
        )
        current_state = get_git_source_state()
        if not current_state.is_clean:
            raise PromotionEvidenceError("working tree is dirty; refusing to promote")
        eval_commit = report.get("evaluation_source_git_commit", report.get("source_git_commit"))
        if current_state.commit != eval_commit:
            raise PromotionEvidenceError(
                "current source commit differs from evaluation source commit; reevaluation required after code changes"
            )
        path = _champion_path(models_dir)
        data = _load_champion_data(path, models_dir)
        old = data.get("model_id")
        if old == model_id:
            return
        if model_id in data.get("lineage", []):
            raise PromotionEvidenceError(f"candidate {model_id!r} already in champion lineage")
        data["model_id"] = model_id
        data["lineage"] = [*data.get("lineage", []), model_id]
        data["generation"] = data.get("generation", 0) + 1
        data["model_artifact_sha256"] = artifact_sha256(candidate_dir / MODEL_FILE)
        _write_champion_atomically(path, data, action=f"promote:{model_id}")


def rollback(models_dir: Path) -> str:
    """Pop the current champion off the lineage stack and restore the one beneath it."""
    with _champion_lock(models_dir):
        path = _champion_path(models_dir)
        if not path.exists():
            raise RuntimeError("no champion history to roll back")
        data = _load_champion_data(path, models_dir)
        lineage: list[str] = list(data.get("lineage", []))
        if len(lineage) < 2:
            raise RuntimeError("no previous champion to roll back to")
        current = lineage[-1]
        previous = lineage[-2]
        current = validate_model_id(current)
        previous = validate_model_id(previous)
        load_record(Path(models_dir) / current)
        prev_record = load_record(Path(models_dir) / previous)
        data["model_id"] = previous
        data["lineage"] = lineage[:-1]
        data["generation"] = data.get("generation", 0) + 1
        data["model_artifact_sha256"] = prev_record.metadata.get("artifact_sha256") or artifact_sha256(
            Path(models_dir) / previous / MODEL_FILE
        )
        _write_champion_atomically(path, data, action=f"rollback:{current}->{previous}")
        return previous
