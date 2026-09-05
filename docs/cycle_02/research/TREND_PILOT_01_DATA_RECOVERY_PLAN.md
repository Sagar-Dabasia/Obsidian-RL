# Cycle 02 Phase 4C-R: Trend Pilot 01 Data Recovery Plan

## Objective
Establish deterministic recovery rules to handle genuine provider data gaps (e.g., exchange maintenance outages) without compromising point-in-time integrity, introducing lookahead bias, or inventing synthetic data. This plan is pre-registered before auditing or modifying the dataset builder.

## Unchanged Constraints
- **Trend Engine Horizons**: 20, 60, 120 days.
- **Signal Rules & Execution Timing**: Execution on the NEXT bar after signal confirmation. No same-bar execution.
- **Costs**: Unchanged Phase 4B cost models.
- **Symbols**: `BTCUSDT`, `ETHUSDT`, `EUR_USD`, `GBP_USD`.
- **Evaluation Dates**: `2020-01-01` to `2023-12-31`.
- **Confirmation/Holdout**: Untouched.
- **Pass/Fail Criteria**: Retain exactly the original Phase 4C development screen.

## Data Recovery Rules
1. **Evaluation Gaps are Fatal**: Any missing crypto interval occurring inside the evaluation period (`2020-01-01` to `2023-12-31`) causes an immediate `EXPERIMENT INVALID` failure.
2. **Warm-up Gaps are Conditional**: A gap inside the `2019` warm-up period is only acceptable if all of the following hold true:
   - It is explicitly logged in the final report.
   - Absolutely NO synthetic or interpolated candles are created to fill the gap.
   - There are **at least 721 continuous 4h bars** strictly after the final gap and before `2020-01-01` (to satisfy a full 120-day trend horizon + 1 bar).
   - The trend engine calculates metrics and signals only on the continuous history *after* the final gap.
   - No returns or trades are calculated during the warm-up period.
3. **Bounded Refetch**: Each missing crypto interval must be retried using the Binance adapter to ensure it is not a transient rate-limit or network failure.
4. **No Substitution**: Data from other exchanges (e.g., Coinbase, Kraken) cannot be spliced in to fill gaps.
5. **Preserve Forex**: The existing `EUR_USD` and `GBP_USD` data and hashes are reused exactly. They will not be redownloaded unless integrity fails.

These rules ensure we can recover from documented provider maintenance without creating synthetic history.
