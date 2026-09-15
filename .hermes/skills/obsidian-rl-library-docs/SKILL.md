---
name: obsidian-rl-library-docs
description: Version-specific library documentation retrieval for Obsidian-RL using Context7 MCP. Use when third-party API behavior matters for coding tasks.
category: software-development
version: 1.1.0
author: Hermes Agent
tags:
  - obsidian-rl
  - library-docs
  - context7
  - mcp
  - version-specific
---

# Obsidian-RL Library Documentation Skill

This skill teaches Hermes to retrieve exact version-matched documentation for third-party libraries used in Obsidian-RL, using the Context7 MCP server.

**CRITICAL**: Installed code + repo source/tests remain authoritative. Context7 documentation is advisory evidence only.

## When to Use Retrieval

### DO NOT retrieve for:
- Pure repo-internal logic (no third-party API involved)
- Mechanical edits where API is already known
- User has already provided exact API usage

### USE retrieval for:
- Third-party library API behavior is uncertain
- Cross-version compatibility questions
- Unfamiliar library APIs
- Debugging library-specific issues
- Financial/accounting library usage (pandas, numpy, pyarrow, gymnasium, stable-baselines3, lightgbm, scikit-learn, websockets, pydantic, streamlit)

## Retrieval Workflow (MANDATORY ORDER)

1. **Resolve exact installed version** — From `pyproject.toml` + `D:/Obsidian-RL/.venv/Scripts/pip list` or `uv.lock` (if present). Record `INSTALLED_VERSION`.
2. **Attempt EXPLICIT version-pinned Context7 lookup** — Use `/owner/library@<exact-version>` format or version ID returned by `resolve_library_id` with version specified.
3. **If exact version unavailable on Context7**:
   - Mark `CONTEXT7_EXACT_MATCH = NO`
   - Context7 may be used only for orientation/navigation
   - It MUST NOT justify an implementation/API claim
4. **Exact-version fallback (AUTHORITATIVE)**:
   - Inspect the locally installed package using:
     - `importlib.metadata.version("<package>")`
     - Module/package source: `D:/Obsidian-RL/.venv/Lib/site-packages/<package>/`
     - `inspect.signature` / `inspect.getsource` where appropriate
     - `pydoc` / `help`
     - Package-bundled docs / type hints (`.pyi` files)
   - Local installed package IS authoritative for exact API behavior
   - Record `LOCAL_SOURCE_VERIFIED = YES`
5. **Same-major/minor Context7 docs** may help navigation only.
6. **Major-version mismatch** is HIGH-RISK and MUST trigger local-source verification before ANY coding.

## Context7 MCP Tool Whitelist (ONLY these tools exposed)

- `mcp__context7__resolve_library_id` — Resolve package name to Context7 library ID
- `mcp__context7__query_docs` — Retrieve version-specific documentation

**Disabled (not exposed to Hermes):**
- `mcp__context7__list_prompts`
- `mcp__context7__list_resources`
- `mcp__context7__read_resource`

## Hard Rules

- **NEVER send to Context7**: Repository source code, secrets, credentials, market data, DB contents, experiment results, private runtime state
- **Context7 docs are advisory** — Installed code + repo source/tests remain authoritative
- **Exact version priority** — If exact installed version unavailable on Context7, clearly mark mismatch and inspect local package source
- **If Context7 unavailable/rate-limited** — Fall back to official/local package docs/source; never guess
- **Selective context budget** — Query narrow topics only (≤3 calls per library); do not dump large doc sets
- **No auto dependency upgrades** — Documentation lookup does not imply version changes
- **Never infer compatibility** merely because an API name still exists
- **Before any third-party-library edit**, Hermes MUST record:
  - `INSTALLED_VERSION`
  - `CONTEXT7_VERSION_USED`
  - `EXACT_VERSION_MATCH YES/NO`
  - `LOCAL_SOURCE_VERIFIED YES/NO`
- **If neither exact docs nor local installed source can establish behavior**: STOP instead of guessing

## Installed Versions (from pyproject.toml + venv)

| Library | Pinned Version | Category |
|---------|---------------|----------|
| numpy | 2.4.6 | Core runtime |
| pandas | 3.0.3 | Core runtime |
| pyarrow | 24.0.0 | Core runtime |
| requests | 2.34.2 | Core runtime |
| websockets | 16.1 | Core runtime |
| pydantic-settings | 2.14.2 | Core runtime |
| gymnasium | 1.3.0 | RL optional |
| stable-baselines3 | 2.9.0 | RL optional |
| lightgbm | 4.7.0 | Gate optional |
| scikit-learn | 1.9.0 | Gate optional |
| streamlit | 1.59.2 | Dashboard optional |
| pytest | 9.1.1 | Dev |
| ruff | 0.15.22 | Dev |
| mypy | 2.3.0 | Dev |

## Version Mismatch Handling (STRICT)

If Context7 returns docs for different version than installed:
1. **Clearly state**: `VERSION MISMATCH: Context7 returned vX.Y, installed is vA.B`
2. **Mark**: `CONTEXT7_EXACT_MATCH = NO`
3. **For minor/patch mismatch** — Context7 may orient navigation ONLY; local source REQUIRED for API claims
4. **For major-version mismatch** — Context7 is HIGH-RISK; MUST verify locally before coding
5. **Never label mismatched docs** "compatible" or "stable enough"
6. **Local installed package** is the source of truth for exact API behavior

## Integration with Other Skills

- **obsidian-rl-repo-map**: Use Graphify for internal code navigation
- **obsidian-rl-selective-context**: Apply retrieval budgets and source priority rules
- This skill ONLY handles third-party library documentation

## Smoke Test Libraries (Version-Mismatch Hardened)

1. **numpy 2.4.6** → Context7 ID: `/numpy/numpy` (versions: v2.3.1, v2.1.3) — **NO EXACT MATCH** — minor mismatch, MUST verify locally
2. **pandas 3.0.3** → Context7 ID: `/pandas-dev/pandas` (versions: v1.3.0) — **NO EXACT MATCH** — **MAJOR MISMATCH**, MUST verify locally, Context7 cannot authorize code
3. **gymnasium 1.3.0** → Context7 ID: `/farama-foundation/gymnasium` (versions: v1.2.3) — **NO EXACT MATCH** — minor mismatch, MUST verify locally

## Verification Commands

```bash
# Verify Context7 MCP loaded
hermes mcp list

# Check installed versions
D:/Obsidian-RL/.venv/Scripts/pip list | grep -E "numpy|pandas|gymnasium|pydantic|requests|websockets|pyarrow|stable-baselines3|lightgbm|scikit-learn|streamlit"

# Local package verification (example)
D:/Obsidian-RL/.venv/Scripts/python -c "import numpy; print(numpy.__version__); import inspect; print(inspect.signature(numpy.array))"
D:/Obsidian-RL/.venv/Scripts/python -c "import pandas; print(pandas.__version__); print(pandas.DataFrame.__init__.__doc__[:200])"
D:/Obsidian-RL/.venv/Scripts/python -c "import gymnasium; print(gymnasium.__version__); import inspect; print(inspect.signature(gymnasium.Env.reset))"
```