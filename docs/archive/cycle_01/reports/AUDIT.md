# Legacy audit (2026-07-19, commit 8c5cec9)

## Confirmed facts
- Legacy: tabular Q-learning (3 actions), yfinance data (relative windows, tz discarded),
  Binance Testnet klines in `live_trader.py`/`train_alpha_gate.py`, LightGBM Alpha Gate,
  Streamlit dashboard regex-parsing `live_trades.log`.
- No code places exchange orders. `live_trader.py:358` and `train_alpha_gate.py:58` build
  AUTHENTICATED clients (env `BINANCE_API_KEY`/`BINANCE_API_SECRET`) but call only public
  kline endpoints — over-privileged.
- `.env` was committed in 8c5cec9 and pushed to `origin/main` → **credentials compromised**.
- Environment: Windows 11, Python 3.11.4 (.venv), git 2.45.1, RTX 4060 Laptop 8 GB
  (driver 610.74), PyTorch not installed at audit time.

## Critical defects (full details in workflow audit, keyed by file:line)
- Alpha Gate label bug: `High.shift(-1).rolling(4).max()` is trailing → label at t spans
  t-2..t+1 (backward-looking). Both gate trainers affected.
- `alpha_gate.py`: silent synthetic random-walk fallback; silent auto-training at inference;
  duplicate feature schemas (normalized vs absolute-price); no split anywhere.
- Fill-at-observation-price in every env and the live trader; retroactive stop execution.
- `real_market.py`: long-only trailing stop applied to shorts; dead risk params; stale
  position bookkeeping keyed on requested action; no candle validation; tz discarded.
- `ql_agent.py`: EV filter on absolute-dollar vol blocks all exploitation trades; duplicate
  position state; no terminal masking; unseeded exploration; unsafe pickle load.
- `live_trader.py`: `tick_3_dir` always 0 (train/live skew); no idempotency; no restart
  recovery; local-clock finality check; unfinalized-candle fallback; 1-BTC fixed sizing.
- `evaluate.py`: "out-of-sample" label on in-sample runtime-fetched data; reward-vs-dollar
  unit mismatch against a costless buy&hold.
- `dashboard.py`: splices restarted sessions into one equity curve; double-counts TxCost;
  fabricates initial balance; regex truncates timestamps to date.
- UTF-16 `.gitignore` unparseable by git → `.pyc`/`.pkl`/logs/PNGs were tracked.

## Reusable
- Indicator math (RSI/SMA/MACD/ATR) after Wilder-smoothing fix; candle-boundary scheduler
  concept; closed-candle filter idea (rebased on event flag); Streamlit layout; discrete
  state encoding as reference for a documented Q-learning baseline (optional).

## Deprecated (kept in `legacy/`, do not import in new code)
All of `legacy/*.py`. Legacy artifacts (`*.pkl`, logs, PNGs) untracked; provenance
unverifiable → never loaded by the new system.

## Required external action (user)
Revoke/rotate the Binance API key that was in the committed `.env` (pushed to GitHub).
History rewriting (e.g. `git filter-repo` on .env) is documented as an option but NOT
executed — it rewrites shared history and requires a force-push decision by the owner.
