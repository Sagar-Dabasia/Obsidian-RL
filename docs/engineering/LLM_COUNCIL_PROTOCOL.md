# LLM Council Decision-Pressure-Test Protocol

## Purpose

This document defines the **LLM Council** — an advisory deliberation overlay on top of the permanent 15-role Obsidian-RL engineering office. The Council provides structured pressure-testing for high-stakes decisions with genuine tradeoffs.

**CRITICAL**: The 15 permanent roles remain EXACT. Council advisors/reviewers are temporary deliberation instances with NO write authority and NO commit/push capability. They cannot override managers, Gatekeeper, repository evidence, or USER. Chief remains council chairman/synthesizer.

**Council is advisory evidence, NEVER authorization.**

---

## Council Triggers

### Council IS for:
- Major architecture change
- Financial/accounting/risk design change
- Research-governance change
- Large dependency/platform choice
- Major refactor
- Disputed manager/reviewer finding
- Phase-direction decision where being wrong is expensive

### Council is NOT for:
- Factual lookup
- Mechanical edit
- Routine test/lint failure
- Obvious bounded bugfix
- Ordinary documentation change
- Decisions USER already explicitly made

**Do NOT council:**
- factual lookup
- mechanical edit
- routine test/lint failure
- obvious bounded bugfix
- ordinary documentation change
- decisions USER already explicitly made

### Explicit USER Triggers:
- "council this"
- "pressure-test this"
- "war-room this"

Council is **advisory evidence, NEVER authorization**.

---

## Protocol Steps

### STEP 1 — FREEZE QUESTION
**Owner**: Planning / Workflow Manager

Planning Manager creates:
1. ONE neutral question (no leading language)
2. Frozen context digest (byte-identical decision facts for all advisors)
3. Record SHA-256 fingerprint of context
4. Record HEAD, branch, worktree fingerprint
5. **Record worktree fingerprint: `git status --porcelain=v1 --untracked-files=all` + `git diff --name-status` + `git ls-files --others --exclude-standard`**

**Output**: `council_id`, frozen prompt bundle, context SHA-256, pre-smoke worktree fingerprint

---

### STEP 2 — 5 INDEPENDENT ADVISORS
**Owner**: Chief Orchestrator (delegates via Hermes)

Temporary lenses (personas):
- **A. Contrarian** — hunt fatal flaws/downside
- **B. First-Principles** — question assumptions/root objective
- **C. Expansionist** — identify upside/adjacent opportunity
- **D. Outsider** — challenge expert blind spots from literal evidence
- **E. Executor** — smallest practical experiment/next action

**Execution**:
- Batch 1: 3 advisors (A, B, C)
- Batch 2: 2 advisors (D, E)
- Max 3 concurrent children (Hermes physical limit)

**MAX 3 children concurrently**

**POST-BATCH WORKTREE CHECK**: After each advisor batch (Batch 1 and Batch 2), verify worktree unchanged:
```bash
git status --porcelain=v1 --untracked-files=all
git diff --name-status
```
Must match pre-smoke fingerprint exactly. Any new modification => `COUNCIL_STATE = WRITE_VIOLATION` => STOP immediately, archive evidence, Gatekeeper veto. No later stage may convert WRITE_VIOLATION to PASS.

**CRITICAL Independence Rules**:
- Each advisor receives IDENTICAL frozen prompt
- NO advisor receives/reads prior advisor output
- NO shared response context before all 5 finish
- Scheduling later does NOT permit information bleed
- Provider failure = `FAILED_PROVIDER` in ledger, NEVER fabricated PASS
- All 5 advisors REQUIRED for COMPLETE status

---

### STEP 3 — ANONYMIZE
**Owner**: Chief Orchestrator (or Coordination Agent)

After all 5 complete:
1. Deterministically relabel responses A-E using `council_id` + session fingerprint
2. Remove obvious persona identifiers from responses
3. Preserve substantive content
4. Internal identity map preserved privately in `.agent_runtime/council/<council_id>/anonymization_map.json`

**Review Bundle**: Anonymized A-E responses (Reviewers cannot see identity map)

---

### STEP 4 — 5 PEER REVIEWERS
**Owner**: Chief Orchestrator (delegates via Hermes)

Each temporary reviewer receives identical anonymized A-E bundle.
- Batch 1: 3 reviewers
- Batch 2: 2 reviewers

**MAX 3 children concurrently**

**POST-BATCH WORKTREE CHECK**: After each reviewer batch (Batch 1 and Batch 2), verify worktree unchanged:
```bash
git status --porcelain=v1 --untracked-files=all
git diff --name-status
```
Must match pre-smoke fingerprint exactly. Any new modification => `COUNCIL_STATE = WRITE_VIOLATION` => STOP immediately, archive evidence, Gatekeeper veto. No later stage may convert WRITE_VIOLATION to PASS.

Each reviewer returns ONLY:
- Strongest response + why
- Biggest blind spot/error
- What ALL FIVE missed
- Ranking A-E
- Confidence

**CRITICAL Independence Rules**:
- Each reviewer receives IDENTICAL anonymized bundle
- NO reviewer receives/reads prior reviewer output
- NO shared response context before all 5 finish
- Reviewers CANNOT see identity map
- Provider failure = `FAILED_PROVIDER` in ledger, NEVER fabricated PASS
- All 5 reviewers REQUIRED for COMPLETE status

---

### STEP 5 — CHAIRMAN
**Owner**: Chief Orchestrator (root Hermes session)

Chief synthesizes:
- 5 anonymized advisor responses
- 5 anonymized peer reviews
- Internal identity map (privately, not for output)

**Canonical Output Format**:
```
AGREEMENT:
<What advisors AND reviewers agree on. Specific, evidence-backed.>

DISAGREEMENT:
<Where advisors/reviewers materially disagree. Specific points. No false consensus.>

BLIND_SPOTS:
<What ALL FIVE advisors AND ALL FIVE reviewers missed. Systemic gaps.>

RECOMMENDATION:
<Advisory only. One paragraph. Must name relevant Domain Manager(s) for routing.>

FIRST_ACTION:
<Smallest practical experiment. From Executor lens, validated by others. Time-boxed. Regression test produced.>

CONFIDENCE:
<0.0-1.0. Weighted by evidence quality, not vote count.>

MINORITY_WARNING:
<Any material dissent with evidence. If none, "NONE". Must not be empty string.>

ROUTING:
<Domain Manager(s): ENGINEERING / FINANCIAL_INTEGRITY / RESEARCH_DATA / VERIFICATION_RELEASE>
```

**Chairman Rules**:
- Chief is SYNTHESIS ONLY — not a new writer, not a decision-maker
- Majority vote alone is NOT truth — evidence quality > count
- MUST preserve material minority warnings
- Cannot override BLOCKED financial/safety evidence
- Cannot authorize commit/push
- Cannot bypass USER
- Recommendation routes through existing Domain Manager(s)
- Release Gatekeeper retains veto

---

### STEP 6 — EXISTING OFFICE STILL DECIDES
**Owner**: Relevant Domain Manager(s) → Release Gatekeeper → Chief → USER

Council recommendation routes through relevant existing Domain Manager(s).
Release Gatekeeper still applies existing veto rules.

**A council recommendation CANNOT**:
- Convert BLOCKED to PASS
- Override reproducible financial/safety evidence
- Authorize commit/push
- Bypass USER
- Cannot modify trading/research rules automatically

**USER remains final commit/push authority**

---

## Runtime Evidence

**Location**: `.agent_runtime/council/<council_id>/` (Git-ignored via `.gitignore`)

**Preserved**:
- `question_context.json` — question + context digest + SHA-256
- `advisor_responses/` — 5 raw advisor outputs
- `anonymization_map.json` — internal mapping (NEVER shared with reviewers)
- `review_bundle.json` — anonymized A-E sent to reviewers
- `reviewer_outputs/` — 5 raw reviewer outputs
- `chairman_synthesis.json` — canonical output
- `metadata.json` — provider failures, timestamps, order, HEAD, worktree fingerprint, final office disposition

**Rules**:
- Never delete failed councils automatically
- Preserve negative/contradictory evidence
- Do NOT commit runtime transcripts by default

---

## Implementation Files

### New Files (Clean Scope)
```
.hermes/skills/obsidian-rl-council/SKILL.md
.hermes/skills/obsidian-rl-council/references/advisor-prompts.md
.hermes/skills/obsidian-rl-council/references/reviewer-prompts.md
.hermes/skills/obsidian-rl-council/references/chairman-prompts.md
.hermes/skills/obsidian-rl-council/references/anonymization.md
docs/engineering/LLM_COUNCIL_PROTOCOL.md
tests/test_llm_council_governance.py
```

### Minimal Integration Edits (Only if Required)
```
docs/engineering/MULTI_AGENT_WORKFLOW.md
docs/engineering/AGENT_OFFICE_ROLES.md
```

### Do NOT Edit (Preexisting Dirty Artifacts)
```
.hermes/skills/obsidian-rl-office/SKILL.md
tests/test_agent_office_governance.py
```

### Do NOT Alter
- Trading code
- Production code

---

## Governance Tests

Repository-owned contract tests in `tests/test_llm_council_governance.py` validating:

1. **Permanent role count remains exactly 15** — Council adds zero permanent roles
2. **Hierarchy unchanged** — Council is advisory overlay only
3. **Council advisors/reviewers read-only** — No write_file, patch, git add/commit/push
4. **Temporary council roles cannot commit/push/write production** — Enforced by delegation config
5. **Max active children remains 3** — Inherits from office config
6. **Advisor prompt/context frozen identically** — Deterministic verification
7. **Advisor outputs hidden until all 5 complete** — No information bleed
8. **5 advisors required for COMPLETE** — Partial = BLOCKED
9. **Deterministic anonymization contract** — Same inputs → same outputs, persona markers removed
10. **Reviewer identity map hidden** — Reviewers cannot access anonymization_map.json
11. **5 reviewers required for COMPLETE** — Partial = BLOCKED
12. **Partial/provider-failed council cannot claim complete** — FAILED_PROVIDER blocks COMPLETE
13. **Chief is synthesis only, not new writer** — No write authority
14. **Minority warning preserved** — MINORITY_WARNING field mandatory, not empty
15. **Council cannot override BLOCKED financial/safety evidence** — Domain Manager + Gatekeeper veto
16. **Release Gatekeeper retains veto** — Existing gate unchanged
17. **USER retains sole commit/push authority** — No role has git commit/push in allowed_commands
18. **Trivial/mechanical tasks do not automatically invoke council** — Trigger list is explicit
19. **Runtime evidence path is Git-ignored/non-authoritative** — .gitignore contains .agent_runtime/
20. **No automatic deletion of failed council evidence** — Preservation rule explicit

---

## Live Smoke Test

After static governance tests pass, run ONE real council smoke test using Hermes delegation.

**Question**:
> "Should passing tests alone be sufficient evidence to bypass the Obsidian-RL Release Gatekeeper?"

**Purpose**: Protocol validation, NOT repository decision.

**Pre-Smoke Worktree Fingerprint**:
```bash
git status --porcelain=v1 --untracked-files=all
git diff --name-status
git ls-files --others --exclude-standard
```
Record as `pre_smoke_fingerprint.json`.

**ENFORCEMENT CLASSIFICATION**: **LIVE_COUNCIL_WRITE_ISOLATION = NOT_ENFORCEABLE**
- Hermes delegation does NOT support per-child tool allowlists, write-tool denial, or repository mutation restrictions
- prompt instructions alone do NOT provide hard isolation
- If enforcement becomes available, Council children MUST be restricted to READ-ONLY tools
- Until enforcement available: Council live delegation CANNOT be marked SAFE; Council local gate MUST be BLOCKED

**STANDALONE ZERO-TOOL RUNNER ISOLATION**:
The standalone `tools/council_runner.py` provides physical read-only isolation that Hermes delegation cannot enforce. It runs the 5 advisors via direct API calls with **ZERO tools attached** — no filesystem, no shell, no git, no write capabilities. Advisors receive context and return responses; no repository mutation is physically possible through this runner. This runner does NOT depend at runtime on `.hermes/skills/` files; all personas and prompts are embedded inline. The `.hermes/skills/` files are governance documentation/specification, not runtime dependencies.

**Required**:
- 5 isolated advisor results
- Anonymous A-E bundle
- 5 isolated peer reviews
- Chief synthesis
- Gatekeeper remains authoritative

**Constraints**:
- Max 3 children concurrently
- No repository writes by temporary council agents
- No commit/push
- No production changes

**POST-BATCH WORKTREE CHECK**: After EVERY advisor batch AND EVERY reviewer batch:
```bash
git status --porcelain=v1 --untracked-files=all
git diff --name-status
```
Must match `pre_smoke_fingerprint.json` exactly. Any new modification =>
`COUNCIL_STATE = WRITE_VIOLATION` => STOP immediately, archive evidence under `.agent_runtime/council/<council_id>/unauthorized_write/`, Gatekeeper veto. **WRITE_VIOLATION IS TERMINAL — cannot be converted to COMPLETE/PASS by any later stage.**

Scope Sentinel MUST treat any Council-created tracked/untracked repo file outside Council runtime evidence as violation.

**Failure Mode**:
- Provider failure => COUNCIL_SMOKE = BLOCKED
- Write violation => COUNCIL_SMOKE = FAIL_WRITE_VIOLATION
- Do not fake completion

---

## Invariants

- Paper trading only
- No live/Testnet/private orders
- No secrets
- No synthetic market data
- No future leakage
- No holdout access
- Centralized accounting/state unchanged
- No Cycle-1 revival
- No strategy/cost/timing changes
- Preserve historical/negative evidence
- Passing tests ≠ financial proof
- No destructive Git commands
- No unrelated refactor

---

## Verification

### Focused Council Tests
```
.venv/Scripts/python -m pytest tests/test_llm_council_governance.py -q
.venv/Scripts/python -m ruff check tests/test_llm_council_governance.py
.venv/Scripts/python -m ruff format --check tests/test_llm_council_governance.py
git diff --check
scope sentinel
```

### Full CI (After Focused + Smoke Pass)
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

### Release Gatekeeper Checks
- Exact branch/HEAD/worktree match
- Full diff/scope within authorized files
- Original 15 hierarchy unchanged
- Preexisting dirty artifacts fingerprint unchanged
- No trading code touched
- No reviewer contradiction
- Evidence current
- Council cannot override office/user

---

## MIT Attribution

This protocol adapts concepts from **YonasValentin/llm-council** (MIT License):
> 5 independent perspectives → anonymized peer review → chairman synthesis.

Original implementation was Claude-specific; this adaptation is for Hermes/Obsidian-native operation with frozen 15-role office integration.

**MIT License Notice**:
```
MIT License

Copyright (c) YonasValentin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## Status

This council protocol is established as an **advisory overlay** to the mandatory 15-role governance checkpoint BETWEEN phases.