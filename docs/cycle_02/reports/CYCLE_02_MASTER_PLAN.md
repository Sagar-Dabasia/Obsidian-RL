# Obsidian-RL Research Cycle 02: Master Implementation Plan

## Executive Summary & Scope
Research Cycle 02 transitions Obsidian-RL from a single-asset, high-turnover intraday reinforcement learning repository into a institutional-grade **Cross-Asset Multi-Engine Platform**. 

The scope supports:
1. **Cryptocurrency** (primary focus on major liquid pairs, e.g., BTC/USDT, ETH/USDT).
2. **Foreign Exchange (Forex)** (major fiat pairs via institutional providers, e.g., EUR/USD, USD/JPY, GBP/USD).
3. **Future Extension Architecture** to natively support equities (stocks), market indices, and commodities without refactoring core accounting, risk, or data contracts.

This plan enforces strict segregation between quantitative calculation (owned by Python/Obsidian-RL), visual display/charting (owned by TradingView), and scheduling/workflow coordination (owned by n8n).

---

## Fixed Implementation Order (Phases 1 through 12)

### Phase 1: Canonical Cross-Asset Data Contracts
- **Objective**: Establish immutable, standardized data contracts for multi-asset market bars and economic/news events that prevent look-ahead bias and enforce strict schema versioning across all execution layers.
- **Files / Modules**:
  - `src/obsidian_rl/data/contracts.py` (canonical schemas: `MarketBar`, `EventNewsItem`)
  - `src/obsidian_rl/data/fingerprint.py` (hashing and immutability utilities)
- **Dependencies**: Python standard library (`typing`, `dataclasses`, `hashlib`), `numpy`, `pandas`.
- **Tests**:
  - `tests/data/test_contracts.py` (verifies exact field enforcement, `observed_at_utc` vs `timestamp_utc` ordering, and deterministic `row_hash`/`raw_content_hash` computation).
- **Security Risks**: Malformed or maliciously injected data rows that attempt to alter historical timestamps or inject non-finite values into downstream risk engines.
- **Pass / Fail Rules**:
  - **Pass**: All required schema fields are enforced; attempts to instantiate contracts with future `observed_at_utc` relative to current wall-clock fail fast; schema hashing is 100% deterministic across platforms.
  - **Fail**: Any missing field, silent type coercion, or mutable timestamp allowed after construction.
- **Estimated Duration**: 1 week.
- **Outputs Required Before Continuing**: Validated schema module `contracts.py`, fully passing unit tests, and frozen `SCHEMA_VERSION_V2` documentation.

---

### Phase 2: Forex and Crypto Provider Adapters
- **Objective**: Implement robust, fault-tolerant ingestion adapters for institutional Forex data (OANDA) and public Cryptocurrency market data (exchange APIs) mapping directly to Phase 1 canonical contracts.
- **Files / Modules**:
  - `src/obsidian_rl/data/adapters/base.py` (`ProviderAdapter` abstract base class)
  - `src/obsidian_rl/data/adapters/oanda.py` (OANDA Practice and Historical API adapter)
  - `src/obsidian_rl/data/adapters/crypto_exchange.py` (Crypto REST/WebSocket adapter)
  - `src/obsidian_rl/data/adapters/research_fallback.py` (Public research-only fallback, e.g., Yahoo Finance)
- **Dependencies**: Phase 1 (`contracts.py`), `requests`, `aiohttp`, `pydantic`/`tenacity` for rate limiting and backoff.
- **Tests**:
  - `tests/data/adapters/test_oanda_adapter.py` (mocked OANDA responses and pagination handling)
  - `tests/data/adapters/test_crypto_adapter.py` (mocked exchange order books, funding rates, and trades)
  - `tests/data/adapters/test_fallback_isolation.py` (verifies fallback adapter cannot be selected when execution mode is live or paper)
- **Security Risks**: Exposure of API tokens/secrets via logging or stack traces; unauthenticated rate-limit exhaustion causing denial-of-service.
- **Pass / Fail Rules**:
  - **Pass**: All incoming data mapped exactly to canonical `MarketBar` with verified rate-limit backoff, proper fallback isolation, and zero secret leakage.
  - **Fail**: Any unhandled network exception causing state corruption, missing rate-limit handling, or leakage of API credentials in error messages.
- **Estimated Duration**: 2 weeks.
- **Outputs Required Before Continuing**: Functional OANDA and Crypto adapters, integration test harnesses, and documented data-provider rate limit profiles.

---

### Phase 3: Storage and Data-Quality Validation
- **Objective**: Construct partitioned, checksummed local persistence and comprehensive data-quality inspection pipelines to guarantee historical integrity before backtesting or live ingestion.
- **Files / Modules**:
  - `src/obsidian_rl/data/storage/partitioned_store.py` (Parquet/Arrow partitioned data store by asset/timeframe/month)
  - `src/obsidian_rl/data/validation/quality_check.py` (gap detection, duplicate detection, OHLCV integrity, timestamp monotonic checks)
- **Dependencies**: Phase 1 (`contracts.py`), Phase 2 (`adapters`), `pyarrow`, `pandas`.
- **Tests**:
  - `tests/data/storage/test_partitioned_store.py` (verifies read/write parity, directory structure, and hash verification upon load)
  - `tests/data/validation/test_quality_check.py` (injects artificial gaps, duplicates, zero volume, negative prices, and verifies explicit rejection)
- **Security Risks**: Path traversal vulnerabilities during file writing/reading (`../../` attack vectors); disk exhaustion from uncontrolled data writing.
- **Pass / Fail Rules**:
  - **Pass**: Storage layer rejects any row not passing `QualityReport` validation; exact zero duplicates; explicit accounting of every missing bar or trading halt.
  - **Fail**: Silent acceptance of duplicate timestamps, missing intervals without marking gaps, or unvalidated file paths.
- **Estimated Duration**: 2 weeks.
- **Outputs Required Before Continuing**: Partitioned data store supporting multi-asset schemas, quality validation CLI (`obsidian_rl data-validate`), and clean benchmark datasets.

---

### Phase 4: Multi-Asset Trend Baseline
- **Objective**: Build the foundational Market Trend Engine across cryptocurrency and forex using slower, high-stability timeframes (1H, 4H, 1D) to establish baseline cross-asset momentum behavior.
- **Files / Modules**:
  - `src/obsidian_rl/engines/trend.py` (`MarketTrendEngine` calculation logic)
  - `src/obsidian_rl/strategies/trend_baseline.py` (multi-asset momentum strategy implementations: regime SMA ratio, Donchian breakout)
- **Dependencies**: Phase 1, Phase 3, `numpy`, `pandas`.
- **Tests**:
  - `tests/engines/test_trend_engine.py` (verifies exact mathematical output against synthetic multi-asset price series across multiple timeframes)
  - `tests/strategies/test_trend_baseline.py` (verifies signal generation rules, direction constraints, and zero look-ahead bias across boundary updates)
- **Security Risks**: Floating-point overflow/underflow or division-by-zero during high-volatility price shocks.
- **Pass / Fail Rules**:
  - **Pass**: Deterministic calculation of multi-timeframe trend scores across all configured assets; zero look-ahead bias across historical folds; finite metrics across all evaluation windows.
  - **Fail**: Any non-finite value output, inconsistent signal generation across identical historical slices, or execution logic coupled to chart plotting.
- **Estimated Duration**: 2 weeks.
- **Outputs Required Before Continuing**: Functional `MarketTrendEngine`, verified multi-asset baseline evaluation reports across development data, and finalized trend indicator specifications.

---

### Phase 5: Portfolio and Risk Engine
- **Objective**: Implement centralized multi-asset portfolio accounting, exposure aggregation, position sizing based on volatility targets, and strict deterministic risk controls.
- **Files / Modules**:
  - `src/obsidian_rl/engines/portfolio.py` (`PortfolioCombinationEngine`, cross-asset capital allocation, correlation weighting)
  - `src/obsidian_rl/engines/risk.py` (`RiskEngine`, hard drawdown limits, leverage caps, venue concentration limits, default-deny gating)
- **Dependencies**: Phase 1, Phase 4, `numpy`.
- **Tests**:
  - `tests/engines/test_portfolio_engine.py` (verifies capital allocation parity across multi-currency assets and net/gross exposure accounting)
  - `tests/engines/test_risk_engine.py` (tests hard stop enforcement, leverage limit rejections, max position limits, and default-deny state on missing data)
- **Security Risks**: Bypass of risk checks via corrupted target inputs; race conditions between position accounting and order proposal.
- **Pass / Fail Rules**:
  - **Pass**: `RiskEngine` intercepts and vetoes any proposal exceeding predefined drawdown (`max_drawdown_limit`), leverage (`max_leverage`), or concentration limits; default-deny triggered if market freshness checks fail (`observed_at_utc` too old).
  - **Fail**: Any order proposal passing to execution that violates risk constraints or executes when risk parameters are uninitialized.
- **Estimated Duration**: 2 weeks.
- **Outputs Required Before Continuing**: Fully unit-tested `PortfolioCombinationEngine` and `RiskEngine`, risk audit log schema, and verified safety interlocks.

---

### Phase 6: TradingView Pine Signal Layer
- **Objective**: Construct visual representation and alert generation layers in TradingView Pine Script aligned strictly with Python engine calculations, utilizing JSON webhooks to transmit visual alerts.
- **Files / Modules**:
  - `pine/ObsidianMultiAssetTrend.pine` (TradingView Pine Script for charting and visual signals)
  - `src/obsidian_rl/interop/webhook_receiver.py` (FastAPI/AIOHTTP webhook endpoint validating and parsing incoming TradingView JSON alerts)
- **Dependencies**: Phase 1 (`contracts.py`), Phase 5 (`risk.py`), `pydantic`, HMAC signing/validation.
- **Tests**:
  - `tests/interop/test_webhook_receiver.py` (tests HMAC signature verification, timestamp replay protection, malformed JSON handling, and payload parsing)
  - `tests/interop/test_pine_parity.py` (verifies Pine Script mathematical parity against Python engine outputs over identical candle sequences)
- **Security Risks**: Unauthenticated or spoofed webhook requests attempting to inject unauthorized trading signals; replay attacks using captured valid payloads.
- **Pass / Fail Rules**:
  - **Pass**: Webhook endpoint requires valid HMAC signature and nonce/event ID; rejected requests logged immediately; TradingView signals treated strictly as informational proposals subject to Python `RiskEngine` verification.
  - **Fail**: Acceptance of unsigned webhooks, acceptance of expired timestamps (>60 seconds skew), or TradingView signals bypassing internal calculation verification.
- **Estimated Duration**: 1.5 weeks.
- **Outputs Required Before Continuing**: Verified Pine Script files, secure webhook receiver service with replay protection, and end-to-end signal transmission logs.

---

### Phase 7: Funding and Macro-Information Engines
- **Objective**: Implement specialized analytical engines for Crypto funding rates/carry and Macroeconomic events/news sentiment, converting external asynchronous events into deterministic numerical scores.
- **Files / Modules**:
  - `src/obsidian_rl/engines/funding_carry.py` (`CryptoFundingCarryEngine`, annualized carry yield calculation, funding arbitrage score)
  - `src/obsidian_rl/engines/macro_event.py` (`MacroEconomicEventEngine`, economic calendar tracking, surprise score calculation)
  - `src/obsidian_rl/engines/news_sentiment.py` (`NewsSentimentEngine`, ingestion of structured LLM/provider news scores)
  - `src/obsidian_rl/engines/positioning.py` (`MarketPositioningEngine`, open interest, long/short ratio aggregation)
- **Dependencies**: Phase 1 (`contracts.py`), Phase 2 (`adapters`), `numpy`, `pandas`.
- **Tests**:
  - `tests/engines/test_funding_carry.py` (tests carry yield math across positive/negative funding regimes and historical fee deduction)
  - `tests/engines/test_macro_event.py` (tests surprise score calculation `(actual - expected) / std` and revision handling)
  - `tests/engines/test_news_sentiment.py` (tests freshness decay, source reliability weighting, and bounding between -1.0 and +1.0)
- **Security Risks**: Injection of malformed text or extreme numerical outliers from news APIs attempting to skew sentiment scores.
- **Pass / Fail Rules**:
  - **Pass**: All auxiliary engine outputs bounded to exact deterministic ranges (`[-1.0, +1.0]` for sentiment/surprise); zero reliance on unverified raw text during execution; strict point-in-time timestamp enforcement using `first_observed_at`.
  - **Fail**: Unbounded numerical outputs, crash upon missing macroeconomic releases, or look-ahead bias from revised economic figures.
- **Estimated Duration**: 2.5 weeks.
- **Outputs Required Before Continuing**: Functional funding, macro, news, and positioning engines with historical test suites and verified canonical event contracts.

---

### Phase 8: Combined Rule-Based System
- **Objective**: Integrate all quantitative engines into a cohesive deterministic strategy across multiple asset classes, blending trend, carry, macro, and positioning scores under strict portfolio risk rules.
- **Files / Modules**:
  - `src/obsidian_rl/strategies/multi_engine_composite.py` (`MultiEngineCompositeStrategy` combining scores with transparent rule weights)
  - `src/obsidian_rl/evaluation/cross_asset_runner.py` (multi-asset walk-forward backtest and simulation harness)
- **Dependencies**: Phase 4 (`trend.py`), Phase 5 (`portfolio.py`, `risk.py`), Phase 7 (`auxiliary engines`), `numpy`, `pandas`.
- **Tests**:
  - `tests/strategies/test_multi_engine_composite.py` (verifies component weighting, deterministic blending, and zero allocation during conflicting regimes)
  - `tests/evaluation/test_cross_asset_runner.py` (tests multi-asset portfolio accounting, execution cost deduction across Forex/Crypto, and exact walk-forward fold boundaries)
- **Security Risks**: Memory exhaustion during multi-asset multi-year backtests across high-frequency interval arrays.
- **Pass / Fail Rules**:
  - **Pass**: Seamless execution of multi-engine strategy across full historical development data; all execution costs (spread, taker/maker fees, carry fees) deducted accurately; 100% deterministic output across runs.
  - **Fail**: Inconsistent backtest results on repeated runs, failure to account for funding fees during holding periods, or risk engine bypass.
- **Estimated Duration**: 2 weeks.
- **Outputs Required Before Continuing**: Complete rule-based composite system, multi-asset walk-forward performance reports on development data, and baseline multi-engine benchmarks.

---

### Phase 9: Small ML Meta-Filter
- **Objective**: Introduce a lightweight, strictly bounded Machine Learning meta-filter (e.g., LightGBM regression/classification booster) trained solely to filter or size composite rule-based signals based on multi-engine feature state without replacing core deterministic direction.
- **Files / Modules**:
  - `src/obsidian_rl/engines/meta_filter.py` (`MlMetaFilterEngine`, training, inference, and feature attribution)
  - `src/obsidian_rl/strategies/filtered_composite.py` (`FilteredCompositeStrategy` wrapping `MultiEngineCompositeStrategy` with meta-filter gating)
- **Dependencies**: Phase 8 (`composite system`), `lightgbm`, `numpy`, `pandas`.
- **Tests**:
  - `tests/engines/test_meta_filter.py` (verifies time-aware purged cross-validation, booster text serialization, and non-finite prediction handling)
  - `tests/strategies/test_filtered_composite.py` (verifies that meta-filter can only down-weight or veto signals, never invert or bypass deterministic risk limits)
- **Security Risks**: Overfitting to development data leading to out-of-sample brittleness; loading of unverified pickle/joblib files instead of raw text boosters.
- **Pass / Fail Rules**:
  - **Pass**: Meta-filter uses strictly text-format boosters (`model.txt` + `meta.json`); only acts as a dampener or gate (`multiplier in [0.0, 1.0]`); passes strict cross-asset out-of-sample walk-forward checks.
  - **Fail**: Use of pickle/joblib, meta-filter generating new directional positions outside rule-based proposals, or non-finite inference outputs.
- **Estimated Duration**: 2 weeks.
- **Outputs Required Before Continuing**: Trained and verified `MlMetaFilterEngine` artifacts, cross-asset comparative evaluation reports, and validated meta-filter governance rules.

---

### Phase 10: n8n Orchestration Layer
- **Objective**: Deploy external orchestration workflows using n8n to handle scheduled data ingestion triggers, API health monitoring, automated daily reporting, and human-in-the-loop approval requests.
- **Files / Modules**:
  - `n8n/workflows/daily_ingestion_schedule.json` (n8n workflow definition for automated cron scheduling)
  - `n8n/workflows/system_audit_report.json` (n8n workflow for daily performance/audit summary generation)
  - `n8n/workflows/human_approval_gate.json` (n8n workflow handling manual intervention requests and notification dispatch)
  - `src/obsidian_rl/interop/n8n_client.py` (Python client for dispatching status notifications and receiving orchestration commands)
- **Dependencies**: Phase 6 (`webhook_receiver.py`), Phase 8/9 (`strategies`), secure REST APIs.
- **Tests**:
  - `tests/interop/test_n8n_client.py` (mocks n8n webhook triggers and status callbacks, verifying auth token inclusion and idempotent handling)
- **Security Risks**: Unauthenticated n8n endpoints allowing external attackers to trigger workflow loops or access sensitive reporting summaries.
- **Pass / Fail Rules**:
  - **Pass**: All n8n workflows authenticate using mutual API headers/HMAC; n8n restricted strictly to scheduling, notification, and workflow gating; zero trading calculations performed inside n8n nodes.
  - **Fail**: n8n workflows directly calling exchange order APIs or storing persistent API secrets inside workflow JSON definitions.
- **Estimated Duration**: 1.5 weeks.
- **Outputs Required Before Continuing**: Verified n8n workflow definitions, integrated health-check monitoring dashboards, and tested human-in-the-loop alert protocols.

---

### Phase 11: Frozen Paper Trading
- **Objective**: Execute live real-time paper trading across configured Forex and Crypto venues using the frozen Phase 8/9 system, validating end-to-end multi-engine behavior, order state management, and execution latency without financial risk.
- **Files / Modules**:
  - `src/obsidian_rl/engines/paper_execution.py` (`PaperExecutionEngine`, realistic order book simulation, slippage modeling, fill latency accounting)
  - `src/obsidian_rl/engines/monitoring_audit.py` (`MonitoringAuditEngine`, real-time state persistence, audit trail logging, state snapshotting)
- **Dependencies**: All prior phases (`adapters`, `engines`, `strategies`, `interop`).
- **Tests**:
  - `tests/engines/test_paper_execution.py` (verifies order lifecycle: `PROPOSED` -> `APPROVED_BY_RISK` -> `SUBMITTED` -> `FILLED`/`CANCELLED`, and realistic spread/slippage applied to fills)
  - `tests/engines/test_monitoring_audit.py` (verifies immutable append-only audit logs and exact reconstruction of portfolio state from snapshot logs)
- **Security Risks**: Accidental connection to live real-money execution endpoints due to misconfigured venue parameters or missing paper-mode guardrails.
- **Pass / Fail Rules**:
  - **Pass**: `PaperExecutionEngine` enforces `execution_mode == 'PAPER'`; hard check raises `RuntimeError` if real-money exchange URLs are supplied; complete immutable audit history recorded for every tick and decision.
  - **Fail**: Any order routed to live production endpoints, missing audit records, or discrepancies between simulated equity and fill accounting.
- **Estimated Duration**: 3 weeks (including minimum 2-week live observation window).
- **Outputs Required Before Continuing**: Minimum 14-day continuous paper trading audit log, live vs. backtest slippage/fill analysis report, and verified system stability sign-off.

---

### Phase 12: Controlled Real-Money Consideration
- **Objective**: Establish strict formal criteria, governance checklists, and multi-signature authorization requirements before any consideration of deploying the verified system to real-money capital.
- **Files / Modules**:
  - `docs/REAL_MONEY_GOVERNANCE_CHECKLIST.md` (formal audit checklist and authorization procedure)
  - `src/obsidian_rl/engines/live_execution_guard.py` (`LiveExecutionGuard`, multi-layer interlock requiring explicit cryptographic/environment authorization before live order routing)
- **Dependencies**: Phase 11 (`paper trading sign-off`).
- **Tests**:
  - `tests/engines/test_live_guard.py` (verifies that live execution remains locked (`default-deny`) unless all environmental, configuration, and explicit sign-off tokens are perfectly verified)
- **Security Risks**: Unauthorized activation of real-money trading, excessive capital allocation during initial cutover, or missing circuit breakers during live flash crashes.
- **Pass / Fail Rules**:
  - **Pass**: Live execution unlocked only when explicit formal approval is documented, all Phase 11 paper benchmarks are satisfied, and strict hard-coded capital limits (`max_initial_capital`) are enforced by `LiveExecutionGuard`.
  - **Fail**: Any bypass of the formal review process, deployment without verified circuit breakers, or activation of live execution during unverified market conditions.
- **Estimated Duration**: 1 week (process and verification setup).
- **Outputs Required Before Continuing**: Completed `REAL_MONEY_GOVERNANCE_CHECKLIST.md`, executive review sign-off, and verified live execution guardrail documentation.

---

## Estimated Total Duration
- **Phases 1 to 3 (Data Infrastructure & Quality)**: 5 weeks
- **Phases 4 to 5 (Core Trend & Risk Engines)**: 4 weeks
- **Phases 6 to 7 (Interop & Auxiliary Engines)**: 4 weeks
- **Phases 8 to 9 (Composite Strategy & Meta-Filter)**: 4 weeks
- **Phases 10 to 12 (Orchestration, Paper Execution & Governance)**: 5.5 weeks
- **Total Estimated Timeline**: **22.5 weeks** (approx. 5.5 months of systematic, bounded, test-driven engineering and validation).
