---
name: obsidian-rl-patch-gate
description: Deterministic patch-acceptance gate for Obsidian-RL. Runs mechanical checks before Hermes declares a patch complete.
category: software-development
version: 1.0.0
author: Hermes Agent
tags:
  - obsidian-rl
  - patch-gate
  - validation
  - task-scope
  - safety
---

# Obsidian-RL Patch Gate Skill

This skill provides a deterministic, stdlib-only patch-acceptance gate that mechanically rejects unsafe/unexpected diffs before Hermes declares a code patch complete.

**CRITICAL**: This gate REUSES existing task_scope_sentinel and composes with repair-workflow. It does NOT create duplicate safety systems.

## Gate Checks (Mandatory)

| Check | Severity | Description |
|-------|----------|-------------|
| Task Scope | FAIL | Reuses `task_scope_sentinel` — unauthorized paths, deleted files, mutations |
| Test Weakening | FAIL/REVIEW_REQUIRED | Unauthorized test mods = FAIL; authorized mods with removed assertions/functions = REVIEW_REQUIRED |
| Dependency Changes | REVIEW_REQUIRED | pyproject.toml, uv.lock, CI configs, Dockerfiles |
| Archived Imports | REVIEW_REQUIRED | New imports from legacy/ or archive/ |
| Diff Size | REVIEW_REQUIRED | >20 files or >1000 lines (one bounded defect budget) |
| Deleted Tracked Files | FAIL | Non-authorized tracked file deletions |
| git diff --check | FAIL | Whitespace/syntax issues |

## Output Format

Machine-readable + concise human:
```
PATCH GATE: PASS / FAIL / REVIEW_REQUIRED
Task: <task_id>
  task_scope: PASS
  test_weakening: REVIEW_REQUIRED
    - test_x.py: 2 assertion(s) removed
  ...
```

**FAIL CLOSED**: Missing/malformed task scope, checker crash, ambiguous base, or unsupported state → never silently PASS.

## Integration with Repair Workflow

The `obsidian-rl-repair-workflow` validation step MUST invoke patch gate before final acceptance:
1. Run `python -m tools.patch_gate check`
2. Gate PASS ≠ financial correctness or strategy validity
3. REVIEW_REQUIRED → human must explicitly acknowledge before proceeding

## Usage

```bash
# Run gate (requires task_scope contract initialized)
python -m tools.patch_gate check

# JSON output for automation
python -m tools.patch_gate check --json
```

## Smoke Test Scenarios

| Case | Expected |
|------|----------|
| A. Permitted one-file change | PASS |
| B. Unauthorized extra file | FAIL |
| C. Dependency file without authorization | FAIL |
| D. Deleted existing test | FAIL |
| E. Removed assertion | REVIEW_REQUIRED |
| F. Oversized diff | REVIEW_REQUIRED |
| G. LONG-fix style broad test rewrite | FAIL/REVIEW_REQUIRED (not clean PASS) |
| H. Malformed/missing scope | FAIL CLOSED |

## Tests

Focused tests in `tests/tools/test_patch_gate.py` verify:
- Each check in isolation
- FAIL CLOSED behavior
- REVIEW_REQUIRED vs FAIL classification
- Integration with task_scope_sentinel

## Verification Commands

```bash
# Test gate on clean state (no contract)
python -m tools.patch_gate check

# Initialize task scope, make permitted change, verify PASS
python -m tools.task_scope_sentinel init test-gate "src/obsidian_rl/portfolio/engine.py"
# ... make change to engine.py ...
python -m tools.patch_gate check

# Test unauthorized file detection
# ... make change to unauthorized file ...
python -m tools.patch_gate check
```