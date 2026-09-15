# Cycle 02 Phase 4B: Trend Backtesting Framework

## Objective
Implement a point-in-time deterministic backtesting framework to evaluate the Trend Engine V1, without modifying execution logic, using only local SQLite data.

## Implementation Details

### Core Engine (`trend_backtest.py`)
- Evaluates Trend Engine V1 recursively point-in-time using `PortfolioEngine`.
- Executes signal on the NEXT bar after the bar the signal becomes known.
- Enforces strict point-in-time isolation with `observe_at_utc`.
- Returns three evaluation runs:
  - Strategy
  - Baseline Flat (buy and hold nothing)
  - Baseline Long (buy and hold full exposure)

### Cost Enforcement
- Crypto requires explicit `CostModel` instances with `taker_fee`, `half_spread` and `slippage`.
- Forex forces `CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)` because spreads are embedded in the bid/ask prices.
- If forex quotes are missing, the backtest fails closed (`ValueError`), avoiding hallucinated Zero spreads.

### Execution Tools (`run_trend_backtest.py`)
- Standard CLI providing point-in-time constraints.
- Loads data exclusively from local SQLite database, remaining completely offline.
- Explicit requirement of `--taker-fee`, `--half-spread` and `--slippage` ensures user explicitly understands costs.

### Validation (`test_trend_backtest.py`)
- Offline mock bars ensuring identical object fingerprint hashes via `compute_market_bar_hash`.
- Validates failure closures for absent quotes in Forex.
- Checks identical equity baseline performance for strictly flat strategies.
- Enforces next-bar execution constraint strictly.

## Constraints Preserved
- No forward-looking data usage (strictly point-in-time).
- No neural network or RL model training (used heuristic evaluation).
- No paper/real trades executed.
- Maintained "free tier" requirement.
- No modifications to verified accounting logic in `PortfolioEngine`.
