---
name: obsidian-rl-repair-workflow
description: Diagnose → Localize → Minimal Repair → Validate workflow for Obsidian-RL. Prevents speculative edits and fix loops.
category: software-development
version: 1.0.0
author: Hermes Agent
tags:
  - obsidian-rl
  - repair-workflow
  - debugging
  - minimal-repair
  - validation
---

# Obsidian-RL Repair Workflow Skill

This skill enforces a disciplined Diagnose → Localize → Minimal Repair → Validate workflow for all defect work in Obsidian-RL. It COMPOSES WITH existing skills (repo-map, selective-context, library-docs) — does not duplicate them.

**CRITICAL**: Passing tests alone ≠ defect absence. Financial correctness cannot be proven by software tests alone.

## Workflow (MANDATORY ORDER)

### 1. DIAGNOSE
Before ANY edit, explicitly state:
- Observed failure (exact error/behavior)
- Expected behavior (from spec/tests/invariants)
- Evidence reproducing/supporting defect (logs, test output, graph query)
- Defect classification (logic/performance/contract/regression)
- Uncertainty/ambiguity remaining

### 2. LOCALIZE
Use selective-context + Graphify to identify:
- Exact target file(s) and symbol(s)
- Caller/callee path (graphify path / affected)
- Directly relevant tests (not full suite)
- Governing invariant(s) from repo/docs/tests
- Likely root cause hypothesis (with evidence)

**HARD STOP**: If root cause remains unresolved → STOP. Do NOT edit speculatively.

### 3. PATCH PLAN
Before modifying, document:
- Exact files allowed to change (minimal set)
- Smallest behavioral change to address root cause
- Behavior that MUST remain unchanged (invariants)
- Focused regression test to add/update

Prefer 1 root-cause repair over multiple symptom patches.

### 4. MINIMAL REPAIR
- Edit ONLY localized scope
- NO unrelated refactor/cleanup
- NO dependency upgrades unless explicitly authorized
- Preserve historical/negative evidence
- NEVER weaken/delete tests to make patch pass
- Financial/accounting/timing/cost/signal contracts unchanged without authorization

### 5. VALIDATE IN ORDER
A. Regression reproducer (original failure case)
B. Directly relevant tests (≤5, focused)
C. Affected-path / Graphify impact inspection where useful
D. Broader/full suite ONLY when appropriate per task
E. `git diff --check`
F. Scope sentinel
G. Patch gate: `python -m tools.patch_gate check` (MUST PASS or REVIEW_REQUIRED with explicit acknowledgment)
H. Exact final diff review

### 6. ADJUDICATE
Classify result:
- CONFIRMED_FIXED — defect resolved, invariants held, scope contained
- INVALID_ORIGINAL_DIAGNOSIS — root cause was wrong, reassess
- PARTIALLY_FIXED — some aspects resolved, residual uncertainty
- STILL_UNVERIFIED — cannot confirm without protected data/access
- NEW_BLOCKER — repair revealed new issue

**If first repair fails**: STOP and reassess root cause. Do NOT automatically enter another edit loop.

### 7. HARD STOP CONDITIONS
STOP before editing/continuing if:
- Branch/HEAD unexpected
- Preexisting unrelated dirty worktree
- Root cause unsupported by evidence
- Required protected data would be accessed (holdout/market/secrets)
- Synthetic fallback needed
- Tests would need weakening
- Scope expands materially beyond plan
- Accounting/timing/cost/signal contract would change without explicit authorization

### 8. FINANCIAL/RESEARCH RULES
Never let software test success alone prove:
- Financial correctness
- Absence of leakage (future data, lookahead)
- Strategy validity
- Profitability
- Production readiness

## Integration with Existing Skills

| Skill | Role in Repair Workflow |
|-------|------------------------|
| obsidian-rl-repo-map | Graphify query/path/affected for localization |
| obsidian-rl-selective-context | Budget-limited retrieval of relevant source/tests/docs |
| obsidian-rl-library-docs | Exact-version third-party API verification |

This skill provides the WORKFLOW GOVERNANCE; other skills provide the NAVIGATION/RETRIEVAL.

## Smoke Test Scenarios (Read-Only)

### Case A: LONG buy-and-hold defect
**Diagnosis**: LONG benchmark repeatedly rebalanced toward 100% exposure instead of fixed-quantity buy-and-hold
**Localization via Graphify**: `graphify query "LONG benchmark backtest rebalance" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000` → `src/obsidian_rl/evaluation/trend_backtest.py`, `tests/evaluation/test_trend_backtest.py`
**Invariant**: True LONG = one entry + fixed quantity + terminal close (per `test_long_mode_buy_and_hold_semantics`)
**Minimal scope**: LONG-mode backtest semantics in `trend_backtest.py` only
**Edit allowed**: YES — if root cause localized to specific symbol

### Case B: Accidental LONG-fix test regression
**Diagnosis**: Tests pass but baseline behavior changed
**Localization**: `git diff` shows test assertions modified alongside fix
**Invariant**: Existing tests MUST NOT be weakened to make patch pass
**Minimal scope**: Revert test changes, fix production code only
**Edit allowed**: YES — but ONLY if test assertions restored to original

### Case C: Hypothetical unknown failure with insufficient evidence
**Diagnosis**: "Something might be wrong with funding calculation"
**Localization**: Graphify returns 500+ nodes, no focused evidence
**Invariant**: No specific invariant identified
**Minimal scope**: NONE — root cause unresolved
**Edit allowed**: NO — STOP instead of speculative edit

## Verification Commands

```bash
# Verify Graphify available for localization
graphify query "TrendSignal PortfolioEngine Ledger" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000

# Verify selective-context budget rules
# (enforced by skill, not a single command)

# Verify library-docs for third-party APIs
# (used during localize if external lib involved)
```