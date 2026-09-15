# Data AGENTS.md
These rules apply ONLY within src/obsidian_rl/data/.
Root AGENTS.md invariants remain absolute; this file adds domain-specific constraints.

## Real Data Only
- Never synthesize, interpolate, or fabricate market data.
- Missing bars/gaps must be explicitly represented (Outage/NaN), never silently filled.
- Source of truth: Binance/OANDA raw responses -> Parquet storage.

## Provenance & Chronology
- Every dataset row must carry ingestion timestamp and source metadata.
- Fingerprint/hash must match source at rest.
- Chronological ordering is invariant; no future data in historical windows.

## Point-in-Time Causality
- Features/labels computed at timestamp T must use only data available at T.
- No look-ahead in rolling windows, resampling, or alignment.
- Graphify path "data feature" before adding derived columns.

## Explicit Outages/Gaps
- Outage detector output is the contract for missing data.
- Downstream consumers must handle Outage, not assume continuity.
- Never impute funding rates, spreads, or orderbook depth.

## No Synthetic Fallback
- If real data unavailable -> FAIL explicitly.
- No generated candles, no GARCH/volatility models as substitute.
- Paper: "Data gap in window [t1, t2]" is acceptable output.
