# Phase 4D-R3 Perpetual USD-M Funding Verification Plan

## Preregistration Details
- **Provider**: BINANCE_FUTURES (Official USD-M)
- **Symbols**: BTCUSDT, ETHUSDT
- **Timeframe**: H4
- **Market Model**: PERPETUAL
- **Exposure Policy**: BIDIRECTIONAL
- **Raw Start**: 1574827200000 (2019-11-27 04:00:00Z - first common)
- **Evaluation Start**: 1585209600000 (after 721 H4 bars warm-up)
- **Evaluation End**: 1704067200000 (2024-01-01)
- **Warm-up Count**: 721 bars (120 trading days of H4)
- **Strategy Config**: 20/60/120 multi-timeframe trend
- **Execution Timing**: NEXT_BAR_OPEN
- **Cost Methodology**: Taker Fee = 0.0005, Half Spread = 0.00005, Slippage = 0.0001
- **Funding Application**: Point-in-time exact replication from BINANCE_FUTURES funding rate history.

## Acceptance Criteria
1. No SPOT data contamination.
2. Funding applied exactly once per event.
3. Funding correctly signed for LONG/SHORT exposure.
4. Total Costs precisely reconcile (Fees + Spread + Slippage - Funding).
5. All reported metrics must be finite.
6. Manifest digest matches runtime digest exactly.
