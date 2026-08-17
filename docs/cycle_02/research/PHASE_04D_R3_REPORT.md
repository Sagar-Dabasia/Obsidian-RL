# Phase 4D-R3 Perpetual Futures Execution Report

## Overview
This report summarizes the execution of Phase 4D-R3, implementing standard historical perpetual futures backtests over BTCUSDT and ETHUSDT. Both tests utilized exact ingestion models matching the Phase 4C-R4 methodology but extended to accommodate Binance Futures endpoints, including comprehensive continuous block funding rates and slippage models.

## Backtest Summary

### 1. BTCUSDT Perpetual
- **Dataset**: Binance Futures (USD-M), 4H timeframe
- **Warm-up**: 721 bars (Nov 2019 to Mar 2020)
- **Evaluation**: 8254 bars (Mar 2020 to Dec 2023)
- **Baseline (Long)**:
  - Net Return: +399.97%
  - Max Drawdown: 77.74%
  - Sharpe: 0.66
- **Strategy**:
  - Net Return: +280.42%
  - Gross Return: +388.28%
  - Max Drawdown: 56.19%
  - Sharpe: 0.72
  - Win Rate: 65.09%
  - Exposure: 54.83%
  - Total Costs (Fees/Slippage/Funding): 10,785.99 USDT

### 2. ETHUSDT Perpetual
- **Dataset**: Binance Futures (USD-M), 4H timeframe
- **Warm-up**: 721 bars (Nov 2019 to Mar 2020)
- **Evaluation**: 8254 bars (Mar 2020 to Dec 2023)
- **Baseline (Long)**:
  - Net Return: +1146.53%
  - Max Drawdown: 81.53%
  - Sharpe: 0.81
- **Strategy**:
  - Net Return: +285.98%
  - Gross Return: +470.67%
  - Max Drawdown: 65.26%
  - Sharpe: 0.58
  - Win Rate: 56.44%
  - Exposure: 57.20%
  - Total Costs (Fees/Slippage/Funding): 18,468.85 USDT

## Conclusion
The Trend-following strategy exhibits strong absolute returns but underperforms the Long baseline across both BTC and ETH, confirming exactly what was found in the Forex and Spot tests. Risk-adjusted metrics (Sharpe) are marginally higher for BTC but lower for ETH.

The backtest mechanically succeeded:
- Warm-up gap processing natively skipped the known `1582113600000` Binance Futures outage using `outages.py` rules.
- Funding arrays were correctly initialized from raw manifests.
- Slippage overrides applied appropriately in parallel.

## Erratum
The original backtest evaluation incorrectly applied a "median maximum drawdown <= 20%" gate. This gate was absent from the frozen `PHASE_04D_R3_PERPETUAL_PLAN.md` which governed this run. Under the actual execution-verification gates, this run successfully passes all checks.

However, the high drawdowns (BTC 56.19%, ETH 65.26%) are prominently retained as risk evidence and MUST NOT be treated as paper-trading promotion evidence merely because the narrower execution-verification plan passed.

## Final Classification
`VALID_PASS — Execution verification mathematically passed all preregistered accounting criteria, but unacceptable risk parameters prevent paper-trading promotion.`
