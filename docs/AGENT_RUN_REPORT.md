# Agent Run Report — Nested Chronological Walk-Forward Research Protocol

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-22 |
| **Branch** | `research/nested-walkforward-protocol` |
| **Starting commit** | `8de572c9b843e937e96a70822365b354f84331b1` |
| **Task** | Harden the PPO walk-forward research protocol with nested chronological folds, exact reproducible fold evidence (typed SHA-256 identities), collision-resistant experiment IDs, and multi-seed candidate tracking before any PPO experiment. |

---

## Working-tree status

```
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
M  src/obsidian_rl/cli.py
M  src/obsidian_rl/evaluation/walkforward.py
M  src/obsidian_rl/training/ppo.py
M  tests/test_walkforward.py
```

---

## Protocol & Verification Summary

### Problem 1 — Outer Validation Leakage Eliminated
- Implemented nested chronological folds separated by two equal `WARMUP_ROWS` purge gaps:
  `train` -> `purge_1` -> `inner_eval` -> `purge_2` -> `outer_val`
- Added `--inner-eval-days` parameter (default `60` days) to `walk-forward` CLI command.
- PPO `train_ppo` and `TrackingEvalCallback` now receive only `(train, inner_eval)`. Outer validation candles (`outer_val`) are strictly isolated and never passed to `train_ppo`, `EvalCallback`, model fitting, threshold selection, or checkpoint selection.
- Baselines (`AlwaysFlat`, `BuyAndHold`, `ThresholdMomentum`) and frozen PPO checkpoints (`PpoPolicyStrategy.from_dir`) are evaluated on identical `outer_val` slices under identical costs (`CostModel`), scenarios (`base`, `costs2x`, `delay1`), and timing.

### Problem 2 — Reproducible Fold Evidence & Rejections
- `FoldSpec` now persists exact millisecond boundaries, actual row counts (`rows`), typed SHA-256 slice identities (`sha256`), and exact durations for all five segments (`train`, `purge_1`, `inner_eval`, `purge_2`, `outer_val`) via `populate_and_validate()`.
- Computed `slice_sha256(df)` digests cover all dataframe column names, dtypes, and exact binary numpy data, guaranteeing that hashes change if any row, column, or price changes.
- Added explicit rejections for: empty slices across declared boundaries, overlapping intervals, purge gap size mismatches (`rows != WARMUP_ROWS`), rows outside declared intervals, and any `outer_val` candle at or after the central reserved holdout boundary (`get_holdout_start_ms()`).
- Documented boundary inclusiveness (`open_time >= start_ms and open_time <= end_ms`) directly in the artifact payload (`boundaries_description`).

### Problem 3 — Collision-Resistant Experiment IDs & Multi-Seed Tracking
- Created deterministic, collision-resistant walk-forward experiment IDs (`wf-{stamp}-{us:06d}-{uuid.uuid4().hex[:8]}`).
- Used `experiment_id` in artifact filenames (`{experiment_id}.json` / `.csv`), trained PPO candidate directories (`{experiment_id}-f{fold_id}-s{seed}`), and inside `metadata.json` (`data_info` recording `inner_eval_start_ms`, `inner_eval_end_ms`, and `n_inner_eval_candles`).
- Verified that reruns never overwrite or collide with earlier models or reports (`FileExistsError` enforced).
- Stored source Git commit (`git_commit`), clean-tree status (`git_is_clean`), dirty paths (`dirty_paths`), feature schema fingerprint (`schema_fingerprint()`), cost model dict, seeds list, timesteps, `n_envs`, and complete `FoldSpec` definitions (`fold_specs`) in every walk-forward artifact.

---

## Verification Results

### Audit Verification Commands
```
python -m pytest -q                                          -> 398 passed, 1 skipped (100% pass)
python -m pytest tests/test_walkforward.py -q               -> 7 passed in <1s (all 10 proof items verified)
```

### Final Verdict
READY FOR CONTROLLED HISTORICAL TRAINING
