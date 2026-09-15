# Phase 4C-R1 Plan (Genuine Cross-Market Replication)

**Objective**: Replicate Phase 4C trend following strategy evaluation on Forex markets using genuine Dukascopy historical data to replace unverified OANDA data.

## Frozen Preregistration Parameters
- **Data Providers**: Dukascopy (official historical tick/CSV data)
- **Symbols**: EURUSD, GBPUSD
- **Timeframe**: 4h (H4)
- **Evaluation Window**: 2017-01-01 to 2024-01-01 (or first available common window based on data availability)
- **Warm-up**: 120 days
- **Costs**: 0.0 taker fee, 0.0 slippage, 0.0 spread (baseline Forex margin proxy)
- **Execution Timing**: Next-bar open
- **Market Model**: FOREX_MARGIN
- **Exposure Policy**: BIDIRECTIONAL
- **Acceptance Criteria**: Technically valid execution. A failed profitability screen is still a valid experiment.

*Frozen Hash*: Computed prior to execution.
