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
- Check market data freshness (reject stale with `DEFAULT_DENY_STALE_TARGET_BAR`)
- Validate market bar identity matches target (symbol, venue, asset_class)
- Enforce per-asset exposure cap
- Enforce portfolio gross exposure cap
- Enforce portfolio net exposure cap
- Enforce leverage cap (gross exposure / equity)
- Enforce concentration cap (single-asset fraction of gross exposure) — fail-closed rejection
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

### Decision Outcomes
- `APPROVE` — proposal passes all checks unchanged
- `SCALE` — proposal scaled down to meet limits (reason = OK)
- `REJECT` — proposal vetoed entirely (reason = specific reason code)

### Machine-Readable Reason Codes
- `OK`
- `DEFAULT_DENY_UNINITIALIZED`
- `DEFAULT_DENY_STALE_TARGET_BAR`
- `DEFAULT_DENY_MISSING_PORTFOLIO_STATE`
- `DEFAULT_DENY_NON_FINITE_PROPOSAL`
- `DEFAULT_DENY_MISSING_TARGET_PRICE`
- `DEFAULT_DENY_MISSING_TARGET_BAR`
- `DEFAULT_DENY_STALE_TARGET_BAR`
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

### Market Data Identity Validation
For EVERY target, RiskEngine validates:
- `current_prices[target.symbol]` exists
- `market_bars[target.symbol]` exists
- `bar.symbol == target.symbol`
- `bar.venue == target.venue`
- `bar.asset_class == target.asset_class`
- `bar.observed_at_utc` is within `market_freshness_ms`

Any mismatch triggers deterministic default-deny REJECT.

### Multi-Asset Portfolio State
PortfolioEngine is the SOLE owner of financial state. Extended with per-symbol position state:
- `positions: dict[str, PositionState]` — per-symbol qty, avg_entry_price, realized_pnl, costs, turnover
- `multi_asset_equity(prices)` — total equity using each symbol's own mark price
- `multi_asset_gross_exposure(prices)` — sum of absolute position notionals / total equity
- `multi_asset_net_exposure(prices)` — sum of signed position notionals / total equity
- `multi_asset_drawdown(prices)` — drawdown based on total multi-asset equity
- Deterministic regardless of Mapping insertion order
- Backwards compatible with single-asset fields (qty, avg_entry_price)

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
| Default-deny | Engine rejects all until `initialize()` called |
| NaN/inf rejection | Independent check in RiskEngine; test-only helpers bypass CombinedTarget constructor |
| Stale data rejection | `market_freshness_ms` enforced; rejects with `DEFAULT_DENY_STALE_TARGET_BAR` |
| Missing state rejection | `RiskContext.__post_init__` validates required fields |
| Market identity validation | Validates bar symbol/venue/asset_class match target |
| Drawdown gate | Blocks exposure increases when drawdown ≥ limit; allows reductions |
| Concentration gate | Fail-closed: rejects with `CONCENTRATION_CAP_EXCEEDED` if max concentration > limit |
| Leverage gate | Scales down if leverage > max_leverage |
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
python -m mypy src           # exit 0 (all source files)
python -m pytest -q          # exit 0 (481 passed, 1 skipped)
python -m build              # exit 0
git diff --check             # exit 0
```

### Test Coverage
- `tests/engines/test_portfolio_combination.py`: 18 tests (determinism, weights, caps, scaling, ordering, confidence, zero-confidence, contributing engines)
- `tests/engines/test_risk_engine.py`: 23 tests (default-deny, stale data, NaN/inf, per-asset cap, gross/net/leverage/concentration caps, drawdown gate, exact boundaries, idempotency, no mutation, config fingerprint, market identity validation, concentration gate, leverage gate)

### Adversarial Tests Verified
- Price order invariance: same BTC+ETH positions/prices with reversed Mapping insertion order produce identical results
- Own price valuation: BTC=100000, ETH=4000 each valued with own mark price
- Market identity validation: symbol/venue/asset_class mismatches default-deny
- Concentration gate reachable: BTC 0.9 / ETH 0.1 with cap 0.5 triggers `CONCENTRATION_CAP_EXCEEDED`
- Leverage gate reachable: single asset at max per-asset exposure shows correct leverage computation
- Missing/mismatched market data fail closed: missing price, missing bar, stale bar, symbol/venue/asset_class mismatches all default-deny
- Drawdown gate allows reductions while blocking increases
- Price order invariance: same portfolio with reversed price/bar Mapping insertion order produces identical results

## Files Added/Modified
```
src/obsidian_rl/engines/__init__.py
src/obsidian_rl/engines/portfolio_combination.py
src/obsidian_rl/engines/risk.py
src/obsidian_rl/portfolio/engine.py
tests/engines/test_portfolio_combination.py
tests/engines/test_risk_engine.py
```

## Conclusion

Phase 5 delivers deterministic portfolio combination and risk gating with default-deny semantics, complete risk audit schema, and full unit test coverage. PortfolioEngine remains the single source of truth for financial state with authoritative multi-asset accounting. RiskEngine evaluates multi-asset proposals using complete authoritative portfolio state with per-target market data identity validation. Concentration and leverage gates are reachable and proven. No financial performance claims are made. No live/Testnet/private order capability exists. Holdout data remains untouched.