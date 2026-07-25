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
        from obsidian_rl.evaluation.trend_backtest import parse_and_validate_manifest
        with open(args.manifest, "r") as f:
            manifest_data = json.load(f)

        try:
            manifest_digest, end_ts = parse_and_validate_manifest(
                manifest_data, args.asset_class, args.venue, args.symbol, args.timeframe
            )
        except ValueError as e:
            print(str(e))
            sys.exit(1)

        # We also need row_count and start_timestamp_utc for runtime validation
        c = [comp for comp in manifest_data["components"]
             if comp.get("asset_class") == args.asset_class
             and comp.get("venue") == args.venue
             and comp.get("symbol") == args.symbol
             and comp.get("timeframe") == args.timeframe][0]
        start_ts = c.get("start_timestamp_utc")

        if args.start_ms is not None and args.start_ms != start_ts:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)
        if args.end_ms is not None and args.end_ms != end_ts:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)

        args.start_ms = start_ts
        args.end_ms = end_ts
        manifest_component = c

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

        # Check runtime first/last timestamps differ
        # Using tf.value_ms() logic to compute expected last bar boundary
        expected_interval = (tf.value_ms() if hasattr(tf, "value_ms") else 14400000)

        if bars[0].timestamp_utc != manifest_component.get("start_timestamp_utc"):
            print("Error: runtime first/last timestamps different from manifest")
            sys.exit(1)
        if bars[-1].timestamp_utc + expected_interval != manifest_component.get("end_timestamp_utc"):
            print("Error: runtime first/last timestamps different from manifest")
            sys.exit(1)

    print(f"Loaded {len(bars)} bars from local storage.")

    import hashlib
    h = hashlib.sha256()
    for b in bars:
        h.update(b.row_hash.encode("utf-8"))
    computed_digest = h.hexdigest()
    digest_match = (manifest_digest == computed_digest) if manifest_digest else False

    if args.manifest:
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

    from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy

    if "SPOT" in args.venue:
        market_model = MarketModel.SPOT
        exposure_policy = ExposurePolicy.LONG_FLAT
    elif asset == AssetClass.FOREX:
        market_model = MarketModel.FOREX_MARGIN
        exposure_policy = ExposurePolicy.BIDIRECTIONAL
    else:
        market_model = MarketModel.PERPETUAL
        exposure_policy = ExposurePolicy.BIDIRECTIONAL

    try:
        report = run_trend_backtest(
            tuple(bars),
            config,
            cost_model,
            outage_registry=registry,
            eval_start_ms=eval_start_ms,
            market_model=market_model,
            exposure_policy=exposure_policy,
            manifest_digest=manifest_digest
        )
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

    first_nonzero_signal_ts = report.strategy.first_decision_ts
    first_exec_ts = report.strategy.first_exec_ts
    first_exec_price = report.strategy.first_exec_price
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
    print(f"First Exec TS: {first_exec_ts}")
    print(f"First Exec Price: {first_exec_price}")
    print(f"Liq TS: {report.strategy.liq_ts}")
    print(f"Liq Price: {report.strategy.liq_price}")
    print(f"Turnover: {turnover:.4f}")
    print(f"Weekend Gaps Accepted: {weekend_gaps}")
    print(f"Outages Accepted: {outages_accepted}")

    _print_result("Strategy", report.strategy)
    _print_result("Baseline Flat", report.baseline_flat)
    _print_result("Baseline Long", report.baseline_long)

if __name__ == "__main__":
    main()
