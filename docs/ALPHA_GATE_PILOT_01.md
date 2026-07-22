# Alpha Gate Historical Pilot 01 Plan and Report

## Fixed Protocol

- **Asset / Resolution**: BTCUSDT 15-minute candles
- **Data Range**: `2020-01-01T00:00:00Z` through `2022-11-26T23:45:00Z`
- **Train Window**: 365 days
- **Inner Evaluation Window**: 60 days
- **Outer Validation Window**: 90 days
- **Step**: 180 days
- **Purge Gap**: WARMUP_ROWS (96 candles)
- **Expected Folds**: 4
- **Seed**: 42 fixed
- **Target**: Directional net-edge target
- **Cost Model**: Default CostModel (taker_fee=0.0005, half_spread=0.00005, slippage=0.0001)
- **No Hyperparameter Search / Tuning**: Existing Alpha Gate default settings only.

## Predefined Development Screen Criteria
Alpha Gate passes the development screen if and only if at least one supported Alpha Gate strategy satisfies all of the following:
1. Positive base return in at least 3 of 4 outer validation folds;
2. Worst base fold return is strictly above -5% (-0.05);
3. Mean base return across 4 folds is positive;
4. Mean costs2x return across 4 folds is positive;
5. Mean delay1 return across 4 folds is positive;
6. Mean max drawdown across 4 folds is at most 15% (0.15);
7. All metrics are finite;
8. No outer-validation data was used during training or checkpoint selection.

## Predefined Verdicts
- **ALPHA GATE DEVELOPMENT SCREEN PASSES**: Meets all screen criteria.
- **ALPHA GATE DEVELOPMENT SCREEN FAILS**: Fails one or more screen criteria.
- **EXPERIMENT INVALID**: Protocol violation, schema error, or data corruption.

## Safety & Isolation Confirmations
- PPO training, model promotion, candidate evaluation, 2022 confirmation window, 2025 confirmation window, and the central reserved holdout (`2025-07-01T00:00:00Z` onwards) remain completely UNTOUCHED.
