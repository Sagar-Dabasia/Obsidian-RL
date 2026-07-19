"""Download orchestration: bulk monthly history + REST tail, incremental updates."""

import logging
import time
from datetime import UTC, datetime

import pandas as pd

from obsidian_rl.config import Settings
from obsidian_rl.data.binance_client import BinanceFuturesRest
from obsidian_rl.data.schema import interval_to_ms
from obsidian_rl.data.store import CandleStore
from obsidian_rl.data.validation import drop_unfinalized, require_valid
from obsidian_rl.data.vision import VisionBulkSource

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _month_range(start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    cur = datetime.fromtimestamp(start_ms / 1000, tz=UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end = datetime.fromtimestamp(end_ms / 1000, tz=UTC)
    while cur <= end:
        months.append((cur.year, cur.month))
        cur = (
            cur.replace(year=cur.year + 1, month=1)
            if cur.month == 12
            else cur.replace(month=cur.month + 1)
        )
    return months


def initial_download(
    settings: Settings,
    start_ms: int,
    end_ms: int | None = None,
    *,
    store: CandleStore | None = None,
    bulk: VisionBulkSource | None = None,
    rest: BinanceFuturesRest | None = None,
    now_ms: int | None = None,
) -> CandleStore:
    """Bulk-download [start_ms, end_ms] into the Parquet store (monthly zips + REST tail)."""
    now = now_ms if now_ms is not None else _now_ms()
    end = end_ms if end_ms is not None else now
    store = store or CandleStore(settings.data_dir, settings.symbol, settings.interval)
    bulk = bulk or VisionBulkSource(settings.vision_base_url, timeout_s=settings.request_timeout_s)
    rest = rest or BinanceFuturesRest(
        settings.fapi_base_url,
        timeout_s=settings.request_timeout_s,
        max_retries=settings.max_retries,
    )

    unpublished_from: int | None = None
    for year, month in _month_range(start_ms, end):
        frame = bulk.fetch_month(settings.symbol, settings.interval, year, month)
        if frame is None:
            unpublished_from = int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)
            logger.info("vision month %04d-%02d not published; switching to REST", year, month)
            break
        frame = frame[(frame["open_time"] >= start_ms) & (frame["open_time"] <= end)]
        if len(frame):
            require_valid(frame, settings.interval, now_ms=now)
            store.write(frame, source=f"vision:{year:04d}-{month:02d}")

    rest_from = unpublished_from
    latest = store.max_open_time()
    if latest is not None:
        rest_from = latest + interval_to_ms(settings.interval)
    elif rest_from is None:
        rest_from = start_ms
    if rest_from <= end:
        tail = rest.fetch_klines(settings.symbol, settings.interval, rest_from, end)
        tail = drop_unfinalized(tail, now)
        if len(tail):
            require_valid(tail, settings.interval, now_ms=now)
            store.write(tail, source="fapi:initial")
    return store


def incremental_update(
    settings: Settings,
    *,
    store: CandleStore | None = None,
    rest: BinanceFuturesRest | None = None,
    now_ms: int | None = None,
) -> int:
    """Fetch finalized candles after the stored maximum. Returns number of new rows."""
    now = now_ms if now_ms is not None else _now_ms()
    store = store or CandleStore(settings.data_dir, settings.symbol, settings.interval)
    latest = store.max_open_time()
    if latest is None:
        raise RuntimeError("store is empty — run the initial download first")
    rest = rest or BinanceFuturesRest(
        settings.fapi_base_url,
        timeout_s=settings.request_timeout_s,
        max_retries=settings.max_retries,
    )
    start = latest + interval_to_ms(settings.interval)
    df = rest.fetch_klines(settings.symbol, settings.interval, start)
    df = drop_unfinalized(df, now)
    if df.empty:
        return 0
    require_valid(df, settings.interval, now_ms=now)
    result = store.write(df, source="fapi:update")
    return result.rows_new


def dataset_gap_frame(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Convenience: gap list as a frame for reporting."""
    from obsidian_rl.data.validation import validate_candles

    rep = validate_candles(df, interval)
    return pd.DataFrame(rep.gaps, columns=["last_open_before_gap", "next_open_after_gap"])
