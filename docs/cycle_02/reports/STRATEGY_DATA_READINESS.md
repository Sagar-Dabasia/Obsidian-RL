# Strategy Research Workstream 1 — DEV_TRAIN Data Readiness Audit (Post-Backfill + Warm-up Correction + Preregistration Alignment)

**Branch**: `research/cycle-02-trend-pilot-02`
**HEAD**: `9edfa0ed1f382d8110633c3208e413d1d8bc972f`
**Date**: 2026-09-04
**Context**: Post-backfill verification of DEV_TRAIN datasets through guarded APIs. OUTER_VAL, CONFIRMATION, FINAL_HOLDOUT remain inaccessible.

---

## 1. Executive Summary

| Market | Ready | Venue/Product | Interval | DEV_TRAIN Coverage | Gaps | Warm-up | Product Match |
|--------|-------|---------------|----------|-------------------|------|---------|---------------|
| **BTCUSDT** | ⚠️ **CONDITIONAL** | BINANCE_FUTURES (4h SQLite) | 4h | 2020-01-01 → 2025-06-30 (complete) | None | 209 pre-2020 bars (<721) | PERPETUAL + funding ✅ |
| **ETHUSDT** | ⚠️ **CONDITIONAL** | BINANCE_FUTURES (4h SQLite) | 4h | 2020-01-01 → 2025-06-30 (complete) | None | 209 pre-2020 bars (<721) | PERPETUAL + funding ✅ |
| **EUR_USD** | ⚠️ **PARTIAL** | OANDA_PRACTICE (4h SQLite) | 4h | 2019-01-01 → 2023-12-31 (ends early) | Missing 2024-01-01 → 2025-06-30 | Sufficient (60 months) | FOREX_MARGIN — no funding |
| **GBP_USD** | ⚠️ **PARTIAL** | OANDA_PRACTICE (4h SQLite) | 4h | 2019-01-01 → 2023-12-31 (ends early) | Missing 2024-01-01 → 2025-06-30 | Sufficient (60 months) | FOREX_MARGIN — no funding |

**Overall**: **BTCUSDT and ETHUSDT perpetual (4h) have full DEV_TRAIN coverage with funding data, BUT causal warm-up for scoring starting 2020-01-01 is NOT available** (only 209 pre-2020 native perpetual 4h bars exist). Earliest valid causal scoring start with 721-bar warm-up = **2020-03-26T04:00:00Z** (eval_start_ms = 1585195200000). EUR_USD and GBP_USD remain partial (forex, missing 2024-2025).

---

## 2. Detailed Findings by Market (Post-Backfill + Warm-up Correction)

### 2.1 BTCUSDT — BINANCE_FUTURES (4h SQLite) — **CONDITIONAL**

| Metric | Value |
|--------|-------|
| **Venue** | BINANCE_FUTURES (Binance USD-M Perpetual) |
| **Product Model** | PERPETUAL (requires funding) |
| **Interval** | 4h |
| **Storage** | SQLite (`data/trend_pilot_01.sqlite`) |
| **Earliest (full DEV_TRAIN)** | 2020-01-01T00:00:00Z (1577836800000) |
| **Earliest native perpetual 4h** | 2019-11-27T00:00:00Z (1574827200000) |
| **Pre-2020 native bars** | 209 (from 2019-11-27 to 2019-12-31) |
| **Latest** | 2025-06-30T20:00:00Z (1751313600000) |
| **Total Rows (full DEV_TRAIN)** | 12,048 |
| **Months** | 66 (2020-01 → 2025-06) |
| **Missing Bars** | 0 (verified continuous) |
| **Duplicates** | 0 |
| **Monotonic** | Yes |
| **Pre-2020 warm-up bars** | 209 (< 721 minimum) |
| **721st usable 4h signal bar** | 2020-03-26T00:00:00Z (1585180800000) |
| **Earliest valid eval_start_ms (721 warm-up)** | 2020-03-26T04:00:00Z (1585195200000) |
| **Funding Data** | ✅ **STORED** — 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |

**Quality**: Excellent continuous 4h coverage from 2020-01-01 to 2025-06-30. Native 4h provider data. Funding rates stored alongside klines. **However, only 209 native perpetual 4h bars exist before 2020-01-01 (from 2019-11-27), which is insufficient for the 721-bar (120-day) causal warm-up required for scoring starting 2020-01-01.**

### 2.2 ETHUSDT — BINANCE_FUTURES (4h SQLite) — **CONDITIONAL**

| Metric | Value |
|--------|-------|
| **Venue** | BINANCE_FUTURES (Binance USD-M Perpetual) |
| **Product Model** | PERPETUAL (requires funding) |
| **Interval** | 4h |
| **Storage** | SQLite (`data/trend_pilot_01.sqlite`) |
| **Earliest (full DEV_TRAIN)** | 2020-01-01T00:00:00Z (1577836800000) |
| **Earliest native perpetual 4h** | 2019-11-27T00:00:00Z (1574827200000) |
| **Pre-2020 native bars** | 209 (from 2019-11-27 to 2019-12-31) |
| **Latest** | 2025-06-30T20:00:00Z (1751313600000) |
| **Total Rows (full DEV_TRAIN)** | 12,048 |
| **Months** | 66 (2020-01 → 2025-06) |
| **Missing Bars** | 0 (verified continuous) |
| **Duplicates** | 0 |
| **Monotonic** | Yes |
| **Pre-2020 warm-up bars** | 209 (< 721 minimum) |
| **721st usable 4h signal bar** | 2020-03-26T00:00:00Z (1585180800000) |
| **Earliest valid eval_start_ms (721 warm-up)** | 2020-03-26T04:00:00Z (1585195200000) |
| **Funding Data** | ✅ **STORED** — 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |

**Quality**: Excellent continuous 4h coverage from 2020-01-01 to 2025-06-30. Native 4h provider data. Funding rates stored alongside klines. **However, only 209 native perpetual 4h bars exist before 2020-01-01 (from 2019-11-27), which is insufficient for the 721-bar (120-day) causal warm-up required for scoring starting 2020-01-01.**

---

## 3. Warm-Up Sufficiency (Corrected + Preregistration Aligned)

**Critical Correction**: Previous audit claimed "61+ months available before 2025-07-01" — this measured warm-up availability relative to DEV_TRAIN end, not scoring start. The correct measure for causal indicator initialization is bars available **before the scoring start timestamp**.

| Market | Pre-scoring native 4h bars | Required (721) | Status |
|--------|---------------------------|----------------|--------|
| BTCUSDT | 209 (2019-11-27 → 2020-01-01) | 721 | **INSUFFICIENT** |
| ETHUSDT | 209 (2019-11-27 → 2020-01-01) | 721 | **INSUFFICIENT** |

**Native perpetual 4h history starts**: **2019-11-27T00:00:00Z** (1574827200000)

**721st usable 4h signal bar**: **2020-03-26T00:00:00Z** (1585180800000)

**Earliest valid eval_start_ms (721 warm-up complete)**: **2020-03-26T04:00:00Z** (1585195200000)
- This is the first timestamp where 721 full 4h bars of native perpetual history exist
- First signal bar: 2020-03-26T00:00:00Z (721st completed warm-up bar)
- First execution: 2020-03-26T04:00:00Z (signal from 00:00 bar executes at next bar open)
- First scored bar interval: [2020-03-26T04:00:00Z, 2020-03-26T08:00:00Z)
- Any scoring/evaluation with `eval_start_ms < 1585195200000` is **not causally valid** for 721-bar indicators

**Implication**: Any evaluation/backtest with `eval_start_ms = 1577836800000` (2020-01-01) and indicators requiring 721-bar warm-up is **not causally valid**. The earliest causally valid `eval_start_ms` is **1585195200000 (2020-03-26T04:00:00Z)**.

---

## 4. Product/Model Compatibility Matrix

| Market | Venue | Required Model | Allowed Exposure | Funding Required |
|--------|-------|----------------|------------------|------------------|
| BTCUSDT | BINANCE_FUTURES | PERPETUAL | BIDIRECTIONAL | YES ✅ STORED |
| ETHUSDT | BINANCE_FUTURES | PERPETUAL | BIDIRECTIONAL | YES ✅ STORED |
| EUR_USD | OANDA_PRACTICE | FOREX_MARGIN | BIDIRECTIONAL | NO (carry) |
| GBP_USD | OANDA_PRACTICE | FOREX_MARGIN | BIDIRECTIONAL | NO (carry) |

**No product mismatches found** in stored data. All venues match declared product types.

---

## 5. Data Gaps Summary (Post-Backfill + Warm-up Correction)

| Market | Venue | Missing Period | Impact |
|--------|-------|----------------|--------|
| BTCUSDT | BINANCE_FUTURES | Pre-2019-11-27 (for 721 warm-up) | No 721-bar warm-up for 2020-01-01 scoring |
| ETHUSDT | BINANCE_FUTURES | Pre-2019-11-27 (for 721 warm-up) | No 721-bar warm-up for 2020-01-01 scoring |
| EUR_USD | OANDA_PRACTICE | 2024-01-01 → 2025-06-30 | Two years missing |
| GBP_USD | OANDA_PRACTICE | 2024-01-01 → 2025-06-30 | Two years missing |

---

## 6. Funding Data Status

| Market | Venue | Funding in Storage | Coverage |
|--------|-------|-------------------|----------|
| BTCUSDT | BINANCE_FUTURES | ✅ **YES** | 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |
| ETHUSDT | BINANCE_FUTURES | ✅ **YES** | 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |
| EUR_USD/GBP_USD | OANDA_PRACTICE | N/A (Forex carry) | N/A |

**Funding is complete for both BTCUSDT and ETHUSDT perpetual evaluation.**

---

## 7. Phase 4D Negative Evidence — Classification Corrected

**Phase 4D (Crypto Trend Robustness) results are classified as: INVALID / NO STRATEGY CONCLUSION**

| Issue | Impact |
|-------|--------|
| **Product mismatch** | Phase 4D used BINANCE_SPOT data evaluated as PERPETUAL + BIDIRECTIONAL — this is a product/model mismatch explicitly forbidden by Cycle 2 rules |
| **Wrong exposure policy** | SPOT + BIDIRECTIONAL is explicitly rejected by the system (SPOT only supports LONG_FLAT) |
| **No funding** | Perpetual evaluation requires funding rates; Phase 4D used none |
| **Wrong instrument** | Spot klines ≠ perpetual klines (different funding, liquidation, margin mechanics) |

**Classification**: **INVALID / NO STRATEGY CONCLUSION**

**Usage restriction**: Phase 4D returns/DD/Sharpe metrics **must not** be used for:
- Parameter selection or optimization
- Risk model calibration
- Strategy family selection
- Any evidence supporting TrendEngine V1+ design choices

**Permitted use**: Historical record only — documented as a product-mismatch invalidation case that motivated the Cycle 2 product guard. May be cited as "prior invalid attempt" in audit trail.

---

## 8. Reconciliation with Phase 4 Negative Evidence (Corrected)

| Phase | Result | Validity | Usage |
|-------|--------|----------|-------|
| 4C (Trend Pilot 01) | BTC: 367% return, 55.86% DD | **UNRELATED** — Spot data, different interval (4h), different product | Historical record only |
| 4D (Crypto Trend Robustness) | BTC: 367% return, 55.86% DD | **INVALID** — Spot data run as Perpetual+BIDIRECTIONAL | INVALID — must not inform strategy |
| 4E (Statistical Validity) | Various | Valid for statistical methodology only | Statistical methodology reference only |

**Phase 4D invalidation is the primary reason Cycle 2 enforces the product guard (BINANCE_FUTURES → PERPETUAL, BINANCE_SPOT → SPOT)**.

---

## 9. Access Control Verification

- ✅ All backfill/validation performed via guarded APIs (`ingest_historical_range()`, `BinanceFuturesProvider.fetch_funding_rates()`, `SQLiteStorage.query_funding_rates()`)
- ✅ OUTER_VAL (2025-07-01 → 2026-03-01) **not accessed**
- ✅ CONFIRMATION (2026-03-01 → 2026-07-01) **not accessed**
- ✅ FINAL_HOLDOUT (2026-07-01 → 2027-01-01) **not accessed**
- ✅ No data downloaded outside DEV_TRAIN window
- ✅ No Spot data substituted for Perpetual

---

## 10. Verdict (Corrected + Preregistration Aligned)

**DATA_READINESS_VERDICT: CONDITIONAL for BTCUSDT + ETHUSDT Perpetual (4h)**

- **BTCUSDT BINANCE_FUTURES (4h)**: ⚠️ **CONDITIONAL** — Full DEV_TRAIN coverage, continuous, product-consistent, funding stored. **BUT**: No 721-bar causal warm-up for 2020-01-01 scoring. Earliest causally valid `eval_start_ms` = 1585195200000 (2020-03-26T04:00:00Z).
- **ETHUSDT BINANCE_FUTURES (4h)**: ⚠️ **CONDITIONAL** — Same as BTCUSDT.
- **BTCUSDT BINANCE_FUTURES (15m Parquet)**: ⚠️ **CONDITIONAL** — Same warm-up limitation.
- **EUR_USD / GBP_USD (OANDA)**: ⚠️ **PARTIAL** — Missing 2024-2025 data (forex, requires separate backfill).

**Recommendation**:
- For TrendEngine V1+ candidates requiring 721-bar warm-up: Use `eval_start_ms >= 1585195200000` (2020-03-26T04:00:00Z).
- For candidates not requiring 721-bar warm-up: Full DEV_TRAIN from 2020-01-01 is available.
- Phase 4D results are INVALID and must not inform any parameter/risk/strategy decisions.
- Product-model guards are satisfied for BINANCE_FUTURES perpetual evaluation.

---

## 11. Preregistered First Valid TrendEngine V1+ Baseline

Per `docs/cycle_02/research/TREND_V1_PERPETUAL_BASELINE_PREREG.md`, the first valid experiment is preregistered with:
- **eval_start_ms**: 1585195200000 (2020-03-26T04:00:00Z)
- **Scoring window**: [2020-03-26T04:00:00Z, 2025-07-01T00:00:00Z)
- **Warm-up**: [2019-11-27T00:00:00Z, 2020-03-26T04:00:00Z) — 721 native 4h bars
- **TrendConfig**: 20/60/120 days EXACTLY (no grid search)
- **Product**: BINANCE_FUTURES / PERPETUAL / BIDIRECTIONAL
- **Funding**: Actual stored rates applied

**Phase 4D remains INVALID / NO STRATEGY CONCLUSION — no parameter reuse permitted.**

---

## 12. Blocker for Strategy Research

**Conditional for BTCUSDT + ETHUSDT 4h Perpetual** — Ready for candidate evaluation **with explicit warm-up boundary** (`eval_start_ms >= 1585195200000` for causal 721-bar warm-up).

Other markets: EUR_USD/GBP_USD require data backfill before full DEV_TRAIN evaluation. This is an ingestion task, not a guard bypass.

---

**END OF CORRECTED AUDIT** — No market data downloaded outside DEV_TRAIN, no OUTER_VAL/CONFIRMATION/FINAL_HOLDOUT accessed, no strategy backtests run, no synthetic/fabricated data.