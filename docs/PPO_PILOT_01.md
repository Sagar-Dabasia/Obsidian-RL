# PPO Historical Pilot 01 Plan and Execution Report

## Overview

This report documents the first bounded PPO walk-forward training pilot under the hardened nested walk-forward protocol.

## Experiment Plan

- **Asset / Interval**: BTCUSDT, 15-minute candles
- **Data Start**: 2023-01-01T00:00:00Z (`1672531200000` ms)
- **Reserved Holdout Start**: 2025-07-01T00:00:00Z (`1751328000000` ms)
- **Train Window**: 365 days (`35040` candles)
- **First Purge Gap**: 15 days (`1440` candles, `WARMUP_ROWS`)
- **Inner Evaluation Window**: 60 days (`5760` candles)
- **Second Purge Gap**: 15 days (`1440` candles, `WARMUP_ROWS`)
- **Outer Validation Window**: 90 days (`8640` candles)
- **Step Size**: 180 days
- **Seed**: 42
- **Timesteps per Fold**: 100,000
- **Environments (`n_envs`)**: 1
- **Device**: auto
- **Expected Folds**: 3
- **Cost Model**: Default pessimism (5.0 bps fee, 0.5 bps half-spread, 1.0 bps slippage)
- **PPO Hyperparameters**: Default (`n_steps=2048`, `batch_size=64`, `net_arch=[64, 64]`)
- **Baselines**: `AlwaysFlat`, `BuyAndHold`, `ThresholdMomentum`
- **Scenarios**: `base`, `costs2x`, `delay1`
- **Purpose**: First bounded PPO historical walk-forward pilot evaluating learning, inner selection, and outer validation performance against baselines without touching holdout data.
- **Holdout Access**: Prohibited

---

## Status

Training Pending
