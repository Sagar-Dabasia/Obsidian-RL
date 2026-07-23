import pytest

from obsidian_rl.data.contracts import AssetClass, Timeframe
from obsidian_rl.data.historical_dataset import ingest_historical_range
from obsidian_rl.data.storage import SQLiteStorage


def test_historical_dataset_rejects_empty(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"

    with SQLiteStorage(db_path) as storage, pytest.raises(RuntimeError):
        ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
                symbol="FAKECOIN",
                timeframe=Timeframe.H4,
                start_ms=1000000000000,
                end_ms=1000000000001,
                storage=storage,
            )


def test_missing_crypto_candle_failure(tmp_path) -> None:
    pass

