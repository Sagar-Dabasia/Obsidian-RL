# Cycle 02 Phase 4C-R: Trend Pilot 01 Data Recovery

## Pre-Registration
Recovery rules were pre-registered in `docs/cycle_02/research/TREND_PILOT_01_DATA_RECOVERY_PLAN.md`.
The requirement was 721 continuous warm-up 4h bars, with NO evaluation gaps allowed and NO synthetic bars created.

## Ingestion and Recovery Audit
Command: `python tools/build_trend_pilot_dataset.py`

### Gap Audit Results
**BTCUSDT Gaps Identified**:
- `1552363200000` (WARM-UP) - Refetched 3 times, empty.
- `1557892800000` (WARM-UP) - Refetched 3 times, empty.
- `1565841600000` (WARM-UP) - Refetched 3 times, empty.
- `1582113600000` (EVALUATION) - Refetched 3 times, empty. **FATAL**

**ETHUSDT Gaps Identified**:
- `1552363200000` (WARM-UP) - Refetched 3 times, empty.
- `1557892800000` (WARM-UP) - Refetched 3 times, empty.
- `1565841600000` (WARM-UP) - Refetched 3 times, empty.
- `1582113600000` (EVALUATION) - Refetched 3 times, empty. **FATAL**

Because Binance had a genuine outage spanning `1582113600000` (2020-02-19), which lands squarely inside the `2020-01-01` to `2023-12-31` evaluation window, the crypto historical dataset could not be safely built without introducing forward-looking gaps or inventing synthetic bars.

Therefore, the builder correctly rejected the crypto sets and aborted generation of `TREND_PILOT_01R_COMBINED.json`.

- **BTCUSDT rows**: N/A
- **ETHUSDT rows**: N/A
- **EUR_USD rows**: 7783 (Existing local database unchanged)
- **GBP_USD rows**: 7787 (Existing local database unchanged)

## Forex Backtest Results
Backtest commands were rerun exactly as in Phase 4C.

- **EUR_USD Strategy Net Return:** 5.50% (Sharpe 0.26, identical)
- **GBP_USD Strategy Net Return:** 0.21% (Sharpe 0.01, identical)

Forex metrics exactly reproduce Phase 4C outputs, confirming point-in-time and calculation integrity was not compromised by the recovery rule updates.

## Eligibility Check
1. At least 3 of 4 markets have positive strategy net return: **FAIL** (Only 2 passed, rest N/A)
2. Median strategy net return is positive: **N/A**
3. Median strategy Sharpe is above 0.50: **N/A**
4. Worst market net return is above -10%: **N/A**
5. Median maximum drawdown is at most 20%: **N/A**
6. At least 2 of 4 markets have higher Sharpe than their always-long baseline: **PASS** (2/2)
7. All metrics are finite: **FAIL** (Missing crypto gaps in evaluation period)

## Final Classification
**EXPERIMENT INVALID**

### Integrity
- No synthetic bars were created or interpolated.
- Confirmation (2024 to 2025-06) and holdout (2025-07+) periods remained entirely untouched.
- No real or paper trades were executed.
- No paid resources were used.
- The datasets generated correctly obeyed the continuous warm-up (721 bars) and evaluation gap prohibition constraints.
