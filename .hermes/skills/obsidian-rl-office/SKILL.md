---
name: obsidian-rl-office
description: Make the 15-role Obsidian engineering office operational in Hermes. References and enforces tracked governance in AGENTS.md, docs/engineering/MULTI_AGENT_WORKFLOW.md, docs/engineering/AGENT_OFFICE_ROLES.md.
category: software-development
version: 1.0.0
author: Hermes Agent
tags:
  - obsidian-rl
  - governance
  - multi-agent
  - delegation
---

# Obsidian-RL Engineering Office Skill

This skill makes the documented 15-role engineering office operational in Hermes using local `delegate_task` capability.

## Governance References

This skill enforces the contracts defined in:
- `AGENTS.md` — agent rules, scope, safety, correctness, validation
- `docs/engineering/MULTI_AGENT_WORKFLOW.md` — workflow state machine, hierarchy, ledger, permissions
- `docs/engineering/AGENT_OFFICE_ROLES.md` — role contracts, command permissions, escalation matrix

**Do not duplicate those documents.** This skill references them as the authoritative source.

## Physical Delegation Configuration

Required Hermes config (set by Chief before office activation):
```bash
hermes config set delegation.max_concurrent_children 3
hermes config set delegation.max_spawn_depth 1
hermes config set delegation.orchestrator_enabled false
```

These enforce:
- Maximum 3 simultaneous children
- Flat delegation only (depth 1)
- Children cannot recursively spawn more agents
- Chief/root Hermes remains sole physical orchestrator

## Role Hierarchy (15 Logical Roles)

### TIER 1 — CHIEF ORCHESTRATOR (ROOT HERMES)
- Manager of managers
- Owns final workflow/state
- Resolves conflicts
- Never edits code
- Cannot authorize commit/push

### TIER 1 — PLANNING / WORKFLOW MANAGER
- Decomposes each task BEFORE execution
- Defines dependencies, allowed files, acceptance criteria, test plan
- Assigns work through Chief
- Prevents unplanned scope expansion

### TIER 2 — DOMAIN MANAGERS (Read-Only, Supervisory)
- **ENGINEERING MANAGER** — supervises Lead/Writer, Architecture Reviewer, Environment/Reproducibility Reviewer
- **FINANCIAL INTEGRITY MANAGER** — supervises Financial/Accounting Reviewer, Adversarial/Red-Team Tester
- **RESEARCH/DATA MANAGER** — supervises Data/Leakage Reviewer
- **VERIFICATION/RELEASE MANAGER** — supervises Safety/Evidence Reviewer, Coordination/Test-Ledger Agent, Release Gatekeeper

### TIER 3 — SPECIALISTS
1. **LEAD / WRITER** — ONLY role allowed to modify repository files
2. **ARCHITECTURE REVIEWER** — centralized state/module boundaries/API consistency
3. **ENVIRONMENT / REPRODUCIBILITY REVIEWER** — venv/dependencies/toolchain/build
4. **FINANCIAL / ACCOUNTING REVIEWER** — cash/PnL/fees/spread/slippage/funding/turnover/trade count
5. **ADVERSARIAL / RED-TEAM TESTER** — actively attacks malformed/NaN/inf inputs, missing/stale data, sequencing
6. **DATA / LEAKAGE REVIEWER** — provenance, chronology, warm-up, future leakage, holdout boundaries
7. **SAFETY / EVIDENCE REVIEWER** — paper-trading-only, no secrets/live/Testnet/private orders
8. **COORDINATION / TEST-LEDGER AGENT** — owns shared temporary evidence ledger (`.agent_runtime/ledger.jsonl`)
9. **RELEASE GATEKEEPER** — independent read-only veto, final internal gate

## Physical Delegation Rules

- All delegated children MUST use `leaf` role
- No recursive delegation (spawn_depth=1 enforces this)
- Max 3 concurrent children
- Chief/root session performs actual delegation

## Workflow for Substantial Repository Work

1. **PREFLIGHT** — git branch/HEAD/worktree/invariants check
2. **PLAN** — Delegate Planning/Workflow Manager first
3. **IMPLEMENT** — Delegate ONE Lead/Writer when implementation required
4. **REVIEW WAVES** — Delegate relevant read-only reviewers in batches ≤3
5. **SEQUENTIAL** — Never run Lead concurrently with reviewers
6. **FINDINGS ONLY** — Reviewers return findings only; they never repair
7. **REPAIR** — Confirmed findings return to Lead for bounded repair
8. **LEDGER** — Consult `.agent_runtime/ledger.jsonl` before rerunning checks
9. **INVALIDATION** — Invalidate only evidence affected by later edits
10. **FULL CI** — Run only after focused review is clean
11. **RELEASE GATE** — Delegate Release Gatekeeper last
12. **VERDICT** — Chief returns `READY_FOR_USER_REVIEW` or `BLOCKED: <exact reason>`
13. **COMMIT** — Never commit/push without explicit user authorization

## Verdict Integrity Rules (Mandatory)

- **Child verdicts preserved exactly**: BLOCKED, PASS, FAIL, OUT_OF_SCOPE, INSUFFICIENT_EVIDENCE are final child outputs. Chief/Managers MUST NOT alter them.
- **BLOCKED never becomes PASS automatically**: Any BLOCKED child verdict requires explicit Domain Manager resolution.
- **Specialist BLOCKED routes to Domain Manager**: The responsible Domain Manager MUST review the BLOCKED finding and return exactly one of:
  - `RESOLVED_WITH_EVIDENCE` — defect fixed, new evidence recorded in ledger, stale marks invalidated
  - `BLOCKER_CONFIRMED` — defect real, cannot be resolved in this task, escalation reason recorded
  - `OUT_OF_SCOPE` — finding was outside assigned scope; recorded as such, does not block task
  - `INSUFFICIENT_EVIDENCE` — finding lacks reproducible evidence; recorded, reviewer may re-run with more data
- **Chief may mark child/domain PASS only after documented resolution**: Chief summary fields must match ledger state exactly.
- **Reproducible financial/safety defect cannot be overridden**: If Domain Manager returns `BLOCKER_CONFIRMED` for financial/safety, Chief MUST return `BLOCKED: <exact reason>`.
- **Release Gatekeeper refuses READY while any unresolved BLOCKED exists**: Gatekeeper checks ledger for any check with `result: BLOCKED` and `escalation_reason` not resolved. Must veto.
- **Out-of-scope findings recorded as OUT_OF_SCOPE, not PASS**: Classification is explicit, not implicit.
- **Contradictory summary fields fail closed**: If Chief reports `FINANCIAL_CHILD: PASS` but ledger shows `BLOCKED`, verification fails.

## Required Reviewers by Change Type

### Financial/Research Changes
- Financial/Accounting Reviewer
- Adversarial/Red-Team Tester
- Data/Leakage Reviewer
- Safety/Evidence Reviewer

### Every Repository-Changing Task
- Architecture Reviewer (where architecture affected)
- Environment/Reproducibility Reviewer (where tooling/env affected)
- Safety/Evidence Reviewer (always)
- Release Gatekeeper (always)

## Ledger

Location: `.agent_runtime/ledger.jsonl` (Git-ignored via `.gitignore` entry)

Records for every check:
- task_id, check_id, role/owner, purpose, exact command/test, affected/relevant files
- result, exit code, evidence timestamp/order, repository HEAD
- working diff fingerprint/version, PASS/FAIL/BLOCKED, evidence CURRENT or STALE
- invalidated_by change/reason, retry count, escalation reason

**Anti-loop rule**: Before running ANY check, consult ledger. Identical check MUST NOT rerun if it already passed, relevant implementation/tests have not changed, no manager supplied new documented reason.

## Command Permissions

### ALLOWED (Final Evidence)
- `git status/diff/log/rev-parse/show/check`
- persisted pytest tests
- `pip check`, `compileall`, `ruff check`, `ruff format --check`, `mypy`, `build`
- approved project tools needed by bounded task

### FORBIDDEN (Final Acceptance)
- random `python -c` diagnostics
- print-only PASS
- repeated already-current diagnostics
- broad repo-wide `--fix`
- destructive reset, history rewrite, force push
- `git add .`, `git add -A`
- reading secrets, synthetic data substitution
- holdout access outside explicitly authorized evaluation
- live/Testnet/private orders

`python -c` may ONLY be used for unique investigation if Lead/manager records why persisted tests cannot answer it yet, not treated as acceptance evidence, any reproduced defect becomes persisted regression test, ledger records it.

## Verification

Governance/contract tests in `tests/test_agent_office_governance.py` validate:
- exactly 15 logical roles represented
- Lead/Writer is sole writer
- reviewers/managers read-only
- user-exclusive commit/push authorization
- max concurrency contract = 3
- physical delegation depth contract = 1
- Release Gatekeeper required
- runtime ledger path is `.agent_runtime/ledger.jsonl`
- duplicate-current-evidence rerun forbidden
- bounded retry/escalation rule exists
- project skill exists and references governance docs
- no live/Testnet/private-order authorization

**Do NOT test global/local Hermes config from pytest.**

## Reference

- `references/first-smoke-test-defect.md` — First live smoke test defect (BLOCKED silently normalized to PASS) and resolution establishing verdict integrity rules