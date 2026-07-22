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
- **Strategies**: Deterministic baselines only (`BuyAndHold`, `SMA_Cross`, `RSI_Threshold`, `RandomPolicy`)
- **PPO**: Disabled (`--skip-ppo`)
- **Purpose**: Verify historical dataset download, schema validation, walk-forward fold segmentation, cost accounting, and baseline reporting infrastructure.
- **Real Holdout Access**: Strictly Prohibited (`--holdout-start 2025-07-01T00:00:00+00:00`).

---

## Status & Execution Log

*(To be updated after dataset download and walk-forward execution)*
