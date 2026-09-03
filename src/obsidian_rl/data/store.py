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

    # -- API ----------------------------------------------------------------
    def write(self, df: pd.DataFrame, *, source: str) -> WriteResult:
        """Merge candles into monthly partitions. Idempotent; conflicts raise."""
        df = coerce_candle_frame(df)
        if df.empty:
            return WriteResult(0, 0, [])
        df = df.sort_values("open_time").reset_index(drop=True)

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
            files = self._partition_files()
            if not files:
                return empty_candle_frame()
            frames = [pd.read_parquet(f) for f in files]
            df = pd.concat(frames, ignore_index=True).sort_values("open_time").reset_index(drop=True)
            if start_ms is not None:
                df = df[df["open_time"] >= start_ms]
            if end_ms is not None:
                df = df[df["open_time"] <= end_ms]
            return coerce_candle_frame(df)

    def max_open_time(self) -> int | None:
        files = self._partition_files()
        if not files:
            return None
        last = pd.read_parquet(files[-1], columns=["open_time"])
        return int(last["open_time"].max())

    def summary(self) -> dict[str, object]:
        df = self.read()
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
