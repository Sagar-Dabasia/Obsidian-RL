# Multi-Agent Engineering Office Workflow

This document describes the permanent hierarchical Hermes/Nemotron engineering office for Obsidian-RL.

## Overview

The office is a permanent governance checkpoint BETWEEN phases that:
- Catches defects BEFORE push
- Prevents repeated test/diagnostic loops
- Preserves evidence across interrupted/compressed sessions
- Separates writing from reviewing
- Has strict management/escalation
- Uses persisted regression tests, not fake PASS labels
- Leaves user as sole commit/push authority

## Hierarchy

### TIER 1 — CHIEF ORCHESTRATOR
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

### TIER 2 — DOMAIN MANAGERS

**ENGINEERING MANAGER** supervises:
- Lead/Writer
- Architecture Reviewer
- Environment/Reproducibility Reviewer

**FINANCIAL INTEGRITY MANAGER** supervises:
- Financial/Accounting Reviewer
- Adversarial/Red-Team Tester

**RESEARCH/DATA MANAGER** supervises:
- Data/Leakage Reviewer

**VERIFICATION/RELEASE MANAGER** supervises:
- Safety/Evidence Reviewer
- Coordination/Test-Ledger Agent
- Release Gatekeeper

### TIER 3 — SPECIALISTS (Read-Only except Lead)

1. **LEAD / WRITER** — ONLY role allowed to modify repository files
2. **ARCHITECTURE REVIEWER** — centralized state/module boundaries/API consistency
3. **ENVIRONMENT / REPRODUCIBILITY REVIEWER** — venv/dependencies/toolchain/build
4. **FINANCIAL / ACCOUNTING REVIEWER** — cash/PnL/fees/spread/slippage/funding/turnover/trade count
5. **ADVERSARIAL / RED-TEAM TESTER** — actively attacks malformed/NaN/inf inputs, missing/stale data, sequencing
6. **DATA / LEAKAGE REVIEWER** — provenance, chronology, warm-up, future leakage, holdout boundaries
7. **SAFETY / EVIDENCE REVIEWER** — paper-trading-only, no secrets/live/Testnet/private orders
8. **COORDINATION / TEST-LEDGER AGENT** — owns shared temporary evidence ledger
9. **RELEASE GATEKEEPER** — independent read-only veto, final internal gate

## Physical Delegation Safety

- Max 3 specialist/reviewer children concurrently
- Spawn depth 1 (if Hermes supports it)
- Chief/root session performs actual delegation
- Managers are logical supervisory roles invoked as sibling reviewers where necessary
- Managers MUST NOT recursively spawn uncontrolled children
- If installed Hermes version/config does not support a requested delegation setting: STOP with exact blocker

## Shared Temporary Test/Evidence Ledger

Location: `.agent_runtime/ledger.jsonl` (Git-ignored via `.gitignore` entry)

Ledger records for every check:
- task_id, check_id, role/owner, purpose, exact command/test, affected/relevant files
- result, exit code, evidence timestamp/order, repository HEAD
- working diff fingerprint/version, PASS/FAIL/BLOCKED, evidence CURRENT or STALE
- invalidated_by change/reason, retry count, escalation reason

**ANTI-LOOP RULE**: Before running ANY check, consult ledger. Identical check MUST NOT rerun if it already passed, relevant implementation/tests have not changed, no manager supplied new documented reason.

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

## Workflow State Machine

1. **PREFLIGHT** — branch/HEAD/worktree/invariants
2. **PLAN** — Planning Manager creates bounded task, allowed files, prohibited changes, acceptance tests, reviewer assignments, dependencies
3. **IMPLEMENT** — Lead only
4. **FOCUSED REVIEW WAVES** — At most 3 reviewers concurrently
5. **FINDINGS** — Every finding: exact file/behavior, reproducible evidence, severity, regression test requirement
6. **REPAIR** — Lead fixes confirmed findings
7. **LEDGER INVALIDATION** — Only checks affected by changed files/behavior become STALE
8. **TARGETED RE-REVIEW** — Run only stale/failed checks
9. **FULL CI** — Run once after focused gates are clean; rerun only if subsequent change invalidates it
10. **RELEASE GATE** — Gatekeeper checks: current HEAD/diff, all required reviews CURRENT, zero unresolved defects, zero contradictory findings, zero unrelated changes, CI current, reports/evidence truthful, safety invariants intact
11. **CHIEF VERDICT** — Only: READY_FOR_USER_REVIEW or BLOCKED: <exact reason>

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

## Failure / Conflict Scenarios

Hard-coded handling for: duplicate testing loop, stale PASS after later code edit, reviewer disagreement, manager disagreement, failing test with unclear ownership, provider overload/429, interrupted Hermes session, context compression, dirty initial worktree, unrelated file modification, weakened/deleted tests, fake/print-only PASS, unsupported Hermes configuration, missing data, synthetic fallback attempt, holdout leakage attempt, future-data leakage, timing/cost change, accounting ownership duplication, archived Cycle-1 logic revival, unknown/non-finite financial inputs, tests pass but financial math wrong, Release Gatekeeper veto.

Conflict chain: specialist → domain manager → Chief. Chief cannot override a reproducible safety/financial defect without evidence. Release Gatekeeper veto remains until defect/evidence issue is resolved.

## Context/Session Recovery

New or resumed sessions must reconstruct state from:
1. Git branch/HEAD/worktree
2. AGENTS.md
3. Active Cycle-2/current-state docs
4. Temporary ledger
5. Current task contract

Never rely only on conversational memory.

## Repository Governance

Tracked files:
- `docs/engineering/MULTI_AGENT_WORKFLOW.md` (this file)
- `docs/engineering/AGENT_OFFICE_ROLES.md`
- `.gitignore` narrow runtime-ledger entry

If Hermes supports a safe reusable repo-local agent-role/config mechanism, use it ONLY after verifying the installed schema/help.

## Repository / Research Invariants

Preserve: historical failures/negative evidence, no deletion by default, no quarantined legacy imports, no Cycle-1 PPO/median-seed PPO/standalone Alpha Gate revival without new hypothesis + evidence, paper trading only, no secrets, no synthetic fallback, no future leakage, centralized accounting/position state, chronological validation, protected holdout, realistic costs, tests ≠ financial proof, no Phase-4 conclusion changes, no strategy tuning in this setup task.

## Testing the Office Itself

Governance/contract tests or deterministic validation checks to prove:
- Only Lead has write permission in role contract
- Reviewers/managers are read-only
- Commit/push requires explicit user authorization
- Ledger duplicate PASS cannot rerun without invalidation/reason
- Stale evidence is invalidated by relevant change
- Unrelated change does not invalidate unrelated evidence
- Retry >2 escalates
- Provider failure preserves prior PASS evidence
- Release Gatekeeper refuses unresolved blocker
- Fake print-only PASS is not acceptance evidence
- Forbidden command causes STOP/escalation
- Full CI is not rerun repeatedly without invalidation

Test repository-owned governance logic/contracts only — not Hermes internals.

---

**Status**: This office is established as the mandatory governance checkpoint BETWEEN Phase 5 and Phase 6.