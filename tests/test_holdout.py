"""Tests for Phase 4 holdout evaluation: single-use, frozen champion, immutable evidence."""

import json
import os
import time
from argparse import Namespace
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from obsidian_rl.cli import cmd_holdout
from obsidian_rl.config import Settings
from obsidian_rl.evaluation import holdout as holdout_module
from obsidian_rl.evaluation.metrics import Metrics
from obsidian_rl.evaluation.walkforward import EvalRow, make_folds
from obsidian_rl.features.observation import schema_fingerprint
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy
from obsidian_rl.training.promotion import (
    _compute_report_hash,
    _json_dumps,
)
from obsidian_rl.training.registry import (
    METADATA_FILE,
    MODEL_FILE,
    GitSourceState,
    ModelCompatibilityError,
    artifact_sha256,
)
from tests.conftest import make_candles


@pytest.fixture
def clean_git() -> Iterator[GitSourceState]:
    state = GitSourceState(commit="a" * 40, is_clean=True, dirty_paths=[])
    with (
        patch("obsidian_rl.evaluation.holdout.get_git_source_state", return_value=state),
        patch("obsidian_rl.training.promotion.get_git_source_state", return_value=state),
    ):
        yield state


@pytest.fixture
def fake_settings(tmp_path: Path) -> Settings:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        models_dir=models_dir,
        data_dir=data_dir,
        symbol="BTCUSDT",
        interval="15m",
        holdout_start_utc="2025-07-01T00:00:00+00:00",
    )


@pytest.fixture
def isolated_holdout_paths(tmp_path: Path) -> Iterator[tuple[Path, Path, Path]]:
    h_dir = tmp_path / "holdout_artifacts"
    h_dir.mkdir(parents=True, exist_ok=True)
    state_path = h_dir / "HOLDOUT_STATE.json"
    lock_path = h_dir / ".holdout.lock"
    with (
        patch("obsidian_rl.evaluation.holdout.HOLDOUT_DIR", h_dir),
        patch("obsidian_rl.evaluation.holdout.HOLDOUT_STATE_PATH", state_path),
        patch("obsidian_rl.evaluation.holdout.HOLDOUT_LOCK_PATH", lock_path),
    ):
        yield h_dir, state_path, lock_path


def _setup_mock_champion(
    models_dir: Path, model_id: str = "m100", commit: str = "a" * 40
) -> dict[str, object]:
    model_dir = models_dir / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / MODEL_FILE
    model_file.write_bytes(b"mock_model_weights_bytes")
    art_sha = artifact_sha256(model_file)

    costs = CostModel(taker_fee=0.0005, half_spread=0.00005, slippage=0.0001)
    schema = schema_fingerprint()
    meta = {
        "model_id": model_id,
        "symbol": "BTCUSDT",
        "interval": "15m",
        "feature_schema": schema,
        "artifact_sha256": art_sha,
        "source_commit": commit,
        "source_tree_clean": True,
    }
    (model_dir / METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")

    report_data = {
        "candidate_id": model_id,
        "model_artifact_sha256": art_sha,
        "source_commit": commit,
        "source_tree_clean": True,
        "costs": asdict(costs),
        "passes": True,
    }
    rep_hash = _compute_report_hash(report_data)
    report_full = {**report_data, "report_sha256": rep_hash}

    evals_dir = models_dir / model_id / "evaluations"
    evals_dir.mkdir(parents=True, exist_ok=True)
    rep_file = evals_dir / f"report-{rep_hash[:8]}.json"
    rep_file.write_text(_json_dumps(report_full) + "\n", encoding="utf-8")

    ptr_data = {
        "model_id": model_id,
        "report_filename": rep_file.name,
        "report_sha256": rep_hash,
        "model_artifact_sha256": art_sha,
    }
    (evals_dir / "latest.json").write_text(_json_dumps(ptr_data) + "\n", encoding="utf-8")

    champion_data = {
        "schema_version": 1,
        "model_id": model_id,
        "generation": 1,
        "lineage": [model_id],
        "model_artifact_sha256": art_sha,
        "history": [],
    }
    (models_dir / "CHAMPION.json").write_text(_json_dumps(champion_data) + "\n", encoding="utf-8")

    return {
        "model_id": model_id,
        "model_dir": model_dir,
        "art_sha": art_sha,
        "commit": commit,
        "costs": costs,
    }


def test_reserved_period_overlap() -> None:
    holdout_dt = int(datetime(2025, 7, 1, tzinfo=UTC).timestamp() * 1000)
    # 1. Non-overlapping before
    holdout_module.check_reserved_period_overlap(
        holdout_dt - 100_000, holdout_dt - 10, purpose="training"
    )
    # 2. Overlapping fixed range
    with pytest.raises(ValueError, match="overlaps reserved holdout period"):
        holdout_module.check_reserved_period_overlap(
            holdout_dt - 10, holdout_dt + 10, purpose="training"
        )
    # 3. Overlapping loaded DataFrame
    df = pd.DataFrame({"open_time": [holdout_dt - 50, holdout_dt + 50]})
    with pytest.raises(ValueError, match="overlaps reserved holdout period"):
        holdout_module.check_reserved_period_overlap(None, None, df, purpose="walkforward")
    # 4. Purpose == 'holdout' is allowed across holdout boundary
    df_h = pd.DataFrame({"open_time": [holdout_dt, holdout_dt + 100]})
    holdout_module.check_reserved_period_overlap(
        holdout_dt, holdout_dt + 100, df_h, purpose="holdout"
    )


def test_walkforward_make_folds_boundary() -> None:
    h_ms = int(datetime(2025, 7, 1, tzinfo=UTC).timestamp() * 1000)
    data_start = h_ms - 1000 * 86_400_000
    folds = make_folds(data_start, h_ms, train_days=500, val_days=100, step_days=100)
    for fold in folds:
        assert fold.val_end_ms < h_ms
        assert fold.train_end_ms < h_ms

    with pytest.raises(ValueError, match="exceeds central reserved boundary"):
        make_folds(data_start, h_ms + 1000)


def test_holdout_single_use_and_crash_safety(
    fake_settings: Settings,
    isolated_holdout_paths: tuple[Path, Path, Path],
    clean_git: GitSourceState,
) -> None:
    _, state_path, _ = isolated_holdout_paths
    _setup_mock_champion(fake_settings.models_dir, "m1")

    start_ms = holdout_module.get_holdout_start_ms(fake_settings)
    df = make_candles(10, start_ms=start_ms, interval="15m")

    mock_strat = MagicMock()
    mock_strat.strategy_id = "ppo:m1"
    mock_metrics = Metrics(
        strategy_id="ppo:m1",
        net_return=0.01,
        gross_return=0.012,
        fees=0.001,
        spread=0.0005,
        slippage=0.0005,
        funding=0.0,
        turnover=100.0,
        trade_count=1,
        mean_abs_exposure=0.5,
        max_drawdown=0.01,
        sharpe=1.5,
        n_candles=10,
    )
    mock_row = EvalRow(
        fold_id=-1,
        strategy_id="ppo:m1",
        seed=None,
        scenario="base",
        metrics=mock_metrics,
        val_buy_hold_return=0.0,
    )

    with (
        patch.object(PpoPolicyStrategy, "from_dir", return_value=mock_strat),
        patch("obsidian_rl.evaluation.holdout.CandleStore.read", return_value=df),
        patch(
            "obsidian_rl.evaluation.holdout.evaluate_strategies_on_slice",
            return_value=[mock_row],
        ),
    ):
        rep_path, rep_hash = holdout_module.run_final_holdout(
            fake_settings, "m1", "2025-07-02T00:00:00+00:00"
        )
        assert rep_path.exists()
        assert state_path.exists()
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["status"] == "completed"
        assert state_data["report_sha256"] == rep_hash

        with pytest.raises(RuntimeError, match="holdout already consumed: status is completed"):
            holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")

    state_path.unlink()
    with (
        patch.object(PpoPolicyStrategy, "from_dir", return_value=mock_strat),
        patch("obsidian_rl.evaluation.holdout.CandleStore.read", return_value=df),
        patch(
            "obsidian_rl.evaluation.holdout.evaluate_strategies_on_slice",
            side_effect=ValueError("simulated crash"),
        ),
    ):
        with pytest.raises(ValueError, match="simulated crash"):
            holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")

        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["status"] == "failed"
        assert "simulated crash" in state_data["reason"]

        with pytest.raises(RuntimeError, match="holdout already consumed: status is failed"):
            holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")


def test_frozen_champion_verification_and_provenance(
    fake_settings: Settings,
    isolated_holdout_paths: tuple[Path, Path, Path],
    clean_git: GitSourceState,
) -> None:
    _, _, _ = isolated_holdout_paths
    setup_info = _setup_mock_champion(fake_settings.models_dir, "m1", commit="a" * 40)

    with pytest.raises(
        RuntimeError, match="requested model 'm2' differs from verified champion 'm1'"
    ):
        holdout_module.run_final_holdout(fake_settings, "m2", "2025-07-02T00:00:00+00:00")

    dirty_state = GitSourceState(commit="a" * 40, is_clean=False, dirty_paths=["src/bad.py"])
    with (
        patch("obsidian_rl.evaluation.holdout.get_git_source_state", return_value=dirty_state),
        pytest.raises(RuntimeError, match="project source tree is dirty"),
    ):
        holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")

    diff_commit = GitSourceState(commit="b" * 40, is_clean=True, dirty_paths=[])
    with patch("obsidian_rl.evaluation.holdout.get_git_source_state", return_value=diff_commit):
        msg = r"source commit .* does not match champion promotion commit"
        with pytest.raises(RuntimeError, match=msg):
            holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")

    model_dir = Path(str(setup_info["model_dir"]))
    (model_dir / MODEL_FILE).write_bytes(b"tampered_weights")
    with pytest.raises(ModelCompatibilityError, match="checksum mismatch"):
        holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")


def test_immutable_report_verification_and_path_traversal(
    isolated_holdout_paths: tuple[Path, Path, Path],
) -> None:
    h_dir, _, _ = isolated_holdout_paths

    traversal_path = Path("artifacts/holdout/../../secret.json")
    with pytest.raises(RuntimeError, match="path traversal detected"):
        holdout_module._verify_report_file(traversal_path, "a" * 64)

    rep_data = {"schema_version": 1, "value": 123}
    rep_hash = _compute_report_hash(rep_data)
    rep_full = {**rep_data, "report_sha256": rep_hash}

    test_rep_path = h_dir / "report-test.json"
    test_rep_path.write_text(_json_dumps(rep_full) + "\n", encoding="utf-8")

    holdout_module._verify_report_file(test_rep_path, rep_hash)

    tampered_full = {**rep_data, "value": 999, "report_sha256": rep_hash}
    test_rep_path.write_text(_json_dumps(tampered_full) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="holdout report hash mismatch"):
        holdout_module._verify_report_file(test_rep_path, rep_hash)


def test_cmd_holdout_zero_leakage(
    fake_settings: Settings,
    isolated_holdout_paths: tuple[Path, Path, Path],
    clean_git: GitSourceState,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _, _ = isolated_holdout_paths
    _setup_mock_champion(fake_settings.models_dir, "m1")

    start_ms = holdout_module.get_holdout_start_ms(fake_settings)
    df = make_candles(10, start_ms=start_ms, interval="15m")
    mock_strat = MagicMock()
    mock_strat.strategy_id = "ppo:m1"
    mock_metrics = Metrics(
        strategy_id="ppo:m1",
        net_return=0.5,
        gross_return=0.6,
        fees=0.01,
        spread=0.01,
        slippage=0.01,
        funding=0.0,
        turnover=1000.0,
        trade_count=10,
        mean_abs_exposure=0.8,
        max_drawdown=0.05,
        sharpe=3.5,
        n_candles=10,
    )
    mock_row = EvalRow(
        fold_id=-1,
        strategy_id="ppo:m1",
        seed=None,
        scenario="base",
        metrics=mock_metrics,
        val_buy_hold_return=0.1,
    )

    with (
        patch("obsidian_rl.cli.get_settings", return_value=fake_settings),
        patch.object(PpoPolicyStrategy, "from_dir", return_value=mock_strat),
        patch("obsidian_rl.evaluation.holdout.CandleStore.read", return_value=df),
        patch(
            "obsidian_rl.evaluation.holdout.evaluate_strategies_on_slice",
            return_value=[mock_row],
        ),
    ):
        args = Namespace(model_id="m1", end="2025-07-02T00:00:00+00:00")
        code = cmd_holdout(args)
        assert code == 0
        out = capsys.readouterr().out
        assert "holdout completed" in out
        assert "model_id: m1" in out
        assert "report path:" in out
        assert "report sha256:" in out
        for forbidden in ("net_return", "sharpe", "equity", "drawdown", "0.5", "3.5", "0.05"):
            assert forbidden not in out


def test_holdout_concurrency_lock(
    fake_settings: Settings,
    isolated_holdout_paths: tuple[Path, Path, Path],
    clean_git: GitSourceState,
) -> None:
    _, _, lock_path = isolated_holdout_paths
    _setup_mock_champion(fake_settings.models_dir, "m1")

    lock_path.write_text(json.dumps({"pid": 999999, "created_at": time.time()}), encoding="utf-8")
    with pytest.raises(
        RuntimeError, match="timed out waiting for holdout lock; holdout currently running"
    ):
        holdout_module.run_final_holdout(fake_settings, "m1", "2025-07-02T00:00:00+00:00")


def test_holdout_repo_anchor_and_cwd_change(tmp_path: Path) -> None:
    with patch("obsidian_rl.evaluation.holdout.HOLDOUT_DIR", Path("artifacts/holdout")):
        orig_cwd = Path.cwd()
        dir1 = holdout_module.get_holdout_dir()
        state1 = holdout_module.get_holdout_state_path()
        try:
            os.chdir(tmp_path)
            dir2 = holdout_module.get_holdout_dir()
            state2 = holdout_module.get_holdout_state_path()
            assert dir1 == dir2
            assert state1 == state2
            assert dir1.is_absolute()
            assert state1.is_absolute()
        finally:
            os.chdir(orig_cwd)


def test_holdout_utc_boundaries() -> None:
    ms1, can1 = holdout_module.parse_utc_boundary("2025-07-01")
    assert ms1 == 1751328000000
    assert can1 == "2025-07-01T00:00:00Z"

    ms2, can2 = holdout_module.parse_utc_boundary("2025-07-01T00:00:00+00:00")
    assert ms2 == 1751328000000
    assert can2 == "2025-07-01T00:00:00Z"

    ms3, can3 = holdout_module.parse_utc_boundary("2025-07-01T00:00:00Z")
    assert ms3 == 1751328000000
    assert can3 == "2025-07-01T00:00:00Z"

    with pytest.raises(ValueError, match="naive timestamp or non-UTC offset rejected"):
        holdout_module.parse_utc_boundary("2025-07-01T12:00:00")

    with pytest.raises(ValueError, match="naive timestamp or non-UTC offset rejected"):
        holdout_module.parse_utc_boundary("2025-07-01T12:00:00+05:00")

    with pytest.raises(ValueError, match="malformed YYYY-MM-DD date"):
        holdout_module.parse_utc_boundary("2025-02-31")

    with pytest.raises(ValueError, match="reversed range"):
        holdout_module.check_reserved_period_overlap(200, 100)


def _valid_base_state() -> dict[str, object]:
    return {
        "schema_version": 1,
        "consumption_id": "0123456789abcdef0123456789abcdef",
        "started_at_utc": "2025-07-01T00:00:00Z",
        "status": "started",
        "reserved_start_utc": "2025-07-01T00:00:00Z",
        "fixed_end_utc": "2025-07-02T00:00:00Z",
        "symbol": "BTCUSDT",
        "interval": "15m",
        "model_id": "m1",
        "model_artifact_sha256": "a" * 64,
        "feature_schema": schema_fingerprint(),
        "source_commit": "b" * 40,
        "source_tree_clean": True,
        "costs": {"taker_fee": 0.0005, "half_spread": 0.00005, "slippage": 0.0001},
        "baselines": ["buy_hold", "rsi"],
        "scenarios": ["base", "costs2x", "delay1"],
        "report_filename": None,
        "report_sha256": None,
    }


def test_holdout_source_tree_clean_false(isolated_holdout_paths: tuple[Path, Path, Path]) -> None:
    _, state_path, _ = isolated_holdout_paths
    state = _valid_base_state()
    state["source_tree_clean"] = False
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="source_tree_clean must be exactly True"):
        holdout_module.load_holdout_state(state_path)


def test_holdout_state_strict_validation(isolated_holdout_paths: tuple[Path, Path, Path]) -> None:
    h_dir, state_path, _ = isolated_holdout_paths

    def _assert_invalid(state_dict: dict[str, object], match: str) -> None:
        state_path.write_text(json.dumps(state_dict), encoding="utf-8")
        with pytest.raises(RuntimeError, match=match):
            holdout_module.load_holdout_state(state_path, holdout_dir=h_dir)

    # Malformed consumption ID
    st = _valid_base_state()
    st["consumption_id"] = "not-a-hex-uuid"
    _assert_invalid(st, "consumption_id must be a 32-char hex UUID")

    # Malformed commit
    st = _valid_base_state()
    st["source_commit"] = "NOTLOWERCASECOMMIT"
    _assert_invalid(st, "source_commit must be lowercase 40-char hex")

    # Mismatched feature schema
    st = _valid_base_state()
    st["feature_schema"] = {"version": "wrong"}
    _assert_invalid(st, "feature_schema does not match current complete schema fingerprint")

    # Malformed costs
    st = _valid_base_state()
    st["costs"] = {"taker_fee": 0.0005}
    _assert_invalid(st, "costs must be a dict with exactly taker_fee, half_spread, slippage")

    # Malformed baselines
    st = _valid_base_state()
    st["baselines"] = []
    _assert_invalid(st, "baselines must be a non-empty list of unique non-empty strings")

    # Malformed scenarios
    st = _valid_base_state()
    st["scenarios"] = ["base", "other"]
    _assert_invalid(st, "scenarios must exactly equal \\['base', 'costs2x', 'delay1'\\]")

    # Extra fields
    st = _valid_base_state()
    st["extra_field"] = "unexpected"
    _assert_invalid(st, "unknown or extra fields in HOLDOUT_STATE.json")

    # Failed state containing metrics
    st = _valid_base_state()
    st["status"] = "failed"
    st["failure_class"] = "ValueError"
    st["reason"] = "something broke"
    st["failed_at_utc"] = "2025-07-01T01:00:00Z"
    st.pop("report_filename")
    st.pop("report_sha256")
    st["metrics"] = {"net_return": 0.5}
    _assert_invalid(st, "failed state must not contain metrics")

    # Completed state field disagreement
    st = _valid_base_state()
    st["status"] = "completed"
    rep_data = {
        "schema_version": 1,
        "consumption_id": "differentconsumptionid1234567890",
        "symbol": "BTCUSDT",
        "interval": "15m",
        "reserved_start_utc": "2025-07-01T00:00:00Z",
        "fixed_end_utc": "2025-07-02T00:00:00Z",
        "model_id": "m1",
        "model_artifact_sha256": "a" * 64,
        "source_commit": "b" * 40,
        "costs": st["costs"],
    }
    rep_hash = _compute_report_hash(rep_data)
    rep_full = {**rep_data, "report_sha256": rep_hash}
    rep_filename = "report-test-complete.json"
    (h_dir / rep_filename).write_text(_json_dumps(rep_full) + "\n", encoding="utf-8")
    st["report_filename"] = rep_filename
    st["report_sha256"] = rep_hash
    _assert_invalid(st, "report consumption_id does not match state")


def test_holdout_dataset_identity() -> None:
    df = pd.DataFrame(
        {
            "open_time": pd.Series([1000, 2000], dtype="int64"),
            "price": pd.Series([10.0, 20.0], dtype="float64"),
        }
    )
    base_id = holdout_module.compute_dataset_identity(df, start_ms=1000, end_ms=2000)

    # Index change alters hash
    df_idx = df.copy()
    df_idx.index = pd.Index([5, 10])
    idx_id = holdout_module.compute_dataset_identity(df_idx, start_ms=1000, end_ms=2000)
    assert idx_id["dataset_sha256"] != base_id["dataset_sha256"]

    # Dtype change alters hash
    df_dtype = df.copy()
    df_dtype["price"] = df_dtype["price"].astype("float32")
    dtype_id = holdout_module.compute_dataset_identity(df_dtype, start_ms=1000, end_ms=2000)
    assert dtype_id["dataset_sha256"] != base_id["dataset_sha256"]

    # Column order alters hash
    df_cols = df[["price", "open_time"]]
    cols_id = holdout_module.compute_dataset_identity(df_cols, start_ms=1000, end_ms=2000)
    assert cols_id["dataset_sha256"] != base_id["dataset_sha256"]

    # Row value alters hash
    df_row = df.copy()
    df_row.loc[0, "price"] = 15.0
    row_id = holdout_module.compute_dataset_identity(df_row, start_ms=1000, end_ms=2000)
    assert row_id["dataset_sha256"] != base_id["dataset_sha256"]

    # Middle row outside requested interval is rejected
    df_mid = pd.DataFrame(
        {
            "open_time": pd.Series([500, 1000, 2000], dtype="int64"),
            "price": pd.Series([10.0, 15.0, 20.0], dtype="float64"),
        }
    )
    with pytest.raises(ValueError, match=r"loaded dataset open_time .* precedes requested start"):
        holdout_module.compute_dataset_identity(df_mid, start_ms=1000, end_ms=2000)

    # Unsorted or duplicate open_time values are rejected
    df_dup = pd.DataFrame(
        {
            "open_time": pd.Series([1000, 1000], dtype="int64"),
            "price": pd.Series([10.0, 20.0], dtype="float64"),
        }
    )
    with pytest.raises(ValueError, match="open_time values must be unique and strictly increasing"):
        holdout_module.compute_dataset_identity(df_dup, start_ms=1000, end_ms=2000)


def test_holdout_lock_integrity_and_symlinks(
    isolated_holdout_paths: tuple[Path, Path, Path],
) -> None:
    h_dir, state_path, lock_path = isolated_holdout_paths

    # Ownership mismatch does not remove another process's lock
    with (
        pytest.raises(RuntimeError, match="holdout lock ownership mismatch"),
        holdout_module._holdout_lock(h_dir),
    ):
        # Simulate another process taking ownership or modifying the token
        lock_path.write_text("another-token", encoding="utf-8")
    assert lock_path.exists()
    assert lock_path.read_text(encoding="utf-8") == "another-token"
    lock_path.unlink()

    # Symlinked paths rejected
    with patch.object(Path, "is_symlink", return_value=True):
        with pytest.raises(RuntimeError, match="must not be a symlink"):
            holdout_module.load_holdout_state(state_path, holdout_dir=h_dir)
        with pytest.raises(RuntimeError, match="must not be a symlink"):
            holdout_module._verify_report_file(state_path, "a" * 64, holdout_dir=h_dir)
        with (
            pytest.raises(RuntimeError, match="must not be a symlink"),
            holdout_module._holdout_lock(h_dir),
        ):
            pass

    # Unexpected lock filesystem errors are not swallowed
    with (
        patch("builtins.open", side_effect=OSError("simulated disk error")),
        pytest.raises(RuntimeError, match="unexpected filesystem error creating lock file"),
        holdout_module._holdout_lock(h_dir),
    ):
        pass
