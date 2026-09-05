# TrendEngine V1 Perpetual Baseline — Preregistration

**Status**: PREREGISTERED (do not modify after commitment)
**Branch**: `research/cycle-02-trend-pilot-02`
**Date**: 2026-09-04
**Context**: First product-correct BTC/ETH perpetual trend experiment. Phase 4D INVALID — no parameter reuse.

---

## 1. Experiment Identity

| Field | Value |
|-------|-------|
| **Experiment ID** | TREND_V1_PERPETUAL_BASELINE |
| **Branch** | `research/cycle-02-trend-pilot-02` |
| **Parent Commit** | `9edfa0ed1f382d8110633c3208e413d1d8bc972f` |
| **Purpose** | Establish first product-correct perpetual trend baseline |
| **Phase 4D Status** | INVALID — no parameter reuse permitted |

---

## 2. Assets & Product

| Asset | Venue | Product Model | Exposure Policy | Funding Required |
|-------|-------|---------------|-----------------|------------------|
| BTCUSDT | BINANCE_FUTURES | MarketModel.PERPETUAL | ExposurePolicy.BIDIRECTIONAL | YES (stored rates) |
| ETHUSDT | BINANCE_FUTURES | MarketModel.PERPETUAL | ExposurePolicy.BIDIRECTIONAL | YES (stored rates) |

**Provider**: BINANCE_FUTURES (Binance USD-M Perpetual)  
**Data Source**: BINANCE_FUTURES_REST (native 4h klines + funding rates)  
**No Spot substitution, no synthetic data, no interpolation**

---

## 3. Timeframe & Warm-up
|
| Parameter | Value |
|-----------|-------|
| **Interval** | 4h (native BINANCE_FUTURES 4h klines) |
| **Pre-signal History** | [2019-11-27T04:00:00Z, 2020-03-26T04:00:00Z) — 720 native 4h bar opens |
| **721st Signal-Formation Bar** | 2020-03-26T04:00:00Z (1585195200000) |
| **Total Signal-Input Bars** | 721 (720 pre-signal + 1 signal-formation) |
| **First Execution / Scoring Start** | 2020-03-26T08:00:00Z (eval_start_ms = 1585209600000) |
| **Scoring Window** | [2020-03-26T08:00:00Z, 2025-07-01T00:00:00Z) |
| **Scoring End Exclusive** | 2025-07-01T00:00:00Z (DEV_TRAIN end) |

**Causal Execution**: NEXT_BAR_OPEN — signal on bar T executes at bar T+1 open.

---

## 4. TrendEngine Configuration (FROZEN)

```python
TrendConfig(
    short_horizon_days=20,   # 20 days EXACTLY
    medium_horizon_days=60,  # 60 days EXACTLY  
    long_horizon_days=120,   # 120 days EXACTLY
    # NO grid search, NO parameter tuning in this experiment
)
```

**No grid search, no parameter tuning, no walk-forward optimization in this experiment.**

---

## 5. Cost Model (FROZEN)

| Cost Component | Value | Source |
|----------------|-------|--------|
| taker_fee | 0.0005 (5 bps) | Binance standard |
| half_spread | 0.00005 (0.5 bps) | Typical perpetual |
| slippage | 0.0001 (1 bp) | Conservative |
| **Funding** | Actual stored rates applied | BINANCE_FUTURES_REST |

**Funding applied per-bar at funding timestamps using stored BINANCE_FUTURES_REST rates.**

---

## 5. Scoring Window
|
| Boundary | Timestamp (UTC) | Milliseconds |
|----------|-----------------|--------------|
| **Scoring Start (eval_start_ms)** | 2020-03-26T08:00:00Z | 1585209600000 |
| **Scoring End (exclusive)** | 2025-07-01T00:00:00Z | 1751328000000 |
| **Pre-signal History Complete** | 2020-03-26T04:00:00Z | 1585195200000 (720 bar opens) |
| **721st Signal-Formation Bar** | 2020-03-26T04:00:00Z | 1585195200000 |
| **Total Signal-Input Bars** | 721 (720 pre-signal + 1 signal-formation) |
| **First Execution / Scoring Start** | 2020-03-26T08:00:00Z | Signal from 04:00 bar executes at 08:00 open |

**Half-open scoring window**: [1585209600000, 1751328000000)

---

## 6. Execution & Cost Assumptions

| Assumption | Value |
|------------|-------|
| **Execution** | NEXT_BAR_OPEN (causal) |
| **Signal on bar T** | Executes at bar T+1 open |
| **Funding** | Applied at exact funding timestamps from stored rates |
| **Liquidation** | Terminal episode close only — no exchange liquidation/margin-call model. max_abs_exposure = 1.0. Any open terminal position closed at LAST_BAR_CLOSE. |
| **Costs applied** | Per trade: fee + half_spread + slippage |

---

## 7. Required Outputs (Per Asset)

When executed, the experiment MUST produce for each asset (BTCUSDT, ETHUSDT separately):

| Metric | Required |
|--------|----------|
| **Net return** | Yes |
| **Gross return (pre-cost)** | Yes |
| **Annualized Sharpe** | Yes |
| **Max drawdown (path)** | Yes |
| **Trade count** | Yes |
| **Trades per year** | Yes |
| **Notional turnover** | Yes |
| **Total trading costs** | Yes (fee + spread + slippage) |
| **Total funding paid/received** | Yes |
| **Average exposure** | Yes |
| **FLAT baseline** | Yes (cash) |
| **LONG baseline** | Yes (buy & hold) |

---

## 7. Phase 4D Invalidation — Explicit Acknowledgment

| Phase 4D Result | Status | Usage in This Experiment |
|-----------------|--------|-------------------------|
| BTCUSDT: 367% return, 55.86% DD | **INVALID** | **MUST NOT** influence any parameter |
| ETHUSDT: 396% return, 64.27% DD | **INVALID** | **MUST NOT** influence any parameter |
| Product: Spot → Perpetual+BIDIRECTIONAL | **INVALID** | Product mismatch |
| Exposure: SPOT + BIDIRECTIONAL | **INVALID** | Explicitly rejected by system |
| Funding: None applied | **INVALID** | Perpetual requires funding |

**No parameter, risk model, or strategy choice in this experiment may reference Phase 4D results.**  
TrendConfig (20/60/120) is a priori, not derived from Phase 4D.

---

## 7. Data Access Governance
|
- ✅ DEV_TRAIN only [2020-01-01, 2025-07-01)
- ✅ Pre-signal history [2019-11-27T04:00, 2020-03-26T04:00) — 720 bar opens, no scored returns
- ✅ 721st signal-formation bar: 2020-03-26T04:00:00Z
- ✅ First execution/scoring: 2020-03-26T08:00:00Z
- ✅ OUTER_VAL [2025-07-01, 2026-03-01) — NOT accessed
- ✅ CONFIRMATION [2026-03-01, 2026-07-01) — NOT accessed
- ✅ FINAL_HOLDOUT [2026-07-01, 2027-01-01) — NOT accessed
- ✅ No Spot data used for perpetual evaluation
- ✅ Actual stored funding rates applied

---

## 8. Success Criteria (For Later Evaluation)

This experiment is a **baseline establishment only**. It does not need to meet profitability thresholds.  
Its purpose: provide a valid, product-correct perpetual trend baseline for future comparison.

When executed, the experiment is "valid" if:
1. All required outputs are produced for both BTCUSDT and ETHUSDT
2. No causal violations (warm-up respected, next-bar execution)
3. No product/model mismatches (PERPETUAL + BIDIRECTIONAL + funding)
4. Phase 4D results not referenced in any parameter or design choice

---

## 9. Governance
|
| Gate | Status |
|------|--------|
| **Data Readiness** | CONDITIONAL (eval_start_ms = 1585209600000) |
| **Product Guard** | SATISFIED (BINANCE_FUTURES → PERPETUAL) |
| **Phase 4D Acknowledgment** | DOCUMENTED (INVALID) |
| **Preregistration** | THIS DOCUMENT (frozen on commit) |
| **Execution Gate** | PENDING (requires explicit authorization) |

**Amendment Record**:
- Original prereg committed before any baseline execution.
- Native SQLite verification (data/trend_pilot_01.sqlite) proved first bar = 2019-11-27T04:00:00Z.
- Warm-up boundary corrected BEFORE any baseline result was observed.
- No strategy/cost/parameter/product/end-window changes.
- BACKTEST_RUN = NO.

**Governance Rule**: Documented pre-execution factual corrections (data-boundary verification) are permitted. Post-result parameter changes are forbidden. Post-execution modifications = protocol violation.

---

**END OF PREREGISTRATION** — No strategy backtest run, no market data downloaded outside DEV_TRAIN, no OUTER_VAL/CONFIRMATION/FINAL_HOLDOUT accessed.