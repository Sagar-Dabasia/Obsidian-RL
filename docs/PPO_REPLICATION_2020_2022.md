# Frozen PPO Replication 2020-2022 Plan and Report

## Fixed Protocol

- **Asset / Resolution**: BTCUSDT 15-minute candles
- **Development Data Range**: `2020-01-01T00:00:00Z` through `2022-11-26T23:45:00Z`
- **One-Time Confirmation Range**: `2022-11-27T00:00:00Z` through `2022-12-31T23:45:00Z`
- **Train Window**: 365 days
- **Inner Evaluation Window**: 60 days
- **Outer Validation Window**: 90 days
- **Step**: 180 days
- **Expected Folds**: 4
- **Seeds**: 42, 7, 23, 101, 202
- **Timesteps per Fold**: 100,000
- **n_envs**: 1
- **Device**: auto
- **Turnover Penalty**: 0.0 bps
- **Ensemble Method**: Median of 5 seed-policy targets (`ensemble_target = median(target_1, ..., target_5)`)

## Eligibility Criteria
An ensemble is eligible for confirmation if and only if all of the following hold:
1. Positive base return in at least 3 of 4 outer validation folds;
2. Worst base fold return is strictly above -5% (-0.05);
3. Mean base return across 4 folds is positive;
4. Mean costs2x return across 4 folds is positive;
5. Mean delay1 return across 4 folds is positive;
6. Mean max drawdown across 4 folds is at most 15% (0.15);
7. Ensemble turnover is below the median individual-seed turnover for the 2020-2022 dataset.

## One-Time Confirmation Criteria
If eligible, evaluate the final fold (Fold 3) 5-seed ensemble once on the confirmation window (`2022-11-27T00:00:00Z` through `2022-12-31T23:45:00Z`).
Confirmation passes if and only if:
1. Base net return is positive;
2. Costs2x net return is positive;
3. Delay1 net return is positive;
4. Base max drawdown is at most 10% (0.10);
5. Every metric is finite.

## Predefined Classifications
- **FROZEN REPLICATION PASSES**: Eligible and passes confirmation.
- **FROZEN REPLICATION FAILS OUTER VALIDATION**: Fails eligibility criteria.
- **FROZEN REPLICATION FAILS CONFIRMATION**: Eligible but fails confirmation window.
- **EXPERIMENT INVALID**: Protocol violation, schema error, or data corruption.

## Safety & Boundaries
- 2025 confirmation window and central reserved holdout (`2025-07-01T00:00:00Z` onwards) remain strictly untouched.
- No model tuning, hyperparameter adjustments, or best-seed selection permitted.
