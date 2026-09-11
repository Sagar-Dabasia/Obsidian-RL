# Phase 4D-R1 Plan (Genuine Perpetual Replication)

**Objective**: Replicate Phase 4D trend following strategy evaluation on Crypto markets using authentic Binance USD-M Futures data and actual funding rates, replacing the invalid Binance Spot proxies.

## Frozen Preregistration Parameters
- **Data Providers**: Binance USD-M Futures (official public API)
- **Symbols**: BTCUSDT, ETHUSDT
- **Timeframe**: 4h (H4)
- **Evaluation Window**: First common COMPLETE 4h bar after ETHUSDT launch + strategy warm-up, to 2024-01-01 (or latest available).
- **Warm-up**: 120 days
- **Costs**: 0.0004 taker fee, 0.0001 half spread, 0.0005 slippage + authentic funding rates applied point-in-time.
- **Execution Timing**: Next-bar open
- **Market Model**: PERPETUAL
- **Exposure Policy**: BIDIRECTIONAL
- **Acceptance Criteria**: Technically valid execution. A failed profitability screen is still a valid experiment.

*Frozen Hash*: Computed prior to execution.
