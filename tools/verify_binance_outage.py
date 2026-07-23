"""Verify the Binance 2020-02-19 outage using the official public kline archive.

Downloads daily 4h kline CSVs from https://data.binance.vision/ and checks
whether the 1582113600000 timestamp is present for BTCUSDT and ETHUSDT.

No trading, no credentials, no paid resources.
"""

import csv
import hashlib
import io
import sys
import zipfile
from urllib.request import urlopen

# The outage timestamp we need to verify
OUTAGE_TS_MS = 1582113600000  # 2020-02-19T12:00:00Z

# Binance public kline archive URLs (free, no auth)
# Format: monthly klines for 4h
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = "4h"
MONTH = "2020-02"


def download_and_check(symbol: str) -> tuple[bool, str, int]:
    """Download monthly kline zip, extract CSV, check for outage timestamp.

    Returns (timestamp_missing, content_sha256, total_rows).
    """
    url = f"{BASE_URL}/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{MONTH}.zip"
    print(f"Downloading: {url}")

    response = urlopen(url)
    raw = response.read()
    content_hash = hashlib.sha256(raw).hexdigest()
    print(f"  SHA-256: {content_hash}")
    print(f"  Size: {len(raw)} bytes")

    # Extract CSV from zip
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csv_names = zf.namelist()
        assert len(csv_names) == 1, f"Expected 1 CSV, got {csv_names}"
        csv_name = csv_names[0]
        csv_data = zf.read(csv_name).decode("utf-8")

    # Parse CSV: columns are open_time, open, high, low, close, volume, ...
    reader = csv.reader(io.StringIO(csv_data))
    timestamps = []
    for row in reader:
        if not row:
            continue
        try:
            ts = int(row[0])
            timestamps.append(ts)
        except (ValueError, IndexError):
            continue

    total_rows = len(timestamps)
    timestamp_missing = OUTAGE_TS_MS not in timestamps

    return timestamp_missing, content_hash, total_rows


def main() -> None:
    print("=" * 60)
    print("Binance Outage Verification: 2020-02-19T12:00:00Z")
    print(f"Target timestamp: {OUTAGE_TS_MS}")
    print("=" * 60)
    print()

    results = {}
    for symbol in SYMBOLS:
        try:
            missing, sha, rows = download_and_check(symbol)
            results[symbol] = {
                "missing": missing,
                "sha256": sha,
                "rows": rows,
            }
            status = "MISSING (outage confirmed)" if missing else "PRESENT (no outage)"
            print(f"  {symbol}: {OUTAGE_TS_MS} is {status}")
            print(f"  Total rows: {rows}")
            print()
        except Exception as e:
            print(f"  {symbol}: DOWNLOAD FAILED: {e}")
            results[symbol] = {"missing": None, "sha256": None, "rows": 0}
            print()

    # Verdict
    print("=" * 60)
    all_missing = all(r["missing"] is True for r in results.values())
    if all_missing:
        print("VERDICT: Outage INDEPENDENTLY VERIFIED")
        print("  The timestamp 1582113600000 is missing from ALL symbols.")
        print("  This confirms a venue-wide outage, not a symbol-specific issue.")
    else:
        print("VERDICT: Outage NOT confirmed venue-wide")
        for sym, r in results.items():
            print(f"  {sym}: missing={r['missing']}")

    print("=" * 60)

    if not all_missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
