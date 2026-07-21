# Codex handoff

Updated: 2026-07-21

## Current branch and commit
- Branch: `wip/phase6-schema-contract`
- Starting commit: `0748c4aa219274c561ee4a3516eca7761e2f0a6b`

## Status
Phase 6 — Strict Feature and Observation Schema Contract — **COMPLETE (verified)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-21T170000Z-phase6-schema-contract.md](agent-runs/2026-07-21T170000Z-phase6-schema-contract.md)

## What was implemented in Phase 6

### `src/obsidian_rl/features/schema.py` (New)
- Created explicit versioned schema descriptor (`fs-v2`) binding candle requirements, market features, stable formulas, lags, rolling windows (`96`), warm-up rows (`96`), clipping rules (`CLIP = 10.0`), portfolio features, bounds (`PORTFOLIO_BOUNDS`), and observation properties (`OBSERVATION_DIM = 17`, `float32`).
- Serializes canonically via sorted-keys compact JSON (`allow_nan=False`) and computes lowercase 64-character SHA-256 (`schema_sha256()`).
- Added `validate_fingerprint(stored)` to explicitly reject legacy versions, missing/extra fields, malformed hashes, descriptor/hash disagreement, reordered features, and altered constants/bounds.

### `src/obsidian_rl/features/pipeline.py` & `src/obsidian_rl/features/observation.py`
- Implemented `validate_candle_frame(candles)` to enforce schema constraints on candle DataFrames before feature computation (checking required columns, numeric dtypes not bool, strictly increasing unique time, `close_time >= open_time`, finite positive prices, finite non-negative volume, and `high >= max(open, close)` / `low <= min(open, close)`).
- Added `validate_portfolio_obs(portfolio)` and hardened `build_observation(market_row, portfolio)` to guarantee exact shape `(OBSERVATION_DIM,)` contiguous `float32` arrays with zero non-finite values.

### `src/obsidian_rl/evaluation/backtest.py` & `src/obsidian_rl/env/trading_env.py`
- Removed duplicated hardcoded constants, importing `PORTFOLIO_BOUNDS`, `OBSERVATION_DIM`, and `OBSERVATION_DTYPE` from `schema.py`.

### `src/obsidian_rl/training/registry.py` & `src/obsidian_rl/gate/alpha_gate.py`
- Updated model and gate metadata saving/loading (`load_record`, `save_gate`, `_load_and_validate_meta`) to bind the complete schema fingerprint and reject incompatibilities using `validate_fingerprint`.

## Files changed / created
- `src/obsidian_rl/env/trading_env.py`
- `src/obsidian_rl/evaluation/backtest.py`
- `src/obsidian_rl/features/observation.py`
- `src/obsidian_rl/features/pipeline.py`
- `src/obsidian_rl/features/schema.py` (New)
- `src/obsidian_rl/gate/alpha_gate.py`
- `src/obsidian_rl/training/registry.py`
- `tests/test_alpha_gate.py`
- `tests/test_features.py`
- `tests/test_observation.py` (New)
- `tests/test_observation_parity.py`
- `tests/test_registry.py` (New)
- `tests/test_training.py`
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-21T170000Z-phase6-schema-contract.md` (New)

## Verification
- Focused tests (`pytest tests/test_features.py tests/test_observation.py tests/test_registry.py tests/test_alpha_gate.py tests/test_observation_parity.py -q`): **91 passed**
- Full suite (`pytest -q`): **340 passed, 1 skipped**
