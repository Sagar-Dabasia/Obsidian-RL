"""Bulk historical klines from data.binance.vision (futures/um monthly zips).

Each monthly zip contains one CSV with the same 12 kline fields as the REST API and is
verified against its published SHA256 .CHECKSUM before use. Timestamp unit is detected
explicitly (ms vs us) and recorded; values are normalized to milliseconds.
"""

import csv
import hashlib
import io
import logging
import zipfile
from collections.abc import Callable

import pandas as pd
import requests

from obsidian_rl.data.binance_client import DataFetchError
from obsidian_rl.data.schema import klines_to_frame

logger = logging.getLogger(__name__)

# Epoch ms for year ~2100; open_time values above this are microseconds.
_US_THRESHOLD = 4_102_444_800_000


def monthly_zip_url(base_url: str, symbol: str, interval: str, year: int, month: int) -> str:
    return (
        f"{base_url.rstrip('/')}/data/futures/um/monthly/klines/"
        f"{symbol}/{interval}/{symbol}-{interval}-{year:04d}-{month:02d}.zip"
    )


def _download(url: str, session: requests.Session, timeout_s: float) -> bytes | None:
    """Fetch a URL; None for 404 (month not published), DataFetchError otherwise."""
    try:
        resp = session.get(url, timeout=timeout_s)
    except requests.RequestException as exc:
        raise DataFetchError(f"download failed for {url}: {exc}") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise DataFetchError(f"download failed for {url}: HTTP {resp.status_code}")
    return resp.content


def _verify_checksum(payload: bytes, checksum_text: str, url: str) -> None:
    expected = checksum_text.strip().split()[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise DataFetchError(f"SHA256 mismatch for {url}: expected {expected}, got {actual}")


def _parse_zip_csv(payload: bytes) -> list[list[object]]:
    rows: list[list[object]] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise DataFetchError(f"expected 1 file in zip, found {names}")
        with zf.open(names[0]) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8")
            reader = csv.reader(text)
            for row in reader:
                if not row:
                    continue
                if row[0].strip().lower() in ("open_time", "opentime"):
                    continue  # newer files carry a header row
                rows.append(list(row))
    return rows


def _normalize_timestamp_unit(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) and int(df["open_time"].iloc[0]) > _US_THRESHOLD:
        logger.info("timestamps detected as microseconds; converting to ms")
        df = df.copy()
        df["open_time"] = df["open_time"] // 1000
        df["close_time"] = df["close_time"] // 1000
    return df


class VisionBulkSource:
    """Monthly bulk kline downloads with mandatory checksum verification."""

    def __init__(
        self,
        base_url: str = "https://data.binance.vision",
        *,
        session: requests.Session | None = None,
        timeout_s: float = 60.0,
        downloader: Callable[[str, requests.Session, float], bytes | None] = _download,
    ) -> None:
        self._base = base_url
        self._session = session or requests.Session()
        self._timeout = timeout_s
        self._download = downloader

    def fetch_month(self, symbol: str, interval: str, year: int, month: int) -> pd.DataFrame | None:
        """Fetch one month. None if the month is not published (404). Raises on any failure."""
        url = monthly_zip_url(self._base, symbol, interval, year, month)
        payload = self._download(url, self._session, self._timeout)
        if payload is None:
            return None
        checksum = self._download(url + ".CHECKSUM", self._session, self._timeout)
        if checksum is None:
            raise DataFetchError(f"checksum file missing for {url}")
        _verify_checksum(payload, checksum.decode("utf-8"), url)
        frame = klines_to_frame(_parse_zip_csv(payload))
        return _normalize_timestamp_unit(frame)
