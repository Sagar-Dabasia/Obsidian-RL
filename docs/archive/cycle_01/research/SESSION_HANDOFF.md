# Session handoff

Updated: 2026-07-20 · Branch: `rebuild/deep-rl-platform` (never pushed)

## State: rebuild COMPLETE (all phases 0-12) + adversarial review pass
- 146 tests green; ruff/mypy/compileall clean. Results: ../reports/VALIDATION_REPORT.md.
- Multi-agent correctness review done (../reports/REVIEW.md): 6 confirmed defects fixed with
  regression tests (funding drop, gap-index, store conflict, CRITICAL carried-pending
  loss on backfill, double-rollback, no-trade-band close).
- Data: 2020-01-01→2026-07-19 BTCUSDT 15m in data/ (local, gitignored); update via
  `python -m obsidian_rl.cli data-update`.
- Champion: `ppo-20260719-200553-seed42` (models/CHAMPION.json; rollback available).
- Honest verdict: walk-forward shows NO repeatable net edge (PPO ~break-even, momentum
  baselines deeply negative after costs). Single holdout run of the champion: +33.5%
  vs buy&hold −39.1% — one realization, not evidence of an edge.

## Blocking external action
- Revoke the Binance API key committed+pushed in 8c5cec9 (see ../reports/AUDIT.md).

## Key commands (run with .venv\Scripts\python.exe -m obsidian_rl.cli ...)
data-download/-update/-validate/-summary · gpu-check · train [--smoke] ·
walk-forward · holdout · replay · paper-trade · candidate-eval · promote · rollback
Dashboard: `.venv\Scripts\python.exe -m streamlit run src/obsidian_rl/dashboard/app.py`

## Known limitations / next steps
- Live paper loop does not yet apply funding in real time (backtests do when supplied).
- Live-paper long-run soak not yet performed (WS connectivity + replay parity verified).
- legacy/ still present (deprecated, never imported); remove after sign-off.
