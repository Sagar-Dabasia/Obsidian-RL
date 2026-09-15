import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path("src").resolve()))

import math
from datetime import datetime, timezone
from obsidian_rl.data.providers.binance_futures import BinanceFuturesProvider
from obsidian_rl.data.contracts import Timeframe

def main():
    provider = BinanceFuturesProvider()
    end_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    # Let's find the start_ms for ETHUSDT. ETHUSDT launched around Nov 2019.
    # We will just fetch from 2019-11-01 and it will skip empty periods or start when data is available?
    # Wait, Binance API might return empty list if we request before listing.
    # Let's binary search or just request from 2019-09-01.
    start_ms = int(datetime(2019, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    print("Fetching BTCUSDT bars...")
    btc_bars = provider.fetch_bars("BTCUSDT", Timeframe.H4, start_ms, end_ms)
    print(f"BTC bars: {len(btc_bars)}")
    if btc_bars:
        print(f"First BTC bar: {datetime.fromtimestamp(btc_bars[0].timestamp_utc/1000, tz=timezone.utc)}")

    print("Fetching ETHUSDT bars...")
    eth_bars = provider.fetch_bars("ETHUSDT", Timeframe.H4, start_ms, end_ms)
    print(f"ETH bars: {len(eth_bars)}")
    if eth_bars:
        print(f"First ETH bar: {datetime.fromtimestamp(eth_bars[0].timestamp_utc/1000, tz=timezone.utc)}")

    print("Fetching BTCUSDT funding...")
    btc_funding = provider.fetch_funding_rates("BTCUSDT", start_ms, end_ms)
    print(f"BTC funding: {len(btc_funding)}")

    print("Fetching ETHUSDT funding...")
    eth_funding = provider.fetch_funding_rates("ETHUSDT", start_ms, end_ms)
    print(f"ETH funding: {len(eth_funding)}")

if __name__ == "__main__":
    main()
