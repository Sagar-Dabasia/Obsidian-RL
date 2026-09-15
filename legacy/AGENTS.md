# Legacy AGENTS.md
These rules apply ONLY within legacy/.
Root AGENTS.md invariants remain absolute; this file reinforces the quarantine.

## Archive Is Evidence Only
- legacy/ contains historical Cycle-1 artifacts: PPO, median-seed, standalone Alpha Gate.
- Files are evidence, NOT active code - never import, execute, or reference.
- Graphify queries "legacy portfolio", "Cycle-1 evaluation", "Cycle-1 PPO" before any work.

## No Active Imports
- Active code (src/, tests/, tools/) must never import legacy.* or from legacy.* import.
- Patch gate rejects any new import from legacy/.
- Legacy existence alone is not contamination; active import IS.

## No Revival
- Do not resurrect Cycle-1 patterns, configs, or training loops.
- Cycle-2 uses fresh architecture; no compatibility layer required.
- Negative findings from Cycle-1 are preserved as boundary evidence.
