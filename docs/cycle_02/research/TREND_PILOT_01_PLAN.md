# Cycle 02 Phase 4C: Fixed Cross-Market Trend Historical Pilot 01 Plan

## Objective
Evaluate the predefined Trend Engine V1 across four fixed crypto and forex markets without parameter tuning or accessing future out-of-sample holdout data.

## Markets
- **Crypto:** `BTCUSDT` (Binance Spot), `ETHUSDT` (Binance Spot)
- **Forex:** `EUR_USD` (OANDA Practice), `GBP_USD` (OANDA Practice)
- **Timeframe:** 4-hour (4h) exclusively.

## Frozen Dates
- **Historical Dataset (Inclusive):** `2019-01-01T00:00:00Z` to `2024-01-01T00:00:00Z` (exclusive of end).
- **Evaluation Period:** `2020-01-01T00:00:00Z` to `2024-01-01T00:00:00Z`.
- **Warm-up:** The year 2019 is strictly reserved for trend history buffer (e.g. 120-day lookback).

## Reserved Data (Strictly No Access)
- **Confirmation:** `2024-01-01` through `2025-06-30`.
- **Final Protected Holdout:** `2025-07-01` onward.

## Cost Configuration
We use the pre-established Phase 4B cost model with no tuning:
- **Crypto:** `CostModel(taker_fee=0.0005, half_spread=0.00005, slippage=0.0001)`
- **Forex:** `CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)` (Spreads embedded in observed bid/ask).

## Execution Constraints
- Strict next-bar execution constraint. Signals generated at the end of bar `T` execute at the open of bar `T+1`.
- Long exposure target: `1.0`. Short exposure target: `-1.0`. Flat target: `0.0`.
- Point-in-time isolation enforced using `observe_at_utc`. No future data usage.

## Development Screen Pass Criteria
The experiment will be classified as `TREND DEVELOPMENT SCREEN PASSES` only if all the following are true:
1. At least 3 of 4 markets have positive strategy net return.
2. Median strategy net return is positive.
3. Median strategy Sharpe is above 0.50.
4. Worst market net return is above -10%.
5. Median maximum drawdown is at most 20%.
6. At least 2 of 4 markets have higher Sharpe than their always-long baseline.
7. All metrics are finite.
8. No same-bar execution, future leakage, or reserved-data access occurred.

If the criteria are not met, the result is `TREND DEVELOPMENT SCREEN FAILS`.
Under no circumstances will parameters be tuned after running the evaluation.
