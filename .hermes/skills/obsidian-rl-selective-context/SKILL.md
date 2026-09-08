---
name: obsidian-rl-selective-context
description: Selective context retrieval for Obsidian-RL. Teaches Hermes to retrieve only task-relevant context using Graphify + focused source inspection.
category: software-development
version: 1.0.0
author: Hermes Agent
tags:
  - obsidian-rl
  - selective-context
  - context-retrieval
  - graphify
  - efficiency
---

# Obsidian-RL Selective Context Retrieval Skill

This skill teaches Hermes to retrieve ONLY context needed for the current task. It builds on the existing obsidian-rl-repo-map skill (Graphify) and does NOT duplicate repo-map functionality.

**CRITICAL**: Source code and Git history remain the absolute authority. Graphify is an optional navigation aid only.

## When to Use Retrieval

### DO NOT retrieve for:
- Typo/formatting fixes
- Exact known-file mechanical edits
- User already supplied sufficient exact context

### USE retrieval for:
- Debugging/root cause analysis
- Architecture/call path questions
- Cross-module behavior understanding
- Unfamiliar code areas
- Financial/accounting/data-validity changes

## Retrieval Order (follow strictly)

1. **Focused Graphify query/path/affected** — `graphify query "<question>" --budget 2000`
2. **Inspect exact active source files returned** — Read actual source files from Graphify results
3. **Inspect direct callers/callees only when needed** — Use `graphify path` or `graphify affected` for specific relationships
4. **Inspect directly relevant tests** — Only tests for the specific module/function under investigation
5. **Inspect relevant active governance/research docs only when task requires them** — Current Cycle 2 docs, not archive

## Context Budget (expand ONLY with explicit unresolved question)

Start narrow:
- Graphify budget: ≤2000 tokens
- Source files: ≤5 initially
- Test files: ≤3 directly relevant
- Docs: ≤3 relevant

**Do not dump full repository/reports into context.**

## Source Priority Hierarchy

```
active src/ + active tests/ + current Cycle 2 docs
    >
Git history (when provenance matters)
    >
legacy/archive (historical evidence ONLY)
```

**Never import/use legacy as active implementation.**

## Before Editing: Hermes Must Know

Before any edit, verify you have:
- [ ] Target symbol/file identified
- [ ] Relevant caller/callee path traced
- [ ] Relevant tests located
- [ ] Applicable invariant(s) understood
- [ ] Why each retrieved file is necessary (explicit rationale)

If root cause remains unclear:
- STOP diagnosis
- Retrieve another focused slice
- Do NOT edit speculatively

## After Editing

- Use `graphify affected` / `graphify path` where useful
- Run focused tests first
- Then normal broader verification required by task
- Do NOT automatically broaden implementation scope

## Integration with Existing Skills

This skill COMPLEMENTS `obsidian-rl-repo-map` — it provides the *policy* for when and how much context to retrieve. The repo-map skill provides the *Graphify mechanics*. Do not duplicate Graphify commands here.

## Smoke Test Cases

### Case A: Exact-file mechanical task (e.g., fix typo in README)
- Retrieval invoked: NO (or minimal)
- Files: Only the target file
- Rationale: User knows exact location; no cross-module understanding needed

### Case B: "trace Trend signal to execution/accounting"
- Retrieval invoked: YES
- Graphify query: `graphify query "Trend signal to PortfolioEngine Ledger execution" --budget 2000`
- Files selected: `src/obsidian_rl/signals/trend.py`, `src/obsidian_rl/portfolio/engine.py`, `src/obsidian_rl/ledger/ledger.py`, `src/obsidian_rl/live/paper_trader.py`, `tests/evaluation/test_trend_backtest.py`
- Why: Direct data flow from signal → portfolio → ledger → paper execution
- Unnecessary avoided: Full GRAPH_REPORT.md, legacy/, unrelated strategies, dashboard queries

### Case C: "investigate restart accounting defect"
- Retrieval invoked: YES
- Graphify query: `graphify query "PaperTrader restart recovery Ledger funding state" --budget 2000`
- Files selected: `src/obsidian_rl/live/paper_trader.py` (restore/restart logic), `src/obsidian_rl/ledger/ledger.py` (restore_state, get_closure), `src/obsidian_rl/portfolio/engine.py` (PortfolioState), `tests/test_live_accounting.py` (restart tests), `tests/test_paper_trader.py` (restart recovery tests)
- Why: Direct restart/recovery paths for accounting state
- Unnecessary avoided: Signal generation, feature pipeline, training code, Alpha Gate, legacy backtests

## Verification Commands

```bash
# Case A - no retrieval needed
# (mechanical edit - just read target file)

# Case B - trace Trend signal
graphify query "Trend signal to PortfolioEngine Ledger execution" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000

# Case C - restart accounting
graphify query "PaperTrader restart recovery Ledger funding state" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000
```