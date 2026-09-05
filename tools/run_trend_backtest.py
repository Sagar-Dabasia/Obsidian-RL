"""CLI to run a point-in-time trend backtest against local SQLite storage."""

import argparse
import sys

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.outages import default_registry
from obsidian_rl.data.quality import is_forex_weekend_gap
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.evaluation.trend_backtest import (
    TrendBacktestResult,
    run_trend_backtest,
)
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.signals.trend import TrendConfig


def _print_result(name: str, res: TrendBacktestResult) -> None:
    print(f"--- {name} ---")
    print(f"Identity: {res.backtest_identity[:8]}")
    print(f"Return (net): {res.net_return:.2%}")
    print(f"Return (gross): {res.gross_return:.2%}")
    print(f"Max Drawdown: {res.maximum_drawdown:.2%}")
    print(f"Sharpe (Ann.): {res.annualized_sharpe:.2f}")
    print(f"Hit Rate: {res.hit_rate:.2%}")
    print(f"Trades: {res.trade_count}")
    print(f"Total Trading Costs: {res.total_trading_costs:.2f}")
    print(f"Total Funding: {res.total_funding:.2f}")
    print(f"Total Costs (all-in): {res.total_costs:.2f}")
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

    parser.add_argument(
        "--taker-fee", type=float, required=True, help="Taker fee (e.g. 0.001 for 10bps)"
    )
    parser.add_argument("--half-spread", type=float, required=True, help="Half spread")
    parser.add_argument("--slippage", type=float, required=True, help="Slippage model factor")
    parser.add_argument("--outage-aware", action="store_true", help="Use default outage registry")

    parser.add_argument(
        "--market-model", required=True, choices=["SPOT", "PERPETUAL", "FOREX_MARGIN"]
    )
    parser.add_argument("--exposure-policy", required=True, choices=["LONG_FLAT", "BIDIRECTIONAL"])

    args = parser.parse_args()

    if (args.start_ms is None or args.end_ms is None) and not args.manifest:
        print("Error: Must provide --start-ms and --end-ms if no manifest provided.")
        sys.exit(1)

    eval_start_ms = args.eval_start_ms if args.eval_start_ms else args.start_ms

    asset = AssetClass(args.asset_class)
    tf = Timeframe(args.timeframe)
    # Use module-level SQLiteStorage to allow test patching
    import obsidian_rl.data.storage as storage_module
    storage_cls = storage_module.SQLiteStorage
    with storage_cls(args.database) as store:
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

    import hashlib

    h = hashlib.sha256()
    for b in bars:
        h.update(b.row_hash.encode("utf-8"))
    computed_digest = h.hexdigest()

    expected_interval = tf.value_ms() if hasattr(tf, "value_ms") else 14400000

    manifest_digest = None
    digest_match = False
    from obsidian_rl.data.contracts import FundingRate

    funding_rates: tuple[FundingRate, ...] = tuple()
    if args.manifest:
        import json

        from obsidian_rl.data.manifest import load_and_validate_manifest

        try:
            mc = load_and_validate_manifest(
                args.manifest,
                args.asset_class,
                args.venue,
                args.symbol,
                args.timeframe,
                bars[0].timestamp_utc,
                bars[-1].timestamp_utc + expected_interval,
                len(bars),
                computed_digest,
                args.start_ms,
                args.end_ms,
            )
            manifest_digest = mc.digest
            digest_match = True
            print("Digest matched successfully.")

            with open(args.manifest, encoding="utf-8") as f:
                raw_manifest = json.load(f)
            mc_raw = raw_manifest.get("components", [{}])[0]
            if "funding_csv_path" in mc_raw and args.market_model == "PERPETUAL":
                import csv

                from obsidian_rl.data.contracts import SCHEMA_VERSION_V2, FundingRate

                funding_path = mc_raw["funding_csv_path"]
                print(f"Loading funding rates from {funding_path}")
                rates = []
                with open(funding_path, encoding="utf-8") as ff:
                    reader = csv.reader(ff)
                    next(reader)
                    for row in reader:
                        ts = int(row[0])
                        val = float(row[1])
                        if args.start_ms is not None and ts < args.start_ms:
                            continue
                        if args.end_ms is not None and ts >= args.end_ms:
                            continue
                        rates.append(
                            FundingRate(
                                asset_class=AssetClass.CRYPTO,
                                venue=args.venue,
                                symbol=args.symbol,
                                timestamp_utc=ts,
                                observed_at_utc=ts,
                                rate=val,
                                data_source="CSV",
                                schema_version=SCHEMA_VERSION_V2,
                            )
                        )
                funding_rates = tuple(sorted(rates, key=lambda x: x.timestamp_utc))
                print(f"Loaded {len(funding_rates)} funding rates.")
        except Exception as e:
            print(str(e))
            sys.exit(1)

    # For PERPETUAL without manifest, load funding from SQLite storage
    if not funding_rates and args.market_model == "PERPETUAL":
        from obsidian_rl.data.storage import SQLiteStorage

        asset = AssetClass(args.asset_class)
        with SQLiteStorage(args.database) as store:
            frates = store.query_funding_rates(
                asset_class=asset,
                venue=args.venue,
                symbol=args.symbol,
                start_timestamp_utc=args.start_ms if args.start_ms else 0,
                end_timestamp_utc=args.end_ms if args.end_ms else (1 << 63) - 1,
                observed_before_ms=args.observed_before_ms,
            )
            funding_rates = tuple(frates)
            print(f"Loaded {len(funding_rates)} funding rates from SQLite storage.")
            if not funding_rates:
                print("Error: PERPETUAL market model requires funding rates but none found in storage.")
                sys.exit(1)

    cost_model = CostModel(
        taker_fee=args.taker_fee,
        half_spread=args.half_spread,
        slippage=args.slippage,
    )
    config = TrendConfig()
    registry = default_registry() if args.outage_aware else None

    from obsidian_rl.portfolio.engine import ExposurePolicy, MarketModel

    market_model = MarketModel(args.market_model)
    exposure_policy = ExposurePolicy(args.exposure_policy)

    if market_model == MarketModel.SPOT and exposure_policy == ExposurePolicy.BIDIRECTIONAL:
        print("SPOT market model cannot execute BIDIRECTIONAL positions")
        sys.exit(1)

    try:
        report = run_trend_backtest(
            tuple(bars),
            config,
            cost_model,
            eval_start_ms=eval_start_ms,
            market_model=market_model,
            exposure_policy=exposure_policy,
            funding_rates=funding_rates,
            outage_registry=registry,
            manifest_digest=manifest_digest,
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
    expected_interval = tf.value_ms() if hasattr(tf, "value_ms") else 14400000
    for i in range(1, len(bars)):
        diff = bars[i].timestamp_utc - bars[i - 1].timestamp_utc
        if diff > expected_interval:
            if "OANDA" in args.venue and is_forex_weekend_gap(
                bars[i - 1].timestamp_utc, bars[i].timestamp_utc
            ):
                weekend_gaps += 1
            elif registry and registry.covers_gap(
                args.venue, bars[i - 1].timestamp_utc + expected_interval, bars[i].timestamp_utc
            ):
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