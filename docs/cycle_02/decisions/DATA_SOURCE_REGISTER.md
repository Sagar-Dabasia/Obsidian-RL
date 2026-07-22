# Cross-Asset Data Source Register

## Data Source Policy & Governance
All historical and live data ingested into Obsidian-RL Research Cycle 02 must be registered in this document and conform to the canonical data contracts (`MarketBar`, `EventNewsItem`). This register defines primary institutional providers, supplementary public APIs, and strict data-quality governance rules across Forex, Cryptocurrency, Macroeconomics, and Charting layers.

---

## Registered Provider Specifications

### 1. OANDA Practice & Historical API (Primary Forex Provider)
- **Asset Class**: Foreign Exchange (`FOREX`), e.g., `EUR_USD`, `USD_JPY`, `GBP_USD`.
- **Licensing / Usage Notes**: Commercial/Developer API subject to OANDA Practice Account or Live Account terms of service. Practice account data provides parity with live institutional spreads and pricing.
- **Timestamp Behaviour**:
  - `timestamp_utc`: Exact RFC 3339 / UNIX millisecond open time of the candlestick as reported by OANDA servers.
  - `observed_at_utc`: Stamped immediately upon receipt by Python adapter (`time.time() * 1000`).
- **Rate Limits**: Maximum 120 requests per second across all REST endpoints; streaming API limited to 20 concurrent connections per token.
- **Missing-Data Behaviour**:
  - Forex markets close over weekends (Friday 21:00 UTC to Sunday 21:00 UTC). Weekend periods are explicitly marked as `MARKET_CLOSED` and do not trigger missing data alarms.
  - Intraday gaps during open market hours raise `DATA_GAP_DETECTED` events and trigger automatic backfill requests.
- **Revision Behaviour**: Historical OHLCV bars are immutable once finalized at candle close. Real-time incomplete bars (`is_complete == False`) are discarded until marked complete by OANDA.
- **Fallback Policy**: If OANDA REST/streaming APIs experience consecutive timeouts (>5 minutes), the Forex asset class is placed into `DEFAULT_DENY_PAUSE` mode inside the `RiskEngine`.
- **Data-Quality Tests**: Must pass `QualityReport` checks verifying exact 5-decimal place pricing (`pip` integrity), positive volume, zero duplicate timestamps, and zero gaps during active weekday sessions.

---

### 2. Crypto Exchange Public & Auxiliary APIs (Primary Cryptocurrency Provider)
- **Asset Class**: Cryptocurrency (`CRYPTO`), e.g., `BTCUSDT`, `ETHUSDT` (Spot & Perpetual Futures).
- **Licensing / Usage Notes**: Public REST and WebSocket APIs (e.g., Binance, Bybit) utilized under standard public usage guidelines without requiring personal trading credentials for market data.
- **Timestamp Behaviour**:
  - `timestamp_utc`: Candle open timestamp provided by exchange match engine.
  - `observed_at_utc`: Wall-clock receipt timestamp recorded by Python WebSocket/REST listener.
- **Rate Limits**: Enforced via IP weights (e.g., Binance 6000 weight per minute per IP). Adapter implements exponential backoff (`tenacity`) upon receiving `HTTP 429` (Rate Limit Exceeded).
- **Missing-Data Behaviour**: Cryptocurrency markets operate 24/7/365. Any gap exceeding 1 candle interval (e.g., >15 minutes for `15m` timeframe) raises a critical `CRYPTO_DATA_GAP` alarm and blocks new position entries.
- **Auxiliary Endpoints (When Supported)**:
  - **Funding Rates**: Periodic 8-hour perpetual contract funding rates (`/fapi/v1/fundingRate`).
  - **Open Interest (OI)**: Real-time and historical open interest (`/fapi/v1/openInterest`).
  - **Liquidations**: Public liquidation order streams (`/ws/!forceOrder@arr`).
- **Revision Behaviour**: Spot and perpetual candlestick data is immutable once closed. Funding rates and OI snapshots are immutable point-in-time observations (`first_observed_at`).
- **Fallback Policy**: If the primary crypto exchange WebSocket disconnects, the adapter automatically switches to REST polling every 15 seconds while initiating reconnection attempts.
- **Data-Quality Tests**: Must pass `QualityReport` checks verifying non-negative pricing, exact timestamp periodicity, tick size compliance, and volume monotonicity.

---

### 3. Public Research Fallback Provider (e.g., Yahoo Finance / `yfinance`)
- **Asset Class**: Cross-Asset Exploratory Research (`FOREX`, `CRYPTO`, `EQUITY`, `COMMODITY`).
- **Licensing / Usage Notes**: Supplementary public data source utilized strictly for exploratory historical comparisons and cross-checking broader market benchmarks.
- **Strict Execution Prohibition**: Public fallback sources (`Yahoo Finance`) can **never** be used as the primary or sole live/paper execution data feed due to lack of institutional SLA, unverified timestamp precision, and delayed reporting.
- **Timestamp Behaviour**:
  - `timestamp_utc`: Converted from provider daily/hourly timestamps to UTC milliseconds.
  - `observed_at_utc`: Stamped upon batch download completion.
- **Rate Limits**: Unofficial public limits; adapter restricts requests to <200 calls per hour with randomized jitter to prevent IP blocking.
- **Missing-Data Behaviour**: Subject to frequent gaps, unannounced maintenance, and split/dividend adjustments. Gaps are logged but ignored during exploratory backtests.
- **Revision Behaviour**: High probability of retrospective adjustment due to corporate actions or delayed data corrections.
- **Fallback Policy**: If primary providers fail, the system **cannot** failover to Yahoo Finance for execution; execution halts instead.
- **Data-Quality Tests**: Run through standard `QualityReport` validation; discrepancies >0.1% against primary OANDA/Crypto data generate data mismatch warnings.

---

### 4. Official Central Bank & Economic Calendars (Primary Macro Provider)
- **Asset Class**: Macroeconomic & Monetary Policy Events (`MACRO`).
- **Licensing / Usage Notes**: Publicly accessible official government and central bank data releases (e.g., Federal Reserve, European Central Bank, Bank of Japan, US Bureau of Labor Statistics).
- **Timestamp Behaviour**:
  - `original_published_at`: Official scheduled release timestamp (ms UTC).
  - `first_observed_at`: Exact millisecond the release figure is ingested and parsed by the system.
- **Rate Limits**: Subject to public portal limits or intermediary economic calendar API limits (e.g., OANDA Eco Calendar / ForexFactory JSON feeds).
- **Missing-Data Behaviour**: If a scheduled macroeconomic release is delayed or unavailable within 5 minutes of `original_published_at`, `surprise_value` is set to `NaN` and macroeconomic contribution is zeroed out.
- **Revision Behaviour**:
  - Macroeconomic figures are frequently revised months later.
  - Revisions are captured as distinct `EventNewsItem` records stamped with the new `first_observed_at` time (`revision_status == 'REVISED'`).
- **Fallback Policy**: If primary calendar feed fails, macro event contribution to the `MultiEngineCompositeStrategy` defaults to neutral (`0.0`).
- **Data-Quality Tests**: Must pass `EventNewsItem` contract checks: non-empty `event_id`, valid numeric `expected_value` and `actual_value`, and exact `surprise_value` math calculation.

---

### 5. TradingView Webhook & Chart Feed (Visual & Alert Provider)
- **Asset Class**: Multi-Asset Visual Alerts (`TV_ALERT`).
- **Licensing / Usage Notes**: Utilized via TradingView Pro/Premium webhook alerting mechanism running Pine Script indicators (`ObsidianMultiAssetTrend.pine`).
- **Source of Truth Prohibition**: TradingView is strictly a visualization and alert generator. TradingView is **never** the system's quantitative source of truth. All calculations, pricing, and risk checks originate inside Python (`Obsidian-RL Core`).
- **Timestamp Behaviour**:
  - `timestamp_utc`: Time embedded in the Pine Script webhook payload (`timenow`).
  - `observed_at_utc`: Exact wall-clock receipt timestamp stamped by `webhook_receiver.py`.
- **Rate Limits**: TradingView webhook dispatch limits (typically max 100 alerts per minute per account).
- **Missing-Data Behaviour**: Webhook delivery over public internet is unreliable (no guaranteed QoS). Missing alerts do not disrupt system state because Python engines independently evaluate bar data.
- **Revision Behaviour**: Webhook alerts are one-shot immutable events (`event_id` enforced).
- **Fallback Policy**: If TradingView webhooks stop arriving, the Python `MarketTrendEngine` continues generating signals independently from canonical data store updates.
- **Data-Quality Tests**: Must pass HMAC signature verification, timestamp freshness checks (`|observed_at - timestamp| < 60s`), and JSON schema validation.

---

## Data Quality & Validation Summary Matrix

| Provider | Asset Class | Primary Role | Live Execution Allowed? | SLA & Rate Limit | Timestamp Verification | Quality Enforcement |
|---|---|---|---|---|---|---|
| **OANDA Practice/Live** | Forex | Institutional Pricing & Bars | Yes | High SLA (120 req/s) | Strict `observed_at` parity | 100% `QualityReport` checks |
| **Crypto Exchanges** | Crypto | Spot/Perp Bars, Funding, OI | Yes | High SLA (IP Weight limits) | Strict `observed_at` parity | 100% `QualityReport` checks |
| **Yahoo Finance (`yfinance`)** | Multi | Exploratory Research & Benchmarks | **NO (Research Only)** | Low SLA (Unofficial limits) | Batch timestamp check | Discrepancy tracking vs. primary |
| **Central Banks / Gov** | Macro | Economic Calendar & Surprise | Yes (Auxiliary) | Public portal limits | Point-in-time (`first_observed`) | Exact `EventNewsItem` validation |
| **TradingView Webhooks** | Chart/Alert | Visual Alerts & Charting | **NO (Informational)** | Webhook delivery limits | HMAC & 60s freshness check | Replay protection & schema check |
