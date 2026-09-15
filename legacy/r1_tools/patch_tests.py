import sys
from unittest.mock import Mock
import pytest

from obsidian_rl.data.contracts import AssetClass, MarketBar, QuoteStatus, Timeframe, VolumeType
from obsidian_rl.data.historical_dataset import ingest_historical_range
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.data.outages import OutageRegistry

def make_oanda_bar(ts: int) -> MarketBar:
    return MarketBar(
        asset_class=AssetClass.FOREX,
        venue="OANDA_PRACTICE",
        symbol="EUR_USD",
        timeframe=Timeframe.H4,
        timestamp_utc=ts,
        observed_at_utc=ts + 1,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        quote_status=QuoteStatus.UNAVAILABLE,
        bid=None,
        ask=None,
        volume_type=VolumeType.BASE,
        volume=1.0,
        data_source="MOCK",
        schema_version="SCHEMA_V2",
    )

def test_oanda_weekend_gap_accepted(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "oanda_we.sqlite"
    eval_start_ms = 1672617600000  # Jan 2, 2023 00:00 UTC (Monday)
    # Friday close
    start_ts = 1672430400000 # Friday Dec 30 20:00 UTC (1672430400)
    bars = []
    # Add warmup before gap
    for i in range(1000, 0, -1):
        bars.append(make_oanda_bar(start_ts - i * 14400000))
    bars.append(make_oanda_bar(start_ts))
    
    # Next bar is Sunday 22:00 UTC (1672610400000)
    # That is a 180,000,000 ms gap (50 hours), valid weekend gap.
    sunday_open = 1672610400000
    bars.append(make_oanda_bar(sunday_open))
    for i in range(1, 10):
        bars.append(make_oanda_bar(sunday_open + i * 14400000))
        
    mock_provider = Mock()
    mock_provider.fetch_bars.return_value = bars
    monkeypatch.setattr("obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider)
    
    with SQLiteStorage(db_path) as storage:
        manifest = ingest_historical_range(
            asset_class=AssetClass.FOREX,
            symbol="EUR_USD",
            timeframe=Timeframe.H4,
            start_ms=bars[0].timestamp_utc,
            end_ms=bars[-1].timestamp_utc + 1,
            storage=storage,
        )
        assert manifest.row_count == len(bars)

def test_oanda_weekday_gap_fails(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "oanda_wd.sqlite"
    eval_start_ms = 1672617600000
    start_ts = 1672617600000 # Monday 00:00 UTC
    bars = []
    for i in range(2000):
        if i == 500: # Tuesday gap
            continue
        bars.append(make_oanda_bar(start_ts + i * 14400000))
        
    mock_provider = Mock()
    mock_provider.fetch_bars.return_value = bars
    monkeypatch.setattr("obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider)
    
    with SQLiteStorage(db_path) as storage, pytest.raises(ValueError, match="Unregistered gap"):
        ingest_historical_range(
            asset_class=AssetClass.FOREX,
            symbol="EUR_USD",
            timeframe=Timeframe.H4,
            start_ms=bars[0].timestamp_utc,
            end_ms=bars[-1].timestamp_utc + 1,
            storage=storage,
        )

def test_oanda_registered_outage_accepted(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "oanda_outage.sqlite"
    start_ts = 1672617600000 # Monday 00:00 UTC
    bars = []
    for i in range(2000):
        if i == 500: # Tuesday gap
            continue
        bars.append(make_oanda_bar(start_ts + i * 14400000))
        
    mock_provider = Mock()
    mock_provider.fetch_bars.return_value = bars
    monkeypatch.setattr("obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider)
    
    registry = OutageRegistry()
    registry.register_outage("OANDA_PRACTICE", start_ts + 499*14400000 + 14400000, start_ts + 501*14400000)
    
    with SQLiteStorage(db_path) as storage:
        manifest = ingest_historical_range(
            asset_class=AssetClass.FOREX,
            symbol="EUR_USD",
            timeframe=Timeframe.H4,
            start_ms=bars[0].timestamp_utc,
            end_ms=bars[-1].timestamp_utc + 1,
            storage=storage,
            outage_registry=registry
        )
        assert manifest.row_count == len(bars)

def test_crypto_gaps_remain_strict(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "crypto_strict.sqlite"
    start_ts = 1672430400000 # Friday Dec 30 20:00 UTC
    bars = []
    # Make a weekend gap for crypto
    from tests.data.test_historical_dataset import make_bar
    for i in range(1000):
        bars.append(make_bar(start_ts - i * 14400000))
    bars.reverse()
    bars.append(make_bar(start_ts))
    
    sunday_open = 1672610400000
    bars.append(make_bar(sunday_open))
    for i in range(1, 10):
        bars.append(make_bar(sunday_open + i * 14400000))
        
    mock_provider = Mock()
    mock_provider.fetch_bars.return_value = bars
    monkeypatch.setattr("obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider)
    
    with SQLiteStorage(db_path) as storage, pytest.raises(ValueError, match="Unregistered gap"):
        ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_ms=bars[0].timestamp_utc,
            end_ms=bars[-1].timestamp_utc + 1,
            storage=storage,
        )

def test_pilot_720_bars_fails(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "fail_720.sqlite"
    eval_start_ms = 1577836800000
    start_ts = eval_start_ms - 720 * 14400000
    from tests.data.test_historical_dataset import make_bar
    bars = [make_bar(start_ts + i * 14400000) for i in range(721)]
    
    mock_provider = Mock()
    mock_provider.fetch_bars.return_value = bars
    monkeypatch.setattr("obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider)
    
    with SQLiteStorage(db_path) as storage, pytest.raises(ValueError, match="Insufficient warmup history"):
        ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_ms=bars[0].timestamp_utc,
            end_ms=bars[-1].timestamp_utc + 1,
            storage=storage,
            min_warmup_bars=721
        )

def test_pilot_721_bars_passes(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "pass_721.sqlite"
    eval_start_ms = 1577836800000
    start_ts = eval_start_ms - 721 * 14400000
    from tests.data.test_historical_dataset import make_bar
    bars = [make_bar(start_ts + i * 14400000) for i in range(722)]
    
    mock_provider = Mock()
    mock_provider.fetch_bars.return_value = bars
    monkeypatch.setattr("obsidian_rl.data.historical_dataset._get_provider", lambda x: mock_provider)
    
    with SQLiteStorage(db_path) as storage:
        manifest = ingest_historical_range(
            asset_class=AssetClass.CRYPTO,
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            start_ms=bars[0].timestamp_utc,
            end_ms=bars[-1].timestamp_utc + 1,
            storage=storage,
            min_warmup_bars=721
        )
        assert manifest.row_count == len(bars)
