# Strategy Research Plan — Cycle 2

**Status**: DRAFT (awaiting review)\
**Branch**: `research/cycle-02-trend-pilot-02`\
**Date**: 2026-09-01\
**Context**: Phase 6 (TradingView Interop) complete — engineering infrastructure frozen.

---

## 1. Objective

Discover a **profitable, net-of-cost trading signal** for the Obsidian-RL multi-asset portfolio engine, using the fully validated Phase 5/6 infrastructure as a fixed evaluation harness.

**Success criteria** (all must be satisfied):

| Metric | Threshold | Notes |
|--------|-----------|-------|
| **Positive net-of-cost OOS performance** | > 0 | After *all* market-specific costs (fees, spread, slippage, funding) |
| **Portfolio max drawdown** | ≤ 15% | Path maximum drawdown on holdout period |
| **Stability** | Positive on ≥2 independent assets/folds | Across multiple independent assets and chronological folds |
| **Turnover** | Explicitly measured | Trades/year per asset and notional turnover (not ambiguous "<2x") |
| **Baseline comparison** | Required | Always-long / buy-and-hold benchmark on identical data |
| **Statistical validity** | Per Phase 4E | PSR/DSR where applicable; PBO/CPCV deferred until computable |
| **All metrics finite & reproducible** | Required | No NaN/Inf; deterministic on repeated runs |

> **Note**: Annualized Net Sharpe > 1.0 may remain as a clearly labeled **promotion target**, not proof of profitability. Hit-rate > 52% is **removed** as a universal hard gate. Thresholds are frozen BEFORE strategy results are observed.

---

## 2. Evaluation Harness (Frozen — Do Not Modify)

The following components are **locked** and must not be changed during research:

| Component | File | Version |
|-----------|------|---------|
| Portfolio Engine | `src/obsidian_rl/portfolio/engine.py` | Batch 2 fixed |
| Cost Model | `src/obsidian_rl/portfolio/costs.py` | Market-specific canonical costs (see §5) |
| Risk Engine | `src/obsidian_rl/engines/risk.py` | Batch 3 cleaned |
| Multi-Asset Accounting | `src/obsidian_rl/engines/portfolio_combination.py` | Phase 5 |
| Data Schema / Contracts | `src/obsidian_rl/data/contracts.py` | Phase 5 |
| Webhook Receiver | `src/obsidian_rl/interop/webhook_receiver.py` | Phase 6 |
| Pine Script Indicator | `pine/ObsidianMultiAssetTrend.pine` | Phase 6 |

**Test suite**: `pytest tests/ -q` (816 tests) must pass before any research artifact is considered.

---

## 3. Data & Holdout Protocol — Four-Tier Governance

Per `docs/cycle_02/research/CYCLE_02_RESEARCH_REGISTER.md`, Cycle 02 enforces **four-tier window governance**. Calendar dates are **NOT frozen yet** — they must be formally defined and committed to `docs/CYCLE_02_EXPERIMENTAL_WINDOWS.md` before any data is downloaded or inspected.

### 3.1 Four Tiers (Strict Isolation)

| Tier | Purpose | Access |
|------|---------|--------|
| **DEV_TRAIN** | Engine design, indicator validation, Phase 9 ML cross-validation | Open read/write during Phases 4–9 |
| **OUTER_VAL** | Walk-forward fold evaluation, pass/fail per completed engine phase | Isolated; used once per phase |
| **CONFIRMATION** | One-time verification of finalized composite (Phase 8/9) before paper trading | **Locked**; loaded only after ALL OUTER_VAL criteria passed |
| **FINAL_HOLDOUT** | Ultimate out-of-sample benchmark across all cycles | **STRICTLY LOCKED AND UNTOUCHED** — no access during Cycle 02 |

### 3.2 Contamination Policy — Historical Exposure Inventory

**Repository-supported exposure periods (already inspected/evaluated — excluded from FINAL_HOLDOUT):**

| Period | Purpose | Source |
|--------|---------|--------|
| **2020-01-01 → 2022-11-26** | Cycle 1 PPO replication (`PPO_REPLICATION_2020_2022`) | `docs/archive/cycle_01/reports/PPO_REPLICATION_2020_2022.md` |
| **2023-01-01 → 2025-06-30** | Cycle 1 historical screening/evaluation | `docs/archive/cycle_01/reports/HISTORICAL_PILOT_01.md` |
| **2025-05-27 → 2025-06-30** | Cycle 1 development-confirmation exposure (PPO ensemble failed) | `docs/cycle_02/research/CYCLE_02_RESEARCH_REGISTER.md` |
| **2019-08-15 → 2020-01-01** | Phase 4 warm-up/history exposure (721 bars required, 590 available) | `docs/cycle_02/research/PHASE_04C_R3_REPORT.md` |
| **2020-01-01 → 2024-01-01 exclusive** | Phase 4C/4D evaluation exposure (crypto + forex) | `PHASE_04C_TREND_PILOT_01.md`, `PHASE_04D_CRYPTO_TREND_ROBUSTNESS.md` |

**Current reservoir status per repository evidence:**

- **Cycle 2 CONFIRMATION window**: Dates UNASSIGNED — Phase 4C/4D reports state their *then-reserved* confirmation period (2024 to 2025-06) was untouched, **however overlapping dates were already exposed by Cycle 1 research (2023-01-01 → 2025-06-30)**. Therefore those dates cannot automatically serve as a pristine future Cycle 2 CONFIRMATION or FINAL_HOLDOUT. New `DEV_TRAIN`, `OUTER_VAL`, `CONFIRMATION`, and `FINAL_HOLDOUT` dates remain **UNASSIGNED** and require separate preregistration using contamination-aware boundaries. `FINAL_HOLDOUT` must be selected only from data not previously inspected.
- **FINAL_HOLDOUT**: Locked/untouched — all reports confirm final holdout (2025-07+) "strictly prohibited" / "untouched" / "zero access verified across all audit logs".
- **CYCLE_02_EXPERIMENTAL_WINDOWS.md**: Absent — recorded as a governance gap requiring a later preregistration task (not created in this task).

**Important distinction:** The above dates are an **exposure inventory of already-inspected periods**, NOT the new Cycle 2 experimental-window assignment. Future `DEV_TRAIN`, `OUTER_VAL`, `CONFIRMATION`, and `FINAL_HOLDOUT` calendar dates require separate formal preregistration before any data access.

- Any historical period already inspected/evaluated in Cycle 2 (Phase 4D crypto screen, Phase 4E statistical review) is **excluded from FINAL_HOLDOUT**.
- `docs/CYCLE_02_EXPERIMENTAL_WINDOWS.md` is **absent** — recorded as a governance gap requiring a later preregistration task (not created in this task).
- No retroactive shifting of window boundaries once frozen.
- CONFIRMATION is **one-time and distinct** from FINAL_HOLDOUT.

### 3.3 Data Sources & Quality

- **Primary**: Binance spot & perpetual klines (4h, 1d) via `src/obsidian_rl/data/binance_client.py`
- **Assets**: BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, DOGEUSDT, BNBUSDT (expandable per provenance rules)
- **Quality**: `DataQualityReport` must pass (no gaps > 1 bar, no stale prices, no negative volumes)

---

## 4. Research Methodology

### 4.1 Signal Families to Explore (Prioritized)

| Priority | Family | Description | Expected Turnover |
|----------|--------|-------------|-------------------|
| 1 | **TrendEngine V1+** | Extend EMA horizons (20/60/120 → 30/90/180, 50/150/300) | Low |
| 2 | **Multi-Timeframe Confluence** | 4h + 1d alignment (both must agree) | Very Low |
| 3 | **Volatility-Adjusted Trend** | Scale position by inverse vol (target constant risk) | Medium |
| 4 | **Cross-Asset Momentum** | BTC lead → ETH/SOL follow (lagged correlation) | Medium |
| 5 | **Funding Rate Basis** | Perpetual funding as carry signal (perp vs spot) | Low |
| 6 | **Regime-Switching** | HMM on vol/correlation; different signal per regime | Low |
| 7 | **ML Meta-Filter (LightGBM)** | Features: returns, vol, funding, OI, basis; Target: next-bar direction | Medium-High |

> **ML Constraint**: The ML classifier is **NOT a revival of the retired standalone Alpha Gate** (Cycle 1, permanently retired). It must follow the **Phase 9 meta-filter contract**: veto/down-weight only (`multiplier ∈ [0.0, 1.0]`), never invert or independently create directional trades. Future Cycle 2 ML use requires a genuinely new preregistered hypothesis with separate approval.

### 4.2 Research Loop (Per Candidate)

```
1. IMPLEMENT signal in Python (src/obsidian_rl/signals/<name>.py)
2. BACKTEST on DEV_TRAIN (walk-forward, expanding window, chronological folds)
3. VALIDATE on OUTER_VAL (single run, no tuning)
4. If OUTER_VAL passes thresholds → DOCUMENT in research log
5. Only after ≥2 independent candidates pass OUTER_VAL → CONFIRMATION test (one-time)
6. CONFIRMATION result → FINAL_HOLDOUT remains locked; promotion requires full governance gate
```

### 4.3 Walk-Forward Protocol (Proposed Preregistered Protocol)

The **1-year train / 1-month test rolling** window may be used **only if**:

- Folds are strictly chronological (no look-ahead).
- Folds remain entirely inside authorized DEV_TRAIN / OUTER_VAL data.
- CONFIRMATION and FINAL_HOLDOUT are **never** rolled through.
- No parameter tuning uses OUTER_VAL metrics.
- Protocol is **preregistered** in `docs/CYCLE_02_EXPERIMENTAL_WINDOWS.md` before execution.

**Metrics tracked per fold**: Net Sharpe, Max DD, Turnover (trades/year & notional), #Trades, PSR/DSR where applicable.
**Aggregation**: Median across folds (robust to outliers).

---

## 5. Cost Model Discipline — Market-Specific Canonical Costs

**No universal "40 bp round-trip" canonical cost.** The 40 bp figure exists **only as an explicitly labeled conservative STRESS scenario**, not as canonical truth.

### 5.1 Frozen Market-Specific Costs (from Phase 4D)

For BTC/ETH historical reference (and extended to other crypto assets unless asset-specific manifests dictate otherwise):

```
taker_fee     = 0.0005   # 5 bp
half_spread   = 0.00005  # 0.5 bp
slippage      = 0.0001   # 1 bp
plus applicable funding/carry per holding period
```

**Round-trip (open + close) = 2 × (taker + half_spread + slippage) = 13 bp** (not 40 bp).

### 5.2 Cost Model Usage

```python
# Canonical for BTC/ETH (Phase 4D frozen)
CostModel(
    taker_fee=0.0005,
    half_spread=0.00005,
    slippage=0.0001,
)
```

- All backtests **MUST** use the exact frozen cost model for the relevant asset/class.
- No "optimistic" cost assumptions.
- No zero-cost ablation studies for final reporting.
- STRESS scenario (40 bp) may be run additionally and explicitly labeled.

**Do not change production `CostModel` or historical frozen experiments.**

---

## 6. Multi-Asset Portfolio Construction

- **Allocation**: Equal risk budget (1/N volatility-weighted) across active signals
- **Rebalancing**: Daily (24h) or 4h — match signal frequency
- **Risk Limits**: `max_abs_exposure = 1.0` (100% gross), per-asset cap 0.5
- **No leverage**: `max_abs_exposure ≤ 1.0` enforced by `PortfolioEngine`

---

## 7. Documentation & Evidence Standards

Every candidate signal **must** produce:

1. **Research Log Entry** (`docs/cycle_02/research_log/<signal_name>.md`)
   - Hypothesis & rationale
   - Hyperparameter grid searched
   - DEV_TRAIN / OUTER_VAL metrics table (all folds)
   - Code diff link (if new file created)

2. **Reproducible Artifact**
   - Python signal module in `src/obsidian_rl/signals/`
   - Unit test in `tests/signals/test_<name>.py`
   - Backtest script in `tools/backtest_<name>.py` (deterministic, seeded)

3. **Confirmation Report** (only for finalists passing OUTER_VAL)
   - Single PDF/MD with all metrics, equity curve, drawdown chart, trade list
   - `pytest tests/ -q` passing on the exact commit
   - Explicit CONFIRMATION window results (one-time)

---

## 8. Governance & Review Gates

Per repository governance (not Council-only), final research promotion requires:

| Gate | Reviewer(s) | Criteria |
|------|-------------|----------|
| **DEV_TRAIN → OUTER_VAL** | Financial Reviewer | No lookahead, costs correct, metrics computed per spec |
| **OUTER_VAL → CONFIRMATION** | Red Team Reviewer | No holdout peek, single candidate per family, stability ≥2 assets |
| **CONFIRMATION → Paper Trading (Phase 11)** | Office (Financial + Red Team + Release) | All success criteria met, evidence complete, test suite green |

**No bypasses**. Each gate requires explicit sign-off in the research log.
**Council is advisory**, not authorization. The "Council (Chairman + 3 Advisors)" in the original draft is replaced by the existing office/financial/red-team/release governance chain.

---

## 9. Initial Workstream (Week 1-2)

| Workstream | Owner | Deliverable |
|------------|-------|-------------|
| Data Pipeline Audit | Data Engineer | Verified `DataQualityReport` for all candidate assets × timeframes |
| Experimental Windows Preregistration | Lead | `docs/CYCLE_02_EXPERIMENTAL_WINDOWS.md` (governance gap closure) |
| TrendEngine V1+ Grid Search | Quant Researcher | Walk-forward results for horizon sets on DEV_TRAIN |
| Multi-TF Confluence Prototype | Quant Researcher | 4h+1d AND-gate backtest on DEV_TRAIN |
| Vol-Adjusted Trend | Quant Researcher | Inverse-vol scaling backtest on DEV_TRAIN |
| Research Log Template | Lead | `docs/cycle_02/research_log/TEMPLATE.md` |

---

## 10. Risk Controls (Research Phase)

- **No live/paper trading** during research — backtest only.
- **No external data** beyond Binance klines (no alternative data, no on-chain, no sentiment).
- **No ensemble/stacking** until single signals pass OUTER_VAL.
- **Maximum 3 concurrent candidates** in OUTER_VAL to prevent overfitting by selection.
- **Weekly advisory review** — progress, failed candidates logged, scope creep check.

---

## 11. Definition of Done (Research Phase)

Research phase completes when **either**:

1. **Success**: ≥1 candidate passes OUTER_VAL → proceeds to CONFIRMATION (one-time) → if passed, full governance gate to Paper Trading Pilot (Phase 11).
2. **Exhaustion**: All prioritized families explored, no candidate passes OUTER_VAL → document negative results, archive, reassess.

**No "almost passed" promotions.** CONFIRMATION is binary and one-time. FINAL_HOLDOUT remains locked.

---

## 12. Roadmap Integration — Feeds Phases 7–11, Does Not Replace

Strategy Research **feeds** the canonical Cycle 2 roadmap; it does **not** replace Phases 7–11:

```
Phase 7: Auxiliary Funding / Macro Engines
Phase 8: Deterministic Composite (trend + carry + macro + positioning)
Phase 9: Bounded ML Meta-Filter (veto/down-weight only)
Phase 10: n8n Orchestration Layer
Phase 11: Frozen Paper Trading
```

TradingView / Phase 6 remains **frozen infrastructure** (visualization + alert proposal only).

---

## 13. Invariants (Non-Negotiable)

- Paper trading only — no live/Testnet/private order capability
- No synthetic/fabricated data
- No future leakage in features, labels, normalization, or selection
- No holdout peeking (CONFIRMATION and FINAL_HOLDOUT locked)
- No silent window shifting — dates frozen before data access
- Realistic market-specific costs (not universal 40 bp)
- Next-bar/causal execution timing only
- Centralized accounting/state (PortfolioEngine owns all position state)
- RiskEngine remains read-only gate
- Preserve all negative evidence (failed candidates logged)
- No retired Cycle 1 revival (Alpha Gate, 15m PPO, seed ensembles)
- No trading/financial production changes

---

## Appendix A: Cost Model Math Reference

```
Canonical BTC/ETH (Phase 4D frozen):
Per-trade (one way) = taker_fee + half_spread + slippage
                    = 0.0005 + 0.00005 + 0.0001
                    = 0.00065 (6.5 bp)

Round-trip = 13 bp of notional

STRESS scenario (explicitly labeled, not canonical):
taker_fee=0.0010, half_spread=0.0005, slippage=0.0005 → 40 bp round-trip
```

---

## Appendix B: File Layout for New Signals

```
src/obsidian_rl/signals/
├── __init__.py
├── trend_engine_v1.py              # Existing (Phase 4D)
├── trend_engine_v1_extended.py     # New: horizon variations
├── multi_tf_confluence.py          # New: 4h+1d AND gate
├── vol_adjusted_trend.py           # New: inverse-vol scaling
├── cross_asset_momentum.py         # New: BTC lead-lag
├── funding_basis.py                # New: funding rate carry
├── regime_switching.py             # New: HMM regime
└── ml_meta_filter.py               # New: LightGBM meta-filter (Phase 9 contract)

tests/signals/
├── test_trend_engine_v1.py
├── test_trend_engine_v1_extended.py
├── test_multi_tf_confluence.py
...

tools/
├── backtest_trend_extended.py
├── backtest_multi_tf.py
...
```

---

**End of Plan** — Ready for governance review and workstream assignment.