# PPO Seed Ensemble Screen 01 Plan and Report

## Fixed Method & Pre-Registration Plan

- **Penalties**: 0.0, 2.5, 5.0 bps
- **Folds**: 0, 1, 2
- **Seeds**: 42, 7, 23, 101, 202 (all 5 required per ensemble)
- **Aggregation**: Median of five seed-policy targets (`ensemble_target = median(target_1, ..., target_5)`)
- **Inference**: Deterministic inference only (`predict(obs, deterministic=True)`). Members reset before evaluation.
- **Model Resolution**: Resolved strictly from registered metadata (`models/`) and walk-forward JSON artifacts (`artifacts/walkforward/`).

## Eligibility Criteria
An ensemble penalty qualifies as eligible if and only if all of the following hold:
1. Positive base return in at least 2 of 3 folds;
2. Worst base fold return is strictly above -5% (-0.05);
3. Mean base return across 3 folds is positive;
4. Mean costs2x return across 3 folds is positive;
5. Mean delay1 return across 3 folds is positive;
6. Mean max drawdown across 3 folds is at most 15% (0.15);
7. Ensemble turnover is no greater than the median individual-seed turnover for the same penalty.

## Selection & Confirmation Rules
- If multiple penalties qualify, rank by: (1) highest worst-fold base return, (2) lower turnover, (3) lower penalty.
- If no penalty qualifies, the confirmation dataset is NOT accessed.
- If one penalty qualifies, evaluate its Fold 2 5-seed ensemble ONCE on `2025-05-27T00:00:00Z` through `2025-06-30T23:45:00Z`.
- Confirmation passes if all metrics are finite, net returns for base, costs2x, and delay1 are each positive, and base max drawdown is at most 10% (0.10).
- The central reserved holdout (`2025-07-01T00:00:00Z` onwards) remains completely untouched.
