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

## Protocol Confirmations

- Outer validation was not used for PPO checkpoint selection (`EvalCallback` evaluated strictly on inner evaluation window).
- All metrics are finite across all folds, seeds, and scenarios.
- No candidate evaluation, promotion, or holdout access occurred.

## Screen 01 Comparative Results

| Metric / Scenario | 0.0 bps (Baseline) | 2.5 bps Penalty | 5.0 bps Penalty |
|---|---|---|---|
| **Positive Seeds (out of 5)** | 3/5 | 4/5 | 3/5 |
| **Positive Fold-Seed Runs (out of 15)** | 7/15 | 10/15 | 8/15 |
| **Median Seed Mean Return (base)** | +8.33% (+0.0833) | +6.60% (+0.0660) | +6.70% (+0.0670) |
| **Median Seed Worst-Fold Return** | -6.57% (-0.0657) | -12.39% (-0.1239) | -3.83% (-0.0383) |
| **Median Seed Sharpe** | +1.1148 | +0.6331 | +0.9216 |
| **Median Seed Max Drawdown** | 10.39% (0.1039) | 10.16% (0.1016) | 9.32% (0.0932) |
| **Median Seed Turnover** | 243,662.26 | 151,682.37 (-37.75%) | 105,475.52 (-56.71%) |
| **Median Seed Trade Count** | 122.0 | 94.7 | 121.7 |
| **Costs2x Median Return (seed means)** | +5.30% (+0.0530) | +4.42% (+0.0442) | +5.78% (+0.0578) |
| **Delay1 Median Return (seed means)** | +7.94% (+0.0794) | +6.36% (+0.0636) | +7.01% (+0.0701) |
| **Average Within-Fold Seed Range** | 0.2886 | 0.2955 | 0.2740 |

## Detailed Seed Breakdown (3-Fold Mean Returns)

### 0.0 bps (Baseline)
- Seed 7: -11.80% (Worst fold: -23.22%, Turnover: 455,056.6)
- Seed 23: -4.91% (Worst fold: -9.65%, Turnover: 1,000,218.0)
- Seed 42: +12.14% (Worst fold: -6.57%, Turnover: 31,597.9)
- Seed 101: +8.33% (Worst fold: -4.74%, Turnover: 243,662.3)
- Seed 202: +12.09% (Worst fold: -6.57%, Turnover: 24,913.4)

### 2.5 bps Penalty
- Seed 7: -9.62% (Worst fold: -23.22%, Turnover: 151,682.4)
- Seed 23: +6.60% (Worst fold: -12.39%, Turnover: 548,875.7)
- Seed 42: +14.79% (Worst fold: +1.46%, Turnover: 309,553.8)
- Seed 101: +4.57% (Worst fold: -14.54%, Turnover: 24,871.9)
- Seed 202: +15.65% (Worst fold: +4.13%, Turnover: 14,473.7)

### 5.0 bps Penalty
- Seed 7: -9.93% (Worst fold: -23.22%, Turnover: 25,319.9)
- Seed 23: -1.01% (Worst fold: -3.83%, Turnover: 636,970.9)
- Seed 42: +15.38% (Worst fold: +3.16%, Turnover: 105,475.5)
- Seed 101: +15.45% (Worst fold: +2.41%, Turnover: 17,880.8)
- Seed 202: +6.70% (Worst fold: -6.57%, Turnover: 128,167.5)

## Criteria Evaluation & Classification

### Criteria Checks for REGULARIZATION HELPS
1. **At least 4 of 5 positive seeds**: 2.5 bps passes (4/5), 5.0 bps fails (3/5).
2. **At least 9 of 15 positive fold-seed results**: 2.5 bps passes (10/15), 5.0 bps fails (8/15).
3. **Keeps positive costs2x and delay1 medians**: Both 2.5 bps and 5.0 bps pass.
4. **Reduces median turnover by at least 25% vs zero**: 2.5 bps passes (-37.75%), 5.0 bps passes (-56.71%).
5. **Improves median worst-fold return vs zero**: 2.5 bps fails (-12.39% vs -6.57%), 5.0 bps passes (-3.83% vs -6.57%).
6. **Does not reduce median base return by >25% vs zero**: Both 2.5 bps (-20.82%) and 5.0 bps (-19.59%) pass.

### Final Classification
- Neither tested penalty meets all 6 criteria for `REGULARIZATION HELPS` simultaneously.
- Turnover was meaningfully reduced by 37.75% (2.5 bps) and 56.71% (5.0 bps).
- Therefore, per the predefined classification rule, the outcome is **TRADE-OFF ONLY**.
- **Preferred Penalty**: none (cannot be named because no penalty met all criteria).
