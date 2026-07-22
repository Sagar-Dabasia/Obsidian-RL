# Historical Pilot 01 Plan & Results

## Experiment Plan

- **Data Start**: `2023-01-01T00:00:00Z`
- **Data End**: `2025-06-30T23:45:00Z`
- **Reserved Holdout Begins**: `2025-07-01T00:00:00Z`
- **Train Window**: 365 days
- **Validation Window**: 90 days
- **Step Size**: 180 days
- **Symbol**: BTCUSDT
- **Interval**: 15m (15-minute candles)
- **Strategies**: Deterministic baselines only (`BuyAndHold`, `AlwaysFlat`, `SMA_Cross`, `RSI_Threshold`, `RandomPolicy`, etc.)
- **PPO**: Disabled (`--skip-ppo`)
- **Purpose**: Verify historical dataset download, schema validation, walk-forward fold segmentation, cost accounting, and baseline reporting infrastructure.
- **Real Holdout Access**: Strictly Prohibited (`--holdout-start 2025-07-01T00:00:00+00:00`).

---

## Command Execution & Exit Codes

| Command | Exit Code | Result Summary |
|---|---|---|
| `python -m obsidian_rl.cli gpu-check` | `0` | CUDA available (RTX 4060 Laptop GPU, VRAM 8187MB) |
| `python -m pytest -q` | `0` | `383 passed, 1 skipped` |
| `git status --short` | `0` | Clean working tree |
| `python -m obsidian_rl.cli data-download --start 2023-01-01T00:00:00+00:00 --end 2025-06-30T23:45:00+00:00` | `0` | Downloaded 87,552 rows across 30 monthly partitions |
| `python -m obsidian_rl.cli data-validate --strict` | `0` | `OK: rows=87552 span=[1672531200000,1751327100000] dups=0 gaps=0 missing=0 errors=[]` |
| `python -m obsidian_rl.cli data-summary` | `0` | Validated stored summary: 87,552 rows, 0 gaps |
| `python -m obsidian_rl.cli walk-forward --data-start 2023-01-01T00:00:00+00:00 --holdout-start 2025-07-01T00:00:00+00:00 --train-days 365 --val-days 90 --step-days 180 --skip-ppo` | `0` | Completed 3-fold evaluation across 18 strategy scenarios |

---

## Dataset Audit

- **Rows**: 87,552
- **First Open Time**: `2023-01-01 00:00:00+00:00` (timestamp `1672531200000`)
- **Last Open Time**: `2025-06-30 23:45:00+00:00` (timestamp `1751327100000`)
- **Gaps**: 0
- **Missing Candles**: 0
- **Duplicate Timestamps**: 0
- **Validation Errors**: None (`errors=[]`)
- **Holdout Boundary Verification**: Last open time (`2025-06-30 23:45:00+00:00`) is strictly prior to reserved holdout start (`2025-07-01 00:00:00+00:00`). Zero holdout candles loaded or accessed.

---

## Walk-Forward Fold Boundaries

| Fold ID | Train Start (UTC) | Train End (UTC) | Val Start (UTC) | Val End (UTC) | Val Days | Val Candles |
|---|---|---|---|---|---|---|
| **Fold 0** | `2023-01-01 00:00:00` | `2024-01-01 00:00:00` | `2024-01-01 00:00:00` | `2024-03-31 00:00:00` | 90 | 8,544 |
| **Fold 1** | `2023-06-29 00:00:00` | `2024-06-28 00:00:00` | `2024-06-28 00:00:00` | `2024-09-26 00:00:00` | 90 | 8,640 |
| **Fold 2** | `2023-12-26 00:00:00` | `2024-12-25 00:00:00` | `2024-12-25 00:00:00` | `2025-03-25 00:00:00` | 90 | 8,544 |

---

## Baseline Evaluation Results

### Aggregate Baseline Summary Across Folds (Base Scenario)

| Strategy ID | Folds | Runs | Mean Net Return | Std Net Return | Min Net Return | Mean Sharpe | Mean Max DD | Mean Turnover | Mean Trades |
|---|---|---|---|---|---|---|---|---|---|
| **buy-and-hold** | 3 | 3 | **+18.35%** | 35.16% | -8.06% | **+0.993** | **26.28%** | 21,850 | 2.0 |
| **always-flat** | 3 | 3 | **0.00%** | 0.00% | 0.00% | **0.000** | **0.00%** | 0 | 0.0 |
| **regime-momentum-0.01-0.002** | 3 | 3 | **-28.12%** | 13.31% | -36.89% | **-3.233** | **32.09%** | 5,035,540 | 877.0 |
| **cooldown-momentum-0.005-0.001-8** | 3 | 3 | **-33.96%** | 8.66% | -43.42% | **-3.986** | **39.50%** | 4,963,223 | 890.0 |
| **fixed-holding-0.005-16** | 3 | 3 | **-38.10%** | 12.77% | -50.93% | **-3.706** | **45.44%** | 5,136,852 | 983.0 |
| **threshold-momentum-0.005** | 3 | 3 | **-63.88%** | 5.60% | -70.02% | **-8.792** | **65.49%** | 9,827,466 | 1,839.7 |

### Output Artifacts

- Summary JSON: `artifacts/walkforward/walkforward-20260722-133154.json`
- Numeric finiteness: **All metrics are finite** (no NaN, Infinity, or unhandled exceptions occurred).

---

## Separated Assessment

### 1. Engineering & Data Validity
- **Verified**: Data download, partitioning, and strict validation execute deterministically.
- **Verified**: Timestamp continuity, interval enforcement (15m), and partition boundaries operate cleanly without missing bars or duplicate records.
- **Verified**: Fold generation correctly respects `--holdout-start`, guaranteeing no evaluation candles touch the reserved holdout range (`2025-07-01` onwards).
- **Verified**: Cost accounting (fees, spread, slippage) functions deterministically and reflects turnover penalties as expected.

### 2. Baseline Simulated Performance
- **Buy-and-Hold**: Achieved +18.35% mean net return across the 3 validation folds (Sharpe +0.993, max drawdown 26.28%), driven by positive market regime performance in early 2024.
- **Naive Momentum Baselines**: High-frequency naive momentum benchmarks (`threshold-momentum`, `regime-momentum`, `fixed-holding`, `cooldown-momentum`) suffered significant net losses due to transaction cost friction over frequent turnovers (~800–1800 trades per fold).

### 3. Unproven / Excluded Scope
- **PPO Training**: Prohibited and disabled (`--skip-ppo`). Policy learning performance across these market regimes remains to be tested in subsequent controlled experiments.
- **Supervised Alpha Gating**: Gating performance filtering out unpromising trades remains unverified.
- **Real Holdout**: Completely unobserved and untouched (`HOLDOUT_LOCK.json` clean).
