"""Model registry: metadata, checksums, compatibility gates, promotion status.

Models are only ever loaded from registry directories whose metadata validates against
the current feature schema and whose artifact checksum matches. Unidentified legacy
pickle artifacts are never loaded.
"""

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from obsidian_rl.features.observation import schema_fingerprint

METADATA_FILE = "metadata.json"
MODEL_FILE = "model.zip"

PROMOTION_STATES = ("candidate", "champion", "retired")

_SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


class ModelCompatibilityError(RuntimeError):
    """Model artifact rejected: schema mismatch, checksum mismatch, or missing metadata."""


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    model_dir: Path
    metadata: dict[str, Any]


def validate_model_id(model_id: object) -> str:
    """Validate and return a safe canonical model/candidate ID string."""
    if not isinstance(model_id, str):
        raise ValueError(f"model_id must be a string, got {type(model_id).__name__}")
    if not model_id or len(model_id) > 128:
        raise ValueError("model_id must be non-empty and at most 128 characters")
    if model_id != model_id.strip():
        raise ValueError("model_id must not have leading or trailing whitespace")
    if "/" in model_id or "\\" in model_id:
        raise ValueError("model_id must not contain path separators")
    if ".." in model_id:
        raise ValueError("model_id must not contain '..'")
    if model_id.startswith((".", "-", "_")) or model_id.endswith((".", "-", "_")):
        raise ValueError("model_id must not start or end with '.', '-', or '_'")
    if not _SAFE_ID_REGEX.match(model_id):
        raise ValueError(f"model_id {model_id!r} contains unsafe characters")
    stem = model_id.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise ValueError(f"model_id {model_id!r} uses a Windows reserved device name")
    return model_id


def artifact_sha256(path: Path) -> str:
    """Return the SHA-256 of a model artifact without loading it."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def current_git_commit(repo_root: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


@dataclass(frozen=True)
class GitSourceState:
    commit: str | None
    is_clean: bool
    dirty_paths: list[str]


def get_git_source_state(repo_root: Path | None = None) -> GitSourceState:
    """Check Git HEAD commit and working tree status (`git status --porcelain`)."""
    commit = current_git_commit(repo_root)
    if not commit:
        return GitSourceState(commit=None, is_clean=False, dirty_paths=[])
    try:
        out = subprocess.run(
            ["git", "-c", "safe.directory=*", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
        lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
        dirty_paths = []
        for line in lines:
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                dirty_paths.append(parts[1])
            else:
                dirty_paths.append(line)
        return GitSourceState(
            commit=commit, is_clean=len(dirty_paths) == 0, dirty_paths=dirty_paths
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return GitSourceState(commit=commit, is_clean=False, dirty_paths=[])


def dependency_versions() -> dict[str, str]:
    import gymnasium
    import numpy
    import pandas
    import stable_baselines3
    import torch

    return {
        "python": ".".join(map(str, __import__("sys").version_info[:3])),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "gymnasium": gymnasium.__version__,
        "stable_baselines3": stable_baselines3.__version__,
        "torch": torch.__version__,
    }


def register_model(
    models_dir: Path,
    model_id: str,
    *,
    algorithm: str,
    config: dict[str, Any],
    seeds: list[int],
    data_info: dict[str, Any],
    metrics: dict[str, Any],
) -> ModelRecord:
    """Finalize a trained model directory with metadata + checksum."""
    model_id = validate_model_id(model_id)
    model_dir = models_dir / model_id
    artifact = model_dir / MODEL_FILE
    if not artifact.exists():
        raise FileNotFoundError(artifact)
    metadata: dict[str, Any] = {
        "model_id": model_id,
        "algorithm": algorithm,
        "created_utc_ms": int(time.time() * 1000),
        "git_commit": current_git_commit(),
        "dependencies": dependency_versions(),
        "feature_schema": schema_fingerprint(),
        "data": data_info,
        "config": config,
        "seeds": seeds,
        "metrics": metrics,
        "artifact_sha256": artifact_sha256(artifact),
        "promotion": "candidate",
    }
    (model_dir / METADATA_FILE).write_text(json.dumps(metadata, indent=1), encoding="utf-8")
    return ModelRecord(model_id, model_dir, metadata)


def load_record(model_dir: Path) -> ModelRecord:
    """Validate metadata + checksum + feature schema before anyone touches the artifact."""
    meta_path = Path(model_dir) / METADATA_FILE
    artifact = Path(model_dir) / MODEL_FILE
    if not meta_path.exists():
        raise ModelCompatibilityError(f"no {METADATA_FILE} in {model_dir}; refusing to load")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if not artifact.exists():
        raise ModelCompatibilityError(f"artifact missing: {artifact}")
    actual = artifact_sha256(artifact)
    if actual != metadata.get("artifact_sha256"):
        raise ModelCompatibilityError(
            f"checksum mismatch for {artifact}: metadata says "
            f"{metadata.get('artifact_sha256')}, file is {actual}"
        )
    current = schema_fingerprint()
    stored = metadata.get("feature_schema", {})
    if (
        stored.get("version") != current["version"]
        or stored.get("observation_dim") != current["observation_dim"]
    ):
        raise ModelCompatibilityError(
            f"feature schema mismatch: model has {stored.get('version')}/"
            f"{stored.get('observation_dim')}, code has {current['version']}/"
            f"{current['observation_dim']}"
        )
    model_id = validate_model_id(str(metadata["model_id"]))
    return ModelRecord(model_id, Path(model_dir), metadata)


def set_promotion(model_dir: Path, status: str) -> None:
    if status not in PROMOTION_STATES:
        raise ValueError(f"invalid promotion state {status}")
    record = load_record(model_dir)  # re-validate before mutating
    record.metadata["promotion"] = status
    record.metadata["promotion_changed_utc_ms"] = int(time.time() * 1000)
    (Path(model_dir) / METADATA_FILE).write_text(
        json.dumps(record.metadata, indent=1), encoding="utf-8"
    )


def list_models(models_dir: Path) -> list[ModelRecord]:
    records = []
    if not Path(models_dir).exists():
        return []
    for child in sorted(Path(models_dir).iterdir()):
        if (child / METADATA_FILE).exists():
            try:
                records.append(load_record(child))
            except ModelCompatibilityError:
                continue  # listed elsewhere as invalid; never auto-loaded
    return records
