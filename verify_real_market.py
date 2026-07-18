"""Verification script for RealMarketEnv data ingestion and state transitions.

Standalone quality assurance test script that instantiates `RealMarketEnv` using
historical market data streamed from `yfinance`, resets the environment, and
executes a 5-step test loop while logging state tuples, prices, rewards, and status flags.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

# Ensure project root is accessible on sys.path for robust module import
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.real_market import RealMarketEnv


def main() -> None:
    """Runs data ingestion and state transition verification for `RealMarketEnv`.

    Instantiates the market environment for BTC-USD, resets the state, and runs
    5 discrete steps using a fixed neutral action (`action=1`), handling any
    initialization or connection errors cleanly.
    """
    print("=== Institutional QA: Verifying RealMarketEnv (BTC-USD) ===")
    try:
        env = RealMarketEnv(ticker="BTC-USD", period="1mo", interval="15m")
        initial_state: tuple[int, int, int, int] = env.reset()
        print(
            f"Data Ingestion Successful | Loaded {len(env.prices)} bars for {env.ticker}"
        )
        print(
            f"INITIAL STATE: {initial_state} | Starting Price: {env.current_price:.4f}"
        )

        for step_idx in range(1, 6):
            next_state, reward, done, _ = env.step(action=1)
            print(
                f"Step {step_idx:2d} | Price: {env.current_price:12.4f} | "
                f"State (t1, t2, t3, pnl_state): {next_state} | "
                f"Reward: {reward:+.4f} | Done: {done}"
            )
    except Exception as exc:
        print(f"[QA Verification Error] Failed during execution: {exc}")


if __name__ == "__main__":
    main()
