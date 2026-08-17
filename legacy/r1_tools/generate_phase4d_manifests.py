import json
from datetime import UTC, datetime
from pathlib import Path
from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.historical_dataset import ingest_historical_range
from obsidian_rl.data.outages import default_registry
from obsidian_rl.data.storage import SQLiteStorage

START_MS = 1546300800000  # 2019-01-01T00:00:00Z
END_MS = 1704067200000  # 2024-01-01T00:00:00Z
MARKETS = [
    (AssetClass.CRYPTO, "BTCUSDT", Timeframe.H4),
    (AssetClass.CRYPTO, "ETHUSDT", Timeframe.H4),
]

def main():
    manifest_dir = Path("artifacts/cycle_02/manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)

    with SQLiteStorage("data/trend_pilot_01.sqlite") as storage:
        for asset_class, symbol, timeframe in MARKETS:
            print(f"Generating Phase 4D manifest for {symbol}...")
            try:
                manifest = ingest_historical_range(
                    asset_class=asset_class,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_ms=START_MS,
                    end_ms=END_MS,
                    storage=storage,
                    outage_registry=default_registry(),
                    min_warmup_bars=721,
                )
                
                manifest_path = manifest_dir / f"PHASE_4D_PROVENANCE_{symbol}.json"
                out_data = {
                    "dataset_id": f"PHASE_4D_{symbol}",
                    "created_at_utc": int(datetime.now(UTC).timestamp() * 1000),
                    "start_ms": START_MS,
                    "end_ms": END_MS,
                    "component": {
                        "symbol": manifest.symbol,
                        "asset_class": manifest.asset_class.value,
                        "venue": manifest.venue,
                        "timeframe": manifest.timeframe.value,
                        "start_timestamp_utc": manifest.start_timestamp_utc,
                        "end_timestamp_utc": manifest.end_timestamp_utc,
                        "row_count": manifest.row_count,
                        "digest": manifest.digest,
                    }
                }
                with open(manifest_path, "w") as f:
                    json.dump(out_data, f, indent=2)
                print(f"Success for {symbol}. Manifest saved to {manifest_path}")
            except Exception as e:
                print(f"Failed {symbol}: {e}")

if __name__ == "__main__":
    main()
