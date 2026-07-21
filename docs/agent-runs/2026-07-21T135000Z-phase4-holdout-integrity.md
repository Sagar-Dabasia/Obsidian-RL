# Agent Run Report — Phase 4: Single-Use & Immutable Final Holdout Enforcement

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase4-holdout-enforcement` |
| **Starting commit** | `30136da586f2723dcf930ed1a165f3a755cee1c9` |
| **Task** | Phase 4 Single-Use & Immutable Final Holdout Enforcement (`resolve_repo_root` path derivation, `HOLDOUT_SCHEMA_VERSION = 2`, strict 22-field state/report schema verification, deep state-vs-report cross validation, and `dataset_identity` / `report_sha256` integrity) |

---

## Working-tree status

**Before**:
```
git status --short
(clean at commit 30136da586f2723dcf930ed1a165f3a755cee1c9 on branch wip/phase4-holdout-enforcement)
```

**After** (this session, allowed source/test files and docs):
```
 M docs/AGENT_RUN_REPORT.md
 M docs/CODEX_HANDOFF.md
?? docs/agent-runs/2026-07-21T135000Z-phase4-holdout-integrity.md
 M src/obsidian_rl/evaluation/holdout.py
 M tests/test_holdout.py
```

---

## Files inspected & modified

### Production Files Modified
- `src/obsidian_rl/evaluation/holdout.py`

### Test Files Modified
- `tests/test_holdout.py`

---

## Defects & Resolution Summary

### Problem — Mutable holdout paths, schema bypass, and weak report verification
- **Root cause**:
  1. `artifacts/holdout` path derivation previously relied on mutable runtime overrides (`HOLDOUT_DIR`, `HOLDOUT_STATE_PATH`, `HOLDOUT_LOCK_PATH`) or relative paths based on `process.cwd()`, allowing holdout state bypass or path traversal.
  2. `HOLDOUT_STATE.json` and report files lacked strict schema versioning (`schema_version = 2`) and thorough validation across all 22 required metadata fields.
  3. Report verification did not verify canonical timestamps, lowercase 64-char SHA-256 hashes (`report_sha256`, `dataset_sha256`, `model_artifact_sha256`), lowercase 40-char commit SHAs (`source_commit`), strict boolean `source_tree_clean=True`, exact metric fields (`net_return`, `sharpe`, `max_drawdown`, `turnover`, `trade_count`), and exact state-vs-report agreement across all bound configuration fields (`consumption_id`, `model_id`, `model_artifact_sha256`, `feature_schema`, `source_commit`, `source_tree_clean`, `symbol`, `interval`, `reserved_start_utc`, `fixed_end_utc`, `costs`, `baselines`, `scenarios`).
- **Resolution**:
  - **Strict Repository Anchoring**: Removed mutable module-level path override mechanisms (`HOLDOUT_DIR`, `HOLDOUT_STATE_PATH`, `HOLDOUT_LOCK_PATH`). `get_holdout_dir(repo_root=None)` now always returns `resolve_repo_root(repo_root) / "artifacts" / "holdout"`, ensuring state locking (`.holdout.lock`) and `HOLDOUT_STATE.json` are strictly anchored to the repository root regardless of current working directory (`os.chdir`).
  - **Schema Version 2 & Strict Field Validation**: Bumped `HOLDOUT_SCHEMA_VERSION = 2`. Both `load_holdout_state` and `_verify_report_file` enforce exact allowed key sets without extra/unknown keys, canonical `UTC` timestamps ending in `Z` (`parse_utc_boundary`), strict boolean checks (`type(v) is bool`), finite floating-point checks (`math.isfinite`), non-empty unique strings for baselines, and exact allowed scenarios (`['base', 'costs2x', 'delay1']`).
  - **Deep Report & State Integrity Verification**:
    - `_verify_report_file` verifies that `report_sha256` matches both the expected hash and the dynamically recomputed SHA-256 of the report contents (`_compute_report_hash`).
    - `_verify_report_file` verifies `dataset_identity` dictionary fields against root metadata (`dataset_sha256`, `row_count`, `first_open_ms`, `last_open_ms`).
    - `_verify_report_file` wraps `_json_loads_strict` to catch `PromotionEvidenceError` (`or malformed JSON or non-finite numbers`) and cleanly raise `RuntimeError("holdout report non-finite or malformed JSON: ...")`.
    - When `status == "completed"`, `load_holdout_state` calls `_verify_report_file` and performs strict cross validation, ensuring all 13 bound metadata fields (`schema_version`, `consumption_id`, `model_id`, `model_artifact_sha256`, `feature_schema`, `source_commit`, `source_tree_clean`, `symbol`, `interval`, `reserved_start_utc`, `fixed_end_utc`, `costs`, `baselines`, `scenarios`) exactly match between state and report. Any mismatch raises `RuntimeError("report <field> does not match state")`.

---

## Verification Results

### Focused Unit Tests (`tests/test_holdout.py`)
```
python -m pytest tests/test_holdout.py -q
............... [100%]
15 passed in 0.58s
```

### Ruff Linter & Formatting
```
python -m ruff check src/obsidian_rl/evaluation/holdout.py tests/test_holdout.py
All checks passed!

python -m ruff format --check src/obsidian_rl/evaluation/holdout.py tests/test_holdout.py
2 files already formatted
```

### Mypy Static Type Checking
```
python -m mypy src
Success: no issues found in 45 source files
```

### Compileall & Git Whitespace Check
```
python -m compileall -q src tests
git diff --check
(clean)
```

### Complete Test Suite
```
python -m pytest -q
........................................................................ [ 26%]
........................................................................ [ 53%]
........................................................................ [ 79%]
........s..............................................                  [100%]
271 passed, 1 skipped in 5.34s
```
