# Phase 04C R3 Plan

## Prerequisites
- provider = DUKASCOPY_JFOREX_HISTORICAL_DATA_MANAGER
- symbols = EURUSD, GBPUSD
- source = local immutable official JForex CSV exports
- timeframe = H4
- BID/ASK both available = True
- raw start = 2019-08-15 00:00:00 UTC
- eval start = 2020-01-01 00:00:00 UTC
- eval end = 2023-12-31 20:00:00 UTC (final valid H4 boundary)
- required warm-up bars = 721
- strategy parameters = Trend Pilot default
- FOREX market model = FOREX_MARGIN
- exposure policy = BIDIRECTIONAL
- NEXT_BAR_OPEN = True

## Costs Methodology
- taker_fee = 0.0 (Forex typically spread only)
- half_spread = 0.00005 (or point-in-time spread if supported, default half spread 0.5 pips)
- slippage = 0.0001 (1 pip slippage)
Because BID+ASK data is available, prefer actual point-in-time spread treatment if existing architecture supports it without changing strategy semantics. Since strategy takes half_spread, we will configure it with half_spread 0.00005 and slippage 0.0001.

## Acceptance Criteria
- Valid statistical metrics
- No leakage

## Dataset Hashes
- EURUSD BID SHA-256: 1138E22CAE9D897C20757039B280C6ECDF5C935527B9040B16692510AF192A88
- EURUSD ASK SHA-256: 8B2CB8DB54E9E55F12E6C9F36AD428413E5DE6995D167966BBB56CE7C8440BE2
- GBPUSD BID SHA-256: CD9C7407F63EECA775969C7611085ACDF6A767F84ED197DBC93D1CDCB5DFE296
- GBPUSD ASK SHA-256: EF04E8C1549EC451AA06979801AD7C42B7193CD59C7CE4C9A0D769E3D5C71DF7
