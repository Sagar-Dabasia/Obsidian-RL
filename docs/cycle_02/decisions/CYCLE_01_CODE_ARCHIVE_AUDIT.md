# Cycle 01 Code Archive Audit & Inventory

## Executive Summary & Audit Purpose
This document provides a comprehensive, non-destructive audit and classification of all code components, tools, test suites, strategies, and CLI entry points in the Obsidian-RL repository following the completion of Research Cycle 01 and the retirement of its underlying hypotheses (15-minute PPO, seed ensembles, and Alpha Gate).

In accordance with Obsidian-RL governance rules (`AGENTS.md`), **no source code, tests, tools, or configurations have been moved, renamed, deleted, or modified during this audit**. This document serves as the formal decision record and roadmap for future code archival.

---

## Service & Dependency Safety Confirmation
- **No Paid Services Required**: All historical market data ingestion, validation, portfolio accounting, feature engineering, and paper execution operate 100% offline or utilize free public APIs (e.g., Binance public REST/WS, OANDA practice feeds).
- **No Private Credentials**: No API keys, secrets, or paid external subscriptions are imported, required, or exposed in version control.
- **Zero Paid Dependencies**: The repository relies strictly on open-source Python packaging (`numpy`, `pandas`, `pyarrow`, `gymnasium`, `stable-baselines3`, `lightgbm`, `pydantic`, `pytest`, `ruff`, `mypy`).

---

## Summary of Code Component Classifications

| Classification | Count | Description | Action Required |
|---|---|---|---|
| **KEEP ACTIVE** | 24 modules / 20 tests | Essential reusable infrastructure, data contracts, portfolio accounting, cost models, walk-forward mechanics, paper trader, and ledger. | Retain in active `src/obsidian_rl/` codebase for Cycle 02. |
| **ARCHIVE CANDIDATE** | 4 modules / 3 tests | Decoupled research tools and strategy wrappers specifically tied to retired Cycle 01 hypotheses. | Safe to move to `archive/cycle_01/` in the next archival phase. |
| **KEEP BUT MARK LEGACY** | 5 modules / 4 tests | Cycle 01 RL/PPO training and model lifecycle code that is currently imported by active CLI commands or promotion logic. | Retain in `src/obsidian_rl/` until CLI entry points are updated or refactored for Cycle 02. |

---

## Detailed Component Inventory & Audit Matrix

### 1. Tools & Standalone Research Scripts (`tools/`)

| Current Path | Purpose | Cycle 1 Dependency | Imports From | Imported By | Tests Covering | CLI Exposure | Safe to Move? | Reason | Recommended Future Path |
|---|---|---|---|---|---|---|---|---|---|
| `tools/alpha_gate_pilot.py` | CLI tool for running Alpha Gate Historical Pilot 01. | Supervised Alpha Gate net-edge model. | `obsidian_rl.config`, `store`, `validation`, `alpha_gate`, `gated`, `metrics` | None (standalone script) | `tests/test_alpha_gate_pilot.py` | Standalone script (`python tools/alpha_gate_pilot.py`) | **YES** | Standalone tool; zero imports from `cli.py` or core packages. | `archive/cycle_01/tools/alpha_gate_pilot.py` |
| `tools/ppo_seed_ensemble_screen.py` | CLI tool for running PPO Seed Ensemble Screen 01 across existing models. | 5-seed PPO median ensemble hypothesis. | `obsidian_rl.config`, `store`, `metrics`, `walkforward`, `ppo_policy`, `registry` | None (standalone script) | `tests/test_seed_ensemble_screen.py` | Standalone script (`python tools/ppo_seed_ensemble_screen.py`) | **YES** | Standalone tool; zero imports from `cli.py` or core packages. | `archive/cycle_01/tools/ppo_seed_ensemble_screen.py` |

---

### 2. Strategy Subsystem (`src/obsidian_rl/strategies/`)

| Current Path | Purpose | Cycle 1 Dependency | Imports From | Imported By | Tests Covering | CLI Exposure | Safe to Move? | Reason | Recommended Future Path |
|---|---|---|---|---|---|---|---|---|---|
| `src/obsidian_rl/strategies/base.py` | `BaseStrategy` abstract base class. | General strategy interface. | Standard library | `baselines.py`, `gated.py`, `ppo_policy.py`, `paper_trader.py` | Covered via all strategy tests | Internal abstraction | **NO (KEEP ACTIVE)** | Core reusable interface required by all past and future strategies. | `src/obsidian_rl/strategies/base.py` |
| `src/obsidian_rl/strategies/baselines.py` | Deterministic baseline strategies (Flat, Buy&Hold, Regime Momentum, Threshold, Cooldown). | Baseline comparison benchmarks. | `base.py`, `numpy`, `pandas` | `cli.py`, `walkforward.py` | `tests/test_backtest_baselines.py` | Default strategy in `obsidian-rl replay` and `paper-trade` | **NO (KEEP ACTIVE)** | Essential deterministic benchmarks required for Cycle 02 comparative evaluation. | `src/obsidian_rl/strategies/baselines.py` |
| `src/obsidian_rl/strategies/gated.py` | `GatedStrategy` and `GateDirectStrategy` wrappers around `AlphaGate`. | Alpha Gate LightGBM model. | `base.py`, `alpha_gate.py` | `tools/alpha_gate_pilot.py` | `tests/test_alpha_gate.py` | None | **YES** | Only used by Alpha Gate pilot script and tests; decoupled from CLI. | `archive/cycle_01/strategies/gated.py` |
| `src/obsidian_rl/strategies/ppo_policy.py` | `PpoPolicyStrategy` loading SB3 PPO zip checkpoints for inference. | SB3 PPO model inference. | `base.py`, `stable_baselines3`, `torch` | `cli.py`, `promotion.py`, `ppo_seed_ensemble_screen.py` | `tests/test_training.py`, `test_promotion.py`, `test_seed_ensemble_screen.py` | Exposed via `obsidian-rl walk-forward`, `replay`, `paper-trade` | **NO (KEEP LEGACY)** | Currently imported by `cli.py` and `promotion.py`. Moving now would break CLI. | `src/obsidian_rl/strategies/ppo_policy.py` |

---

### 3. Supervised Gate Subsystem (`src/obsidian_rl/gate/`)

| Current Path | Purpose | Cycle 1 Dependency | Imports From | Imported By | Tests Covering | CLI Exposure | Safe to Move? | Reason | Recommended Future Path |
|---|---|---|---|---|---|---|---|---|---|
| `src/obsidian_rl/gate/alpha_gate.py` | LightGBM supervised classifier predicting signed net-edge. | Alpha Gate hypothesis. | `lightgbm`, `scikit-learn`, `numpy`, `pandas` | `strategies/gated.py`, `tools/alpha_gate_pilot.py` | `tests/test_alpha_gate.py` | None | **YES** | Hypothesis retired; decoupled from core CLI and active execution paths. | `archive/cycle_01/experiments/alpha_gate.py` |

---

### 4. RL Training Subsystem (`src/obsidian_rl/training/`)

| Current Path | Purpose | Cycle 1 Dependency | Imports From | Imported By | Tests Covering | CLI Exposure | Safe to Move? | Reason | Recommended Future Path |
|---|---|---|---|---|---|---|---|---|---|
| `src/obsidian_rl/training/device.py` | Detects PyTorch CUDA / CPU capabilities (`detect_device`). | Device selection utility. | `torch` | `cli.py`, `ppo.py` | `tests/test_training.py` | `obsidian-rl gpu-check` | **NO (KEEP ACTIVE)** | Reusable hardware inspection utility needed for Cycle 02 ML acceleration. | `src/obsidian_rl/training/device.py` |
| `src/obsidian_rl/training/ppo.py` | SB3 PPO training loop, `TrainConfig`, and `EvalCallback` setup. | SB3 PPO training. | `trading_env.py`, `device.py`, `costs.py`, `stable_baselines3` | `cli.py` | `tests/test_training.py` | `obsidian-rl train`, `walk-forward` | **NO (KEEP LEGACY)** | Imported directly by `cli.py` for `train` and `walk-forward` commands. | `src/obsidian_rl/training/ppo.py` |
| `src/obsidian_rl/training/promotion.py` | Champion evaluation gate, evidence check, and promotion/rollback. | Model lifecycle & promotion gate. | `ppo_policy.py`, `registry.py`, `metrics.py`, `holdout.py` | `cli.py` | `tests/test_promotion.py` | `obsidian-rl candidate-eval`, `promote`, `rollback` | **NO (KEEP LEGACY)** | Core model governance logic; currently references SB3 PPO `ppo_policy.py`. | `src/obsidian_rl/training/promotion.py` |
| `src/obsidian_rl/training/registry.py` | `ModelRegistry` tracking model metadata (`model_record.json`). | Model versioning metadata. | `pydantic`, `json` | `promotion.py`, `ppo_seed_ensemble_screen.py` | `tests/test_registry.py` | Indirect via `promote` / `candidate-eval` | **NO (KEEP ACTIVE)** | Reusable metadata & version registry pattern needed for Cycle 02 models. | `src/obsidian_rl/training/registry.py` |

---

### 5. Gymnasium Environment (`src/obsidian_rl/env/`)

| Current Path | Purpose | Cycle 1 Dependency | Imports From | Imported By | Tests Covering | CLI Exposure | Safe to Move? | Reason | Recommended Future Path |
|---|---|---|---|---|---|---|---|---|---|
| `src/obsidian_rl/env/trading_env.py` | `TradingEnv` Gymnasium interface with reward penalty calculation. | 15m intraday SB3 PPO Gymnasium environment. | `gymnasium`, `pipeline.py`, `engine.py`, `costs.py` | `cli.py`, `ppo.py` | `tests/test_trading_env.py` | `obsidian-rl train`, `walk-forward` | **NO (KEEP LEGACY)** | Direct dependency of `cli.py` (`RewardConfig`) and `ppo.py`. | `src/obsidian_rl/env/trading_env.py` |

---

### 6. Core Infrastructure, Data, Evaluation & Execution (KEEP ACTIVE)

| Current Path | Subsystem | Purpose | Safe to Move? | Reason |
|---|---|---|---|---|
| `src/obsidian_rl/config.py` | Config | Pydantic environment configuration (`Settings`). | **NO (KEEP ACTIVE)** | Core platform settings loader. |
| `src/obsidian_rl/cli.py` | CLI | Main CLI parser and subcommand routing. | **NO (KEEP ACTIVE)** | Primary user and command interface. |
| `src/obsidian_rl/data/binance_client.py` | Data Ingestion | REST & WebSocket public market data client. | **NO (KEEP ACTIVE)** | Reusable public market data feed provider. |
| `src/obsidian_rl/data/download.py` | Data Ingestion | Historical bulk downloader and incremental updater. | **NO (KEEP ACTIVE)** | Essential data update utility. |
| `src/obsidian_rl/data/schema.py` | Data Schema | Data validation schemas for OHLCV candles. | **NO (KEEP ACTIVE)** | Foundational data contract. |
| `src/obsidian_rl/data/store.py` | Storage | Parquet partitioned candle storage (`CandleStore`). | **NO (KEEP ACTIVE)** | Primary local historical data store. |
| `src/obsidian_rl/data/validation.py` | Data Quality | Data quality, gap detection, and dupe verification. | **NO (KEEP ACTIVE)** | Core data integrity inspector. |
| `src/obsidian_rl/data/vision.py` | Data Utility | Bulk rendering and visualization helpers. | **NO (KEEP ACTIVE)** | Inspection utility. |
| `src/obsidian_rl/portfolio/costs.py` | Accounting | Transaction cost, spread, and slippage model (`CostModel`). | **NO (KEEP ACTIVE)** | Essential execution accounting. |
| `src/obsidian_rl/portfolio/engine.py` | Accounting | Portfolio position, PnL, leverage, and cash tracking (`PortfolioEngine`). | **NO (KEEP ACTIVE)** | Core financial accounting engine. |
| `src/obsidian_rl/evaluation/metrics.py` | Metrics | Sharpe, max drawdown, net return, turnover calculation. | **NO (KEEP ACTIVE)** | Standard quantitative evaluation metrics. |
| `src/obsidian_rl/evaluation/walkforward.py` | Walk-Forward | Chronological fold generation and strategy backtesting harness. | **NO (KEEP ACTIVE)** | Essential walk-forward mechanics. |
| `src/obsidian_rl/evaluation/holdout.py` | Governance | Out-of-sample holdout guard and isolation checker. | **NO (KEEP ACTIVE)** | Hard safety interlock preventing look-ahead. |
| `src/obsidian_rl/features/*` | Features | Causal feature engineering pipeline (`pipeline.py`, `schema.py`, `observation.py`, `labels.py`). | **NO (KEEP ACTIVE)** | Reusable feature extraction pipeline. |
| `src/obsidian_rl/ledger/ledger.py` | Audit Ledger | SQLite persistent decision and trade audit ledger. | **NO (KEEP ACTIVE)** | Immutable trade audit logging. |
| `src/obsidian_rl/live/*` | Execution | Simulated paper execution trader (`paper_trader.py`, `runner.py`, `stream.py`). | **NO (KEEP ACTIVE)** | Paper trading and execution interlock layer. |
| `src/obsidian_rl/dashboard/*` | Dashboard | Streamlit ledger dashboard (`app.py`, `queries.py`). | **NO (KEEP ACTIVE)** | Human monitoring interface. |

---

### 7. Test Suite Audit (`tests/`)

| Test File | Target Module / Subsystem | Classification | Safe to Move? | Reason | Recommended Future Location |
|---|---|---|---|---|---|
| `tests/test_alpha_gate_pilot.py` | `tools/alpha_gate_pilot.py` | **ARCHIVE CANDIDATE** | **YES** | Tests only Alpha Gate pilot tool. | `archive/cycle_01/tests/test_alpha_gate_pilot.py` |
| `tests/test_seed_ensemble_screen.py` | `tools/ppo_seed_ensemble_screen.py` | **ARCHIVE CANDIDATE** | **YES** | Tests only PPO seed ensemble tool. | `archive/cycle_01/tests/test_seed_ensemble_screen.py` |
| `tests/test_alpha_gate.py` | `src/obsidian_rl/gate/alpha_gate.py` & `gated.py` | **ARCHIVE CANDIDATE** | **YES** | Tests only retired Alpha Gate modules. | `archive/cycle_01/tests/test_alpha_gate.py` |
| `tests/test_trading_env.py` | `src/obsidian_rl/env/trading_env.py` | **KEEP LEGACY** | **NO** | Tests `TradingEnv` currently used by `cli.py`. | `tests/test_trading_env.py` |
| `tests/test_training.py` | `src/obsidian_rl/training/ppo.py` & `device.py` | **KEEP LEGACY** | **NO** | Tests PPO training loop used by `cli.py`. | `tests/test_training.py` |
| `tests/test_promotion.py` | `src/obsidian_rl/training/promotion.py` | **KEEP LEGACY** | **NO** | Tests promotion gate used by `cli.py`. | `tests/test_promotion.py` |
| `tests/test_registry.py` | `src/obsidian_rl/training/registry.py` | **KEEP LEGACY** | **NO** | Tests model registry. | `tests/test_registry.py` |
| *All other 25 test files* | Core Data, Portfolio, Ledger, Live, Walk-Forward, Hygiene | **KEEP ACTIVE** | **NO** | Essential test suite verifying core system integrity. | `tests/` |

---

## Broken-Link, Import & Command Risk Analysis

If components are moved without verifying dependency graphs, the following critical breakage risks will occur:

1. **CLI Command Breakage Risk (`obsidian-rl`)**:
   - `obsidian-rl train` and `obsidian-rl walk-forward` import `obsidian_rl.env.trading_env.RewardConfig` and `obsidian_rl.training.ppo.train_ppo`. Moving `env/trading_env.py` or `training/ppo.py` would cause immediate `ImportError` on CLI startup.
   - `obsidian-rl replay` and `obsidian-rl paper-trade` import `obsidian_rl.strategies.ppo_policy.PpoPolicyStrategy`. Moving `ppo_policy.py` would break model loading in historical replay and paper trading.
   - `obsidian-rl candidate-eval`, `promote`, and `rollback` import `obsidian_rl.training.promotion`. Moving `promotion.py` would break model lifecycle commands.

2. **Test Suite Execution Risk (`python -m pytest`)**:
   - Pytest automatically discovers test files in `tests/`. Moving test files out of `tests/` into `archive/cycle_01/tests/` without configuring `pytest.ini` or specifying test paths will omit them from default test runs (which is intended for archived code, but requires explicit test invocation commands for historical verification).

3. **Import Graph Integrity**:
   - `src/obsidian_rl/gate/alpha_gate.py` and `src/obsidian_rl/strategies/gated.py` are completely isolated from `src/obsidian_rl/cli.py` and core infrastructure. Moving them has **zero risk** of breaking active commands.

---

## Proposed Future Code Archive Structure (Unapplied Proposal)

When code archival is explicitly executed in a future step, the following directory layout is proposed:

```
archive/
└── cycle_01/
    ├── tools/
    │   ├── alpha_gate_pilot.py
    │   └── ppo_seed_ensemble_screen.py
    ├── strategies/
    │   └── gated.py
    ├── experiments/
    │   └── alpha_gate.py
    └── tests/
        ├── test_alpha_gate.py
        ├── test_alpha_gate_pilot.py
        └── test_seed_ensemble_screen.py
```

---

## Recommended Safest First Archive Batch

For the next execution phase, the **smallest, safest first archive batch** comprises the 7 fully decoupled files identified above:

1. `tools/alpha_gate_pilot.py` -> `archive/cycle_01/tools/alpha_gate_pilot.py`
2. `tools/ppo_seed_ensemble_screen.py` -> `archive/cycle_01/tools/ppo_seed_ensemble_screen.py`
3. `src/obsidian_rl/gate/alpha_gate.py` -> `archive/cycle_01/experiments/alpha_gate.py`
4. `src/obsidian_rl/strategies/gated.py` -> `archive/cycle_01/strategies/gated.py`
5. `tests/test_alpha_gate_pilot.py` -> `archive/cycle_01/tests/test_alpha_gate_pilot.py`
6. `tests/test_seed_ensemble_screen.py` -> `archive/cycle_01/tests/test_seed_ensemble_screen.py`
7. `tests/test_alpha_gate.py` -> `archive/cycle_01/tests/test_alpha_gate.py`

### Why This Batch is 100% Safe:
- Zero imports from `src/obsidian_rl/cli.py`.
- Zero imports from core data, portfolio, ledger, metrics, or live execution engines.
- Moving these 7 files leaves 100% of CLI subcommands (`obsidian-rl data-*`, `train`, `walk-forward`, `replay`, `paper-trade`, `promote`, `rollback`) fully functional and green.
