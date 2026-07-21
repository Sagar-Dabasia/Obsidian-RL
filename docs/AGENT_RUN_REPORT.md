# Agent Run Report — Phase 6: Feature Validation Wiring & Immutability

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase6-schema-contract` |
| **Starting commit** | `69ced4b6bbf2516ae87e5b2c32a0dbb13fe8ac4e` |
| **Task** | Finalize Phase 6 validation wiring: feature calculation candle validation in `compute_market_features`, interval validation, single-pass validation in `feature_matrix`, output contiguity/dtype/finite guarantees, and schema descriptor/fingerprint deepcopy immutability. |

---

## Working-tree status

**Before**: clean on `wip/phase6-schema-contract` at `69ced4b6bbf2516ae87e5b2c32a0dbb13fe8ac4e`

**After**:
```
M  src/obsidian_rl/env/trading_env.py
M  src/obsidian_rl/features/pipeline.py
M  src/obsidian_rl/features/schema.py
M  tests/test_features.py
M  tests/test_registry.py
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
A  docs/agent-runs/2026-07-21T190000Z-phase6-validation-wiring.md
```

---

## Fixes & Implementation

### 1. `compute_market_features` & `feature_matrix` Validation Wiring (`pipeline.py`)
- `compute_market_features` now calls `validate_candle_frame(candles, expected_interval_ms=expected_interval_ms)` as its first action before reading any columns or performing calculations.
- Added optional `expected_interval_ms` parameter to `compute_market_features` and `feature_matrix`.
- Validated `expected_interval_ms` as `int` > 0 (rejecting `bool`, negative, zero, or float values even for a 1-row DataFrame).
- `feature_matrix` delegates candle validation to `compute_market_features` to avoid double validation.
- `feature_matrix` guarantees exact output shape, contiguous C-order `float32` feature matrix, contiguous C-order `int64` timestamps, exact row alignment, and explicitly rejects any post-warmup NaN or infinity.

### 2. Schema Contract Immutability (`schema.py`)
- Wrapping dict constants (`MARKET_FEATURE_FORMULAS`, `PORTFOLIO_BOUNDS`, `CANDLE_VALIDATION_RULES`) in `MappingProxyType` to prevent accidental in-place mutation.
- `schema_descriptor()` and `schema_fingerprint()` now return deep-copied, fully independent data structures.
- Mutating any nested list or dictionary returned by `schema_descriptor()` or `schema_fingerprint()` does not alter subsequent schema outputs, SHA-256 hashes, feature order, bounds, or observation behavior.

---

## Verification Results

### Focused Tests
```
python -m pytest tests/test_features.py tests/test_registry.py tests/test_observation.py -q
............................ [100%]
28 passed
```

### Full Suite
```
python -m pytest -q
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 62%]
........................................................................ [ 82%]
...s.......................................................              [100%]
344 passed, 1 skipped
```

### Static Analysis & Linting
```
python -m compileall -q src tests                            -> clean
python -m mypy src                                          -> Success: 46 source files
python -m ruff check src/... tests/...                       -> All checks passed!
python -m ruff format --check src/... tests/...              -> 4 files already formatted
git diff --check                                             -> clean
```
