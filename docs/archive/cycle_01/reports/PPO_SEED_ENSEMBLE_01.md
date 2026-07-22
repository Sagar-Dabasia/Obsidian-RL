# PPO Seed Ensemble Screen 01 — Plan and Report

## Fixed Method & Pre-Registration Plan

- **Penalties**: 0.0, 2.5, 5.0 bps
- **Folds**: 0, 1, 2
- **Seeds**: 42, 7, 23, 101, 202 (all 5 required per ensemble)
- **Aggregation**: `ensemble_target = median(target_1, ..., target_5)`
- **Inference**: Deterministic only (`predict(obs, deterministic=True)`). Members reset before evaluation.
- **Model Resolution**: Resolved from registered metadata (`models/METADATA.json`) and walk-forward JSON artifacts.

## Artifacts and Model IDs Used

### Walk-Forward Artifacts (Individual Seeds)
| Penalty | Artifact |
|---|---|
| 0.0 bps | `wf-20260722-160014-022860-7a725ec7.json` (seed 42) |
| 0.0 bps | `wf-20260722-161119-636691-02223b83.json` (seeds 7, 23, 101, 202) |
| 2.5 bps | `wf-20260722-170718-091601-tp2.5-5eaff12a.json` |
| 5.0 bps | `wf-20260722-172239-240346-tp5.0-8d04a46e.json` |

### Model Directories (45 total, 3 penalties × 3 folds × 5 seeds)
All models resolved successfully from `models/` via registered METADATA.json.
No missing or incompatible models.

## Ensemble Outer Validation Results

| Metric | 0.0 bps Ensemble | 2.5 bps Ensemble | 5.0 bps Ensemble |
|---|---|---|---|
| **Positive outer folds (of 3)** | 3/3 | 2/3 | 2/3 |
| **Mean base return** | +14.38% | +10.29% | +13.91% |
| **Worst base fold** | +0.35% | -1.32% | -0.25% |
| **Mean costs2x return** | +14.28% | +9.29% | +12.76% |
| **Mean delay1 return** | +14.42% | +8.91% | +13.17% |
| **Mean max drawdown** | 9.43% | 8.06% | 6.50% |
| **Mean ensemble turnover** | 14,362 | 177,049 | 180,161 |

## Individual-vs-Ensemble Turnover & Stability

| Penalty | Median Indiv-Seed Turnover | Ensemble Turnover | Ratio |
|---|---|---|---|
| 0.0 bps | 243,662 | 14,362 | 0.059× (94.1% reduction) |
| 2.5 bps | 151,682 | 177,049 | 1.167× (exceeds individual) |
| 5.0 bps | 105,476 | 180,161 | 1.708× (exceeds individual) |

The 0.0 bps ensemble achieves a dramatic 94% turnover reduction versus the median individual seed.  The 2.5 and 5.0 bps ensembles paradoxically increase turnover above the individual seed median — the regularized policies disagree more on specific targets, causing the ensemble median to oscillate.

## Eligibility Checks

| Criterion | 0.0 bps | 2.5 bps | 5.0 bps |
|---|---|---|---|
| Positive base return ≥ 2/3 folds | ✅ 3/3 | ✅ 2/3 | ✅ 2/3 |
| Worst base fold > -5% | ✅ +0.35% | ✅ -1.32% | ✅ -0.25% |
| Mean base return > 0 | ✅ +14.38% | ✅ +10.29% | ✅ +13.91% |
| Mean costs2x return > 0 | ✅ +14.28% | ✅ +9.29% | ✅ +12.76% |
| Mean delay1 return > 0 | ✅ +14.42% | ✅ +8.91% | ✅ +13.17% |
| Mean max drawdown ≤ 15% | ✅ 9.43% | ✅ 8.06% | ✅ 6.50% |
| Ensemble turnover ≤ indiv median | ✅ 14,362 ≤ 243,662 | ❌ 177,049 > 151,682 | ❌ 180,161 > 105,476 |
| **ELIGIBLE** | **YES** | **NO** | **NO** |

## Selected Penalty

**0.0 bps** — the only eligible penalty.

## One-Time Development Confirmation

### Confirmation Window Validation
- **Window**: 2025-05-27T00:00:00Z through 2025-06-30T23:45:00Z
- **Begins after Fold 2 outer validation end**: ✅ (Fold 2 outer val ends 2025-05-26T23:45:00Z)
- **Ends before final holdout**: ✅ (holdout starts 2025-07-01T00:00:00Z)
- **Never appeared in any fold evaluation**: ✅ confirmed
- **Continuous**: ✅ 3,360 candles
- **Confirmation dataset SHA-256**: `9db02ed63263df8760ffd978037c6b7e41532158e4d891f79715a039a08fc91c`

### Confirmation Results (0.0 bps, Fold 2, 5-seed ensemble)

| Scenario | Net Return | Max Drawdown | Sharpe |
|---|---|---|---|
| base | -0.6248% | 5.56% | -0.477 |
| costs2x | -0.6954% | 5.56% | -0.502 |
| delay1 | -0.7281% | 5.55% | -0.443 |

### Confirmation Verdict
- All metrics finite: ✅
- Base, costs2x, delay1 returns each positive: ❌ (all three negative)
- Base max drawdown ≤ 10%: ✅ (5.56%)
- **CONFIRMATION FAILED**: returns are negative for all three scenarios.

## Protocol Confirmations

- Outer validation was never used for PPO checkpoint selection (EvalCallback evaluated strictly on inner evaluation window).
- All metrics across all folds, seeds, and scenarios are finite.
- No candidate evaluation, promotion, or holdout access occurred.
- Confirmation data was accessed only because 0.0 bps qualified as eligible.
- The final holdout (2025-07-01T00:00:00Z onwards) was NOT touched.

## Overall Classification

**ENSEMBLE IMPROVES VALIDATION BUT FAILS CONFIRMATION**

The 0.0 bps 5-seed median ensemble demonstrated strong outer-validation performance (+14.38% mean, +0.35% worst fold, 94% turnover reduction), passed all 7 eligibility criteria, but failed the one-time confirmation window with small negative returns across all three scenarios (-0.62% base, -0.70% costs2x, -0.73% delay1).
