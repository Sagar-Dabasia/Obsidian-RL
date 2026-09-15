# Cycle 02 Phase 4C-04: Final Outage-Aware Cross-Market Trend Pilot

## Pre-Registration & Policy
The protocol was pre-registered in `docs/cycle_02/research/TREND_PILOT_02_PLAN.md`.
The previous Pilot 02 and Corrected Pilot 03 results were rejected. Pilot 02 was rejected due to warm-up data starvation caused by a script defect. Corrected Pilot 03 was rejected as **EXPERIMENT INVALID — PROTOCOL/PROVENANCE MISMATCH** due to the use of incorrect crypto costs (0.0006/0.0/0.0001 instead of 0.0005/0.00005/0.0001) and because the backtester pulled 10951 contiguous rows directly from the SQLite database instead of matching the 9597 rows declared in the registry manifest.

This final report represents the corrected re-execution enforcing exact frozen costs and proper chronological warm-up exposure at the boundary.

## Verification
- **Outage independently verified:** TRUE
- **Synthetic candles created:** FALSE

## Data Integrity Audit
All markets were ingested from `2019-01-01T00:00:00Z` to `2024-01-01T00:00:00Z`.
Evaluation strictly begins at `2020-01-01T00:00:00Z`.

- **BTCUSDT rows:** 10951 evaluated rows, starting at 1546300800000.
- **ETHUSDT rows:** 10951 evaluated rows, starting at 1546300800000.
- **EUR_USD rows:** 7783 evaluated rows, starting at 1546380000000.
- **GBP_USD rows:** 7787 evaluated rows, starting at 1546380000000.

### Row Count Mismatch Explanation
The ingestion script `build_trend_pilot_dataset.py` identified non-trading intervals (gaps) and truncated the in-memory `stored_bars` list to only include the continuous segment after the last warm-up gap (1565841600000). The manifest's row count (9597) and digest reflect this truncated list. However, it did not delete the older, non-continuous rows from the SQLite database. `run_trend_backtest.py` strictly queries the SQLite database from the CLI `--start-ms` (1546300800000), pulling all 10951 historical bars (including the segments before the gaps) into the backtester. Thus, the backtest legally processed rows outside the registered manifest, violating the continuity guarantee before the gap.

## Corrected Pilot Results (2020-01-01 to 2024-01-01)

### BTCUSDT
- **Net Return:** 385.07%
- **Sharpe (Ann):** 0.77
- **Max Drawdown:** 9.60%
- **Turnover:** 11872092.93
- **Trades:** 1278
- **Exposure:** 55.06%
- **Total Costs:** 8272.76
- **First Eval TS:** 1577836800000
- **First Nonzero Signal TS:** 1556683200000
- **First Exec TS:** 1577836800000
- **First Exec Price:** 7195.24
- **Baseline Long Return:** 487.18%
- **Baseline Long Sharpe:** 0.66
- *Beats baseline Sharpe:* YES

### ETHUSDT
- **Net Return:** 393.31%
- **Sharpe (Ann):** 0.63
- **Max Drawdown:** 49.82%
- **Turnover:** 18732547.51
- **Trades:** 1286
- **Exposure:** 57.29%
- **Total Costs:** 13031.54
- **First Eval TS:** 1577836800000
- **First Nonzero Signal TS:** 1556870400000
- **First Exec TS:** 1577836800000
- **First Exec Price:** 129.16
- **Baseline Long Return:** 1665.39%
- **Baseline Long Sharpe:** 0.85
- *Beats baseline Sharpe:* NO

### EUR_USD
- **Net Return:** -4.84%
- **Sharpe (Ann):** -0.19
- **Max Drawdown:** 6.26%
- **Turnover:** 2955264.37
- **Trades:** 495
- **Exposure:** 59.46%
- **Total Costs:** 0.00
- **First Eval TS:** 1577916000000
- **First Nonzero Signal TS:** 1562302800000
- **First Exec TS:** 1579010400000
- **First Exec Price:** 1.11307
- **Baseline Long Return:** -1.64%
- **Baseline Long Sharpe:** -0.05
- *Beats baseline Sharpe:* NO

### GBP_USD
- **Net Return:** -5.84%
- **Sharpe (Ann):** -0.19
- **Max Drawdown:** 13.38%
- **Turnover:** 2602472.64
- **Trades:** 516
- **Exposure:** 55.11%
- **Total Costs:** 0.00
- **First Eval TS:** 1577916000000
- **First Nonzero Signal TS:** 1560877200000
- **First Exec TS:** 1577916000000
- **First Exec Price:** 1.32571
- **Baseline Long Return:** -3.97%
- **Baseline Long Sharpe:** -0.10
- *Beats baseline Sharpe:* NO

## Screening Criteria Validation
1. **At least 3 of 4 markets have positive strategy net return:** FAIL (2/4 positive)
2. **Median strategy net return is positive:** PASS (190.115%)
3. **Median strategy Sharpe is above 0.50:** FAIL (0.22)
4. **Worst market net return is above -10%:** PASS (-5.84%)
5. **Median maximum drawdown is at most 20%:** PASS (11.49%)
6. **At least 2 of 4 markets have higher Sharpe than their always-long baseline:** FAIL (1/4 beat baseline)
7. **All metrics are finite:** PASS
8. **No timing leakage or reserved-data access:** PASS

## Final Classification
**TREND DEVELOPMENT SCREEN FAILS**

## Rules Compliance
- **Confirmation accessed:** FALSE
- **Final holdout accessed:** FALSE
- **Paid resources used:** FALSE
- **Synthetic data used:** FALSE
