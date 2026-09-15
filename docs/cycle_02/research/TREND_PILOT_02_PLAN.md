# Trend Pilot 02 Plan: Outage-Aware Cross-Market Trend Pilot

## Pre-Registration

**Date**: 2026-07-23
**Parent branch**: fix/cycle-02-trend-pilot-data-recovery
**Parent commit**: 7e7c158

## Background

Phase 4C-R established that a Binance evaluation-period outage at
`1582113600000` (2020-02-19T12:00:00Z) prevented the crypto historical
datasets from being built. Both BTCUSDT and ETHUSDT had identical gaps at the
same timestamp, suggesting a venue-wide outage rather than a symbol-specific
data issue.

This plan defines a strict outage policy that allows the experiment to proceed
without inventing data.

## Outage Policy

A missing crypto interval is accepted only when ALL of the following are true:

1. The same timestamp is missing across every tested symbol on the venue.
2. The outage is confirmed using an official Binance announcement or official
   Binance public-data archive.
3. The outage interval is recorded in a deterministic outage registry.
4. No synthetic candle is created.
5. No signal or order executes while the venue is unavailable.
6. Existing positions remain unchanged through the outage.
7. Any pending position change executes at the first real tradable bar after
   reopening using that bar's actual execution price.
8. Returns across reopening use real prices only.
9. Any unexplained or symbol-specific gap makes the experiment invalid.

## Previously Observed Evaluation Outage

**Timestamp**: 2020-02-19T12:00:00Z (1582113600000 ms)
**Venue**: BINANCE_SPOT
**Affected symbols**: BTCUSDT, ETHUSDT (venue-wide)

This outage must be independently verified using the Binance public kline
archive before it can be accepted.

## Frozen Parameters

- Symbols: BTCUSDT, ETHUSDT, EUR_USD, GBP_USD
- Historical: 2019-01-01 to 2024-01-01
- Evaluation: 2020-01-01 to 2024-01-01
- Confirmation: 2024-01-01 to 2025-06-30 (untouched)
- Final holdout: 2025-07-01 onward (untouched)
- Trend horizons: 20/60/120 days
- Costs: unchanged from Phase 4C
- Signal rules: unchanged
- Next-bar execution: unchanged
- Pass/fail criteria: unchanged

## Classification Rules (Unchanged)

The experiment will be classified as one of:
- TREND DEVELOPMENT SCREEN PASSES
- TREND DEVELOPMENT SCREEN FAILS
- EXPERIMENT INVALID
