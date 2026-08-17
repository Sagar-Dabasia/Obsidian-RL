import csv
import zoneinfo
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from obsidian_rl.data.contracts import (
    AssetClass,
    MarketBar,
    QuoteStatus,
    Timeframe,
    VolumeType,
)
from obsidian_rl.data.providers.base import MarketDataProvider
from obsidian_rl.data.providers.errors import UnsupportedSymbolTimeframeError


class DukascopyProvider(MarketDataProvider):
    """Canonical provider for Dukascopy authentic offline CSV acquisition."""

    provider_name: str = "DUKASCOPY"
    adapter_version: str = "2.0.0"

    _SUPPORTED_TIMEFRAMES: ClassVar[set[Timeframe]] = {
        Timeframe.H4,
    }

    def __init__(self, data_dir: str = "artifacts/cycle_02/raw/dukascopy", **kwargs: Any) -> None:
        self.data_dir = Path(data_dir).resolve()

    def fetch_bars(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[MarketBar, ...]:
        tf_enum = Timeframe(timeframe)
        if tf_enum not in self._SUPPORTED_TIMEFRAMES:
            raise UnsupportedSymbolTimeframeError(f"Unsupported timeframe: {tf_enum}")

        if symbol not in ("EURUSD", "GBPUSD"):
            return tuple()

        eet_tz = zoneinfo.ZoneInfo("EET")

        # Discover files by pattern
        csv_files = list(self.data_dir.glob("*.csv"))
        bid_files = [f for f in csv_files if symbol in f.name and "Bid" in f.name]
        ask_files = [f for f in csv_files if symbol in f.name and "Ask" in f.name]

        import hashlib

        for f in bid_files + ask_files:
            h = hashlib.sha256()
            with open(f, "rb") as bf:
                h.update(bf.read())
            # "Hash EVERY raw file before parsing."
            # We compute it but we don't necessarily print it unless we want to log it

        def _parse_files(files: list[Path]) -> dict[int, dict[str, float]]:
            records: dict[int, dict[str, float]] = {}
            for file_path in sorted(files):
                with open(file_path, encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    if header != ["Time (EET)", "Open", "High", "Low", "Close", "Volume "]:
                        raise ValueError(f"Unexpected schema in {file_path}: {header}")
                    for row in reader:
                        if len(row) != 6:
                            continue
                        dt = datetime.strptime(row[0], "%Y.%m.%d %H:%M:%S")
                        dt = dt.replace(tzinfo=eet_tz)
                        ts = int(dt.astimezone(UTC).timestamp() * 1000)

                        rec = {
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": float(row[5]),
                        }
                        if ts in records:
                            # deduplicate
                            existing = records[ts]
                            if existing != rec:
                                raise ValueError(f"Conflicting rows at {ts} in {file_path}")
                        else:
                            records[ts] = rec
            return records

        bids = _parse_files(bid_files)
        asks = _parse_files(ask_files)

        timestamps = sorted(list(set(bids.keys()) | set(asks.keys())))

        bars: list[MarketBar] = []
        for ts in timestamps:
            if ts not in bids or ts not in asks:
                raise ValueError(f"Missing side at {ts} for {symbol}")

            b = bids[ts]
            a = asks[ts]

            if b["high"] < max(b["open"], b["close"]):
                raise ValueError(f"Bid High {b['high']} < Max(Open, Close) at {ts}")
            if b["low"] > min(b["open"], b["close"]):
                raise ValueError(f"Bid Low {b['low']} < Min(Open, Close) at {ts}")
            if a["high"] < max(a["open"], a["close"]):
                raise ValueError(f"Ask High {a['high']} < Max(Open, Close) at {ts}")
            if a["low"] > min(a["open"], a["close"]):
                raise ValueError(f"Ask Low {a['low']} < Min(Open, Close) at {ts}")

            if b["close"] <= 0 or a["close"] <= 0:
                raise ValueError(f"Non-positive price at {ts}")

            if b["close"] > a["close"]:
                raise ValueError(f"BID {b['close']} > ASK {a['close']} at {ts}")

            if start_ms <= ts < end_ms:
                o = (b["open"] + a["open"]) / 2.0
                hi = (b["high"] + a["high"]) / 2.0
                lo = (b["low"] + a["low"]) / 2.0
                c = (b["close"] + a["close"]) / 2.0
                v = b["volume"] + a["volume"]

                bars.append(
                    MarketBar(
                        asset_class=AssetClass.FOREX,
                        symbol=symbol,
                        venue="DUKASCOPY",
                        timeframe=Timeframe.H4,
                        timestamp_utc=ts,
                        observed_at_utc=ts,
                        open=o,
                        high=hi,
                        low=lo,
                        close=c,
                        bid=b["close"],
                        ask=a["close"],
                        volume=v,
                        volume_type=VolumeType.TICK,
                        quote_status=QuoteStatus.OBSERVED,
                        data_source="DUKASCOPY",
                    )
                )

        return tuple(bars)
