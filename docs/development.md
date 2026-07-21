# Development Guide & Clean-Machine Setup

Obsidian-RL is designed to be fully reproducible in fresh development environments and continuous integration (CI) workflows without relying on local state, external market calls, or private credentials.

## Supported Python Versions

Obsidian-RL requires **Python `>=3.11`**. Automated clean-machine CI testing verifies compatibility across:
- **Python 3.11** (Linux & Windows)
- **Python 3.12** (Linux & Windows)

## Clean Environment Setup

To set up a clean, isolated development environment from a fresh repository clone using standard packaging (`setuptools`):

```bash
# 1. Create and activate an isolated virtual environment
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# 2. Upgrade pip and install the package with dev dependencies
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The `.[dev]` optional dependency group installs exact versions of the required development tooling (`pytest`, `ruff`, `mypy`, `build`) without adding global packages or unused dependencies.

If working with specific optional subsystems (e.g., reinforcement learning, supervised gating, or dashboarding), install those dependency groups as needed:
```bash
python -m pip install -e ".[rl,gate,dashboard,dev]"
```

## Verification Commands

Run the following checks locally before committing changes:

### Test Suite
```bash
python -m pytest -q
```

### Static Analysis & Syntax Verification
```bash
# Check Python compilation across source and tests
python -m compileall -q src tests

# Run Ruff linter checks
python -m ruff check src tests

# Run Ruff formatting check
python -m ruff format --check src tests

# Run Mypy static type checking
python -m mypy src

# Check package dependency tree consistency
python -m pip check
```

## Building and Installing Distribution Wheels

To build standard source (`sdist`) and wheel (`bdist_wheel`) packages:
```bash
python -m build
```

Artifacts will be generated in `dist/` (e.g., `dist/obsidian_rl-0.1.0-py3-none-any.whl`).

To verify wheel self-containment, install the wheel into a separate clean environment and run outside the repository:
```bash
python -m venv wheel_test_env
source wheel_test_env/bin/activate  # or wheel_test_env\Scripts\activate on Windows
pip install dist/obsidian_rl-*.whl

# Run outside the repository directory to ensure no source checkout leakage
cd ..
python -c "import obsidian_rl; print(obsidian_rl.__version__)"
obsidian-rl --help
```

## Test Isolation & CI Principles

- **Offline & Synthetic**: All automated unit tests run completely offline against synthetic market data and mocked API clients. No network access or Binance connection is required or attempted.
- **No Local State Dependencies**: Tests execute cleanly inside temporary directories and never read or write to user directories, hardcoded paths (`D:\Obsidian-RL`), or existing `.venv` environments.
- **Holdout Isolation**: Real holdout evaluation against production holdout candles (`run_final_holdout`) is strictly segregated and **is not part of CI**. CI and development tests never touch real holdout evaluation datasets or live API secrets.
