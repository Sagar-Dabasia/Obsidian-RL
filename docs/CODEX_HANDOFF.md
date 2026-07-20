# Codex handoff

Updated: 2026-07-20

## Current branch and commit
- Branch: `wip/phase1-review`
- Commit: `5fb2868caa96fb50f781fec62167a670f2ada19e` (working tree — uncommitted Phase 1 patch including final integrity corrections)

## Status
Phase 1 model-lifecycle integrity & correctness corrections — **COMPLETE (verified, uncommitted)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-20T163000Z-phase1-integrity-final.md](agent-runs/2026-07-20T163000Z-phase1-integrity-final.md)

## What was fixed in this session (Final Phase 1 Integrity Corrections — Defects 1–6)
- **Defect 1 (`ppo.py`)**: Called `validate_model_id(model_id)` inside `train_ppo` before constructing any paths or directories (`models_dir / model_id`), blocking `../` traversal outside `models_dir` and preventing creation of Windows reserved device names (`CON`, `NUL`, etc.).
- **Defect 2 & 3 (`registry.py`)**: `register_model()` requires a clean working tree (`get_git_source_state().is_clean == True`) and a valid 40-character hex commit, recording exact `"training_source_git_commit"` and `"training_source_tree_clean": True` in `metadata.json`. `load_record()` enforces strict matching between `metadata["model_id"]` and directory name (`Path(model_dir).name`), confirms root JSON schema structure, and validates `"artifact_sha256"` without fallback.
- **Defect 4 (`costs.py`)**: Added `__post_init__()` to `CostModel` raising `ValueError` on boolean (`isinstance(value, bool)`) or non-finite (`not math.isfinite(value)`) parameter inputs (`taker_fee`, `half_spread`, `slippage`).
- **Defect 5 & 6 (`promotion.py`)**:
  - Implemented `.champion.lock` (`_champion_lock(models_dir)`) atomic cross-process lock around all `promote()` and `rollback()` invocations.
  - Bumped `EVALUATION_REPORT_SCHEMA_VERSION = 2`, enforcing `math.isfinite()` on all evaluation metrics and threshold values. Added `PromotionThresholds.__post_init__` checks rejecting boolean and non-finite inputs or invalid range limits (`max_drawdown_limit` outside `[0, 1]`).
  - Added strict symlink containment verification (`is_symlink()`) across `_load_and_verify_latest_pointer` and `_get_latest_report_path`.
  - Added Git provenance cross-checking: `evaluate_candidate` records `evaluation_source_git_commit` (40-char hex) and `evaluation_source_tree_clean: True`. `promote()` enforces that candidate evaluation commit matches both the current project commit and the original candidate training commit (`_check_training_provenance`).

## Files changed (Final Phase 1 Integrity Corrections)
- `src/obsidian_rl/training/ppo.py`
- `src/obsidian_rl/portfolio/costs.py`
- `src/obsidian_rl/training/registry.py`
- `src/obsidian_rl/training/promotion.py`
- `tests/test_costs.py`
- `tests/test_training.py`
- `tests/test_promotion.py`
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-20T163000Z-phase1-integrity-final.md`

## Verification Commands Run
- `python -m pytest tests/test_promotion.py tests/test_training.py tests/test_costs.py -q`: **83 passed, 1 skipped**, 0 failed.
- `python -m pytest -q` (full suite across project): **214 passed, 1 skipped in 49s**, 0 failed.
- `python -m compileall -q src tests`: **Clean (0 errors)**.
- `git diff --check`: **Clean (0 whitespace errors)**.
- `git status --short`: Verified only allowed production/test files and documentation changed.

## Open risks
1. **Windows NTFS `os.replace` Across Volumes**: `os.replace` is atomic on local NTFS volumes, but across network shares or different drive mounts, atomicity guarantees depend on filesystem driver support.
2. **Backward Compatibility of `metadata.json` Promotion Status**: `metadata.json` is no longer mutated during `promote()` or `rollback()`. External observers relying on `metadata.json` `promotion` field instead of `CHAMPION.json` will read `"candidate"`.

## Next steps
Review and commit the Phase 1 working-tree patch when explicitly requested by user.
