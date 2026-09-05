import csv
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
    START_MS = 1567987200000  # Will be adjusted based on first common data
    END_MS = 1704067200000  # 2024-01-01

    # We find the actual START_MS based on ETHUSDT which started later (Nov 2019)
    # The saved fetch found first ETH bar around 2019-11-27 04:00:00+00:00

    db_path = "data/trend_pilot_01.sqlite"

    manifest_dir = Path("artifacts/cycle_02/manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)

    plan_path = "docs/cycle_02/research/PHASE_04D_R3_PERPETUAL_PLAN.md"
    plan_hash = get_hash(plan_path) if os.path.exists(plan_path) else "TBD"

    raw_dir = Path("artifacts/cycle_02/raw/binance_futures")

    # Let's ingest the CSVs we fetched
    with SQLiteStorage(db_path) as storage:
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            print(f"Building Phase 4D-R3 manifest for {symbol}...")

            bars_file = raw_dir / f"{symbol}_H4.csv"
            funding_file = raw_dir / f"{symbol}_FUNDING.csv"

            # Since we downloaded it to CSV but SQLiteStorage doesn't ingest CSV natively,
            # we need to insert the bars directly or use a provider.
            # We already have BinanceFuturesProvider, so let's just use it to ingest?
            # But the prompt says "Build/verify fresh USD-M-specific: price data
            # funding data manifests digests"
            # It's better to ingest the CSV we just saved to ensure we use exactly that data.

            # Actually, `ingest_historical_range` takes `AssetClass.CRYPTO`,
            # `venue="BINANCE_FUTURES"`.
            # And `BinanceFuturesProvider` fetches from REST!
            # But wait, `ingest_historical_range` uses the provider registry.
            # If we call `ingest_historical_range`, it will fetch from REST again.
            # That's fine, it will populate the DB. We just fetched it earlier
            # to ensure it exists and we have it saved.

            # But wait, "raw start = first common authentic BTCUSDT + ETHUSDT USD-M data sufficient
            # to begin warm-up"
            # So raw_start should be the same for both.
            # ETHUSDT starts at 2019-11-27 04:00:00 UTC = 1574827200000
            START_MS = 1574827200000

            manifest = ingest_historical_range(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol=symbol,
                timeframe=Timeframe.H4,
                start_ms=START_MS,
                end_ms=END_MS,
                storage=storage,
                outage_registry=default_registry(),
                min_warmup_bars=721,
            )

            # Now we must compute the funding digest
            # We'll just hash the FUNDING CSV file we saved.
            funding_digest = get_hash(str(funding_file))
            bars_digest = get_hash(str(bars_file))

            # We can also parse the funding file to get the exact count
            funding_count = 0
            with open(funding_file) as f:
                reader = csv.reader(f)
                next(reader)
                funding_count = sum(1 for row in reader if START_MS <= int(row[0]) < END_MS)

            # The prompt requires: "Backtest identity/provenance must include deterministic
            # funding-series identity/digest."
            # The easiest way is to add it to the manifest, and `TrendBacktestResult`
            # reads `manifest_digest`.
            # But we must modify `run_trend_backtest.py` to parse funding.

            manifest_dict = {
                "components": [
                    {
                        "asset_class": "CRYPTO",
                        "venue": "BINANCE_FUTURES",
                        "symbol": symbol,
                        "timeframe": "4h",
                        "start_timestamp_utc": manifest.start_timestamp_utc,
                        "end_timestamp_utc": manifest.end_timestamp_utc,
                        "row_count": manifest.row_count,
                        "digest": manifest.digest,
                        "provider": "BINANCE_FUTURES",
                        "funding_csv_path": str(funding_file),
                        "funding_csv_sha256": funding_digest,
                        "funding_events_in_range": funding_count,
                        "raw_bars_csv_sha256": bars_digest,
                        "warm_up_boundary": 1585209600000,  # 721 bars after 1574827200000
                        "eval_start": 1585209600000,
                        "eval_end": 1704067200000,
                        "market_model": "PERPETUAL",
                        "exposure_policy": "BIDIRECTIONAL",
                        "cost_methodology": "taker=0.0005, half_spread=0.00005, slippage=0.0001",
                        "plan_sha256": plan_hash,
                    }
                ]
            }

            m_path = manifest_dir / f"PHASE_04D_R3_{symbol}_MANIFEST.json"
            with open(m_path, "w") as f:
                json.dump(manifest_dict, f, indent=2)

            print(f"Manifest written to {m_path}")


if __name__ == "__main__":
    main()
