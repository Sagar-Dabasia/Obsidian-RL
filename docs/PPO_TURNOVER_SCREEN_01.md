# PPO Turnover Regularization Screen 01 Plan and Report

## Fixed Experiment Plan

- **Asset / Resolution**: BTCUSDT 15-minute candles
- **Data Start**: 2023-01-01T00:00:00Z
- **Reserved Holdout Start**: 2025-07-01T00:00:00Z
- **Train Window**: 365 days
- **Inner Evaluation Window**: 60 days
- **Outer Validation Window**: 90 days
- **Step**: 180 days
- **Seeds**: 42, 7, 23, 101, 202
- **Timesteps per fold**: 100,000
- **n_envs**: 1
- **Device**: auto
- **Penalties Tested**: 2.5 bps, 5.0 bps (compared against 0.0 bps baseline from seed stability pilot)
- **Baselines & Scenarios**: base, costs2x, delay1
- **Holdout Access**: strictly prohibited

## Execution & Protocol Confirmation

- Folds use nested chronological structure (train -> purge -> inner eval -> purge -> outer validation).
- Outer validation candles are never used for PPO checkpoint selection (`EvalCallback` evaluates strictly on inner eval).
- Zero-penalty baseline results are loaded from existing walk-forward artifacts.
- No model promotion or candidate evaluation occurs.
