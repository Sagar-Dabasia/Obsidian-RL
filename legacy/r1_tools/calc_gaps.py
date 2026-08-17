from datetime import datetime, timezone

gaps = [
    (1577224800000, 1577311200000),
    (1577829600000, 1577916000000),
    (1608847200000, 1609106400000),
    (1609452000000, 1609711200000),
    (1671832800000, 1672092000000),
    (1703282400000, 1703541600000)
]

for start, end in gaps:
    timestamps = list(range(start, end, 4*3600*1000))
    dates = [datetime.fromtimestamp(t/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M') for t in timestamps]
    print(f"[{start}, {end}]: {dates[0]} to {datetime.fromtimestamp(end/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("Missing timestamps:", dates)
    print()
