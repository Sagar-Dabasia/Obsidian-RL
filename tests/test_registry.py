"""Model registry schema contract validation tests."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from obsidian_rl.features.schema import MARKET_FEATURES, schema_fingerprint, schema_sha256
from obsidian_rl.training.registry import (
    METADATA_FILE,
    MODEL_FILE,
    GitSourceState,
    ModelCompatibilityError,
    load_record,
    register_model,
)


@pytest.fixture(autouse=True)
def _mock_clean_git_state() -> Iterator[None]:
    clean_state = GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[])
    with patch("obsidian_rl.training.registry.get_git_source_state", return_value=clean_state):
        yield


def _register_stub(models_dir: Path, model_id: str) -> Path:
    model_dir = models_dir / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / MODEL_FILE
    model_file.write_bytes(b"PK\x03\x04stub_zip_content")
    register_model(
        models_dir,
        model_id,
        algorithm="ppo-mlp",
        config={"env": "test"},
        seeds=[42],
        data_info={"train_end_ms": 100},
        metrics={"return": 0.1},
    )
    return model_dir


def _write_metadata(model_dir: Path, meta: dict[str, Any]) -> None:
    (model_dir / METADATA_FILE).write_text(
        json.dumps(meta, indent=2, allow_nan=False), encoding="utf-8"
    )


def test_registry_register_and_load_record_passes_for_valid_schema(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    assert record.model_id == "test-model-1"
    expected_ver = schema_fingerprint()["schema_version"]
    assert record.metadata["feature_schema"]["schema_version"] == expected_ver


def test_load_record_rejects_legacy_schema_version(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    meta["feature_schema"]["schema_version"] = "fs-v1"
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="legacy schema version"):
        load_record(model_dir)


def test_load_record_rejects_missing_schema_field(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    del meta["feature_schema"]["warmup_rows"]
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="missing or extra schema fields"):
        load_record(model_dir)


def test_load_record_rejects_extra_schema_field(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    meta["feature_schema"]["unexpected_key"] = "bad"
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="missing or extra schema fields"):
        load_record(model_dir)


def test_load_record_rejects_changed_constants(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    meta["feature_schema"]["warmup_rows"] = 999
    desc = {k: v for k, v in meta["feature_schema"].items() if k != "schema_sha256"}
    meta["feature_schema"]["schema_sha256"] = schema_sha256(desc)
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="changed constants or schema mismatch"):
        load_record(model_dir)


def test_load_record_rejects_reordered_features(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    meta["feature_schema"]["market_features"] = list(reversed(MARKET_FEATURES))
    desc = {k: v for k, v in meta["feature_schema"].items() if k != "schema_sha256"}
    meta["feature_schema"]["schema_sha256"] = schema_sha256(desc)
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="reordered features"):
        load_record(model_dir)


def test_load_record_rejects_changed_bounds(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    bounds = dict(meta["feature_schema"]["portfolio_bounds"])
    bounds["exposure"] = dict(bounds["exposure"])
    bounds["exposure"]["clip_high"] = 99.0
    meta["feature_schema"]["portfolio_bounds"] = bounds
    desc = {k: v for k, v in meta["feature_schema"].items() if k != "schema_sha256"}
    meta["feature_schema"]["schema_sha256"] = schema_sha256(desc)
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="changed bounds or normalization"):
        load_record(model_dir)


def test_load_record_rejects_malformed_schema_hash(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    meta["feature_schema"]["schema_sha256"] = "bad_hash"
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="malformed schema hash"):
        load_record(model_dir)


def test_load_record_rejects_descriptor_hash_disagreement(tmp_path: Path) -> None:
    model_dir = _register_stub(tmp_path, "test-model-1")
    record = load_record(model_dir)
    meta = dict(record.metadata)
    meta["feature_schema"] = dict(meta["feature_schema"])
    meta["feature_schema"]["warmup_rows"] = 999  # changed descriptor without updating schema_sha256
    _write_metadata(model_dir, meta)

    with pytest.raises(ModelCompatibilityError, match="descriptor/hash disagreement"):
        load_record(model_dir)
