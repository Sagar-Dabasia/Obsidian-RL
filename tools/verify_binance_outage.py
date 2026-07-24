import urllib.request
import hashlib
import zipfile
import io
from datetime import datetime, timezone

URLS = {
    "BTCUSDT": "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-2019-03.zip",
    "ETHUSDT": "https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/4h/ETHUSDT-4h-2019-03.zip"
}

def verify_archive(symbol, url):
    print(f"Downloading {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = response.read()

    timestamp = datetime.now(timezone.utc).isoformat()
    sha256 = hashlib.sha256(data).hexdigest()

    # Check rows
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csv_filename = z.namelist()[0]
        with z.open(csv_filename) as f:
            content = f.read().decode('utf-8')

    rows = [line.split(',') for line in content.split('\n') if line.strip()]
    row_count = len(rows)

    timestamps = [int(r[0]) for r in rows]

    has_00 = 1552348800000 in timestamps
    has_04 = 1552363200000 in timestamps
    has_08 = 1552377600000 in timestamps

    print(f"[{symbol}] SHA-256: {sha256}")
    print(f"[{symbol}] Retrieval: {timestamp}")
    print(f"[{symbol}] Row count: {row_count}")
    print(f"[{symbol}] 00:00 (1552348800000) exists: {has_00}")
    print(f"[{symbol}] 04:00 (1552363200000) missing: {not has_04}")
    print(f"[{symbol}] 08:00 (1552377600000) exists: {has_08}")

    return {
        "symbol": symbol,
        "url": url,
        "sha256": sha256,
        "timestamp": timestamp,
        "row_count": row_count,
        "00_exists": has_00,
        "04_absent": not has_04,
        "08_exists": has_08,
    }

def main():
    results = []
    for sym, url in URLS.items():
        results.append(verify_archive(sym, url))

    # Write evidence record
    evidence_path = "docs/cycle_02/research/BINANCE_2019_03_12_OUTAGE_EVIDENCE.md"
    with open(evidence_path, "w") as f:
        f.write("# Binance System Upgrade Evidence (March 12, 2019)\n\n")
        f.write("Official notice ID: 360024825992\n")
        f.write("Completion notice ID: 360024907012\n\n")

        for r in results:
            f.write(f"## {r['symbol']}\n")
            f.write(f"- URL: {r['url']}\n")
            f.write(f"- SHA-256: {r['sha256']}\n")
            f.write(f"- Retrieval: {r['timestamp']}\n")
            f.write(f"- Row count: {r['row_count']}\n")
            f.write(f"- 1552348800000 exists: {r['00_exists']}\n")
            f.write(f"- 1552363200000 absent: {r['04_absent']}\n")
            f.write(f"- 1552377600000 exists: {r['08_exists']}\n\n")

    print(f"Evidence written to {evidence_path}")

if __name__ == "__main__":
    main()
