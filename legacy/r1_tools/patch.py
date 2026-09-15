import sys

new_prints = '''
    # --- Audited Outputs ---
    queried_row_count = len(bars)
    warmup_bars = [b for b in bars if b.timestamp_utc < eval_start_ms]
    eval_bars = [b for b in bars if b.timestamp_utc >= eval_start_ms]
    first_loaded_ts = bars[0].timestamp_utc if bars else None
    last_loaded_ts = bars[-1].timestamp_utc if bars else None
    first_eval_ts = eval_bars[0].timestamp_utc if eval_bars else None
    
    # Find first nonzero signal
    first_nonzero_signal_ts = None
    for b in eval_bars:
        s = strategy.generate_signal(b)
        if s.target_position != 0:
            first_nonzero_signal_ts = b.timestamp_utc
            break
            
    # Find first execution
    first_exec_ts = None
    first_exec_price = None
    for fill in engine.portfolio.history:
        if fill.size != 0:
            first_exec_ts = fill.timestamp_utc
            first_exec_price = fill.price
            break
            
    # Outages accepted
    outages_accepted = 0
    expected_interval = (tf.value_ms() if hasattr(tf, "value_ms") else 14400000)
    for i in range(1, len(bars)):
        diff = bars[i].timestamp_utc - bars[i - 1].timestamp_utc
        if diff > expected_interval:
            if registry and registry.covers_gap(args.venue, bars[i-1].timestamp_utc + expected_interval, bars[i].timestamp_utc):
                outages_accepted += 1
                
    # Turnover
    turnover = engine.portfolio.metrics.turnover if hasattr(engine.portfolio.metrics, "turnover") else 0.0

    manifest_digest = None
    if manifest_component:
        manifest_digest = manifest_component.get("digest")
        
    digest_match = (manifest_digest == computed_digest) if manifest_digest else False

    print("\\n\\n--- AUDIT DATA ---")
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
    print(f"First Execution TS: {first_exec_ts}")
    print(f"First Execution Price: {first_exec_price}")
    print(f"Turnover: {turnover:.4f}")
    print(f"Outages Accepted: {outages_accepted}")
'''

with open('tools/run_trend_backtest.py', 'r') as f:
    content = f.read()

content = content.replace('_print_result("Strategy", report.strategy)', new_prints + '\n    _print_result("Strategy", report.strategy)')

with open('tools/run_trend_backtest.py', 'w') as f:
    f.write(content)
