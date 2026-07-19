# Roadmap

- [x] Audit legacy system (docs/AUDIT.md)
- [x] P0 Security + foundation: .env untracked, .gitignore fixed, pyproject, tooling, legacy/ quarantined
- [x] P1 Market-product ADR (USD-M perp BTCUSDT) — docs/adr/ADR-003
- [x] P2 Historical data layer: 229,583 candles 2020→2026, 0 gaps, validated
- [x] P3 Portfolio engine + cost model + SQLite ledger (28 hand-calculated tests)
- [x] P4 Causal feature/label pipeline fs-v1, parity tests
- [x] P5 Deterministic baselines + shared backtest runner
- [x] P6 Gymnasium environment (check_env, trajectory tests)
- [x] P7 PPO (SB3 MLP, discrete-5) + GPU detection + smoke training
- [x] P8 Walk-forward: 5 folds × 3 seeds + cost/delay sensitivity → docs/VALIDATION_REPORT.md
- [x] P9 Alpha Gate: implemented, ablated, NOT retained (ADR-005)
- [x] P10 Live paper trader: replay/live parity, restart recovery, WS verified
- [x] P11 Session-aware dashboard on ledger (queries tested)
- [x] P12 Promotion: champion `ppo-20260719-200553-seed42`, rollback tested
- [ ] External (user): revoke the Binance API key pushed in commit 8c5cec9
- [ ] Future: real-time funding application in the live paper loop
- [ ] Future: longer PPO budgets / more seeds; legacy/ removal after sign-off
