# Task Scope Sentinel Hardening

## Problem Solved

The original `task_scope_sentinel.py` had three critical fail-open defects:

1. **Git failure swallowing** — `get_git_status()` caught `RuntimeError` from failed `git diff` / `git ls-files` calls and returned partial results instead of propagating failure.

2. **Baseline disappearance ignored** — Deleted fingerprinted baseline files were silently ignored (treated as no-change).

3. **Windows incompatibility** — Behavioral tests used `shutil.rmtree(".git")` which fails with PermissionError on Windows.

## Fixes Applied

### Git Failure Propagation

**Before:**
```python
try:
    stdout, _, _ = run_git_command(["diff", "--name-only", "--no-renames", "HEAD"])
    # ... process output
except RuntimeError:
    pass  # FAIL OPEN
```

**After:**
```python
stdout, _, _ = run_git_command(["diff", "--name-only", "--no-renames", "HEAD"])
# Let RuntimeError propagate to check_task_scope() -> exit 1
```

`run_git_command()` already raises `RuntimeError` on non-zero exit. Removing try/except lets failures propagate to `check_task_scope()` which catches and returns exit code 1 with "Git command failure" message.

### Baseline Deletion Detection

Fingerprint tracking now explicitly checks for missing baseline files:

```python
for baseline_path, baseline_fp in baseline_fingerprints.items():
    if baseline_path.startswith(".agent_runtime/"):
        continue
    if baseline_path in current_paths:
        # check fingerprint for mutation
    else:
        # FILE DELETED - check if authorized
        is_authorized = ...
        if not is_authorized:
            unauthorized.append(f"{baseline_path} (deleted)")
```

### Windows-Compatible Failure Injection

**Don't use:** `shutil.rmtree(".git")` — fails on Windows with PermissionError due to file locks in `.git/objects/`.

**Use instead:** Test outside a git repo entirely (no `git init`), or corrupt only `.git/index`:

```python
# Outside git repo - works on all platforms
os.chdir(tmpdir)
# No git init
sentinel.check()  # fails with "Not a git repository"

# Or corrupt just the index
os.remove(".git/index")
```

## Behavioral Test Coverage (45 tests)

All tests use isolated temporary Git repos:

| Test | Purpose |
|------|---------|
| `test_sentinel_behavioral_authorized_unstaged_edit_passes` | Happy path |
| `test_sentinel_behavioral_unauthorized_unstaged_edit_fails` | Untracked detection |
| `test_sentinel_behavioral_unauthorized_staged_edit_fails` | Staged detection |
| `test_sentinel_behavioral_unauthorized_rename_fails` | Rename = delete + add |
| `test_sentinel_behavioral_untouched_baseline_artifact_passes` | No false positive |
| `test_sentinel_behavioral_modified_baseline_artifact_fails` | Mutation detection |
| `test_sentinel_behavioral_git_diff_failure_fails_closed` | Git diff failure → FAIL |
| `test_sentinel_behavioral_git_ls_files_failure_fails_closed` | Git ls-files failure → FAIL |
| `test_sentinel_behavioral_unauthorized_baseline_deletion_fails` | Unauthorized delete → FAIL |
| `test_sentinel_behavioral_authorized_baseline_deletion_passes` | Authorized delete → PASS |
| `test_sentinel_behavioral_git_failure_cannot_produce_pass` | No false PASS |
| `test_sentinel_behavioral_exact_offending_path_reported` | Path reporting |
| `test_sentinel_behavioral_no_repair_delete_behavior` | Read-only invariant |

## Sentinel Contract (CLI)

```bash
# Initialize scope (Lead, before first write)
python -m tools.task_scope_sentinel init <task_id> <authorized_path>...

# Verify scope (after each batch, Release Gate)
python -m tools.task_scope_sentinel check
# PASS: "TASK SCOPE: PASS - All changes within authorized paths"
# FAIL: "TASK SCOPE VIOLATION: Unauthorized paths detected:\n  <path1>\n  <path2>"
```

## Contract File: `.agent_runtime/task_scope.json`

```json
{
  "task_id": "office_setup",
  "authorized_paths": [
    ".gitignore",
    "docs/engineering/MULTI_AGENT_WORKFLOW.md",
    "tools/task_scope_sentinel.py"
  ],
  "baseline_paths": ["_context_export/...", "graphify-out/...", ...],
  "baseline_fingerprints": {
    "baseline_file.txt": "sha256:..."
  }
}
```

## Integration Points

| Role | Responsibility |
|------|----------------|
| Lead | Run `init` before first write; run `check` after each batch |
| Release Gatekeeper | Run `check` before `READY_FOR_USER_REVIEW` (required in allowed_commands) |
| Chief | Verify sentinel PASS in final verdict |