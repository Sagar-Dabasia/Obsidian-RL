# Evaluation AGENTS.md
These rules apply ONLY within src/obsidian_rl/evaluation/.
Root AGENTS.md invariants remain absolute; this file adds domain-specific constraints.

## Chronological Validation
- Walk-forward only: train on [0, t), validate on [t, t+Delta), never reverse.
- Each fold must advance in time; no overlapping validation windows into train.

## Next-Bar Timing
- Signal at bar T executes at T+1 open; no same-bar fill.
- CostModel applied at execution bar, not signal bar.
- Warm-up bars excluded from metrics; causality verified by graphify path "signal evaluation".

## Holdout Isolation
- Frozen windows (CONFIRMATION, FINAL_HOLDOUT) are read-only; no parameter tuning on them.
- Access requires explicit user authorization per task scope.
- No leakage from holdout into feature engineering or model selection.

## Full Cost Stack
- Include all costs applicable to the frozen experiment/instrument contract.
- Current crypto perpetual evaluation uses fee/spread/slippage/funding where applicable.
- Never invent new cost semantics.
- New cost components require explicit implementation + preregistration/evidence.

## Preserve Negative Evidence
- Failed strategies, overfit detections, leakage findings -> keep in reports.
- Do not filter "bad" results from evaluation output.
- Negative result is evidence of boundary, not failure.

## No Legacy Revival
- Cycle-1 PPO/median-seed/standalone Alpha Gate are archived.
- Do not import evaluation logic from legacy/.
- Graphify query "Cycle-1 evaluation" before reusing any pattern.
