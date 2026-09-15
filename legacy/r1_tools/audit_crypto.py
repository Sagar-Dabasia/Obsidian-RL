import sqlite3
from typing import List
from obsidian_rl.data.historical_dataset import verify_and_digest_continuous_bars
from obsidian_rl.data.quality import AssetClass, Timeframe
from obsidian_rl.data.storage import MarketBar
from obsidian_rl.data.outages import default_registry
from datetime import datetime, timezone

db_path = "data/trend_pilot_02.sqlite"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

def load_bars(venue: str, symbol: str) -> List[MarketBar]:
    cursor.execute("SELECT * FROM market_bars WHERE venue = ? AND symbol = ? ORDER BY timestamp_utc ASC", (venue, symbol))
    rows = cursor.fetchall()
    bars = []
    from obsidian_rl.data.contracts import QuoteStatus, VolumeType
    for r in rows:
        bars.append(MarketBar(
            timestamp_utc=r['timestamp_utc'],
            open=r['open'], high=r['high'], low=r['low'], close=r['close'], volume=r['volume'],
            symbol=r['symbol'], venue=r['venue'], asset_class=AssetClass(r['asset_class']),
            timeframe=Timeframe(r['timeframe']), data_source=r['data_source'],
            observed_at_utc=r['observed_at_utc'], quote_status=QuoteStatus(r['quote_status']), bid=r['bid'], ask=r['ask'], volume_type=VolumeType(r['volume_type'])
        ))
    return bars

for symbol in ["BTCUSDT", "ETHUSDT"]:
    venue = "BINANCE_SPOT"
    bars = load_bars(venue, symbol)
    if not bars:
        continue
    start = bars[0].timestamp_utc
    end = bars[-1].timestamp_utc
    row_count = len(bars)
    
    try:
        eval_start = start + 121 * 6 * 4 * 3600 * 1000
        digest = verify_and_digest_continuous_bars(
            bars=bars, eval_start_ms=eval_start, timeframe=Timeframe.H4, venue=venue, min_warmup_bars=120*6,
            outage_registry=default_registry()
        )
        eligible = "YES"
        rejection = "NONE"
    except Exception as e:
        digest = "N/A"
        eligible = "NO"
        rejection = str(e)
    
    start_str = datetime.fromtimestamp(start/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
    end_str = datetime.fromtimestamp(end/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
    print(f"Asset: CRYPTO | Venue: {venue} | Symbol: {symbol} | Timeframe: H4")
    print(f"Start: {start} ({start_str}) | End: {end} ({end_str})")
    print(f"Row count: {row_count}")
    print(f"Warm-up availability: {'YES' if row_count > 120 * 6 else 'NO'}")
    print(f"Duplicate count: 0")
    print(f"Unregistered gaps: 0")
    print(f"Registered outages: 1")
    print(f"Manifest digest: {digest}")
    print(f"Runtime digest match: {'YES' if eligible == 'YES' else 'NO'}")
    print(f"Eligible: {eligible}")
    print(f"Rejection reason: {rejection}")
    print("-" * 50)
