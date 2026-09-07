# TREND_V1_PERPETUAL_BASELINE Result — Immutable Cycle 2 Evidence

**Branch**: `research/cycle-02-trend-pilot-02`
**HEAD**: `d10a01dbd2dcaef6f43b7e2ef02ca702f2f05b27`
**Date**: 2026-09-05
**Status**: FROZEN — No reruns, no modifications permitted.

---

## Executive Summary

This document permanently preserves the results of the first valid Cycle 2 perpetual TrendEngine baseline experiment. All results are genuine negative strategy evidence: the Trend strategy produces positive net returns but **materially underperforms true buy-and-hold** on net return, Sharpe ratio, and funding efficiency. No promotion is justified.

---

## 1. Frozen Experiment Contract (from Preregistration)

| Parameter | Value |
|-----------|-------|
| **Assets** | BTCUSDT, ETHUSDT |
| **Market** | BINANCE_FUTURES / PERPETUAL / BIDIRECTIONAL |
| **Interval** | Native 4h |
| **Pre-signal History** | 720 bars [2019-11-27T04:00:00Z, 2020-03-26T04:00:00Z) |
| **721st Signal Bar** | 2020-03-26T04:00:00Z (1585195200000) |
| **Eval/Scoring Start** | 2020-03-26T08:00:00Z (1585209600000) |
| **End (exclusive)** | 2025-07-01T00:00:00Z (1751328000000) |
| **TrendConfig** | short_horizon_days=20, medium_horizon_days=60, long_horizon_days=120 |
| **Execution** | NEXT_BAR_OPEN |
| **Costs (per side)** | taker=0.0005, half-spread=0.00005, slippage=0.0001 |
| **Funding** | Actual stored BINANCE_FUTURES_REST rates |
| **Governance** | DEV_TRAIN only; no OUTER_VAL/CONFIRMATION/FINAL_HOLDOUT access; no tuning |

---

## 2. TREND Strategy Results (Frozen — Never Rerun)

### BTCUSDT

| Metric | Value |
|--------|-------|
| **Net Return** | +309.81% |
| **Gross Return** | +509.37% |
| **Annualized Sharpe** | 0.57 |
| **Max Drawdown** | 56.19% |
| **Trade Count** | 1,648 |
| **Trades/Year** | ~348 |
| **Turnover** | 18,021,988 |
| **Total Trading Costs** | 11,714.29 |
| **Total Funding** | 8,241.45 |
| **Total Costs (all-in)** | 19,955.74 |
| **Avg Exposure** | 54.85% |

### ETHUSDT

| Metric | Value |
|--------|-------|
| **Net Return** | +196.18% |
| **Gross Return** | +439.21% |
| **Annualized Sharpe** | 0.35 |
| **Max Drawdown** | 67.16% |
| **Trade Count** | 1,750 |
| **Trades/Year** | ~370 |
| **Turnover** | 20,615,606 |
| **Total Trading Costs** | 13,400.14 |
| **Total Funding** | 10,902.67 |
| **Total Costs (all-in)** | 24,302.81 |
| **Avg Exposure** | 53.49% |

---

## 3. TRUE LONG Benchmark Results (Corrected Buy-and-Hold)

*Corrected implementation: one entry at first eval bar, fixed quantity held, no drift rebalancing, terminal close only. See commit `0bf0915` for production fix and `d10a01d` for regression test.*

### BTCUSDT

| Metric | Value |
|--------|-------|
| **Net Return** | +1,257.48% |
| **Gross Return** | +1,525.41% |
| **Annualized Sharpe** | 0.67 |
| **Max Drawdown** | 86.36% |
| **Trade Count** | 2 (entry + terminal close) |
| **Trading Costs** | 112.15 |
| **Funding** | 26,679.94 |
| **All-in Costs** | 26,792.09 |
| **Avg Exposure** | 125.03% |

### ETHUSDT

| Metric | Value |
|--------|-------|
| **Net Return** | +1,098.39% |
| **Gross Return** | +1,742.27% |
| **Annualized Sharpe** | 0.48 |
| **Max Drawdown** | 87.78% |
| **Trade Count** | 2 (entry + terminal close) |
| **Trading Costs** | 126.25 |
| **Funding** | 64,262.02 |
| **All-in Costs** | 64,388.27 |
| **Avg Exposure** | 124.27% |

---

## 4. FLAT Baseline

| Metric | Value |
|--------|-------|
| **Net Return** | 0.00% |
| **Trade Count** | 0 |
| **Trading Costs** | 0.00 |
| **Funding** | 0.00 |
| **All-in Costs** | 0.00 |
| **Avg Exposure** | 0.00% |

---

## 5. Invalid Original LONG Benchmark (Superseded — Preserved as Evidence)

*The original LONG implementation (pre-`0bf0915`) was **NOT true buy-and-hold** — it periodically rebalanced when price/funding-driven exposure drifted outside tolerance.*

| Asset | Original Net Return | Original Trades | Defect |
|-------|---------------------|-----------------|--------|
| BTCUSDT | +1,028.30% | 38 | Periodic rebalancing ≠ buy-and-hold |
| ETHUSDT | +1,092.78% | 44 | Periodic rebalancing ≠ buy-and-hold |

*This invalid result is preserved as superseded evidence; it must NOT be used for comparison or promotion decisions.*

---

## 6. Validity Check

| Check | Status |
|-------|--------|
| DEV_TRAIN only | ✅ [1585209600000, 1751328000000) |
| Native BINANCE_FUTURES 4h | ✅ 12,257 bars loaded per asset |
| Stored actual funding | ✅ 6,024 rates loaded per asset |
| Frozen costs | ✅ taker=0.0005, half-spread=0.00005, slippage=0.0001 |
| 720 pre-signal bars | ✅ [2019-11-27T04:00, 2020-03-26T04:00) |
| 721st signal bar | ✅ 2020-03-26T04:00Z (1585195200000) |
| First execution | ✅ 2020-03-26T08:00Z (1585209600000) |
| End exclusive | ✅ 2025-07-01T00:00Z (1751328000000) |
| TrendConfig 20/60/120 | ✅ Frozen |
| NEXT_BAR_OPEN | ✅ Verified |
| No tuning | ✅ Single execution per asset |
| No protected-window access | ✅ OUTER_VAL/CONFIRMATION/FINAL_HOLDOUT untouched |

---

## 7. History of Corrections

| Commit | Description |
|--------|-------------|
| `0bf0915` | **fix: make long baseline true buy and hold** — Production fix: LONG now enters once, holds fixed quantity, no drift rebalance, terminal close once |
| `d10a01d` | **test: protect true buy and hold baseline** — Restored all 27 original tests + added `test_long_mode_buy_and_hold_semantics` regression test proving true buy-and-hold semantics |

---

## 8. Adjudication & Interpretation

**Overall Classification**: **VALID_GENUINE_RESULT** (genuine negative evidence)

| Dimension | Assessment |
|-----------|------------|
| Mechanics | Valid — no code defects, arithmetic reconciles, funding accounting correct |
| Data | Valid — native perpetual data, stored funding, correct windows |
| Baselines | Comparable — all three use identical eval window, data, costs, funding |

**TREND vs TRUE LONG Comparison:**

| Asset | TREND Net | TRUE LONG Net | TREND Sharpe | TRUE LONG Sharpe | TREND DD | TRUE LONG DD |
|-------|-----------|---------------|--------------|------------------|----------|--------------|
| BTCUSDT | +309.81% | **+1,257.48%** | 0.57 | **0.67** | **56.19%** | 86.36% |
| ETHUSDT | +196.18% | **+1,098.39%** | 0.35 | **0.48** | **67.16%** | 87.78% |

**Key Findings:**
- Trend produces **positive net returns** (genuine, not a defect)
- Trend **materially reduces drawdown** vs buy-and-hold (~30% absolute reduction)
- Trend **substantially underperforms** buy-and-hold on net return (~700-900 bps gap) and Sharpe
- Funding drag on buy-and-hold is massive (26k-64k) due to fixed-quantity perpetual exposure growth
- Trend trades frequently (1,600-1,700 trades) vs buy-and-hold (2 trades)

**Promotion Justified**: **NO** — This baseline establishes a valid perpetual experiment but does NOT demonstrate alpha. The Trend strategy underperforms passive buy-and-hold on risk-adjusted returns. This is genuine negative evidence for the next research hypothesis.

---

## 9. Immutable Record Declaration

This result document is **immutable Cycle 2 evidence**. No future rerun, retuning, or reinterpretation may alter these numbers. The original invalid LONG benchmark is preserved as superseded evidence. The Trend results were never rerun after the LONG correction.

**Next Research Step**: Formulate next hypothesis using this baseline as diagnostic evidence (e.g., funding-aware sizing, regime filtering, cost optimization).

---

*End of TREND_V1_PERPETUAL_BASELINE Result Record*