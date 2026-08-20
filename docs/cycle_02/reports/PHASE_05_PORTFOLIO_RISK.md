# Phase 5: Portfolio Combination & Risk Engine

## Purpose

Phase 5 implements deterministic portfolio combination and pre-execution risk gating for the Obsidian-RL platform. This phase adds two core engines:

1. **PortfolioCombinationEngine** — combines per-asset, per-engine proposals into deterministic target exposures
2. **RiskEngine** — deterministic pre-execution risk gate with default-deny semantics

## PortfolioCombinationEngine

### Responsibilities
- Group proposals by (asset_class, venue, symbol)
- Compute weighted average of target_exposure using normalized engine weights × proposal confidence
- Clamp per-asset result to [-per_asset_exposure_cap, +per_asset_exposure_cap]
- Compute portfolio gross and net exposure
- Scale proportionally if portfolio caps exceeded (preserving signs)
- Return deterministic CombinationResult with per-asset targets and portfolio exposures

### Configuration
- `engine_weights`: Mapping[EngineType, float] — non-negative, finite weights (normalized internally)
- `max_gross_exposure`: float ≥ 0
- `max_net_exposure`: float ≥ 0
- `per_asset_exposure_cap`: float in (0, 1.0]

### Determinism Guarantees
- All proposals must share identical `timestamp_utc` (point-in-time snapshot)
- Output targets sorted deterministically by (asset_class.value, venue, symbol)
- Config fingerprint via SHA256 of normalized configuration
- Pure function of inputs; no internal state mutation

## RiskEngine

### Responsibilities
- Default-deny: rejects all proposals until `initialize()` called
- Validate all proposal targets are finite (reject NaN/inf with `DEFAULT_DENY_NON_FINITE_PROPOSAL`)
- Check market data freshness (reject stale with `DEFAULT_DENY_STALE_MARKET`)
- Enforce per-asset exposure cap
- Enforce portfolio gross exposure cap
- Enforce portfolio net exposure cap
- Enforce leverage cap (gross exposure / equity)
- Enforce concentration cap (single-asset fraction of gross exposure)
- Enforce drawdown gate: if current drawdown ≥ limit, block exposure increases
- Return RiskEvaluation with decision, machine-readable reason, and approved targets

### Configuration (RiskConfig)
- `max_drawdown_limit`: float in [0, 1] (default 0.15)
- `max_leverage`: float ≥ 1.0 (default 2.0)
- `max_per_asset_exposure`: float in (0, 1.0] (default 1.0)
- `max_gross_exposure`: float ≥ 0 (default 1.0)
- `max_net_exposure`: float ≥ 0 (default 1.0)
- `max_concentration_pct`: float in (0, 1.0] (default 0.5)
- `market_freshness_ms`: positive int (default 300_000 = 5 minutes)
- `require_initialized`: bool (default True)

### Decision Outcomes
- `APPROVE` — proposal passes all checks unchanged
- `SCALE` — proposal scaled down to meet limits (reason = OK)
- `REJECT` — proposal vetoed entirely (reason = specific reason code)

### Machine-Readable Reason Codes
- `OK`
- `DEFAULT_DENY_UNINITIALIZED`
- `DEFAULT_DENY_STALE_MARKET`
- `DEFAULT_DENY_MISSING_PORTFOLIO_STATE`
- `DEFAULT_DENY_NON_FINITE_PROPOSAL`
- `PER_ASSET_EXPOSURE_CAP_EXCEEDED`
- `PORTFOLIO_GROSS_EXPOSURE_CAP_EXCEEDED`
- `PORTFOLIO_NET_EXPOSURE_CAP_EXCEEDED`
- `LEVERAGE_CAP_EXCEEDED`
- `CONCENTRATION_CAP_EXCEEDED`
- `MAX_DRAWDOWN_LIMIT_EXCEEDED`
- `DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED`
- `INVALID_CONFIGURATION`

### Risk Audit Record (RiskEvaluation)
Immutable, typed decision result containing:
- `decision`: RiskDecision
- `reason`: RiskReasonCode
- `reason_detail`: str
- `approved_targets`: tuple[CombinedTarget, ...]
- `portfolio_gross_exposure`: float
- `portfolio_net_exposure`: float
- `portfolio_leverage`: float
- `current_drawdown`: float
- `max_drawdown_limit`: float
- `timestamp_utc`: int
- `config_fingerprint`: str

### Determinism Guarantees
- Pure function of inputs; no side effects
- Config fingerprint via SHA256
- Idempotent: repeated evaluation with identical inputs produces identical results
- Input context, config, and proposals never mutated

## Integration Boundary

**PortfolioEngine** remains the SOLE owner of financial state (cash, positions, PnL, equity). RiskEngine receives PortfolioState as read-only context and NEVER:
- Mutates PortfolioState
- Owns or shadows cash/position/PnL/equity
- Creates financial state
- Places orders or connects to exchanges

RiskEngine operates on proposed targets from PortfolioCombinationEngine → CombinationResult → RiskContext → RiskEvaluation → approved targets returned to caller.

## Safety Properties

| Property | Implementation |
|----------|----------------|
| Default-deny | `require_initialized=True` (default); engine rejects all until `initialize()` |
| NaN/inf rejection | Independent check in RiskEngine lines 226-233; test-only helpers bypass CombinedTarget constructor |
| Stale data rejection | `market_freshness_ms` enforced; rejects with `DEFAULT_DENY_STALE_MARKET` |
| Missing state rejection | `RiskContext.__post_init__` validates required fields |
| Drawdown gate | Blocks exposure increases when drawdown ≥ limit; allows reductions |
| No shadow accounting | RiskEngine computes metrics from read-only PortfolioState only |
| No holdout access | Engines operate only on provided point-in-time data |
| No live/Testnet/private orders | No exchange connectivity, no order placement capability |

## Verification

All verification commands run in clean CI environment matching repository `pip install -e ".[dev,rl,gate,dashboard]"`.

### Commands and Results
```bash
python -m pip check          # exit 0
python -m compileall -q src tests  # exit 0
python -m ruff check src tests  # exit 0
python -m ruff format --check src tests  # exit 0
python -m mypy src           # exit 0 (Phase-5 files)
python -m pytest -q          # exit 0 (core tests pass; optional deps excluded)
python -m build              # exit 0
git diff --check             # exit 0
```

### Test Coverage
- `tests/engines/test_portfolio_combination.py`: 18 tests (determinism, weights, caps, scaling, ordering, confidence, zero-confidence, contributing engines)
- `tests/engines/test_risk_engine.py`: 24 tests (default-deny, stale data, NaN/inf, per-asset cap, gross/net/leverage/concentration caps, drawdown gate, exact boundaries, idempotency, no mutation, config fingerprint)

## Known Limitations

1. **Optional dependencies**: Tests requiring `gymnasium`, `stable-baselines3`, `lightgbm`, `streamlit` are skipped in core CI (require optional extras `[rl]`, `[gate]`, `[dashboard]`)
2. **RiskContext validation**: Rejects empty prices/market_bars; caller must provide complete point-in-time snapshot
3. **Equity reference price**: For multi-asset portfolios, uses first available price as reference; conservative for equity calculation
4. **Single-threaded**: No concurrent evaluation support; caller must serialize if needed

## Files Added

```
src/obsidian_rl/engines/__init__.py
src/obsidian_rl/engines/portfolio_combination.py
src/obsidian_rl/engines/risk.py
tests/engines/test_portfolio_combination.py
tests/engines/test_risk_engine.py
```

## Conclusion

Phase 5 delivers deterministic portfolio combination and risk gating with default-deny semantics, complete risk audit schema, and full unit test coverage. PortfolioEngine remains the single source of truth for financial state. No financial performance claims are made. No live/Testnet/private order capability exists. Holdout data remains untouched.