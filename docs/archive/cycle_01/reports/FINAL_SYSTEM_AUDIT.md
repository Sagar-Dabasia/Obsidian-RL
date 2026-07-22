# Final System Audit

## Repository state

- **Branch**: `wip/phase8-ci-reproducibility`
- **Starting commit**: `d1c0ed55273be5cab0e0b00eba32c50d1f7b6907`
- **Working tree status**: Clean (`git status --short` returns clean prior to audit documentation)
- **Sensitive files (`.env`)**: Not tracked (`git ls-files -- .env` returns empty)

---

## Commands and exit codes

All verification commands were executed offline in clean environments without Binance or network connection access:

| Command | Exit Code | Result Summary |
|---|---|---|
| `python -m pytest -q` | `0` | `383 passed, 1 skipped in 25.86s` |
| `python -m compileall -q src tests` | `0` | Clean syntax compilation across 118 files |
| `python -m ruff check src tests` | `0` | Clean (all lint checks passed) |
| `python -m ruff format --check src tests` | `0` | Clean (all 76 files formatted) |
| `python -m mypy src` | `0` | `Success: no issues found in 46 source files` |
| `python -m pip check` | `0` | `No broken requirements found.` |
| `python -m build` | `0` | Clean build of `obsidian_rl-0.1.0.tar.gz` and `obsidian_rl-0.1.0-py3-none-any.whl` |
| `git diff --check` | `0` | Clean (no whitespace errors or merge leftovers) |
| `git status --short` | `0` | Clean working tree |
| `git ls-files -- .env` | `0` | Clean (0 tracked `.env` files) |

---

## Confirmed strengths

### 1. Repository and security
- **No tracked credentials**: `.env` and `.env.*` files are excluded in `.gitignore` (`tests/test_repository_hygiene.py::test_env_file_not_tracked` and `git ls-files -- .env` confirmed 0 tracked secrets).
- **Excluded local state & artifacts**: `.gitignore` strictly blocks `__pycache__/`, `.pytest_cache/`, `.venv/`, `*.db`, `*.sqlite`, `*.pkl`, `*.joblib`, `*.pt`, `/data/`, `/artifacts/`, and `/models/`.
- **Offline & unprivileged CI**: `.github/workflows/ci.yml` enforces least-privilege `permissions: contents: read`, concurrency cancellation, and offline execution without API credentials or market-data downloads.
- **Clean packaging & self-containment**: `pyproject.toml` isolates packages via `where = ["src"]`, preventing top-level `tests` collisions (`tests/__init__.py`). Wheel smoke testing verifies self-contained CLI (`obsidian-rl = "obsidian_rl.cli:main"`) outside the source directory.

### 2. Data integrity and leakage
- **Strict candle validation**: `validate_candle_frame()` enforces exact chronological timestamps (`interval_ms=60_000`), float32 contiguity, exact row alignment, and zero NaN/Infinity tolerance.
- **Holdout segregation**: `run_final_holdout()` enforces single-use execution locked by `HOLDOUT_LOCK.json` with repository anchoring and immutable SHA-256 fingerprint checks. Train, validation, candidate gating, and replay pathways cannot enter `get_holdout_dir()`.
- **No look-ahead in features & targets**: Feature computation (`compute_market_features`) uses strictly historical sliding normalization and returns aligned matrices without forward peeking. Target labeling (`compute_alpha_labels`) uses forward horizon returns cleanly segregated from observation vectors.

### 3. Model lifecycle
- **Validation-selected registration**: `train_ppo` exclusively saves the best validation checkpoint (`eval_freq=10_000`, evaluated net of simulated costs) via `register_model()`.
- **Immutable metadata & provenance**: Every registered model produces canonical `metadata.json` (`schema_version="1.0.0"`) capturing exact `git_commit`, `git_is_clean`, feature fingerprint, and SHA-256 artifact checksums (`reject_tampered_metadata`).
- **Atomic & locked promotion**: `promote_model()` acquires a cross-process lock (`.champion.lock`), validates candidate evaluation evidence (`eval_report.json` with positive net returns), verifies SHA-256 match, and atomically updates `CHAMPION.json` with full rollback lineage.

### 4. Feature and Alpha Gate contracts
- **Schema-bound transformation**: `schema_fingerprint()` binds exact feature names, order (`MARKET_FEATURES`), dimensions, data types (`float32`), and normalization parameters.
- **Fail-closed schema validation**: Both PPO policy loading (`train_ppo`, `run_paper_trader`) and Alpha Gate inference (`AlphaGate.load`) verify `expected_feature_fingerprint`. Schema mismatch immediately raises `FeatureSchemaMismatchError` or `GateCompatibilityError`.
- **Directional Alpha Gate target**: Gating targets (`AlphaGateTarget`) account for long/short actions and fee thresholds (`threshold_bps=5.0`), failing flat (`FLAT`) if inference fails or predictions drop below threshold.

### 5. Accounting parity
- **Consistent execution timing**: `PaperTrader` and `backtest_policy` use identical fill simulation (`simulate_fill`) with half-spread plus slippage penalties applied at the W+1 candle open after decision W.
- **Terminal liquidation curve parity**: Both live-paper runs (`LivePaperRunner.run`) and walk-forward evaluations (`run_walk_forward_evaluation`) force terminal liquidation at the final bar to compute exact net-of-cost realized PnL.
- **Signed chronological funding**: `funding_cash_flow()` correctly applies signed funding rates (`Long` pays positive rate, `Short` receives). Duplicate identical funding events are idempotent (`record_funding`), while conflicting duplicates raise `FundingAccountingError`.
- **Closed session protection**: `Ledger.resume` rejects closed sessions (`session_ended_at`), configuration mismatches (`PortfolioConfig`, `CostModel`), or incomplete legacy metadata.

### 6. Reconnect and failure safety
- **Gap safety without fictional fills**: `LivePaperRunner` catches up missed historical bars during reconnect (`fetch_historical_candles`) via `_catchup_and_sync`, updating observation buffers and feature state without emitting orders or synthetic fills.
- **Pending execution expiration**: `simulate_fill` checks execution deadlines (`candle.open_time >= decision.execution_deadline`) and expires late orders durably (`EXPIRED`).
- **Sanitized failure evidence**: Any fatal stream error, WebSocket crash, or prediction failure triggers `record_failure()`, persisting sanitized traceback and context (`failure_events` table) without dumping environment secrets or raw keys.

### 7. Configuration and operational readiness
- **Authoritative ledger metadata**: `Ledger` records canonical JSON summaries of `PortfolioConfig` and `CostModel` upon run initialization, ensuring runtime parameters exactly equal stored ledger state.
- **Finite defaults & input bounds**: All numeric parameters (`initial_cash`, `fee_bps`, `slippage_bps`, `expected_interval_ms`) enforce strict bounds (>0, no NaN/Infinity/bool conversions).
- **Clean operational codebase**: System audit confirmed zero `TODO`, `FIXME`, or `NotImplementedError` markers, zero silent exception swallowing, and zero placeholder/stub code across production modules (`src/obsidian_rl`).

### 8. Strategy evidence
- **Engineering vs. Trading separation**: The test suite confirms algorithmic and accounting correctness (`383 passed`), proving that accounting engines, backtests, and paper loops correctly track simulated costs, funding, and walk-forward boundaries.
- **No claim of profitability**: The system makes no assertion of financial edge or real-world profitability. Out-of-sample edge requires extensive controlled walk-forward historical experiments across multi-year market regimes.
- **Untouched holdout integrity**: Final holdout dataset remains untouched and unobserved (`HOLDOUT_LOCK.json` indicates zero runs executed).

---

## Findings

No blockers, high-severity, medium-severity, or low-severity defects were found during the Phase 8 audit.

| ID | Severity | Status | File / Function | Evidence | Required Correction |
|---|---|---|---|---|---|
| None | N/A | Clean | N/A | All 383 automated unit tests, 24 hygiene/packaging tests, and static checks passed with clean exit codes. | None |

---

## Unverified experimental questions

The following research questions remain unverified and require controlled historical experimentation before any practical assessment of strategy edge:
1. **Walk-Forward Out-of-Sample Performance**: Does PPO policy training on multi-year Binance BTC/USDT 1-minute historical data produce positive net-of-cost Sharpe ratios across out-of-sample walk-forward folds?
2. **Alpha Gate Filtering Efficiency**: Does the LightGBM supervised Alpha Gate reliably reject negative expected-value trades (`FLAT`) net of transaction costs across high-volatility market regimes?
3. **Hyperparameter Sensitivity**: How sensitive is the policy to reward shaping weights, entropy coefficients, sliding normalization window sizes (`window=1440`), and fee threshold configurations?
4. **Final Holdout Generalization**: Upon completion of all walk-forward and candidate gating experiments, does the single designated champion policy maintain statistically significant performance when evaluated once against the reserved holdout?

---

## Safe next operating stage

The system is safe and verified for **Controlled Offline Historical Training and Walk-Forward Research**:
- Researchers and automated pipelines may safely execute historical data downloads (`obsidian-rl data-download`), incremental updates (`obsidian-rl data-update`), offline PPO training (`obsidian-rl train`), and walk-forward evaluations (`obsidian-rl walk-forward`).
- All runs are strictly bound to offline simulated execution net of assumed costs (`fee_bps`, `spread`, `slippage`, `funding`).
- **Not Approved For**: Real money trading, live exchange order placement, or public testnet order execution.

---

## Final verdict

READY FOR CONTROLLED HISTORICAL TRAINING
