# Cycle 02 Phase 4C-02: Outage-Aware Cross-Market Trend Pilot

## Pre-Registration & Policy
The protocol was pre-registered in `docs/cycle_02/research/TREND_PILOT_02_PLAN.md`.
We established an outage policy that allows known, venue-wide missing intervals to be accepted into the historical dataset, provided they are independently verified and no synthetic candles are created. The evaluation metrics switch to elapsed-time-based annualization instead of fixed `bars_per_year`.

## Verification
- **Outage independently verified:** TRUE
- **Outage source:** Binance public kline archive (data.binance.vision)
- **Synthetic candles created:** FALSE

## Data Integrity Audit
All markets were ingested from `2019-01-01T00:00:00Z` to `2024-01-01T00:00:00Z`.
The Binance gap at `1582113600000` (2020-02-19T12:00:00Z) was successfully resolved by the deterministic outage registry.
The dataset sizes confirm successful build without inventing bars:
- **BTCUSDT rows:** 8765 (Evaluation slice) / 9597 (Total)
- **ETHUSDT rows:** 8765 (Evaluation slice) / 9597 (Total)
- **EUR_USD rows:** 6228 (Evaluation slice) / 7783 (Total)
- **GBP_USD rows:** 6228 (Evaluation slice) / 7787 (Total)

## Pilot Results (2020-01-01 to 2024-01-01)

### BTCUSDT
- **Net Return:** 334.10%
- **Sharpe (Ann):** 0.78
- **Max Drawdown:** 8.21%
- **Baseline Long Sharpe:** 0.66
- *Beats baseline Sharpe:* YES

### ETHUSDT
- **Net Return:** 445.88%
- **Sharpe (Ann):** 0.71
- **Max Drawdown:** 49.03%
- **Baseline Long Sharpe:** 0.85
- *Beats baseline Sharpe:* NO

### EUR_USD
- **Net Return:** 5.50%
- **Sharpe (Ann):** 0.22
- **Max Drawdown:** 3.21%
- **Baseline Long Sharpe:** -0.05
- *Beats baseline Sharpe:* YES

### GBP_USD
- **Net Return:** 0.21%
- **Sharpe (Ann):** 0.01
- **Max Drawdown:** 13.38%
- **Baseline Long Sharpe:** -0.10
- *Beats baseline Sharpe:* YES

## Screening Criteria Validation
1. **At least 3 of 4 markets have positive strategy net return:** PASS (4/4 positive)
2. **Median strategy net return is positive:** PASS (0.21, 5.50, 334.10, 445.88 -> Median is 169.80%)
3. **Median strategy Sharpe is above 0.50:** FAIL (0.01, 0.22, 0.71, 0.78 -> Median is 0.465)
4. **Worst market net return is above -10%:** PASS (0.21%)
5. **Median maximum drawdown is at most 20%:** PASS (3.21, 8.21, 13.38, 49.03 -> Median is 10.795%)
6. **At least 2 of 4 markets have higher Sharpe than their always-long baseline:** PASS (3/4 beat baseline)

## Final Classification
**TREND DEVELOPMENT SCREEN FAILS**

*Note: The strategy failed the median Sharpe > 0.50 hurdle by a very narrow margin (0.465).*

## Rules Compliance
- **Confirmation accessed:** FALSE
- **Final holdout accessed:** FALSE
- **Paid resources used:** FALSE
- **Trading performed:** FALSE
