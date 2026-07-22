# Alpha Gate Historical Pilot 01 Plan and Report

## Fixed Protocol

- **Asset / Resolution**: BTCUSDT 15-minute candles
- **Data Range**: `2020-01-01T00:00:00Z` through `2022-11-26T23:45:00Z` (101,856 candles)
- **Train Window**: 365 days
- **Inner Evaluation Window**: 60 days
- **Outer Validation Window**: 90 days
- **Step**: 180 days
- **Purge Gap**: WARMUP_ROWS (96 candles)
- **Expected Folds**: 4
- **Seed**: 42 fixed
- **Target**: Directional net-edge target (`signed_directional_net_edge`, horizon=16, cost=0.0013)
- **Cost Model**: Default CostModel (taker_fee=0.0005, half_spread=0.00005, slippage=0.0001)
- **Hyperparameters**: Default LightGBM booster settings (`objective="regression"`, `metric="l2"`, `learning_rate=0.05`, `num_leaves=31`, `min_data_in_leaf=50`). No tuning.

## Execution & Models

- **Command**: `python tools/alpha_gate_pilot.py`
- **Exit Code**: 0
- **Runtime**: ~35 seconds
- **Models Artifacts Saved**:
  - `artifacts/alpha_gate_pilot/alpha-gate-f0` (SHA-256 verified)
  - `artifacts/alpha_gate_pilot/alpha-gate-f1` (SHA-256 verified)
  - `artifacts/alpha_gate_pilot/alpha-gate-f2` (SHA-256 verified)
  - `artifacts/alpha_gate_pilot/alpha-gate-f3` (SHA-256 verified)

## Performance Comparison (4 Outer Folds, 2020–2022)

| Strategy | Positive Folds (of 4) | Mean Base Return | Worst Base Fold | Mean Costs2x Return | Mean Delay1 Return | Mean Sharpe | Mean Max DD | Passed Screen |
|---|---|---|---|---|---|---|---|---|
| **always-flat** | 0/4 | **+0.00%** | +0.00% | +0.00% | +0.00% | +0.0000 | **0.00%** | ❌ FAIL |
| **prior PPO ensemble** | 1/4 | **-5.78%** | -11.83% | -5.92% | -6.11% | -0.6931 | **20.12%** | ❌ FAIL |
| **buy-and-hold** | 1/4 | **-15.01%** | -25.77% | -15.13% | -14.87% | -1.0039 | **37.62%** | ❌ FAIL |
| **gated-regime-m0.0** | 0/4 | **-21.04%** | -25.30% | -42.38% | -25.51% | -2.6952 | **28.92%** | ❌ FAIL |
| **gate-direct-m0.0** | 0/4 | **-23.44%** | -33.99% | -45.65% | -22.88% | -1.5046 | **42.30%** | ❌ FAIL |
| **regime-momentum-0.01-0.002** | 0/4 | **-37.20%** | -50.56% | -58.33% | -39.99% | -3.3135 | **44.72%** | ❌ FAIL |
| **cooldown-momentum-0.005-0.001-8** | 0/4 | **-53.49%** | -61.66% | -69.73% | -51.33% | -5.7323 | **56.54%** | ❌ FAIL |
| **fixed-holding-0.005-16** | 0/4 | **-56.83%** | -79.47% | -72.18% | -55.43% | -5.2044 | **61.58%** | ❌ FAIL |
| **threshold-momentum-0.005** | 0/4 | **-75.31%** | -80.37% | -91.42% | -77.61% | -9.3110 | **76.48%** | ❌ FAIL |

## Eligibility Criteria Verification for Alpha Gate

### Gate-Direct (`gate-direct-m0.0`)
1. Positive outer folds ≥ 3: ❌ 0/4
2. Worst base fold > -5.0%: ❌ -33.99% (Fold 0)
3. Mean base return > 0.0%: ❌ -23.44%
4. Mean costs2x return > 0.0%: ❌ -45.65%
5. Mean delay1 return > 0.0%: ❌ -22.88%
6. Mean max drawdown ≤ 15.0%: ❌ 42.30%
7. All metrics finite: ✅ True
8. Outer validation isolated during training: ✅ True

### Gated Regime (`gated-regime-m0.0`)
1. Positive outer folds ≥ 3: ❌ 0/4
2. Worst base fold > -5.0%: ❌ -25.30%
3. Mean base return > 0.0%: ❌ -21.04%
4. Mean costs2x return > 0.0%: ❌ -42.38%
5. Mean delay1 return > 0.0%: ❌ -25.51%
6. Mean max drawdown ≤ 15.0%: ❌ 28.92%
7. All metrics finite: ✅ True
8. Outer validation isolated during training: ✅ True

## Safety & Boundary Confirmation

- **PPO Trained**: No (0 PPO models trained during this experiment).
- **Model Promotion**: None.
- **2022 Confirmation Window Accessed**: No (`2022-11-27` to `2022-12-31` was untouched).
- **2025 Confirmation Window Accessed**: No.
- **Final Holdout Accessed**: No (`2025-07-01` onwards was untouched).

## Verdict & Conclusion

**ALPHA GATE DEVELOPMENT SCREEN FAILS**

### Conclusion & Hypothesis Retirement
Neither `gate-direct-m0.0` nor `gated-regime-m0.0` met any of the positive return or drawdown criteria, losing -23.44% and -21.04% on average across the 4 outer validation folds with drawdowns up to 42.30%.

Per protocol rules, the fixed Alpha Gate hypothesis is **RETIRED**. No parameter tuning or further iterations are proposed.
