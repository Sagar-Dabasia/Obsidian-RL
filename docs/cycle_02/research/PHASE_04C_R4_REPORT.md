# Phase 4C-R4 Forex Trend Stability Report

## Execution Identity
- **Manifest EURUSD**: `a26d1297fe909edbb6599721db0a3b284a97def044d59a9d67bbd45cc66e5e5e`
- **Manifest GBPUSD**: `99c3791719eafa0486f251379fd07864bcda8a7d6d1f608197885b13d473a69f`
- **Warm-up Count**: 909 H4 bars (Exceeds required 721)

## Performance Results

### EURUSD
- **Net Return**: -6.42%
- **Annualized Sharpe**: -0.26
- **Max Drawdown**: 11.46%
- **Hit Rate**: 52.30%
- **Trades**: 489
- **Total Costs**: 291.07

### GBPUSD
- **Net Return**: -7.09%
- **Annualized Sharpe**: -0.23
- **Max Drawdown**: 13.49%
- **Hit Rate**: 57.14%
- **Trades**: 505
- **Total Costs**: 249.07

## Acceptance Criteria Audit
1. Both markets yield positive net return: **FAIL** (-6.42%, -7.09%)
2. Median net return > 0: **FAIL** (-6.75%)
3. Median annualized Sharpe > 0.50: **FAIL** (-0.245)
4. Worst net return > -10%: **PASS** (-7.09%)
5. Median maximum drawdown <= 20%: **PASS** (12.47%)
6. At least 1/2 markets beat long Sharpe: **FAIL** (Both underperformed respective long baseline Sharpe)

## Erratum
The sidecar SHA256 (83B59C47A6EDE38FBE6E1A581F04E3659200D6C778D8314F8D377E2331180128) has no pre-result evidence of binding the plan. It was generated post-results in the same commit. Therefore, this run is invalid as a preregistered execution, though its metrics are retained as diagnostic negative evidence.

## Final Classification
`INVALID_PROVENANCE — No pre-result cryptographic proof that the exact plan was governed before execution.`
