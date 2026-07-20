# Codex handoff

Updated: 2026-07-20

## Current branch and commit
- Branch: `wip/phase1-review`
- Commit: `f09843fcd582ba367c6200d528f801967e9ffbed` (working tree — Phase 1 model-lifecycle patch including registered model immutability enforcement)

## Status
Phase 1 model-lifecycle integrity & registered model immutability enforcement — **COMPLETE (verified)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-20T201600Z-enforce-immutable-registered-models.md](agent-runs/2026-07-20T201600Z-enforce-immutable-registered-models.md)

## What was fixed in this session (Enforce Immutable Registered Model IDs)
- **`train_ppo` Immutability & Collision Resistance (`ppo.py`)**:
  - Automatically generated `model_id`s now include microsecond precision and an 8-character random UUID fragment (`f"ppo-{time.strftime('%Y%m%d-%H%M%S')}-{us:06d}-seed{cfg.seed}-{uuid.uuid4().hex[:8]}"`).
  - `model_dir` is created exclusively via `model_dir.mkdir(parents=False, exist_ok=False)` after checking parent directory existence (`parents=True, exist_ok=True` on `models_dir`). If `model_dir` already exists (as a directory, empty folder, or file), `train_ppo` immediately raises `FileExistsError("model directory ... already exists; refusing to reuse or overwrite")` before touching or deleting anything inside it.
  - When `resume_from` is supplied, `train_ppo` checks that the new output `model_id` / directory does not equal `resume_from`, ensuring resumed runs never overwrite their parent model directory.
- **`register_model` Exclusive Creation & Immutability (`registry.py`)**:
  - Checked `(model_dir / METADATA_FILE).exists()` upfront immediately after validating `model_id` and paths.
  - Wrote `metadata.json` exclusively using `open(meta_path, "xb")` with explicit `flush()` and `os.fsync()`. If `metadata.json` already exists, `FileExistsError` is raised with a clear diagnostic and existing `model.zip` and `metadata.json` remain byte-for-byte unchanged.

## Files changed (Immutable Registered Model IDs)
- `src/obsidian_rl/training/ppo.py`
- `src/obsidian_rl/training/registry.py`
- `tests/test_training.py`
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-20T201600Z-enforce-immutable-registered-models.md`

## Verification Commands Run
- `python -m pytest tests/test_training.py tests/test_promotion.py -q`: **81 passed, 1 skipped**, 0 failed.
- `python -m pytest -q` (full suite across project): **215 passed, 1 skipped in 49s**, 0 failed.
- `python -m compileall -q src tests`: **Clean (0 errors)**.
- `git diff --check`: **Clean (0 whitespace errors)**.
- `python -m ruff check src tests` / `python -m ruff format --check src tests` / `python -m mypy src`: **BLOCKED (modules missing from environment)**.

## Open risks
1. **Windows NTFS `os.replace` Across Volumes**: `os.replace` is atomic on local NTFS volumes, but across network shares or different drive mounts, atomicity guarantees depend on filesystem driver support.

## Next steps
Review and commit the Phase 1 working-tree patch when requested by user.
