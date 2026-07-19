# ADR-003: Market product — Binance USDⓈ-M perpetual BTCUSDT (2026-07-19)

**Decision: Design 1 — USD-M perpetual BTCUSDT market data with paper-only long/short
execution.** Spot rejected: ordinary spot cannot express naked short target exposures
{-1.0, -0.5}; restricting to long/flat would change the research question. Testnet data
rejected: prices/liquidity diverge from production (legacy defect). All endpoints below
are public; **no credentials, no orders, ever**.

| Item | Decision |
|---|---|
| Product | Binance USDⓈ-M perpetual futures |
| Symbol | BTCUSDT |
| Interval | 15m klines |
| Timestamps | UTC; epoch **milliseconds** from API; canonical key = kline **open time**; close time = open+899999 ms |
| Price type | Last-traded OHLCV klines (execution & features). Mark price NOT used initially (no liquidation modeling at ≤1x). Funding from funding-rate history |
| Quantity | Signed BTC quantity; notional = qty × price (USDT). Target exposure = position notional / net equity |
| Leverage | Default cap \|exposure\| ≤ 1.0 (no leverage); configurable; margin checks required before any cap > 1 |
| Funding | Applied at funding timestamps: cash −= rate × position notional (sign-aware); rates from `/fapi/v1/fundingRate` |
| REST klines | `GET https://fapi.binance.com/fapi/v1/klines` — public, `limit` ≤ 1500, weight 1/2/5/10 by limit; 12-field arrays (openTime, O, H, L, C, vol, closeTime, quoteVol, trades, takerBase, takerQuote, ignore) |
| Bulk history | `https://data.binance.vision/data/futures/um/{monthly,daily}/klines/BTCUSDT/15m/*.zip` + SHA256 `.CHECKSUM`; same 12-column CSV |
| WebSocket | `wss://fstream.binance.com/market/ws/{symbol}@kline_{interval}` (raw), `/market/stream?streams=...` (combined). Fallback host `wss://stream.binancefuture.com` |
| Finalized-candle event | kline event `k.x == true` ("Is this kline closed?"); only then is the candle model input |
| Data source env | **Production public market data** (fapi/fstream/data.binance.vision). Never authenticated; never Testnet |

Verified 2026-07-19 against developers.binance.com (catalog: core-trading-derivatives-
trading-usd-s-m-futures → rest-api & ws-streams/market) and github.com/binance/binance-
public-data. Kline WS payload fields confirmed: `k.t/T/i/o/h/l/c/v/n/x/q/V/Q`.

Why this matches the action space: discrete target exposures {-1,-0.5,0,+0.5,+1} map
directly to signed perpetual positions; a long→short reversal is close-then-open with
costs on the full traded delta (Phase 3 engine).
