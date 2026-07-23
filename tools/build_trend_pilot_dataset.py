"""CLI tool to build the historical dataset for Trend Pilot 01."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.historical_dataset import ingest_historical_range
from obsidian_rl.data.storage import SQLiteStorage

START_MS = 1546300800000  # 2019-01-01T00:00:00Z
END_MS = 1704067200000  # 2024-01-01T00:00:00Z

MARKETS = [
    (AssetClass.CRYPTO, "BTCUSDT", Timeframe.H4),
    (AssetClass.CRYPTO, "ETHUSDT", Timeframe.H4),
    (AssetClass.FOREX, "EUR_USD", Timeframe.H4),
    (AssetClass.FOREX, "GBP_USD", Timeframe.H4),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Historical Dataset for Trend Pilot 01")
    parser.add_argument("--database", default="data/trend_pilot_01.sqlite", help="SQLite DB path")
    args = parser.parse_args()

    manifests = []

    with SQLiteStorage(args.database) as storage:
        for asset_class, symbol, timeframe in MARKETS:
            print(f"Ingesting {symbol}...")
            try:
                manifest = ingest_historical_range(
                    asset_class=asset_class,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_ms=START_MS,
                    end_ms=END_MS,
                    storage=storage,
                )
                manifests.append(manifest)
                print(f"Done {symbol}. Rows: {manifest.row_count}")
            except Exception as e:
                print(f"Failed {symbol}: {e}")

    # Combine manifests
    manifest_dir = Path("artifacts/cycle_02/manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)

    combined = {
        "dataset_id": "TREND_PILOT_01_COMBINED",
        "created_at_utc": int(datetime.now(UTC).timestamp() * 1000),
        "start_ms": START_MS,
        "end_ms": END_MS,
        "components": [
            {
                "symbol": m.symbol,
                "asset_class": m.asset_class.value,
                "venue": m.venue,
                "row_count": m.row_count,
                "digest": m.digest,
            }
            for m in manifests
        ],
    }

    manifest_path = manifest_dir / "TREND_PILOT_01_COMBINED.json"
    with open(manifest_path, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"Combined manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
