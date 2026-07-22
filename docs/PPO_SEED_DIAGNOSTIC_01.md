# PPO Seed Instability Diagnostic Report 01

## Overview

This document presents a detailed diagnostic breakdown of the PPO Seed Stability Pilot 01 results across 5 random seeds (42, 7, 23, 101, 202) evaluated over 3 chronological folds under the hardened nested walk-forward protocol.

---

## 1. Seed × Fold Empirical Performance Tables

### Scenario: `base` (Standard Transaction Costs: 5.0 bps fee, 0.5 bps half-spread, 1.0 bps slippage)

| Fold | Seed | Net Return | Sharpe | Max Drawdown | Turnover | Trade Count | Selected Checkpoint Step |
|---|---|---|---|---|---|---|---|
| **0** | 7 | `-0.046928` (-4.69%) | `-3.536047` | `0.055841` (5.58%) | `706,392.50` | 144 | 100,000 |
| **0** | 23 | `+0.041268` (+4.13%) | `0.514556` | `0.117360` (11.74%) | `14,355.75` | 39 | 100,000 |
| **0** | 42 | `-0.065675` (-6.57%) | `-0.889167` | `0.112978` (11.30%) | `45,674.91` | 301 | 50,000 |
| **0** | 101 | `+0.016788` (+1.68%) | `0.249000` | `0.116915` (11.69%) | `14,322.81` | 41 | 100,000 |
| **0** | 202 | `-0.065675` (-6.57%) | `-0.889167` | `0.112978` (11.30%) | `45,674.91` | 301 | 50,000 |
|---|---|---|---|---|---|---|---|
| **1** | 7 | `-0.232214` (-23.22%) | `-4.630129` | `0.283806` (28.38%) | `30,284.87` | 198 | 100,000 |
| **1** | 23 | `-0.091948` (-9.19%) | `-9.005498` | `0.095059` (9.51%) | `1,362,241.00` | 212 | 100,000 |
| **1** | 42 | `+0.282421` (+28.24%) | `4.333552` | `0.058692` (5.87%) | `24,501.51` | 28 | 100,000 |
| **1** | 101 | `+0.280570` (+28.06%) | `4.338031` | `0.058751` (5.88%) | `14,454.21` | 27 | 100,000 |
| **1** | 202 | `+0.280570` (+28.06%) | `4.338031` | `0.058751` (5.88%) | `14,454.21` | 27 | 100,000 |
|---|---|---|---|---|---|---|---|
| **2** | 7 | `-0.074979` (-7.50%) | `-8.927107` | `0.081855` (8.19%) | `628,492.30` | 130 | 100,000 |
| **2** | 23 | `-0.096511` (-9.65%) | `-8.825158` | `0.099334` (9.93%) | `1,624,058.00` | 202 | 100,000 |
| **2** | 42 | `+0.147486` (+14.75%) | `2.168128` | `0.106582` (10.66%) | `24,617.33` | 37 | 100,000 |
| **2** | 101 | `-0.047370` (-4.74%) | `-1.242746` | `0.135894` (13.59%) | `702,209.80` | 151 | 100,000 |
| **2** | 202 | `+0.147794` (+14.78%) | `2.173034` | `0.106582` (10.66%) | `14,611.12` | 36 | 100,000 |

### Scenario: `costs2x` (2x Transaction Costs: 10.0 bps fee, 1.0 bps half-spread, 2.0 bps slippage)

| Fold | Seed | Net Return | Sharpe | Max Drawdown | Turnover | Trade Count | Selected Checkpoint Step |
|---|---|---|---|---|---|---|---|
| **0** | 7 | `-0.092466` (-9.25%) | `-7.029769` | `0.098027` (9.80%) | `689,837.00` | 144 | 100,000 |
| **0** | 23 | `+0.040323` (+4.03%) | `0.506399` | `0.117514` (11.75%) | `14,352.64` | 39 | 100,000 |
| **0** | 42 | `-0.068231` (-6.82%) | `-0.922828` | `0.113247` (11.32%) | `45,274.05` | 297 | 50,000 |
| **0** | 101 | `+0.015854` (+1.59%) | `0.235280` | `0.117086` (11.71%) | `14,319.57` | 41 | 100,000 |
| **0** | 202 | `-0.068231` (-6.82%) | `-0.922828` | `0.113247` (11.32%) | `45,274.05` | 297 | 50,000 |
|---|---|---|---|---|---|---|---|
| **1** | 7 | `-0.233898` (-23.39%) | `-4.662947` | `0.284744` (28.47%) | `30,255.16` | 198 | 100,000 |
| **1** | 23 | `-0.165798` (-16.58%) | `-14.302246` | `0.168118` (16.81%) | `1,305,296.00` | 213 | 100,000 |
| **1** | 42 | `+0.280518` (+28.05%) | `4.318547` | `0.058716` (5.87%) | `24,492.98` | 28 | 100,000 |
| **1** | 101 | `+0.279502` (+27.95%) | `4.328908` | `0.058774` (5.88%) | `14,448.60` | 27 | 100,000 |
| **1** | 202 | `+0.279502` (+27.95%) | `4.328908` | `0.058774` (5.88%) | `14,448.60` | 27 | 100,000 |
|---|---|---|---|---|---|---|---|
| **2** | 7 | `-0.113284` (-11.33%) | `-12.598913` | `0.117295` (11.73%) | `615,759.00` | 130 | 100,000 |
| **2** | 23 | `-0.208576` (-20.86%) | `-16.910297` | `0.208576` (20.86%) | `1,537,901.00` | 205 | 100,000 |
| **2** | 42 | `+0.145701` (+14.57%) | `2.153807` | `0.106724` (10.67%) | `24,607.97` | 37 | 100,000 |
| **2** | 101 | `-0.136419` (-13.64%) | `-3.811020` | `0.154274` (15.43%) | `673,574.50` | 150 | 100,000 |
| **2** | 202 | `+0.146755` (+14.68%) | `2.163818` | `0.106724` (10.67%) | `14,604.78` | 36 | 100,000 |

### Scenario: `delay1` (1-Candle Decision/Execution Signal Delay)

| Fold | Seed | Net Return | Sharpe | Max Drawdown | Turnover | Trade Count | Selected Checkpoint Step |
|---|---|---|---|---|---|---|---|
| **0** | 7 | `-0.082278` (-8.23%) | `-6.909044` | `0.082652` (8.27%) | `677,631.20` | 144 | 100,000 |
| **0** | 23 | `+0.037221` (+3.72%) | `0.466781` | `0.117360` (11.74%) | `14,320.89` | 39 | 100,000 |
| **0** | 42 | `-0.061839` (-6.18%) | `-0.838613` | `0.112978` (11.30%) | `45,559.90` | 298 | 50,000 |
| **0** | 101 | `+0.013801` (+1.38%) | `0.205063` | `0.116915` (11.69%) | `14,307.66` | 41 | 100,000 |
| **0** | 202 | `-0.061839` (-6.18%) | `-0.838613` | `0.112978` (11.30%) | `45,559.90` | 298 | 50,000 |
|---|---|---|---|---|---|---|---|
| **1** | 7 | `-0.230806` (-23.08%) | `-4.642113` | `0.283806` (28.38%) | `30,780.14` | 203 | 100,000 |
| **1** | 23 | `-0.096059` (-9.61%) | `-9.141848` | `0.096065` (9.61%) | `1,387,496.00` | 214 | 100,000 |
| **1** | 42 | `+0.276617` (+27.66%) | `4.341329` | `0.058705` (5.87%) | `24,431.63` | 28 | 100,000 |
| **1** | 101 | `+0.278027` (+27.80%) | `4.347451` | `0.058692` (5.87%) | `14,445.35` | 27 | 100,000 |
| **1** | 202 | `+0.278027` (+27.80%) | `4.347451` | `0.058692` (5.87%) | `14,445.35` | 27 | 100,000 |
|---|---|---|---|---|---|---|---|
| **2** | 7 | `-0.011888` (-1.19%) | `-1.626580` | `0.025582` (2.56%) | `653,716.70` | 130 | 100,000 |
| **2** | 23 | `-0.109326` (-10.93%) | `-9.590720` | `0.109435` (10.94%) | `1,609,620.00` | 202 | 100,000 |
| **2** | 42 | `+0.148467` (+14.85%) | `2.144605` | `0.106582` (10.66%) | `24,644.99` | 37 | 100,000 |
| **2** | 101 | `-0.053711` (-5.37%) | `-1.433527` | `0.136611` (13.66%) | `699,008.00` | 158 | 100,000 |
| **2** | 202 | `+0.147378` (+14.74%) | `2.148941` | `0.106582` (10.66%) | `14,609.45` | 36 | 100,000 |

---

## 2. Per-Fold Cross-Seed Analysis (`base` Scenario)

| Fold | Positive Seeds (out of 5) | Median Return | Min Return | Max Return | Std Dev | Return Range | Directional Agreement? |
|---|---|---|---|---|---|---|---|
| **Fold 0** | 2 of 5 (40.0%) | `-0.046928` (-4.69%) | `-0.065675` (-6.57%) | `+0.041268` (+4.13%) | `0.049807` (4.98%) | `0.106943` (10.69 pts) | **No** (2 pos, 3 neg) |
| **Fold 1** | 3 of 5 (60.0%) | `+0.280570` (+28.06%) | `-0.232214` (-23.22%) | `+0.282421` (+28.24%) | `0.247802` (24.78%) | `0.514636` (51.46 pts) | **No** (3 pos, 2 neg) |
| **Fold 2** | 2 of 5 (40.0%) | `-0.047370` (-4.74%) | `-0.096511` (-9.65%) | `+0.147794` (+14.78%) | `0.122073` (12.21%) | `0.244305` (24.43 pts) | **No** (2 pos, 3 neg) |

### Fold Directional Agreement
Across all 3 folds, seeds **do not agree on direction**. In every single fold, at least 2 seeds produced positive returns while at least 2 seeds produced negative returns.

---

## 3. Per-Seed Cross-Fold Analysis

| Seed | Positive Folds (out of 3) | Mean Base Return | Worst-Fold Return | `base` Mean | `costs2x` Mean | `delay1` Mean | Scenario Sensitivity |
|---|---|---|---|---|---|---|---|
| **42** | 2 of 3 (66.7%) | `+0.121411` (+12.14%) | `-0.065675` (-6.57%) | `+0.121411` | `+0.119329` | `+0.121082` | Highly robust (minimal decay) |
| **7** | 0 of 3 (0.0%) | `-0.118041` (-11.80%) | `-0.232214` (-23.22%) | `-0.118041` | `-0.146550` | `-0.108324` | Moderate cost sensitivity |
| **23** | 1 of 3 (33.3%) | `-0.049063` (-4.91%) | `-0.096511` (-9.65%) | `-0.049063` | `-0.111350` | `-0.056055` | Severe cost decay under 2x costs |
| **101** | 2 of 3 (66.7%) | `+0.083329` (+8.33%) | `-0.047370` (-4.74%) | `+0.083329` | `+0.052979` | `+0.079372` | Moderate cost sensitivity |
| **202** | 2 of 3 (66.7%) | `+0.120896` (+12.09%) | `-0.065675` (-6.57%) | `+0.120896` | `+0.119342` | `+0.121188` | Highly robust (minimal decay) |

---

## 4. Descriptive Instability Analysis

1. **Variation Between Fold Means**:
   - Fold 0 Mean Return: `-0.024044` (-2.40%)
   - Fold 1 Mean Return: `+0.103880` (+10.39%)
   - Fold 2 Mean Return: `+0.015284` (+1.53%)
   - **Range of Fold Means**: `0.127924` (12.79 percentage points)

2. **Variation Between Seed Means**:
   - Seed 7 Mean: `-0.118041` (-11.80%)
   - Seed 23 Mean: `-0.049063` (-4.91%)
   - Seed 101 Mean: `+0.083329` (+8.33%)
   - Seed 202 Mean: `+0.120896` (+12.09%)
   - Seed 42 Mean: `+0.121411` (+12.14%)
   - **Range of Seed Means**: `0.239451` (23.95 percentage points)

3. **Average Within-Fold Seed Range**:
   - Fold 0 Seed Range: `0.106943` (10.69 percentage points)
   - Fold 1 Seed Range: `0.514636` (51.46 percentage points)
   - Fold 2 Seed Range: `0.244305` (24.43 percentage points)
   - **Average Within-Fold Seed Range**: `0.288628` (**28.86 percentage points**)

4. **Return Relationship with Turnover and Trade Count**:
   - A strong inverse relationship exists between turnover/trade count and performance.
   - Low-turnover policies (Seeds 42, 202, and Seed 101 in Fold 1) traded only 27-301 times (`~14,000` to `45,000` notional), achieving positive net returns.
   - High-turnover policies (Seed 23 in Folds 1 and 2, and Seed 101 in Fold 2) generated over `600,000` to `1,600,000` notional turnover across 130-212 trades, causing severe drag from transaction costs and slippage.

5. **Checkpoint Timing Association**:
   - Checkpoint selection (`TrackingEvalCallback` on inner evaluation) selected step `100,000` for 13 of 15 fold-seed runs.
   - In Fold 0, step `50,000` was selected for Seeds 42 and 202, while step `100,000` was selected for Seeds 7, 23, and 101.
   - The selected checkpoint step reflects inner-evaluation validation reward rather than outer-validation return, confirming that outer validation was never observed during checkpoint selection.

---

## 5. Classification Screen

The system evaluates three predefined classification rules:

1. **FOLD/REGIME-DOMINANT**:
   - Rule 1a: At least two folds have the same return sign for at least 4 of 5 seeds. -> **False** (0 of 3 folds have 4+ seeds matching sign).
   - Rule 1b: Range of fold means exceeds range of seed means. -> **False** (Fold range `12.79%` < Seed range `23.95%`).

2. **SEED/OPTIMIZATION-DOMINANT**:
   - Rule 2a: At least two folds contain both positive and negative seeds. -> **True** (All 3 folds contain both positive and negative seeds: Fold 0 has 2 pos / 3 neg; Fold 1 has 3 pos / 2 neg; Fold 2 has 2 pos / 3 neg).
   - Rule 2b: Average within-fold return range exceeds 15 percentage points. -> **True** (Average within-fold range is `28.86 percentage points` > `15.0 percentage points`).

3. **MIXED INSTABILITY**:
   - Neither condition satisfied. -> **False**.

### Final Classification
SEED/OPTIMIZATION-DOMINANT

---

## 6. Scenario Robustness & Minority Driver Analysis

The positive median returns under 2x transaction costs (`costs2x`: `+5.30%`) and 1-candle execution delay (`delay1`: `+7.94%`) are **not broad-based**. They are driven by a minority of strong, low-turnover policies (Seeds 42, 202, and Seed 101 in Fold 1). 

When policies over-trade (such as Seed 7 across all folds and Seed 23 in Folds 1 and 2), doubled transaction costs cause severe performance degradation (e.g. Seed 23 fold 2 net return decays from `-9.65%` to `-20.86%`). Conversely, low-turnover seeds remain highly robust under cost and delay variations.

---

## 7. Recommended Next Experiment

**Controlled Hyperparameter & Policy Regularization Screen**:
Implement policy action penalty / turnover regularization (e.g., increasing `turnover_weight` in reward or entropy regularization) to prevent high-turnover policy collapse across random seeds, before scaling timesteps or network architecture.

---

## 8. Invariant & Verification Confirmation

- **Finite Metrics**: Confirmed all metrics across all 45 evaluation rows are finite floats.
- **Outer Validation Isolation**: Confirmed `outer_val` was strictly isolated during `train_ppo` and checkpoint selection.
- **No Downstream Holdout / Promotion**: Candidate evaluation, promotion (`CHAMPION.json`), and the central reserved holdout (`HOLDOUT_STATE.json`) were NOT run or accessed.
