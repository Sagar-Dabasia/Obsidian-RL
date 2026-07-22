"""Champion/challenger promotion tests: immutable gates, promotion, rollback."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import obsidian_rl.training.promotion as promotion_module
from obsidian_rl.features.pipeline import WARMUP_ROWS
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.training.ppo import PpoHyperparams, TrainConfig, train_ppo
from obsidian_rl.training.promotion import (
    EVALUATION_REPORT_FILE,
    EVALUATIONS_DIR,
    LATEST_POINTER_FILE,
    PromotionEvidenceError,
    PromotionThresholds,
    _json_dumps,
    _latest_pointer_path,
    current_champion,
    evaluate_candidate,
    promote,
    rollback,
)
from obsidian_rl.training.registry import (
    METADATA_FILE,
    MODEL_FILE,
    GitSourceState,
    artifact_sha256,
    load_record,
    register_model,
)
from tests.conftest import make_candles
from typing import Iterator


@pytest.fixture(scope="module", autouse=True)
def _mock_clean_git_state_module() -> Iterator[None]:
    from unittest.mock import patch
    from obsidian_rl.training.registry import GitSourceState, get_git_source_state as real_get_git_source_state

    clean_state = GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[])

    def fake_get_git_source_state(path: Path | None = None) -> GitSourceState:
        if path is not None:
            return real_get_git_source_state(path)
        return clean_state

    with (
        patch("obsidian_rl.training.registry.get_git_source_state", fake_get_git_source_state),
        patch("obsidian_rl.training.promotion.get_git_source_state", fake_get_git_source_state),
    ):
        yield


CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)
CFG = TrainConfig(
    total_timesteps=192,
    n_envs=1,
    seed=1,
    device="cpu",
    episode_length=32,
    checkpoint_freq=96,
    eval_freq=96,
    hyperparams=PpoHyperparams(n_steps=48, batch_size=24, net_arch=(8, 8)),
    costs=CM,
)

PERMISSIVE = PromotionThresholds(
    max_drawdown_limit=1.0,
    min_net_return_vs_flat=-1.0,
    must_not_trail_champion_by=1.0,
)


def _record_passing_evidence(models_dir: Path, candidate_id: str) -> None:
    val = make_candles(WARMUP_ROWS + 200, seed=9)
    with patch(
        "obsidian_rl.training.promotion.get_git_source_state",
        return_value=GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[]),
    ):
        report = evaluate_candidate(
            models_dir,
            candidate_id,
            val,
            cost_model=CM,
            thresholds=PERMISSIVE,
        )
    assert report["passes"] is True


@pytest.fixture(scope="module")
def models_with_two_candidates(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    models_dir = tmp_path_factory.mktemp("models")
    train = make_candles(350, seed=1)
    evalc = make_candles(250, seed=2, start_ms=int(train["open_time"].iloc[-1]) + 900_000)
    a = train_ppo(train, evalc, CFG, models_dir, model_id="cand-a")
    b = train_ppo(train, evalc, CFG, models_dir, model_id="cand-b")
    return models_dir, a.record.model_id, b.record.model_id


# ---------------------------------------------------------------------------
# Promotion and rollback (CHAMPION.json is the sole authority)
# ---------------------------------------------------------------------------


def test_promote_and_retire(models_with_two_candidates: tuple[Path, str, str]) -> None:
    models_dir, a, b = models_with_two_candidates
    assert current_champion(models_dir) is None
    _record_passing_evidence(models_dir, a)
    promote(models_dir, a)
    assert current_champion(models_dir) == a
    # Per-model metadata is NOT mutated by promote; CHAMPION.json is authoritative.
    _record_passing_evidence(models_dir, b)
    promote(models_dir, b)
    assert current_champion(models_dir) == b
    assert current_champion(models_dir) != a

    restored = rollback(models_dir)
    assert restored == a
    assert current_champion(models_dir) == a


def test_multi_step_rollback_walks_strictly_back(
    models_with_two_candidates: tuple[Path, str, str],
) -> None:
    """Regression (review): a second rollback must walk further back (C->B->A), never
    reinstate the just-abandoned champion."""
    models_dir, a, b = models_with_two_candidates
    (models_dir / "CHAMPION.json").unlink(missing_ok=True)  # fresh lineage for this test
    train = make_candles(350, seed=1)
    evalc = make_candles(250, seed=2, start_ms=int(train["open_time"].iloc[-1]) + 900_000)
    c = train_ppo(train, evalc, CFG, models_dir, model_id="cand-c").record.model_id

    _record_passing_evidence(models_dir, a)
    promote(models_dir, a)
    _record_passing_evidence(models_dir, b)
    promote(models_dir, b)
    _record_passing_evidence(models_dir, c)
    promote(models_dir, c)
    assert current_champion(models_dir) == c

    assert rollback(models_dir) == b
    assert current_champion(models_dir) == b
    assert rollback(models_dir) == a  # must reach A, NOT bounce back to C
    assert current_champion(models_dir) == a

    with pytest.raises(RuntimeError, match="no previous champion"):
        rollback(models_dir)  # nothing before A


# ---------------------------------------------------------------------------
# Candidate evaluation gates (integration — real PPO models)
# ---------------------------------------------------------------------------


def test_candidate_evaluation_gates(models_with_two_candidates: tuple[Path, str, str]) -> None:
    models_dir, a, _ = models_with_two_candidates
    val = make_candles(WARMUP_ROWS + 200, seed=9)
    with patch(
        "obsidian_rl.training.promotion.get_git_source_state",
        return_value=GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[]),
    ):
        report = evaluate_candidate(models_dir, a, val, cost_model=CM)
        assert "candidate" in report["metrics"]
        assert "always-flat" in report["metrics"]
        # an impossible threshold must fail the candidate
        strict = evaluate_candidate(
            models_dir,
            a,
            val,
            cost_model=CM,
            thresholds=PromotionThresholds(max_drawdown_limit=0.0),
        )
    assert strict["passes"] is False and strict["failures"]


def test_unknown_candidate_rejected(models_with_two_candidates: tuple[Path, str, str]) -> None:
    models_dir, _, _ = models_with_two_candidates
    val = make_candles(WARMUP_ROWS + 150, seed=3)
    with pytest.raises(Exception, match=r"refusing to load|No such|not found|missing"):
        evaluate_candidate(models_dir, "nonexistent-model", val, cost_model=CM)


# ---------------------------------------------------------------------------
# Evidence-gate fixture helpers
# ---------------------------------------------------------------------------


def _register_test_candidate(models_dir: Path, model_id: str) -> None:
    candidate_dir = models_dir / model_id
    candidate_dir.mkdir(parents=True)
    (candidate_dir / MODEL_FILE).write_bytes(f"known-test-artifact:{model_id}".encode())
    register_model(
        models_dir,
        model_id,
        algorithm="test-policy",
        config={},
        seeds=[1],
        data_info={},
        metrics={},
    )


@pytest.fixture
def evidence_models(tmp_path: Path) -> tuple[Path, str, pd.DataFrame]:
    models_dir = tmp_path / "models"
    candidate_id = "candidate-a"
    _register_test_candidate(models_dir, candidate_id)
    validation = pd.DataFrame(
        {
            "open_time": [1_700_000_000_000, 1_700_000_900_000],
            "close": [100.0, 101.0],
        }
    )
    return models_dir, candidate_id, validation


def _stub_successful_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    class Metrics:
        net_return = 0.1
        max_drawdown = 0.05

        def to_dict(self) -> dict[str, float]:
            return {"net_return": self.net_return, "max_drawdown": self.max_drawdown}

    from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy

    monkeypatch.setattr(PpoPolicyStrategy, "from_dir", lambda _path: object())
    monkeypatch.setattr(promotion_module, "default_baselines", lambda: [])
    monkeypatch.setattr(
        promotion_module,
        "evaluate_strategies_on_slice",
        lambda *_args, **_kwargs: [SimpleNamespace(strategy_id="candidate", metrics=Metrics())],
    )
    from obsidian_rl.training.registry import GitSourceState

    monkeypatch.setattr(
        promotion_module,
        "get_git_source_state",
        lambda: GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[]),
    )


def _write_passing_evidence(
    models_dir: Path,
    candidate_id: str,
    validation: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    _stub_successful_evaluation(monkeypatch)
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert report["passes"] is True
    return report


def _get_latest_report_path(models_dir: Path, candidate_id: str) -> Path:
    """Resolve the immutable report path via latest.json."""
    ptr = _latest_pointer_path(models_dir, candidate_id)
    data = json.loads(ptr.read_text(encoding="utf-8"))
    evals = models_dir / candidate_id / EVALUATIONS_DIR
    return evals / data["report_filename"]


# ---------------------------------------------------------------------------
# Promotion gate tests (unit — stubbed evaluation)
# ---------------------------------------------------------------------------


def test_unevaluated_candidate_cannot_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame],
) -> None:
    models_dir, candidate_id, _ = evidence_models
    with pytest.raises(PromotionEvidenceError, match="no evaluation report"):
        promote(models_dir, candidate_id)


def test_failed_candidate_cannot_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    report = evaluate_candidate(
        models_dir,
        candidate_id,
        validation,
        thresholds=PromotionThresholds(max_drawdown_limit=0.0),
    )
    assert report["passes"] is False

    with pytest.raises(PromotionEvidenceError, match="does not record a passing candidate"):
        promote(models_dir, candidate_id)


def test_passing_candidate_can_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)

    promote(models_dir, candidate_id)
    assert current_champion(models_dir) == candidate_id
    # CHAMPION.json is the sole authority — per-model metadata is NOT mutated.
    assert load_record(models_dir / candidate_id).metadata["promotion"] == "candidate"


def test_artifact_changed_after_evaluation_cannot_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    artifact = models_dir / candidate_id / MODEL_FILE
    artifact.write_bytes(b"changed-after-evaluation")
    metadata_path = models_dir / candidate_id / METADATA_FILE
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifact_sha256"] = artifact_sha256(artifact)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match="artifact checksum differs"):
        promote(models_dir, candidate_id)


def test_mismatched_report_model_id_cannot_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    # Tamper: corrupt the report file so hash no longer matches
    report_path = _get_latest_report_path(models_dir, candidate_id)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["report_sha256"]
    report["model_id"] = "different-candidate"
    report["report_sha256"] = hashlib.sha256(
        _json_dumps({k: v for k, v in report.items() if k != "report_sha256"}).encode()
    ).hexdigest()
    report_path.write_text(json.dumps(report), encoding="utf-8")
    # Also update latest.json so filename/hash are consistent with new content
    new_hash = report["report_sha256"]
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    ptr_data["report_sha256"] = new_hash
    ptr.write_text(json.dumps(ptr_data), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match="model_id does not match"):
        promote(models_dir, candidate_id)


def test_mismatched_report_feature_schema_cannot_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["report_sha256"]
    report["feature_schema"]["version"] = "fs-incompatible"
    new_hash = hashlib.sha256(
        _json_dumps({k: v for k, v in report.items() if k != "report_sha256"}).encode()
    ).hexdigest()
    report["report_sha256"] = new_hash
    report_path.write_text(json.dumps(report), encoding="utf-8")
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    ptr_data["report_sha256"] = new_hash
    ptr.write_text(json.dumps(ptr_data), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match="feature schema fingerprint"):
        promote(models_dir, candidate_id)


@pytest.mark.parametrize("ptr_contents", ["{not-json", "{}"])
def test_malformed_or_missing_latest_json_cannot_be_promoted(
    evidence_models: tuple[Path, str, pd.DataFrame],
    ptr_contents: str,
) -> None:
    models_dir, candidate_id, _ = evidence_models
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(ptr_contents, encoding="utf-8")

    with pytest.raises(PromotionEvidenceError):
        promote(models_dir, candidate_id)


# ---------------------------------------------------------------------------
# Append-only content-addressed evidence
# ---------------------------------------------------------------------------


def test_first_evaluation_creates_immutable_report_and_latest(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    report = evaluate_candidate(models_dir, candidate_id, validation)

    evals_dir = models_dir / candidate_id / EVALUATIONS_DIR
    ptr = evals_dir / LATEST_POINTER_FILE
    assert ptr.is_file(), "latest.json must exist"
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    filename = ptr_data["report_filename"]
    assert filename.startswith("evaluation-v1-")
    assert filename.endswith(".json")

    report_file = evals_dir / filename
    assert report_file.is_file(), "immutable report file must exist"

    on_disk = json.loads(report_file.read_text(encoding="utf-8"))
    stored_hash = on_disk.pop("report_sha256")
    assert on_disk == report  # payload matches return value
    assert len(stored_hash) == 64
    assert int(stored_hash, 16) >= 0  # valid hex
    # Verify hash is deterministic
    expected_hash = hashlib.sha256(_json_dumps(on_disk).encode("utf-8")).hexdigest()
    assert stored_hash == expected_hash


def test_second_evaluation_creates_different_file_first_preserved(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    evaluate_candidate(models_dir, candidate_id, validation)
    evals_dir = models_dir / candidate_id / EVALUATIONS_DIR
    files_after_first = set(p.name for p in evals_dir.iterdir() if p.name != LATEST_POINTER_FILE)
    first_contents = {
        p.name: (evals_dir / p.name).read_bytes()
        for p in evals_dir.iterdir()
        if p.name != LATEST_POINTER_FILE
    }

    # Second evaluation (different timestamp → different filename)
    import time

    time.sleep(0.002)  # ensure timestamp differs
    _stub_successful_evaluation(monkeypatch)
    evaluate_candidate(models_dir, candidate_id, validation)
    files_after_second = set(p.name for p in evals_dir.iterdir() if p.name != LATEST_POINTER_FILE)

    new_files = files_after_second - files_after_first
    assert len(new_files) >= 1, "second evaluation must create at least one new file"

    # First report files are byte-for-byte unchanged
    for name, original_bytes in first_contents.items():
        assert (evals_dir / name).read_bytes() == original_bytes, (
            f"file {name!r} must not be modified after second evaluation"
        )


def test_report_hash_is_verified_on_load(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    evaluate_candidate(models_dir, candidate_id, validation)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    # Silently corrupt the file content — change schema_version to something different
    data = json.loads(report_path.read_text(encoding="utf-8"))
    data["schema_version"] = 999  # definitely changes the hash
    report_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match=r"hash mismatch|tampered"):
        promote(models_dir, candidate_id)


def test_tampered_latest_json_hash_is_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    evaluate_candidate(models_dir, candidate_id, validation)
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    ptr_data["report_sha256"] = "a" * 64  # wrong hash
    ptr.write_text(json.dumps(ptr_data), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match="does not match"):
        promote(models_dir, candidate_id)


def test_path_traversal_in_latest_json_is_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame],
) -> None:
    models_dir, candidate_id, _ = evidence_models
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(
        json.dumps(
            {
                "report_filename": "../../../etc/passwd",
                "report_sha256": "a" * 64,
                "model_id": candidate_id,
                "model_artifact_sha256": "b" * 64,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromotionEvidenceError, match="illegal path"):
        promote(models_dir, candidate_id)


def test_missing_immutable_report_is_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    evaluate_candidate(models_dir, candidate_id, validation)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    report_path.unlink()  # simulate missing immutable file

    with pytest.raises(PromotionEvidenceError, match="does not exist"):
        promote(models_dir, candidate_id)


def test_legacy_evaluation_file_cannot_authorize_promotion(
    evidence_models: tuple[Path, str, pd.DataFrame],
) -> None:
    """A plain evaluation-v1.json without the evaluations/ structure must be rejected."""
    models_dir, candidate_id, _ = evidence_models
    # Write only the legacy file — no evaluations/ dir
    legacy = models_dir / candidate_id / EVALUATION_REPORT_FILE
    legacy.write_text(json.dumps({"passes": True}), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match=r"legacy|reevaluation"):
        promote(models_dir, candidate_id)


def test_failed_evaluation_produces_immutable_evidence(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    report = evaluate_candidate(
        models_dir,
        candidate_id,
        validation,
        thresholds=PromotionThresholds(max_drawdown_limit=0.0),
    )
    assert report["passes"] is False
    assert report["failures"]

    # Report must still be persisted as an immutable file
    ptr = _latest_pointer_path(models_dir, candidate_id)
    assert ptr.is_file()
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    evals_dir = models_dir / candidate_id / EVALUATIONS_DIR
    report_file = evals_dir / ptr_data["report_filename"]
    assert report_file.is_file()
    on_disk = json.loads(report_file.read_text(encoding="utf-8"))
    assert on_disk["passes"] is False


def test_no_tmp_files_remain_after_successful_write(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    evaluate_candidate(models_dir, candidate_id, validation)
    evals_dir = models_dir / candidate_id / EVALUATIONS_DIR
    tmp_files = list(evals_dir.glob("*.tmp"))
    assert tmp_files == [], f"temp files remain: {tmp_files}"


def test_evaluation_report_keys_complete(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report must include all required fields (Req 16 / append-only schema)."""
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert set(report) == {
        "schema_version",
        "model_id",
        "model_artifact_filename",
        "model_artifact_sha256",
        "feature_schema",
        "validation",
        "cost_model",
        "source_git_commit",
        "source_tree_clean",
        "evaluation_source_git_commit",
        "evaluation_source_tree_clean",
        "evaluated_at_utc",
        "thresholds",
        "champion_id",
        "passes",
        "failures",
        "metrics",
    }
    report_path = _get_latest_report_path(models_dir, candidate_id)
    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    # On-disk has report_sha256 extra; minus that it must equal report
    on_disk_payload = {k: v for k, v in on_disk.items() if k != "report_sha256"}
    assert on_disk_payload == report


def test_evaluate_report_is_written_atomically(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Immutable report uses exclusive creation; latest.json must use os.replace."""
    models_dir, candidate_id, validation = evidence_models
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = promotion_module.os.replace

    def record_replace(source: str | Path, destination: str | Path) -> None:
        replace_calls.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(promotion_module.os, "replace", record_replace)
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)

    # Immutable report created exclusively; latest.json atomically replaced
    assert len(replace_calls) == 1
    destinations = [d for _, d in replace_calls]
    latest = _latest_pointer_path(models_dir, candidate_id)
    assert latest in destinations
    for src, _ in replace_calls:
        assert src.suffix == ".tmp", f"expected .tmp source, got {src.name!r}"
    assert _get_latest_report_path(models_dir, candidate_id).exists()
    evals_dir = models_dir / candidate_id / EVALUATIONS_DIR
    assert not list(evals_dir.glob("*.tmp"))


# ---------------------------------------------------------------------------
# Finite-value validation tests
# ---------------------------------------------------------------------------


def test_nan_net_return_fails_validation(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models

    class NanMetrics:
        net_return = float("nan")
        max_drawdown = 0.05

        def to_dict(self) -> dict[str, object]:
            return {"net_return": self.net_return, "max_drawdown": self.max_drawdown}

    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "evaluate_strategies_on_slice",
        lambda *_a, **_kw: [SimpleNamespace(strategy_id="candidate", metrics=NanMetrics())],
    )
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert report["passes"] is False
    assert any("non-finite" in f for f in report["failures"])
    assert report["metrics"]["candidate"]["net_return"] is None  # serialised as JSON null


def test_positive_infinity_net_return_fails_validation(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models

    class InfMetrics:
        net_return = float("inf")
        max_drawdown = 0.05

        def to_dict(self) -> dict[str, object]:
            return {"net_return": self.net_return, "max_drawdown": self.max_drawdown}

    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "evaluate_strategies_on_slice",
        lambda *_a, **_kw: [SimpleNamespace(strategy_id="candidate", metrics=InfMetrics())],
    )
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert report["passes"] is False


def test_negative_infinity_net_return_fails_validation(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models

    class NegInfMetrics:
        net_return = float("-inf")
        max_drawdown = 0.05

        def to_dict(self) -> dict[str, object]:
            return {"net_return": self.net_return, "max_drawdown": self.max_drawdown}

    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "evaluate_strategies_on_slice",
        lambda *_a, **_kw: [SimpleNamespace(strategy_id="candidate", metrics=NegInfMetrics())],
    )
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert report["passes"] is False


def test_nan_max_drawdown_fails_validation(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models

    class NanDDMetrics:
        net_return = 0.05
        max_drawdown = float("nan")

        def to_dict(self) -> dict[str, object]:
            return {"net_return": self.net_return, "max_drawdown": self.max_drawdown}

    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "evaluate_strategies_on_slice",
        lambda *_a, **_kw: [SimpleNamespace(strategy_id="candidate", metrics=NanDDMetrics())],
    )
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert report["passes"] is False
    assert report["metrics"]["candidate"]["max_drawdown"] is None


def test_bool_metric_rejected_by_require_finite() -> None:
    from obsidian_rl.training.promotion import _require_finite

    with pytest.raises(PromotionEvidenceError, match="bool"):
        _require_finite(True, "some.field")


def test_nan_in_report_rejected_by_validate(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Injecting NaN into a report's metrics.candidate must be rejected at promotion."""
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["report_sha256"]
    report["metrics"]["candidate"]["net_return"] = None  # None → null → not finite
    # Recompute hash with tampered data
    new_hash = hashlib.sha256(
        _json_dumps({k: v for k, v in report.items() if k != "report_sha256"}).encode()
    ).hexdigest()
    report["report_sha256"] = new_hash
    report_path.write_text(json.dumps(report), encoding="utf-8")
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    ptr_data["report_sha256"] = new_hash
    ptr.write_text(json.dumps(ptr_data), encoding="utf-8")

    # None is not finite — validation should reject it
    with pytest.raises(PromotionEvidenceError, match=r"finite|missing"):
        promote(models_dir, candidate_id)


def test_nan_in_cost_model_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """NaN in any cost_model field must cause promotion to reject the report."""
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["report_sha256"]
    first_cost_key = next(iter(report["cost_model"]))
    report["cost_model"][first_cost_key] = None  # null → not finite
    new_hash = hashlib.sha256(
        _json_dumps({k: v for k, v in report.items() if k != "report_sha256"}).encode()
    ).hexdigest()
    report["report_sha256"] = new_hash
    report_path.write_text(json.dumps(report), encoding="utf-8")
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    ptr_data["report_sha256"] = new_hash
    ptr.write_text(json.dumps(ptr_data), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match=r"finite|numeric"):
        promote(models_dir, candidate_id)


def test_nan_in_thresholds_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["report_sha256"]
    first_thresh_key = next(iter(report["thresholds"]))
    report["thresholds"][first_thresh_key] = None
    new_hash = hashlib.sha256(
        _json_dumps({k: v for k, v in report.items() if k != "report_sha256"}).encode()
    ).hexdigest()
    report["report_sha256"] = new_hash
    report_path.write_text(json.dumps(report), encoding="utf-8")
    ptr = _latest_pointer_path(models_dir, candidate_id)
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    ptr_data["report_sha256"] = new_hash
    ptr.write_text(json.dumps(ptr_data), encoding="utf-8")

    with pytest.raises(PromotionEvidenceError, match="finite"):
        promote(models_dir, candidate_id)


def test_json_with_nan_constant_rejected() -> None:
    """JSON text containing literal NaN (Python extension) must be rejected."""
    from obsidian_rl.training.promotion import _json_loads_strict

    nan_json = '{"value": NaN}'
    with pytest.raises(PromotionEvidenceError, match=r"malformed|non-finite"):
        _json_loads_strict(nan_json, "test")


def test_json_with_infinity_constant_rejected() -> None:
    """JSON text containing literal Infinity must be rejected."""
    from obsidian_rl.training.promotion import _json_loads_strict

    inf_json = '{"value": Infinity}'
    with pytest.raises(PromotionEvidenceError, match=r"malformed|non-finite"):
        _json_loads_strict(inf_json, "test")


def test_non_finite_evaluation_uses_json_null_not_nan(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-finite strategy metrics must be serialised as null, not NaN."""
    models_dir, candidate_id, validation = evidence_models

    class NanMetrics:
        net_return = float("nan")
        max_drawdown = float("inf")

        def to_dict(self) -> dict[str, object]:
            return {"net_return": self.net_return, "max_drawdown": self.max_drawdown}

    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "evaluate_strategies_on_slice",
        lambda *_a, **_kw: [SimpleNamespace(strategy_id="candidate", metrics=NanMetrics())],
    )
    evaluate_candidate(models_dir, candidate_id, validation)
    # The immutable report must be valid JSON (no NaN/Infinity)
    report_path = _get_latest_report_path(models_dir, candidate_id)
    raw_text = report_path.read_text(encoding="utf-8")
    # Must not contain Python JSON extension keywords
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text
    # Must be parseable as standard JSON
    parsed = json.loads(raw_text)
    assert parsed["metrics"]["candidate"]["net_return"] is None
    assert parsed["metrics"]["candidate"]["max_drawdown"] is None


# ---------------------------------------------------------------------------
# Crash-safe champion state tests
# ---------------------------------------------------------------------------


def test_promote_atomically_updates_champion_json(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = promotion_module.os.replace

    def record_replace(src: str | Path, dst: str | Path) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    monkeypatch.setattr(promotion_module.os, "replace", record_replace)
    promote(models_dir, candidate_id)

    champion_path = models_dir / "CHAMPION.json"
    # CHAMPION.json must have been written via os.replace exactly once
    champion_writes = [d for _, d in replace_calls if d == champion_path]
    assert len(champion_writes) == 1


def test_rollback_atomically_updates_champion_json(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir = evidence_models[0]
    candidate_id = evidence_models[1]
    validation = evidence_models[2]

    # Need two candidates for rollback; reuse second registered candidate
    other_id = "candidate-b-rollback"
    _register_test_candidate(models_dir, other_id)

    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    promote(models_dir, candidate_id)
    _write_passing_evidence(models_dir, other_id, validation, monkeypatch)
    promote(models_dir, other_id)
    assert current_champion(models_dir) == other_id

    replace_calls: list[tuple[Path, Path]] = []
    original_replace = promotion_module.os.replace

    def record_replace(src: str | Path, dst: str | Path) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(promotion_module.os, "replace", record_replace)
    rollback(models_dir)
    champion_path = models_dir / "CHAMPION.json"
    champion_writes = [d for _, d in replace_calls if d == champion_path]
    assert len(champion_writes) == 1
    assert current_champion(models_dir) == candidate_id


def test_simulated_replace_failure_preserves_previous_champion(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    promote(models_dir, candidate_id)
    assert current_champion(models_dir) == candidate_id

    # Register a second candidate to promote
    other_id = "candidate-crash-test"
    _register_test_candidate(models_dir, other_id)
    _write_passing_evidence(models_dir, other_id, validation, monkeypatch)

    # Simulate os.replace failure during the champion write
    def failing_replace(src: str | Path, dst: str | Path) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(promotion_module.os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated"):
        promote(models_dir, other_id)

    # Previous champion must be unchanged
    assert current_champion(models_dir) == candidate_id


def test_no_per_model_metadata_changed_during_promote(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    metadata_before = json.loads(
        (models_dir / candidate_id / METADATA_FILE).read_text(encoding="utf-8")
    )
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    promote(models_dir, candidate_id)
    metadata_after = json.loads(
        (models_dir / candidate_id / METADATA_FILE).read_text(encoding="utf-8")
    )
    assert metadata_before == metadata_after, "promote() must not modify per-model metadata"


def test_no_per_model_metadata_changed_during_rollback(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    other_id = "candidate-rb-meta"
    _register_test_candidate(models_dir, other_id)

    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    promote(models_dir, candidate_id)
    _write_passing_evidence(models_dir, other_id, validation, monkeypatch)
    promote(models_dir, other_id)

    meta_a = json.loads((models_dir / candidate_id / METADATA_FILE).read_text(encoding="utf-8"))
    meta_b = json.loads((models_dir / other_id / METADATA_FILE).read_text(encoding="utf-8"))

    rollback(models_dir)

    assert (
        json.loads((models_dir / candidate_id / METADATA_FILE).read_text(encoding="utf-8"))
        == meta_a
    )
    assert json.loads((models_dir / other_id / METADATA_FILE).read_text(encoding="utf-8")) == meta_b


def test_malformed_champion_json_raises_explicitly(tmp_path: Path) -> None:
    champion = tmp_path / "CHAMPION.json"
    champion.write_text("{not valid json}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="malformed"):
        rollback(tmp_path)


# ---------------------------------------------------------------------------
# Defect 1 & 2 tests — CHAMPION.json strict schema, validation, normalization
# ---------------------------------------------------------------------------


def test_champion_json_invalid_schema_version_rejected(tmp_path: Path) -> None:
    path = tmp_path / "CHAMPION.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "generation": 0,
                "model_id": None,
                "model_artifact_sha256": None,
                "lineage": [],
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unsupported schema_version"):
        promotion_module._load_champion_data(path)


def test_champion_json_invalid_generation_rejected(tmp_path: Path) -> None:
    path = tmp_path / "CHAMPION.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": promotion_module.CHAMPION_SCHEMA_VERSION,
                "generation": -1,
                "model_id": None,
                "model_artifact_sha256": None,
                "lineage": [],
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="generation must be a non-negative integer"):
        promotion_module._load_champion_data(path)


def test_champion_json_duplicate_lineage_rejected(tmp_path: Path) -> None:
    path = tmp_path / "CHAMPION.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": promotion_module.CHAMPION_SCHEMA_VERSION,
                "generation": 1,
                "model_id": "cand-a",
                "model_artifact_sha256": "a" * 64,
                "lineage": ["cand-a", "cand-a"],
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="contains duplicate model IDs"):
        promotion_module._load_champion_data(path)


def test_champion_json_null_id_nonempty_lineage_rejected(tmp_path: Path) -> None:
    path = tmp_path / "CHAMPION.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": promotion_module.CHAMPION_SCHEMA_VERSION,
                "generation": 1,
                "model_id": None,
                "model_artifact_sha256": None,
                "lineage": ["cand-a"],
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="model_id is null but lineage is not empty"):
        promotion_module._load_champion_data(path)


def test_champion_json_lineage_last_mismatch_rejected(tmp_path: Path) -> None:
    path = tmp_path / "CHAMPION.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": promotion_module.CHAMPION_SCHEMA_VERSION,
                "generation": 1,
                "model_id": "cand-b",
                "model_artifact_sha256": "b" * 64,
                "lineage": ["cand-a"],
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="does not match model_id"):
        promotion_module._load_champion_data(path)


def test_champion_json_legacy_normalization(tmp_path: Path) -> None:
    path = tmp_path / "CHAMPION.json"
    legacy_data = {
        "model_id": "cand-a",
        "lineage": ["cand-a"],
        "history": [{"action": "promote:cand-a"}],
    }
    path.write_text(json.dumps(legacy_data), encoding="utf-8")
    loaded = promotion_module._load_champion_data(path)
    assert loaded["schema_version"] == promotion_module.CHAMPION_SCHEMA_VERSION
    assert loaded["generation"] == 1
    assert loaded["model_id"] == "cand-a"
    assert loaded["lineage"] == ["cand-a"]
    assert "updated_at_utc" in loaded


def test_promote_rejects_candidate_already_in_lineage(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    promote(models_dir, candidate_id)
    champ_path = models_dir / "CHAMPION.json"
    data = promotion_module._load_champion_data(champ_path, models_dir)
    other_id = "candidate-other"
    _register_test_candidate(models_dir, other_id)
    _write_passing_evidence(models_dir, other_id, validation, monkeypatch)
    data["model_id"] = other_id
    data["lineage"].append(other_id)
    data["model_artifact_sha256"] = promotion_module.artifact_sha256(
        models_dir / other_id / MODEL_FILE
    )
    promotion_module._write_champion_atomically(champ_path, data, "test")

    with pytest.raises(PromotionEvidenceError, match="already in champion lineage"):
        promote(models_dir, candidate_id)


def test_promote_and_rollback_update_generation_and_sha(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    other_id = "candidate-gen-test"
    _register_test_candidate(models_dir, other_id)
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    _write_passing_evidence(models_dir, other_id, validation, monkeypatch)

    promote(models_dir, candidate_id)
    data1 = promotion_module._load_champion_data(models_dir / "CHAMPION.json", models_dir)
    assert data1["generation"] >= 1
    assert data1["model_artifact_sha256"] == promotion_module.artifact_sha256(
        models_dir / candidate_id / MODEL_FILE
    )

    promote(models_dir, other_id)
    data2 = promotion_module._load_champion_data(models_dir / "CHAMPION.json", models_dir)
    assert data2["generation"] == data1["generation"] + 1
    assert data2["model_artifact_sha256"] == promotion_module.artifact_sha256(
        models_dir / other_id / MODEL_FILE
    )

    rollback(models_dir)
    data3 = promotion_module._load_champion_data(models_dir / "CHAMPION.json", models_dir)
    assert data3["generation"] == data2["generation"] + 1
    assert data3["model_id"] == candidate_id
    assert data3["model_artifact_sha256"] == promotion_module.artifact_sha256(
        models_dir / candidate_id / MODEL_FILE
    )


# ---------------------------------------------------------------------------
# Defect 4 tests — Exclusive immutable creation and collision
# ---------------------------------------------------------------------------


def test_immutable_report_exclusive_creation_collision(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    fixed_name = "evaluation-v1-9999-collision-hash.json"
    monkeypatch.setattr(promotion_module, "_report_filename", lambda ts, rh: fixed_name)

    report1 = evaluate_candidate(models_dir, candidate_id, validation)
    evals_dir = models_dir / candidate_id / "evaluations"
    report_path = evals_dir / fixed_name
    assert report_path.is_file()
    first_bytes = report_path.read_bytes()

    with pytest.raises((FileExistsError, PromotionEvidenceError)):
        evaluate_candidate(models_dir, candidate_id, validation)

    assert report_path.read_bytes() == first_bytes


# ---------------------------------------------------------------------------
# Defect 5 tests — Git source state verification
# ---------------------------------------------------------------------------


def test_git_dirty_source_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "get_git_source_state",
        lambda: GitSourceState(commit="a" * 40, is_clean=False, dirty_paths=["src/foo.py"]),
    )
    with pytest.raises(PromotionEvidenceError, match="working tree is dirty"):
        evaluate_candidate(models_dir, candidate_id, validation)


def test_git_missing_commit_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "get_git_source_state",
        lambda: GitSourceState(commit=None, is_clean=True, dirty_paths=[]),
    )
    with pytest.raises(PromotionEvidenceError, match="unable to resolve source Git commit"):
        evaluate_candidate(models_dir, candidate_id, validation)


def test_git_clean_source_accepted(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _stub_successful_evaluation(monkeypatch)
    report = evaluate_candidate(models_dir, candidate_id, validation)
    assert report["source_git_commit"] == "a" * 40
    assert report["source_tree_clean"] is True


def test_validate_report_rejects_source_tree_clean_false() -> None:
    report = {
        "schema_version": promotion_module.EVALUATION_REPORT_SCHEMA_VERSION,
        "model_id": "cand-a",
        "model_artifact_filename": MODEL_FILE,
        "model_artifact_sha256": "0" * 64,
        "feature_schema": promotion_module.schema_fingerprint(),
        "validation": {"data_sha256": "1" * 64, "start_utc_ms": 1, "end_utc_ms": 2},
        "cost_model": pd.Series(asdict(CostModel())).to_dict(),
        "source_git_commit": "a" * 40,
        "source_tree_clean": False,
        "evaluated_at_utc": "2026-01-01T00:00:00Z",
        "thresholds": pd.Series(asdict(PromotionThresholds())).to_dict(),
        "passes": True,
        "metrics": {"candidate": {"net_return": 0.1, "max_drawdown": 0.05}},
    }
    with pytest.raises(PromotionEvidenceError, match="source_tree_clean must be true"):
        promotion_module._validate_evaluation_report(
            report,
            candidate_id="cand-a",
            record_feature_schema=promotion_module.schema_fingerprint(),
            artifact_checksum="0" * 64,
        )


# ---------------------------------------------------------------------------
# Defect 6 tests — Model and candidate ID validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["../foo", "foo/bar", "a\\b", ".hidden", "foo..bar", "-flag", "CON", "NUL", "COM1.json"],
)
def test_validate_model_id_bad_names_rejected(bad_id: str) -> None:
    with pytest.raises((ValueError, PromotionEvidenceError)):
        promotion_module.validate_model_id(bad_id)


def test_validate_model_id_good_names_accepted() -> None:
    assert promotion_module.validate_model_id("candidate-1_test") == "candidate-1_test"
    assert promotion_module.validate_model_id("ppo-2026-v1") == "ppo-2026-v1"


# ---------------------------------------------------------------------------
# Defect 7 tests — Evaluation locking
# ---------------------------------------------------------------------------


def test_evaluation_lock_prevents_concurrent_evaluations(
    evidence_models: tuple[Path, str, pd.DataFrame],
) -> None:
    models_dir, candidate_id, _ = evidence_models
    lock = promotion_module._evaluation_lock(models_dir, candidate_id)
    with lock:
        lock2 = promotion_module._evaluation_lock(models_dir, candidate_id)
        with pytest.raises(PromotionEvidenceError, match="already running"), lock2:
            pass


def test_promote_commit_mismatch_rejected(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    monkeypatch.setattr(
        promotion_module,
        "get_git_source_state",
        lambda: GitSourceState(commit="b" * 40, is_clean=True, dirty_paths=[]),
    )
    with pytest.raises(PromotionEvidenceError, match="current source commit differs from evaluation source commit"):
        promote(models_dir, candidate_id)


def test_promotion_thresholds_validation() -> None:
    for name in ("max_drawdown_limit", "min_net_return_vs_flat", "must_not_trail_champion_by"):
        with pytest.raises(ValueError):
            PromotionThresholds(**{name: True})
        with pytest.raises(ValueError):
            PromotionThresholds(**{name: False})
        with pytest.raises(ValueError):
            PromotionThresholds(**{name: float("nan")})
        with pytest.raises(ValueError):
            PromotionThresholds(**{name: float("inf")})
    with pytest.raises(ValueError):
        PromotionThresholds(max_drawdown_limit=1.5)
    with pytest.raises(ValueError):
        PromotionThresholds(must_not_trail_champion_by=-0.1)


def test_champion_lock_concurrent_and_error_handling(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    lock = promotion_module._champion_lock(models_dir, timeout_sec=0.1)
    with lock:
        lock2 = promotion_module._champion_lock(models_dir, timeout_sec=0.1)
        with pytest.raises(PromotionEvidenceError, match="already running"), lock2:
            pass

    with patch("builtins.open", side_effect=PermissionError("no access")):
        with pytest.raises(PermissionError, match="no access"):
            with promotion_module._champion_lock(models_dir):
                pass


def test_symlink_containment_checks(
    evidence_models: tuple[Path, str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir, candidate_id, validation = evidence_models
    _write_passing_evidence(models_dir, candidate_id, validation, monkeypatch)
    ptr_path = _latest_pointer_path(models_dir, candidate_id)
    _, report_path = promotion_module._load_and_verify_latest_pointer(models_dir, candidate_id)

    sym_ptr = models_dir / candidate_id / "sym_latest.json"
    try:
        sym_ptr.symlink_to(ptr_path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this filesystem/user")

    with patch("obsidian_rl.training.promotion._latest_pointer_path", return_value=sym_ptr):
        with pytest.raises(PromotionEvidenceError, match="must not be a symlink"):
            promotion_module._load_and_verify_latest_pointer(models_dir, candidate_id)

    sym_report = report_path.parent / "sym_report.json"
    try:
        sym_report.symlink_to(report_path)
    except (OSError, NotImplementedError):
        pass
    else:
        ptr_data = json.loads(ptr_path.read_text(encoding="utf-8"))
        ptr_data["report_filename"] = sym_report.name
        ptr_path.write_text(json.dumps(ptr_data), encoding="utf-8")
        with pytest.raises(PromotionEvidenceError, match="must not be a symlink"):
            promotion_module._load_and_verify_latest_pointer(models_dir, candidate_id)
