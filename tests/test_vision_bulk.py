"""Vision bulk download tests with in-memory zips and checksum verification. No network."""

import hashlib
import io
import zipfile

import pytest
import requests

from obsidian_rl.data.binance_client import DataFetchError
from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.data.vision import VisionBulkSource, monthly_zip_url

MS15 = interval_to_ms("15m")


def make_zip(csv_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BTCUSDT-15m-2024-01.csv", csv_text)
    return buf.getvalue()


def csv_rows(start_ms: int, n: int, header: bool = False) -> str:
    lines = []
    if header:
        lines.append(
            "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
            "taker_buy_volume,taker_buy_quote_volume,ignore"
        )
    for i in range(n):
        ot = start_ms + i * MS15
        lines.append(f"{ot},100,101,99,100.5,10,{ot + MS15 - 1},1005,5,5,502,0")
    return "\n".join(lines) + "\n"


def make_source(files: dict[str, bytes]) -> VisionBulkSource:
    def downloader(url: str, session: requests.Session, timeout: float) -> bytes | None:
        return files.get(url)

    return VisionBulkSource("https://example.invalid", downloader=downloader)


def url_for() -> str:
    return monthly_zip_url("https://example.invalid", "BTCUSDT", "15m", 2024, 1)


def test_fetch_month_verifies_checksum_and_parses() -> None:
    payload = make_zip(csv_rows(1_704_067_200_000, 20))
    digest = hashlib.sha256(payload).hexdigest()
    files = {url_for(): payload, url_for() + ".CHECKSUM": f"{digest}  x.zip".encode()}
    df = make_source(files).fetch_month("BTCUSDT", "15m", 2024, 1)
    assert df is not None and len(df) == 20
    assert int(df["open_time"].iloc[0]) == 1_704_067_200_000


def test_header_row_skipped() -> None:
    payload = make_zip(csv_rows(1_704_067_200_000, 5, header=True))
    digest = hashlib.sha256(payload).hexdigest()
    files = {url_for(): payload, url_for() + ".CHECKSUM": digest.encode()}
    df = make_source(files).fetch_month("BTCUSDT", "15m", 2024, 1)
    assert df is not None and len(df) == 5


def test_checksum_mismatch_raises() -> None:
    payload = make_zip(csv_rows(1_704_067_200_000, 5))
    files = {url_for(): payload, url_for() + ".CHECKSUM": b"deadbeef" * 8}
    with pytest.raises(DataFetchError, match="SHA256 mismatch"):
        make_source(files).fetch_month("BTCUSDT", "15m", 2024, 1)


def test_missing_month_returns_none() -> None:
    assert make_source({}).fetch_month("BTCUSDT", "15m", 2024, 1) is None


def test_missing_checksum_raises() -> None:
    payload = make_zip(csv_rows(1_704_067_200_000, 5))
    files = {url_for(): payload}
    with pytest.raises(DataFetchError, match="checksum file missing"):
        make_source(files).fetch_month("BTCUSDT", "15m", 2024, 1)


def test_microsecond_timestamps_normalized() -> None:
    start_us = 1_704_067_200_000_000
    lines = []
    for i in range(3):
        ot = start_us + i * MS15 * 1000
        lines.append(f"{ot},100,101,99,100.5,10,{ot + (MS15 - 1) * 1000},1005,5,5,502,0")
    payload = make_zip("\n".join(lines) + "\n")
    digest = hashlib.sha256(payload).hexdigest()
    files = {url_for(): payload, url_for() + ".CHECKSUM": digest.encode()}
    df = make_source(files).fetch_month("BTCUSDT", "15m", 2024, 1)
    assert df is not None
    assert int(df["open_time"].iloc[0]) == 1_704_067_200_000
