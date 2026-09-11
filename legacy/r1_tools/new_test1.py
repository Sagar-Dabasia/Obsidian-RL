import hashlib
from obsidian_rl.data.historical_dataset import verify_and_digest_continuous_bars

def test_no_synthetic_row_introduced() -> None:
    from obsidian_rl.data.contracts import MarketBar, AssetClass, Timeframe, QuoteStatus, VolumeType
    from obsidian_rl.data.outages import default_registry
    reg = default_registry()

    def make_test_bar(ts: int, close: float) -> MarketBar:
        b = MarketBar(
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp_utc=ts,
            observed_at_utc=ts,
            open=close,
            high=close,
            low=close,
            close=close,
            quote_status=QuoteStatus.OBSERVED,
            volume=1.0,
            volume_type=VolumeType.BASE,
            bid=close,
            ask=close,
            data_source="TEST",
            schema_version="SCHEMA_V2",
            row_hash=""
        )
        object.__setattr__(b, "row_hash", "hash_" + str(ts))
        return b
        
    bars = []
    # Generate 800 continuous bars up to 1552348800000 (inclusive)
    # So the last one is 1552348800000
    ts = 1552348800000 - 799 * 4 * 3600 * 1000
    for i in range(800):
        bars.append(make_test_bar(ts + i * 4 * 3600 * 1000, 100.0))
        
    # the last one is exactly 1552348800000
    
    # next one after the missing bar
    b_after = make_test_bar(1552377600000, 100.0)
    bars.append(b_after)
    
    # Eval start is some time before the gap
    eval_start_ms = 1552348800000 - 10 * 4 * 3600 * 1000
    
    # This should pass without raising ValueError
    digest = verify_and_digest_continuous_bars(bars, eval_start_ms, Timeframe.H4, "BINANCE_SPOT", outage_registry=reg, min_warmup_bars=720)
    
    # 1. returned row count equals authentic input count (it's in place, so len(bars) unchanged)
    assert len(bars) == 801
    # 2. returned timestamps equal authentic input timestamps
    assert bars[-2].timestamp_utc == 1552348800000
    assert bars[-1].timestamp_utc == 1552377600000
    # 3. missing candle remains absent (no 1552363200000)
    assert not any(b.timestamp_utc == 1552363200000 for b in bars)
    # 4. row hashes remain unchanged
    assert bars[-2].row_hash == "hash_1552348800000"
    assert bars[-1].row_hash == "hash_1552377600000"
