# Architecture Decision Records

## ADR-001: Rebuild in-place under `src/obsidian_rl`, quarantine legacy (2026-07-19)
Legacy flat modules moved to `legacy/` (git mv, history preserved), never imported by new
code. Rationale: every legacy subsystem has correctness-critical defects (docs/AUDIT.md);
characterization tests would certify wrong behavior. Legacy artifacts (`*.pkl`) untrusted —
never loaded. Removal only after replacement parity (see Legacy policy in prompt/CLAUDE.md).

## ADR-002: Toolchain and dependency discipline (2026-07-19)
pip + `pyproject.toml` (setuptools, src-layout), pinned direct deps, extras `rl|gate|dashboard|dev`.
No uv/poetry available; lock = pinned direct deps now, `pip freeze` snapshot at stabilization.
**pandas** is the single dataframe library (already in venv; Polars rejected to avoid dual
implementations). pytest/ruff/mypy; pre-commit rejected (single-developer, CI-less repo, gates
run per phase). SQLite via stdlib `sqlite3` (no SQLAlchemy until a measured need exists).
One Binance integration: hand-rolled public REST + websocket client behind an interface
(python-binance rejected: pulls auth surface we must never use).

## ADR-003: Market product (Phase 1) — see docs/adr/ADR-003-market-product.md

## ADR-004: PyTorch CUDA install (2026-07-19)
torch 2.11.0+cu128 installed from https://download.pytorch.org/whl/cu128 into .venv
(PyPI torch is CPU-only on Windows, so it is not listed in pyproject deps; reinstall with
`.venv\Scripts\python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128`).
Verified: RTX 4060 Laptop GPU, 8187 MB, CUDA 12.8 available. gymnasium==1.3.0,
stable-baselines3==2.9.0. VecNormalize deliberately not used: all features are
scale-free and clipped upstream, avoiding a fitted-preprocessing leakage surface.
Measured throughput (20k steps, 8 envs, 64x64 MLP): CPU 2316 steps/s vs CUDA 791 steps/s
— per SB3 guidance, small-MLP PPO is env/CPU-bound, so training commands use CPU for this
architecture; the GPU stays available for larger networks.
