# PPO Seed Stability Pilot 01 Plan and Execution Report

## Overview

This report documents the PPO Seed Stability Pilot 01 evaluation across 5 random seeds (42, 7, 23, 101, 202) under the hardened nested walk-forward protocol.

---

## 1. Experiment Specification

- **Asset / Interval**: BTCUSDT 15-minute candles
- **Data Period**: 2023-01-01T00:00:00Z (`1672531200000` ms) to 2025-06-30T23:45:00Z (`1751327100000` ms)
- **Holdout Start**: Reserved boundary at 2025-07-01T00:00:00Z (`1751328000000` ms) — Strictly Untouched
- **Train Window**: 365 days (`35,040` candles)
- **First Purge Gap**: 15 days (`1,440` candles, `WARMUP_ROWS`)
- **Inner Evaluation Window**: 60 days (`5,760` candles)
- **Second Purge Gap**: 15 days (`1,440` candles, `WARMUP_ROWS`)
- **Outer Validation Window**: 90 days (`8,640` candles)
- **Step Size**: 180 days
- **Seeds Evaluated**: 42, 7, 23, 101, 202
- **Timesteps per Fold**: 100,000
- **Environments (`n_envs`)**: 1
- **Device**: `auto` (resolved to `cpu`)
- **Cost Model**: Default pessimism (5.0 bps fee, 0.5 bps half-spread, 1.0 bps slippage)
- **Scenarios Evaluated**: `base`, `costs2x`, `delay1`

---

## 2. Command & Artifact Provenance

### Execution Command
```bash
python -m obsidian_rl.cli walk-forward \
  --data-start 2023-01-01T00:00:00+00:00 \
  --holdout-start 2025-07-01T00:00:00+00:00 \
  --train-days 365 \
  --inner-eval-days 60 \
  --val-days 90 \
  --step-days 180 \
  --seeds 7,23,101,202 \
  --timesteps 100000 \
  --n-envs 1 \
  --device auto
```

- **Seed 42 Artifact**: [artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.json](file:///D:/Obsidian-RL/artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.json)
- **Seeds 7, 23, 101, 202 Artifact**: [artifacts/walkforward/wf-20260722-161119-636691-02223b83.json](file:///D:/Obsidian-RL/artifacts/walkforward/wf-20260722-161119-636691-02223b83.json)
- **Total Training Runtime**: ~202s (seed 42) + ~973s (seeds 7, 23, 101, 202) = ~1,175 seconds (~19.6 minutes)
- **Device**: CPU (`torch 2.13.0+cpu`)

---

## 3. Individual Seed Results (`base` Scenario)

### Seed 42
- **Checkpoints Selected**: Fold 0: 50,000 | Fold 1: 100,000 | Fold 2: 100,000
- **Fold Returns**: Fold 0: `-0.065675` (-6.57%) | Fold 1: `+0.282421` (+28.24%) | Fold 2: `+0.147486` (+14.75%)
- **Mean Net Return**: `+0.121411` (+12.14%) | **Std**: `0.175507` | **Worst Fold**: `-0.065675` (-6.57%)
- **Mean Sharpe**: `1.870838` | **Mean Max DD**: `0.092751` (9.28%)
- **Mean Turnover**: `31,597.92` | **Mean Trades**: `122.0`
- **Costs2x Mean Return**: `+0.119329` (+11.93%) | **Delay1 Mean Return**: `+0.121082` (+12.11%)

### Seed 7
- **Checkpoints Selected**: Fold 0: 100,000 | Fold 1: 100,000 | Fold 2: 100,000
- **Fold Returns**: Fold 0: `-0.046928` (-4.69%) | Fold 1: `-0.232214` (-23.22%) | Fold 2: `-0.074979` (-7.50%)
- **Mean Net Return**: `-0.118041` (-11.80%) | **Std**: `0.099867` | **Worst Fold**: `-0.232214` (-23.22%)
- **Mean Sharpe**: `-5.697818` | **Mean Max DD**: `0.140455` (14.05%)
- **Mean Turnover**: `455,056.64` | **Mean Trades**: `157.3`
- **Costs2x Mean Return**: `-0.146550` (-14.65%) | **Delay1 Mean Return**: `-0.108324` (-10.83%)

### Seed 23
- **Checkpoints Selected**: Fold 0: 100,000 | Fold 1: 100,000 | Fold 2: 100,000
- **Fold Returns**: Fold 0: `+0.041268` (+4.13%) | Fold 1: `-0.091948` (-9.19%) | Fold 2: `-0.096511` (-9.65%)
- **Mean Net Return**: `-0.049063` (-4.91%) | **Std**: `0.078263` | **Worst Fold**: `-0.096511` (-9.65%)
- **Mean Sharpe**: `-5.772023` | **Mean Max DD**: `0.103853` (10.39%)
- **Mean Turnover**: `1,000,218.04` | **Mean Trades**: `151.0`
- **Costs2x Mean Return**: `-0.111350` (-11.14%) | **Delay1 Mean Return**: `-0.056055` (-5.61%)

### Seed 101
- **Checkpoints Selected**: Fold 0: 100,000 | Fold 1: 100,000 | Fold 2: 100,000
- **Fold Returns**: Fold 0: `+0.016788` (+1.68%) | Fold 1: `+0.280570` (+28.06%) | Fold 2: `-0.047370` (-4.74%)
- **Mean Net Return**: `+0.083329` (+8.33%) | **Std**: `0.173801` | **Worst Fold**: `-0.047370` (-4.74%)
- **Mean Sharpe**: `1.114762` | **Mean Max DD**: `0.103853` (10.39%)
- **Mean Turnover**: `243,662.30` | **Mean Trades**: `73.0`
- **Costs2x Mean Return**: `+0.052979` (+5.30%) | **Delay1 Mean Return**: `+0.079372` (+7.94%)

### Seed 202
- **Checkpoints Selected**: Fold 0: 50,000 | Fold 1: 100,000 | Fold 2: 100,000
- **Fold Returns**: Fold 0: `-0.065675` (-6.57%) | Fold 1: `+0.280570` (+28.06%) | Fold 2: `+0.147794` (+14.78%)
- **Mean Net Return**: `+0.120896` (+12.09%) | **Std**: `0.174682` | **Worst Fold**: `-0.065675` (-6.57%)
- **Mean Sharpe**: `1.873995` | **Mean Max DD**: `0.092751` (9.28%)
- **Mean Turnover**: `24,913.43` | **Mean Trades**: `121.3`
- **Costs2x Mean Return**: `+0.119342` (+11.93%) | **Delay1 Mean Return**: `+0.121188` (+12.12%)

---

## 4. Combined 5-Seed Summary Statistics

| Metric | Empirical Value |
|---|---|
| **Seeds Completed** | 5 (42, 7, 23, 101, 202) |
| **Total Fold-Seed Evaluations (`base`)** | 15 (5 seeds x 3 folds) |
| **Positive Mean-Return Seeds** | 3 of 5 (60.0%) (Seeds 42, 101, 202) |
| **Positive Fold-Seed Results** | 7 of 15 (46.67%) |
| **Median Mean Net Return (`base`)** | **`+0.083329`** (+8.33%) |
| **Range of Mean Net Returns** | `-0.118041` (-11.80%) to `+0.121411` (+12.14%) |
| **Median Worst-Fold Return** | **`-0.065675`** (-6.57%) |
| **Median Sharpe Ratio** | **`1.114762`** |
| **Median Max Drawdown** | **`0.103853`** (10.39%) |
| **Costs2x Median Mean Return** | **`+0.052979`** (+5.30%) |
| **Delay1 Median Mean Return** | **`+0.079372`** (+7.94%) |

---

## 5. Predefined Classification Screen

The seed stability protocol evaluates four mandatory criteria for a `SEED-STABLE SIGNAL`:
1. At least 4 of 5 seeds have positive mean base return: **FAILED** (3 of 5 positive: Seeds 42, 101, 202 positive; Seeds 7, 23 negative)
2. Median worst-fold return is above -10%: **PASSED** (-6.57% > -10.0%)
3. Median mean return remains positive under costs2x: **PASSED** (+5.30% > 0)
4. Median mean return remains positive under delay1: **PASSED** (+7.94% > 0)

### Classification
SEED-UNSTABLE SIGNAL

*Note: This classification represents an empirical research screen evaluating seed sensitivity, not proof of profitability or a recommendation of any individual seed.*

---

## 6. Verification and Invariant Confirmation

1. **Finite Metrics**: Confirmed that all metrics across all 45 evaluation rows (5 seeds x 3 folds x 3 scenarios) are finite floats. Zero `NaN`, `Inf`, or `null` values exist.
2. **Outer Validation Isolation**: Confirmed that checkpoint selection (`TrackingEvalCallback`) used only `(train, inner_eval)` slices. `outer_val` was strictly isolated for final strategy comparison.
3. **No Downstream Promotion/Holdout Access**: Candidate evaluation, promotion (`CHAMPION.json`), and central reserved holdout (`HOLDOUT_STATE.json`) were NOT run or accessed.
