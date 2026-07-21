# Agent Run Report — Phase 8: CI & Clean-Machine Reproducibility

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase8-ci-reproducibility` |
| **Starting commit** | `e90b8e4914cf9b5888a683f9d1a1458186f60ecb` |
| **Task** | Implement Phase 8 clean-machine continuous integration (`.github/workflows/ci.yml`), reproducible packaging (`build==1.5.0` in `[dev]`, console entrypoint `obsidian-rl`), and hygiene/packaging test suites (`test_repository_hygiene.py`, `test_packaging.py`). |

---

## Working-tree status

```
M  README.md
M  pyproject.toml
A  .github/workflows/ci.yml
A  docs/development.md
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
A  docs/agent-runs/2026-07-21T203000Z-phase8-ci-reproducibility.md
A  tests/test_packaging.py
A  tests/test_repository_hygiene.py
```

---

## Fixes & Implementation

### 1. Development Environment & Packaging (`pyproject.toml`, `docs/development.md`, `README.md`)
- Added `build==1.5.0` to the `[dev]` optional dependency table in `pyproject.toml` so that `python -m pip install -e ".[dev]"` provides a complete development toolchain (`pytest`, `ruff`, `mypy`, `build`).
- Added `[project.scripts]` table defining the `obsidian-rl` console entrypoint (`obsidian-rl = "obsidian_rl.cli:main"`), ensuring `obsidian-rl` is created in bin/Scripts upon package installation.
- Created `docs/development.md` documenting supported Python versions (`>=3.11`), clean virtual environment setup, static verification commands, distribution packaging, offline test guarantees, and holdout segregation.
- Updated `README.md` to display the clean setup instructions and link directly to `docs/development.md`.

### 2. GitHub Actions CI Workflow (`.github/workflows/ci.yml`)
- Created least-privilege CI workflow triggered on pull requests and pushes across all branches with `permissions: contents: read`.
- Configured concurrency grouping (`cancel-in-progress: true`) to abort superseded runs automatically.
- Tested across `ubuntu-latest` and `windows-latest` for Python `3.11` and `3.12` (`2x2` matrix) using pip dependency caching.
- Executes clean package installation (`-e ".[dev]"`), `pip check`, compilation (`compileall`), `ruff check`, `ruff format --check`, `mypy`, `pytest`, and package building (`python -m build`).
- Includes an isolated wheel smoke test that creates a clean virtual environment, installs the built wheel, runs from outside the repository directory, verifies importability without source checkout leakage, and runs the CLI help command (`obsidian-rl --help` and `python -m obsidian_rl.cli --help`).

### 3. Test Isolation & Repository Hygiene (`tests/test_packaging.py`, `tests/test_repository_hygiene.py`)
- Created `test_packaging.py` verifying `pyproject.toml` metadata, runtime dependencies, `setuptools.packages.find.where = ["src"]`, all 13 runtime submodules can be imported cleanly, and `obsidian_rl` origin validation.
- Created `test_repository_hygiene.py` verifying `.env` files are not tracked in git, no API keys or secret patterns are committed across tracked files, `.gitignore` excludes required cache/database/model/holdout paths, runtime directories are present, installed package isolation holds outside source checkout, and `tests/__init__.py` prevents top-level namespace collisions.

---

## Verification Results

### Focused Tests
```
python -m pytest tests/test_packaging.py tests/test_repository_hygiene.py -q
......................                                                   [100%]
22 passed
```

### Full Suite
```
python -m pytest -q
........................................................................ [ 18%]
........................................................................ [ 37%]
........................................................................ [ 56%]
........................................................................ [ 75%]
..................................s..................................... [ 93%]
........................                                                 [100%]
381 passed, 1 skipped
```

### Static Analysis, Linting & Package Check
```
python -m compileall -q src tests                            -> clean
python -m mypy src                                          -> Success: no issues found in 46 source files
python -m ruff check src tests                               -> All checks passed!
python -m ruff format --check src tests                      -> 13 files already formatted
python -m pip check                                         -> No broken requirements found
python -m build                                             -> Successfully built obsidian_rl-0.1.0.tar.gz and wheel
git diff --check                                             -> clean
```

### Wheel Smoke Test
```
Installed dist/obsidian_rl-0.1.0-py3-none-any.whl in fresh virtual environment outside repository.
python -c "import obsidian_rl; print('Version:', obsidian_rl.__version__)" -> Version: 0.1.0
obsidian-rl.exe --help                                                     -> Full CLI usage output cleanly shown
python -m obsidian_rl.cli --help                                           -> Full CLI usage output cleanly shown
```
