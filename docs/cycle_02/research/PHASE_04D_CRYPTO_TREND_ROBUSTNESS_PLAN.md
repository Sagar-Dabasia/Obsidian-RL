# Phase 4D Crypto Trend Robustness Plan

## Objective and Hypothesis
This phase defines a crypto-only evaluation of the core trend strategy. 
The new hypothesis is:
> “Does the fixed trend strategy generalize across independently selected, provenance-valid cryptocurrency markets?”

Do not reuse Phase 4C Forex metrics in the new screen.

## Provenance Rules for Candidate Markets
Candidate crypto markets must be selected using strict preregistered provenance rules before any strategy results are observed:
* Supported by the registered provider.
* Sufficient chronological development history.
* Complete reproducible manifest.
* Valid runtime digest.
* No unsupported gaps.
* Adequate liquidity/data coverage.
* No synthetic data.
* No selection using historical strategy returns.

## Frozen Two-Market Protocol

Markets:
* BTCUSDT / BINANCE_SPOT / 4h
* ETHUSDT / BINANCE_SPOT / 4h

Manifest components:
* BTC start: `1565856000000`
* BTC rows: `9597`
* BTC digest: `0a70bdb71bcafeb5837485037c663a775b625263d8df2b1c8000e807c87b3bd3`
* ETH start: `1565856000000`
* ETH rows: `9597`
* ETH digest: `7b86b57f2e34fc0b1b17f3f83561e5ecdb976460433acf951b5f05bb4ca42652`

Evaluation:
* Eval start: `1577836800000`
* End exclusive: `1704067200000`
* 20/60/120-day trend configuration
* next-bar-open execution
* no tuning
* no synthetic data
* no Forex
* confirmation and final holdout untouched

Frozen crypto costs:
```text
--taker-fee 0.0005
--half-spread 0.00005
--slippage 0.0001
--outage-aware
```

## Frozen Two-Market Screen
1. Both markets have positive net return: 2/2.
2. Median net return > 0.
3. Median annualized Sharpe > 0.50.
4. Worst net return > -10%.
5. Median maximum drawdown <= 20%.
6. At least 1/2 markets beat always-long Sharpe.
7. All metrics are finite.
8. Manifest/runtime digests match and no timing or reserved-data violation occurs.

**Explicit Limitation:**
Passing this screen supports only bounded BTC/ETH development evidence. It does not establish broad crypto or cross-asset generalization.

## Future Forex Data-Acquisition Protocol
To eventually restore multi-asset capabilities, Forex data must undergo a rigorous, independent future acquisition protocol. Do not mix providers or attempt Forex ingestion without formally executing this protocol:
* Fresh, automated provider download.
* Complete raw request/response payload preservation.
* Endpoint, parameters, HTTP status, and pagination fully recorded.
* Exact retrieval timestamp and SHA-256 hash stored for every raw artifact.
* Generation of unique immutable manifests linking the downloaded payload hashes.
* Authenticated external gap evidence explicitly linked and hashed in the `OutageRegistry`.
