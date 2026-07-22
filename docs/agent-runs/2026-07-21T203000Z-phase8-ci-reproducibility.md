# Agent Run Report — Phase 8: CI & Clean-Machine Reproducibility

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase8-ci-reproducibility` |
| **Starting commit** | `1cf5483e43e13cea91b43d7dfbb1f77bafaa57b6` |
| **Task** | Finish Phase 8 clean-environment dependency wiring: install `.[dev,rl,gate,dashboard]` in CI workflow (`.github/workflows/ci.yml`), `README.md`, and `docs/development.md`. Validate documented extras in `tests/test_packaging.py`. Verify clean virtual environment setup and wheel installation. |

---

## Working-tree status

```
M  README.md
M  pyproject.toml
M  .github/workflows/ci.yml
M  docs/development.md
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
M  docs/agent-runs/2026-07-21T203000Z-phase8-ci-reproducibility.md
M  tests/test_packaging.py
A  tests/test_repository_hygiene.py
```

---

## Fixes & Implementation

### 1. Clean Environment Dependency Wiring (`.github/workflows/ci.yml`, `README.md`, `docs/development.md`)
- Updated GitHub Actions CI workflow to install all four required optional dependency groups using the single consistent command: `python -m pip install -e ".[dev,rl,gate,dashboard]"`.
- Updated `README.md` setup instructions to document `python -m pip install -e ".[dev,rl,gate,dashboard]"`.
- Updated `docs/development.md` setup instructions and documentation to mandate `python -m pip install -e ".[dev,rl,gate,dashboard]"`.

### 2. Packaging & CI Extras Verification (`tests/test_packaging.py`)
- Added `test_optional_dependency_groups_defined` verifying `pyproject.toml` defines all required extras (`dev`, `rl`, `gate`, `dashboard`).
- Added `test_ci_workflow_installs_all_four_extras` reading `.github/workflows/ci.yml` and proving the CI installation step specifies `pip install -e ".[dev,rl,gate,dashboard]"`.

### 3. Real Clean-Venv Verification
- Created brand-new temporary virtual environment `D:\clean_ci_venv`.
- Inside `D:\clean_ci_venv`, successfully ran:
  - `python -m pip install --upgrade pip`
  - `python -m pip install -e ".[dev,rl,gate,dashboard]"`
  - `python -m pip check` -> Clean
  - `python -m pytest -q` -> 383 passed, 1 skipped
  - `python -m compileall -q src tests` -> Clean
  - `python -m ruff check src tests` -> All checks passed
  - `python -m ruff format --check src tests` -> Formatted
  - `python -m mypy src` -> Success: no issues found in 46 source files
  - `python -m build` -> Built obsidian_rl-0.1.0.tar.gz and wheel
- Installed built wheel in separate clean virtual environment `D:\wheel_clean_venv` and verified:
  - `python -c "import obsidian_rl"` -> Clean import
  - `obsidian-rl --help` -> Full CLI usage displayed

---

## Verification Results

### Focused / Packaging Tests
```
python -m pytest tests/test_packaging.py tests/test_repository_hygiene.py -q
........................                                                 [100%]
24 passed
```

### Fresh-Venv Test Suite
```
python -m pytest -q (inside D:\clean_ci_venv)
........................................................................ [ 18%]
........................................................................ [ 37%]
........................................................................ [ 55%]
........................................................................ [ 74%]
....................................s................................... [ 93%]
..........................                                               [100%]
383 passed, 1 skipped
```

### Local Repository Test Suite
```
python -m pytest -q (inside .venv)
........................................................................ [ 18%]
........................................................................ [ 37%]
........................................................................ [ 55%]
........................................................................ [ 74%]
....................................s................................... [ 93%]
..........................                                               [100%]
383 passed, 1 skipped
```

### Static Analysis, Linting & Package Check
```
python -m compileall -q src tests                            -> clean
python -m mypy src                                          -> Success: no issues found in 46 source files
python -m ruff check tests/test_packaging.py                -> All checks passed!
python -m ruff format --check tests/test_packaging.py       -> 1 file already formatted
python -m pip check                                         -> No broken requirements found
python -m build                                             -> Successfully built obsidian_rl-0.1.0.tar.gz and wheel
git diff --check                                             -> clean
```
