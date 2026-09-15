# Phase 4C-R4 Forex Trend Stability Plan

## Preregistration Details
- **Provider**: DUKASCOPY_JFOREX_HISTORICAL_DATA_MANAGER
- **Raw Files**: Dukascopy CSV exports (June 1, 2019 to Dec 31, 2023)
- **Symbols**: EURUSD, GBPUSD
- **Timeframe**: H4
- **Raw Data Treatment**: Deterministic deduplication, BID/ASK midpoint execution
- **Raw Start**: 1559347200000 (2019-06-01T00:00:00Z)
- **Evaluation Start**: 1577836800000 (2020-01-01T00:00:00Z)
- **Evaluation End**: 1704052800000 (2023-12-31T20:00:00Z)
- **Warm-up Count**: 721 bars (120 trading days of H4)
- **Strategy Config**: 20/60/120 multi-timeframe trend
- **Market Model**: FOREX_MARGIN
- **Exposure Policy**: BIDIRECTIONAL
- **Execution Timing**: NEXT_BAR_OPEN
- **Cost Methodology**: Taker Fee = 0.0, Spread = Point-in-time authentic BID/ASK, Slippage = 0.0001
- **Gap Policy**: Standard weekend exclusions apply. Known source gaps mapped as DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL (Fail closed for any unevidenced gap).

## Acceptance Criteria
1. Both markets must yield a positive net return.
2. Median net return > 0.
3. Median annualized Sharpe > 0.50.
4. Worst net return > -10%.
5. Median maximum drawdown <= 20%.
6. At least 1/2 markets must strictly beat the always-long Sharpe ratio.
7. All reported metrics must be finite.
8. Manifest digest must exactly match runtime digest.
