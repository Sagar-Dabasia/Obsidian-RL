# Validation report — 2026-07-19

All results are **simulated paper performance net of assumed costs** (taker 5bp,
half-spread 0.5bp, slippage 1bp per side). No profitability claim is made.

## Data
BTCUSDT USD-M perpetual, 15m klines, 2020-01-01 → 2026-07-19 UTC (229,583 candles,
0 gaps, 0 validation errors). Folds use 2020-01-01 → 2025-07-01; **holdout
2025-07-01 → 2026-07-19 was untouched until the single final run below.**

## Walk-forward (5 folds: 720d train / 1d purge / 180d val, step 270d; PPO 150k steps × seeds 42/43/44)
artifacts/walkforward/walkforward-20260719-200001.json

| strategy | runs | mean net | std | min | mean Sharpe | mean maxDD | mean trades |
|---|---|---|---|---|---|---|---|
| buy-and-hold | 5 | +2.4% | 46.3% | −57.6% | −0.00 | 0.36 | 2 |
| ppo-150000 (3 seeds) | 15 | +0.1% | 44.4% | −57.6% | −0.42 | 0.37 | 1310 |
| always-flat | 5 | 0.0% | 0 | 0 | 0.00 | 0.00 | 0 |
| regime-momentum | 5 | −39.7% | 17.0% | −60.2% | −2.72 | 0.48 | 1523 |
| cooldown-momentum | 5 | −52.6% | 8.0% | −64.3% | −3.89 | 0.57 | 1626 |
| fixed-holding | 5 | −57.6% | 13.0% | −75.1% | −3.60 | 0.62 | 1815 |
| threshold-momentum | 5 | −83.4% | 6.7% | −90.4% | −8.38 | 0.85 | 3250 |

**Conclusion: no strategy shows a repeatable net edge across folds and seeds.** Momentum
baselines are destroyed by costs at 15m frequency. PPO is ~break-even and learned far
lower turnover than the deterministic momentum policies. Cost-doubling and one-candle
delay scenarios are recorded per row in the results files (scenario = costs2x / delay1).

## Alpha Gate ablation (same folds; LightGBM on executable net-return labels, h=16)
artifacts/gate_ablation: gated-PPO −0.6% vs PPO-alone −0.7% mean (indistinguishable;
maxDD 0.31 vs 0.38); gate-direct −8.5%; gated-regime-momentum −23.3%.
**Gate NOT retained** (ADR-005): retention criterion (repeatable net improvement or
material risk reduction) not met.

## Final candidate + holdout (run once)
Candidate `ppo-20260719-200553-seed42` (validated config: 150k steps, seed 42; trained
2022-07-01→2024-12-30, validated 2025-01-01→2025-06-30, net +13.9% ≈ buy&hold +14.5%,
passes risk gates). Single holdout run 2025-07-01→2026-07-19
(artifacts/holdout/walkforward-20260719-200826.json):

| strategy | net return | Sharpe | maxDD | trades |
|---|---|---|---|---|
| ppo candidate | **+33.5%** | 0.63 | 0.32 | 3457 |
| always-flat | 0.0% | 0.00 | 0.00 | 0 |
| buy-and-hold | −39.1% | −1.07 | 0.54 | 2 |
| best momentum baseline | −80.4% | −4.94 | 0.81 | 2920 |

**Caveat (do not over-read):** this is one seed on one period. Combined with the
walk-forward evidence (~0 mean across regimes/seeds), the honest conclusion is that the
holdout number is a single favorable realization, not repeatable evidence of an edge.

## Live-paper readiness
- Replay of the frozen champion through the live-paper path: 7,534 decisions over
  2026-05-01→2026-07-19, ledger-recorded, clean session close (run 2ee92793bdd94ff3).
- Replay/backtest parity, restart recovery, and idempotency proven by tests.
- Production websocket stream verified (3 events parsed, `k.x` finality flag present).
- Champion promoted: `ppo-20260719-200553-seed42` (rollback history in models/CHAMPION.json).

## Known limitations
- Funding cash flows are modeled in backtests when rates are supplied, but the live
  paper loop does not yet apply funding events in real time (fees/spread/slippage are).
- Sharpe assumes i.i.d. per-candle returns; win rate counts realized-P&L events, not
  round trips.
