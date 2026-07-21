# Phase 6: Feature Validation Wiring & Schema Immutability

## Executive Summary
We finalized the Phase 6 validation wiring and schema immutability across `src/obsidian_rl/features/schema.py` and `src/obsidian_rl/features/pipeline.py`.

## Key Improvements
1. **Validation Wiring**:
   - `compute_market_features` invokes `validate_candle_frame` prior to column access or computation.
   - Optional `expected_interval_ms` parameter supported across `compute_market_features` and `feature_matrix`.
   - `expected_interval_ms` validated as `int > 0` (excluding `bool`) even on single-row frames.
   - `feature_matrix` guarantees contiguous C-order `float32` matrix and `int64` timestamp array, with explicit non-finite rejection.

2. **Schema Immutability**:
   - Dict constants wrapped in `MappingProxyType`.
   - `schema_descriptor()` and `schema_fingerprint()` return independent `deepcopy` structures.
   - In-place mutation of returned descriptors or fingerprints does not alter future calls, SHA-256 hashes, or runtime observation behavior.
