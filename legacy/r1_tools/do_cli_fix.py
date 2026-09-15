import os
import re

path = "tools/run_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Update argparse options
old_argparse = """    parser.add_argument("--asset-class", required=True, choices=[a.value for a in AssetClass])
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

    args = parser.parse_args()"""

new_argparse = """    parser.add_argument("--asset-class", required=True, choices=[a.value for a in AssetClass])
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
    
    parser.add_argument("--market-model", required=True, choices=["SPOT", "PERPETUAL", "FOREX_MARGIN"])
    parser.add_argument("--exposure-policy", required=True, choices=["LONG_FLAT", "BIDIRECTIONAL"])

    args = parser.parse_args()"""

content = content.replace(old_argparse, new_argparse)

# Remove old manifest handling
old_manifest_logic = """    manifest_component = None
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
        sys.exit(1)"""

new_manifest_logic = """    if args.start_ms is None or args.end_ms is None:
        if not args.manifest:
            print("Error: Must provide --start-ms and --end-ms if no manifest provided.")
            sys.exit(1)"""

content = content.replace(old_manifest_logic, new_manifest_logic)

# Replace the runtime check logic
old_runtime_check = """    if args.manifest and manifest_component:
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
        print("Digest matched successfully.")"""

new_runtime_check = """    print(f"Loaded {len(bars)} bars from local storage.")

    import hashlib
    h = hashlib.sha256()
    for b in bars:
        h.update(b.row_hash.encode("utf-8"))
    computed_digest = h.hexdigest()
    
    expected_interval = (tf.value_ms() if hasattr(tf, "value_ms") else 14400000)
    
    manifest_digest = None
    digest_match = False

    if args.manifest:
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
                args.end_ms
            )
            manifest_digest = mc.digest
            digest_match = True
            print("Digest matched successfully.")
        except Exception as e:
            print(str(e))
            sys.exit(1)"""

content = content.replace(old_runtime_check, new_runtime_check)

# Update market model / exposure policy instantiation
old_market = """    from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy

    if "SPOT" in args.venue:
        market_model = MarketModel.SPOT
        exposure_policy = ExposurePolicy.LONG_FLAT
    elif asset == AssetClass.FOREX:
        market_model = MarketModel.FOREX_MARGIN
        exposure_policy = ExposurePolicy.BIDIRECTIONAL
    else:
        market_model = MarketModel.PERPETUAL
        exposure_policy = ExposurePolicy.BIDIRECTIONAL"""

new_market = """    from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy

    market_model = MarketModel(args.market_model)
    exposure_policy = ExposurePolicy(args.exposure_policy)
    
    if market_model == MarketModel.SPOT and exposure_policy == ExposurePolicy.BIDIRECTIONAL:
        print("SPOT market model cannot execute BIDIRECTIONAL positions")
        sys.exit(1)"""

content = content.replace(old_market, new_market)

content = content.replace("eval_start_ms=eval_start_ms,", "eval_start_ms=eval_start_ms,\n            market_model=market_model,\n            exposure_policy=exposure_policy,")

# Now I must update test defaults? 
# "Keep tests’ default market bars as BINANCE_SPOT; tests requiring shorts must pass an explicit compatible contract."
with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("CLI fixed")
