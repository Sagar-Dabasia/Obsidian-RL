import argparse
import math
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.evaluation.trend_backtest import calculate_trend_signal, _get_exec_price
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.signals.trend import TrendConfig
from obsidian_rl.data.outages import default_registry

MARKETS = [
    (AssetClass.CRYPTO, "BINANCE_SPOT", "BTCUSDT", Timeframe.H4, CostModel(0.0005, 0.00005, 0.0001), True),
    (AssetClass.CRYPTO, "BINANCE_SPOT", "ETHUSDT", Timeframe.H4, CostModel(0.0005, 0.00005, 0.0001), True),
    (AssetClass.FOREX, "OANDA_PRACTICE", "EUR_USD", Timeframe.H4, CostModel(0.0, 0.0, 0.0), False),
    (AssetClass.FOREX, "OANDA_PRACTICE", "GBP_USD", Timeframe.H4, CostModel(0.0, 0.0, 0.0), False),
]

START_MS = 1546300800000
EVAL_START_MS = 1577836800000
END_MS = 1704067200000

def run_audit():
    with SQLiteStorage("data/trend_pilot_01.sqlite") as store:
        for asset_class, venue, symbol, timeframe, cost_model, use_outage in MARKETS:
            print(f"\n--- {symbol} ---")
            bars = store.query_market_bars(
                asset_class=asset_class, venue=venue, symbol=symbol, timeframe=timeframe,
                start_timestamp_utc=START_MS, end_timestamp_utc=END_MS
            )
            print(f"Loaded {len(bars)} bars")
            if not bars:
                continue

            config = TrendConfig(short_horizon_days=20, medium_horizon_days=60, long_horizon_days=120)
            portfolio_config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0, allow_short=True)
            engine = PortfolioEngine(portfolio_config, cost_model)

            eval_bars = [b for b in bars if b.timestamp_utc >= EVAL_START_MS]
            first_ts = eval_bars[0].timestamp_utc
            last_ts = eval_bars[-1].timestamp_utc

            target_exposure = 0.0
            last_equity = None

            first_nonzero_signal_ts = None
            first_exec_ts = None
            first_exec_px = None

            for i in range(len(bars)):
                bar = bars[i]
                is_eval = bar.timestamp_utc >= EVAL_START_MS

                if is_eval:
                    if last_equity is None:
                        last_equity = engine.state.net_equity(bar.open)

                    current_exp = engine.state.exposure(bar.open)
                    if target_exposure != current_exp:
                        exec_px = _get_exec_price(asset_class, bar, current_exp, target_exposure)
                        if first_exec_ts is None and target_exposure != 0.0:
                            first_exec_ts = bar.timestamp_utc
                            first_exec_px = exec_px
                        engine.rebalance(target_exposure, exec_px)

                    engine.mark_to_market(bar.close)

                history = tuple(bars[: i + 1])
                try:
                    sig = calculate_trend_signal(history, observed_before_ms=bar.observed_at_utc, config=config)
                    if first_nonzero_signal_ts is None and sig.direction != "FLAT":
                        first_nonzero_signal_ts = bar.timestamp_utc
                    
                    if sig.direction == "LONG":
                        target_exposure = 1.0
                    elif sig.direction == "SHORT":
                        target_exposure = -1.0
                    else:
                        target_exposure = 0.0
                except Exception:
                    target_exposure = 0.0

            engine.liquidate(bars[-1].close)
            
            s = engine.state
            
            print(f"First loaded ts: {bars[0].timestamp_utc}")
            print(f"Last loaded ts: {bars[-1].timestamp_utc}")
            print(f"First eval ts: {first_ts}")
            print(f"First nonzero signal ts: {first_nonzero_signal_ts}")
            print(f"First exec ts: {first_exec_ts}")
            print(f"First exec px: {first_exec_px}")
            print(f"Turnover: {s.turnover}")
            print(f"Trade Count: {s.trade_count}")

run_audit()
