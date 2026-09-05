import argparse
import sys
import json
import math

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.outages import default_registry
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.evaluation.trend_backtest import TrendBacktestResult, run_trend_backtest
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.signals.trend import TrendConfig
from obsidian_rl.data.historical_dataset import verify_and_digest_continuous_bars
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine

def _get_exec_price(asset_class: AssetClass, bar, current_exp: float, target_exp: float) -> float:
    return bar.open

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--asset-class", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--eval-start-ms", type=int, required=True)
    parser.add_argument("--manifest", type=str)
    parser.add_argument("--taker-fee", type=float, default=0.0)
    parser.add_argument("--half-spread", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--outage-aware", action="store_true")
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    ac = AssetClass(args.asset_class)
    
    with SQLiteStorage(args.database) as storage:
        bars = storage.query_market_bars(
            asset_class=ac,
            venue=args.venue,
            symbol=args.symbol,
            timeframe=tf,
            start_timestamp_utc=args.start_ms,
            end_timestamp_utc=args.end_ms,
        )
    
    if not bars:
        print("No bars")
        return

    # Basic stats
    queried_row_count = len(bars)
    warmup_bars = [b for b in bars if b.timestamp_utc < args.eval_start_ms]
    eval_bars = [b for b in bars if b.timestamp_utc >= args.eval_start_ms]
    first_loaded = bars[0].timestamp_utc
    last_loaded = bars[-1].timestamp_utc
    first_eval = eval_bars[0].timestamp_utc if eval_bars else None

    # Run backtest to get metrics
    config = TrendConfig()
    cost_model = CostModel(args.taker_fee, args.half_spread, args.slippage)
    registry = default_registry() if args.outage_aware else None

    report = run_trend_backtest(tuple(bars), config, cost_model, registry, eval_start_ms=args.eval_start_ms)
    
    # We need to manually simulate the first part to get first signal/exec
    from obsidian_rl.signals.trend import calculate_trend_signal

    first_nonzero_signal_ts = None
    first_exec_ts = None
    first_exec_price = None

    engine = PortfolioEngine(PortfolioConfig(10000.0, 1.0, True), cost_model)
    target_exp = 0.0
    
    current_bars = list(warmup_bars)
    
    for b in eval_bars:
        curr_exp = engine.state.exposure(b.open)
        if target_exp != curr_exp:
            exec_px = b.open
            engine.rebalance(target_exp, exec_px)
            if first_exec_ts is None:
                first_exec_ts = b.timestamp_utc
                first_exec_price = exec_px
                    
        engine.mark_to_market(b.close)
        current_bars.append(b)
        
        try:
            sig = calculate_trend_signal(tuple(current_bars), b.timestamp_utc, config)
            if sig.direction == "LONG":
                target_exp = 1.0
            elif sig.direction == "SHORT":
                target_exp = -1.0
            else:
                target_exp = 0.0
                
            if sig.direction != "FLAT" and first_nonzero_signal_ts is None:
                first_nonzero_signal_ts = b.timestamp_utc
        except Exception as e:
            print(e)
            target_exp = 0.0

    # Compute digest
    manifest_comp = None
    if args.manifest:
        with open(args.manifest, 'r') as f:
            man = json.load(f)
        for c in man.get("components", []):
            if c["symbol"] == args.symbol:
                manifest_comp = c
                break
                
    computed_digest = verify_and_digest_continuous_bars(bars, args.eval_start_ms, tf, args.venue, registry, min_warmup_bars=config.long_horizon_days)
    man_digest = manifest_comp["digest"] if manifest_comp else None
    
    outages = 0
    interval = tf.value_ms() if hasattr(tf, "value_ms") else 14400000
    for i in range(1, len(bars)):
        diff = bars[i].timestamp_utc - bars[i-1].timestamp_utc
        if diff > interval:
            if registry and registry.covers_gap(args.venue, bars[i-1].timestamp_utc + interval, bars[i].timestamp_utc):
                outages += 1

    print("=== AUDIT RESULTS ===")
    print(f"manifest component digest: {man_digest}")
    print(f"recomputed runtime digest: {computed_digest}")
    print(f"exact queried row count: {queried_row_count}")
    print(f"warm-up row count: {len(warmup_bars)}")
    print(f"evaluation row count: {len(eval_bars)}")
    print(f"first loaded timestamp: {first_loaded}")
    print(f"last loaded timestamp: {last_loaded}")
    print(f"first evaluation timestamp: {first_eval}")
    print(f"first nonzero signal timestamp: {first_nonzero_signal_ts}")
    print(f"first execution timestamp: {first_exec_ts}")
    print(f"first execution price: {first_exec_price}")
    print(f"gross return: {report.strategy.gross_return:.2%}")
    print(f"net return: {report.strategy.net_return:.2%}")
    print(f"Sharpe: {report.strategy.annualized_sharpe:.2f}")
    print(f"max drawdown: {report.strategy.maximum_drawdown:.2%}")
    print(f"turnover: {report.strategy.turnover:.4f}")
    print(f"exposure: {report.strategy.exposure_percentage:.2%}")
    print(f"trades: {report.strategy.trade_count}")
    print(f"total costs: {report.strategy.total_costs:.2f}")
    print(f"always-long return: {report.baseline_long.net_return:.2%}")
    print(f"always-long Sharpe: {report.baseline_long.annualized_sharpe:.2f}")
    print(f"outages accepted: {outages}")
    print(f"digest match: {str(man_digest == computed_digest).upper()}")

if __name__ == "__main__":
    main()
