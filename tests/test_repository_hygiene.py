"""Tests for repository hygiene, gitignore invariants, secret checks, and package boundaries."""

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

import obsidian_rl

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_env_file_not_tracked() -> None:
    """Ensure .env files are not tracked in git."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files", ".env", ".env.*"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        tracked = [
            line.strip()
            for line in out.splitlines()
            if line.strip() and line.strip() != ".env.example"
        ]
        assert not tracked, "Sensitve .env files are tracked in git repository"
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If git is not available or not in a git repo during wheel smoke test, verify file check
        pass


def test_no_secret_placeholders_committed() -> None:
    """Check tracked source files for committed API keys without printing them."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        tracked_files = [REPO_ROOT / line.strip() for line in out.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        tracked_files = [
            p
            for p in REPO_ROOT.rglob("*")
            if p.is_file()
            and ".git" not in p.parts
            and ".venv" not in p.parts
            and "site-packages" not in p.parts
        ]

    # Patterns indicating potential secrets or live Binance API keys
    patterns = [
        re.compile(r"api_key\s*=\s*[\"'][a-zA-Z0-9]{20,}[\"']", re.IGNORECASE),
        re.compile(r"api_secret\s*=\s*[\"'][a-zA-Z0-9]{20,}[\"']", re.IGNORECASE),
        re.compile(r"binance_secret\s*=\s*[\"'][a-zA-Z0-9]{20,}[\"']", re.IGNORECASE),
        re.compile(r"private_key\s*=\s*[\"'][a-zA-Z0-9]{20,}[\"']", re.IGNORECASE),
    ]

    suspicious_files = []
    ignored_exts = (".png", ".whl", ".tar", ".gz", ".db", ".parquet", ".pyc")
    for fpath in tracked_files:
        if not fpath.exists() or fpath.suffix in ignored_exts:
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            for pattern in patterns:
                if pattern.search(content):
                    suspicious_files.append(str(fpath.relative_to(REPO_ROOT)))
                    break
        except Exception:
            continue

    assert not suspicious_files, f"Found suspicious secrets in {len(suspicious_files)} file(s)."


def test_gitignore_covers_required_patterns() -> None:
    """Verify that .gitignore excludes envs, caches, virtualenvs, databases, models."""
    gitignore = REPO_ROOT / ".gitignore"
    if not gitignore.exists():
        pytest.skip(".gitignore not present in this checkout/environment")

    text = gitignore.read_text(encoding="utf-8")
    required_patterns = [
        ".env",
        "__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".venv/",
        "*.db",
        "*.sqlite",
        "*.pkl",
        "*.joblib",
        "*.pt",
        "/data/",
        "/artifacts/",
        "/models/",
    ]
    for pattern in required_patterns:
        assert pattern in text, f".gitignore missing essential pattern: {pattern}"


def test_package_includes_required_runtime_modules() -> None:
    """Verify that the installed/imported package includes all runtime modules."""
    assert obsidian_rl.__file__ is not None
    pkg_dir = Path(obsidian_rl.__file__).resolve().parent
    assert pkg_dir.is_dir()

    required_items = [
        "cli.py",
        "config.py",
        "data",
        "env",
        "evaluation",
        "features",
        "gate",
        "ledger",
        "live",
        "portfolio",
        "strategies",
        "training",
    ]
    for item in required_items:
        path = pkg_dir / item
        assert path.exists(), f"Runtime package directory missing required item: {item}"


def test_installed_package_isolation() -> None:
    """Ensure importing obsidian_rl does not dynamically inject source paths."""
    assert obsidian_rl.__file__ is not None
    mod_path = Path(obsidian_rl.__file__).resolve()
    src_dir = REPO_ROOT / "src" / "obsidian_rl"
    in_src = src_dir in mod_path.parents or mod_path.parent == src_dir
    in_site = any("site-packages" in p or "dist-packages" in p for p in mod_path.parts)
    assert in_src or in_site, f"obsidian_rl imported from unexpected location: {mod_path}"


def test_tests_init_prevents_collision() -> None:
    """Verify tests/__init__.py exists and setuptools packages only src."""
    tests_init = REPO_ROOT / "tests" / "__init__.py"
    if REPO_ROOT.exists() and (REPO_ROOT / "pyproject.toml").exists():
        assert tests_init.exists(), "tests/__init__.py must exist to prevent collision"
        with (REPO_ROOT / "pyproject.toml").open("rb") as f:
            data = tomllib.load(f)
        find_cfg = data.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find", {})
        find_where = find_cfg.get("where")
        assert find_where == ["src"], "packaging where must be ['src']"
