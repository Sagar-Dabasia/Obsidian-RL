# Phase 6: Strict Feature and Observation Schema Contract

## Executive Summary
We implemented a strict, centralized, and versioned feature and observation schema contract (`fs-v2`) inside `src/obsidian_rl/features/schema.py`. This contract eliminates scattered magic numbers, duplicate normalization definitions, and silent model migrations across the feature pipeline, observation assembly, environment, backtester, and gate evaluation.

## Key Changes
1. **Central Schema Contract (`src/obsidian_rl/features/schema.py`)**:
   - Defined `SCHEMA_VERSION = "fs-v2"`.
   - Created complete ordered descriptors for market features, formulas, lags, rolling windows (`96`), warm-up rows (`96`), clipping rules (`CLIP = 10.0`), portfolio bounds (`PORTFOLIO_BOUNDS`), and observation dimensions (`17`).
   - Implemented canonical JSON serialization (`_canonical_json` using sorted keys, compact separators, `allow_nan=False`) and lowercase 64-character SHA-256 computation (`schema_sha256()`).
   - Added `validate_fingerprint(stored)` to explicitly verify stored fingerprints against `SCHEMA_VERSION`, check for malformed hashes, verify descriptor/hash agreement, and ensure zero drift in constants, ordering, or normalization bounds.

2. **Feature Pipeline & Candle Validation (`src/obsidian_rl/features/pipeline.py`)**:
   - Refactored `pipeline.py` to import constants and feature lists from `schema.py`.
   - Implemented `validate_candle_frame(candles, expected_interval_ms=None)` to enforce strict candle requirements (DataFrame type, required columns `open_time`, `close_time`, `open`, `high`, `low`, `close`, `volume`, numeric dtype rejecting `bool` and non-numeric columns, `open_time` unique and strictly increasing, `close_time >= open_time`, positive finite OHLC, non-negative finite volume, and `high >= max(open, close)` / `low <= min(open, close)`).

3. **Observation Assembly (`src/obsidian_rl/features/observation.py`)**:
   - Added `validate_portfolio_obs(portfolio)` to ensure `PortfolioObs` fields are numeric (`not bool`), finite, and strictly within `PORTFOLIO_BOUNDS`.
   - Updated `build_observation(market_row, portfolio)` to validate inputs and emit a contiguous `float32` array of shape `(OBSERVATION_DIM,)` without any non-finite values.

4. **Environment & Backtest Alignment (`src/obsidian_rl/env/trading_env.py`, `src/obsidian_rl/evaluation/backtest.py`)**:
   - Updated `PortfolioFeatureTracker.observe` and `ROLLING_WINDOW` in `backtest.py` to use `PORTFOLIO_BOUNDS` from `schema.py`.
   - Updated `TradingEnv.observation_space` in `trading_env.py` to use `OBSERVATION_DIM` and `np.dtype(OBSERVATION_DTYPE)` from `schema.py`.

5. **Model & Gate Metadata Binding (`src/obsidian_rl/training/registry.py`, `src/obsidian_rl/gate/alpha_gate.py`)**:
   - Updated `load_record` in `registry.py` to run `validate_fingerprint(stored)` on model metadata.
   - Updated `save_gate` and `_load_and_validate_meta` in `alpha_gate.py` to bind `feature_schema` (containing the full descriptor plus SHA-256) and strictly validate it when loading text boosters.

## Verification
- Created `tests/test_observation.py` covering `PortfolioObs` bounds validation, non-numeric/bool rejection, and `build_observation` shape/contiguity checks.
- Created `tests/test_registry.py` covering model loading rejections across legacy versions, missing/extra schema fields, changed constants, reordered features, changed bounds, malformed SHA-256 hashes, and descriptor/hash disagreements.
- Updated `tests/test_features.py` and `tests/test_alpha_gate.py` with comprehensive candle validation and feature schema verification tests.
- Ran the full repository test suite: `python -m pytest -q` passed 340 tests (with 1 skipped for live test isolation).
