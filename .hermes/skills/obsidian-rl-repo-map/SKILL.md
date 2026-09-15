---
name: obsidian-rl-repo-map
description: Graphify-backed repo navigation for Obsidian-RL. Use when doing architecture, debugging, or call-path questions.
category: software-development
version: 1.0.0
author: Hermes Agent
tags:
  - obsidian-rl
  - graphify
  - repo-map
  - architecture
  - navigation
---

# Obsidian-RL Graphify Repo Map Skill

This skill makes Graphify a reliable, token-efficient repo-navigation aid for Hermes to invoke before architecture/debugging work.

**CRITICAL**: Source code and Git history remain the absolute authority. Graphify is an optional navigation aid only.

## When to Use This Skill

Activate this skill for:
- Architecture questions (module relationships, data flow, call paths)
- Debugging tasks (finding where a symbol is defined/used, tracing execution paths)
- Locating relevant tests for a given module
- Understanding community structure and god nodes

Do NOT activate for:
- Mechanical edits (typos, formatting, simple renames)
- Tasks where the user already knows the exact file location
- Financial verification (graph is navigation, not proof)

## Graphify Commands

When graphify-out/graph.json exists, use these commands via terminal:

```bash
# Query for relevant subgraph (token-efficient)
graphify query "<question>" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000

# Find path between two nodes
graphify path "NodeA" "NodeB" --graph "D:/Obsidian-RL/graphify-out/graph.json"

# Explain a specific concept/node
graphify explain "ConceptName" --graph "D:/Obsidian-RL/graphify-out/graph.json"

# Find affected nodes (reverse traversal)
graphify affected "NodeName" --graph "D:/Obsidian-RL/graphify-out/graph.json"

# List architectural hubs
graphify god-nodes --graph "D:/Obsidian-RL/graphify-out/graph.json"

# Update graph after code changes (AST-only, no API cost)
graphify update "D:/Obsidian-RL" --code-only
```

## Required Behaviors

1. **Source code + Git remain authoritative** — Never treat inferred graph edges as proof of behavior. Always inspect actual source before editing.

2. **Query only relevant subgraph** — Use `graphify query` with focused questions and `--budget` to get token-efficient context. Do not read full GRAPH_REPORT.md unless query results are insufficient.

3. **Inspect actual source before editing** — Graphify shows where things are; you must read the actual files to understand them.

4. **Never use archived/legacy nodes as active implementation** — The graph includes legacy/archived code. Filter by `community` or check `src/` vs `legacy/` paths.

5. **Regenerate/update map when stale** — After code modifications, run `graphify update . --code-only` to keep the graph current.

6. **Fall back to normal source inspection if Graphify is unavailable** — If the CLI is not installed or graph.json is missing, use `search_files`, `read_file`, and standard grep/rg patterns.

## Smoke Verification

Before relying on the graph, verify:
- Graph build/update exits 0: `graphify update . --code-only`
- Query locating Trend signal path works
- Query locating PaperTrader/Ledger/accounting path works
- Query locating relevant tests works
- Generated graphify-out remains gitignored/untracked
- No secrets/data/artifacts indexed
- `git diff --check` passes
- Scope sentinel: no trading/research code touched

## Ignore Rules

The `.graphifyignore` file excludes:
- `.git/`, `graphify-out/cache/`
- `/data/`, `*.sqlite*`, `*.db`
- `*.zip`, `*.parquet`, `*.pkl`, `*.pt`, `*.pth`, `*.onnx`
- `.env*`, `_context_export/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`

These align with `.gitignore` for data, models, runtime artifacts, and secrets.

## Integration with Hermes

This skill is automatically available when working in the Obsidian-RL repository. The AGENTS.md file includes Graphify usage rules that Hermes follows.

## Verification Commands

```bash
# Verify graph build works
graphify update "D:/Obsidian-RL" --code-only

# Verify key queries
graphify query "Trend signal path" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000
graphify query "PaperTrader Ledger accounting" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000
graphify query "relevant tests for trend signal portfolio" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 2000

# Verify gitignore compliance
git check-ignore graphify-out/graph.json && echo "gitignored" || echo "NOT gitignored"

# Verify no secrets indexed
graphify query "secret" --graph "D:/Obsidian-RL/graphify-out/graph.json" --budget 500 || echo "no secrets found"
```