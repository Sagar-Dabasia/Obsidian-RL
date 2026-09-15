---
name: obsidian-rl-council
description: LLM Council decision-pressure-test protocol for Obsidian-RL. 5 independent advisors + 5 peer reviewers + Chairman synthesis. Advisory only, zero write authority, runs on top of frozen 15-role office.
category: software-development
version: 1.0.0
author: Hermes Agent
tags:
  - obsidian-rl
  - governance
  - council
  - llm-council
  - decision-protocol
---

# Obsidian-RL LLM Council Skill

This skill implements a deliberation overlay on top of the permanent 15-role engineering office. The Council provides advisory pressure-testing for high-stakes decisions with genuine tradeoffs.

**CRITICAL**: The 15 permanent roles remain EXACT. Council advisors/reviewers are temporary deliberation instances with NO write authority and NO commit/push capability. They cannot override managers, Gatekeeper, repository evidence, or USER. Chief remains council chairman/synthesizer.

## Governance References

This skill enforces the contracts defined in:
- `AGENTS.md` — agent rules, scope, safety, correctness, validation
- `docs/engineering/MULTI_AGENT_WORKFLOW.md` — workflow state machine, hierarchy, ledger, permissions
- `docs/engineering/AGENT_OFFICE_ROLES.md` — role contracts, command permissions, escalation matrix
- `docs/engineering/LLM_COUNCIL_PROTOCOL.md` — council protocol, triggers, steps, evidence

**Do not duplicate those documents.** This skill references them as the authoritative source.

## Physical Delegation Configuration

Inherits from obsidian-rl-office:
- `delegation.max_concurrent_children: 3`
- `delegation.max_spawn_depth: 1`
- `delegation.orchestrator_enabled: false`

Council respects the same physical limits:
- Maximum 3 simultaneous children
- Flat delegation only (depth 1)
- Children cannot recursively spawn more agents
- Chief/root Hermes remains sole physical orchestrator

**max_concurrent_children 3**
**max_spawn_depth 1**

**ENFORCEMENT CLASSIFICATION**: **LIVE_COUNCIL_WRITE_ISOLATION = NOT_ENFORCEABLE**
- Hermes delegation does NOT support per-child tool allowlists, write-tool denial, or repository mutation restrictions
- prompt instructions alone do NOT provide hard isolation
- If enforcement becomes available, Council children MUST be restricted to READ-ONLY tools
- Until enforcement available: Council live delegation CANNOT be marked SAFE; Council local gate MUST be BLOCKED

## Council Triggers

Council ONLY for high-stakes decisions with genuine tradeoffs:
- major architecture change
- financial/accounting/risk design change
- research-governance change
- large dependency/platform choice
- major refactor
- disputed manager/reviewer finding
- phase-direction decision where being wrong is expensive

**Do NOT council:**
- factual lookup
- mechanical edit
- routine test/lint failure
- obvious bounded bugfix
- ordinary documentation change
- decisions USER already explicitly made

USER may explicitly trigger with:
- "council this"
- "pressure-test this"
- "war-room this"

Council is advisory evidence, NEVER authorization.

## Council Protocol

### STEP 1 — FREEZE QUESTION
Planning Manager creates ONE neutral question + frozen context digest.
All advisors receive byte/logically identical decision facts.
No leading language.
Record SHA-256/fingerprint of context.

### STEP 2 — 5 INDEPENDENT ADVISORS
Temporary lenses:
- A. Contrarian — hunt fatal flaws/downside
- B. First-Principles — question assumptions/root objective
- C. Expansionist — identify upside/adjacent opportunity
- D. Outsider — challenge expert blind spots from literal evidence
- E. Executor — smallest practical experiment/next action

Run advisors in isolated batches:
- batch 1 = 3 advisors
- batch 2 = 2 advisors

CRITICAL independence:
- each advisor receives same frozen prompt
- no advisor receives/reads prior advisor output
- no shared response context before all 5 finish
- scheduling later does NOT permit information bleed
- provider failure remains FAILED_PROVIDER, never fabricated PASS
- **5 advisors REQUIRED for COMPLETE**

### STEP 3 — ANONYMIZE
After all 5 complete:
- deterministically relabel responses A-E using council_id/session fingerprint
- Review bundle must remove obvious persona identifiers where practical
- Preserve internal mapping privately in runtime evidence

### STEP 4 — 5 PEER REVIEWERS
Each temporary reviewer gets identical anonymized A-E bundle.
Run isolated batches 3 + 2.
Each returns ONLY:
- strongest response + why
- biggest blind spot/error
- what ALL FIVE missed
- ranking A-E
- confidence

Reviewers cannot see identity map.
- **5 reviewers REQUIRED for COMPLETE**
- **NEVER fabricated PASS**

### STEP 5 — CHAIRMAN
Chief synthesizes:
```
AGREEMENT:
DISAGREEMENT:
BLIND_SPOTS:
RECOMMENDATION:
FIRST_ACTION:
CONFIDENCE:
MINORITY_WARNING:
```

**Chief is SYNTHESIS ONLY — not a new writer, not a decision-maker**
**Majority vote alone is NOT truth — evidence quality > count**
**MUST preserve material minority warnings**
**Cannot override BLOCKED financial/safety evidence**
**Cannot authorize commit/push**
**Cannot bypass USER**
**Recommendation routes through existing Domain Manager(s)**
**Release Gatekeeper retains veto**

### STEP 6 — EXISTING OFFICE STILL DECIDES
Council recommendation routes through relevant existing Domain Manager(s).
Release Gatekeeper still applies existing veto rules.

**A council recommendation CANNOT**:
- Convert BLOCKED to PASS
- Override reproducible financial/safety evidence
- Authorize commit/push
- Bypass USER
- Cannot modify trading/research rules automatically

**USER retains sole commit/push authority**

## Runtime Evidence

Use Git-ignored:
`.agent_runtime/council/<council_id>/`

Preserve:
- question/context fingerprint
- 5 advisor outputs
- anonymization map
- 5 reviewer outputs
- chairman synthesis
- provider failures
- timestamps/order
- HEAD
- worktree fingerprint
- final office disposition

Never delete failed councils automatically.
Preserve negative/contradictory evidence.

Do NOT commit runtime transcripts by default.

## Implementation Files

### New Files
```
.hermes/skills/obsidian-rl-council/SKILL.md
.hermes/skills/obsidian-rl-council/references/advisor-prompts.md
.hermes/skills/obsidian-rl-council/references/reviewer-prompts.md
.hermes/skills/obsidian-rl-council/references/chairman-prompts.md
.hermes/skills/obsidian-rl-council/references/anonymization.md
docs/engineering/LLM_COUNCIL_PROTOCOL.md
tests/test_llm_council_governance.py
```

### Minimal Integration Edits (Only if required)
```
docs/engineering/MULTI_AGENT_WORKFLOW.md
docs/engineering/AGENT_OFFICE_ROLES.md
```

Do NOT edit existing dirty:
- `.hermes/skills/obsidian-rl-office/SKILL.md`
- `tests/test_agent_office_governance.py`

Do NOT alter trading code.

Planning Manager must establish exact allowlist before Lead writes.

## Governance Tests

Persist tests proving:
- permanent role count remains exactly 15
- hierarchy unchanged
- Council advisors/reviewers read-only
- temporary council roles cannot commit/push/write production
- max active children remains 3
- advisor prompt/context frozen identically
- advisor outputs hidden until all 5 complete
- 5 advisors required for COMPLETE
- deterministic anonymization contract
- reviewer identity map hidden
- 5 reviewers required for COMPLETE
- partial/provider-failed council cannot claim complete
- Chief is synthesis only, not new writer
- minority warning preserved
- Council cannot override BLOCKED financial/safety evidence
- Release Gatekeeper retains veto
- USER retains sole commit/push authority
- trivial/mechanical tasks do not automatically invoke council
- runtime evidence path is Git-ignored/non-authoritative
- no automatic deletion of failed council evidence

Do not claim pytest can test Hermes internals.
Test repository-owned contracts only.

## Live Smoke Test

After static governance tests pass, run ONE real council smoke test using Hermes delegation.

Question:
"Should passing tests alone be sufficient evidence to bypass the Obsidian-RL Release Gatekeeper?"

Purpose = protocol validation, NOT repository decision.

Require:
- 5 isolated advisor results
- anonymous A-E bundle
- 5 isolated peer reviews
- Chief synthesis
- Gatekeeper remains authoritative

Max 3 children concurrently.
No repository writes by temporary council agents.
No commit/push.
No production changes.

Provider failure => COUNCIL_SMOKE = BLOCKED.
Do not fake completion.

## Invariants

Paper trading only.
No live/Testnet/private orders.
No secrets.
No synthetic market data.
No future leakage.
No holdout access.
Centralized accounting/state unchanged.
No Cycle-1 revival.
No strategy/cost/timing changes.
Preserve historical/negative evidence.
Passing tests ≠ financial proof.
No destructive Git commands.
No unrelated refactor.

## Verification

Focused:
```
.venv/Scripts/python -m pytest tests/test_llm_council_governance.py -q
.venv/Scripts/python -m ruff check tests/test_llm_council_governance.py
.venv/Scripts/python -m ruff format --check tests/test_llm_council_governance.py
git diff --check
scope sentinel
```

If any confirmed defect appears:
ONE consolidated Lead repair pass only.
Then rerun only invalidated checks.

If focused + live smoke pass:
```
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy src
.venv/Scripts/python -m compileall -q src tests
.venv/Scripts/python -m pip check
.venv/Scripts/python -m build
git diff --check
```

Release Gatekeeper:
- exact branch/HEAD/worktree
- full diff/scope
- original 15 hierarchy unchanged
- preexisting dirty artifacts fingerprint unchanged
- no trading code touched
- no reviewer contradiction
- evidence current
- council cannot override office/user

NO COMMIT.
NO PUSH.