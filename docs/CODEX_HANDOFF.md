# Codex handoff

Updated: 2026-07-20

## Current branch and commit
- Branch: `master`
- Commit: `4295f70a31248083a2166e95267b2d5ed666f049` (working tree — uncommitted Phase 1 patch)

## Status
Phase 1 model-lifecycle integrity & correctness defects — **COMPLETE (verified, uncommitted)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-20T150000Z-phase1-defects1-7.md](agent-runs/2026-07-20T150000Z-phase1-defects1-7.md)

## What was fixed in this session (Defects 1–7)
- **Defect 1**: Strict `CHAMPION.json` validation via `validate_champion_state()` (`schema_version == 1`, `generation` non-negative integer, strict `lineage` invariants without duplicates, and exact 64-char lowercase `model_artifact_sha256` checked against `model.zip` on disk). Added explicit `normalize_legacy_champion_state()` to safely back-fill legacy files without data loss.
- **Defect 2**: `promote` and `rollback` check candidate absence from lineage history (unless restoring current champion), increment `generation` count by 1, and write exact lowercase `model_artifact_sha256` to `CHAMPION.json`.
- **Defect 3**: `_load_evaluation_report` cross-verifies model ID and artifact checksums against `latest.json` pointer and embedded/disk SHA-256 values before returning evidence. `evaluation_report_path()` rejects corrupted pointers without fallback.
- **Defect 4**: Immutable evaluation reports (`evaluations/<id>-<ts>-<hash>.json`) are written exclusively via `_write_exclusive_file()` (`open(path, "xb")` + flush + fsync), raising `PromotionEvidenceError` on collision.
- **Defect 5**: `evaluate_candidate` checks `get_git_source_state()`, enforces `is_clean == True`, and records exact `source_git_commit` and `source_tree_clean=True` in every report. `_validate_evaluation_report` rejects any report without `source_tree_clean=True`.
- **Defect 6**: Created `validate_model_id()` in `registry.py` verifying canonical safe IDs (`_SAFE_ID_REGEX`), blocking path traversal (`/`, `\`, `..`), rejecting leading/trailing dots/hyphens/underscores, and blocking Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`). Enforced across `register_model()` and `load_record()`.
- **Defect 7**: Added `_evaluation_lock(models_dir, candidate_id)` (`.eval.lock` via `"xb"` cross-process lock) around all evaluations (`evaluate_candidate`), preventing concurrent evaluations or pointer collisions.

## Files changed (Phase 1 cumulative)
- `src/obsidian_rl/cli.py`
- `src/obsidian_rl/training/ppo.py`
- `src/obsidian_rl/training/promotion.py`
- `src/obsidian_rl/training/registry.py`
- `tests/test_promotion.py`
- `tests/test_training.py`
- `tests/__init__.py`

## Verification Commands Run
- `python -m pytest tests/test_promotion.py tests/test_training.py -q`: **74 passed**, 0 failed.
- `python -m pytest -q` (full suite): **207 passed in 49s**, 0 failed.
- `python -m compileall -q src tests`: **0 errors**.
- `python -m ruff check src/obsidian_rl/training/promotion.py src/obsidian_rl/training/registry.py tests/test_promotion.py`: **All checks passed**.
- `python -m ruff format --check src/obsidian_rl/training/promotion.py src/obsidian_rl/training/registry.py tests/test_promotion.py`: **Clean (already formatted)**.
- `python -m mypy src`: **Success: no issues found in 44 source files**.
- `git status --short`: Verified only allowed source/test files and documentation changed.

## Open risks
1. **Windows NTFS `os.replace` Across Volumes**: `os.replace` is atomic on local NTFS volumes, but across network shares or different drive mounts, atomicity guarantees depend on filesystem driver support.
2. **Backward Compatibility of `metadata.json` Promotion Status**: `metadata.json` is no longer modified during `promote()` or `rollback()`. External monitors relying on `metadata.json` `promotion` field instead of `CHAMPION.json` will read `"candidate"`.

## Next steps
Review and commit the Phase 1 working-tree patch (`git add` and `git commit` as per repository rules when requested by user).
