# Codex handoff

Updated: 2026-07-21

## Current branch and commit
- Branch: `wip/phase6-schema-contract`
- Starting commit: `69ced4b6bbf2516ae87e5b2c32a0dbb13fe8ac4e`

## Status
Phase 6 Validation Wiring & Schema Immutability — **COMPLETE (verified)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-21T190000Z-phase6-validation-wiring.md](agent-runs/2026-07-21T190000Z-phase6-validation-wiring.md)

## What was implemented in Phase 6 Validation Wiring
- `compute_market_features` calls `validate_candle_frame` prior to reading columns or computing features.
- Optional `expected_interval_ms` added to `compute_market_features` and `feature_matrix`.
- Strict validation of `expected_interval_ms` (`int > 0`, non-bool) on all frames.
- Single-pass validation in `feature_matrix` with contiguous float32/int64 array guarantees and non-finite rejection.
- Dict constants protected with `MappingProxyType` and independent deep-copy returned by `schema_descriptor()` and `schema_fingerprint()`.

## Verification
- Focused tests (`pytest tests/test_features.py tests/test_registry.py tests/test_observation.py -q`): **28 passed**
- Full suite (`pytest -q`): **344 passed, 1 skipped**
- `compileall`, `mypy`, `ruff check`, `ruff format --check`, `git diff --check`: **All clean**
