# Graph Report - D:\Obsidian-RL-graphify  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1988 nodes · 5282 edges · 94 communities (74 shown, 20 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 359 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c6f4e5cf`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- make_candles
- Timeframe
- costs.py
- Ledger
- test_promotion.py
- cli.py
- PpoSeedEnsembleStrategy
- PortfolioObs
- SQLiteStorage
- contracts.py
- promotion.py
- CostModel
- test_outages.py
- storage.py
- signed_directional_net_edge
- TrendConfig
- Settings
- test_contracts.py
- holdout.py
- stub_gate
- test_alpha_gate.py
- test_provider_smoke.py
- ingest_provider_market_data
- test_packaging.py
- RewardConfig
- validate_market_bars
- test_dashboard_queries.py
- schema_fingerprint
- test_holdout.py
- calculate_trend_signal
- test_ledger.py
- MarketBar
- test_portfolio_engine.py
- PortfolioConfig
- test_training.py
- trend_backtest.py
- test_binance_client.py
- save_gate
- load_record
- extract_continuous_features
- run_live_trader
- QLearningAgent
- download.py
- DataFetchError
- CandleStore
- ppo.py
- data/schema.py
- validation.py
- registry.py
- RealMarketEnv
- SyntheticMarketEnv
- _load_champion_data
- trend.py
- test_oanda.py
- test_vision_bulk.py
- train_and_save_alpha_gate
- test_costs.py
- parse_trades_log
- evaluate_agent
- .fetch_klines
- test_binance.py
- Path
- parse_kline_event
- run_migrations
- test_manifest_provenance.py
- test_alpha_gate_pilot.py
- test_secret_hygiene.py
- .from_dir
- PromotionThresholds
- test_repo_foundation.py
- main
- manifest.py
- models_with_two_candidates
- _parse_args
- _validation_data_sha256
- verify_binance_outage.py
- agent.py
- dashboard/__init__.py
- env/__init__.py
- features/__init__.py
- gate/__init__.py
- ledger/__init__.py
- live/__init__.py
- portfolio/__init__.py
- signals/__init__.py
- .identity
- strategies/__init__.py
- training/__init__.py
- tests/data/__init__.py
- tests/__init__.py
- parametrize
- tools/__init__.py
- obsidian-rl

## God Nodes (most connected - your core abstractions)
1. `CostModel` - 111 edges
2. `make_candles()` - 107 edges
3. `Ledger` - 69 edges
4. `MarketBar` - 59 edges
5. `PortfolioConfig` - 52 edges
6. `PortfolioObs` - 51 edges
7. `SQLiteStorage` - 51 edges
8. `evaluate_candidate()` - 47 edges
9. `PaperTrader` - 45 edges
10. `PortfolioEngine` - 44 edges

## Surprising Connections (you probably didn't know these)
- `test_cli_parser_turnover_penalty_bps()` --calls--> `build_parser()`  [INFERRED]
  tests/test_training.py → src/obsidian_rl/cli.py
- `test_schema_fingerprint_stable()` --calls--> `schema_fingerprint()`  [INFERRED]
  tests/test_observation_parity.py → src/obsidian_rl/features/schema.py
- `test_normal_forex_weekends_pass()` --calls--> `is_forex_weekend_gap()`  [INFERRED]
  tests/data/test_outages.py → src/obsidian_rl/data/quality.py
- `BoolTargetStrategy` --uses--> `Settings`  [INFERRED]
  tests/test_live_accounting.py → src/obsidian_rl/config.py
- `FaultyStrategy` --uses--> `Settings`  [INFERRED]
  tests/test_live_accounting.py → src/obsidian_rl/config.py

## Import Cycles
- None detected.

## Communities (94 total, 20 thin omitted)

### Community 0 - "make_candles"
Cohesion: 0.05
Nodes (85): CandleValidationError, feature_matrix(), DataFrame, ndarray, ValueError, Return (open_time_ms, features) for all rows past warm-up, as float32. Raises…, Raised when a candle DataFrame does not satisfy the schema contract., Validate a candle DataFrame against the schema contract. Raises… (+77 more)

### Community 1 - "Timeframe"
Cohesion: 0.06
Nodes (55): AssetClass, Strict string enum of supported institutional asset classes., Reconstruct MarketBar from dict, enforcing exact boundaries and tamper check., Strict string enum of supported market bar intervals., Timeframe, _get_provider(), _get_venue(), Historical dataset builder. Supports downloading and validating large bounded… (+47 more)

### Community 2 - "costs.py"
Cohesion: 0.05
Nodes (51): Protocol, DataFrame, Standards-compliant Gymnasium trading environment. Uses the centralized feature…, BacktestResult, PortfolioFeatureTracker, DataFrame, Shared backtest runner: the single decision/execution loop for baselines and…, Run one chronological pass. `candles` must be a validated canonical frame.… (+43 more)

### Community 3 - "Ledger"
Cohesion: 0.06
Nodes (36): Row, DuplicateClosureError, DuplicateDecisionError, EventConflictError, Ledger, Any, Path, RuntimeError (+28 more)

### Community 4 - "test_promotion.py"
Cohesion: 0.13
Nodes (66): evaluate_candidate(), _latest_pointer_path(), promote(), Compare candidate vs champion vs baselines on a predefined validation slice., Explicitly promote a validated candidate to champion; retire the old champion., GitSourceState, evidence_models(), _get_latest_report_path() (+58 more)

### Community 5 - "cli.py"
Cohesion: 0.07
Nodes (51): ArgumentParser, build_parser(), cmd_candidate_eval(), cmd_data_download(), cmd_data_summary(), cmd_data_update(), cmd_data_validate(), cmd_gpu_check() (+43 more)

### Community 6 - "PpoSeedEnsembleStrategy"
Cohesion: 0.08
Nodes (33): PpoPolicyStrategy, Any, _dummy_market_row(), _dummy_portfolio(), _make_fake_member(), ndarray, Tests for PpoSeedEnsembleStrategy: median aggregation, reset, validation, non-…, Confirmation data must NOT be loaded unless a penalty qualifies. (+25 more)

### Community 7 - "PortfolioObs"
Cohesion: 0.06
Nodes (38): build_observation(), PortfolioObs, ndarray, Portfolio-state inputs to the observation (all scale-free). All fields must be…, Raise ValueError if any PortfolioObs field is invalid. Checks: - numeric, not…, Assemble the versioned observation vector (float32, OBSERVATION_DIM). Returns a…, validate_portfolio_obs(), feature() (+30 more)

### Community 8 - "SQLiteStorage"
Cohesion: 0.05
Nodes (47): ingest_historical_range(), Ingest a historical range chunk by chunk into SQLite., Any, Transactional, point-in-time SQLite storage engine for cross-asset market data., Close the underlying SQLite connection., Store or replace a dataset manifest record., Retrieve a stored dataset manifest by dataset_id., Record an ingestion run entry. (+39 more)

### Community 9 - "contracts.py"
Cohesion: 0.07
Nodes (45): EventNewsItem, from_dict(), Any, Canonical data contracts (`MarketBar`, `EventNewsItem`) for Cycle 02 cross-…, Canonical economic event and news item data contract. Enforces strict enums,…, Serialize EventNewsItem to dictionary with stable enum string values., Validate data receipt timestamp is deterministic and within allowed clock skew.…, Serialize a MarketBar or EventNewsItem contract to a JSON-compatible dictionary. (+37 more)

### Community 10 - "promotion.py"
Cohesion: 0.12
Nodes (44): _champion_lock(), _champion_path(), _check_training_provenance(), _evaluation_lock(), evaluation_report_path(), _evaluations_dir(), get_verified_champion_info(), _load_and_verify_latest_pointer() (+36 more)

### Community 11 - "CostModel"
Cohesion: 0.12
Nodes (32): PaperTrader, Terminal liquidation at the given mark and run closure (explicit, logged)., Owns one run's decision loop. Portfolio state lives ONLY in the engine + ledger., CostModel, Fractions of traded notional. Defaults are pessimistic for BTCUSDT USD-M perp., Total cost fraction for entering and exiting the same notional., AlwaysFlat, BoolTargetStrategy (+24 more)

### Community 12 - "test_outages.py"
Cohesion: 0.07
Nodes (30): default_registry(), OutageRegistry, Deterministic venue-outage registry. Records confirmed, independently verified…, Check if the entire gap is covered by a known outage. The gap [gap_start_ms,…, Check if the outage at timestamp is venue-wide., Return the default outage registry with all pre-registered entries., A single confirmed venue outage interval., Deterministic hash of this outage entry. (+22 more)

### Community 13 - "storage.py"
Cohesion: 0.11
Nodes (33): EventType, QuoteStatus, Strict string enum representing bid/ask quote availability., Strict string enum representing volume reporting mode., Reconstruct EventNewsItem from dict, enforcing boundaries and tamper check., Strict string enum of economic and market news event types., Strict string enum representing economic release revision states., RevisionStatus (+25 more)

### Community 14 - "signed_directional_net_edge"
Cohesion: 0.08
Nodes (38): forward_executable_net_return(), forward_log_return(), Series, Forward labels for supervised models (Alpha Gate). The label at row t uses ONLY…, log(close[t+horizon] / close[t]). NaN for the last `horizon` rows. Kept for…, LEGACY long-only label: log(open[t+1+h] / open[t+1]) - cost. Kept for…, Signed executable directional edge. For a decision made after candle t closes:…, signed_directional_net_edge() (+30 more)

### Community 15 - "TrendConfig"
Cohesion: 0.13
Nodes (33): OutageRegistry, Run backtests for strategy, flat baseline, and long baseline., run_trend_backtest(), Configuration for Trend Engine V1., TrendConfig, make_bar(), make_custom_bar(), AssetClass (+25 more)

### Community 16 - "Settings"
Cohesion: 0.11
Nodes (24): BaseSettings, Typed application settings. Reads ONLY process environment variables with the…, Settings, LivePaperRunner, Fetch finalized candles between the trader's last candle and now via REST., Route one websocket kline event through the two-phase protocol with gap safety., Consume the stream forever. No orders. No training. Frozen policy only., kline_events() (+16 more)

### Community 17 - "test_contracts.py"
Cohesion: 0.08
Nodes (35): Unit tests for canonical data contracts (`MarketBar`, `EventNewsItem`)., Verify that NaN and Infinity are rejected for all price and volume fields., Verify OHLC, bid/ask ordering, and non-negative volume enforcement., Verify strict enum instance checks and rejection of silent string conversion., Verify crypto observed, forex unavailable/tick, and bar-only mode rules., Verify observed_at_utc vs timestamp_utc ordering and deterministic ingestion…, Verify round-trip dictionary serialization, unknown/missing field and tamper…, Verify valid EventNewsItem construction and automatic record_hash generation. (+27 more)

### Community 18 - "holdout.py"
Cohesion: 0.12
Nodes (34): compute_dataset_identity(), get_holdout_dir(), get_holdout_lock_path(), get_holdout_state_path(), _holdout_lock(), load_holdout_state(), parse_utc_boundary(), _parse_utc_date() (+26 more)

### Community 19 - "stub_gate"
Cohesion: 0.09
Nodes (24): AlphaGate, ndarray, Return +1 (long), -1 (short), or 0 (flat) based on signed edge vs margin. Args:…, GateDirectStrategy, GatedStrategy, ndarray, Clamp a base strategy's proposal to directions the gate permits. Gate…, Direct supervised target-position policy: full long/short beyond the margin. (+16 more)

### Community 20 - "test_alpha_gate.py"
Cohesion: 0.23
Nodes (33): load_gate(), Load a text-format booster after validating metadata, checksum, and schema., _base_meta(), Path, Alpha Gate tests: chronological ES split with purge, artifact safety, gating…, Write a gate_meta.json with a stub gate.txt to allow path checks., Write gate.txt stub and gate_meta.json with the given meta (allow_nan=True)., test_gate_changed_feature_schema_bounds_rejected() (+25 more)

### Community 21 - "test_provider_smoke.py"
Cohesion: 0.09
Nodes (31): CaptureFixture, patch, QuoteStatus, make_smoke_bar(), MonkeyPatch, Unit tests for live provider smoke test tool CLI and safety interlocks…, Verify OANDA secret token is scrubbed from error output if provider fails., Verify non-zero exit when returned bars fail contract validation. (+23 more)

### Community 22 - "ingest_provider_market_data"
Cohesion: 0.14
Nodes (30): ingest_provider_market_data(), Fetch, validate, and securely store market data from a provider., make_bar(), mock_binance(), mock_oanda(), Any, fixture, Path (+22 more)

### Community 23 - "test_packaging.py"
Cohesion: 0.06
Nodes (28): Obsidian-RL: deep-RL cryptocurrency research and live-paper-trading platform.…, parametrize, Tests for package metadata, module structure, and installability., Verify pyproject.toml configuration and dependencies., Ensure setuptools find where is set to src to avoid packaging tests or legacy., Verify that all required runtime submodules can be cleanly imported., Verify obsidian_rl module origin relative to sys.path entries., Verify pyproject.toml defines all required optional dependency groups. (+20 more)

### Community 24 - "RewardConfig"
Cohesion: 0.12
Nodes (24): integer, Any, ndarray, Weights for reward shaping. Purposes: - turnover_weight: discourages churn…, RewardConfig, TradingEnv, make_env(), Gymnasium environment tests: compliance, determinism, hand-calculated… (+16 more)

### Community 25 - "validate_market_bars"
Cohesion: 0.12
Nodes (28): ForexSessionConfig, is_forex_weekend_gap(), Configurable hours and rules for Forex market weekend closures., Check if the gap between two timestamps represents a standard Forex weekend…, Inspect a sequence of MarketBar objects for data quality violations., validate_market_bars(), make_bar(), Comprehensive test suite for MarketBar data quality validation pipeline. (+20 more)

### Community 26 - "test_dashboard_queries.py"
Cohesion: 0.19
Nodes (25): _fmt_ts(), main(), Streamlit dashboard over the ledger. Run: .venv\\Scripts\\python.exe -m…, closed_trade_events(), equity_and_drawdown(), get_run_closure(), kpis(), list_run_summaries() (+17 more)

### Community 27 - "schema_fingerprint"
Cohesion: 0.13
Nodes (25): _build_descriptor(), _canonical_json(), Any, Obsidian-RL versioned feature schema contract. This module is the single…, Build the complete ordered schema descriptor used for hashing., Return the complete versioned schema descriptor (not hashed yet)., Serialise a descriptor as canonical sorted-keys compact JSON with…, Compute the lowercase 64-char SHA-256 of the canonical schema descriptor. If… (+17 more)

### Community 28 - "test_holdout.py"
Cohesion: 0.15
Nodes (20): Backtest runner, metrics, and walk-forward evaluation., clean_git(), fake_settings(), isolated_holdout_paths(), fixture, Path, Tests for Phase 4 holdout evaluation: single-use, frozen champion, immutable…, _setup_mock_champion() (+12 more)

### Community 29 - "calculate_trend_signal"
Cohesion: 0.14
Nodes (25): calculate_trend_signal(), MarketBar, Calculate the trend signal from a chronologically ordered series of bars., make_bar(), AssetClass, MarketBar, Timeframe, Tests for Trend Engine V1. (+17 more)

### Community 30 - "test_ledger.py"
Cohesion: 0.21
Nodes (25): make_ledger(), Path, Ledger tests: idempotency, restart recovery, session separation., record_one(), test_duplicate_candle_rejected(), test_finalize_run_idempotence(), test_finalize_run_inconsistent_closure_without_ended(), test_finalize_run_inconsistent_ended_without_closure() (+17 more)

### Community 31 - "MarketBar"
Cohesion: 0.08
Nodes (20): LogCaptureFixture, MarketBar, Serialize MarketBar to dictionary with stable enum string values., Canonical multi-asset OHLCV market bar data contract. Enforces strict enums,…, Filter [start_ms, end_ms), deduplicate by timestamp, and sort chronologically., Construct a deterministic dataset manifest from an ordered list of bars., DummyProvider, Verify permanent HTTP 4xx errors immediately fail without retry. (+12 more)

### Community 32 - "test_portfolio_engine.py"
Cohesion: 0.14
Nodes (24): make_engine(), Hand-calculated portfolio accounting tests. Cost model used throughout: fee…, Regression (review finding): a close must bypass the no-trade band., Regression (review finding): |exposure| < tolerance must not make a position…, test_bankrupt_forces_flat(), test_close_executes_even_within_exposure_tolerance(), test_drawdown_tracking(), test_equity_conservation_at_constant_price() (+16 more)

### Community 33 - "PortfolioConfig"
Cohesion: 0.13
Nodes (11): run_audit(), PortfolioConfig, PortfolioEngine, Owns cash, position, P&L, costs, turnover, drawdown. Nothing else may., Update peak equity; return a snapshot copy of state., Move the position toward a target exposure at the given executable price., Apply a funding event; returns the cash delta (negative = paid)., Terminal close of any open position (episode end / session end). (+3 more)

### Community 34 - "test_training.py"
Cohesion: 0.15
Nodes (22): _mock_clean_git_state_module(), fixture, Path, TempPathFactory, PPO training pipeline tests: CPU smoke training, save/load, compatibility…, test_checksum_tamper_rejected(), test_cli_parser_turnover_penalty_bps(), test_deterministic_inference() (+14 more)

### Community 35 - "trend_backtest.py"
Cohesion: 0.19
Nodes (18): Enum, _get_exec_price(), _hash_dataset(), AssetClass, MarketBar, Cross-Market Trend Backtesting Framework., Run a single pass of the backtest logic., Return the correct execution price for a given transition. (+10 more)

### Community 36 - "test_binance_client.py"
Cohesion: 0.26
Nodes (14): BinanceFuturesRest, FakeResponse, FakeSession, make_client(), make_raw_klines(), Any, REST client tests with a fully mocked HTTP session. No network access., Returns queued responses; records request params. (+6 more)

### Community 37 - "save_gate"
Cohesion: 0.13
Nodes (19): build_training_frame(), DataFrame, Series, Train on a chronological prefix; early-stop on the purged chronological tail., save_gate(), train_gate(), Path, test_alpha_gate_training_save_load() (+11 more)

### Community 38 - "load_record"
Cohesion: 0.31
Nodes (18): load_record(), Validate metadata + checksum + feature schema before anyone touches the…, _mock_clean_git_state(), Any, fixture, Path, Model registry schema contract validation tests., _register_stub() (+10 more)

### Community 39 - "extract_continuous_features"
Cohesion: 0.19
Nodes (17): extract_continuous_features(), extract_uppercase_features(), get_alpha_gate_model(), predict_trade_viability(), Any, DataFrame, LGBMRegressor, ndarray (+9 more)

### Community 40 - "run_live_trader"
Cohesion: 0.17
Nodes (17): compute_7d_state(), extract_current_kline_features(), load_agent_checkpoint(), DataFrame, ndarray, Path, Live Paper-Trading Execution Module for Institutional RL Trading Systems.…, Calculates the 7D observation state tuple from recent market price arrays.… (+9 more)

### Community 41 - "QLearningAgent"
Cohesion: 0.13
Nodes (10): ndarray, QLearningAgent, Q-Learning Agent for Institutional Reinforcement Learning Trading Systems. This…, Appends the latest asset return to the rolling history window…, Selects an action using an epsilon-greedy policy with dynamic EV threshold…, Updates the Q-table using the standard Temporal Difference (TD) learning rule.…, Tabular Q-Learning Agent for financial market trading environments. Uses a…, Decays exploration probability epsilon multiplicatively toward min_epsilon.… (+2 more)

### Community 42 - "download.py"
Cohesion: 0.19
Nodes (15): Settings, BinanceFuturesRest, Session, Public Binance USD-M futures REST client (ADR-003). Market data only. No…, Paginated public kline fetcher for GET /fapi/v1/klines., incremental_update(), initial_download(), _month_range() (+7 more)

### Community 43 - "DataFetchError"
Cohesion: 0.19
Nodes (15): DataFetchError, RuntimeError, Market data could not be retrieved. Callers must not fall back to synthetic…, _download(), monthly_zip_url(), _normalize_timestamp_unit(), _parse_zip_csv(), DataFrame (+7 more)

### Community 44 - "CandleStore"
Cohesion: 0.20
Nodes (8): CandleStore, DataFrame, Path, RuntimeError, Same open_time present with different values — refusing to rewrite history., Merge candles into monthly partitions. Idempotent; conflicts raise., StoreConflictError, WriteResult

### Community 45 - "ppo.py"
Cohesion: 0.26
Nodes (14): detect_device(), DeviceReport, Torch device detection. Reports capability; never alters global CUDA state., prefer: 'auto' | 'cpu' | 'cuda'. Falls back to CPU with an honest report., _make_env_fn(), PpoHyperparams, DataFrame, PPO training on the TradingEnv (Stable-Baselines3, MLP policy, discrete-5… (+6 more)

### Community 46 - "data/schema.py"
Cohesion: 0.21
Nodes (13): Series, coerce_candle_frame(), empty_candle_frame(), klines_to_frame(), open_time_to_utc(), DataFrame, ValueError, Canonical candle schema shared by training, evaluation, replay, and live paper… (+5 more)

### Community 47 - "validation.py"
Cohesion: 0.20
Nodes (11): dataset_gap_frame(), DataFrame, Convenience: gap list as a frame for reporting., CandleValidationError, DataFrame, ValueError, Candle validation: duplicates, gaps, malformed OHLCV, interval spacing,…, Validate a canonical candle frame. Returns a report; never mutates or repairs. (+3 more)

### Community 48 - "registry.py"
Cohesion: 0.27
Nodes (14): current_git_commit(), dependency_versions(), get_git_source_state(), list_models(), Any, Path, RuntimeError, Model registry: metadata, checksums, compatibility gates, promotion status.… (+6 more)

### Community 49 - "RealMarketEnv"
Cohesion: 0.16
Nodes (8): Any, Real Market Environment for Reinforcement Learning Trading Systems. This module…, The signed integer representation of the current position (-1, 0, or 1)., Constructs the current 7D observation state tuple. Calculates directional…, Real Financial Market Environment streaming historical data via `yfinance`.…, Re-initializes the environment to its starting state. Resets step counter to 0,…, Advances the market environment by one step using historical close prices.…, RealMarketEnv

### Community 50 - "SyntheticMarketEnv"
Cohesion: 0.19
Nodes (8): Any, Synthetic Market Environment for Reinforcement Learning Trading Systems. This…, Constructs the current observation state dictionary. Returns ------- dict[str,…, Re-initializes the environment to its starting state. Resets the price to…, Advances the market environment by one time step and calculates reward.…, Synthetic Financial Market Environment for Reinforcement Learning. Simulates…, The signed integer representation of the current position (-1, 0, or 1)., SyntheticMarketEnv

### Community 51 - "_load_champion_data"
Cohesion: 0.15
Nodes (14): current_champion(), _load_champion_data(), Return the current champion model_id from CHAMPION.json, or None., Load CHAMPION.json; strictly validate or normalize legacy files; reject…, Regression (review): a second rollback must walk further back (C->B->A), never…, _record_passing_evidence(), test_champion_json_duplicate_lineage_rejected(), test_champion_json_invalid_generation_rejected() (+6 more)

### Community 52 - "trend.py"
Cohesion: 0.17
Nodes (9): Exception, DataQualityError, Cross-Market Trend Engine V1., Output signal from the trend engine., Base exception for Trend Engine errors., Raised when the input series fails data quality checks., TrendEngineError, TrendSignal (+1 more)

### Community 53 - "test_oanda.py"
Cohesion: 0.15
Nodes (12): MonkeyPatch, Unit tests for OANDA Practice Forex adapter (`OandaPracticeProvider`)., Verify exact midpoint OHLC, closing bid/ask, daily UTC alignment, and…, Verify Timeframe.M3 is rejected by OANDA adapter with…, Verify malformed timestamps or missing mid/bid/ask raise MalformedResponseError., Verify environment-token loading, missing token rejection, and complete…, Verify crossed quotes (ask < bid) raise MalformedResponseError and incomplete…, test_oanda_crossed_quotes_and_incomplete_candle_rejection() (+4 more)

### Community 54 - "test_vision_bulk.py"
Cohesion: 0.41
Nodes (12): csv_rows(), make_source(), make_zip(), Vision bulk download tests with in-memory zips and checksum verification. No…, test_checksum_mismatch_raises(), test_fetch_month_verifies_checksum_and_parses(), test_header_row_skipped(), test_microsecond_timestamps_normalized() (+4 more)

### Community 55 - "train_and_save_alpha_gate"
Cohesion: 0.25
Nodes (10): engineer_features_and_target(), fetch_binance_testnet_klines(), DataFrame, LGBMRegressor, Path, Alpha Gate Training Module for Institutional RL Trading Systems. Fetches…, Fetches Binance Testnet data, engineers features/targets, fits LGBMRegressor,…, Retrieves historical klines from Binance Testnet and parses into a clean… (+2 more)

### Community 56 - "test_costs.py"
Cohesion: 0.22
Nodes (10): funding_cash_flow(), Signed cash flow of a funding event for a perpetual position. Longs pay when…, Cost model tests with hand-calculated values., test_component_costs_on_notional(), test_funding_long_pays_positive_rate(), test_funding_negative_rate_reverses(), test_funding_short_receives_positive_rate(), test_insane_parameters_rejected() (+2 more)

### Community 57 - "parse_trades_log"
Cohesion: 0.27
Nodes (9): compute_closed_trades_metrics(), parse_trades_log(), DataFrame, Path, Streamlit Web Dashboard for Monitoring Paper-Trading Performance. This…, Renders the Streamlit quantitative monitoring dashboard., Reads and parses `live_trades.log` into a structured pandas DataFrame. Handles…, Calculates total closed trades count and win rate from closed positions.… (+1 more)

### Community 58 - "evaluate_agent"
Cohesion: 0.22
Nodes (8): evaluate_agent(), main(), Evaluation Module for Institutional Reinforcement Learning Trading Systems.…, Evaluates a trained Q-learning agent in a deterministic exploitation mode. Sets…, Orchestrates agent training, evaluation, and chart generation., Training Orchestration Module for Institutional Reinforcement Learning Systems.…, Runs the reinforcement learning training loop against historical market data.…, train()

### Community 59 - ".fetch_klines"
Cohesion: 0.20
Nodes (6): MarketDataSource, Any, DataFrame, Protocol, Fetch funding rate history from GET /fapi/v1/fundingRate., Fetch [start_ms, end_ms] inclusive, paginating past the 1500-candle limit.

### Community 60 - "test_binance.py"
Cohesion: 0.20
Nodes (9): Unit tests for Binance Spot public kline adapter (`BinanceSpotProvider`)., Verify exact interval strings and rejection of unsupported timeframes., Verify invalid response or NaN/Infinity prices raise MalformedResponseError., Verify exact OHLC conversion, QuoteStatus.UNAVAILABLE, and multi-page…, Verify that candles whose observed_at_utc > current_time_ms are rejected., test_binance_exact_timeframe_mappings_and_unsupported_rejection(), test_binance_incomplete_candle_rejection(), test_binance_malformed_payload_and_non_finite_rejection() (+1 more)

### Community 61 - "Path"
Cohesion: 0.28
Nodes (5): Path, Saves the agent's Q-table dictionary to disk using pickle. Parameters…, Loads a saved Q-table dictionary from disk using pickle. Parameters ----------…, Alias for `save` to persist the Q-table checkpoint to disk., Alias for `load` to load a Q-table checkpoint from disk.

### Community 62 - "parse_kline_event"
Cohesion: 0.32
Nodes (7): parse_kline_event(), Parse one websocket message; None for non-kline payloads or invalid events., test_parse_kline_event_official_payload(), Tests for websocket kline stream parsing and validation., test_parse_kline_event_malformed_or_invalid(), test_parse_kline_event_non_kline_type(), test_parse_kline_event_valid()

### Community 63 - "run_migrations"
Cohesion: 0.29
Nodes (5): Connection, Database schema definitions and migration scripts for SQLite storage., Initialize database schema idempotently and configure pragmas., run_migrations(), Path

### Community 65 - "test_alpha_gate_pilot.py"
Cohesion: 0.43
Nodes (6): Tests for Alpha Gate Historical Pilot 01., test_eligibility_checks_failing_worst_fold(), test_eligibility_checks_passing(), test_non_finite_rejection(), check_strategy_eligibility(), Any

### Community 66 - "test_secret_hygiene.py"
Cohesion: 0.38
Nodes (4): Secret hygiene: no credentials or runtime artifacts may be tracked by git., test_no_forbidden_files_tracked(), test_no_hardcoded_secrets_in_tracked_sources(), tracked_files()

### Community 67 - ".from_dir"
Cohesion: 0.33
Nodes (5): Path, load_policy(), Any, Path, Load a validated model for inference (exploration disabled by the caller).

### Community 68 - "PromotionThresholds"
Cohesion: 0.33
Nodes (5): PromotionThresholds, ValueError, Risk gates a candidate must pass on the validation slice (base cost scenario)., test_promotion_thresholds_validation(), test_validate_report_rejects_source_tree_clean_false()

### Community 70 - "main"
Cohesion: 0.50
Nodes (3): main(), Verification script for RealMarketEnv data ingestion and state transitions.…, Runs data ingestion and state transition verification for `RealMarketEnv`.…

### Community 71 - "manifest.py"
Cohesion: 0.67
Nodes (3): load_and_validate_manifest(), ManifestComponent, Canonical immutable manifest loading and validation.

### Community 72 - "models_with_two_candidates"
Cohesion: 0.50
Nodes (4): _mock_clean_git_state_module(), models_with_two_candidates(), fixture, TempPathFactory

### Community 73 - "_parse_args"
Cohesion: 0.67
Nodes (3): main(), _parse_args(), Namespace

### Community 74 - "_validation_data_sha256"
Cohesion: 0.67
Nodes (3): DataFrame, Hash validation data including its column order, dtypes, index, and values., _validation_data_sha256()

## Knowledge Gaps
- **1 isolated node(s):** `obsidian-rl`
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CostModel` connect `CostModel` to `PortfolioConfig`, `costs.py`, `trend_backtest.py`, `Ledger`, `cli.py`, `test_promotion.py`, `PromotionThresholds`, `PortfolioObs`, `PpoSeedEnsembleStrategy`, `promotion.py`, `ppo.py`, `TrendConfig`, `Settings`, `holdout.py`, `RewardConfig`, `test_costs.py`, `test_holdout.py`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Why does `make_candles()` connect `make_candles` to `test_alpha_gate_pilot.py`, `costs.py`, `test_training.py`, `test_promotion.py`, `save_gate`, `cli.py`, `PortfolioObs`, `models_with_two_candidates`, `CostModel`, `Settings`, `_load_champion_data`, `test_alpha_gate.py`, `RewardConfig`, `test_dashboard_queries.py`, `test_holdout.py`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Why does `Ledger` connect `Ledger` to `make_candles`, `PortfolioConfig`, `costs.py`, `cli.py`, `CostModel`, `Settings`, `test_dashboard_queries.py`, `test_ledger.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 35 inferred relationships involving `CostModel` (e.g. with `RewardConfig` and `TradingEnv`) actually correct?**
  _`CostModel` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `Ledger` (e.g. with `RunSummary` and `CostModel`) actually correct?**
  _`Ledger` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `MarketBar` (e.g. with `BaseRestProvider` and `MarketDataProvider`) actually correct?**
  _`MarketBar` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `obsidian-rl` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._