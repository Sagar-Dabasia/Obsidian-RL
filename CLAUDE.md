# Obsidian-RL — working notes for Claude

Deep-RL crypto research + live-paper-trading platform. Research software; no profit claims.
Read `docs/archive/cycle_01/research/SESSION_HANDOFF.md` first for current state; `docs/archive/cycle_01/research/DECISIONS.md` for ADRs.

## Hard rules
- NEVER read/print `.env` or any secret. Public market-data endpoints only; no authenticated calls.
- NEVER place exchange orders (real or Testnet). Paper execution only.
- NEVER use future data in features/labels/normalization/selection. No shuffled financial splits.
- NEVER silently substitute synthetic market data. Fail explicitly.
- NEVER load unverified pickle/joblib artifacts (`legacy/` artifacts are untrusted).
- No `git push`, no history rewrite, no `git reset --hard`.
- Do not weaken tests/costs/benchmarks to improve reported numbers.

## Layout
- `src/obsidian_rl/` — the platform (only supported code)
  - `config.py` settings · `data/` historical layer + validation · `features/` causal pipeline
  - `portfolio/` engine + costs · `ledger/` SQLite ledger · `strategies/` baselines
  - `env/` Gymnasium env · `training/` PPO · `evaluation/` walk-forward · `live/` paper trader
  - `dashboard/` Streamlit · `cli.py` entry points
- `legacy/` — deprecated Q-learning system (audited defects: `docs/archive/cycle_01/reports/AUDIT.md`). Do not import.
- `tests/` — pytest; network always mocked; CPU-only; no credentials required.
- `data/`, `artifacts/`, `models/` — local only, gitignored.

## Environment
- Windows 11, PowerShell; Python 3.11.4 in `.venv` (use `.venv\Scripts\python.exe`)
- RTX 4060 Laptop 8 GB; CUDA via PyTorch wheel only (no system CUDA changes)
- Package manager: pip; deps pinned in `pyproject.toml` (extras: rl, gate, dashboard, dev)

## Commands
```powershell
.venv\Scripts\python.exe -m pytest -q            # tests
.venv\Scripts\ruff.exe check . ; .venv\Scripts\ruff.exe format --check .
.venv\Scripts\python.exe -m mypy                  # scoped to src/obsidian_rl
.venv\Scripts\python.exe -m compileall -q src tests
.venv\Scripts\python.exe -m obsidian_rl.cli --help
```

## Market/product (ADR-003)
Binance USD-M perpetual BTCUSDT, 15m klines, UTC, public REST + websocket.
Long/short via target-exposure {-1,-0.5,0,0.5,1}. Paper-only execution at next candle open.

## Git
Branch: `rebuild/deep-rl-platform`. Commit per phase after gates pass. Never push.
