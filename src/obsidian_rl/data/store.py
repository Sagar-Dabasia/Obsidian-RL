"""Month-partitioned Parquet candle store with source metadata and idempotent merge.

Layout: <root>/klines/<SYMBOL>/<interval>/<YYYY>/<MM>.parquet plus one _meta.json per
symbol/interval recording sources, download timestamps, and row counts. Raw candles are
immutable: merging identical rows is a no-op; conflicting rows for the same open_time
raise instead of silently overwriting history.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from obsidian_rl.data.schema import coerce_candle_frame, empty_candle_frame
from obsidian_rl.data.research_access import (
    validate_temporal_access,
    DEV_TRAIN_START_MS,
    DEV_TRAIN_END_MS,
    ResearchAccessError,
)

_MS_PER_MONTH_KEY = "%Y/%m"


class StoreConflictError(RuntimeError):
    """Same open_time present with different values — refusing to rewrite history."""


@dataclass
class WriteResult:
    rows_written: int
    rows_new: int
    partitions: list[str]


class CandleStore:
    def __init__(self, root: Path, symbol: str, interval: str) -> None:
        self.symbol = symbol
        self.interval = interval
        self.base = Path(root) / "klines" / symbol / interval
        self.meta_path = self.base / "_meta.json"

    # -- internals ---------------------------------------------------------
    def _partition_path(self, year: int, month: int) -> Path:
        return self.base / f"{year:04d}" / f"{month:02d}.parquet"

    def _partition_files(self) -> list[Path]:
        if not self.base.exists():
            return []
        return sorted(self.base.glob("[0-9]" * 4 + "/[0-9][0-9].parquet"))

    def _load_meta(self) -> dict[str, object]:
        if self.meta_path.exists():
            return json.loads(self.meta_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        return {"symbol": self.symbol, "interval": self.interval, "writes": []}

    def _record_write(self, source: str, result: WriteResult) -> None:
        meta = self._load_meta()
        writes = meta.setdefault("writes", [])
        assert isinstance(writes, list)
        writes.append(
            {
                "source": source,
                "downloaded_at_utc_ms": int(time.time() * 1000),
                "rows_written": result.rows_written,
                "rows_new": result.rows_new,
                "partitions": result.partitions,
            }
        )
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")

    def _parse_partition_bounds(self, path: Path) -> tuple[int, int] | None:
        """Extract [start_ms, end_ms) bounds from partition file path.
        Returns None if path doesn't match expected format."""
        try:
            # path format: .../klines/SYMBOL/interval/YYYY/MM.parquet
            parts = path.parts
            if len(parts) < 2:
                return None
            year_str = parts[-2]
            month_str = parts[-1].replace(".parquet", "")
            year = int(year_str)
            month = int(month_str)
            # Calculate month bounds
            start_dt = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
            if month == 12:
                end_dt = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
            else:
                end_dt = pd.Timestamp(year=year, month=month + 1, day=1, tz="UTC")
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)
            return (start_ms, end_ms)
        except (ValueError, IndexError):
            return None

    def _filter_authorized_partitions(
            self, files: list[Path], start_ms: int, end_ms: int
        ) -> list[Path]:
            """Filter partition files to only those overlapping with authorized bounds.
            Returns partitions that overlap with the requested range.
            The final row-level filtering in read() handles exact bounds.
            """
            authorized = []
            for f in files:
                bounds = self._parse_partition_bounds(f)
                if bounds is None:
                    # Unknown format - skip conservatively
                    continue
                part_start, part_end = bounds
                # Partition overlaps with requested range (half-open intervals)?
                if part_start < end_ms and part_end > start_ms:
                    authorized.append(f)
            return authorized

    # -- API ---------------------------------------------------------------
    def write(self, df: pd.DataFrame, *, source: str) -> WriteResult:
        """Merge candles into monthly partitions. Idempotent; conflicts raise."""
        df = coerce_candle_frame(df)
        if df.empty:
            return WriteResult(0, 0, [])
        df = df.sort_values("open_time").reset_index(drop=True)

        # Validate write bounds before any partition access
        data_start = int(df["open_time"].min())
        data_end = int(df["open_time"].max()) + 1  # Half-open end
        validate_temporal_access(data_start, data_end)

        month_key = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.strftime(
            _MS_PER_MONTH_KEY
        )
        rows_new = 0
        partitions: list[str] = []
        for key, chunk in df.groupby(month_key):
            year, month = int(key[:4]), int(key[5:7])
            path = self._partition_path(year, month)
            if path.exists():
                existing = pd.read_parquet(path)
                merged = pd.concat([existing, chunk], ignore_index=True)
                merged = merged.sort_values("open_time").reset_index(drop=True)
                dup_all = merged.duplicated(keep="first")  # identical full rows
                dup_key = merged["open_time"].duplicated(keep="first")
                conflict = dup_key & ~dup_all
                if conflict.any():
                    bad = merged.loc[conflict, "open_time"].head(3).tolist()
                    raise StoreConflictError(
                        f"{self.symbol}/{self.interval} {key}: differing rows for open_time {bad}"
                    )
                deduped = merged[~dup_key].reset_index(drop=True)
                rows_new += len(deduped) - len(existing)
                out = deduped
            else:
                chunk = chunk.sort_values("open_time").reset_index(drop=True)
                dup_all = chunk.duplicated(keep="first")  # identical full rows
                dup_key = chunk["open_time"].duplicated(keep="first")
                conflict = dup_key & ~dup_all
                if conflict.any():
                    bad = chunk.loc[conflict, "open_time"].head(3).tolist()
                    raise StoreConflictError(
                        f"{self.symbol}/{self.interval} {key}: differing rows for open_time {bad}"
                    )
                deduped = chunk[~dup_key].reset_index(drop=True)
                rows_new += len(deduped)
                out = deduped
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            out.to_parquet(tmp, index=False)
            tmp.replace(path)
            partitions.append(key)

        result = WriteResult(rows_written=len(df), rows_new=rows_new, partitions=partitions)
        self._record_write(source, result)
        return result

    def read(self, start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
        # Cycle 2 research temporal access guard
        # Handle unbounded reads by using effective bounds
        effective_start = start_ms if start_ms is not None else 0
        effective_end = end_ms if end_ms is not None else (1 << 63) - 1  # Max int64
        validate_temporal_access(effective_start, effective_end)

        files = self._partition_files()
        if not files:
            return empty_candle_frame()
        # Filter to only partitions within the requested bounds
        authorized_files = self._filter_authorized_partitions(files, effective_start, effective_end)
        if not authorized_files:
            return empty_candle_frame()
        frames = [pd.read_parquet(f) for f in authorized_files]
        df = pd.concat(frames, ignore_index=True).sort_values("open_time").reset_index(drop=True)
        if start_ms is not None:
            df = df[df["open_time"] >= start_ms]
        if end_ms is not None:
            df = df[df["open_time"] < end_ms]  # Half-open: end exclusive
        return coerce_candle_frame(df)

    def max_open_time(self, start_ms: int | None = None, end_ms: int | None = None) -> int | None:
        """Return max open_time within the specified bounds (defaults to DEV_TRAIN).

        Only reads partitions fully within the authorized range.
        """
        effective_start = start_ms if start_ms is not None else DEV_TRAIN_START_MS
        effective_end = end_ms if end_ms is not None else DEV_TRAIN_END_MS
        validate_temporal_access(effective_start, effective_end)

        files = self._partition_files()
        if not files:
            return None
        # Filter to only partitions within the authorized bounds
        authorized_files = self._filter_authorized_partitions(files, effective_start, effective_end)
        if not authorized_files:
            return None
        # Read only the latest authorized partition
        last = pd.read_parquet(authorized_files[-1], columns=["open_time"])
        max_time = int(last["open_time"].max())
        # Ensure result is within the effective bounds
        if max_time >= effective_end:
            return effective_end - 1
        return max_time

    def summary(self, start_ms: int | None = None, end_ms: int | None = None) -> dict[str, object]:
        """Summarize candles within the specified bounds (defaults to DEV_TRAIN).

        Args:
            start_ms: Start timestamp (default: DEV_TRAIN start)
            end_ms: End timestamp (default: DEV_TRAIN end)

        Returns:
            Summary dict for the specified window.
        """
        effective_start = start_ms if start_ms is not None else DEV_TRAIN_START_MS
        effective_end = end_ms if end_ms is not None else DEV_TRAIN_END_MS
        df = self.read(start_ms=effective_start, end_ms=effective_end)
        if df.empty:
            return {"symbol": self.symbol, "interval": self.interval, "rows": 0}
        from obsidian_rl.data.validation import validate_candles

        rep = validate_candles(df, self.interval)
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "rows": len(df),
            "start_utc": str(pd.to_datetime(df["open_time"].iloc[0], unit="ms", utc=True)),
            "end_utc": str(pd.to_datetime(df["open_time"].iloc[-1], unit="ms", utc=True)),
            "gaps": len(rep.gaps),
            "missing_candles": rep.n_missing_candles,
            "validation_errors": rep.errors,
            "partitions": len(self._partition_files()),
        }