import os
import re

path = "tools/run_trend_backtest.py"
with open(path, "r") as f:
    code = f.read()

# Replace the manual JSON parsing with parse_and_validate_manifest
old_manifest_logic = """    manifest_component = None
    manifest_digest = None
    if args.manifest:
        import re as re_mod
        with open(args.manifest, "r") as f:
            manifest_data = json.load(f)
        
        components = manifest_data.get("components")
        if not isinstance(components, list):
            print("Manifest component missing or ambiguous")
            sys.exit(1)
            
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
            
        c = matching_components[0]
        
        start_ts = c.get("start_timestamp_utc")
        end_ts = c.get("end_timestamp_utc")
        row_count = c.get("row_count")
        
        if isinstance(start_ts, bool) or not isinstance(start_ts, int) or \\
           isinstance(end_ts, bool) or not isinstance(end_ts, int) or \\
           isinstance(row_count, bool) or not isinstance(row_count, int):
            print("Manifest component missing or ambiguous")
            sys.exit(1)
            
        if start_ts >= end_ts:
            print("Manifest component missing or ambiguous")
            sys.exit(1)
            
        if row_count <= 0:
            print("Manifest component missing or ambiguous")
            sys.exit(1)
            
        manifest_digest = c.get("digest")
        if not manifest_digest or not re_mod.match(r"^[0-9a-f]{64}$", str(manifest_digest)):
            print("Manifest digest is malformed")
            sys.exit(1)
            
        if args.start_ms is not None and args.start_ms != start_ts:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)
        if args.end_ms is not None and args.end_ms != end_ts:
            print("Error: CLI boundaries conflict with the manifest")
            sys.exit(1)
            
        args.start_ms = start_ts
        args.end_ms = end_ts
        manifest_component = c"""

new_manifest_logic = """    manifest_component = None
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
        manifest_component = c"""
code = code.replace(old_manifest_logic, new_manifest_logic)

# Replace the run_trend_backtest call to use MarketModel and ExposurePolicy
old_run = """    allow_short = True
    market_model = "SPOT" if "SPOT" in args.venue else ("FOREX_MARGIN" if asset == AssetClass.FOREX else "PERPETUAL")

    try:
        report = run_trend_backtest(tuple(bars), config, cost_model, outage_registry=registry, eval_start_ms=eval_start_ms, allow_short=allow_short, market_model=market_model)"""

new_run = """    from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy
    
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
        )"""
code = code.replace(old_run, new_run)

with open(path, "w") as f:
    f.write(code)
