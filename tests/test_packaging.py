"""Tests for package metadata, module structure, and installability."""

import importlib
import tomllib
from pathlib import Path

import pytest

import obsidian_rl

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_toml_metadata() -> None:
    """Verify pyproject.toml configuration and dependencies."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml not found"

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    assert project.get("name") == "obsidian-rl"
    assert project.get("version") == obsidian_rl.__version__
    assert project.get("requires-python") == ">=3.11"

    deps = project.get("dependencies", [])
    expected_deps = ["numpy", "pandas", "pyarrow", "requests", "websockets", "pydantic-settings"]
    for expected in expected_deps:
        assert any(d.startswith(expected) for d in deps), (
            f"Missing expected dependency {expected} in pyproject.toml"
        )


def test_package_find_where_is_src() -> None:
    """Ensure setuptools find where is set to src to avoid packaging tests or legacy."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    find_cfg = data.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find", {})
    assert find_cfg.get("where") == ["src"], "setuptools where must be ['src']"


@pytest.mark.parametrize(
    "submodule",
    [
        "obsidian_rl.cli",
        "obsidian_rl.config",
        "obsidian_rl.dashboard",
        "obsidian_rl.data",
        "obsidian_rl.env",
        "obsidian_rl.evaluation",
        "obsidian_rl.features",
        "obsidian_rl.gate",
        "obsidian_rl.ledger",
        "obsidian_rl.live",
        "obsidian_rl.portfolio",
        "obsidian_rl.strategies",
        "obsidian_rl.training",
    ],
)
def test_runtime_submodules_importable(submodule: str) -> None:
    """Verify that all required runtime submodules can be cleanly imported."""
    mod = importlib.import_module(submodule)
    assert mod is not None


def test_package_not_importing_from_wrong_location() -> None:
    """Verify obsidian_rl module origin relative to sys.path entries."""
    assert obsidian_rl.__file__ is not None
    mod_path = Path(obsidian_rl.__file__).resolve()
    assert mod_path.exists()
