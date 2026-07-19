# Architecture

```
Binance public data (REST + WS)          [no credentials, no orders — ever]
        │
        ▼
data/            immutable raw 15m klines → partitioned Parquet, validated (UTC, gaps,
                 dupes, OHLC sanity, finalized-only), incremental update, dataset summary
        │
        ▼
features/        ONE causal feature pipeline (versioned schema); used identically by
                 training, evaluation, replay, and live-paper inference
        │
        ▼
portfolio/       ONE authoritative engine: cash, signed qty, avg entry, realized/unrealized
                 PnL, equity, fees/spread/slippage/funding, turnover, drawdown, limits.
                 Target-exposure semantics {-1,-.5,0,.5,1}; reversal = close + open.
cost model       shared by training / replay / evaluation / paper / dashboard
        │
        ├── strategies/   deterministic baselines (flat, buy&hold, threshold,
        │                 regime momentum, fixed-hold, cooldown)
        ├── env/          Gymnasium env (obs = features + portfolio state; reward =
        │                 net-equity return − turnover/drawdown/exposure penalties)
        ├── training/     SB3 PPO (MLP, discrete-5), seeds, checkpoints, metadata
        ├── evaluation/   walk-forward folds, purge gaps, multi-seed, cost/delay
        │                 sensitivity, fixed final holdout
        └── live/         frozen policy → finalized WS candles → paper execution;
                          replay mode drives the same code path over recorded candles
        │
        ▼
ledger/          SQLite, session-aware, idempotency keys, every decision + cost component
        │
        ▼
dashboard/       Streamlit over the ledger only (no log parsing); session-scoped equity
```

Execution timing: decision on finalized candle t → execute at open of candle t+1.
Model registry: `models/` (gitignored) with metadata JSON (git commit, data range,
feature schema version, seeds, metrics, checksum); champion/challenger promotion in
`training/promotion.py` via explicit CLI command.
