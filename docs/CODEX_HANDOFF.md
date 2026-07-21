# Codex handoff

Updated: 2026-07-21

## Current branch and commit
- Branch: `wip/phase4-holdout-enforcement`
- Starting commit: `30136da586f2723dcf930ed1a165f3a755cee1c9`

## Status
Phase 4 — Single-Use & Immutable Final Holdout Enforcement (`resolve_repo_root` path derivation, `HOLDOUT_SCHEMA_VERSION = 2`, strict 22-field state/report schema verification, deep state-vs-report cross validation, and `dataset_identity` / `report_sha256` integrity) — **COMPLETE (verified & ready to commit)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-21T135000Z-phase4-holdout-integrity.md](agent-runs/2026-07-21T135000Z-phase4-holdout-integrity.md)

## What was implemented/fixed in Phase 4 Holdout Enforcement
- **Strict Repository Anchoring (`holdout.py`)**:
  - Removed mutable module-level path override mechanisms (`HOLDOUT_DIR`, `HOLDOUT_STATE_PATH`, `HOLDOUT_LOCK_PATH`). `get_holdout_dir(repo_root=None)` now always returns `resolve_repo_root(repo_root) / "artifacts" / "holdout"`, ensuring state locking (`.holdout.lock`) and `HOLDOUT_STATE.json` are strictly anchored to the repository root regardless of current working directory (`os.chdir`).
- **Schema Version 2 & Strict Field Validation (`holdout.py`)**:
  - Bumped `HOLDOUT_SCHEMA_VERSION = 2`. Both `load_holdout_state` and `_verify_report_file` enforce exact allowed key sets without extra/unknown keys, canonical `UTC` timestamps ending in `Z` (`parse_utc_boundary`), strict boolean checks (`type(v) is bool`), finite floating-point checks (`math.isfinite`), non-empty unique strings for baselines, and exact allowed scenarios (`['base', 'costs2x', 'delay1']`).
- **Deep Report & State Integrity Verification (`holdout.py`)**:
  - `_verify_report_file` verifies that `report_sha256` matches both the expected hash and the dynamically recomputed SHA-256 of the report contents (`_compute_report_hash`).
  - `_verify_report_file` verifies `dataset_identity` dictionary fields against root metadata (`dataset_sha256`, `row_count`, `first_open_ms`, `last_open_ms`).
  - `_verify_report_file` wraps `_json_loads_strict` to catch `PromotionEvidenceError` (`or malformed JSON or non-finite numbers`) and cleanly raise `RuntimeError("holdout report non-finite or malformed JSON: ...")`.
  - When `status == "completed"`, `load_holdout_state` calls `_verify_report_file` and performs strict cross validation, ensuring all 13 bound metadata fields (`schema_version`, `consumption_id`, `model_id`, `model_artifact_sha256`, `feature_schema`, `source_commit`, `source_tree_clean`, `symbol`, `interval`, `reserved_start_utc`, `fixed_end_utc`, `costs`, `baselines`, `scenarios`) exactly match between state and report. Any mismatch raises `RuntimeError("report <field> does not match state")`.

## Files changed
- `src/obsidian_rl/evaluation/holdout.py`
- `tests/test_holdout.py`
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-21T135000Z-phase4-holdout-integrity.md`

## Verification Commands Run
- `python -m pytest tests/test_holdout.py -q`: **15 passed in 0.58s**.
- `python -m ruff check src/obsidian_rl/evaluation/holdout.py tests/test_holdout.py`: **All checks passed!**.
- `python -m ruff format --check src/obsidian_rl/evaluation/holdout.py tests/test_holdout.py`: **Clean (already formatted)**.
- `python -m mypy src`: **Success (no issues found in 45 source files)**.
- `python -m compileall -q src tests`: **Clean**.
- `git diff --check`: **Clean**.
- `python -m pytest -q`: **271 passed, 1 skipped in 5.34s**.
