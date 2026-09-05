# Phase 4F: Execution/Accounting Parity Audit

## Objectives

Compare Obsidian execution and accounting semantics against mature event-driven trading-engine principles (conceptually referenced via NautilusTrader paradigms). Establish financial correctness of the `PortfolioEngine` and `Ledger` state transitions in deterministic paths without using live market data or strategy performance claims.

## Audited Paths
- Flat → Long
- Hold Long
- Long → Flat
- Long → Short Reversal
- Terminal Liquidation
- Funding Event

## Parity Scenarios & Findings

A deterministic harness (`test_execution_accounting_parity.py` and `test_ledger_drawdown_regression.py`) was created to assert semantic correctness of the following quantities:
- Executed Target
- Position Quantity
- Cash
- Realized/Unrealized P&L
- Fees / Net Equity / Gross Equity / Turnover
- Peak Equity and Path Drawdown

### Defects Found and Fixed

1. **Lost Path Maximum Drawdown on Restore**
   - **Defect:** The `Ledger` was missing the `path_maximum_drawdown_pct` column in both the `decisions` and `run_closures` schemas. Since this state is path-dependent, it cannot be recalculated cleanly on ledger restoration (which only restores the most recent snapshot). Upon restoration, `path_maximum_drawdown_pct` was resetting to `0.0`.
   - **Correction:** Safely migrated `path_maximum_drawdown_pct` into the SQLite ledger `_SCHEMA` via `ALTER TABLE` statements inside `Ledger.__init__` initialization. Updated the INSERT payload and tuple sizes within `record_decision` and `record_closure`. Updated `restore_state` to safely unpack `path_maximum_drawdown_pct` and restore it onto `PortfolioState`. Regression tests now explicitly prove that drawdown logic survives roundtrip serialization.

### Intentional Differences

1. **Target Sizing and Cost Deduction Sequence**
   - **Observation:** When requesting a target exposure of `1.0` (100%), the system computes quantity purely on current net equity (`target_qty = approved * equity / price`). *After* quantity is executed, execution costs (fees, spread, slippage) reduce the available cash and therefore reduce net equity. The resulting calculated exposure strictly exceeds `1.0` (e.g. `10000.0 / 9990.0 = 1.001`).
   - **Reasoning:** In Obsidian, all components are separately attributable and charged directly to cash based on traded notional to keep costs decoupled from explicit fill-price adjustment logic. The side-effect of equity reduction post-execution matches the intended math. This was verified via `math.isclose` instead of enforcing strict rounding.

## Remaining Limitations
- Drawdowns are evaluated only exactly at decision intervals (`mark_to_market`). Intrabar drawdown extrema are invisible to the ledger unless sub-candle sampling is injected.

## Verification
- CI checks: Full `pytest -q`, `mypy src`, `ruff check`, `ruff format` run with 0 exit codes.
- No strategy/profitability conclusions drawn. No leaked live/Testnet order capabilities added.
