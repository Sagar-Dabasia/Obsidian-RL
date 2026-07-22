# Codex handoff

Updated: 2026-07-22

## Current branch and commit
- Branch: `research/nested-walkforward-protocol`
- Starting commit: `8de572c9b843e937e96a70822365b354f84331b1`

## Status
PPO Walk-Forward Research Protocol Hardening — **COMPLETE (verified)**

See full readiness agent run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)

## What was verified in the Walk-Forward Protocol Hardening
- **Outer Validation Leakage Eliminated**: Implemented nested chronological folds (`train` -> `purge_1` -> `inner_eval` -> `purge_2` -> `outer_val`) with `--inner-eval-days` (default `60`). PPO training and checkpoint selection (`EvalCallback`) receive only `(train, inner_eval)`. `outer_val` is isolated strictly for final strategy comparison (`evaluate_strategies_on_slice`).
- **Reproducible Fold Evidence & Rejections**: `FoldSpec` now persists exact start/end ms boundaries, actual row counts, typed SHA-256 slice identities (`slice_sha256`), and exact durations for all 5 slices. Added strict rejections for empty slices, overlapping bounds, purge gap mismatches (`rows != WARMUP_ROWS`), rows outside declared bounds, and `outer_val` touching holdout (`get_holdout_start_ms()`).
- **Collision-Resistant Experiment IDs & Multi-Seed Tracking**: Generated unique `experiment_id` (`wf-{stamp}-{us:06d}-{uuid.hex[:8]}`) used across artifact filenames, candidate model IDs (`{experiment_id}-f{fold_id}-s{seed}`), and `metadata.json` (`inner_eval_start_ms` / `inner_eval_end_ms`), preventing collisions and overwrites across reruns while storing complete Git state, cost models, seeds, and fold definitions.

## Verification Commands & Status
- `python -m pytest -q`: **398 passed, 1 skipped (100% pass across entire repository)**
- `python -m pytest tests/test_walkforward.py -q`: **7 passed (verified all 10 required proof properties)**

## Verdict
READY FOR CONTROLLED HISTORICAL TRAINING
