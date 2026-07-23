"""CLI to run a point-in-time trend backtest against local SQLite storage.

Example:
    python tools/run_trend_backtest.py \\
      --database data/market_data.sqlite \\
      --asset-class CRYPTO \\
      --venue BINANCE_SPOT \\
      --symbol BTCUSDT \\
      --timeframe 4h \\
      --start-ms 1600000000000 \\
      --end-ms 1700000000000 \\
      --taker-fee 0.001 \\
      --half-spread 0.0005 \\
      --slippage 0.0002
"""

import argparse
import sys

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.evaluation.trend_backtest import TrendBacktestResult, run_trend_backtest
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.signals.trend import TrendConfig


def _print_result(name: str, res: TrendBacktestResult) -> None:
    # res is TrendBacktestResult
    print(f"--- {name} ---")
    print(f"Identity: {res.backtest_identity[:8]}")
    print(f"Return (net): {res.net_return:.2%}")
    print(f"Return (gross): {res.gross_return:.2%}")
    print(f"Max Drawdown: {res.maximum_drawdown:.2%}")
    print(f"Sharpe (Ann.): {res.annualized_sharpe:.2f}")
    print(f"Hit Rate: {res.hit_rate:.2%}")
    print(f"Trades: {res.trade_count}")
    print(f"Total Costs: {res.total_costs:.2f}")
    print(f"Exposure: {res.exposure_percentage:.2%}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Trend Engine Backtest")
    parser.add_argument("--database", required=True, help="SQLite database path")
    parser.add_argument("--asset-class", required=True, choices=[a.value for a in AssetClass])
    parser.add_argument("--venue", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True, choices=[t.value for t in Timeframe])
    parser.add_argument("--start-ms", type=int, required=True, help="Start UTC ms")
    parser.add_argument("--end-ms", type=int, required=True, help="End UTC ms")
    parser.add_argument("--observed-before-ms", type=int, help="Point-in-time cutoff")

    parser.add_argument(
        "--taker-fee", type=float, required=True, help="Taker fee (e.g. 0.001 for 10bps)"
    )
    parser.add_argument("--half-spread", type=float, required=True, help="Half spread")
    parser.add_argument("--slippage", type=float, required=True, help="Slippage model factor")

    args = parser.parse_args()

    # Load data locally without network
    asset = AssetClass(args.asset_class)
    tf = Timeframe(args.timeframe)
    with SQLiteStorage(args.database) as store:
        bars = store.query_market_bars(
            asset_class=asset,
            venue=args.venue,
            symbol=args.symbol,
            timeframe=tf,
            start_timestamp_utc=args.start_ms,
            end_timestamp_utc=args.end_ms,
            observed_before_ms=args.observed_before_ms,
        )

    if not bars:
        print("Error: No bars found matching criteria.")
        sys.exit(1)

    print(f"Loaded {len(bars)} bars from local storage.")

    cost_model = CostModel(
        taker_fee=args.taker_fee,
        half_spread=args.half_spread,
        slippage=args.slippage,
    )
    config = TrendConfig()

    try:
        report = run_trend_backtest(tuple(bars), config, cost_model)
    except Exception as e:
        print(f"Backtest failed: {e}")
        sys.exit(1)

    print("Backtest completed.\n")
    _print_result("Strategy", report.strategy)
    _print_result("Baseline Flat", report.baseline_flat)
    _print_result("Baseline Long", report.baseline_long)


if __name__ == "__main__":
    main()
