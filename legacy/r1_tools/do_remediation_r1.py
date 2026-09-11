import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path("src").resolve()))

from obsidian_rl.data.providers.binance_futures import BinanceFuturesProvider
from obsidian_rl.data.providers.dukascopy import DukascopyCSVProvider
from obsidian_rl.data.contracts import Timeframe
from obsidian_rl.data.fingerprint import canonical_json
from obsidian_rl.signals.trend import TrendConfig
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy
from obsidian_rl.evaluation.trend_backtest import run_trend_backtest

def run_4c():
    print("Running 4C-R1 (Dukascopy)")
    provider = DukascopyCSVProvider(data_dir="data/dukascopy")
    end_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    start_ms = int(datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    try:
        eur_bars = provider.fetch_bars("EURUSD", Timeframe.H4, start_ms, end_ms)
        gbp_bars = provider.fetch_bars("GBPUSD", Timeframe.H4, start_ms, end_ms)
    except Exception as e:
        print(f"4C-R1 Data Unavailable: {e}")
        # Write Fail Closed Report
        report_path = Path("docs/cycle_02/research/PHASE_04C_R1_REPORT.md")
        report_path.write_text(f"""# Phase 4C-R1 Cross-Market Replication Report

## Data Authentication Failure

**FAIL CLOSED**: Genuine Dukascopy Bank historical data for EURUSD and GBPUSD could not be obtained or verified locally.

In accordance with strict research governance, we do not manufacture completion, interpolate missing data, or silently fall back to unverified providers (e.g., OANDA proxy data).

**Action**: Experiment terminated. Strategy status on Forex remains INVALID due to lack of verifiable authentic data.
""")
        return

def run_4d():
    print("Running 4D-R1 (Binance Futures)")
    provider = BinanceFuturesProvider()
    end_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    start_ms = int(datetime(2019, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)

    try:
        btc_bars = provider.fetch_bars("BTCUSDT", Timeframe.H4, start_ms, end_ms)
        eth_bars = provider.fetch_bars("ETHUSDT", Timeframe.H4, start_ms, end_ms)
        btc_funding = provider.fetch_funding_rates("BTCUSDT", start_ms, end_ms)
        eth_funding = provider.fetch_funding_rates("ETHUSDT", start_ms, end_ms)
    except Exception as e:
        print(f"4D-R1 Data Unavailable: {e}")
        # Write Fail Closed Report
        report_path = Path("docs/cycle_02/research/PHASE_04D_R1_PERPETUAL_REPORT.md")
        report_path.write_text(f"""# Phase 4D-R1 Perpetual Replication Report

## Data Authentication Failure

**FAIL CLOSED**: Authentic Binance USD-M Futures data could not be fully obtained or verified via the public API. Exception: {e}

In accordance with strict research governance, we do not manufacture completion or silently fall back to Binance Spot data.

**Action**: Experiment terminated.
""")
        return

    if not btc_bars or not eth_bars:
        print("Missing bars")
        return
        
    print(f"BTC bars: {len(btc_bars)}, ETH bars: {len(eth_bars)}")
    
    first_btc = btc_bars[0].timestamp_utc
    first_eth = eth_bars[0].timestamp_utc
    first_common = max(first_btc, first_eth)
    
    # 120 days warm-up
    warmup_ms = 120 * 24 * 3600 * 1000
    eval_start_ms = first_common + warmup_ms
    
    print(f"Eval start MS: {eval_start_ms}")
    
    config = TrendConfig(
        short_horizon_days=20,
        medium_horizon_days=60,
        long_horizon_days=120
    )
    
    cost_model = CostModel(
        taker_fee=0.0004,
        half_spread=0.0001,
        slippage=0.0005
    )
    
    print("Running backtest for BTCUSDT...")
    btc_report = run_trend_backtest(
        bars=btc_bars,
        config=config,
        cost_model=cost_model,
        eval_start_ms=eval_start_ms,
        market_model=MarketModel.PERPETUAL,
        exposure_policy=ExposurePolicy.BIDIRECTIONAL,
        funding_rates=btc_funding,
        outage_registry=None,
        manifest_digest=None
    )
    
    print("Running backtest for ETHUSDT...")
    eth_report = run_trend_backtest(
        bars=eth_bars,
        config=config,
        cost_model=cost_model,
        eval_start_ms=eval_start_ms,
        market_model=MarketModel.PERPETUAL,
        exposure_policy=ExposurePolicy.BIDIRECTIONAL,
        funding_rates=eth_funding,
        outage_registry=None,
        manifest_digest=None
    )
    
    btc_res = btc_report.strategy
    eth_res = eth_report.strategy
    
    # Check criteria (positive net return)
    btc_pass = btc_res.net_return > 0
    eth_pass = eth_res.net_return > 0
    
    overall_status = "PASS" if (btc_pass and eth_pass) else "FAIL"
    
    # Create new manifests
    btc_manifest = {
        "experiment_id": "PHASE_04D_R1_PERPETUAL",
        "components": [
            {
                "asset_class": "CRYPTO",
                "venue": "BINANCE_FUTURES",
                "symbol": "BTCUSDT",
                "timeframe": "4h",
                "start_timestamp_utc": first_btc,
                "end_timestamp_utc": btc_bars[-1].timestamp_utc + 14400000,
                "row_count": len(btc_bars),
                "digest": btc_res.input_dataset_digest
            }
        ]
    }
    
    eth_manifest = {
        "experiment_id": "PHASE_04D_R1_PERPETUAL",
        "components": [
            {
                "asset_class": "CRYPTO",
                "venue": "BINANCE_FUTURES",
                "symbol": "ETHUSDT",
                "timeframe": "4h",
                "start_timestamp_utc": first_eth,
                "end_timestamp_utc": eth_bars[-1].timestamp_utc + 14400000,
                "row_count": len(eth_bars),
                "digest": eth_res.input_dataset_digest
            }
        ]
    }
    
    Path("data").mkdir(exist_ok=True)
    Path("data/manifests").mkdir(exist_ok=True)
    with open("data/manifests/PHASE_04D_R1_BTCUSDT.json", "w") as f:
        f.write(canonical_json(btc_manifest).decode('utf-8'))
    with open("data/manifests/PHASE_04D_R1_ETHUSDT.json", "w") as f:
        f.write(canonical_json(eth_manifest).decode('utf-8'))
        
    report = f"""# Phase 4D-R1 Perpetual Replication Report

## Execution Context
- **Market Model**: PERPETUAL
- **Exposure Policy**: BIDIRECTIONAL
- **Funding applied**: YES

## Results

### BTCUSDT
- Net Return: {btc_res.net_return:.4%}
- Gross Return: {btc_res.gross_return:.4%}
- Trade Count: {btc_res.trade_count}
- Win Rate: {btc_res.hit_rate:.2%}
- Max Drawdown: {btc_res.maximum_drawdown:.2%}

### ETHUSDT
- Net Return: {eth_res.net_return:.4%}
- Gross Return: {eth_res.gross_return:.4%}
- Trade Count: {eth_res.trade_count}
- Win Rate: {eth_res.hit_rate:.2%}
- Max Drawdown: {eth_res.maximum_drawdown:.2%}

## Conclusion
Strategy Profitability Screen: **{overall_status}**
Validity: **VALID** (Executed on authentic perpetual data without Spot proxies).
"""
    Path("docs/cycle_02/research/PHASE_04D_R1_PERPETUAL_REPORT.md").write_text(report)
    print("Done 4D-R1")

if __name__ == "__main__":
    run_4c()
    run_4d()
