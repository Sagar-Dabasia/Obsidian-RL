# Frozen PPO Replication 2020-2022 Plan and Report

## Fixed Protocol & Dataset Boundaries

- **Asset / Resolution**: BTCUSDT 15-minute candles
- **Development Data Range**: `2020-01-01T00:00:00Z` to `2022-11-26T23:45:00Z` (101,856 candles)
- **One-Time Confirmation Range**: `2022-11-27T00:00:00Z` to `2022-12-31T23:45:00Z` (3,265 candles)
- **Total Historical Range Loaded**: `2020-01-01T00:00:00Z` to `2022-12-31T00:00:00Z` (105,121 candles)
- **Candle Validation**: `rows=105121, dups=0, gaps=0, missing=0, errors=[]`
- **Isolation Confirmation**: Data from 2023 onward, the 2025 confirmation window, and the central reserved holdout (`2025-07-01T00:00:00Z` onwards) were completely UNTOUCHED.

## Training Execution & Artifacts

- **Command**:
  ```bash
  python -m obsidian_rl.cli walk-forward \
    --data-start 2020-01-01T00:00:00+00:00 \
    --holdout-start 2022-11-27T00:00:00+00:00 \
    --train-days 365 \
    --inner-eval-days 60 \
    --val-days 90 \
    --step-days 180 \
    --seeds 42,7,23,101,202 \
    --timesteps 100000 \
    --n-envs 1 \
    --device auto \
    --turnover-penalty-bps 0.0
  ```
- **Exit Code**: 0
- **Walk-Forward Experiment ID**: `wf-20260722-183747-963746-cfa04865`
- **Models Registered**: 20 models registered under `models/wf-20260722-183747-963746-cfa04865-f{0..3}-s{42,7,23,101,202}` with verified checksums and feature schemas.

## Ensemble Outer Validation Results

| Fold | Base Net Return | Costs2x Net Return | Delay1 Net Return | Max Drawdown | Sharpe | Turnover | Trades |
|---|---|---|---|---|---|---|---|
| Fold 0 | -11.75% (-0.117451) | -11.83% (-0.118320) | -12.22% (-0.122178) | 29.07% | -1.0067 | 20,228.4 | 98 |
| Fold 1 | +9.52% (+0.095241) | +9.44% (+0.094401) | +9.61% (+0.096123) | 12.44% | +1.1200 | 16,806.6 | 53 |
| Fold 2 | -11.83% (-0.118279) | -11.90% (-0.118991) | -12.16% (-0.121614) | 24.65% | -1.5671 | 15,492.6 | 57 |
| Fold 3 | -9.08% (-0.090823) | -9.37% (-0.093744) | -9.64% (-0.096442) | 14.30% | -1.3187 | 34,340.3 | 49 |
| **Mean** | **-5.78% (-0.057828)** | **-5.92% (-0.059164)** | **-6.11% (-0.061053)** | **20.12%** | **-0.6931** | **21,717.0** | **64.3** |

## Eligibility Verification

| Criterion | Target | Measured | Result |
|---|---|---|---|
| 1. Positive outer folds | ≥ 3 of 4 | 1 of 4 (Fold 1 only) | ❌ FAIL |
| 2. Worst base fold return | > -5.0% | -11.83% (Fold 2) | ❌ FAIL |
| 3. Mean base net return | > 0.0% | -5.78% | ❌ FAIL |
| 4. Mean costs2x net return | > 0.0% | -5.92% | ❌ FAIL |
| 5. Mean delay1 net return | > 0.0% | -6.11% | ❌ FAIL |
| 6. Mean max drawdown | ≤ 15.0% | 20.12% | ❌ FAIL |
| 7. Ensemble turnover | < indiv median | 21,716.99 < 54,312.91 | ✅ PASS |
| **OVERALL ELIGIBILITY** | **All pass** | **6 of 7 Failed** | **NOT ELIGIBLE** |

## One-Time Confirmation

Per protocol rules, because the replication failed eligibility criteria, the confirmation window (`2022-11-27T00:00:00Z` through `2022-12-31T23:45:00Z`) was **NOT ACCESSED OR LOADED**.

## Final Classification & Conclusion

**FROZEN REPLICATION FAILS OUTER VALIDATION**

### Conclusion & Hypothesis Retirement
The 5-seed median PPO policy ensemble failed outer validation across the 2020–2022 historical replication period, exhibiting negative mean returns (-5.78%), severe drawdown (20.12% mean, up to 29.07%), and failing 3 of 4 outer validation folds.

In accordance with protocol rules, the current PPO median-ensemble hypothesis is **RETIRED**. No further hyperparameter tuning, strategy variations, or re-runs are proposed.
