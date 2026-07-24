# Phase 4D Crypto Trend Robustness Report

## Evaluation Protocol
Markets: BTCUSDT, ETHUSDT
Evaluation Window: `1577836800000` to `1704067200000`
Strategy: 20/60/120-day trend with next-bar-open execution.

## Results Table

| Metric | BTCUSDT | ETHUSDT |
|--------|---------|---------|
| Manifest Digest | 0a70bdb71bcafeb5837485037c663a775b625263d8df2b1c8000e807c87b3bd3 | 7b86b57f2e34fc0b1b17f3f83561e5ecdb976460433acf951b5f05bb4ca42652 |
| Runtime Digest | 0a70bdb71bcafeb5837485037c663a775b625263d8df2b1c8000e807c87b3bd3 | 7b86b57f2e34fc0b1b17f3f83561e5ecdb976460433acf951b5f05bb4ca42652 |
| Digest Match | True | True |
| Total Rows | 9597 | 9597 |
| Warmup / Eval Rows | 832 / 8765 | 832 / 8765 |
| Accepted Outages | 1 | 1 |
| Gross Return | 466.63% | 517.40% |
| Net Return | 389.46% | 395.64% |
| Ann. Sharpe | 0.77 | 0.63 |
| Max Drawdown | 8.21% | 49.03% |
| Turnover | 11872092.93 | 18732547.51 |
| Exposure | 55.06% | 57.29% |
| Trades | 1278 | 1286 |
| Total Costs | 7716.86 | 12176.16 |
| Always-Long Return | 487.21% | 1665.49% |
| Always-Long Sharpe | 0.66 | 0.85 |
| Finite Metrics | True | True |

## Criterion Verdicts

1. Both markets have positive net return: 2/2 -> PASS
2. Median net return (392.55%) > 0 -> PASS
3. Median annualized Sharpe (0.70) > 0.50 -> PASS
4. Worst net return (389.46%) > -10% -> PASS
5. Median maximum drawdown (28.62%) <= 20% -> FAIL
6. At least 1/2 markets beat always-long Sharpe (1/2: BTC beats, ETH fails) -> PASS
7. All metrics are finite -> PASS
8. Manifest/runtime digests match -> PASS

## Final Classification
`CRYPTO TREND DEVELOPMENT SCREEN FAILS`

## Scope Limitation
The frozen BTCUSDT/ETHUSDT trend configuration failed the Phase 4D development screen because median maximum drawdown was 28.62%, above the 20% threshold. It is not eligible for promotion or production. This does not establish failure across all cryptocurrencies, trend configurations or cross-asset markets.
