import sqlite3
c = sqlite3.connect('data/trend_pilot_01.sqlite')
c.row_factory = sqlite3.Row
r = c.execute("SELECT timestamp_utc FROM market_bars WHERE symbol='BTCUSDT' ORDER BY timestamp_utc").fetchall()
gaps = [(r[i]['timestamp_utc'], r[i-1]['timestamp_utc']) for i in range(1, len(r)) if r[i]['timestamp_utc'] - r[i-1]['timestamp_utc'] != 14400000]
print(gaps)
