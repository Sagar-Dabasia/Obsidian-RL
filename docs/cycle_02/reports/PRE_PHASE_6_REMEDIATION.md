# Pre-Phase-6 Bounded Remediation Plan

**Status**: READY FOR IMPLEMENTATION
**Audit Complete**: YES (Financial, Red-Team, Environment reviewers all passed)
**Branch**: research/cycle-02-trend-pilot-02
**HEAD**: ff1bdda

---

## Summary

Hostile pre-Phase-6 audit found **8 confirmed defects** across 3 reviewers. This plan structures remediation into 4 bounded batches, prioritizing HIGH/CRITICAL issues first. Each batch is independently verifiable with existing test suite.

---

## Defect Inventory

| ID | Severity | Class | File:Line | Summary |
|----|----------|-------|-----------|---------|
| F-01 | HIGH | TYPE_CONFUSION | src/obsidian_rl/portfolio/engine.py:40,43,46 | `PortfolioConfig` accepts booleans (`True`→1.0, `False`→0.0) for `initial_cash`, `max_abs_exposure` |
| F-02 | HIGH | TYPE_CONFUSION | src/obsidian_rl/engines/risk.py:78-108 | `RiskConfig` accepts booleans for all numeric limits |
| F-03 | HIGH | TYPE_CONFUSION | src/obsidian_rl/portfolio/engine.py:242,258,263,265,323,339 | Validation methods (`_validate_target`, `_validate_execution_price`, `_validate_funding_params`) accept booleans via `isinstance(x, (int, float))` |
| F-04 | MEDIUM | TYPE_CONFUSION | src/obsidian_rl/engines/portfolio_combination.py:63-70 | `EngineProposal`, `CombinedTarget` accept boolean `target_exposure`/`confidence` |
| F-05 | MEDIUM | CALCULATION_ERROR | src/obsidian_rl/portfolio/engine.py:461-462 | Multi-asset `rebalance()` uses execution `price` instead of `marks[symbol]` for `executed_exposure` calculation |
| F-06 | LOW | INCONSISTENT_VALIDATION | src/obsidian_rl/portfolio/costs.py:25 vs engine.py | `CostModel` correctly rejects booleans; engines do not — inconsistent fail-closed behavior |
| F-07 | LOW | DOCUMENTATION_ERROR | src/obsidian_rl/portfolio/engine.py:93 | `PortfolioState.funding_paid` comment inverted vs actual implementation |
| F-08 | LOW | UNUSED_CODE | src/obsidian_rl/engines/risk.py:38 | `RiskReasonCode.DEFAULT_DENY_MULTI_ASSET_UNSUPPORTED` defined but never returned |

---

## Remediation Batches

### Batch 1: Boolean Type Guards (CRITICAL — Blocks all financial operations)

**Files to modify**:
- `src/obsidian_rl/portfolio/engine.py` — `PortfolioConfig.__post_init__`, all validation methods
- `src/obsidian_rl/engines/risk.py` — `RiskConfig.__post_init__`
- `src/obsidian_rl/engines/portfolio_combination.py` — `EngineProposal.__post_init__`, `CombinedTarget.__post_init__`
- `src/obsidian_rl/portfolio/costs.py` — Already correct, use as reference pattern

**Pattern to apply** (from `CostModel.__post_init__` line 25):
```python
if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise ValueError(f"{name}={value!r} must be int or float, not {type(value).__name__}")
```

**Specific changes**:
1. `PortfolioConfig.__post_init__`: Add boolean rejection for `initial_cash`, `max_abs_exposure`, `min_trade_notional`, `exposure_tolerance`
2. `RiskConfig.__post_init__`: Add boolean rejection for all numeric fields
3. `PortfolioEngine._validate_target`: Add `isinstance(proposed, bool)` check before `isinstance(proposed, (int, float))`
4. `PortfolioEngine._validate_execution_price`: Same
5. `PortfolioEngine._validate_funding_params`: Same for both `price` and `funding_rate`
6. `EngineProposal.__post_init__`: Add boolean rejection for `target_exposure`, `confidence`
7. `CombinedTarget.__post_init__`: Add boolean rejection for `target_exposure`, `gross_exposure_contribution`, `net_exposure_contribution`

**Verification**:
- Run full test suite: `pytest tests/ -q` → must pass (819 passed)
- New unit tests: Add boolean rejection tests to `test_portfolio_engine.py`, `test_risk_engine.py`, `test_portfolio_combination.py`, `test_costs.py`

---

### Batch 2: Multi-Asset Exposure Calculation Fix (MEDIUM — Financial correctness)

**File**: `src/obsidian_rl/portfolio/engine.py:461-462`

**Current bug**:
```python
post_equity = self.state.multi_asset_equity(marks)
executed_exposure = pos.qty * price / post_equity if post_equity > 0 else 0.0
```

**Fix**: Use mark price for position notional, execution price for cash accounting:
```python
post_equity = self.state.multi_asset_equity(marks)
mark_price = marks[symbol]
executed_exposure = pos.qty * mark_price / post_equity if post_equity > 0 else 0.0
```

**Verification**:
- Existing test `test_post_cost_executed_target_correct` currently passes only because `price == marks[symbol]` in test setup
- Add test case where execution price ≠ mark price (simulate slippage/spread) and verify `executed_target` uses mark price
- Run `pytest tests/test_portfolio_engine.py -q` → must pass

---

### Batch 3: Documentation & Dead Code Cleanup (LOW — No behavioral change)

**Files**:
1. `src/obsidian_rl/portfolio/engine.py:93` — Fix comment:
   - **Current**: `"net funding cash outflow (negative = received)"`
   - **Fixed**: `"net funding cash outflow (positive = paid, negative = received)"`

2. `src/obsidian_rl/engines/risk.py:38` — Remove unused enum variant:
   - Remove `DEFAULT_DENY_MULTI_ASSET_UNSUPPORTED = "DEFAULT_DENY_MULTI_ASSET_UNSUPPORTED"` from `RiskReasonCode`

**Verification**:
- Run full test suite → must pass
- No new tests needed (documentation only)

---

### Batch 4: Test File Ruff Fixes (PRE-EXISTING — Not part of audit findings)

**File**: `tests/test_agent_office_governance.py`

**Issues** (98 ruff errors):
- Unsorted imports (I001)
- Unused imports `json`, `sys` (F401)
- Lines exceeding 100 chars (E501)
- Missing trailing newline (W292)

**Note**: These are style issues in a modified test file, not production defects. Fix in separate PR or as part of Batch 1 if desired.

---

## Implementation Rules

1. **One batch at a time** — Complete and verify Batch 1 before starting Batch 2
2. **Test-first** — Add failing tests for each defect before implementing fix
3. **No scope creep** — Do not refactor unrelated code, rename variables, or change formatting beyond what's needed
4. **Verify after each batch** — Run `pytest tests/ -q` and confirm 819 passed
5. **Task scope sentinel** — Run `python tools/task_scope_sentinel.py check` after each batch

---

## Expected End State

After all 3 remediation batches:
- All 8 defects resolved
- Full test suite passes (819 passed, 1 skipped)
- `ruff check src/` — All checks passed
- `mypy src/obsidian_rl` — Success: no issues found
- Worktree clean except for intentional test file modifications
- Ready for Phase 6 governance checkpoint

---

## Rollback Procedure

If any batch causes regression:
1. `git restore <modified_files>`
2. Run full test suite to confirm baseline
3. Re-plan that specific batch with smaller steps

No database migrations, no schema changes, no external dependencies affected.