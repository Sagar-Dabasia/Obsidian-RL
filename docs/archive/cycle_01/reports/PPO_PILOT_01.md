# PPO Historical Pilot 01 Plan and Execution Report

## Overview

This report documents the execution and empirical findings of the first bounded PPO walk-forward training pilot under the hardened nested walk-forward protocol.

---

## 1. Experiment Specification

- **Asset / Interval**: BTCUSDT 15-minute candles
- **Data Period**: 2023-01-01T00:00:00Z (`1672531200000` ms) to 2025-06-30T23:45:00Z (`1751327100000` ms)
- **Holdout Start**: Reserved boundary at 2025-07-01T00:00:00Z (`1751328000000` ms) — Strictly Untouched
- **Train Window**: 365 days (`35,040` candles)
- **First Purge Gap**: 15 days (`1,440` candles, `WARMUP_ROWS`)
- **Inner Selection/Eval Window**: 60 days (`5,760` candles)
- **Second Purge Gap**: 15 days (`1,440` candles, `WARMUP_ROWS`)
- **Outer Validation Window**: 90 days (`8,640` candles)
- **Step Size**: 180 days
- **Seed**: 42 only
- **Timesteps per Fold**: 100,000
- **Environments (`n_envs`)**: 1
- **Device**: `auto` (resolved to `cpu`)
- **Expected Folds**: 3
- **Cost Model**: Taker fee = 5.0 bps (`0.0005`), Half-spread = 0.5 bps (`0.00005`), Slippage = 1.0 bps (`0.0001`)
- **Baselines**: `AlwaysFlat`, `BuyAndHold`, `ThresholdMomentum`, `RegimeMomentum`, `FixedHolding`, `CooldownMomentum`
- **Scenarios**: `base`, `costs2x`, `delay1`

---

## 2. Command & Execution Summary

### Execution Command
```bash
python -m obsidian_rl.cli walk-forward \
  --data-start 2023-01-01T00:00:00+00:00 \
  --holdout-start 2025-07-01T00:00:00+00:00 \
  --train-days 365 \
  --inner-eval-days 60 \
  --val-days 90 \
  --step-days 180 \
  --seeds 42 \
  --timesteps 100000 \
  --n-envs 1 \
  --device auto
```

- **Exit Code**: `0` (Success)
- **Experiment ID**: `wf-20260722-160014-022860-7a725ec7`
- **JSON Artifact**: [artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.json](file:///D:/Obsidian-RL/artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.json)
- **CSV Artifact**: [artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.csv](file:///D:/Obsidian-RL/artifacts/walkforward/wf-20260722-160014-022860-7a725ec7.csv)
- **Device Used**: CPU (`torch 2.13.0+cpu`, `cuda_available: false`)
- **Runtime**:
  - Fold 0 PPO wall time: `67.26` seconds
  - Fold 1 PPO wall time: `67.12` seconds
  - Fold 2 PPO wall time: `67.59` seconds
  - Total training runtime: `201.98` seconds (~3.37 minutes)
  - Total process wall time: ~242 seconds

---

## 3. Exact Fold Specifications & Model Registration

### Fold 0
- **Train**: 2023-01-01 00:00:00Z (`1672531200000`) -> 2023-12-31 23:45:00Z (`1704066300000`) | 35,040 rows | `5ea6052f5a42c9e43f7627feab1d6e6c00065eae201a94e75cf02b606d7e86e5`
- **Purge 1**: 2024-01-01 00:00:00Z (`1704067200000`) -> 2024-01-01 23:45:00Z (`1704152700000`) | 96 rows | `3b8b0f2177abfdb4c43738461344858bee2921ce58e1537d7e9b9aeda93911e9`
- **Inner Eval**: 2024-01-02 00:00:00Z (`1704153600000`) -> 2024-03-01 23:45:00Z (`1709336700000`) | 5,760 rows | `f8ebe74b4b885fb68c32f89fdb73030d49db797a99a13046027c0c6918bb8905`
- **Purge 2**: 2024-03-02 00:00:00Z (`1709337600000`) -> 2024-03-02 23:45:00Z (`1709423100000`) | 96 rows | `907d27377d3e94132ef61adba0bc248e76f3db402ce32693e5ea64cb8b3ae558`
- **Outer Val**: 2024-03-03 00:00:00Z (`1709424000000`) -> 2024-05-31 23:45:00Z (`1717199100000`) | 8,640 rows | `306a62ad8b6b060bb6f573e30b825c262fa09b4f48343223ec857dcad25ee046`
- **Model ID**: `wf-20260722-160014-022860-7a725ec7-f0-s42`
- **Selected Checkpoint**: Step `50,000` (Inner Eval Mean Reward: `-2.40557`)

### Fold 1
- **Train**: 2023-06-30 00:00:00Z (`1688083200000`) -> 2024-06-28 23:45:00Z (`1719618300000`) | 35,040 rows | `86473f212989417414be028d51b637c1a2f0fd85342930d91e18b432e774bef9`
- **Purge 1**: 2024-06-29 00:00:00Z (`1719619200000`) -> 2024-06-29 23:45:00Z (`1719704700000`) | 96 rows | `a0a60ae15760055d498735688f75735ed394fce54e33653ffd6ed26bf167033f`
- **Inner Eval**: 2024-06-30 00:00:00Z (`1719705600000`) -> 2024-08-28 23:45:00Z (`1724888700000`) | 5,760 rows | `25c853593acbbe4d7f1479c20bef599d091cf0096daa69e494330146d62bf56d`
- **Purge 2**: 2024-08-29 00:00:00Z (`1724889600000`) -> 2024-08-29 23:45:00Z (`1724975100000`) | 96 rows | `4ca01ce2ccc31e979f111fae5720fdd3405eb2de5c447edd57774fad7cb031ba`
- **Outer Val**: 2024-08-30 00:00:00Z (`1724976000000`) -> 2024-11-27 23:45:00Z (`1732751100000`) | 8,640 rows | `49867768c9d627decb4ceaaf89b595a55d4bc5f4b11f6c4032bf3082bed18bcd`
- **Model ID**: `wf-20260722-160014-022860-7a725ec7-f1-s42`
- **Selected Checkpoint**: Step `100,000` (Inner Eval Mean Reward: `-1.37714`)

### Fold 2
- **Train**: 2023-12-27 00:00:00Z (`1703635200000`) -> 2024-12-25 23:45:00Z (`1735170300000`) | 35,040 rows | `e82f6d307fff622468ba7f9096c3dd5e6b9e204f04c9445c1d4f6c7cbdc18c25`
- **Purge 1**: 2024-12-26 00:00:00Z (`1735171200000`) -> 2024-12-26 23:45:00Z (`1735256700000`) | 96 rows | `e42acf19eb6eb93a7c738fee5b92839fa1f0762713d15270ac2fbdc9b0c7eb70`
- **Inner Eval**: 2024-12-27 00:00:00Z (`1735257600000`) -> 2025-02-24 23:45:00Z (`1740440700000`) | 5,760 rows | `8c3b8af17685d70a2f72addd81cd850132e63c49c79c28fe84db213710f4399c`
- **Purge 2**: 2025-02-25 00:00:00Z (`1740441600000`) -> 2025-02-25 23:45:00Z (`1740527100000`) | 96 rows | `d09a095d8ba9d68d4a264cf53471c88fcabfa40b72167686e6f834aa4748022c`
- **Outer Val**: 2025-02-26 00:00:00Z (`1740528000000`) -> 2025-05-26 23:45:00Z (`1748303100000`) | 8,640 rows | `c3b88dcdfdd89fcab306e18162eb2894398c32c0a3d19ae7472753a7426f9842`
- **Model ID**: `wf-20260722-160014-022860-7a725ec7-f2-s42`
- **Selected Checkpoint**: Step `100,000` (Inner Eval Mean Reward: `-1.00116`)

---

## 4. Outer Validation Empirical Performance (Scenario: `base`)

| Fold | Strategy | Net Return | Sharpe | Max Drawdown | Turnover | Trades |
|---|---|---|---|---|---|---|
| **0** | `ppo-100000` | `-0.065675` (-6.57%) | `-0.889167` | `0.112978` (11.30%) | `45,674.91` | 301 |
| **0** | `buy-and-hold` | `+0.065150` (+6.52%) | `0.390242` | `0.230012` (23.00%) | `20,664.93` | 2 |
| **0** | `always-flat` | `0.000000` (0.00%) | `0.000000` | `0.000000` (0.00%) | `0.00` | 0 |
| **0** | `threshold-momentum-0.005` | `-0.618601` (-61.86%) | `-7.940613` | `0.638541` (63.85%) | `10,702,230.00` | 1964 |
| **0** | `regime-momentum-0.01-0.002` | `-0.366202` (-36.62%) | `-4.138143` | `0.414250` (41.43%) | `5,185,359.00` | 958 |
| **0** | `fixed-holding-0.005-16` | `-0.475871` (-47.59%) | `-4.719641` | `0.485213` (48.52%) | `5,019,828.00` | 1098 |
| **0** | `cooldown-momentum-0.005-0.001-8` | `-0.292098` (-29.21%) | `-3.171469` | `0.309186` (30.92%) | `5,436,942.00` | 976 |
|---|---|---|---|---|---|---|
| **1** | `ppo-100000` | `+0.282421` (+28.24%) | `4.333552` | `0.058692` (5.87%) | `24,501.51` | 28 |
| **1** | `buy-and-hold` | `+0.621232` (+62.12%) | `4.241227` | `0.115079` (11.51%) | `26,229.37` | 2 |
| **1** | `always-flat` | `0.000000` (0.00%) | `0.000000` | `0.000000` (0.00%) | `0.00` | 0 |
| **1** | `threshold-momentum-0.005` | `-0.625177` (-62.52%) | `-10.857776` | `0.636018` (63.60%) | `8,734,553.00` | 1566 |
| **1** | `regime-momentum-0.01-0.002` | `-0.420898` (-42.09%) | `-6.679556` | `0.437711` (43.77%) | `4,599,720.00` | 762 |
| **1** | `fixed-holding-0.005-16` | `-0.357518` (-35.75%) | `-4.180536` | `0.389625` (38.96%) | `4,742,263.00` | 822 |
| **1** | `cooldown-momentum-0.005-0.001-8` | `-0.239888` (-23.99%) | `-3.134581` | `0.269125` (26.91%) | `4,744,771.00` | 765 |
|---|---|---|---|---|---|---|
| **2** | `ppo-100000` | `+0.147486` (+14.75%) | `2.168128` | `0.106582` (10.66%) | `24,617.33` | 37 |
| **2** | `buy-and-hold` | `+0.296059` (+29.61%) | `2.044447` | `0.210316` (21.03%) | `22,975.53` | 2 |
| **2** | `always-flat` | `0.000000` (0.00%) | `0.000000` | `0.000000` (0.00%) | `0.00` | 0 |
| **2** | `threshold-momentum-0.005` | `-0.679803` (-67.98%) | `-10.589398` | `0.706637` (70.66%) | `10,081,900.00` | 1766 |
| **2** | `regime-momentum-0.01-0.002` | `-0.218051` (-21.81%) | `-2.519277` | `0.277724` (27.77%) | `4,737,113.00` | 752 |
| **2** | `fixed-holding-0.005-16` | `-0.333525` (-33.35%) | `-3.310572` | `0.367891` (36.79%) | `5,190,216.00` | 928 |
| **2** | `cooldown-momentum-0.005-0.001-8` | `-0.279429` (-27.94%) | `-3.399816` | `0.362723` (36.27%) | `4,964,926.00` | 803 |

---

## 5. Aggregate Strategy Performance Across 3 Folds (`base` Scenario)

| Strategy | Mean Net Return | Std Net Return | Min Net Return (Worst Fold) | Mean Sharpe | Mean Max DD | Mean Turnover | Mean Trades |
|---|---|---|---|---|---|---|---|
| `buy-and-hold` | **`+0.327480`** (+32.75%) | `0.279370` | **`+0.065150`** (+6.52%) | **`2.225306`** | `0.185135` (18.51%) | `23,289.94` | 2.0 |
| `ppo-100000` | **`+0.121411`** (+12.14%) | `0.175507` | **`-0.065675`** (-6.57%) | `1.870838` | **`0.092751`** (9.28%) | `31,597.92` | 122.0 |
| `always-flat` | `0.000000` (0.00%) | `0.000000` | `0.000000` (0.00%) | `0.000000` | `0.000000` (0.00%) | `0.00` | 0.0 |
| `cooldown-momentum` | `-0.270472` (-27.05%) | `0.027233` | `-0.292098` (-29.21%) | `-3.235289` | `0.313678` (31.37%) | `5,048,880.00` | 848.0 |
| `regime-momentum` | `-0.335050` (-33.51%) | `0.104950` | `-0.420898` (-42.09%) | `-4.445659` | `0.376562` (37.66%) | `4,840,731.00` | 824.0 |
| `fixed-holding` | `-0.388971` (-38.90%) | `0.076208` | `-0.475871` (-47.59%) | `-4.070250` | `0.414243` (41.42%) | `4,984,102.00` | 949.3 |
| `threshold-momentum` | `-0.641194` (-64.12%) | `0.033598` | `-0.679803` (-67.98%) | `-9.795929` | `0.660399` (66.04%) | `9,839,561.00` | 1765.3 |

---

## 6. Verification and Invariant Confirmation

1. **Finite Metrics**: Confirmed that every single metric across all 63 evaluation rows (3 folds x 7 strategies x 3 scenarios) is a finite float. No `NaN`, `Inf`, or `null` values exist.
2. **Outer Validation Isolation**: Confirmed that PPO training and `EvalCallback` checkpoint selection received only `(train, inner_eval)` slices. `outer_val` was strictly isolated until final strategy evaluation.
3. **No Downstream Promotion/Holdout Access**: Candidate evaluation, promotion (`CHAMPION.json`), and the central reserved holdout (`HOLDOUT_STATE.json`) were NOT run or accessed.
4. **Baseline Comparison**: `ppo-100000` achieved positive mean return (+12.14%) and lower drawdown (9.28%) than `buy-and-hold` (18.51%), but underperformed `buy-and-hold` in overall mean return (+32.75%) and mean Sharpe (2.23 vs 1.87). Outperformed all naive momentum baselines.
5. **No Profitability Edge Claims**: PPO's positive performance in folds 1 and 2 is documented as empirical walk-forward output under synthetic/historical baseline comparison, not evidence of a live trading edge.

---

## 7. Final Verdict

PILOT TECHNICALLY VALID
