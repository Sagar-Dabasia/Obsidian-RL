# Obsidian-RL

Experimental deep-Reinforcement-Learning research platform for cryptocurrency markets.

**This is research software. It does not guarantee profit. It does not provide financial
advice. Nothing here constitutes a recommendation to trade.** All "live" execution is
simulated paper trading against public market data. The system never places exchange
orders and never uses private API credentials.

## What it does

- Trains PPO policies on multi-year historical Binance market data
- Uses realistic portfolio accounting (fees, spread, slippage, funding)
- Evaluates with strict walk-forward temporal validation against deterministic baselines
- Deploys only frozen, validated policies to a live-paper decision loop
- Records every decision in a persistent, session-aware ledger

## What it deliberately does not do

- Place real or Testnet exchange orders
- Train on live data or self-modify a deployed policy
- Claim profitability without repeatable net-of-cost out-of-sample evidence

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[rl,gate,dashboard,dev]
```

See `CLAUDE.md` for the command reference and `docs/` for architecture, decisions,
and validation reports. Historical results are simulated and net-of-assumed-costs;
past simulated performance does not predict future results.
