# Cycle 02 Phase 4C-03: Corrected Outage-Aware Cross-Market Trend Pilot

## Pre-Registration & Policy
The protocol was pre-registered in `docs/cycle_02/research/TREND_PILOT_02_PLAN.md`.
The previous Pilot 02 results are marked **INVALID** due to warm-up data starvation caused by a script defect. This report represents the corrected re-execution with `--eval-start-ms` enforcing proper indicator warm-up prior to evaluation.

## Verification
- **Outage independently verified:** TRUE (Carried over from Pilot 02)
- **Synthetic candles created:** FALSE

## Data Integrity Audit
All markets were ingested from `2019-01-01T00:00:00Z` to `2024-01-01T00:00:00Z`. Evaluation strictly starts at `2020-01-01T00:00:00Z`.
- **BTCUSDT rows:** 10951 (Evaluated from local storage, filtered properly dynamically)
- **ETHUSDT rows:** 10951 (Evaluated from local storage, filtered properly dynamically)
- **EUR_USD rows:** 7783
- **GBP_USD rows:** 7787

## Corrected Pilot Results (2020-01-01 to 2024-01-01)

### BTCUSDT
- **Net Return:** 379.84% (Previously 334.10%)
- **Sharpe (Ann):** 0.76 (Previously 0.78)
- **Max Drawdown:** 9.60% (Previously 8.21%)
- **Baseline Long Sharpe:** 0.66
- *Beats baseline Sharpe:* YES
- **Turnover & Trades:** 1278 trades, costs 8221.78

### ETHUSDT
- **Net Return:** 385.07% (Previously 445.88%)
- **Sharpe (Ann):** 0.62 (Previously 0.71)
- **Max Drawdown:** 49.82% (Previously 49.03%)
- **Baseline Long Sharpe:** 0.85
- *Beats baseline Sharpe:* NO
- **Turnover & Trades:** 1286 trades, costs 12952.52

### EUR_USD
- **Net Return:** -4.84% (Previously 5.50%)
- **Sharpe (Ann):** -0.19 (Previously 0.22)
- **Max Drawdown:** 6.26% (Previously 3.21%)
- **Baseline Long Sharpe:** -0.05
- *Beats baseline Sharpe:* NO
- **Turnover & Trades:** 495 trades, costs 0.00

### GBP_USD
- **Net Return:** -5.84% (Previously 0.21%)
- **Sharpe (Ann):** -0.19 (Previously 0.01)
- **Max Drawdown:** 13.38% (Previously 13.38%)
- **Baseline Long Sharpe:** -0.10
- *Beats baseline Sharpe:* NO
- **Turnover & Trades:** 516 trades, costs 0.00

## Screening Criteria Validation
1. **At least 3 of 4 markets have positive strategy net return:** FAIL (2/4 positive)
2. **Median strategy net return is positive:** PASS (187.50%)
3. **Median strategy Sharpe is above 0.50:** FAIL (0.215)
4. **Worst market net return is above -10%:** PASS (-5.84%)
5. **Median maximum drawdown is at most 20%:** PASS (11.49%)
6. **At least 2 of 4 markets have higher Sharpe than their always-long baseline:** FAIL (1/4 beat baseline)
7. **All metrics are finite:** PASS
8. **No timing leakage or reserved-data access:** PASS

## Final Classification
**TREND DEVELOPMENT SCREEN FAILS**

*Note: The corrected warm-up exposure revealed substantial weaknesses in the Forex pairs during Q1 2020 which were previously masked by the warm-up starvation.*

## Rules Compliance
- **Confirmation accessed:** FALSE
- **Final holdout accessed:** FALSE
- **Paid resources used:** FALSE
- **Synthetic data used:** FALSE
