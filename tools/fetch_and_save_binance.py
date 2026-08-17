import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path("src").resolve()))

from obsidian_rl.data.contracts import Timeframe
from obsidian_rl.data.providers.binance_futures import BinanceFuturesProvider


def main() -> None:
    provider = BinanceFuturesProvider()
    end_ms = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)

    # We want full historical coverage. Binance BTCUSDT futures started ~2019-09-08.
    start_ms = int(datetime(2019, 9, 1, tzinfo=UTC).timestamp() * 1000)

    out_dir = Path("artifacts/cycle_02/raw/binance_futures")
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in ["BTCUSDT", "ETHUSDT"]:
        print(f"Fetching {symbol} bars...")
        bars = provider.fetch_bars(symbol, Timeframe.H4, start_ms, end_ms)
        bars_path = out_dir / f"{symbol}_H4.csv"
        with open(bars_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
            for b in bars:
                writer.writerow([b.timestamp_utc, b.open, b.high, b.low, b.close, b.volume])
        print(f"Saved {len(bars)} bars to {bars_path}")

        print(f"Fetching {symbol} funding...")
        funding = provider.fetch_funding_rates(symbol, start_ms, end_ms)
        funding_path = out_dir / f"{symbol}_FUNDING.csv"
        with open(funding_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_utc", "funding_rate"])
            for fr in funding:
                writer.writerow([fr.timestamp_utc, fr.rate])
        print(f"Saved {len(funding)} funding rates to {funding_path}")


if __name__ == "__main__":
    main()
