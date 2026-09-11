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
    START_MS = 1565827200000  # 2019-08-15T00:00:00Z
    END_MS = 1704052800000  # 2023-12-31T20:00:00Z (last valid H4)
    db_path = "data/trend_pilot_01.sqlite"

    # Clean up old DB and manifests
    if os.path.exists(db_path):
        os.remove(db_path)

    manifest_dir = Path("artifacts/cycle_02/manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)

    plan_path = "docs/cycle_02/research/PHASE_04C_R3_PLAN.md"
    plan_hash = get_hash(plan_path)

    # Dukascopy Raw Dir
    raw_dir = Path("artifacts/cycle_02/raw/dukascopy")

    with SQLiteStorage(db_path) as storage:
        for symbol in ["EURUSD", "GBPUSD"]:
            print(f"Building Phase 4C manifest for {symbol}...")

            # Re-ingest
            # min_warmup_bars = 721
            # We must use ingest_historical_range from DukascopyProvider

            manifest = ingest_historical_range(
                asset_class=AssetClass.FOREX,
                venue="DUKASCOPY",
                symbol=symbol,
                timeframe=Timeframe.H4,
                start_ms=START_MS,
                end_ms=END_MS,
                storage=storage,
                outage_registry=default_registry(),
                min_warmup_bars=721,
            )

            bid_file = raw_dir / f"{symbol}_4 Hours_Bid_2019.08.15_2023.12.31.csv"
            ask_file = raw_dir / f"{symbol}_4 Hours_Ask_2019.08.15_2023.12.31.csv"

            manifest_dict = {
                "provider": "DUKASCOPY_JFOREX_HISTORICAL_DATA_MANAGER",
                "transport": "USER_EXPORTED_OFFICIAL_JFOREX",
                "symbol": symbol,
                "timeframe": "H4",
                "raw_BID_file": str(bid_file),
                "raw_BID_sha256": get_hash(str(bid_file)),
                "raw_ASK_file": str(ask_file),
                "raw_ASK_sha256": get_hash(str(ask_file)),
                "normalized_dataset_sha256": manifest.digest,
                "row_count": manifest.row_count,
                "first_timestamp": manifest.start_timestamp_utc,
                "last_timestamp": manifest.end_timestamp_utc - 14400000,
                "warm_up_boundary": 1577836800000,  # 2020-01-01 00:00:00
                "eval_start": 1577836800000,
                "eval_end": 1704052800000,
                "market_model": "FOREX_MARGIN",
                "exposure_policy": "BIDIRECTIONAL",
                "cost_methodology": "taker=0.0, spread=point-in-time, slippage=0.0001",
                "plan_sha256": plan_hash,
            }

            m_path = manifest_dir / f"PHASE_04C_R3_{symbol}_MANIFEST.json"
            with open(m_path, "w") as f:
                json.dump(manifest_dict, f, indent=2)

            print(f"Manifest written to {m_path}")


if __name__ == "__main__":
    main()
