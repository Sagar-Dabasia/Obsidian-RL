import pytest
import os
import sqlite3
import json
from pathlib import Path
from obsidian_rl.data.storage import SQLiteStorage
from obsidian_rl.data.contracts import AssetClass, Timeframe, MarketBar, QuoteStatus, VolumeType
from obsidian_rl.data.historical_dataset import verify_and_digest_continuous_bars
from obsidian_rl.data.outages import OutageRegistry

import sys
import subprocess

def test_builder_and_runner_digest_match():
    # Simple check that verify_and_digest_continuous_bars is deterministic
    b1 = MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.H4,
        timestamp_utc=1000000000000,
        observed_at_utc=1000000000000,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        quote_status=QuoteStatus.OBSERVED,
        bid=1.49,
        ask=1.51,
        volume_type=VolumeType.BASE,
        volume=100.0,
        data_source="TEST",
    )
    b2 = MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.H4,
        timestamp_utc=1000000000000 + 4*3600*1000,
        observed_at_utc=1000000000000 + 4*3600*1000,
        open=1.5,
        high=2.0,
        low=0.5,
        close=1.5,
        quote_status=QuoteStatus.OBSERVED,
        bid=1.49,
        ask=1.51,
        volume_type=VolumeType.BASE,
        volume=100.0,
        data_source="TEST",
    )
    bars = [b1, b2]
    # For this test, bypass warm-up check to just test digest determinism
    # wait, verify_and_digest_continuous_bars checks warmup length. Let's just create 721 bars.
    bars = []
    ts = 1570000000000
    for i in range(725):
        bars.append(MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp_utc=ts + i * 4 * 3600 * 1000,
            observed_at_utc=ts + i * 4 * 3600 * 1000,
            open=1.0, high=2.0, low=0.5, close=1.5,
            quote_status=QuoteStatus.OBSERVED, bid=1.49, ask=1.51,
            volume_type=VolumeType.BASE, volume=100.0,
            data_source="TEST",
        ))
    
    # 725 bars, eval_start_ms is ts + 722 * 4h -> 722 warmup bars
    digest1 = verify_and_digest_continuous_bars(bars, ts + 722 * 4 * 3600 * 1000, Timeframe.H4, "BINANCE_SPOT", min_warmup_bars=720)
    digest2 = verify_and_digest_continuous_bars(bars, ts + 722 * 4 * 3600 * 1000, Timeframe.H4, "BINANCE_SPOT", min_warmup_bars=720)
    assert digest1 == digest2
    assert len(digest1) == 64

def test_unregistered_gaps_fail():
    bars = []
    ts = 1570000000000
    for i in range(725):
        bars.append(MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp_utc=ts + i * 4 * 3600 * 1000,
            observed_at_utc=ts + i * 4 * 3600 * 1000,
            open=1.0, high=2.0, low=0.5, close=1.5,
            quote_status=QuoteStatus.OBSERVED, bid=1.49, ask=1.51,
            volume_type=VolumeType.BASE, volume=100.0,
            data_source="TEST",
        ))
    
    # create gap
    bars[500] = MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        timeframe=Timeframe.H4,
        timestamp_utc=bars[500].timestamp_utc + 4 * 3600 * 1000,
        observed_at_utc=bars[500].timestamp_utc + 4 * 3600 * 1000,
        open=1.0, high=2.0, low=0.5, close=1.5,
        quote_status=QuoteStatus.OBSERVED, bid=1.49, ask=1.51,
        volume_type=VolumeType.BASE, volume=100.0,
        data_source="TEST",
    )
    bars.sort(key=lambda b: b.timestamp_utc)
    
    with pytest.raises(ValueError, match="Unregistered gap found"):
        verify_and_digest_continuous_bars(bars, ts + 722 * 4 * 3600 * 1000, Timeframe.H4, "BINANCE_SPOT", min_warmup_bars=720)

def test_insufficient_warmup_fails():
    bars = []
    ts = 1570000000000
    for i in range(100):
        bars.append(MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp_utc=ts + i * 4 * 3600 * 1000,
            observed_at_utc=ts + i * 4 * 3600 * 1000,
            open=1.0, high=2.0, low=0.5, close=1.5,
            quote_status=QuoteStatus.OBSERVED, bid=1.49, ask=1.51,
            volume_type=VolumeType.BASE, volume=100.0,
            data_source="TEST",
        ))
    with pytest.raises(ValueError, match="Insufficient continuous warm-up bars"):
        verify_and_digest_continuous_bars(bars, ts + 100 * 4 * 3600 * 1000, Timeframe.H4, "BINANCE_SPOT", min_warmup_bars=720)

def run_backtest_with_manifest(db_path, manifest_path, **kwargs):
    cmd = [
        "python", "tools/run_trend_backtest.py",
        "--database", db_path,
        "--manifest", manifest_path,
        "--asset-class", "CRYPTO",
        "--venue", "BINANCE_SPOT",
        "--symbol", "BTCUSDT",
        "--timeframe", "4h",
        "--taker-fee", "0.0",
        "--half-spread", "0.0",
        "--slippage", "0.0"
    ]
    for k, v in kwargs.items():
        cmd.extend([f"--{k}", str(v)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result

def test_runner_manifest_validation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    manifest_path = tmp_path / "manifest.json"
    
    ts = 1570000000000
    bars = []
    for i in range(750):
        bars.append(MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp_utc=ts + i * 4 * 3600 * 1000,
            observed_at_utc=ts + i * 4 * 3600 * 1000,
            open=1.0, high=2.0, low=0.5, close=1.5,
            quote_status=QuoteStatus.OBSERVED, bid=1.49, ask=1.51,
            volume_type=VolumeType.BASE, volume=100.0,
            data_source="TEST",
        ))
    
    # insert extra pre-gap rows to test rule #1 and #3
    extra_bars = []
    for i in range(100):
        extra_bars.append(MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp_utc=ts - 200 * 4 * 3600 * 1000 + i * 4 * 3600 * 1000,
            observed_at_utc=ts - 200 * 4 * 3600 * 1000 + i * 4 * 3600 * 1000,
            open=1.0, high=2.0, low=0.5, close=1.5,
            quote_status=QuoteStatus.OBSERVED, bid=1.49, ask=1.51,
            volume_type=VolumeType.BASE, volume=100.0,
            data_source="TEST",
        ))

    with SQLiteStorage(str(db_path)) as store:
        store.insert_market_bars(extra_bars + bars)
        
    eval_start = ts + 725 * 4 * 3600 * 1000
    digest = verify_and_digest_continuous_bars(bars, eval_start, Timeframe.H4, "BINANCE_SPOT", min_warmup_bars=720)
    
    manifest_data = {
        "components": [{
            "asset_class": "CRYPTO",
            "venue": "BINANCE_SPOT",
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "start_timestamp_utc": bars[0].timestamp_utc,
            "end_timestamp_utc": bars[-1].timestamp_utc + 4 * 3600 * 1000,
            "row_count": len(bars),
            "digest": digest
        }]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
        
    # Valid run
    res = run_backtest_with_manifest(str(db_path), str(manifest_path), 
                                     **{"start-ms": bars[0].timestamp_utc, "end-ms": bars[-1].timestamp_utc + 4 * 3600 * 1000, "eval-start-ms": eval_start})
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Loaded 750 bars from local storage" in res.stdout
    
    # The exact manifest rows are passed (extra_bars didn't enter)
    # The total in sqlite is 850, but we loaded 750.
    
    # Boundary mismatch fails
    res = run_backtest_with_manifest(str(db_path), str(manifest_path), 
                                     **{"start-ms": bars[0].timestamp_utc - 4*3600*1000, "end-ms": bars[-1].timestamp_utc + 4 * 3600 * 1000, "eval-start-ms": eval_start})
    assert res.returncode != 0
    assert "Error: CLI boundaries conflict with the manifest" in res.stdout
    
    # Row-count mismatch fails
    manifest_data["components"][0]["row_count"] = 999
    with open(manifest_path, "w") as f: json.dump(manifest_data, f)
    res = run_backtest_with_manifest(str(db_path), str(manifest_path), 
                                     **{"start-ms": bars[0].timestamp_utc, "end-ms": bars[-1].timestamp_utc + 4 * 3600 * 1000, "eval-start-ms": eval_start})
    assert res.returncode != 0
    assert "Row count differs from manifest" in res.stdout
    
    # Digest mismatch fails
    manifest_data["components"][0]["row_count"] = len(bars)
    manifest_data["components"][0]["digest"] = digest.replace("a", "b")
    with open(manifest_path, "w") as f: json.dump(manifest_data, f)
    res = run_backtest_with_manifest(str(db_path), str(manifest_path), 
                                     **{"start-ms": bars[0].timestamp_utc, "end-ms": bars[-1].timestamp_utc + 4 * 3600 * 1000, "eval-start-ms": eval_start})
    assert res.returncode != 0
    assert "Computed digest differs from manifest" in res.stdout
    
    # Malformed digest
    manifest_data["components"][0]["digest"] = "short"
    with open(manifest_path, "w") as f: json.dump(manifest_data, f)
    res = run_backtest_with_manifest(str(db_path), str(manifest_path), 
                                     **{"start-ms": bars[0].timestamp_utc, "end-ms": bars[-1].timestamp_utc + 4 * 3600 * 1000, "eval-start-ms": eval_start})
    assert res.returncode != 0
    assert "Manifest digest is malformed" in res.stdout
    
    # Missing component
    manifest_data["components"][0]["symbol"] = "ETHUSDT"
    with open(manifest_path, "w") as f: json.dump(manifest_data, f)
    res = run_backtest_with_manifest(str(db_path), str(manifest_path), 
                                     **{"start-ms": bars[0].timestamp_utc, "end-ms": bars[-1].timestamp_utc + 4 * 3600 * 1000, "eval-start-ms": eval_start})
    assert res.returncode != 0
    assert "Manifest component missing or ambiguous" in res.stdout




def test_manifest_overwrite_protection(tmp_path, monkeypatch) -> None:
    import json
    import subprocess
    import sys
    from pathlib import Path
    
    # Run build script with dummy database
    # It should fail if manifest exists and no --overwrite
    manifest_path = Path("artifacts/cycle_02/manifests/TREND_PILOT_02_COMBINED.json")
    if not manifest_path.parent.exists():
        manifest_path.parent.mkdir(parents=True)
    if not manifest_path.exists():
        manifest_path.write_text("{}")
    
    # We patch the script so that we don't need actual DB
    # Just run it using subprocess but patch MARKETS to be empty
    test_script = tmp_path / "test_build.py"
    with open("tools/build_trend_pilot_dataset.py", "r") as f:
        src = f.read()
    src = src.replace("if len(manifests) != 4:", "if False:")
    test_script.write_text(src)

    res = subprocess.run(
        [sys.executable, str(test_script)],
        capture_output=True,
        text=True
    )
    assert res.returncode != 0
    assert "already exists" in res.stderr or "already exists" in res.stdout or "FileExistsError" in res.stderr
