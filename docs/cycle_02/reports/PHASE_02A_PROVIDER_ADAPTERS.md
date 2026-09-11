# Cycle 02 Phase 2A: Free Crypto & Forex Provider Adapters Report

**Date:** 2026-07-22  
**Status:** COMPLETE (PASSED VERIFICATION AUDIT)  
**Branch:** `feature/cycle-02-provider-adapters`  
**Schema Version:** `SCHEMA_V2`  
**Adapter Version:** `1.0.0`  

---

## 1. Executive Summary

In accordance with [CYCLE_02_MASTER_PLAN.md](CYCLE_02_MASTER_PLAN.md) and [CROSS_ASSET_ARCHITECTURE.md](../architecture/CROSS_ASSET_ARCHITECTURE.md), Phase 2A delivers the foundational read-only market-data provider adapters for the Obsidian-RL cross-asset platform:
1. **Binance Spot Public Market-Data Adapter (`BinanceSpotProvider`)** for cryptocurrency klines (`AssetClass.CRYPTO`).
2. **OANDA Practice Forex Candle Adapter (`OandaPracticeProvider`)** for foreign exchange klines (`AssetClass.FOREX`).

These adapters provide unified, point-in-time compliant ingestion into our immutable Phase 1 `MarketBar` contract (`SCHEMA_V2`) while strictly enforcing zero paid dependencies, fail-closed error handling, automated secret scrubbing, exponential backoff retries on transient network failures, and absolute look-ahead bias prevention.

**Zero Paid Resources or Network Dependency During Verification:**  
In strict adherence to project governance, all provider adapters are built using only standard Python libraries (`requests`, `math`, `time`, `logging`) and verified using deterministic, offline mock session fixtures (`unittest.mock`). No paid APIs, credentials, or live network calls were used during automated test runs.

---

## 2. Provider Endpoints, Free Tiers & Limitations

### 1. Binance Spot Public API (`BinanceSpotProvider`)
- **Base URL:** `https://data-api.binance.vision` (public market data cluster) or `https://api.binance.com`.
- **Target Endpoint:** `GET /api/v3/klines`
- **Authentication & Free Tier:** Completely public and unauthenticated read-only endpoint. Zero API tokens or keys required.
- **Rate Limits & Constraints:**
  - Raw request weight limit per IP: 6000 weight per minute.
  - Each `/api/v3/klines` query consumes a request weight between 1 and 2 depending on requested `limit` (default `limit=1000`).
  - Returns raw lists of strings/integers: `[openTime, open, high, low, close, volume, closeTime, quoteAssetVolume, numberOfTrades, ...]`.
- **Supported Granularities:** `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d` (mapped exactly to canonical `Timeframe` enums).

### 2. OANDA Practice API (`OandaPracticeProvider`)
- **Base URL:** `https://api-fxpractice.oanda.com` (free practice/demo environment).
- **Target Endpoint:** `GET /v3/instruments/{symbol}/candles`
- **Authentication & Free Tier:** Requires an unexpired Practice account Bearer token passed via HTTP header (`Authorization: Bearer <token>`). Tokens are loaded securely from constructor arguments (`api_token`) or the `OANDA_API_TOKEN` environment variable, never hardcoded or printed.
- **Rate Limits & Constraints:**
  - Practice account rate limits: 120 requests per minute per connection.
  - Query parameters strictly enforce UTC alignment: `dailyAlignment=0` and `alignmentTimezone="UTC"`.
  - Returns structured JSON containing candle objects with midpoint or bid/ask quote depth: `{"candles": [{"complete": true, "time": "...", "volume": ..., "mid": {...}, "bid": {...}, "ask": {...}}]}`.
- **Supported Granularities:** `M1`, `M5`, `M15`, `M30`, `H1`, `H2`, `H4`, `D` (mapped exactly to canonical `Timeframe` enums).

---

## 3. Canonical OHLCV and Volume-Type Handling

Both providers transform raw external payload structures into immutable, SHA-256 fingerprinted `MarketBar` instances (`SCHEMA_V2`) while enforcing precise asset-class semantics:

| Provider | Asset Class | Venue | Quote Status | Bid / Ask | Volume Type | Volume Field |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Binance Spot** | `CRYPTO` | `BINANCE_SPOT` | `UNAVAILABLE` | `None` / `None` | `BASE` | Base asset trading volume (`float >= 0.0`) |
| **OANDA Practice** | `FOREX` | `OANDA_PRACTICE` | `OBSERVED` | `bid.c` / `ask.c` | `TICK` | Number of tick price updates (`float >= 0.0`) |

### Key Contract Invariants & Transformations
1. **Point-in-Time Discipline (`observed_at_utc` vs. `timestamp_utc`):**
   - **Binance:** `timestamp_utc = int(openTime)` (bar start time in UTC milliseconds). To prevent look-ahead leakage, `observed_at_utc = int(closeTime) + 1` (the exact millisecond the candle completed). If `observed_at_utc > current_time_ms`, the bar is rejected as an incomplete forming candle.
   - **OANDA:** `timestamp_utc` is parsed from RFC3339 `time` strings (`YYYY-MM-DDTHH:MM:SS.nnnnnnnnnZ`) converted to UTC milliseconds. `observed_at_utc` is calculated exactly as `timestamp_utc + _TIMEFRAME_MS[timeframe]` (bar completion timestamp). If `complete == False` or `observed_at_utc > current_time_ms`, the candle is skipped.
2. **Numeric Safety & Quote Integrity:**
   - All price and volume strings are converted to `float` and checked with `math.isfinite()`. `NaN`, `Infinity`, or boolean substitutions immediately trigger `MalformedResponseError`.
   - For OANDA (`QuoteStatus.OBSERVED`), midpoint OHLC values (`mid.o`, `mid.h`, `mid.l`, `mid.c`) define the primary bar prices, while `bid = float(bid.c)` and `ask = float(ask.c)` capture closing quote depth. If `ask < bid`, `MalformedResponseError("Crossed bid/ask quotes detected...")` is raised immediately.

---

## 4. Error Hierarchy, Retry & Rate-Limit Handling Rules

To guarantee that provider failures fail closed and never corrupt backtesting or live ingestion pipelines, Phase 2A introduces a unified, typed exception hierarchy in `src/obsidian_rl/data/providers/errors.py`:

```
ProviderError (Base Exception with automated secret scrubbing)
 ├── AuthenticationError (HTTP 401/403 or missing required credentials)
 ├── RateLimitError (HTTP 429 exhaustion after respecting Retry-After backoff)
 ├── MalformedResponseError (HTTP 4xx client errors, schema mismatches, non-finite values, crossed quotes)
 ├── UnsupportedSymbolTimeframeError (HTTP 400 invalid symbols or unmapped intervals)
 └── TransportError (Network timeouts, connection drops, or HTTP 5xx server errors after retry exhaustion)
```

### Exact Retry and Backoff Policy (`BaseRestProvider._request`)
1. **Exponential Backoff on Transport & Server Errors (HTTP 5xx / Connection Drops):**
   - Retries automatically up to `max_retries` times (default `max_retries=3`).
   - Sleep delay follows exponential backoff: `min(2.0 ** attempt, 30.0)` seconds.
   - If exhaustion is reached without recovery, raises `TransportError`.
2. **Rate Limit Enforcement (HTTP 429):**
   - If HTTP 429 is received, the adapter parses the `Retry-After` response header (in seconds).
   - Sleep delay is set to `max(retry_after, 2.0 ** (attempt + 1))` seconds.
   - Retries up to `max_retries` times before raising `RateLimitError`.
3. **Fail-Closed on Permanent Client Errors (HTTP 4xx - No Retry):**
   - HTTP `401 / 403` immediately raises `AuthenticationError`.
   - HTTP `400` (or unmapped granularities) immediately raises `UnsupportedSymbolTimeframeError`.
   - HTTP `404 / 422` immediately raises `MalformedResponseError`.
   - **No retries occur on permanent 4xx errors**, preventing infinite loops or rate-limit penalties.

---

## 5. Secret Scrubbing & Credential Safety

To prevent accidental credential leaks across logging pipelines, error tracking services, or terminal outputs, all provider infrastructure integrates rigorous scrubbing:
- **`scrub_secrets(message, secrets)` Utility:** Automatically scans string outputs and replaces exact token occurrences (`self._api_token`) and any generic `Authorization: Bearer <secret>` / `api_token=<secret>` patterns with `"Authorization: Bearer [REDACTED]"` or `"[REDACTED]"`.
- **Exception & Logging Redaction:** `ProviderError.__init__` stores internal secrets and overrides `__str__` and `__repr__` so that formatted traceback strings and custom messages are sanitized automatically before reaching upper layers.

---

## 6. Verification Results & Regression Audit

The Phase 2A implementation underwent comprehensive static analysis, formatting checks, targeted mock provider testing, and full project regression testing:

### 1. Static Analysis & Code Quality
- **`compileall -q src tests`**: Passed with zero compilation errors.
- **`mypy src/obsidian_rl/data tests/data`**: Passed cleanly across 20 source modules with strict typing.
- **`ruff check src/obsidian_rl/data tests/data`**: All lint rules passed cleanly (`0 errors`).
- **`ruff format --check src/obsidian_rl/data tests/data`**: All 20 source and test files exactly formatted according to project standards.

### 2. Targeted Provider Unit Tests (`pytest tests/data/providers tests/data -q`)
- **`test_base.py` (6 tests):** Verifies exponential backoff retries on transport/5xx, `Retry-After` handling on 429, zero-retry behavior on permanent 4xx errors, complete secret scrubbing in exception strings and logs, exact start-inclusive/end-exclusive boundary filtering (`[start_ms, end_ms)`), deduplication, and chronological sorting.
- **`test_binance.py` (4 tests):** Verifies exact OHLC conversion (`AssetClass.CRYPTO`, `QuoteStatus.UNAVAILABLE`, `VolumeType.BASE`), 1000-candle multi-page pagination cursor advancement (`startTime = last_open_time + 1`), forming/incomplete candle rejection (`closeTime + 1 > current_time_ms`), exact interval mapping, and fail-closed rejection of non-finite prices or malformed rows.
- **`test_oanda.py` (5 tests):** Verifies exact midpoint OHLC (`mid`), closing quote depth (`bid`/`ask`), `VolumeType.TICK`, daily UTC alignment query params (`dailyAlignment=0`, `alignmentTimezone="UTC"`), environment and constructor token loading, missing token rejection, secret scrubbing, crossed quote (`ask < bid`) rejection, forming/incomplete candle skipping, and granularity mapping.
- **Summary:** `36 passed in 0.28s (100% pass rate without network access)`.

### 3. Full Project Regression Suite (`pytest -q`)
- **Summary:** `454 passed, 1 skipped in 10.42s (100% pass rate)`.
- **Phase 1 Contract Verification:** All existing Phase 1 canonical SHA-256 digests (`compute_market_bar_hash`) and structural invariants (`__post_init__` / `validate_ingestion_time`) remain 100% satisfied and deterministic across all regression tests without external network dependencies.
