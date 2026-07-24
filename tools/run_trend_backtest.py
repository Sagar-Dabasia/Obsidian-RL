"""CLI to run a point-in-time trend backtest against local SQLite storage."""

import argparse
import sys
import json

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.outages import default_registry
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.evaluation.trend_backtest import TrendBacktestResult, run_trend_backtest, _hash_dataset
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.signals.trend import TrendConfig
from obsidian_rl.data.quality import is_forex_weekend_gap

def _print_result(name: str, res: TrendBacktestResult) -> None:
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
    parser.add_argument("--start-ms", type=int, help="Start UTC ms")
    parser.add_argument("--end-ms", type=int, help="End UTC ms")
    parser.add_argument("--eval-start-ms", type=int, help="Eval start UTC ms")
    parser.add_argument("--observed-before-ms", type=int, help="Point-in-time cutoff")
    parser.add_argument("--manifest", type=str, help="Path to manifest for digest validation")

    parser.add_argument("--taker-fee", type=float, required=True, help="Taker fee (e.g. 0.001 for 10bps)")
    parser.add_argument("--half-spread", type=float, required=True, help="Half spread")
    parser.add_argument("--slippage", type=float, required=True, help="Slippage model factor")
    parser.add_argument("--outage-aware", action="store_true", help="Use default outage registry")

    args = parser.parse_args()

    manifest_component = None
    manifest_digest = None
    if args.manifest:
        import re as re_mod
        with open(args.manifest, "r") as f:
            manifest_data = json.load(f)
        components = manifest_data.get("components", [])
        
        # 1. Require exactly one manifest component matching: (asset_class, venue, symbol, timeframe)
        matching_components = [
            c for c in components
            if c.get("asset_class") == args.asset_class 
            and c.get("venue") == args.venue 
            and c.get("symbol") == args.symbol 
            and c.get("timeframe") == args.timeframe
        ]
        if len(matching_components) != 1:
            print("Manifest component missing or ambiguous")
            sys.exit(1)
            
        manifest_component = matching_components[0]
        
        # 2. Strict start/end MS check
        if manifest_component.get("start_timestamp_utc") != args.start_ms or manifest_component.get("end_timestamp_utc") != args.end_ms:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)
            
        manifest_digest = manifest_component.get("digest")
        if not manifest_digest or not re_mod.match(r"^[0-9a-f]{64}$", manifest_digest):
            print("Error: Manifest digest is malformed")
            sys.exit(1)


        if args.start_ms is not None and args.start_ms != manifest_component["start_timestamp_utc"]:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)
        if args.end_ms is not None and args.end_ms != manifest_component["end_timestamp_utc"]:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)
        args.start_ms = manifest_component["start_timestamp_utc"]

        args.end_ms = manifest_component["end_timestamp_utc"]
        manifest_digest = manifest_component.get("digest")

    if args.start_ms is None or args.end_ms is None:
        print("Error: Must provide --start-ms and --end-ms if no manifest provided.")
        sys.exit(1)

    eval_start_ms = args.eval_start_ms if args.eval_start_ms else args.start_ms

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

    if args.manifest and manifest_component:
        if len(bars) != manifest_component.get("row_count"):
            print("Row count differs from manifest")
            sys.exit(1)

    print(f"Loaded {len(bars)} bars from local storage.")

    import hashlib
    h = hashlib.sha256()
    for b in bars:
        h.update(b.row_hash.encode('utf-8'))
    computed_digest = h.hexdigest()
    digest_match = (manifest_digest == computed_digest) if manifest_digest else False

    if args.manifest:
        if not manifest_digest or len(manifest_digest) != 64:
            print("Manifest digest is malformed")
            sys.exit(1)
        if not digest_match:
            print("Computed digest differs from manifest")
            sys.exit(1)
        print("Digest matched successfully.")

    cost_model = CostModel(
        taker_fee=args.taker_fee,
        half_spread=args.half_spread,
        slippage=args.slippage,
    )
    config = TrendConfig()
    registry = default_registry() if args.outage_aware else None

    try:
        report = run_trend_backtest(tuple(bars), config, cost_model, outage_registry=registry, eval_start_ms=eval_start_ms)
    except Exception as e:
        print(f"Backtest failed: {e}")
        sys.exit(1)

    print("Backtest completed.\n")

    queried_row_count = len(bars)
    warmup_bars = [b for b in bars if b.timestamp_utc < eval_start_ms]
    eval_bars = [b for b in bars if b.timestamp_utc >= eval_start_ms]
    first_loaded_ts = bars[0].timestamp_utc if bars else None
    last_loaded_ts = bars[-1].timestamp_utc if bars else None
    first_eval_ts = eval_bars[0].timestamp_utc if eval_bars else None

    from obsidian_rl.signals.trend import calculate_trend_signal
    first_nonzero_signal_ts = None
    current_bars = warmup_bars.copy()
    for b in eval_bars:
        try:
            sig = calculate_trend_signal(tuple(current_bars), b.timestamp_utc, config)
            if sig.direction != "FLAT" and first_nonzero_signal_ts is None:
                first_nonzero_signal_ts = b.timestamp_utc
                break
        except:
            pass
        current_bars.append(b)

    first_exec_ts = None
    first_exec_price = None
    turnover = report.strategy.turnover

    outages_accepted = 0
    weekend_gaps = 0
    expected_interval = (tf.value_ms() if hasattr(tf, "value_ms") else 14400000)
    for i in range(1, len(bars)):
        diff = bars[i].timestamp_utc - bars[i - 1].timestamp_utc
        if diff > expected_interval:
            if "OANDA" in args.venue and is_forex_weekend_gap(bars[i-1].timestamp_utc, bars[i].timestamp_utc):
                weekend_gaps += 1
            elif registry and registry.covers_gap(args.venue, bars[i-1].timestamp_utc + expected_interval, bars[i].timestamp_utc):
                outages_accepted += 1

    print("\n\n--- AUDIT DATA ---")
    print(f"Manifest Digest: {manifest_digest}")
    print(f"Computed Digest: {computed_digest}")
    print(f"Digest Match: {digest_match}")
    print(f"Queried Row Count: {queried_row_count}")
    print(f"Warm-up Row Count: {len(warmup_bars)}")
    print(f"Evaluation Row Count: {len(eval_bars)}")
    print(f"First Loaded TS: {first_loaded_ts}")
    print(f"Last Loaded TS: {last_loaded_ts}")
    print(f"First Eval TS: {first_eval_ts}")
    print(f"First Nonzero Signal TS: {first_nonzero_signal_ts}")
    print(f"Turnover: {turnover:.4f}")
    print(f"Weekend Gaps Accepted: {weekend_gaps}")
    print(f"Outages Accepted: {outages_accepted}")

    _print_result("Strategy", report.strategy)
    _print_result("Baseline Flat", report.baseline_flat)
    _print_result("Baseline Long", report.baseline_long)

if __name__ == "__main__":
    main()
