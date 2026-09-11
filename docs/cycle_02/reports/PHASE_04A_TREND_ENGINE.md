# Phase 04A: Cross-Market Trend Engine V1

## Objective
Implement a deterministic, cross-market (Crypto and Forex) trend engine calculating LONG, SHORT, or FLAT signals based on immutable rules over multiple timeframes and horizons.

## Implementation Details

### Signal Formula
The `TrendEngineV1` strictly evaluates performance across three distinct historical horizons:
- Short: 20 days
- Medium: 60 days
- Long: 120 days

Returns are computed as: `(Latest Close - Past Close) / Past Close`

Directional Rules:
- **LONG**: Only when the returns across *all three* horizons are strictly positive (`> 0`).
- **SHORT**: Only when the returns across *all three* horizons are strictly negative (`< 0`).
- **FLAT**: Any mixed condition or exactly zero return across the horizons.

The trend `score` maps to `1.0` (LONG), `-1.0` (SHORT), and an average of the three horizon return signs (-1, 0, or 1) bounded in `[-1.0, 1.0]` for FLAT.

### Horizon Conversion
Fixed day-to-bar mappings prevent the engine from silently altering the lookup windows if market data is sparse:
- `1d` timeframe = 1 bar per day
- `4h` timeframe = 6 bars per day
For a 120-day horizon, the engine expects exactly 121 (for daily) or 721 (for 4h) contiguous chronologically sorted canonical bars.

### Point-in-Time Protections
- A strict `observed_before_ms` cutoff acts as a temporal barrier.
- Bars are iterated through, and any bar whose `observed_at_utc` timestamp strictly exceeds the cutoff is discarded as future data.
- The signal uses the final included bar's `observed_at_utc` to stamp its output (`signal_timestamp_utc`).

## Tests and Verification
Test suite comprehensively handles edge cases without altering any existing codebase checks.

Tests executed:
- `test_clear_crypto_uptrend_produces_long`
- `test_clear_forex_downtrend_produces_short`
- `test_mixed_horizons_produce_flat`
- `test_exactly_zero_return_produces_flat`
- `test_insufficient_history_rejection`
- `test_mixed_symbol_timeframe_rejection`
- `test_duplicate_and_out_of_order_rejection`
- `test_tampered_hash_rejection`
- `test_point_in_time_cutoff_protection`
- `test_deterministic_signal_identity`
- `test_4h_and_daily_horizon_conversion`
- `test_frozen_immutability`
- `test_nan_and_infinity_rejection`

Execution commands return `0` exit codes:
- `pytest tests/signals tests/data -q` -> `0`
- `pytest -q` -> `0`
- `mypy src/obsidian_rl/signals tests/signals` -> `0`
- `ruff check src/obsidian_rl/signals tests/signals` -> `0`

## Compliance Confirmations
- **Paid Resources**: No paid databases, storage or networking APIs utilized.
- **Tuning**: No historical backtesting optimization parameters fitted.
- **Trading**: Zero real or simulated exchange trades executed.
- **Holdout**: OOS holdout files completely untouched.
