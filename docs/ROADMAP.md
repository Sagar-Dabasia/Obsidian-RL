# Roadmap

- [x] Audit legacy system (docs/AUDIT.md)
- [x] P0 Security + foundation: .env untracked, .gitignore fixed, pyproject, tooling, legacy/ quarantined
- [x] P1 Market-product ADR (USD-M perp BTCUSDT vs spot) — verify Binance docs
- [ ] P2 Historical data layer: Parquet, validation, incremental update, CLI
- [ ] P3 Portfolio engine + cost model + SQLite ledger + hand-calculated tests
- [ ] P4 Causal feature/label pipeline, versioned schema, parity tests
- [ ] P5 Deterministic baselines (flat, buy&hold, threshold, regime momentum, cooldown)
- [ ] P6 Gymnasium environment + reward components + trajectory tests
- [ ] P7 PPO (SB3, MLP, discrete-5) + GPU detection + CPU smoke training
- [ ] P8 Walk-forward evaluation, multi-seed, cost/delay sensitivity, holdout
- [ ] P9 Optional LightGBM Alpha Gate (corrected labels) + ablation
- [ ] P10 Live paper trader (frozen policy, websocket finalized candles, replay parity)
- [ ] P11 Session-aware dashboard on ledger
- [ ] P12 Champion/challenger retraining + promotion/rollback
- [ ] External (user): revoke pushed Binance key; optional history rewrite decision
