# Agent Office Roles & Permissions

This document defines the exact roles, permissions, and command contracts for the permanent multi-agent engineering office.

## Role Contracts

Each role has a defined contract specifying:
- `write_permission`: ALLOWED | FORBIDDEN | CONDITIONAL
- `allowed_commands`: list of permitted commands for final evidence
- `forbidden_commands`: list of commands that trigger STOP/escalation
- `escalation_path`: who to escalate to when blocked

---

## TIER 1 ROLES

### CHIEF ORCHESTRATOR
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - git rev-parse
  - git show
  - git branch
  - cat/read files
forbidden_commands:
  - git add
  - git commit
  - git push
  - git reset --hard
  - any code modification
  - any test execution
escalation_path: USER (sole commit/push authority)
```

### PLANNING / WORKFLOW MANAGER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - cat/read files
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - any test execution
escalation_path: CHIEF ORCHESTRATOR
```

---

## TIER 2 — DOMAIN MANAGERS (Read-Only, Supervisory)

### ENGINEERING MANAGER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - cat/read files
  - pytest --collect-only (read-only test discovery)
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution (runs tests)
  - python -c
escalation_path: CHIEF ORCHESTRATOR
```

### FINANCIAL INTEGRITY MANAGER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - cat/read files
  - pytest --collect-only
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
escalation_path: CHIEF ORCHESTRATOR
```

### RESEARCH/DATA MANAGER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - cat/read files
  - pytest --collect-only
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - holdout access
escalation_path: CHIEF ORCHESTRATOR
```

### VERIFICATION/RELEASE MANAGER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - git rev-parse
  - cat/read files
  - pytest --collect-only
  - pip check
  - python -m compileall -q src tests (dry-run only)
  - ruff check src tests (dry-run only)
  - ruff format --check src tests
  - mypy src
  - python -m build (dry-run only)
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
escalation_path: CHIEF ORCHESTRATOR
```

---

## TIER 3 — SPECIALISTS

### LEAD / WRITER (ONLY WRITER)
```yaml
write_permission: ALLOWED
allowed_commands:
  - git status
  - git diff
  - git log
  - git rev-parse
  - cat/read files
  - write_file / patch (ONLY on authorized files for bounded task)
  - pytest tests/specific_test.py (focused tests for assigned task)
  - python -m compileall -q src tests
  - ruff check src tests
  - ruff format src tests
  - mypy src
  - pip check
  - python -c (ONLY for unique investigation with ledger record)
forbidden_commands:
  - git commit
  - git push
  - git add . / git add -A
  - git reset --hard
  - history rewrite
  - force push
  - random python -c diagnostics
  - broad repo-wide --fix
  - reading secrets
  - live/Testnet/private orders
  - holdout access outside explicitly authorized evaluation
  - synthetic data substitution
  - any file modification outside authorized files
escalation_path: CHIEF ORCHESTRATOR
```

### ARCHITECTURE REVIEWER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - cat/read files
  - grep/rg (read-only search)
  - pytest --collect-only
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - write_file / patch
escalation_path: ENGINEERING MANAGER → CHIEF ORCHESTRATOR
```

### ENVIRONMENT / REPRODUCIBILITY REVIEWER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - cat/read files
  - pip check
  - pip list
  - python -m compileall -q src tests (dry-run)
  - python -c "import sys; print(sys.version)"
  - python -c "import obsidian_rl; print(obsidian_rl.__version__)"
  - python -m build --dry-run
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c (except version/import checks above)
  - write_file / patch
  - pip install
escalation_path: ENGINEERING MANAGER → CHIEF ORCHESTRATOR
```

### FINANCIAL / ACCOUNTING REVIEWER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - cat/read files
  - pytest --collect-only (focused on portfolio/accounting tests)
  - grep/rg (read-only search for financial terms)
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - write_file / patch
escalation_path: FINANCIAL INTEGRITY MANAGER → CHIEF ORCHESTRATOR
```

### ADVERSARIAL / RED-TEAM TESTER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - cat/read files
  - pytest --collect-only (focused on adversarial edge cases)
  - grep/rg (read-only search for attack vectors)
  - read_file (evidence collection only)
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification (NEVER patches production code)
  - pytest execution
  - python -c
  - write_file / patch
escalation_path: FINANCIAL INTEGRITY MANAGER → CHIEF ORCHESTRATOR
```

### DATA / LEAKAGE REVIEWER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - cat/read files
  - pytest --collect-only (focused on data/provenance tests)
  - grep/rg (read-only search for leakage vectors)
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - write_file / patch
  - holdout access
escalation_path: RESEARCH/DATA MANAGER → CHIEF ORCHESTRATOR
```

### SAFETY / EVIDENCE REVIEWER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - git rev-parse
  - git diff --check
  - cat/read files
  - pytest --collect-only
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - write_file / patch
escalation_path: VERIFICATION/RELEASE MANAGER → CHIEF ORCHESTRATOR
```

### COORDINATION / TEST-LEDGER AGENT
```yaml
write_permission: CONDITIONAL (ONLY .agent_runtime/ledger.jsonl)
allowed_commands:
  - cat/read files (ledger and evidence)
  - write_file .agent_runtime/ledger.jsonl (append-only)
  - git status
  - git diff
  - cat/read files
forbidden_commands:
  - git add (except ledger if explicitly allowed)
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - write_file on production code
escalation_path: VERIFICATION/RELEASE MANAGER → CHIEF ORCHESTRATOR
```

### RELEASE GATEKEEPER
```yaml
write_permission: FORBIDDEN
allowed_commands:
  - git status
  - git diff
  - git log
  - git rev-parse
  - git diff --check
  - cat/read files
  - pytest --collect-only
  - pip check
  - python -m compileall -q src tests (dry-run)
  - ruff check src tests
  - ruff format --check src tests
  - mypy src
  - python -m build --dry-run
  - python -m tools.task_scope_sentinel check
forbidden_commands:
  - git add
  - git commit
  - git push
  - any code modification
  - pytest execution
  - python -c
  - write_file / patch
escalation_path: CHIEF ORCHESTRATOR
```

---

## Command Classification

### FINAL EVIDENCE COMMANDS (Allowed for designated roles)
- `git status`, `git diff`, `git log`, `git rev-parse`, `git show`, `git branch`
- `cat` / `read_file` (any file)
- `grep` / `rg` (read-only search)
- `pip check`
- `python -m compileall -q src tests`
- `ruff check src tests`
- `ruff format --check src tests`
- `mypy src`
- `python -m pytest` (focused tests for Lead; --collect-only for reviewers)
- `python -m build`
- `git diff --check`

### FORBIDDEN COMMANDS (Final Acceptance)
- `python -c` (random diagnostics)
- Print-only PASS without persisted regression test
- Repeated already-current diagnostics
- `ruff check --fix` (broad repo-wide)
- `ruff format` (broad repo-wide)
- `git add .` / `git add -A`
- `git reset --hard`
- `git push --force`
- History rewrite
- Reading `.env` or secrets
- Synthetic data substitution
- Holdout access outside explicitly authorized evaluation
- Live/Testnet/private orders
- Any command not in ALLOWED list for the role's current task

### CONDITIONAL: `python -c`
May ONLY be used for unique investigation if:
1. Lead/manager records why persisted tests cannot answer it yet
2. NOT treated as acceptance evidence
3. Any reproduced defect becomes persisted regression test
4. Ledger records it
5. Not repeated without invalidation

---

## Escalation Matrix

| From Role | To Role | Trigger |
|-----------|---------|---------|
| Specialist | Domain Manager | Blocker, finding, unclear ownership |
| Domain Manager | Chief | Conflict, disagreement, unreproducible finding |
| Chief | USER | Commit/push authorization, unresolvable conflict |
| Release Gatekeeper | Chief | Unresolved blocker, contradictory evidence |
| Any | Chief | Forbidden command attempt, fake PASS detection |

---

## Verification

Role contracts are validated by governance tests in `tests/test_agent_office_governance.py` (repository-owned, not Hermes internals).

### Test Requirements
1. Only Lead has write permission in role contract
2. Reviewers/managers are read-only (write_file/patch forbidden)
3. Commit/push requires explicit user authorization (not in any role's allowed_commands)
4. Ledger duplicate PASS cannot rerun without invalidation/reason
5. Stale evidence is invalidated by relevant file/behavior change
6. Unrelated change does not invalidate unrelated evidence
7. Retry >2 escalates (escalation_path traversed)
8. Provider failure preserves prior PASS evidence
9. Release Gatekeeper refuses unresolved blocker
10. Fake print-only PASS is not acceptance evidence
11. Forbidden command causes STOP/escalation
12. Full CI not rerun repeatedly without invalidation