# Strategy Research Workstream 1 — DEV_TRAIN Data Readiness Audit (Post-Backfill)

**Branch**: `research/cycle-02-trend-pilot-02`
**HEAD**: `48d0526463a7dc20e9c6c5d005a9cf748f3e3695`
**Date**: 2026-09-03
**Context**: Post-backfill verification of DEV_TRAIN datasets through guarded APIs. OUTER_VAL, CONFIRMATION, FINAL_HOLDOUT remain inaccessible.

---

## 1. Executive Summary

| Market | Ready | Venue/Product | Interval | DEV_TRAIN Coverage | Gaps | Warm-up | Product Match |
|--------|-------|---------------|----------|-------------------|------|---------|---------------|
| **BTCUSDT** | ✅ **READY** | BINANCE_FUTURES (4h SQLite), BINANCE_FUTURES (15m Parquet) | 4h/15m | 2020-01-01 → 2025-06-30 (complete) | None | Sufficient (61+ months) | PERPETUAL + funding ✅ |
| **ETHUSDT** | ✅ **READY** | BINANCE_FUTURES (4h SQLite) | 4h | 2020-01-01 → 2025-06-30 (complete) | None | Sufficient (60+ months) | PERPETUAL + funding ✅ |
| **EUR_USD** | ⚠️ **PARTIAL** | OANDA_PRACTICE (4h SQLite) | 4h | 2019-01-01 → 2023-12-31 (ends early) | Missing 2024-01-01 → 2025-06-30 | Sufficient (60 months) | FOREX_MARGIN — no funding |
| **GBP_USD** | ⚠️ **PARTIAL** | OANDA_PRACTICE (4h SQLite) | 4h | 2019-01-01 → 2023-12-31 (ends early) | Missing 2024-01-01 → 2025-06-30 | Sufficient (60 months) | FOREX_MARGIN — no funding |

**Overall**: **BTCUSDT and ETHUSDT perpetual (4h) now both have full DEV_TRAIN coverage with funding data.** EUR_USD and GBP_USD remain partial (forex, missing 2024-2025).

---

## 2. Detailed Findings by Market (Post-Backfill)

### 2.1 BTCUSDT — BINANCE_FUTURES (4h SQLite) — **READY**

| Metric | Value |
|--------|-------|
| **Venue** | BINANCE_FUTURES (Binance USD-M Perpetual) |
| **Product Model** | PERPETUAL (requires funding) |
| **Interval** | 4h |
| **Storage** | SQLite (`data/trend_pilot_01.sqlite`) |
| **Earliest** | 2020-01-01T00:00:00Z (1577836800000) |
| **Latest** | 2025-06-30T20:00:00Z (1751313600000) |
| **Total Rows** | 12,048 |
| **Months** | 66 (2020-01 → 2025-06) |
| **Missing Bars** | 0 (verified continuous) |
| **Duplicates** | 0 |
| **Monotonic** | Yes |
| **Warm-up** | 61+ months available before 2025-07-01 (exceeds 721-bar minimum) |
| **Funding Data** | ✅ **STORED** — 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |

**Quality**: Excellent. Continuous 4h coverage from DEV_TRAIN start to DEV_TRAIN end. Native 4h provider data. Funding rates stored alongside klines.

### 2.2 ETHUSDT — BINANCE_FUTURES (4h SQLite) — **READY**

| Metric | Value |
|--------|-------|
| **Venue** | BINANCE_FUTURES (Binance USD-M Perpetual) |
| **Product Model** | PERPETUAL (requires funding) |
| **Interval** | 4h |
| **Storage** | SQLite (`data/trend_pilot_01.sqlite`) |
| **Earliest** | 2020-01-01T00:00:00Z (1577836800000) |
| **Latest** | 2025-06-30T20:00:00Z (1751313600000) |
| **Total Rows** | 12,048 |
| **Months** | 66 (2020-01 → 2025-06) |
| **Missing Bars** | 0 (verified continuous) |
| **Duplicates** | 0 |
| **Monotonic** | Yes |
| **Warm-up** | 61+ months available before 2025-07-01 (exceeds 721-bar minimum) |
| **Funding Data** | ✅ **STORED** — 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |

**Quality**: Excellent. Continuous 4h coverage from DEV_TRAIN start to DEV_TRAIN end. Native 4h provider data. Funding rates stored alongside klines.

### 2.3 EUR_USD — OANDA_PRACTICE (4h SQLite) — PARTIAL (unchanged)

| Metric | Value |
|--------|-------|
| **Venue** | OANDA_PRACTICE (Forex) |
| **Product Model** | FOREX_MARGIN |
| **Interval** | 4h |
| **Storage** | SQLite (`trend_pilot_01`, `trend_pilot_03`) |
| **Earliest** | 2019-01-01T00:00:00Z |
| **Latest** | 2023-12-30T20:00:00Z |
| **Total Rows** | 7,783 |
| **Gap** | Ends 2023-12-31 — missing 2024-01-01 → 2025-06-30 |

### 2.4 GBP_USD — OANDA_PRACTICE (4h SQLite) — PARTIAL (unchanged)

| Metric | Value |
|--------|-------|
| **Venue** | OANDA_PRACTICE (Forex) |
| **Product Model** | FOREX_MARGIN |
| **Interval** | 4h |
| **Storage** | SQLite (`trend_pilot_01`, `trend_pilot_03`) |
| **Earliest** | 2019-01-01T00:00:00Z |
| **Latest** | 2023-12-30T20:00:00Z |
| **Total Rows** | 7,787 |
| **Gap** | Ends 2023-12-31 — missing 2024-01-01 → 2025-06-30 |

---

## 3. Product/Model Compatibility Matrix

| Market | Venue | Required Model | Allowed Exposure | Funding Required |
|--------|-------|----------------|------------------|------------------|
| BTCUSDT | BINANCE_FUTURES | PERPETUAL | BIDIRECTIONAL | YES ✅ STORED |
| ETHUSDT | BINANCE_FUTURES | PERPETUAL | BIDIRECTIONAL | YES ✅ STORED |
| EUR_USD | OANDA_PRACTICE | FOREX_MARGIN | BIDIRECTIONAL | NO (carry) |
| GBP_USD | OANDA_PRACTICE | FOREX_MARGIN | BIDIRECTIONAL | NO (carry) |

**No product mismatches found** in stored data. All venues match declared product types.

---

## 4. Data Gaps Summary (Post-Backfill)

| Market | Venue | Missing Period | Impact |
|--------|-------|----------------|--------|
| BTCUSDT | BINANCE_FUTURES | **None** | Full coverage ✅ |
| ETHUSDT | BINANCE_FUTURES | **None** | Full coverage ✅ |
| EUR_USD | OANDA_PRACTICE | 2024-01-01 → 2025-06-30 | Two years missing |
| GBP_USD | OANDA_PRACTICE | 2024-01-01 → 2025-06-30 | Two years missing |

---

## 5. Warm-Up Sufficiency

All crypto markets with data starting 2020-01-01 provide 66 months of data before DEV_TRAIN end. This exceeds the 721-bar (120-day) minimum for 4h timeframe and provides ample warm-up for any indicator.

---

## 6. Funding Data Status (Post-Backfill)

| Market | Venue | Funding in Storage | Coverage |
|--------|-------|-------------------|----------|
| BTCUSDT | BINANCE_FUTURES | ✅ **YES** | 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |
| ETHUSDT | BINANCE_FUTURES | ✅ **YES** | 6,024 rates, 2020-01-01 → 2025-06-30, zero gaps |
| EUR_USD/GBP_USD | OANDA_PRACTICE | N/A (Forex carry) | N/A |

**Funding is now complete for both BTCUSDT and ETHUSDT perpetual evaluation.**

---

## 7. Reconciliation with Phase 4 Negative Evidence

Phase 4C/04D reports (BTCUSDT/ETHUSDT perpetual trend pilots) showed:
- BTCUSDT perpetual: Net return 367%, Sharpe 0.84, Max DD 55.86% — failed 15% DD gate
- ETHUSDT perpetual: Net return 396%, Sharpe 0.64, Max DD 64.27% — failed 15% DD gate
- EUR_USD/GBP_USD forex: Low returns, failed to beat baseline

**Implication**: Trend-following on these markets at 4h/15m intervals with default parameters failed Phase 4 DD thresholds. Strategy Research must either:
1. Improve risk management (trailing stops, position sizing)
2. Test different parameter regimes
3. Accept higher DD with stronger statistical validity
4. Pivot to different signal families

---

## 8. Access Control Verification

- ✅ All backfill/validation performed via guarded APIs (`ingest_historical_range()`, `BinanceFuturesProvider.fetch_funding_rates()`, `SQLiteStorage.query_funding_rates()`)
- ✅ OUTER_VAL (2025-07-01 → 2026-03-01) **not accessed**
- ✅ CONFIRMATION (2026-03-01 → 2026-07-01) **not accessed**
- ✅ FINAL_HOLDOUT (2026-07-01 → 2027-01-01) **not accessed**
- ✅ No data downloaded outside DEV_TRAIN window
- ✅ No Spot data substituted for Perpetual

---

## 9. Verdict

**DATA_READINESS_VERDICT: READY for BTCUSDT + ETHUSDT Perpetual (4h)**

- **BTCUSDT BINANCE_FUTURES (4h)**: ✅ **READY** — Full DEV_TRAIN coverage, continuous, product-consistent, funding stored
- **ETHUSDT BINANCE_FUTURES (4h)**: ✅ **READY** — Full DEV_TRAIN coverage, continuous, product-consistent, funding stored
- **BTCUSDT BINANCE_FUTURES (15m Parquet)**: ✅ **READY** — Alternative higher-resolution dataset
- **EUR_USD / GBP_USD (OANDA)**: ⚠️ **PARTIAL** — Missing 2024-2025 data (forex, requires separate backfill)

**Recommendation**: Proceed with TrendEngine V1+ candidates on **BTCUSDT and ETHUSDT BINANCE_FUTURES (4h)** as primary markets. Both have complete DEV_TRAIN coverage with native 4h data and full funding history. Product-model guards are satisfied.

---

## 10. Blocker for Strategy Research

**None for BTCUSDT + ETHUSDT 4h Perpetual** — ready for candidate evaluation on DEV_TRAIN.

Other markets: EUR_USD/GBP_USD require data backfill before full DEV_TRAIN evaluation. This is an ingestion task, not a guard bypass.

---

**END OF POST-BACKFILL AUDIT** — No market data downloaded outside DEV_TRAIN, no OUTER_VAL/CONFIRMATION/FINAL_HOLDOUT accessed, no strategy backtests run, no synthetic/fabricated data.