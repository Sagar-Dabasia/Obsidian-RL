# Agent Run Report — Phase 6: Strict Feature and Observation Schema Contract

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase6-schema-contract` |
| **Starting commit** | `0748c4aa219274c561ee4a3516eca7761e2f0a6b` |
| **Task** | Phase 6 — Create strict feature and observation schema contract (`fs-v2`) inside `schema.py`, refactor `pipeline.py`, `observation.py`, `backtest.py`, `registry.py`, `alpha_gate.py`, and `trading_env.py`, enforcing candle and schema fingerprint validation across the repository. |

---

## Working-tree status

**Before**: clean on `wip/phase6-schema-contract` at `0748c4aa219274c561ee4a3516eca7761e2f0a6b`

**After**:
```
M  src/obsidian_rl/env/trading_env.py
M  src/obsidian_rl/evaluation/backtest.py
M  src/obsidian_rl/features/observation.py
M  src/obsidian_rl/features/pipeline.py
A  src/obsidian_rl/features/schema.py
M  src/obsidian_rl/gate/alpha_gate.py
M  src/obsidian_rl/training/registry.py
M  tests/test_alpha_gate.py
M  tests/test_features.py
A  tests/test_observation.py
M  tests/test_observation_parity.py
A  tests/test_registry.py
M  tests/test_training.py
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
A  docs/agent-runs/2026-07-21T170000Z-phase6-schema-contract.md
```

---

## Fixes & Implementation

### 1. `src/obsidian_rl/features/schema.py` (New)
- `SCHEMA_VERSION = "fs-v2"`.
- Defined complete ordered schema descriptors for market features (`MARKET_FEATURES`), formulas (`MARKET_FEATURE_FORMULAS`), lags (`LOG_RETURN_LAGS`), rolling windows (`96`), warm-up rows (`96`), clipping bounds (`CLIP = 10.0`), portfolio features (`PORTFOLIO_FEATURES`), portfolio normalization bounds (`PORTFOLIO_BOUNDS`), and observation properties (`OBSERVATION_DIM = 17`, `OBSERVATION_DTYPE = "float32"`).
- Serializes `schema_descriptor()` with canonical sorted-keys compact JSON (`allow_nan=False`) and computes lowercase 64-character SHA-256 (`schema_sha256()`).
- `validate_fingerprint(stored)` strictly verifies stored fingerprints against legacy versions, malformed hashes, missing/extra fields, descriptor/hash disagreements, reordered features, and changed constants/bounds.

### 2. `src/obsidian_rl/features/pipeline.py`
- Re-exports schema constants and definitions from `schema.py`.
- `validate_candle_frame(candles)` enforces schema rules: required columns exactly once, numeric (`not bool`) dtypes for OHLCV, strictly increasing unique `open_time`, `close_time >= open_time`, positive finite prices (`high >= max(open, close)`, `low <= min(open, close)`), and non-negative finite volume.

### 3. `src/obsidian_rl/features/observation.py`
- Re-exports `PortfolioObs` and observation definitions from `schema.py`.
- Added `validate_portfolio_obs(portfolio)` to reject boolean, non-finite, or out-of-bounds `PortfolioObs` values.
- `build_observation(market_row, portfolio)` validates inputs and emits a contiguous 1D `float32` array of exactly `(OBSERVATION_DIM,)` without any non-finite values.

### 4. `src/obsidian_rl/evaluation/backtest.py` & `src/obsidian_rl/env/trading_env.py`
- Replaced hardcoded normalization/clipping constants (`ROLLING_WINDOW = 96` and `[-3.0, 3.0, 10]`) with `PORTFOLIO_BOUNDS` from `schema.py`.
- Updated `observation_space` to bind explicitly to `OBSERVATION_DIM` and `np.dtype(OBSERVATION_DTYPE)` from `schema.py`.

### 5. `src/obsidian_rl/training/registry.py` & `src/obsidian_rl/gate/alpha_gate.py`
- Updated `load_record` in `registry.py` to run `validate_fingerprint(stored)` when loading `feature_schema`.
- Updated `save_gate` and `_load_and_validate_meta` in `alpha_gate.py` to include `feature_schema` in `_REQUIRED_META_KEYS` and validate it against the exact `fs-v2` schema contract.

---

## Verification Results

### Focused Tests
```
python -m pytest tests/test_features.py tests/test_observation.py tests/test_registry.py tests/test_alpha_gate.py tests/test_observation_parity.py -q
........................................................................................... [100%]
91 passed
```

### Full Suite
```
python -m pytest -q
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
.....................................................................s.. [ 84%]
.....................................................                    [100%]
340 passed, 1 skipped
```
