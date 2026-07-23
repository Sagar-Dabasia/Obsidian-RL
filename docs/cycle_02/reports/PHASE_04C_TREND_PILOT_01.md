# Cycle 02 Phase 4C: Fixed Cross-Market Trend Historical Pilot 01

## Pre-Registration
Plan committed prior to execution in `docs/cycle_02/research/TREND_PILOT_01_PLAN.md`.
Dates: 2020-01-01 to 2024-01-01. Warm-up: 2019.

## Execution and Validation
Command used for ingestion:
```bash
python tools/build_trend_pilot_dataset.py
```
Exit code: 0 (Tool continued despite BTCUSDT and ETHUSDT failing).
Download runtime: < 1 minute (Forex data loaded efficiently).

### Dataset Manifests
- `BTCUSDT`: Failed (Gap detected at `1552377600000`)
- `ETHUSDT`: Failed (Gap detected at `1552377600000`)
- `EUR_USD`: 7783 rows
- `GBP_USD`: 7787 rows
Combined manifest written to `artifacts/cycle_02/manifests/TREND_PILOT_01_COMBINED.json`.

Data quality: Failed. Crypto series contain genuine gaps (e.g. Binance maintenance on March 12, 2019), causing the strict point-in-time and no-gap rules to correctly reject the crypto data segments. No gap filling was attempted.

## Backtest Results
Backtest command for EUR_USD:
```bash
python tools/run_trend_backtest.py --database data/trend_pilot_01.sqlite --asset-class FOREX --venue OANDA_PRACTICE --symbol EUR_USD --timeframe 4h --start-ms 1577836800000 --end-ms 1704067200000 --taker-fee 0.0 --half-spread 0.0 --slippage 0.0
```

### EUR_USD Metrics
- **Strategy Net Return:** 5.50%
- **Strategy Gross Return:** 5.50%
- **Maximum Drawdown:** 3.21%
- **Sharpe (Ann.):** 0.26
- **Hit Rate:** 55.78%
- **Trades:** 411
- **Total Costs:** 0.00
- **Exposure:** 52.51%
- **Baseline Long Sharpe:** -0.06 (Return: -1.64%)

### GBP_USD Metrics
- **Strategy Net Return:** 0.21%
- **Strategy Gross Return:** 0.21%
- **Maximum Drawdown:** 13.38%
- **Sharpe (Ann.):** 0.01
- **Hit Rate:** 60.37%
- **Trades:** 439
- **Total Costs:** 0.00
- **Exposure:** 50.69%
- **Baseline Long Sharpe:** -0.12 (Return: -3.97%)

### BTCUSDT & ETHUSDT Metrics
- N/A (Failed ingestion)

## Eligibility Check
1. At least 3 of 4 markets have positive strategy net return: **FAIL** (Only 2 markets successfully ran)
2. Median strategy net return is positive: **N/A**
3. Median strategy Sharpe is above 0.50: **N/A**
4. Worst market net return is above -10%: **N/A**
5. Median maximum drawdown is at most 20%: **N/A**
6. At least 2 of 4 markets have higher Sharpe than their always-long baseline: **PASS** (Both Forex markets beat baseline)
7. All metrics are finite: **FAIL** (Missing crypto data)
8. No same-bar execution, future leakage or reserved-data access occurred: **PASS**

## Final Classification
**EXPERIMENT INVALID**

### Confirmations
- Settings were completely unchanged from the pre-registered plan.
- The SQLite database and market bar data were NOT committed to the repository.
- The confirmation (2024 to 2025-06) and final holdout (2025-07+) periods were untouched and unqueried.
- No paid resources or paper/live trading was used.
- Execution was strictly on the next bar.
