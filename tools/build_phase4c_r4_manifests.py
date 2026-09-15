import hashlib
import json
import os
from pathlib import Path

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.historical_dataset import ingest_historical_range
from obsidian_rl.data.outages import default_registry
from obsidian_rl.data.storage import SQLiteStorage


def get_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> None:
    START_MS = 1559347200000  # 2019-06-01T00:00:00Z
    END_MS = 1704052800000  # 2023-12-31T20:00:00Z (last valid H4)
    db_path = "data/trend_pilot_01.sqlite"

    # Clean up old DB and manifests
    if os.path.exists(db_path):
        os.remove(db_path)

    manifest_dir = Path("artifacts/cycle_02/manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)

    plan_path = "docs/cycle_02/research/PHASE_04C_R4_PLAN.md"
    plan_hash = get_hash(plan_path) if os.path.exists(plan_path) else "TBD"

    raw_dir = Path("artifacts/cycle_02/raw/dukascopy")

    with SQLiteStorage(db_path) as storage:
        for symbol in ["EURUSD", "GBPUSD"]:
            print(f"Building Phase 4C-R4 manifest for {symbol}...")

            manifest = ingest_historical_range(
                asset_class=AssetClass.FOREX,
                venue="OANDA_PRACTICE",
                symbol=symbol,
                timeframe=Timeframe.H4,
                start_ms=START_MS,
                end_ms=END_MS,
                storage=storage,
                outage_registry=default_registry(),
                min_warmup_bars=721,
            )

            csv_files = list(raw_dir.glob("*.csv"))
            bid_files = [f for f in csv_files if symbol in f.name and "Bid" in f.name]
            ask_files = [f for f in csv_files if symbol in f.name and "Ask" in f.name]

            file_hashes = {}
            for f in bid_files + ask_files:
                file_hashes[f.name] = get_hash(str(f))

            manifest_dict = {
                "components": [
                    {
                        "asset_class": "FOREX",
                        "venue": "DUKASCOPY",
                        "symbol": symbol,
                        "timeframe": "4h",
                        "start_timestamp_utc": manifest.start_timestamp_utc,
                        "end_timestamp_utc": manifest.end_timestamp_utc,
                        "row_count": manifest.row_count,
                        "digest": manifest.digest,
                        "provider": "DUKASCOPY_JFOREX_HISTORICAL_DATA_MANAGER",
                        "transport": "USER_EXPORTED_OFFICIAL_JFOREX",
                        "raw_files_sha256": file_hashes,
                        "warm_up_boundary": 1577836800000,
                        "eval_start": 1577836800000,
                        "eval_end": 1704052800000,
                        "market_model": "FOREX_MARGIN",
                        "exposure_policy": "BIDIRECTIONAL",
                        "cost_methodology": "taker=0.0, spread=point-in-time, slippage=0.0001",
                        "plan_sha256": plan_hash,
                    }
                ]
            }

            m_path = manifest_dir / f"PHASE_04C_R4_{symbol}_MANIFEST.json"
            with open(m_path, "w") as out_f:
                json.dump(manifest_dict, out_f, indent=2)

            print(f"Manifest written to {m_path}")


if __name__ == "__main__":
    main()
