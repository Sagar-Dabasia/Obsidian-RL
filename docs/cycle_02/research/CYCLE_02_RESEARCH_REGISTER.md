# Obsidian-RL Research Register: Cycle 02

## Cycle 01 Hypothesis Retirements & Rejections
In accordance with Obsidian-RL research governance and validation rules (`AGENTS.md`), the following Research Cycle 01 hypotheses have been rigorously evaluated, formally rejected, and are permanently **RETIRED**. They must **not** be silently re-tuned, re-tested with modified parameters, or re-run on identical historical periods:

### 1. Original BTCUSDT 15-Minute PPO Single-Policy Hypothesis (`PpoPolicyStrategy`)
- **Evaluated Experiments**: `PPO_PILOT_01`, `PPO_SEED_STABILITY_01`, `PPO_TURNOVER_SCREEN_01`.
- **Failure Evidence**: Single PPO models trained on 15-minute BTCUSDT candles exhibited severe seed instability, extreme turnover (>200,000 trades/year), high execution fee friction, and negative net returns across outer validation folds.
- **Retirement Status**: **PERMANENTLY RETIRED**. Single-agent 15-minute intraday PPO without multi-engine filtering is discontinued.

### 2. Five-Seed PPO Median Ensemble Hypothesis (`PpoSeedEnsembleStrategy`)
- **Evaluated Experiments**: `PPO_SEED_ENSEMBLE_01`, `PPO_REPLICATION_2020_2022`.
- **Failure Evidence**: While median aggregation reduced turnover across the 2023–2025 screening period, the ensemble failed the one-time development confirmation window (`2025-05-27` to `2025-06-30`) and suffered catastrophic drawdowns (-20.12% mean max drawdown, -11.83% worst fold) during the frozen 2020–2022 historical replication.
- **Retirement Status**: **PERMANENTLY RETIRED**. 15-minute PPO median ensembles are discontinued across all assets.

### 3. Existing Alpha Gate Hypothesis (`AlphaGate` LightGBM Signed Net-Edge Model)
- **Evaluated Experiments**: `ALPHA_GATE_PILOT_01`.
- **Failure Evidence**: The standalone LightGBM regression booster predicting 16-candle signed directional net edge (`signed_directional_net_edge`) failed all 4 outer validation folds (`-21.04%` mean return for gated regime, `-23.44%` mean return for gate direct, drawdowns up to `42.30%`).
- **Retirement Status**: **PERMANENTLY RETIRED**. Standalone intraday 16-candle LightGBM alpha gating is discontinued.

---

## Continuation of the Obsidian-RL Repository
The formal rejection of Cycle 01 hypotheses **does not** close or terminate the Obsidian-RL project. Rather, the empirical findings of Cycle 01 establish that high-turnover single-asset 15-minute cryptocurrency trading is dominated by execution fee drag and noise.

Obsidian-RL now advances to **Research Cycle 02**, deploying an institutional-grade, multi-engine architecture designed from the ground up to overcome the limitations discovered in Cycle 01.

---

## Cycle 02 Core Research Hypothesis
Research Cycle 02 tests a **materially different scientific hypothesis**:

> **"A cross-asset, multi-engine quantitative platform operating on slower institutional timeframes and integrating diverse economic/market information layers achieves superior risk-adjusted returns, lower turnover friction, and robust out-of-sample stability compared to single-asset intraday reinforcement learning."**

### Five Pillars of the Cycle 02 Hypothesis
1. **Multiple Markets**: Expansion from single-asset Bitcoin (`BTCUSDT`) to multi-asset cryptocurrency (`ETHUSDT`, major altcoins) and institutional foreign exchange (`EUR_USD`, `USD_JPY`, `GBP_USD`), with architecture supporting equities and commodities.
2. **Slower Timeframes**: Shift from noisy 15-minute (`15m`) bars to institutional trend and structural intervals (`1H`, `4H`, `1D`), drastically increasing signal-to-noise ratios and capturing multi-day macro trends.
3. **Economic & Market Information Integration**: Direct quantitative incorporation of auxiliary fundamental drivers—including macroeconomic surprises (`MacroEconomicEventEngine`), perpetual funding/carry yields (`CryptoFundingCarryEngine`), structured news sentiment (`NewsSentimentEngine`), and market positioning (`MarketPositioningEngine`).
4. **Lower Turnover**: Explicit structural design aimed at low-frequency portfolio rebalancing (`mean_turnover < 50 trades/year per asset`), transforming execution fee friction from a dominant loss driver into a negligible operational cost.
5. **Portfolio Diversification**: Capital allocation across imperfectly correlated asset classes and currencies (`PortfolioCombinationEngine`), smoothing portfolio equity curves and reducing maximum drawdowns (`max_drawdown <= 15%`).

---

## Cycle 02 Experimental & Holdout Policies
To preserve absolute scientific integrity and prevent data dredging across cross-asset datasets, Research Cycle 02 enforces a strict protocol for defining, selecting, and freezing data periods.

### 1. Data Window Selection & Freezing Process (No Dates Selected Yet)
- **Selection Rule**: Specific historical calendar dates for Cycle 02 Development, Validation, Confirmation, and Final Holdout windows are **not selected yet**.
- **Pre-Inspection Freezing Requirement**: Before any historical bar or event data is downloaded, inspected, or plotted for Phase 4 trend baselines or Phase 8 composite backtests, the exact UTC start and end timestamps for all four windows must be formally defined, documented, and frozen in `docs/CYCLE_02_EXPERIMENTAL_WINDOWS.md` and committed to version control.
- **Prohibition on Retroactive Shifting**: Once frozen, experimental window boundaries cannot be shifted or adjusted under any circumstances.

### 2. Four-Tier Data Window Governance Policy
1. **Development & Training Window (`DEV_TRAIN`)**:
   - **Purpose**: Used for initial quantitative engine design, technical indicator formula validation, and Phase 9 ML meta-filter cross-validation (`train_gate`).
   - **Access**: Open read/write access during engine development phases (Phases 4 through 9).
2. **Outer Validation Window (`OUTER_VAL`)**:
   - **Purpose**: Used exclusively for evaluating out-of-sample performance across chronological walk-forward folds (`make_folds`).
   - **Access**: Strictly isolated during model training and feature weighting. Used only once per completed engine phase to evaluate pass/fail criteria.
3. **One-Time Confirmation Window (`CONFIRMATION`)**:
   - **Purpose**: A reserved historical buffer used for one-time verification of a finalized, fully assembled composite system (`Phase 8/9`) prior to paper trading cutover (`Phase 11`).
   - **Access**: Stored in isolated partitions (`store.read`). Must **never** be loaded, queried, or evaluated unless all outer validation criteria have been successfully passed across all folds.
4. **Final Reserved Holdout Window (`FINAL_HOLDOUT`)**:
   - **Purpose**: The ultimate out-of-sample repository benchmark across all research cycles.
   - **Access**: **STRICTLY LOCKED AND UNTOUCHED**. No script, tool, backtest, or analysis may load or inspect `FINAL_HOLDOUT` data during Research Cycle 02 development, phase screening, or paper trading.

---

## Research Cycle 02 Governance Checklist
- [x] Canonical Cross-Asset Contracts (`MarketBar`, `EventNewsItem`) finalized and tested (`Phase 1`).
- [ ] Experimental window boundaries (`DEV_TRAIN`, `OUTER_VAL`, `CONFIRMATION`, `FINAL_HOLDOUT`) formally frozen before data download (`Phase 3`).
- [x] Cycle 01 hypotheses verified as retired and excluded from active strategy loops.
- [ ] Multi-engine composite evaluated under strict walk-forward isolation (`Phase 8`).
- [x] Zero access to `FINAL_HOLDOUT` verified across all audit logs.

---

## Phase 4C Final Status
**Classification**: `EXPERIMENT INVALID — UNVERIFIED FOREX DATA GAPS`
Phase 4C is officially closed and cannot be rerun using the current unverifiable Forex data constraints. The experiment was blocked by missing OANDA market data which lacked valid cryptographic proofs of API absence.

## Phase 4D Final Status
**Status**: `INVALID — SPOT/PERPETUAL MARKET-MODEL MISMATCH — NO STRATEGY CONCLUSION`
* Constraints: Erratum logged. Any future perpetual experiment must be a NEW preregistered experiment.
* Diagnostic Report: [PHASE_04D_CRYPTO_TREND_ROBUSTNESS.md](../reports/PHASE_04D_CRYPTO_TREND_ROBUSTNESS.md)
* Erratum Report: [PHASE_04D_POST_PUSH_EVALUATION_ERRATUM.md](../reports/PHASE_04D_POST_PUSH_EVALUATION_ERRATUM.md)

Confirmation and final holdout data remained completely untouched.
The next task must require a genuinely new hypothesis before modifying or rerunning the strategy.

## Cycle 02 Roadmap & Planned Scope

* 4D INVALID closeout
* → 4E Statistical Validity Gate
* → 4F Execution/Accounting Parity Audit
* → remaining Cycle 2 engines/composite
* → possible genuinely-new RL re-entry
* → controlled paper trading

### 4E planned scope:
* PSR
* DSR
* explicit trial/multiple-testing accounting
* PBO only if mathematically valid
* CPCV/purging only if chronology/holdout isolation is preserved
* references only: `purged-cross-validation`, `jsharpe`, `pypbo`
* no dependency additions yet

### 4F planned scope:
* NautilusTrader as execution/accounting reference
* compare timing/fills/costs/order-state/accounting
* never replace centralized Obsidian state/accounting
* `hftbacktest` deferred

### Future reference only:
* FinRL-X
* TradeMaster
* TorchTrade

**RL remains retired unless a genuinely new hypothesis passes a re-entry gate.**
Possible later candidates:
* SB3-Contrib RecurrentPPO
* d3rlpy
* Minari conventions

**Optuna:**
* train/inner-eval only
* never outer/confirmation/final holdout

**Deferred:**
* DVC
* CCXT
* Soup
* public-apis
