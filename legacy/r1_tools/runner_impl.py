
    manifest_component = None
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
        
        if isinstance(start_ts, bool) or not isinstance(start_ts, int) or \
           isinstance(end_ts, bool) or not isinstance(end_ts, int) or \
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

    allow_short = True
    market_model = "SPOT" if "SPOT" in args.venue else ("FOREX_MARGIN" if asset == AssetClass.FOREX else "PERPETUAL")

    try:
        report = run_trend_backtest(tuple(bars), config, cost_model, outage_registry=registry, eval_start_ms=eval_start_ms, allow_short=allow_short, market_model=market_model)
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
