import sys
import re

with open("tools/run_trend_backtest.py", "r") as f:
    content = f.read()

# Add args
content = content.replace(
    'parser.add_argument("--end-ms", type=int, required=True)',
    'parser.add_argument("--end-ms", type=int, required=True)\n    parser.add_argument("--eval-start-ms", type=int, default=0)\n    parser.add_argument("--manifest", type=str, default="")'
)

# Parse manifest and digest
digest_logic = """
    manifest_component = None
    computed_digest = None
    if args.manifest:
        import json
        with open(args.manifest, "r") as f:
            manifest = json.load(f)
        for comp in manifest.get("components", []):
            if comp.get("symbol") == args.symbol:
                manifest_component = comp
                break
        
        from obsidian_rl.data.historical_dataset import verify_and_digest_continuous_bars
        computed_digest = verify_and_digest_continuous_bars(bars, args.eval_start_ms, tf, args.venue, registry, min_warmup_bars=config.long_horizon_days)
"""
content = content.replace(
    'config = TrendConfig()',
    'config = TrendConfig()\n' + digest_logic
)

# Pass eval_start_ms to run_trend_backtest
content = content.replace(
    'report = run_trend_backtest(bars, config, cost_model, registry)',
    'report = run_trend_backtest(bars, config, cost_model, registry, eval_start_ms=args.eval_start_ms)'
)

# Add audited prints
new_prints = """
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

"""

# We'll inject new_prints inside _print_result but wait, _print_result doesn't have bars, eval_start_ms etc.
# The AI actually replaced `print("\n\n--- Strategy ---")` inside main earlier?
# No, run_trend_backtest doesn't print! It returns a report!
# _print_result is called in main:
# _print_result("Strategy", report.strategy)
# So I can inject before that.

audit_code = new_prints.replace("eval_start_ms", "args.eval_start_ms").replace("strategy.generate_signal", "report.strategy.strategy.generate_signal").replace("engine", "report.strategy.engine")
# Wait, report.strategy doesn't have strategy and engine!
# report.strategy is a TrendBacktestResult which has:
# net_return, gross_return, max_drawdown, sharpe, hit_rate, trades, total_costs, exposure, backtest_identity
# It doesn't have the engine! So I can't read turnover from it!
"""

# Wait, if I can't get engine, how did the AI do it?
# In `src/obsidian_rl/evaluation/trend_backtest.py` I need to add them to TrendBacktestResult!
